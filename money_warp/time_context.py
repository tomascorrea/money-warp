"""Shared time context for Warp-compatible time awareness.

A TimeContext is referenced by a Loan and all its CashFlowItems.
``deepcopy`` preserves the shared reference within the clone, so
Warp can override one context and every item sees the warped time.
"""

from datetime import datetime

from .tz import default_time_source


class TimeContext:
    """Shared, overridable time source.

    Default behaviour delegates to :data:`default_time_source` (real
    wall-clock time).  Call :meth:`override` to swap the source — for
    example with a ``WarpedTime`` instance inside a Warp context.
    """

    def __init__(self, source=None):
        self._source = source or default_time_source

    def now(self) -> datetime:
        return self._source.now()

    def override(self, source) -> None:
        self._source = source
