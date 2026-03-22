"""CashFlowEntry hierarchy — abstract base and concrete Expected / Happened types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import FrozenSet, Optional, Set, Union

from ..money import Money

CategoryInput = Union[str, Set[str], FrozenSet[str], None]


def _normalize_category(value: CategoryInput) -> FrozenSet[str]:
    """Convert any category input to a canonical frozenset."""
    if isinstance(value, frozenset):
        return value
    if isinstance(value, str):
        return frozenset({value})
    if isinstance(value, set):
        return frozenset(value)
    return frozenset()


class CashFlowType(str, Enum):
    """Whether a cash-flow entry is a projection or a recorded fact."""

    EXPECTED = "expected"
    HAPPENED = "happened"


@dataclass(frozen=True)
class CashFlowEntry(ABC):
    """Abstract base for a monetary movement at a point in time.

    Use :class:`ExpectedCashFlowEntry` for projected items (e.g. a loan
    schedule) and :class:`HappenedCashFlowEntry` for recorded facts
    (e.g. an actual payment).

    Time-awareness and versioning live in :class:`CashFlowItem`, which
    wraps one or more ``CashFlowEntry`` instances in a timeline.

    ``category`` is a frozenset of string tags. A single string is
    normalized to ``frozenset({string})`` by :class:`CashFlowItem`.

    ``interest_date`` is an optional secondary date used by loan payments
    to indicate the cutoff for interest accrual. When ``None``, the
    entry's ``datetime`` is used as the interest accrual cutoff.
    """

    amount: Money
    datetime: datetime
    description: Optional[str] = None
    category: FrozenSet[str] = frozenset()
    interest_date: Optional[datetime] = None

    @property
    @abstractmethod
    def kind(self) -> CashFlowType:
        ...

    def is_inflow(self) -> bool:
        return self.amount.is_positive()

    def is_outflow(self) -> bool:
        return self.amount.is_negative()

    def is_zero(self) -> bool:
        return self.amount.is_zero()

    def __str__(self) -> str:
        desc = f" - {self.description}" if self.description else ""
        return f"{self.amount} on {self.datetime}{desc}"


@dataclass(frozen=True)
class ExpectedCashFlowEntry(CashFlowEntry):
    """A projected cash flow that has not occurred yet."""

    @property
    def kind(self) -> CashFlowType:
        return CashFlowType.EXPECTED


@dataclass(frozen=True)
class HappenedCashFlowEntry(CashFlowEntry):
    """A recorded cash flow that has already occurred."""

    @property
    def kind(self) -> CashFlowType:
        return CashFlowType.HAPPENED
