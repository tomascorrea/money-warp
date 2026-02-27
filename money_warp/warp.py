"""Time Machine (Warp) context manager for financial projections."""

import copy
from datetime import date, datetime
from typing import Optional, Type, Union

from .loan import Loan
from .tz import ensure_aware


class WarpedTime:
    """Warped time source that returns a fixed time for time travel scenarios."""

    def __init__(self, fixed_datetime: datetime):
        self.fixed_datetime = fixed_datetime

    def now(self) -> datetime:
        """Return the fixed datetime instead of current time."""
        return self.fixed_datetime

    def date(self) -> date:
        """Return the fixed date instead of current date."""
        return self.fixed_datetime.date()


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

    Allows you to temporarily "warp" a loan to a specific date to analyze
    its state at that point in time. This is useful for:
    - Calculating loan balances at future dates
    - Analyzing payment history up to a past date
    - Creating "what if" scenarios at different points in time

    Usage:
        loan = Loan(...)
        with Warp(loan, '2030-01-15') as warped_loan:
            balance = warped_loan.current_balance

    Note: Nested Warp contexts are not allowed for safety.
    """

    _active_warp: Optional["Warp"] = None

    def __init__(self, loan: Loan, target_date: Union[str, date, datetime]) -> None:
        """
        Initialize the Warp context manager.

        Args:
            loan: The loan object to warp
            target_date: The date to warp to (accepts strings, date, or datetime objects)

        Raises:
            NestedWarpError: If another Warp context is already active
            InvalidDateError: If the target_date cannot be parsed
        """
        # Check for nested warps
        if Warp._active_warp is not None:
            raise NestedWarpError(
                "Nested Warp contexts are not allowed. Playing with time is dangerous enough with one level."
            )

        self.original_loan = loan
        self.target_date = self._parse_date(target_date)
        self.warped_loan: Optional[Loan] = None

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

    def __enter__(self) -> Loan:
        """
        Enter the Warp context and return a time-warped loan.

        Returns:
            A cloned loan with its state modified to reflect the target date
        """
        # Mark this warp as active
        Warp._active_warp = self

        # Clone the loan to avoid modifying the original
        self.warped_loan = copy.deepcopy(self.original_loan)

        # Modify the warped loan's state based on target_date
        self._apply_time_warp()

        return self.warped_loan

    def _apply_time_warp(self) -> None:
        """
        Apply time warp logic to the cloned loan.

        Override the datetime_func to return the warped time and automatically
        calculate any late payment fines up to the target date.
        """
        if self.warped_loan is None:
            return

        # Override the datetime_func to return warped time
        self.warped_loan.datetime_func = WarpedTime(self.target_date)  # type: ignore[assignment]

        # Automatically calculate late payment fines up to the target date
        self.warped_loan.calculate_late_fines(self.target_date)

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
        # Clear the active warp
        Warp._active_warp = None
        self.warped_loan = None

        # Don't suppress any exceptions (no return needed for None)

    def __str__(self) -> str:
        """String representation of the Warp."""
        return f"Warp(target_date={self.target_date.isoformat()})"

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return f"Warp(loan={self.original_loan!r}, target_date='{self.target_date.isoformat()}')"
