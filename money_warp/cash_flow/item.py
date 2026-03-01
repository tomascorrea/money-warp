"""CashFlowItem — time-aware container for CashFlowEntry versions."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional, Tuple, Union

from ..money import Money
from ..time_context import TimeContext
from ..tz import default_time_source, tz_aware
from .entry import CashFlowEntry

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

_SENTINEL = object()


class CashFlowItem:
    """Temporal container that wraps a timeline of :class:`CashFlowEntry` snapshots.

    At any point in time exactly one entry (or ``None``, meaning deleted)
    is *active*.  :meth:`resolve` returns that entry for
    ``self.now()``.

    The constructor accepts the same positional/keyword arguments as the
    old ``CashFlowItem`` so that existing call-sites continue to work
    without changes during the migration.
    """

    @tz_aware
    def __init__(
        self,
        amount: Union[Money, Decimal, str, int, float, CashFlowEntry] = _SENTINEL,
        datetime: Optional["datetime"] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        *,
        entry: Optional[CashFlowEntry] = None,
        time_context: Optional[TimeContext] = None,
    ) -> None:
        if entry is not None:
            initial = entry
        elif isinstance(amount, CashFlowEntry):
            initial = amount
        elif amount is not _SENTINEL and datetime is not None:
            money = amount if isinstance(amount, Money) else Money(amount)
            initial = CashFlowEntry(
                amount=money,
                datetime=datetime,
                description=description,
                category=category,
            )
        else:
            raise TypeError(
                "CashFlowItem requires either an 'entry' keyword argument or positional (amount, datetime) arguments."
            )

        self._timeline: List[Tuple["datetime", Optional[CashFlowEntry]]] = [(EPOCH, initial)]
        self._time_ctx = time_context

    # ------------------------------------------------------------------
    # Temporal API
    # ------------------------------------------------------------------

    def resolve(self) -> Optional[CashFlowEntry]:
        """Return the active entry at ``self.now()``, or ``None`` if deleted."""
        current = self._now()
        active: Optional[CashFlowEntry] = None
        for effective_date, entry in self._timeline:
            if effective_date <= current:
                active = entry
            else:
                break
        return active

    def update(self, effective_date: "datetime", new_entry: CashFlowEntry) -> None:
        """From *effective_date* onward this item resolves to *new_entry*."""
        self._timeline.append((effective_date, new_entry))
        self._timeline.sort(key=lambda t: t[0])

    def delete(self, effective_date: "datetime") -> None:
        """From *effective_date* onward this item resolves to ``None``."""
        self._timeline.append((effective_date, None))
        self._timeline.sort(key=lambda t: t[0])

    # ------------------------------------------------------------------
    # Convenience properties (access current entry fields directly)
    # ------------------------------------------------------------------

    @property
    def amount(self) -> Money:
        entry = self._require_resolved()
        return entry.amount

    @property
    def datetime(self) -> "datetime":
        entry = self._require_resolved()
        return entry.datetime

    @property
    def description(self) -> Optional[str]:
        entry = self._require_resolved()
        return entry.description

    @property
    def category(self) -> Optional[str]:
        entry = self._require_resolved()
        return entry.category

    # ------------------------------------------------------------------
    # Delegated helpers
    # ------------------------------------------------------------------

    def is_inflow(self) -> bool:
        return self.amount.is_positive()

    def is_outflow(self) -> bool:
        return self.amount.is_negative()

    def is_zero(self) -> bool:
        return self.amount.is_zero()

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        entry = self.resolve()
        if entry is None:
            return "CashFlowItem(deleted)"
        return str(entry)

    def __repr__(self) -> str:
        entry = self.resolve()
        if entry is None:
            return "CashFlowItem(deleted)"
        return (
            f"CashFlowItem(amount={entry.amount!r}, datetime={entry.datetime!r}, "
            f"description={entry.description!r}, category={entry.category!r})"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CashFlowItem):
            return False
        return self.resolve() == other.resolve()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _now(self) -> "datetime":
        if self._time_ctx is not None:
            return self._time_ctx.now()
        return default_time_source.now()

    def _require_resolved(self) -> CashFlowEntry:
        entry = self.resolve()
        if entry is None:
            raise ValueError("CashFlowItem has been deleted at the current time.")
        return entry
