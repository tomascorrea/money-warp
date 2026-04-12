"""Timezone configuration for MoneyWarp.

UTC is the default timezone. Use ``set_tz`` to change it globally.
All datetimes produced by the library are timezone-aware.
"""

import functools
import inspect
from datetime import date, datetime, timezone, tzinfo
from typing import Callable, TypeVar, Union
from zoneinfo import ZoneInfo

_default_tz: tzinfo = timezone.utc

F = TypeVar("F", bound=Callable)


def get_tz() -> tzinfo:
    """Return the current default timezone."""
    return _default_tz


def set_tz(tz: Union[str, tzinfo]) -> None:
    """Set the default timezone.

    Args:
        tz: A timezone name (e.g. ``"America/Sao_Paulo"``) or a ``tzinfo`` instance.
    """
    global _default_tz
    _default_tz = ZoneInfo(tz) if isinstance(tz, str) else tz


def now() -> datetime:
    """Return the current time in the configured timezone (always aware)."""
    return datetime.now(_default_tz)


def ensure_aware(dt: datetime) -> datetime:
    """Guarantee that *dt* is timezone-aware and normalised to UTC.

    If *dt* is naive, it is interpreted as being in the configured
    business timezone (``_default_tz``) and then converted to UTC.
    If *dt* is already aware, it is converted to UTC directly.

    All datetimes stored inside the library are UTC.  Use
    :func:`to_date` when extracting a calendar date — it converts
    back to the business timezone first.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_default_tz).astimezone(timezone.utc)
    return dt.astimezone(timezone.utc)


def to_date(dt: Union[date, datetime], tz: tzinfo) -> date:
    """Extract the calendar date in the given timezone.

    For ``datetime`` inputs the value is first converted to *tz* so
    the extracted date reflects the correct business day.  Plain
    ``date`` inputs pass through unchanged.
    """
    if isinstance(dt, datetime):
        return dt.astimezone(tz).date()
    return dt


def to_datetime(d: date, tz: tzinfo) -> datetime:
    """Convert a calendar date to a UTC datetime (midnight in *tz*)."""
    naive = datetime.combine(d, datetime.min.time())
    return naive.replace(tzinfo=tz).astimezone(timezone.utc)


def tz_aware(func: F) -> F:
    """Decorator that makes every ``datetime`` argument timezone-aware.

    At call time each positional and keyword argument is inspected:

    * ``datetime`` values are passed through :func:`ensure_aware`.
    * ``list`` values whose first element is a ``datetime`` are coerced
      element-wise.
    * Everything else is left untouched.
    """
    sig = inspect.signature(func)

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        bound = sig.bind(*args, **kwargs)
        for name, value in bound.arguments.items():
            if isinstance(value, datetime):
                bound.arguments[name] = ensure_aware(value)
            elif isinstance(value, list) and value and isinstance(value[0], datetime):
                bound.arguments[name] = [ensure_aware(v) for v in value]
        return func(*bound.args, **bound.kwargs)

    return wrapper  # type: ignore[return-value]


class _DefaultTimeSource:
    """Time source that delegates to :func:`now`."""

    def now(self) -> datetime:
        return now()


default_time_source = _DefaultTimeSource()
