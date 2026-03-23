"""Stateless interest computation and settlement logic.

Interest calculation splits accrued interest into regular and mora
components.  Settlement computation replays payments against the
schedule using a forward pass with per-installment priority:
fine -> mora -> interest -> principal.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

from ..interest_rate import InterestRate
from ..money import Money
from ..scheduler import PaymentSchedule
from ..tz import to_datetime
from .allocation import Allocation
from .installment import Installment
from .settlement import Settlement

# ===================================================================
# Interest calculator
# ===================================================================


class MoraStrategy(Enum):
    """Strategy for computing mora (late) interest.

    SIMPLE: mora rate is applied to the outstanding principal only.
    COMPOUND: mora rate is applied to principal + accrued regular interest.
    """

    SIMPLE = "simple"
    COMPOUND = "compound"


class InterestCalculator:
    """Pure interest math — no mutable state, no time context.

    Holds three immutable rate parameters and computes accrued interest
    split into regular and mora components.
    """

    def __init__(
        self,
        interest_rate: InterestRate,
        mora_interest_rate: InterestRate,
        mora_strategy: MoraStrategy = MoraStrategy.COMPOUND,
    ) -> None:
        self.interest_rate = interest_rate
        self.mora_interest_rate = mora_interest_rate
        self.mora_strategy = mora_strategy

    def compute_accrued_interest(
        self,
        days: int,
        principal_balance: Money,
        due_date: Optional[date] = None,
        last_payment_date: Optional[datetime] = None,
    ) -> Tuple[Money, Money]:
        """Compute accrued interest split into regular and mora components.

        Returns (regular_accrued, mora_accrued). All interest is regular when
        due_date is not provided or the payment is not late. Uses
        ``mora_interest_rate`` and ``mora_strategy`` for the mora portion.
        """
        if due_date is None or last_payment_date is None:
            return self.interest_rate.accrue(principal_balance, days), Money.zero()

        regular_days = (due_date - last_payment_date.date()).days

        if regular_days <= 0:
            return Money.zero(), self.mora_interest_rate.accrue(principal_balance, days)

        if regular_days >= days:
            return self.interest_rate.accrue(principal_balance, days), Money.zero()

        mora_days = days - regular_days
        regular_accrued = self.interest_rate.accrue(principal_balance, regular_days)

        if self.mora_strategy == MoraStrategy.COMPOUND:
            mora_accrued = self.mora_interest_rate.accrue(principal_balance + regular_accrued, mora_days)
        else:
            mora_accrued = self.mora_interest_rate.accrue(principal_balance, mora_days)

        return regular_accrued, mora_accrued


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
# Per-installment payment allocation
# ------------------------------------------------------------------


def allocate_payment_into_installment(
    inst: Installment,
    remaining: Money,
    fine_remaining: Money,
    mora_remaining: Money,
    interest_remaining: Money,
) -> Tuple[Allocation, Money, Money, Money, Money]:
    """Allocate payment money to a single installment.

    Processes fine -> mora -> interest -> principal sequentially,
    each capped by both the installment's remaining obligation and
    the corresponding running cap.

    The running caps prevent over-allocation: they track the
    loan-level accrual computed during the forward pass.

    Principal allocation reserves ``interest_remaining + mora_remaining``
    so that later installments can still absorb their share of
    interest and mora.

    Returns:
        (allocation, remaining, fine_remaining, mora_remaining, interest_remaining)
    """
    fine_owed = inst.expected_fine - inst.fine_paid
    fine_alloc = Money(min(max(fine_owed.raw_amount, 0), remaining.raw_amount, fine_remaining.raw_amount))
    remaining = remaining - fine_alloc
    fine_remaining = fine_remaining - fine_alloc

    mora_owed = inst.expected_mora - inst.mora_paid
    mora_alloc = Money(min(max(mora_owed.raw_amount, 0), remaining.raw_amount, mora_remaining.raw_amount))
    remaining = remaining - mora_alloc
    mora_remaining = mora_remaining - mora_alloc

    interest_owed = inst.expected_interest - inst.interest_paid
    interest_alloc = Money(min(max(interest_owed.raw_amount, 0), remaining.raw_amount, interest_remaining.raw_amount))
    remaining = remaining - interest_alloc
    interest_remaining = interest_remaining - interest_alloc

    principal_owed = inst.expected_principal - inst.principal_paid
    reserved = interest_remaining + mora_remaining
    available_for_principal = remaining - reserved if remaining.raw_amount > reserved.raw_amount else Money.zero()
    principal_alloc = Money(min(max(principal_owed.raw_amount, 0), available_for_principal.raw_amount))
    remaining = remaining - principal_alloc

    total = fine_alloc + mora_alloc + interest_alloc + principal_alloc
    is_covered = total >= (inst.balance - _COVERAGE_TOLERANCE)

    allocation = Allocation(
        installment_number=inst.number,
        principal_allocated=principal_alloc,
        interest_allocated=interest_alloc,
        mora_allocated=mora_alloc,
        fine_allocated=fine_alloc,
        is_fully_covered=is_covered,
    )
    return allocation, remaining, fine_remaining, mora_remaining, interest_remaining


def _fixup_coverage_flags(
    allocations: List[Allocation],
    installments: List[Installment],
    ending_balance: Money,
    principal_total: Money,
) -> List[Allocation]:
    """Mark allocations as fully covered when the loan is paid off.

    After the allocation loop, if the post-payment balance is within
    tolerance of zero, override ``is_fully_covered`` for any allocation
    whose principal was fully allocated.
    """
    post_balance = ending_balance - principal_total
    if post_balance > _COVERAGE_TOLERANCE:
        return allocations

    inst_by_number = {inst.number: inst for inst in installments}
    fixed: List[Allocation] = []
    for alloc in allocations:
        if not alloc.is_fully_covered:
            inst = inst_by_number.get(alloc.installment_number)
            if inst is not None:
                principal_owed = inst.expected_principal - inst.principal_paid
                if alloc.principal_allocated >= (principal_owed - _COVERAGE_TOLERANCE):
                    alloc = Allocation(
                        installment_number=alloc.installment_number,
                        principal_allocated=alloc.principal_allocated,
                        interest_allocated=alloc.interest_allocated,
                        mora_allocated=alloc.mora_allocated,
                        fine_allocated=alloc.fine_allocated,
                        is_fully_covered=True,
                    )
        fixed.append(alloc)
    return fixed


def _compute_spill(
    remaining: Money,
    mora_remaining: Money,
    interest_remaining: Money,
) -> Tuple[Money, Money, Money]:
    """Distribute leftover payment into mora, interest, and principal.

    Returns:
        (mora_spill, interest_spill, principal_spill)
    """
    mora_spill = Money(min(remaining.raw_amount, mora_remaining.raw_amount))
    remaining = remaining - mora_spill

    interest_spill = Money(min(remaining.raw_amount, interest_remaining.raw_amount))
    remaining = remaining - interest_spill

    principal_spill = remaining if remaining.raw_amount > 0 else Money.zero()
    return mora_spill, interest_spill, principal_spill


def _reconcile_allocations(
    allocations: List[Allocation],
    installments: List[Installment],
    fine_total: Money,
    mora_total: Money,
    interest_total: Money,
    principal_total: Money,
) -> None:
    """Adjust allocations so their sums exactly match the totals.

    Sub-cent allocations and spill can cause the totals to diverge
    from ``sum(allocations)``.  This single sweep fixes the gap by
    adjusting the last allocation.  If no allocations exist yet,
    a new one is created for the last installment.
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


def allocate_payment_into_installments(
    amount: Money,
    installments: List[Installment],
    ending_balance: Money,
    fine_cap: Money,
    interest_cap: Money,
    mora_cap: Money,
) -> Tuple[Money, Money, Money, Money, List[Allocation]]:
    """Allocate a payment across installments in priority order.

    Each installment is processed sequentially via
    :func:`allocate_payment_into_installment`.  Installment 1's
    obligations are fully addressed before installment 2 receives
    anything.

    After the per-installment loop, any leftover money (spill) is
    distributed into mora, interest, and principal totals.  A final
    reconciliation sweep adjusts the last allocation so that the
    totals always equal the sum of their per-allocation counterparts.

    Returns:
        (fine_total, mora_total, interest_total, principal_total, allocations)
    """
    remaining = amount
    fine_remaining = fine_cap
    mora_remaining = mora_cap
    interest_remaining = interest_cap
    fine_total = Money.zero()
    mora_total = Money.zero()
    interest_total = Money.zero()
    principal_total = Money.zero()
    allocations: List[Allocation] = []

    for inst in installments:
        if not remaining.raw_amount:
            break

        allocation, remaining, fine_remaining, mora_remaining, interest_remaining = (
            allocate_payment_into_installment(inst, remaining, fine_remaining, mora_remaining, interest_remaining)
        )

        if allocation.total_allocated.raw_amount <= 0:
            continue

        fine_total = fine_total + allocation.fine_allocated
        mora_total = mora_total + allocation.mora_allocated
        interest_total = interest_total + allocation.interest_allocated
        principal_total = principal_total + allocation.principal_allocated

        if allocation.total_allocated.is_positive():
            allocations.append(allocation)

    if remaining.raw_amount > 0:
        mora_spill, interest_spill, principal_spill = _compute_spill(
            remaining, mora_remaining, interest_remaining,
        )
        mora_total = mora_total + mora_spill
        interest_total = interest_total + interest_spill
        principal_total = principal_total + principal_spill

    _reconcile_allocations(allocations, installments, fine_total, mora_total, interest_total, principal_total)
    allocations = _fixup_coverage_flags(allocations, installments, ending_balance, principal_total)
    return fine_total, mora_total, interest_total, principal_total, allocations


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
) -> LoanState:
    """Forward pass: compute all settlements and derived state from payments.

    For each payment, builds installment snapshots, computes interest
    (including skipped contractual interest), and runs the per-installment
    allocation algorithm.

    Fines are computed at each payment date AND at any explicit
    ``fine_observation_dates`` (from Warp or calculate_late_fines calls).
    Without observation dates, fines are only computed when payments
    are processed -- matching the old behavior where fines required
    an explicit trigger.
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

        regular, mora = interest_calc.compute_accrued_interest(
            days,
            running_principal,
            next_due,
            last_payment_date,
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
