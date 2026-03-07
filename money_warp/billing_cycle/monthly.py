"""Monthly billing cycle — statements close on a fixed day each month."""

from datetime import datetime, timedelta
from typing import List

from dateutil.relativedelta import relativedelta

from ..tz import ensure_aware, tz_aware
from .base import BaseBillingCycle


class MonthlyBillingCycle(BaseBillingCycle):
    """Billing cycle that closes on a fixed calendar day every month.

    Args:
        closing_day: Day of month (1-28) when the statement closes.
        payment_due_days: Number of days after closing for the payment
            due date.  Defaults to 15.
    """

    def __init__(self, closing_day: int = 1, payment_due_days: int = 15) -> None:
        if not 1 <= closing_day <= 28:
            raise ValueError("closing_day must be between 1 and 28")
        if payment_due_days < 1:
            raise ValueError("payment_due_days must be at least 1")
        self.closing_day = closing_day
        self.payment_due_days = payment_due_days

    @tz_aware
    def closing_dates_between(self, start: datetime, end: datetime) -> List[datetime]:
        """Return monthly closing dates strictly after *start* up to *end*."""
        first = self._next_closing_after(start)
        dates: List[datetime] = []
        current = first
        while current <= end:
            dates.append(current)
            current = current + relativedelta(months=1)
        return dates

    @tz_aware
    def due_date_for(self, closing_date: datetime) -> datetime:
        return closing_date + timedelta(days=self.payment_due_days)

    def _next_closing_after(self, dt: datetime) -> datetime:
        """First closing date strictly after *dt*."""
        candidate = dt.replace(day=self.closing_day, hour=23, minute=59, second=59, microsecond=0)
        candidate = ensure_aware(candidate)
        if candidate <= dt:
            candidate = candidate + relativedelta(months=1)
        return candidate

    def __repr__(self) -> str:
        return f"MonthlyBillingCycle(closing_day={self.closing_day}, payment_due_days={self.payment_due_days})"
