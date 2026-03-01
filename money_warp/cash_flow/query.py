"""CashFlowQuery class for SQLAlchemy-style filtering and querying."""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Iterator, List, Optional, Union

from ..money import Money
from ..tz import ensure_aware
from .entry import CashFlowEntry
from .item import CashFlowItem

if TYPE_CHECKING:
    from .flow import CashFlow

FlowElement = Union[CashFlowEntry, CashFlowItem]


class CashFlowQuery:
    """SQLAlchemy-style query builder for filtering cash flow entries.

    Works with both :class:`CashFlowEntry` and :class:`CashFlowItem`
    objects — both expose the same attribute interface (``amount``,
    ``datetime``, ``description``, ``category``).
    """

    def __init__(self, items: List[FlowElement]) -> None:
        self._items: List[FlowElement] = list(items)

    def filter_by(
        self,
        predicate: Optional[Callable[[FlowElement], bool]] = None,
        **kwargs: Any,
    ) -> "CashFlowQuery":
        """Filter items using keyword arguments or a predicate function.

        Keyword arguments:
        - category: Filter by category
        - amount / amount__gt / amount__gte / amount__lt / amount__lte
        - datetime / datetime__gt / datetime__gte / datetime__lt / datetime__lte
        - description: Filter by description
        - is_inflow: Filter to only inflows (True) or outflows (False)
        """
        if predicate:
            return CashFlowQuery([i for i in self._items if predicate(i)])

        filtered = self._items
        for key, value in kwargs.items():
            filtered = self._apply_single_filter(filtered, key, value)
        return CashFlowQuery(filtered)

    def _apply_single_filter(self, items: List[FlowElement], key: str, value: Any) -> List[FlowElement]:
        if key == "category":
            return [i for i in items if i.category == value]
        elif key == "description":
            return [i for i in items if i.description == value]
        elif key.startswith("amount"):
            return self._apply_amount_filter(items, key, value)
        elif key.startswith("datetime"):
            return self._apply_datetime_filter(items, key, value)
        elif key == "is_inflow":
            if value:
                return [i for i in items if i.is_inflow()]
            else:
                return [i for i in items if i.is_outflow()]
        else:
            raise ValueError(f"Unknown filter argument: {key}")

    def _apply_amount_filter(self, items: List[FlowElement], key: str, value: Any) -> List[FlowElement]:
        value_money = value if isinstance(value, Money) else Money(value)
        if key == "amount":
            return [i for i in items if i.amount == value_money]
        elif key == "amount__gt":
            return [i for i in items if i.amount > value_money]
        elif key == "amount__gte":
            return [i for i in items if i.amount >= value_money]
        elif key == "amount__lt":
            return [i for i in items if i.amount < value_money]
        elif key == "amount__lte":
            return [i for i in items if i.amount <= value_money]
        return items

    def _apply_datetime_filter(self, items: List[FlowElement], key: str, value: Any) -> List[FlowElement]:
        if isinstance(value, datetime):
            value = ensure_aware(value)
        if key == "datetime":
            return [i for i in items if i.datetime == value]
        elif key == "datetime__gt":
            return [i for i in items if i.datetime > value]
        elif key == "datetime__gte":
            return [i for i in items if i.datetime >= value]
        elif key == "datetime__lt":
            return [i for i in items if i.datetime < value]
        elif key == "datetime__lte":
            return [i for i in items if i.datetime <= value]
        return items

    def order_by(self, *fields: str) -> "CashFlowQuery":
        """Order items by one or more fields.

        Prefix with '-' for descending: '-datetime', '-amount'.
        """
        items = list(self._items)
        for field in reversed(fields):
            reverse = False
            if field.startswith("-"):
                reverse = True
                field = field[1:]
            if field == "datetime":
                items.sort(key=lambda i: i.datetime, reverse=reverse)
            elif field == "amount":
                items.sort(key=lambda i: i.amount.real_amount, reverse=reverse)
            elif field == "description":
                items.sort(key=lambda i: i.description or "", reverse=reverse)
            elif field == "category":
                items.sort(key=lambda i: i.category or "", reverse=reverse)
            else:
                raise ValueError(f"Unknown field: {field}")
        return CashFlowQuery(items)

    def limit(self, count: int) -> "CashFlowQuery":
        return CashFlowQuery(self._items[:count])

    def offset(self, count: int) -> "CashFlowQuery":
        return CashFlowQuery(self._items[count:])

    def first(self) -> Optional[FlowElement]:
        return self._items[0] if self._items else None

    def last(self) -> Optional[FlowElement]:
        return self._items[-1] if self._items else None

    def count(self) -> int:
        return len(self._items)

    def sum_amounts(self) -> Money:
        if not self._items:
            return Money.zero()
        total = Money.zero()
        for item in self._items:
            total = total + item.amount
        return total

    def get_all(self) -> List[FlowElement]:
        return list(self._items)

    def all(self) -> List[FlowElement]:  # noqa: A003
        return self.get_all()

    def to_cash_flow(self) -> "CashFlow":
        """Convert query result back to a CashFlow.

        If the query holds :class:`CashFlowEntry` objects they are
        wrapped in fresh :class:`CashFlowItem` containers.
        """
        from .flow import CashFlow

        wrapped = [item if isinstance(item, CashFlowItem) else CashFlowItem(entry=item) for item in self._items]
        return CashFlow(wrapped)

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[FlowElement]:
        return iter(self._items)

    def __getitem__(self, index: int) -> FlowElement:
        return self._items[index]
