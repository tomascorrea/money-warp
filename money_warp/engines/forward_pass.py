"""Unified forward pass: replay payments against the schedule.

Builds settlements, installment snapshots, and derived state by
processing each payment chronologically.  Also contains coverage
helpers, installment construction, and tolerance adjustment logic
that the forward pass depends on.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from ..cash_flow import CashFlow, CashFlowItem
from ..interest_rate import InterestRate
from ..loan.allocation import Allocation
from ..loan.installment import Installment
from ..loan.settlement import Settlement
from ..money import Money
from ..scheduler import PaymentSchedule, PaymentScheduleEntry
from ..time_context import TimeContext
from ..tz import to_datetime
from .allocation import allocate_payment_into_installments
from .constants import BALANCE_TOLERANCE
from .fines import compute_fines_at
from .interest import InterestCalculator, MoraRateCallback


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


def covered_due_date_count(
    remaining_balance: Money,
    schedule: PaymentSchedule,
) -> int:
    """How many due dates are covered given a remaining principal balance."""
    covered = 0
    for entry in schedule:
        if remaining_balance <= entry.ending_balance + BALANCE_TOLERANCE:
            covered += 1
        else:
            break
    return covered


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
    last_accrual_end = disbursement_date
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
        days = max(0, (interest_date.date() - last_accrual_end.date()).days)

        covered = covered_due_date_count(running_principal, schedule)
        next_due = due_dates[covered] if covered < len(due_dates) else None

        mora_override = mora_rate_for_event(next_due) if mora_rate_for_event else None

        regular, mora = interest_calc.compute_accrued_interest(
            days,
            running_principal,
            next_due,
            last_accrual_end,
            mora_rate_override=mora_override,
        )

        installments = _build_installments_snapshot(
            allocs_by_number,
            running_principal,
            payment.datetime,
            schedule,
            fines_applied,
            interest_calc,
            last_payment_date=last_accrual_end,
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
        last_accrual_end = max(payment.datetime, interest_date)
        processed_payments.append(payment)

    return LoanState(
        settlements=settlements,
        principal_balance=running_principal,
        fines_applied=fines_applied,
        fines_paid_total=fines_paid_total,
        last_payment_date=last_payment_date,
        last_accrual_end=last_accrual_end,
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
    last_accrual_end: datetime,
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
        last_payment_date=last_accrual_end,
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
                )
            )
