"""Unified forward pass: replay payments against the schedule.

Builds settlements, installment snapshots, and derived state by
processing each payment chronologically.  Also contains coverage
helpers, installment construction, and tolerance adjustment logic
that the forward pass depends on.

Data flow is strictly unidirectional: ``CashFlow`` and the static
schedule feed ``compute_state``, which produces ``Settlement`` objects.
The public ``Installment`` view is a projection built downstream of
those settlements by :func:`build_installments`. Inside the forward
pass the allocator is fed only ``_InstallmentExpectation`` primitives
— it never reads back a public ``Installment``.
"""

from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from typing import Dict, List, Optional, Set, Tuple

from ..cash_flow import CashFlow, CashFlowItem
from ..models import Allocation, Installment, Settlement
from ..scheduler import PaymentSchedule, PaymentScheduleEntry
from ..time_context import TimeContext
from ..types.interest_rate import InterestRate
from ..types.money import Money
from ..tz import to_date, to_datetime
from ..working_day import EveryDayCalendar, WorkingDayCalendar, effective_penalty_due_date
from .allocation import _InstallmentExpectation, allocate_payment_into_installments
from .constants import BALANCE_TOLERANCE
from .fines import compute_fines_at, is_payment_late
from .interest import InterestCalculator, MoraRateCallback

_DEFAULT_CALENDAR = EveryDayCalendar()


@dataclass(frozen=True)
class LoanState:
    """Snapshot of derived loan state from the forward pass."""

    settlements: List[Settlement]
    principal_balance: Money
    fines_applied: Dict[date, Money]
    fines_paid_total: Money
    last_payment_date: datetime
    last_accrual_end: datetime
    overpaid: Money


# ------------------------------------------------------------------
# Coverage
# ------------------------------------------------------------------


def principal_covered_count(
    remaining_balance: Money,
    schedule: PaymentSchedule,
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> int:
    """How many due dates have their principal covered given a remaining balance.

    *balance_tolerance* lets the caller override the sub-cent threshold
    used when comparing the running balance to scheduled ending
    balances. Defaults to the engine constant.
    """
    covered = 0
    for entry in schedule:
        if remaining_balance <= entry.ending_balance + balance_tolerance:
            covered += 1
        else:
            break
    return covered


def fully_covered_count(
    installments: List[Installment],
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> int:
    """Count consecutive fully-paid installments from the start.

    Unlike :func:`principal_covered_count`, this checks **all** obligations
    (principal, interest, mora, fine) via :attr:`Installment.is_fully_paid`.
    Sub-cent rounding artifacts within *balance_tolerance* are tolerated.
    """
    count = 0
    for inst in installments:
        if inst.is_fully_paid or inst.balance <= balance_tolerance:
            count += 1
        else:
            break
    return count


# ------------------------------------------------------------------
# Skipped contractual interest
# ------------------------------------------------------------------


def _skipped_contractual_interest(
    expectations: List[_InstallmentExpectation],
    next_due: Optional[date],
    cutoff: date,
) -> Money:
    """Sum unpaid contractual interest for installments past *next_due*.

    Returns the total ``expected_interest - interest_paid`` for every
    installment whose due date falls strictly after *next_due* and on
    or before *cutoff*. These are periods that the interest calculator
    cannot reach because it only considers one due-date boundary.
    """
    if next_due is None:
        return Money.zero()
    total = Money.zero()
    for exp in expectations:
        if exp.due_date > next_due and exp.due_date <= cutoff:
            owed = exp.expected_interest - exp.interest_paid
            if owed.is_positive():
                total = total + owed
    return total


def _prior_underpaid_interest(
    expectations: List[_InstallmentExpectation],
    principal_covered: int,
    waiver_targets: Set[int],
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> Money:
    """Sum unpaid contractual interest for principal-covered installments
    that were targeted by a payment with active waivers.

    When a late payment with waivers (``waive_mora``, ``waive_overdue_interest``,
    or ``discount``) causes an earlier installment to be "covered" by
    ``principal_covered_count`` without its contractual interest being
    satisfied, this function captures the missing interest so it can be
    included in ``interest_cap``.

    Only targets installments whose principal has been strictly overcovered
    AND that were the target of a waiver-affected payment (tracked in
    *waiver_targets* as 0-based indices).  This prevents false positives
    in anticipation scenarios where interest is legitimately lower.
    """
    total = Money.zero()
    for idx in range(min(principal_covered, len(expectations))):
        exp = expectations[idx]
        if idx not in waiver_targets:
            continue
        if exp.principal_paid <= exp.expected_principal:
            continue
        owed = exp.expected_interest - exp.interest_paid
        if owed > balance_tolerance:
            total = total + owed
    return total


def _interest_cap_for_payment(
    payment: CashFlowItem,
    expectations: List[_InstallmentExpectation],
    covered: int,
    next_due: Optional[date],
    interest_date: datetime,
    tz: tzinfo,
    waiver_targets: Set[int],
    regular: Money,
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> Money:
    skipped = _skipped_contractual_interest(expectations, next_due, to_date(interest_date, tz))
    if payment.waive_overdue_interest:
        skipped = Money.zero()
    prior_interest = _prior_underpaid_interest(expectations, covered, waiver_targets, balance_tolerance)
    return Money(regular.raw_amount + skipped.raw_amount + prior_interest.raw_amount)


# ------------------------------------------------------------------
# Installment expectation construction
# ------------------------------------------------------------------


def _build_expectations(
    allocs_by_number: Dict[int, List[Allocation]],
    principal_balance: Money,
    as_of_date: datetime,
    schedule: PaymentSchedule,
    fines_applied: Dict[date, Money],
    interest_calc: InterestCalculator,
    tz: tzinfo,
    last_payment_date: Optional[datetime] = None,
    calendar: WorkingDayCalendar = _DEFAULT_CALENDAR,
    grace_period_days: int = 0,
    waive_fines: bool = False,
    waive_mora: bool = False,
    mora_rate_for_event: MoraRateCallback = None,
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> List[_InstallmentExpectation]:
    """Build :class:`_InstallmentExpectation` records for every installment.

    Single source of waiver-aware ``expected_fine`` / ``expected_mora``
    math. ``_build_installments_snapshot`` (which produces the public
    :class:`Installment` view) reuses these values so the loan-level
    allocator and the public view never disagree.

    When *waive_fines* / *waive_mora* is ``True`` the corresponding
    expectation is capped at what was already paid by prior allocations,
    so the resulting ``balance`` reflects the effective obligation after
    waivers.

    *mora_rate_for_event* mirrors the callback used by
    :func:`compute_state` to resolve a per-cycle mora rate. When
    provided, the resolved rate is passed as ``mora_rate_override``
    to the interest calculator.
    """
    covered = principal_covered_count(principal_balance, schedule, balance_tolerance)

    result: List[_InstallmentExpectation] = []
    for i, entry in enumerate(schedule):
        installment_num = i + 1
        allocs = allocs_by_number.get(installment_num, [])

        prior_principal = Money(sum(a.principal_allocated.raw_amount for a in allocs))
        prior_interest = Money(sum(a.interest_allocated.raw_amount for a in allocs))
        prior_mora = Money(sum(a.mora_allocated.raw_amount for a in allocs))
        prior_fine = Money(sum(a.fine_allocated.raw_amount for a in allocs))
        prior_principal_discounted = Money(sum(a.principal_discounted.raw_amount for a in allocs))
        prior_interest_discounted = Money(sum(a.interest_discounted.raw_amount for a in allocs))
        prior_mora_discounted = Money(sum(a.mora_discounted.raw_amount for a in allocs))
        prior_fine_discounted = Money(sum(a.fine_discounted.raw_amount for a in allocs))

        expected_fine = prior_fine if waive_fines else fines_applied.get(entry.due_date, Money.zero())

        if waive_mora or i < covered:
            expected_mora = prior_mora
        elif i == covered and entry.due_date < to_date(as_of_date, tz):
            within_grace = not is_payment_late(entry.due_date, grace_period_days, as_of_date, tz, calendar)
            if within_grace:
                accrued_mora = Money.zero()
            else:
                mora_override = mora_rate_for_event(entry.due_date) if mora_rate_for_event else None
                penalty_due = effective_penalty_due_date(entry.due_date, calendar)
                if last_payment_date is not None:
                    total_days = (to_date(as_of_date, tz) - to_date(last_payment_date, tz)).days
                    _, accrued_mora = interest_calc.compute_accrued_interest(
                        total_days,
                        principal_balance,
                        tz,
                        penalty_due,
                        last_payment_date,
                        mora_rate_override=mora_override,
                    )
                else:
                    days_overdue = max(0, (to_date(as_of_date, tz) - penalty_due).days)
                    _, accrued_mora = interest_calc.compute_accrued_interest(
                        days_overdue,
                        principal_balance,
                        tz,
                        penalty_due,
                        to_datetime(penalty_due, tz),
                        mora_rate_override=mora_override,
                    )
            expected_mora = prior_mora + accrued_mora
        else:
            expected_mora = Money.zero()

        result.append(
            _InstallmentExpectation(
                number=installment_num,
                due_date=entry.due_date,
                expected_principal=entry.principal_payment,
                expected_interest=entry.interest_payment,
                expected_mora=expected_mora,
                expected_fine=expected_fine,
                principal_paid=prior_principal,
                interest_paid=prior_interest,
                mora_paid=prior_mora,
                fine_paid=prior_fine,
                balance_tolerance=balance_tolerance,
                fine_discounted=prior_fine_discounted,
                mora_discounted=prior_mora_discounted,
                interest_discounted=prior_interest_discounted,
                principal_discounted=prior_principal_discounted,
            )
        )

    return result


# ------------------------------------------------------------------
# Installment snapshot construction (public view)
# ------------------------------------------------------------------


def _build_installments_snapshot(
    allocs_by_number: Dict[int, List[Allocation]],
    principal_balance: Money,
    as_of_date: datetime,
    schedule: PaymentSchedule,
    fines_applied: Dict[date, Money],
    interest_calc: InterestCalculator,
    tz: tzinfo,
    last_payment_date: Optional[datetime] = None,
    calendar: WorkingDayCalendar = _DEFAULT_CALENDAR,
    grace_period_days: int = 0,
    waive_fines: bool = False,
    waive_mora: bool = False,
    mora_rate_for_event: MoraRateCallback = None,
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> List[Installment]:
    """Build the public :class:`Installment` view as a downstream projection.

    Delegates the waiver-aware ``expected_*`` math to
    :func:`_build_expectations` so the public view shares its source
    with the loan-level allocator.
    """
    expectations = _build_expectations(
        allocs_by_number,
        principal_balance,
        as_of_date,
        schedule,
        fines_applied,
        interest_calc,
        tz,
        last_payment_date=last_payment_date,
        calendar=calendar,
        grace_period_days=grace_period_days,
        waive_fines=waive_fines,
        waive_mora=waive_mora,
        mora_rate_for_event=mora_rate_for_event,
        balance_tolerance=balance_tolerance,
    )

    result: List[Installment] = []
    for entry, exp in zip(schedule, expectations):
        allocs = allocs_by_number.get(exp.number, [])
        result.append(
            Installment.from_schedule_entry(
                entry,
                allocs,
                exp.expected_mora,
                exp.expected_fine,
                balance_tolerance=balance_tolerance,
            )
        )

    return result


# ------------------------------------------------------------------
# Waiver and discount helpers
# ------------------------------------------------------------------


@dataclass(frozen=True)
class _WaiverResult:
    effective_fine_cap: Money
    effective_mora_cap: Money
    interest_cap: Money
    fine_discounted: Money
    mora_discounted: Money
    interest_discounted: Money
    principal_discounted: Money
    fines_waived: Money
    mora_waived: Money
    fines_applied: Dict[date, Money]
    fines_paid_total: Money


def _apply_waivers_and_discounts(
    payment: object,
    fine_balance: Money,
    mora: Money,
    interest_cap: Money,
    fines_applied: Dict[date, Money],
    fines_paid_total: Money,
) -> _WaiverResult:
    """Apply waive_fines, waive_mora, and discount to caps.

    The per-category discount amounts (``fine_discounted``,
    ``mora_discounted``, ``interest_discounted``,
    ``principal_discounted``) are returned alongside the reduced caps
    so the allocator can record them on each :class:`Allocation`. That
    keeps the per-installment view's ``balance`` consistent with the
    loan-level ``remaining_balance`` when a discount is applied.
    """
    fines_waived = Money.zero()
    mora_waived = Money.zero()
    effective_fine_cap = fine_balance
    effective_mora_cap = mora

    if payment.waive_fines:
        fines_waived = fine_balance
        fines_applied = {dd: Money.zero() for dd in fines_applied}
        fines_paid_total = Money.zero()
        effective_fine_cap = Money.zero()

    if payment.waive_mora:
        mora_waived = mora
        effective_mora_cap = Money.zero()

    discount_remaining = payment.discount
    fine_discounted = Money(min(effective_fine_cap.raw_amount, discount_remaining.raw_amount))
    discount_remaining = discount_remaining - fine_discounted
    effective_fine_cap = effective_fine_cap - fine_discounted

    mora_discounted = Money(min(effective_mora_cap.raw_amount, discount_remaining.raw_amount))
    discount_remaining = discount_remaining - mora_discounted
    effective_mora_cap = effective_mora_cap - mora_discounted

    interest_discounted = Money(min(interest_cap.raw_amount, discount_remaining.raw_amount))
    discount_remaining = discount_remaining - interest_discounted
    interest_cap = interest_cap - interest_discounted

    return _WaiverResult(
        effective_fine_cap=effective_fine_cap,
        effective_mora_cap=effective_mora_cap,
        interest_cap=interest_cap,
        fine_discounted=fine_discounted,
        mora_discounted=mora_discounted,
        interest_discounted=interest_discounted,
        principal_discounted=discount_remaining,
        fines_waived=fines_waived,
        mora_waived=mora_waived,
        fines_applied=fines_applied,
        fines_paid_total=fines_paid_total + fine_discounted,
    )


# ------------------------------------------------------------------
# Overdue interest waiver
# ------------------------------------------------------------------


def _compute_overdue_interest_waiver(
    regular: Money,
    next_due: Optional[date],
    days: int,
    last_accrual_end: datetime,
    running_principal: Money,
    interest_calc: "InterestCalculator",
    tz: tzinfo,
) -> Tuple[Money, Money]:
    """Compute overdue regular interest and return ``(reduced_regular, waived)``.

    Overdue interest is the portion of *regular* that accrued past
    the contract due date.  Returns the capped regular amount and
    the excess that was waived.
    """
    if next_due is None:
        return regular, Money.zero()
    due_days = max(0, (next_due - to_date(last_accrual_end, tz)).days)
    if due_days >= days:
        return regular, Money.zero()
    capped = interest_calc.interest_rate.accrue(running_principal, due_days)
    excess = regular - capped
    if not excess.is_positive():
        return regular, Money.zero()
    return capped, excess


# ------------------------------------------------------------------
# Forward pass: compute all settlements from cashflow
# ------------------------------------------------------------------


def _accrual_end_with_waiver_cap(
    default_end: datetime,
    payment: object,
    running_principal: Money,
    schedule: PaymentSchedule,
    due_dates: List[date],
    tz: tzinfo,
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> datetime:
    """Cap ``last_accrual_end`` at the latest covered due date when waiving overdue interest.

    When ``waive_overdue_interest`` is active and at least one installment
    is fully covered, the regular interest was capped at the prior due
    date and the late window was not billed.  Returning that due date
    keeps the next installment's interest period at its full contractual
    length instead of being shortened by the late days.

    Tolerance-adjustment items inherit the waiver flag, so this cap also
    holds across the synthetic events ``apply_tolerance_adjustment`` adds
    after a snapped payment.
    """
    if not payment.waive_overdue_interest:
        return default_end
    new_covered = principal_covered_count(running_principal, schedule, balance_tolerance)
    if new_covered <= 0:
        return default_end
    snap_cap = to_datetime(due_dates[new_covered - 1], tz)
    if snap_cap < default_end:
        return snap_cap
    return default_end


def _build_event_timeline(
    payment_entries: list,
    fine_observation_dates: Optional[List[datetime]],
) -> List[Tuple[datetime, bool, Optional[object]]]:
    """Merge payment events and fine observation dates into a sorted timeline.

    Returns a list of ``(datetime, is_payment, payment_or_none)`` tuples
    sorted chronologically.  Payments sort before observations at the
    same timestamp.
    """
    events: List[Tuple[datetime, bool, Optional[object]]] = []
    for payment in payment_entries:
        events.append((payment.datetime, True, payment))
    if fine_observation_dates:
        for dt in fine_observation_dates:
            events.append((dt, False, None))
    events.sort(key=lambda e: (e[0], not e[1]))
    return events


def compute_state(
    principal: Money,
    interest_calc: InterestCalculator,
    schedule: PaymentSchedule,
    due_dates: List[date],
    fine_rate: InterestRate,
    grace_period_days: int,
    disbursement_date: datetime,
    payment_entries: list,
    as_of: datetime,
    tz: tzinfo,
    fine_observation_dates: Optional[List[datetime]] = None,
    mora_rate_for_event: MoraRateCallback = None,
    calendar: WorkingDayCalendar = _DEFAULT_CALENDAR,
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> LoanState:
    """Forward pass: compute all settlements and derived state from payments.

    For each payment, builds installment expectations, computes interest
    (including skipped contractual interest), and runs the per-installment
    allocation algorithm. The allocator is fed
    :class:`_InstallmentExpectation` primitives only — the public
    :class:`Installment` view is built downstream of the produced
    settlements by :func:`build_installments`.

    After all payments have been processed, a single final pass assigns
    every allocation's ``is_fully_covered`` flag from the final
    :class:`Installment` view, restoring the invariant
    ``Allocation.is_fully_covered == Installment.is_fully_paid`` in one
    place.

    Fines are computed at each payment date AND at any explicit
    ``fine_observation_dates`` (from Warp or calculate_late_fines calls).
    Without observation dates, fines are only computed when payments
    are processed.

    Args:
        tz: Business timezone for date extraction from datetimes.
        mora_rate_for_event: Optional callback ``(next_due) -> InterestRate``
            called before each interest computation.  When it returns a
            non-``None`` value, that rate is passed as
            ``mora_rate_override`` to the interest calculator.  Used by
            ``BillingCycleLoan`` to resolve per-cycle mora rates.
            ``Loan`` omits this (``None``), getting the calculator's
            default mora rate.
        calendar: Working-day calendar for penalty due-date adjustment.
    """
    running_principal = principal
    last_payment_date = disbursement_date
    last_accrual_end = disbursement_date
    fines_applied: Dict[date, Money] = {}
    fines_paid_total = Money.zero()
    overpaid = Money.zero()
    settlements: List[Settlement] = []
    allocs_by_number: Dict[int, List[Allocation]] = {}
    processed_payments: list = []
    waiver_targets: Set[int] = set()

    events = _build_event_timeline(payment_entries, fine_observation_dates)

    for event_dt, is_payment, payment in events:
        if event_dt > as_of:
            break

        fines_applied = compute_fines_at(
            event_dt,
            due_dates,
            schedule,
            fine_rate,
            grace_period_days,
            fines_applied,
            processed_payments,
            tz,
            calendar,
            balance_tolerance=balance_tolerance,
        )

        if not is_payment:
            continue

        interest_date = payment.interest_date if payment.interest_date is not None else payment.datetime
        days = max(0, (to_date(interest_date, tz) - to_date(last_accrual_end, tz)).days)

        covered = principal_covered_count(running_principal, schedule, balance_tolerance)
        next_due = due_dates[covered] if covered < len(due_dates) else None

        mora_override = mora_rate_for_event(next_due) if mora_rate_for_event else None

        penalty_next_due = effective_penalty_due_date(next_due, calendar) if next_due else None
        regular, mora = interest_calc.compute_accrued_interest(
            days,
            running_principal,
            tz,
            penalty_next_due,
            last_accrual_end,
            mora_rate_override=mora_override,
        )

        if next_due and not is_payment_late(next_due, grace_period_days, payment.datetime, tz, calendar):
            regular = regular + mora
            mora = Money.zero()

        overdue_interest_waived = Money.zero()
        if payment.waive_overdue_interest:
            regular, overdue_interest_waived = _compute_overdue_interest_waiver(
                regular,
                next_due,
                days,
                last_accrual_end,
                running_principal,
                interest_calc,
                tz,
            )

        has_discount = payment.discount.is_positive()
        if payment.waive_mora or payment.waive_overdue_interest or has_discount:
            waiver_targets.add(covered)

        expectations = _build_expectations(
            allocs_by_number,
            running_principal,
            payment.datetime,
            schedule,
            fines_applied,
            interest_calc,
            tz,
            last_payment_date=last_accrual_end,
            calendar=calendar,
            grace_period_days=grace_period_days,
            waive_fines=payment.waive_fines,
            waive_mora=payment.waive_mora,
            mora_rate_for_event=mora_rate_for_event,
            balance_tolerance=balance_tolerance,
        )

        interest_cap = _interest_cap_for_payment(
            payment,
            expectations,
            covered,
            next_due,
            interest_date,
            tz,
            waiver_targets,
            regular,
            balance_tolerance=balance_tolerance,
        )

        total_fines_amount = Money(sum(f.raw_amount for f in fines_applied.values())) if fines_applied else Money.zero()
        fine_balance = total_fines_amount - fines_paid_total
        if fine_balance.is_negative():
            fine_balance = Money.zero()

        wd = _apply_waivers_and_discounts(
            payment,
            fine_balance,
            mora,
            interest_cap,
            fines_applied,
            fines_paid_total,
        )
        fines_applied = wd.fines_applied

        fine_paid, mora_paid, interest_paid, principal_paid, allocations = allocate_payment_into_installments(
            payment.amount,
            expectations,
            fine_cap=wd.effective_fine_cap,
            interest_cap=wd.interest_cap,
            mora_cap=wd.effective_mora_cap,
            balance_tolerance=balance_tolerance,
            fine_discount_total=wd.fine_discounted,
            mora_discount_total=wd.mora_discounted,
            interest_discount_total=wd.interest_discounted,
            principal_discount_total=wd.principal_discounted,
        )

        fines_paid_total = wd.fines_paid_total + fine_paid
        running_principal = running_principal - principal_paid - wd.principal_discounted
        if running_principal.is_negative():
            overpaid = overpaid + Money(-running_principal.raw_amount)
            running_principal = Money.zero()

        for a in allocations:
            allocs_by_number.setdefault(a.installment_number, []).append(a)

        settlements.append(
            Settlement(
                payment_amount=payment.amount,
                payment_date=payment.datetime,
                fine_paid=fine_paid,
                interest_paid=interest_paid,
                mora_paid=mora_paid,
                principal_paid=principal_paid,
                remaining_balance=running_principal,
                allocations=allocations,
                fines_waived=wd.fines_waived,
                mora_waived=wd.mora_waived,
                overdue_interest_waived=overdue_interest_waived,
                discount_applied=payment.discount,
            )
        )

        last_payment_date = payment.datetime
        last_accrual_end = _accrual_end_with_waiver_cap(
            max(payment.datetime, interest_date),
            payment,
            running_principal,
            schedule,
            due_dates,
            tz,
            balance_tolerance,
        )

        processed_payments.append(payment)

    _finalize_settlements_coverage(
        settlements,
        allocs_by_number,
        running_principal,
        schedule,
        fines_applied,
        interest_calc,
        tz,
        last_payment_date=last_accrual_end,
        as_of=as_of,
        calendar=calendar,
        grace_period_days=grace_period_days,
        mora_rate_for_event=mora_rate_for_event,
        balance_tolerance=balance_tolerance,
    )

    return LoanState(
        settlements=settlements,
        principal_balance=running_principal,
        fines_applied=fines_applied,
        fines_paid_total=fines_paid_total,
        last_payment_date=last_payment_date,
        last_accrual_end=last_accrual_end,
        overpaid=overpaid,
    )


def _finalize_settlements_coverage(
    settlements: List[Settlement],
    allocs_by_number: Dict[int, List[Allocation]],
    principal_balance: Money,
    schedule: PaymentSchedule,
    fines_applied: Dict[date, Money],
    interest_calc: InterestCalculator,
    tz: tzinfo,
    last_payment_date: datetime,
    as_of: datetime,
    calendar: WorkingDayCalendar,
    grace_period_days: int,
    mora_rate_for_event: MoraRateCallback,
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> None:
    """Single coverage pass: align every allocation's ``is_fully_covered``
    with the final :class:`Installment` view.

    The allocator emits provisional ``is_fully_covered=False`` flags
    inside the forward-pass loop. After the loop completes, this pass
    builds the final installment view once and overwrites every flag
    against it. The invariant
    ``Allocation.is_fully_covered == Installment.is_fully_paid`` is
    therefore decided in exactly one place.
    """
    final_installments = _build_installments_snapshot(
        allocs_by_number,
        principal_balance,
        as_of,
        schedule,
        fines_applied,
        interest_calc,
        tz,
        last_payment_date=last_payment_date,
        calendar=calendar,
        grace_period_days=grace_period_days,
        mora_rate_for_event=mora_rate_for_event,
        balance_tolerance=balance_tolerance,
    )
    is_paid_by_number = {inst.number: inst.is_fully_paid for inst in final_installments}

    for settlement in settlements:
        for i, alloc in enumerate(settlement.allocations):
            target = is_paid_by_number.get(alloc.installment_number)
            if target is None or alloc.is_fully_covered == target:
                continue
            settlement.allocations[i] = Allocation(
                installment_number=alloc.installment_number,
                principal_allocated=alloc.principal_allocated,
                interest_allocated=alloc.interest_allocated,
                mora_allocated=alloc.mora_allocated,
                fine_allocated=alloc.fine_allocated,
                is_fully_covered=target,
                fine_discounted=alloc.fine_discounted,
                mora_discounted=alloc.mora_discounted,
                interest_discounted=alloc.interest_discounted,
                principal_discounted=alloc.principal_discounted,
            )


# ------------------------------------------------------------------
# Aggregate views
# ------------------------------------------------------------------


def build_installments(
    schedule: PaymentSchedule,
    settlements: List[Settlement],
    fines_applied: Dict[date, Money],
    principal_balance: Money,
    as_of: datetime,
    interest_calc: InterestCalculator,
    last_accrual_end: datetime,
    tz: tzinfo,
    calendar: WorkingDayCalendar = _DEFAULT_CALENDAR,
    grace_period_days: int = 0,
    mora_rate_for_event: MoraRateCallback = None,
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> List[Installment]:
    """Build the installment view from settlements + schedule.

    *mora_rate_for_event* mirrors the callback used by :func:`compute_state`.
    When provided, it is threaded down to :func:`_build_installments_snapshot`
    so the snapshot's ``expected_mora`` uses the same per-cycle resolved
    rate as the loan-level allocation. Without this, products that resolve
    mora per cycle (e.g. ``BillingCycleLoan``) would expose installments
    whose ``balance`` disagrees with the allocation's ``is_fully_covered``.
    """
    allocs_by_number: Dict[int, List[Allocation]] = {}
    for settlement in settlements:
        for a in settlement.allocations:
            allocs_by_number.setdefault(a.installment_number, []).append(a)

    return _build_installments_snapshot(
        allocs_by_number,
        principal_balance,
        as_of,
        schedule,
        fines_applied,
        interest_calc,
        tz,
        last_payment_date=last_accrual_end,
        calendar=calendar,
        grace_period_days=grace_period_days,
        mora_rate_for_event=mora_rate_for_event,
        balance_tolerance=balance_tolerance,
    )


# ------------------------------------------------------------------
# Tolerance adjustment
# ------------------------------------------------------------------


def apply_tolerance_adjustment(
    cashflow: CashFlow,
    entry: PaymentScheduleEntry,
    settlement: Settlement,
    payment_date: datetime,
    interest_date: datetime,
    payment_tolerance: Money,
    num_installments: int,
    time_ctx: TimeContext,
    waive_overdue_interest: bool = False,
) -> None:
    """Add a small CashFlowItem if the balance drifted from the schedule.

    Compares the settlement's remaining balance against the schedule
    entry's expected ending balance.  When the gap is positive and
    within *payment_tolerance*, a tolerance adjustment is recorded as
    a real, auditable cashflow entry.

    After the last installment, any remaining balance within the
    accumulated tolerance is also absorbed.  The multiplier of 3
    accounts for compounding -- per-period rounding errors grow
    faster than linearly at high interest rates.

    *waive_overdue_interest* is propagated from the originating payment
    so the forward pass treats the synthetic adjustment with the same
    accrual-cap semantics; otherwise a tolerance event scheduled at the
    actual late timestamp would silently undo the snap that
    ``compute_state`` applied to ``last_accrual_end``.
    """
    balance = settlement.remaining_balance
    gap = balance - entry.ending_balance
    if gap.is_positive() and gap <= payment_tolerance:
        cashflow.add_item(
            CashFlowItem(
                gap,
                payment_date,
                f"Tolerance adjustment for installment {entry.payment_number}",
                "payment",
                time_context=time_ctx,
                interest_date=interest_date,
                waive_overdue_interest=waive_overdue_interest,
            )
        )
        return

    is_last_installment = entry.payment_number == num_installments
    if balance.is_positive() and is_last_installment:
        max_tolerance = payment_tolerance * num_installments * 3
        if balance <= max_tolerance:
            cashflow.add_item(
                CashFlowItem(
                    balance,
                    payment_date,
                    f"Tolerance adjustment closing residual after installment {entry.payment_number}",
                    "payment",
                    time_context=time_ctx,
                    interest_date=interest_date,
                    waive_overdue_interest=waive_overdue_interest,
                )
            )
