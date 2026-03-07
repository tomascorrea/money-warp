"""Statement data structure for billing-cycle periods."""

from dataclasses import dataclass
from datetime import datetime

from ..money import Money


@dataclass(frozen=True)
class Statement:
    """A single billing-period statement.

    Statements are derived views built by the billing cycle from a
    cash flow — they describe what happened during one period.
    """

    period_number: int
    opening_date: datetime
    closing_date: datetime
    due_date: datetime
    previous_balance: Money
    purchases_total: Money
    payments_total: Money
    refunds_total: Money
    interest_charged: Money
    fine_charged: Money
    closing_balance: Money
    minimum_payment: Money

    @property
    def is_minimum_met(self) -> bool:
        """Whether total payments in this period met the minimum requirement."""
        return self.payments_total >= self.minimum_payment
