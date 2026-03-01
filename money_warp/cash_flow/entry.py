"""CashFlowEntry — pure data object for a single financial transaction."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ..money import Money


@dataclass(frozen=True)
class CashFlowEntry:
    """Immutable snapshot of a monetary movement at a point in time.

    This is the *data* part of the cash-flow model.  Time-awareness and
    versioning live in :class:`CashFlowItem`, which wraps one or more
    ``CashFlowEntry`` instances in a timeline.
    """

    amount: Money
    datetime: datetime
    description: Optional[str] = None
    category: Optional[str] = None

    def is_inflow(self) -> bool:
        return self.amount.is_positive()

    def is_outflow(self) -> bool:
        return self.amount.is_negative()

    def is_zero(self) -> bool:
        return self.amount.is_zero()

    def __str__(self) -> str:
        desc = f" - {self.description}" if self.description else ""
        return f"{self.amount} on {self.datetime}{desc}"
