"""CashFlow class for managing collections of financial transactions."""

from datetime import datetime
from decimal import Decimal
from typing import Iterator, List, Optional, Union

from ..money import Money
from .item import CashFlowItem
from .query import CashFlowQuery


class CashFlow:
    """
    Container for a collection of cash flow items representing a financial stream.

    A CashFlow represents a series of monetary transactions over time,
    such as loan payments, investment returns, or any financial schedule.
    """

    def __init__(self, items: Optional[List[CashFlowItem]] = None) -> None:
        """
        Create a cash flow from a list of items.

        Args:
            items: List of CashFlowItem objects (empty list if None)
        """
        self._items = list(items) if items else []

    @classmethod
    def empty(cls) -> "CashFlow":
        """Create an empty cash flow."""
        return cls([])

    def add_item(self, item: CashFlowItem) -> None:
        """Add a cash flow item to this stream."""
        self._items.append(item)

    def add(
        self,
        amount: Union[Money, Decimal, str, int, float],
        datetime: datetime,
        description: Optional[str] = None,
        category: Optional[str] = None,
    ) -> None:
        """
        Add a cash flow item by specifying its components.

        Args:
            amount: The monetary amount
            datetime: When this transaction occurs
            description: Optional description
            category: Optional category
        """
        item = CashFlowItem(amount, datetime, description, category)
        self.add_item(item)

    def items(self) -> List[CashFlowItem]:
        """Get all cash flow items (returns a copy)."""
        return list(self._items)

    def sorted_items(self) -> List[CashFlowItem]:
        """Get all cash flow items sorted by datetime."""
        return sorted(self._items, key=lambda item: item.datetime)

    @property
    def query(self) -> CashFlowQuery:
        """Create a query builder for this cash flow."""
        return CashFlowQuery(self._items)

    def __len__(self) -> int:
        """Number of cash flow items."""
        return len(self._items)

    def __iter__(self) -> Iterator[CashFlowItem]:
        """Iterate over cash flow items."""
        return iter(self._items)

    def __getitem__(self, index: int) -> CashFlowItem:
        """Get cash flow item by index."""
        return self._items[index]

    def __str__(self) -> str:
        """String representation showing summary."""
        if not self._items:
            return "CashFlow(empty)"

        total = self.net_present_value()
        count = len(self._items)
        return f"CashFlow({count} items, net: {total})"

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return f"CashFlow(items={self._items!r})"

    def __eq__(self, other: object) -> bool:
        """Two cash flows are equal if they have the same items."""
        if not isinstance(other, CashFlow):
            return False
        return self._items == other._items

    def is_empty(self) -> bool:
        """Check if this cash flow has no items."""
        return len(self._items) == 0

    def net_present_value(self) -> Money:
        """
        Calculate the net present value (simple sum, no discounting).

        This is just the sum of all cash flows. For time-value discounting,
        use the TimeMachine class with a discount rate.
        """
        if not self._items:
            return Money.zero()

        total = Money.zero()
        for item in self._items:
            total = total + item.amount
        return total

    def total_inflows(self) -> Money:
        """Sum of all positive cash flows."""
        total = Money.zero()
        for item in self._items:
            if item.is_inflow():
                total = total + item.amount
        return total

    def total_outflows(self) -> Money:
        """Sum of all negative cash flows (returned as positive amount)."""
        total = Money.zero()
        for item in self._items:
            if item.is_outflow():
                total = total + abs(item.amount)
        return total

    def filter_by_category(self, category: str) -> "CashFlow":
        """Create a new CashFlow containing only items with the specified category."""
        return self.query.filter_by(category=category).to_cash_flow()

    def filter_by_datetime_range(self, start_datetime: datetime, end_datetime: datetime) -> "CashFlow":
        """Create a new CashFlow containing only items within the datetime range (inclusive)."""
        return self.query.filter_by(datetime__gte=start_datetime, datetime__lte=end_datetime).to_cash_flow()

    def earliest_datetime(self) -> Optional[datetime]:
        """Get the earliest datetime in this cash flow, or None if empty."""
        if not self._items:
            return None
        return min(item.datetime for item in self._items)

    def latest_datetime(self) -> Optional[datetime]:
        """Get the latest datetime in this cash flow, or None if empty."""
        if not self._items:
            return None
        return max(item.datetime for item in self._items)
