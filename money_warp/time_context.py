"""Shared time context for Warp-compatible time awareness.

A TimeContext is referenced by a Loan and all its CashFlowItems.
``deepcopy`` preserves the shared reference within the clone, so
Warp can override one context and every item sees the warped time.

Each TimeContext also carries a business timezone (``tz``), used
when converting UTC datetimes to calendar dates.  This is the
per-loan timezone — different loans can have different values.
"""

from datetime import date, datetime, tzinfo
from typing import Optional, Union

from .tz import default_time_source, get_tz, to_date, to_datetime


class TimeContext:
    """Shared, overridable time source with a per-loan timezone.

    Default behaviour delegates to :data:`default_time_source` (real
    wall-clock time).  Call :meth:`override` to swap the source — for
    example with a ``WarpedTime`` instance inside a Warp context.

    The ``tz`` attribute controls which timezone is used when
    extracting calendar dates from UTC datetimes (via :meth:`to_date`
    and :meth:`to_datetime`).  It defaults to :func:`get_tz`.
    """

    def __init__(self, source=None, tz: Optional[tzinfo] = None) -> None:
        self._source = source or default_time_source
        self.tz: tzinfo = tz or get_tz()

    def now(self) -> datetime:
        return self._source.now()

    def to_date(self, dt: Union[date, datetime]) -> date:
        """Extract calendar date in this context's business timezone."""
        return to_date(dt, self.tz)

    def to_datetime(self, d: date) -> datetime:
        """Convert calendar date to UTC datetime (midnight in business tz)."""
        return to_datetime(d, self.tz)

    def override(self, source) -> None:
        self._source = source
