"""CashFlow class for managing collections of financial transactions."""

from datetime import datetime
from decimal import Decimal
from typing import Iterator, List, Optional, Union

from ..money import Money
from .entry import CashFlowEntry
from .item import CashFlowItem
from .query import CashFlowQuery


class CashFlow:
    """Container for a collection of cash flow items representing a financial stream.

    Internally stores :class:`CashFlowItem` (temporal containers).
    Public iteration and query methods resolve each item and filter out
    deleted entries, so consumers see only active :class:`CashFlowEntry`
    objects.
    """

    def __init__(self, items: Optional[List[CashFlowItem]] = None) -> None:
        self._items: List[CashFlowItem] = list(items) if items else []

    @classmethod
    def empty(cls) -> "CashFlow":
        """Create an empty cash flow."""
        return cls([])

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

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
        """Add a cash flow item by specifying its components."""
        item = CashFlowItem(amount, datetime, description, category)
        self.add_item(item)

    # ------------------------------------------------------------------
    # Resolved access (public API)
    # ------------------------------------------------------------------

    def items(self) -> List[CashFlowEntry]:
        """Active entries at the current time (resolves and filters)."""
        return [entry for item in self._items if (entry := item.resolve()) is not None]

    def sorted_items(self) -> List[CashFlowEntry]:
        """Active entries sorted by datetime."""
        return sorted(self.items(), key=lambda e: e.datetime)

    # ------------------------------------------------------------------
    # Raw access (for internal temporal operations)
    # ------------------------------------------------------------------

    def raw_items(self) -> List[CashFlowItem]:
        """Underlying temporal containers (use for update/delete)."""
        return list(self._items)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    @property
    def query(self) -> CashFlowQuery:
        """Create a query builder over active entries."""
        return CashFlowQuery(self.items())

    # ------------------------------------------------------------------
    # Iterable interface (all resolve + filter)
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.items())

    def __iter__(self) -> Iterator[CashFlowEntry]:
        return iter(self.items())

    def __getitem__(self, index: int) -> CashFlowEntry:
        return self.items()[index]

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        resolved = self.items()
        if not resolved:
            return "CashFlow(empty)"
        total = self.net_present_value()
        return f"CashFlow({len(resolved)} items, net: {total})"

    def __repr__(self) -> str:
        return f"CashFlow(items={self._items!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CashFlow):
            return False
        return self._items == other._items

    # ------------------------------------------------------------------
    # Aggregation (all operate on resolved entries)
    # ------------------------------------------------------------------

    def is_empty(self) -> bool:
        return len(self.items()) == 0

    def net_present_value(self) -> Money:
        """Simple sum of all active cash flows (no discounting)."""
        entries = self.items()
        if not entries:
            return Money.zero()
        total = Money.zero()
        for entry in entries:
            total = total + entry.amount
        return total

    def total_inflows(self) -> Money:
        """Sum of all positive cash flows."""
        total = Money.zero()
        for entry in self.items():
            if entry.is_inflow():
                total = total + entry.amount
        return total

    def total_outflows(self) -> Money:
        """Sum of all negative cash flows (returned as positive amount)."""
        total = Money.zero()
        for entry in self.items():
            if entry.is_outflow():
                total = total + abs(entry.amount)
        return total

    def filter_by_category(self, category: str) -> "CashFlow":
        """New CashFlow containing only items with the specified category."""
        return self.query.filter_by(category=category).to_cash_flow()

    def filter_by_datetime_range(self, start_datetime: datetime, end_datetime: datetime) -> "CashFlow":
        """New CashFlow containing only items within the datetime range."""
        return self.query.filter_by(datetime__gte=start_datetime, datetime__lte=end_datetime).to_cash_flow()

    def earliest_datetime(self) -> Optional[datetime]:
        entries = self.items()
        if not entries:
            return None
        return min(e.datetime for e in entries)

    def latest_datetime(self) -> Optional[datetime]:
        entries = self.items()
        if not entries:
            return None
        return max(e.datetime for e in entries)
