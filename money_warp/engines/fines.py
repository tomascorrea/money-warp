"""Fine computation and late-payment detection."""

from datetime import date, datetime, timedelta, tzinfo
from typing import Dict, List, Optional

from ..interest_rate import InterestRate
from ..money import Money
from ..scheduler import PaymentSchedule
from ..tz import to_date, to_datetime
from ..working_day import WorkingDayCalendar, effective_penalty_due_date
from .constants import BALANCE_TOLERANCE

_WINDOW_DAYS_BEFORE = 3
_WINDOW_DAYS_AFTER = 1


def is_payment_late(
    due_date: date,
    grace_period_days: int,
    as_of: datetime,
    tz: tzinfo,
    calendar: WorkingDayCalendar,
) -> bool:
    """Whether a payment is late considering the grace period.

    The effective due date is adjusted to the next working day when
    the original due date falls on a non-working day.
    """
    penalty_due = effective_penalty_due_date(due_date, calendar)
    effective_due = penalty_due + timedelta(days=grace_period_days)
    return to_date(as_of, tz) > effective_due


def _has_payment_near(
    due_date: date,
    as_of: datetime,
    schedule: PaymentSchedule,
    payment_entries: list,
    tz: tzinfo,
    schedule_due_date: Optional[date] = None,
) -> bool:
    """Check if sufficient payment has been made near a due date.

    Replicates the old FineTracker's temporal proximity check:
    exact-date match first, then a small window around the due date.

    Args:
        due_date: The date to center the payment window on (may be
            the effective penalty due date).
        schedule_due_date: When provided, used for the schedule-entry
            lookup instead of *due_date*.  This allows the window to
            be centered on the effective date while looking up the
            expected amount from the original schedule date.
    """
    lookup_date = schedule_due_date if schedule_due_date is not None else due_date

    expected = Money.zero()
    for entry in schedule:
        if entry.due_date == lookup_date:
            expected = entry.payment_amount
            break
    if expected.is_zero():
        return False

    exact = [p for p in payment_entries if to_date(p.datetime, tz) == due_date and p.datetime <= as_of]
    if sum((p.amount for p in exact), Money.zero()) >= (expected - BALANCE_TOLERANCE):
        return True

    window_start = to_datetime(due_date - timedelta(days=_WINDOW_DAYS_BEFORE), tz)
    window_end = min(as_of, to_datetime(due_date + timedelta(days=_WINDOW_DAYS_AFTER), tz))
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
    tz: tzinfo,
    calendar: WorkingDayCalendar,
) -> Dict[date, Money]:
    """Compute fines for overdue due dates as of *as_of*.

    A due date gets a fine when it is past the grace period AND
    no sufficient payment was made near it (within a small window).

    When the original due date falls on a non-working day, the
    effective due date is shifted to the next working day for both
    the lateness check and the payment proximity window.
    """
    fines = dict(existing_fines)

    for dd in due_dates:
        if dd in fines:
            continue
        if not is_payment_late(dd, grace_period_days, as_of, tz, calendar):
            continue
        penalty_dd = effective_penalty_due_date(dd, calendar)
        if _has_payment_near(penalty_dd, as_of, schedule, payment_entries, tz, schedule_due_date=dd):
            continue
        for entry in schedule:
            if entry.due_date == dd:
                fine_amount = Money(entry.payment_amount.raw_amount * fine_rate.as_decimal())
                fines[dd] = fine_amount
                break

    return fines
