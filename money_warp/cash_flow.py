"""Cash flow classes for modeling financial transactions over time."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Callable, List, Optional, Union

from .money import Money


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


class CashFlowQuery:
    """
    SQLAlchemy-style query builder for filtering and manipulating cash flows.

    Allows chaining operations like:
    cash_flow.query.filter(category='loan').filter(amount__gt=Money("100")).order_by('datetime').all()
    """

    def __init__(self, items: List[CashFlowItem]) -> None:
        """Initialize query with a list of cash flow items."""
        self._items = list(items)  # Work with a copy

    def filter_by(self, predicate: Optional[Callable[[CashFlowItem], bool]] = None, **kwargs) -> "CashFlowQuery":
        """
        Filter items using keyword arguments or a predicate function.

        Keyword arguments:
        - category: Filter by category
        - amount: Filter by exact amount
        - amount__gt: Filter by amount greater than
        - amount__gte: Filter by amount greater than or equal
        - amount__lt: Filter by amount less than
        - amount__lte: Filter by amount less than or equal
        - datetime: Filter by exact datetime
        - datetime__gt: Filter by datetime greater than
        - datetime__gte: Filter by datetime greater than or equal
        - datetime__lt: Filter by datetime less than
        - datetime__lte: Filter by datetime less than or equal
        - description: Filter by description
        - is_inflow: Filter to only inflows (True) or outflows (False)
        """
        if predicate:
            # Use predicate function
            filtered_items = [item for item in self._items if predicate(item)]
            return CashFlowQuery(filtered_items)

        # Use keyword arguments
        filtered_items = self._items

        for key, value in kwargs.items():
            filtered_items = self._apply_single_filter(filtered_items, key, value)

        return CashFlowQuery(filtered_items)

    def _apply_single_filter(self, items: List[CashFlowItem], key: str, value: Any) -> List[CashFlowItem]:
        """Apply a single filter to the items list."""
        if key == "category":
            return [item for item in items if item.category == value]
        elif key == "description":
            return [item for item in items if item.description == value]
        elif key.startswith("amount"):
            return self._apply_amount_filter(items, key, value)
        elif key.startswith("datetime"):
            return self._apply_datetime_filter(items, key, value)
        elif key == "is_inflow":
            if value:
                return [item for item in items if item.is_inflow()]
            else:
                return [item for item in items if item.is_outflow()]
        else:
            raise ValueError(f"Unknown filter argument: {key}")

    def _apply_amount_filter(self, items: List[CashFlowItem], key: str, value: Any) -> List[CashFlowItem]:
        """Apply amount-related filter."""
        value_money = value if isinstance(value, Money) else Money(value)
        if key == "amount":
            return [item for item in items if item.amount == value_money]
        elif key == "amount__gt":
            return [item for item in items if item.amount > value_money]
        elif key == "amount__gte":
            return [item for item in items if item.amount >= value_money]
        elif key == "amount__lt":
            return [item for item in items if item.amount < value_money]
        elif key == "amount__lte":
            return [item for item in items if item.amount <= value_money]
        return items

    def _apply_datetime_filter(self, items: List[CashFlowItem], key: str, value: Any) -> List[CashFlowItem]:
        """Apply datetime-related filter."""
        if key == "datetime":
            return [item for item in items if item.datetime == value]
        elif key == "datetime__gt":
            return [item for item in items if item.datetime > value]
        elif key == "datetime__gte":
            return [item for item in items if item.datetime >= value]
        elif key == "datetime__lt":
            return [item for item in items if item.datetime < value]
        elif key == "datetime__lte":
            return [item for item in items if item.datetime <= value]
        return items

    def order_by(self, *fields: str) -> "CashFlowQuery":
        """
        Order items by one or more fields.

        Fields can be: 'datetime', 'amount', 'description', 'category'
        Prefix with '-' for descending order: '-datetime', '-amount'
        """
        items = list(self._items)

        # Apply sorts in reverse order so the first field has priority
        for field in reversed(fields):
            reverse = False
            if field.startswith("-"):
                reverse = True
                field = field[1:]

            if field == "datetime":
                items.sort(key=lambda item: item.datetime, reverse=reverse)
            elif field == "amount":
                items.sort(key=lambda item: item.amount.real_amount, reverse=reverse)
            elif field == "description":
                items.sort(key=lambda item: item.description or "", reverse=reverse)
            elif field == "category":
                items.sort(key=lambda item: item.category or "", reverse=reverse)
            else:
                raise ValueError(f"Unknown field: {field}")

        return CashFlowQuery(items)

    def limit(self, count: int) -> "CashFlowQuery":
        """Limit to first N items."""
        return CashFlowQuery(self._items[:count])

    def offset(self, count: int) -> "CashFlowQuery":
        """Skip first N items."""
        return CashFlowQuery(self._items[count:])

    def first(self) -> Optional[CashFlowItem]:
        """Get the first item, or None if empty."""
        return self._items[0] if self._items else None

    def last(self) -> Optional[CashFlowItem]:
        """Get the last item, or None if empty."""
        return self._items[-1] if self._items else None

    def count(self) -> int:
        """Count the number of items."""
        return len(self._items)

    def sum_amounts(self) -> Money:
        """Sum all amounts."""
        if not self._items:
            return Money.zero()
        total = Money.zero()
        for item in self._items:
            total = total + item.amount
        return total

    def get_all(self) -> List[CashFlowItem]:
        """Get all items as a list."""
        return list(self._items)

    # Convenience aliases for cleaner interface
    def all(self) -> List[CashFlowItem]:  # noqa: A003
        """Alias for get_all() - get all items as a list."""
        return self.get_all()

    def to_cash_flow(self) -> "CashFlow":
        """Convert query result back to a CashFlow object."""
        return CashFlow(self._items)

    def __len__(self) -> int:
        """Number of items in query result."""
        return len(self._items)

    def __iter__(self):
        """Iterate over query results."""
        return iter(self._items)

    def __getitem__(self, index: int) -> CashFlowItem:
        """Get item by index."""
        return self._items[index]


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

    def __iter__(self):
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
