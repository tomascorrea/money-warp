"""CashFlowQuery class for SQLAlchemy-style filtering and querying."""

from typing import TYPE_CHECKING, Any, Callable, List, Optional

from ..money import Money
from .item import CashFlowItem

if TYPE_CHECKING:
    from .flow import CashFlow


class CashFlowQuery:
    """
    SQLAlchemy-style query builder for filtering and manipulating cash flows.

    Allows chaining operations like:
    cash_flow.query.filter_by(category='loan').filter_by(amount__gt=Money("100")).order_by('datetime').all()
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
        # Import here to avoid circular imports
        from .flow import CashFlow

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
