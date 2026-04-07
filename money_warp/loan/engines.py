"""Stateless interest computation and settlement logic.

Interest calculation splits accrued interest into regular and mora
components.  Settlement computation replays payments against the
schedule using a forward pass.  Each payment is allocated in two
steps: loan-level math (fine -> mora -> interest -> principal)
followed by per-installment distribution for reporting.

Shared building blocks (:class:`InterestCalculator`,
:class:`MoraStrategy`) are defined in :mod:`money_warp.engines`
and re-exported here for backward compatibility.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from ..engines import (  # noqa: F401 – re-export
    InterestCalculator,
    MoraRateCallback,
    MoraStrategy,
)
from ..interest_rate import InterestRate
from ..money import Money
from ..scheduler import PaymentSchedule
from ..tz import to_datetime
from .allocation import Allocation
from .installment import Installment
from .settlement import Settlement

# ===================================================================
# Settlement engine
# ===================================================================

_COVERAGE_TOLERANCE = Money("0.01")


@dataclass(frozen=True)
class LoanState:
    """Snapshot of derived loan state from the forward pass."""

    settlements: List[Settlement]
    principal_balance: Money
    fines_applied: Dict[date, Money]
    fines_paid_total: Money
    last_payment_date: datetime
    overpaid: Money


# ------------------------------------------------------------------
# Coverage
# ------------------------------------------------------------------


def covered_due_date_count(
    remaining_balance: Money,
    schedule: PaymentSchedule,
) -> int:
    """How many due dates are covered given a remaining principal balance."""
    covered = 0
    for entry in schedule:
        if remaining_balance <= entry.ending_balance + _COVERAGE_TOLERANCE:
            covered += 1
        else:
            break
    return covered


# ------------------------------------------------------------------
# Fine computation
# ------------------------------------------------------------------


def is_payment_late(due_date: date, grace_period_days: int, as_of: datetime) -> bool:
    """Whether a payment is late considering the grace period."""
    effective_due = due_date + timedelta(days=grace_period_days)
    return as_of.date() > effective_due


_WINDOW_DAYS_BEFORE = 3
_WINDOW_DAYS_AFTER = 1


def _has_payment_near(
    due_date: date,
    as_of: datetime,
    schedule: PaymentSchedule,
    payment_entries: list,
) -> bool:
    """Check if sufficient payment has been made near a due date.

    Replicates the old FineTracker's temporal proximity check:
    exact-date match first, then a small window around the due date.
    """
    expected = Money.zero()
    for entry in schedule:
        if entry.due_date == due_date:
            expected = entry.payment_amount
            break
    if expected.is_zero():
        return False

    exact = [p for p in payment_entries if p.datetime.date() == due_date and p.datetime <= as_of]
    if sum((p.amount for p in exact), Money.zero()) >= (expected - _COVERAGE_TOLERANCE):
        return True

    window_start = to_datetime(due_date - timedelta(days=_WINDOW_DAYS_BEFORE))
    window_end = min(as_of, to_datetime(due_date + timedelta(days=_WINDOW_DAYS_AFTER)))
    window = [p for p in payment_entries if window_start <= p.datetime <= window_end and p.datetime <= as_of]
    return sum((p.amount for p in window), Money.zero()) >= (expected - _COVERAGE_TOLERANCE)


def compute_fines_at(
    as_of: datetime,
    due_dates: List[date],
    schedule: PaymentSchedule,
    fine_rate: InterestRate,
    grace_period_days: int,
    existing_fines: Dict[date, Money],
    payment_entries: list,
) -> Dict[date, Money]:
    """Compute fines for overdue due dates as of *as_of*.

    A due date gets a fine when it is past the grace period AND
    no sufficient payment was made near it (within a small window).
    """
    fines = dict(existing_fines)

    for dd in due_dates:
        if dd in fines:
            continue
        if not is_payment_late(dd, grace_period_days, as_of):
            continue
        if _has_payment_near(dd, as_of, schedule, payment_entries):
            continue
        for entry in schedule:
            if entry.due_date == dd:
                fine_amount = Money(entry.payment_amount.raw_amount * fine_rate.as_decimal())
                fines[dd] = fine_amount
                break

    return fines


# ------------------------------------------------------------------
# Skipped contractual interest
# ------------------------------------------------------------------


def _skipped_contractual_interest(
    installments: List[Installment],
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
    for inst in installments:
        if inst.due_date > next_due and inst.due_date <= cutoff:
            owed = inst.expected_interest - inst.interest_paid
            if owed.is_positive():
                total = total + owed
    return total


# ------------------------------------------------------------------
# Payment allocation
# ------------------------------------------------------------------


def allocate_payment(
    amount: Money,
    fines_owed: Money,
    mora_accrued: Money,
    interest_accrued: Money,
) -> Tuple[Money, Money, Money, Money]:
    """Loan-level allocation: fine -> mora -> interest -> principal.

    Determines how a payment splits across the four obligation
    components.  Everything left after fines, mora, and interest
    goes to principal reduction (which may exceed the current
    balance, producing overpayment handled by the caller).

    Returns:
        (fine_paid, mora_paid, interest_paid, principal_paid)
    """
    remaining = amount

    fine_paid = Money(min(fines_owed.raw_amount, remaining.raw_amount))
    remaining = remaining - fine_paid

    mora_paid = Money(min(mora_accrued.raw_amount, remaining.raw_amount))
    remaining = remaining - mora_paid

    interest_paid = Money(min(interest_accrued.raw_amount, remaining.raw_amount))
    remaining = remaining - interest_paid

    principal_paid = remaining
    return fine_paid, mora_paid, interest_paid, principal_paid


def distribute_into_installments(
    installments: List[Installment],
    fine_total: Money,
    mora_total: Money,
    interest_total: Money,
    principal_total: Money,
    ending_balance: Money,
) -> List[Allocation]:
    """Distribute loan-level totals into per-installment allocations.

    Walks installments sequentially, filling each installment's
    obligations from the pre-computed loan-level totals.  This is a
    reporting view -- the financial math is done by
    :func:`allocate_payment`.

    A residual adjustment ensures ``sum(allocations.X) == X_total``
    for every component, and a coverage fixup marks allocations as
    fully covered when the loan is paid off.

    Returns:
        List of Allocation objects (one per touched installment).
    """
    fine_remaining = fine_total
    mora_remaining = mora_total
    interest_remaining = interest_total
    principal_remaining = principal_total
    allocations: List[Allocation] = []

    for inst in installments:
        fine_owed = inst.expected_fine - inst.fine_paid
        fine_alloc = Money(min(max(fine_owed.raw_amount, 0), fine_remaining.raw_amount))
        fine_remaining = fine_remaining - fine_alloc

        mora_owed = inst.expected_mora - inst.mora_paid
        mora_alloc = Money(min(max(mora_owed.raw_amount, 0), mora_remaining.raw_amount))
        mora_remaining = mora_remaining - mora_alloc

        interest_owed = inst.expected_interest - inst.interest_paid
        interest_alloc = Money(min(max(interest_owed.raw_amount, 0), interest_remaining.raw_amount))
        interest_remaining = interest_remaining - interest_alloc

        principal_owed = inst.expected_principal - inst.principal_paid
        principal_alloc = Money(min(max(principal_owed.raw_amount, 0), principal_remaining.raw_amount))
        principal_remaining = principal_remaining - principal_alloc

        total = fine_alloc + mora_alloc + interest_alloc + principal_alloc
        if total.is_positive():
            is_covered = total >= (inst.balance - _COVERAGE_TOLERANCE)
            allocations.append(
                Allocation(
                    installment_number=inst.number,
                    principal_allocated=principal_alloc,
                    interest_allocated=interest_alloc,
                    mora_allocated=mora_alloc,
                    fine_allocated=fine_alloc,
                    is_fully_covered=is_covered,
                )
            )

    _apply_residual(allocations, installments, fine_total, mora_total, interest_total, principal_total)
    _apply_coverage_fixup(allocations, installments, ending_balance, principal_total)
    return allocations


def _apply_residual(
    allocations: List[Allocation],
    installments: List[Installment],
    fine_total: Money,
    mora_total: Money,
    interest_total: Money,
    principal_total: Money,
) -> None:
    """Adjust the last allocation so ``sum(allocations)`` matches the totals.

    Loan-level accrual can exceed what installments absorb (rounding,
    partial periods, overpayment).  This single sweep patches any gap.
    """
    sum_f = sum((a.fine_allocated.raw_amount for a in allocations), Money.zero().raw_amount)
    sum_m = sum((a.mora_allocated.raw_amount for a in allocations), Money.zero().raw_amount)
    sum_i = sum((a.interest_allocated.raw_amount for a in allocations), Money.zero().raw_amount)
    sum_p = sum((a.principal_allocated.raw_amount for a in allocations), Money.zero().raw_amount)

    f_diff = fine_total.raw_amount - sum_f
    m_diff = mora_total.raw_amount - sum_m
    i_diff = interest_total.raw_amount - sum_i
    p_diff = principal_total.raw_amount - sum_p

    if not (f_diff or m_diff or i_diff or p_diff):
        return

    if allocations:
        last = allocations[-1]
        allocations[-1] = Allocation(
            installment_number=last.installment_number,
            principal_allocated=Money(last.principal_allocated.raw_amount + p_diff),
            interest_allocated=Money(last.interest_allocated.raw_amount + i_diff),
            mora_allocated=Money(last.mora_allocated.raw_amount + m_diff),
            fine_allocated=Money(last.fine_allocated.raw_amount + f_diff),
            is_fully_covered=last.is_fully_covered,
        )
    elif installments:
        allocations.append(
            Allocation(
                installment_number=installments[-1].number,
                principal_allocated=Money(p_diff),
                interest_allocated=Money(i_diff),
                mora_allocated=Money(m_diff),
                fine_allocated=Money(f_diff),
                is_fully_covered=False,
            )
        )


def _apply_coverage_fixup(
    allocations: List[Allocation],
    installments: List[Installment],
    ending_balance: Money,
    principal_total: Money,
) -> None:
    """Override coverage flags when the loan is paid off.

    If the post-payment balance is within tolerance of zero,
    any allocation whose principal was fully allocated is
    marked as fully covered.
    """
    post_balance = ending_balance - principal_total
    if post_balance > _COVERAGE_TOLERANCE:
        return

    inst_by_number = {inst.number: inst for inst in installments}
    for i, alloc in enumerate(allocations):
        if alloc.is_fully_covered:
            continue
        inst = inst_by_number.get(alloc.installment_number)
        if inst is None:
            continue
        principal_owed = inst.expected_principal - inst.principal_paid
        if alloc.principal_allocated >= (principal_owed - _COVERAGE_TOLERANCE):
            allocations[i] = Allocation(
                installment_number=alloc.installment_number,
                principal_allocated=alloc.principal_allocated,
                interest_allocated=alloc.interest_allocated,
                mora_allocated=alloc.mora_allocated,
                fine_allocated=alloc.fine_allocated,
                is_fully_covered=True,
            )


def allocate_payment_into_installments(
    amount: Money,
    installments: List[Installment],
    ending_balance: Money,
    fine_cap: Money,
    interest_cap: Money,
    mora_cap: Money,
) -> Tuple[Money, Money, Money, Money, List[Allocation]]:
    """Allocate a payment across installments in priority order.

    Two-step process:

    1. **Loan-level allocation** (:func:`allocate_payment`) determines
       the totals: fine -> mora -> interest -> principal.
    2. **Per-installment distribution** (:func:`distribute_into_installments`)
       maps those totals to individual installments for reporting.

    Returns:
        (fine_total, mora_total, interest_total, principal_total, allocations)
    """
    fine_paid, mora_paid, interest_paid, principal_paid = allocate_payment(
        amount,
        fine_cap,
        mora_cap,
        interest_cap,
    )

    allocations = distribute_into_installments(
        installments,
        fine_paid,
        mora_paid,
        interest_paid,
        principal_paid,
        ending_balance,
    )

    return fine_paid, mora_paid, interest_paid, principal_paid, allocations


# ------------------------------------------------------------------
# Installment snapshot construction
# ------------------------------------------------------------------


def _build_installments_snapshot(
    allocs_by_number: Dict[int, List[Allocation]],
    principal_balance: Money,
    as_of_date: datetime,
    schedule: PaymentSchedule,
    fines_applied: Dict[date, Money],
    interest_calc: InterestCalculator,
    last_payment_date: Optional[datetime] = None,
) -> List[Installment]:
    """Build Installment objects from pre-computed allocation data."""
    covered = covered_due_date_count(principal_balance, schedule)

    result: List[Installment] = []
    for i, entry in enumerate(schedule):
        installment_num = i + 1
        allocs = allocs_by_number.get(installment_num, [])

        expected_fine = fines_applied.get(entry.due_date, Money.zero())
        prior_mora = Money(sum(a.mora_allocated.raw_amount for a in allocs))

        if i < covered:
            expected_mora = prior_mora
        elif i == covered and entry.due_date < as_of_date.date():
            if last_payment_date is not None:
                total_days = (as_of_date.date() - last_payment_date.date()).days
                _, accrued_mora = interest_calc.compute_accrued_interest(
                    total_days,
                    principal_balance,
                    entry.due_date,
                    last_payment_date,
                )
            else:
                days_overdue = (as_of_date.date() - entry.due_date).days
                _, accrued_mora = interest_calc.compute_accrued_interest(
                    days_overdue,
                    principal_balance,
                    entry.due_date,
                    to_datetime(entry.due_date),
                )
            expected_mora = prior_mora + accrued_mora
        else:
            expected_mora = Money.zero()

        result.append(Installment.from_schedule_entry(entry, allocs, expected_mora, expected_fine))

    return result


# ------------------------------------------------------------------
# Forward pass: compute all settlements from cashflow
# ------------------------------------------------------------------


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
    fine_observation_dates: Optional[List[datetime]] = None,
    mora_rate_for_event: MoraRateCallback = None,
) -> LoanState:
    """Forward pass: compute all settlements and derived state from payments.

    For each payment, builds installment snapshots, computes interest
    (including skipped contractual interest), and runs the per-installment
    allocation algorithm.

    Fines are computed at each payment date AND at any explicit
    ``fine_observation_dates`` (from Warp or calculate_late_fines calls).
    Without observation dates, fines are only computed when payments
    are processed.

    Args:
        mora_rate_for_event: Optional callback ``(next_due) -> InterestRate``
            called before each interest computation.  When it returns a
            non-``None`` value, that rate is passed as
            ``mora_rate_override`` to the interest calculator.  Used by
            ``BillingCycleLoan`` to resolve per-cycle mora rates.
            ``Loan`` omits this (``None``), getting the calculator's
            default mora rate.
    """
    running_principal = principal
    last_payment_date = disbursement_date
    fines_applied: Dict[date, Money] = {}
    fines_paid_total = Money.zero()
    overpaid = Money.zero()
    settlements: List[Settlement] = []
    allocs_by_number: Dict[int, List[Allocation]] = {}
    processed_payments: list = []

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
        )

        if not is_payment:
            continue

        interest_date = payment.interest_date if payment.interest_date is not None else payment.datetime
        days = max(0, (interest_date.date() - last_payment_date.date()).days)

        covered = covered_due_date_count(running_principal, schedule)
        next_due = due_dates[covered] if covered < len(due_dates) else None

        mora_override = mora_rate_for_event(next_due) if mora_rate_for_event else None

        regular, mora = interest_calc.compute_accrued_interest(
            days,
            running_principal,
            next_due,
            last_payment_date,
            mora_rate_override=mora_override,
        )

        installments = _build_installments_snapshot(
            allocs_by_number,
            running_principal,
            payment.datetime,
            schedule,
            fines_applied,
            interest_calc,
            last_payment_date=last_payment_date,
        )

        skipped = _skipped_contractual_interest(installments, next_due, interest_date.date())
        interest_cap = Money(regular.raw_amount + skipped.raw_amount)

        total_fines_amount = Money(sum(f.raw_amount for f in fines_applied.values())) if fines_applied else Money.zero()
        fine_balance = total_fines_amount - fines_paid_total
        if fine_balance.is_negative():
            fine_balance = Money.zero()

        fine_paid, mora_paid, interest_paid, principal_paid, allocations = allocate_payment_into_installments(
            payment.amount,
            installments,
            running_principal,
            fine_cap=fine_balance,
            interest_cap=interest_cap,
            mora_cap=mora,
        )

        fines_paid_total = fines_paid_total + fine_paid
        running_principal = running_principal - principal_paid
        if running_principal.is_negative():
            overpaid = overpaid + Money(-running_principal.raw_amount)
            running_principal = Money.zero()
        elif running_principal.is_positive() and running_principal <= _COVERAGE_TOLERANCE:
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
            )
        )

        last_payment_date = payment.datetime
        processed_payments.append(payment)

    return LoanState(
        settlements=settlements,
        principal_balance=running_principal,
        fines_applied=fines_applied,
        fines_paid_total=fines_paid_total,
        last_payment_date=last_payment_date,
        overpaid=overpaid,
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
    last_payment_date: datetime,
) -> List[Installment]:
    """Build the installment view from settlements + schedule."""
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
        last_payment_date=last_payment_date,
    )
