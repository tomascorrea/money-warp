"""Statement data structure for credit card billing periods."""

from dataclasses import dataclass
from datetime import datetime

from ..money import Money


@dataclass(frozen=True)
class Statement:
    """A single billing-period statement for a credit card.

    Statements are consequences of the credit card's cash flow — they
    describe what happened during one billing cycle.  The CreditCard
    builds these on demand as derived views, never as stored state.
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
