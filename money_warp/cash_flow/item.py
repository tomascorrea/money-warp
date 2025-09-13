"""CashFlowItem class for individual financial transactions."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, Union

from ..money import Money


class CashFlowItem:
    """
    Represents a single financial transaction at a specific point in time.

    A CashFlowItem is an individual monetary movement with metadata about
    when it occurred, what it was for, and how to categorize it.
    """

    def __init__(
        self,
        amount: Union[Money, Decimal, str, int, float],
        datetime: datetime,
        description: Optional[str] = None,
        category: Optional[str] = None,
    ) -> None:
        """
        Create a cash flow item.

        Args:
            amount: The monetary amount (positive for inflows, negative for outflows)
            datetime: When this transaction occurs
            description: Optional description of the transaction
            category: Optional category for grouping (e.g., "interest", "principal", "fee")
        """
        self.amount = amount if isinstance(amount, Money) else Money(amount)
        self.datetime = datetime
        self.description = description
        self.category = category

    def __str__(self) -> str:
        """String representation showing amount, datetime, and description."""
        desc = f" - {self.description}" if self.description else ""
        return f"{self.amount} on {self.datetime}{desc}"

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"CashFlowItem(amount={self.amount!r}, datetime={self.datetime!r}, "
            f"description={self.description!r}, category={self.category!r})"
        )

    def __eq__(self, other: object) -> bool:
        """Two cash flow items are equal if all fields match."""
        if not isinstance(other, CashFlowItem):
            return False
        return (
            self.amount == other.amount
            and self.datetime == other.datetime
            and self.description == other.description
            and self.category == other.category
        )

    def is_inflow(self) -> bool:
        """Check if this is a positive cash flow (money coming in)."""
        return self.amount.is_positive()

    def is_outflow(self) -> bool:
        """Check if this is a negative cash flow (money going out)."""
        return self.amount.is_negative()

    def is_zero(self) -> bool:
        """Check if this is a zero cash flow."""
        return self.amount.is_zero()
