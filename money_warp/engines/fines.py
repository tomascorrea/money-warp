"""Fine computation and late-payment detection."""

from datetime import date, datetime, timedelta
from typing import Dict, List

from ..interest_rate import InterestRate
from ..money import Money
from ..scheduler import PaymentSchedule
from ..tz import to_datetime
from .constants import BALANCE_TOLERANCE

_WINDOW_DAYS_BEFORE = 3
_WINDOW_DAYS_AFTER = 1


def is_payment_late(due_date: date, grace_period_days: int, as_of: datetime) -> bool:
    """Whether a payment is late considering the grace period."""
    effective_due = due_date + timedelta(days=grace_period_days)
    return as_of.date() > effective_due


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
    if sum((p.amount for p in exact), Money.zero()) >= (expected - BALANCE_TOLERANCE):
        return True

    window_start = to_datetime(due_date - timedelta(days=_WINDOW_DAYS_BEFORE))
    window_end = min(as_of, to_datetime(due_date + timedelta(days=_WINDOW_DAYS_AFTER)))
    window = [p for p in payment_entries if window_start <= p.datetime <= window_end and p.datetime <= as_of]
    return sum((p.amount for p in window), Money.zero()) >= (expected - BALANCE_TOLERANCE)


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
