"""Fine computation and late-payment detection."""

from datetime import date, datetime, timedelta, tzinfo
from typing import Dict, List, Optional, Set

from ..scheduler import PaymentSchedule
from ..types.interest_rate import InterestRate
from ..types.money import Money
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
    balance_tolerance: Money = BALANCE_TOLERANCE,
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
        balance_tolerance: Sub-cent threshold for "sufficient" payment;
            defaults to the engine-wide ``BALANCE_TOLERANCE``. This is
            the same setting that controls ``Installment.is_fully_paid``,
            so widening it on a ``Loan`` / ``BillingCycleLoan`` also
            relaxes when a small underpayment triggers a fine on the
            related due date.
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
    if sum((p.amount for p in exact), Money.zero()) >= (expected - balance_tolerance):
        return True

    window_start = to_datetime(due_date - timedelta(days=_WINDOW_DAYS_BEFORE), tz)
    window_end = min(as_of, to_datetime(due_date + timedelta(days=_WINDOW_DAYS_AFTER), tz))
    window = [p for p in payment_entries if window_start <= p.datetime <= window_end and p.datetime <= as_of]
    return sum((p.amount for p in window), Money.zero()) >= (expected - balance_tolerance)


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
    balance_tolerance: Money = BALANCE_TOLERANCE,
    settled_due_dates: Optional[Set[date]] = None,
) -> Dict[date, Money]:
    """Compute fines for overdue due dates as of *as_of*.

    A due date gets a fine when it is past the grace period AND
    no sufficient payment was made near it (within a small window)
    AND its installment is not already settled.

    When the original due date falls on a non-working day, the
    effective due date is shifted to the next working day for both
    the lateness check and the payment proximity window.

    Args:
        settled_due_dates: Due dates whose principal is already covered
            by strictly earlier payments; must be computed **before**
            allocating the current event.  These are exempt from new
            fines: a settlement accepted as full coverage (e.g. under
            ``waive_overdue_interest`` or with a discount) can leave
            the cash near the due date below the original schedule
            face, so the proximity-amount check alone would invent a
            retroactive fine on an installment that owes nothing.
            Passing coverage computed *after* the current event's
            payment would silence the legitimate fine born at the
            first late event.  Due dates after *as_of* (the time-machine
            / observation date) are ignored even if present in the set —
            prepayment can mark future installments as principal-covered,
            but they have not settled yet under the warped clock.
    """
    fines = dict(existing_fines)
    as_of_date = to_date(as_of, tz)
    # Drop dues that are still in the future relative to the observation
    # clock; principal_covered_count may include them after anticipation.
    settled = {dd for dd in (settled_due_dates or set()) if dd <= as_of_date}

    for dd in due_dates:
        if dd in fines:
            continue
        # The exemption deliberately reuses the forward pass's own
        # definition of coverage (principal_covered_count): principal
        # only receives money after every effective obligation ahead
        # of it in the waterfall (fine, mora, waiver-capped interest)
        # is satisfied, so a covered installment owes nothing more.
        if dd in settled:
            continue
        if not is_payment_late(dd, grace_period_days, as_of, tz, calendar):
            continue
        penalty_dd = effective_penalty_due_date(dd, calendar)
        if _has_payment_near(
            penalty_dd,
            as_of,
            schedule,
            payment_entries,
            tz,
            schedule_due_date=dd,
            balance_tolerance=balance_tolerance,
        ):
            continue
        for entry in schedule:
            if entry.due_date == dd:
                fine_amount = Money(entry.payment_amount.raw_amount * fine_rate.as_decimal())
                fines[dd] = fine_amount
                break

    return fines
