"""Time Machine (Warp) context manager for financial projections."""

import copy
from datetime import date, datetime
from typing import Any, Optional, Type, Union

from .tz import ensure_aware, to_date


class WarpedTime:
    """Warped time source that returns a fixed time for time travel scenarios."""

    def __init__(self, fixed_datetime: datetime):
        self.fixed_datetime = fixed_datetime

    def now(self) -> datetime:
        """Return the fixed datetime instead of current time."""
        return self.fixed_datetime

    def date(self) -> date:
        """Return the fixed date instead of current date."""
        return to_date(self.fixed_datetime)


class WarpError(Exception):
    """Base exception for Warp-related errors."""

    pass


class NestedWarpError(WarpError):
    """Raised when attempting to create nested Warp contexts."""

    pass


class InvalidDateError(WarpError):
    """Raised when an invalid date is provided to Warp."""

    pass


class Warp:
    """
    Time Machine context manager for financial projections and analysis.

    Allows you to temporarily "warp" any financial instrument (Loan,
    CreditCard, or any object with a ``_time_ctx`` attribute) to a
    specific date to analyze its state at that point in time.

    Usage:
        instrument = Loan(...)   # or CreditCard(...)
        with Warp(instrument, '2030-01-15') as warped:
            balance = warped.current_balance

    Warping different objects concurrently is allowed, but nested
    warps on the **same** object are not.

    The target object must expose ``_time_ctx`` (a :class:`TimeContext`).
    If it also has an ``_on_warp(target_date)`` method, that method is
    called after overriding the time context on the clone.
    """

    _active_targets: set = set()

    def __init__(self, target: Any, target_date: Union[str, date, datetime]) -> None:
        """
        Initialize the Warp context manager.

        Args:
            target: The financial instrument to warp (Loan, CreditCard, etc.).
                Must have a ``_time_ctx`` attribute.
            target_date: The date to warp to (accepts strings, date, or datetime objects)

        Raises:
            TypeError: If *target* has no ``_time_ctx`` attribute
            NestedWarpError: If the same object is already being warped
            InvalidDateError: If the target_date cannot be parsed
        """
        if not hasattr(target, "_time_ctx"):
            raise TypeError("Warp target must have a _time_ctx attribute (e.g. Loan or CreditCard)")

        if id(target) in Warp._active_targets:
            raise NestedWarpError(
                "Nested Warp contexts on the same object are not allowed. "
                "Playing with time is dangerous enough with one level."
            )

        self._original = target
        self.target_date = self._parse_date(target_date)
        self._warped: Optional[Any] = None

    @property
    def original_loan(self) -> Any:
        """Backward-compatible alias for the original target."""
        return self._original

    @property
    def warped_loan(self) -> Optional[Any]:
        """Backward-compatible alias for the warped clone."""
        return self._warped

    @warped_loan.setter
    def warped_loan(self, value: Any) -> None:
        self._warped = value

    def _parse_date(self, target_date: Union[str, date, datetime]) -> datetime:
        """
        Parse various date formats into a datetime object.

        Args:
            target_date: Date in string, date, or datetime format

        Returns:
            datetime object

        Raises:
            InvalidDateError: If the date cannot be parsed
        """
        try:
            if isinstance(target_date, datetime):
                return ensure_aware(target_date)
            elif isinstance(target_date, date):
                return ensure_aware(datetime.combine(target_date, datetime.min.time()))
            elif isinstance(target_date, str):
                return ensure_aware(datetime.fromisoformat(target_date.replace("Z", "+00:00")))
            else:
                raise InvalidDateError(f"Unsupported date type: {type(target_date)}")
        except (ValueError, TypeError) as e:
            raise InvalidDateError(f"Could not parse date '{target_date}': {e}") from e

    def __enter__(self) -> Any:
        """
        Enter the Warp context and return a time-warped clone.

        Returns:
            A deep-cloned object with its TimeContext overridden to the
            target date.
        """
        Warp._active_targets.add(id(self._original))

        self._warped = copy.deepcopy(self._original)

        self._apply_time_warp()

        return self._warped

    def _apply_time_warp(self) -> None:
        """Apply time warp to the cloned object.

        Overrides the shared TimeContext so every CashFlowItem in the
        clone sees the warped time.  Then calls ``_on_warp`` if the
        target provides it (e.g. Loan materialises fines, CreditCard
        closes billing cycles).
        """
        if self._warped is None:
            return

        self._warped._time_ctx.override(WarpedTime(self.target_date))

        if hasattr(self._warped, "_on_warp"):
            self._warped._on_warp(self.target_date)

    def __exit__(
        self, exc_type: Optional[Type[BaseException]], exc_val: Optional[BaseException], exc_tb: Optional[object]
    ) -> None:
        """
        Exit the Warp context and clean up.

        Args:
            exc_type: Exception type (if any)
            exc_val: Exception value (if any)
            exc_tb: Exception traceback (if any)
        """
        Warp._active_targets.discard(id(self._original))
        self._warped = None

    def __str__(self) -> str:
        """String representation of the Warp."""
        return f"Warp(target_date={self.target_date.isoformat()})"

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return f"Warp(target={self._original!r}, target_date='{self.target_date.isoformat()}')"
