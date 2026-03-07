"""Base billing cycle abstraction for periodic statement generation."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List


class BaseBillingCycle(ABC):
    """Abstract factory for billing cycle date generation.

    Subclasses define how statement closing dates and payment due dates
    are derived.  The credit card uses whichever implementation is
    injected at construction time — same pattern as ``BaseScheduler``
    on the Loan.
    """

    @abstractmethod
    def closing_dates_between(self, start: datetime, end: datetime) -> List[datetime]:
        """Return closing dates for all *complete* cycles in [start, end].

        The first closing date is the earliest one strictly after *start*.
        The last closing date is the latest one at or before *end*.
        """

    @abstractmethod
    def due_date_for(self, closing_date: datetime) -> datetime:
        """Payment due date for a given statement closing date."""
