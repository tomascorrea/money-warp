"""Fine tracking for late loan payments."""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from ..interest_rate import InterestRate
from ..money import Money
from ..scheduler import PaymentSchedule
from ..time_context import TimeContext
from ..tz import to_datetime

_PAYMENT_CATEGORIES = frozenset({"principal", "interest", "fine"})
_TOLERANCE = Money("0.01")
_WINDOW_DAYS_BEFORE = 3
_WINDOW_DAYS_AFTER = 1


class FineTracker:
    """Tracks late-payment fines for a loan.

    Holds the fine-related state (``fines_applied``) and all logic for
    detecting late payments and computing fine amounts.  Reads payment
    data from a shared list of CashFlowItems but never mutates it.
    """

    def __init__(
        self,
        fine_rate: InterestRate,
        grace_period_days: int,
        time_context: TimeContext,
    ) -> None:
        self.fine_rate = fine_rate
        self.grace_period_days = grace_period_days
        self._time_ctx = time_context
        self.fines_applied: Dict[date, Money] = {}

    def now(self) -> datetime:
        return self._time_ctx.now()

    @property
    def total_fines(self) -> Money:
        """Total amount of fines applied to the loan."""
        if not self.fines_applied:
            return Money.zero()
        return Money(sum(fine.raw_amount for fine in self.fines_applied.values()))

    def fine_balance(self, actual_payments: list) -> Money:
        """Unpaid fine amount (total applied minus fines paid).

        Args:
            actual_payments: CashFlowItems visible at the current time.
        """
        total = self.total_fines
        fines_paid = Money.zero()
        for payment in actual_payments:
            if "fine" in payment.category:
                fines_paid = fines_paid + payment.amount
        outstanding = total - fines_paid
        return outstanding if outstanding.is_positive() else Money.zero()

    def is_payment_late(self, due_date: date, as_of: Optional[datetime] = None) -> bool:
        """Whether a payment is late considering the grace period."""
        check_date = as_of.date() if as_of is not None else self.now().date()
        effective_due_date = due_date + timedelta(days=self.grace_period_days)
        return check_date > effective_due_date

    def calculate_late_fines(
        self,
        due_dates: List[date],
        schedule: PaymentSchedule,
        all_payments: list,
        as_of: Optional[datetime] = None,
    ) -> Money:
        """Calculate and apply fines for any newly late payments.

        Args:
            due_dates: All loan due dates.
            schedule: The original payment schedule.
            all_payments: All CashFlowItems ever recorded on the loan.
            as_of: Override for the check date (defaults to now()).

        Returns:
            Total amount of new fines applied in this call.
        """
        as_of = as_of if as_of is not None else self.now()
        new_fines = Money.zero()

        for due_date in due_dates:
            if due_date in self.fines_applied:
                continue
            if not self.is_payment_late(due_date, as_of):
                continue
            if self._has_payment_for_due_date(due_date, as_of, schedule, all_payments):
                continue

            expected_payment = _get_expected_payment(due_date, due_dates, schedule)
            fine_amount = Money(expected_payment.raw_amount * self.fine_rate.as_decimal())
            self.fines_applied[due_date] = fine_amount
            new_fines = new_fines + fine_amount

        return new_fines

    def _has_payment_for_due_date(
        self,
        due_date: date,
        as_of: datetime,
        schedule: PaymentSchedule,
        all_payments: list,
    ) -> bool:
        """Check if sufficient payment has been made for a specific due date."""
        expected_payment = _get_expected_payment(due_date, [due_date], schedule)

        exact_date_payments = [
            p
            for p in all_payments
            if p.datetime.date() == due_date and p.datetime <= as_of and not p.category.isdisjoint(_PAYMENT_CATEGORIES)
        ]
        total_on_date = sum((p.amount for p in exact_date_payments), Money.zero())
        if total_on_date >= (expected_payment - _TOLERANCE):
            return True

        window_start = to_datetime(due_date - timedelta(days=_WINDOW_DAYS_BEFORE))
        window_end = min(as_of, to_datetime(due_date + timedelta(days=_WINDOW_DAYS_AFTER)))
        window_payments = [
            p
            for p in all_payments
            if window_start <= p.datetime <= window_end
            and p.datetime <= as_of
            and not p.category.isdisjoint(_PAYMENT_CATEGORIES)
        ]
        total_in_window = sum((p.amount for p in window_payments), Money.zero())
        return total_in_window >= (expected_payment - _TOLERANCE)


def _get_expected_payment(due_date: date, due_dates: List[date], schedule: PaymentSchedule) -> Money:
    """Look up the expected payment amount for a due date from the schedule."""
    if due_date not in due_dates:
        raise ValueError(f"Due date {due_date} is not in loan's due dates")
    for entry in schedule:
        if entry.due_date == due_date:
            return entry.payment_amount
    raise ValueError(f"Could not find payment amount for due date {due_date}")
