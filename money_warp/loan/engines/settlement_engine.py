"""Settlement computation from cashflow data.

All allocation emerges from the CashFlow + schedule. Nothing is
decomposed or stored at payment time. The forward pass through
payments replicates the financial allocation algorithm (per-installment
priority: fine -> mora -> interest -> principal) on demand.
"""

from datetime import date, datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ...interest_rate import InterestRate
from ...money import Money
from ...scheduler import PaymentSchedule
from ...tz import to_datetime
from ..installment import Installment
from ..settlement import Settlement, SettlementAllocation
from .interest_calculator import InterestCalculator

_COVERAGE_TOLERANCE = Money("0.01")


@dataclass(frozen=True)
class LoanState:
    """Snapshot of derived loan state from the forward pass."""

    settlements: List[Settlement]
    principal_balance: Money
    fines_applied: Dict[date, Money]
    fines_paid_total: Money
    last_payment_date: datetime


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

    exact = [
        p for p in payment_entries
        if p.datetime.date() == due_date and p.datetime <= as_of
    ]
    if sum((p.amount for p in exact), Money.zero()) >= (expected - _COVERAGE_TOLERANCE):
        return True

    window_start = to_datetime(due_date - timedelta(days=_WINDOW_DAYS_BEFORE))
    window_end = min(as_of, to_datetime(due_date + timedelta(days=_WINDOW_DAYS_AFTER)))
    window = [
        p for p in payment_entries
        if window_start <= p.datetime <= window_end and p.datetime <= as_of
    ]
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

def allocate_payment_per_installment(
    amount: Money,
    installments: List[Installment],
    ending_balance: Money,
    fine_cap: Money,
    interest_cap: Money,
    mora_cap: Money,
) -> Tuple[Money, Money, Money, Money, List[SettlementAllocation]]:
    """Allocate a payment across installments in priority order.

    Each installment is processed sequentially. Within each
    installment the priority is fine -> mora -> interest -> principal.
    Installment 1's obligations are fully addressed before
    installment 2 receives anything.

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
    allocations: List[SettlementAllocation] = []

    for inst in installments:
        if not remaining.raw_amount:
            break

        allocation, remaining, fine_remaining, mora_remaining, interest_remaining = inst.allocate_from_payment(
            remaining, fine_remaining, mora_remaining, interest_remaining,
        )

        if allocation.total_allocated.raw_amount <= 0:
            continue

        fine_total = fine_total + allocation.fine_allocated
        mora_total = mora_total + allocation.mora_allocated
        interest_total = interest_total + allocation.interest_allocated
        principal_total = principal_total + allocation.principal_allocated

        if not allocation.total_allocated.is_positive():
            continue
        allocations.append(allocation)

    if remaining.raw_amount > 0:
        mora_spill = Money(min(remaining.raw_amount, mora_remaining.raw_amount))
        remaining = remaining - mora_spill
        mora_total = mora_total + mora_spill

        interest_spill = Money(min(remaining.raw_amount, interest_remaining.raw_amount))
        remaining = remaining - interest_spill
        interest_total = interest_total + interest_spill

        if remaining.raw_amount > 0:
            principal_total = principal_total + remaining

    post_balance = ending_balance - principal_total
    if post_balance <= _COVERAGE_TOLERANCE:
        inst_by_number = {inst.number: inst for inst in installments}
        fixed: List[SettlementAllocation] = []
        for alloc in allocations:
            if not alloc.is_fully_covered:
                inst = inst_by_number.get(alloc.installment_number)
                if inst is not None:
                    principal_owed = inst.expected_principal - inst.principal_paid
                    if alloc.principal_allocated >= (principal_owed - _COVERAGE_TOLERANCE):
                        alloc = SettlementAllocation(
                            installment_number=alloc.installment_number,
                            principal_allocated=alloc.principal_allocated,
                            interest_allocated=alloc.interest_allocated,
                            mora_allocated=alloc.mora_allocated,
                            fine_allocated=alloc.fine_allocated,
                            is_fully_covered=True,
                        )
            fixed.append(alloc)
        allocations = fixed

    return fine_total, mora_total, interest_total, principal_total, allocations


# ------------------------------------------------------------------
# Installment snapshot construction
# ------------------------------------------------------------------

def _build_installments_snapshot(
    allocs_by_number: Dict[int, List[SettlementAllocation]],
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
                    total_days, principal_balance, entry.due_date, last_payment_date,
                )
            else:
                days_overdue = (as_of_date.date() - entry.due_date).days
                _, accrued_mora = interest_calc.compute_accrued_interest(
                    days_overdue, principal_balance, entry.due_date, to_datetime(entry.due_date),
                )
            expected_mora = prior_mora + accrued_mora
        else:
            expected_mora = Money.zero()

        result.append(Installment.from_schedule_entry(entry, allocs, expected_mora, expected_fine))

    return result


# ------------------------------------------------------------------
# Forward pass: compute all settlements from cashflow
# ------------------------------------------------------------------

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
    settlements: List[Settlement] = []
    allocs_by_number: Dict[int, List[SettlementAllocation]] = {}
    processed_payments: list = []

    # Build a merged timeline of payment events and fine observation points
    events: List[Tuple[datetime, bool, Optional[object]]] = []
    for payment in payment_entries:
        events.append((payment.datetime, True, payment))
    if fine_observation_dates:
        for dt in fine_observation_dates:
            events.append((dt, False, None))
    events.sort(key=lambda e: (e[0], not e[1]))

    for event_dt, is_payment, payment in events:
        if event_dt > as_of:
            break

        # Compute fines using only previously processed payments
        fines_applied = compute_fines_at(
            event_dt, due_dates, schedule,
            fine_rate, grace_period_days, fines_applied,
            processed_payments,
        )

        if not is_payment:
            continue

        # Compute interest
        interest_date = payment.interest_date if payment.interest_date is not None else payment.datetime
        days = max(0, (interest_date.date() - last_payment_date.date()).days)

        covered = covered_due_date_count(running_principal, schedule)
        next_due = due_dates[covered] if covered < len(due_dates) else None

        regular, mora = interest_calc.compute_accrued_interest(
            days, running_principal, next_due, last_payment_date,
        )

        # Build installment snapshot for allocation
        installments = _build_installments_snapshot(
            allocs_by_number, running_principal, payment.datetime,
            schedule, fines_applied, interest_calc,
            last_payment_date=last_payment_date,
        )

        # Skipped contractual interest
        skipped = _skipped_contractual_interest(installments, next_due, interest_date.date())
        interest_cap = Money(regular.raw_amount + skipped.raw_amount)

        # Fine balance
        total_fines_amount = (
            Money(sum(f.raw_amount for f in fines_applied.values()))
            if fines_applied
            else Money.zero()
        )
        fine_balance = total_fines_amount - fines_paid_total
        if fine_balance.is_negative():
            fine_balance = Money.zero()

        # Per-installment allocation
        fine_paid, mora_paid, interest_paid, principal_paid, allocations = allocate_payment_per_installment(
            payment.amount, installments, running_principal,
            fine_cap=fine_balance, interest_cap=interest_cap, mora_cap=mora,
        )

        # Update running state
        fines_paid_total = fines_paid_total + fine_paid
        running_principal = running_principal - principal_paid
        if running_principal.is_negative():
            running_principal = Money.zero()

        for a in allocations:
            allocs_by_number.setdefault(a.installment_number, []).append(a)

        settlements.append(Settlement(
            payment_amount=payment.amount,
            payment_date=payment.datetime,
            fine_paid=fine_paid,
            interest_paid=interest_paid,
            mora_paid=mora_paid,
            principal_paid=principal_paid,
            remaining_balance=running_principal,
            allocations=allocations,
        ))

        last_payment_date = payment.datetime
        processed_payments.append(payment)

    return LoanState(
        settlements=settlements,
        principal_balance=running_principal,
        fines_applied=fines_applied,
        fines_paid_total=fines_paid_total,
        last_payment_date=last_payment_date,
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
    allocs_by_number: Dict[int, List[SettlementAllocation]] = {}
    for settlement in settlements:
        for a in settlement.allocations:
            allocs_by_number.setdefault(a.installment_number, []).append(a)

    return _build_installments_snapshot(
        allocs_by_number, principal_balance, as_of,
        schedule, fines_applied, interest_calc,
        last_payment_date=last_payment_date,
    )
