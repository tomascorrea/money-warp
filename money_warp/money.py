"""Money class for high-precision financial calculations."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Union


class Money:
    """
    Represents a monetary amount with high internal precision.

    Maintains full precision internally for calculations but provides
    'real money' representation rounded to 2 decimal places for display
    and comparisons.
    """

    def __init__(self, amount: Union[Decimal, str, int, float]) -> None:
        """
        Create a Money object with high internal precision.

        Args:
            amount: The monetary amount (will be converted to Decimal)
        """
        if isinstance(amount, float):
            # Convert float to string first to avoid precision issues
            self._amount = Decimal(str(amount))
        else:
            self._amount = Decimal(amount)

    @classmethod
    def zero(cls) -> "Money":
        """Create zero money."""
        return cls(0)

    @classmethod
    def from_cents(cls, cents: int) -> "Money":
        """Create from cents to avoid decimal issues."""
        return cls(Decimal(cents) / 100)

    def __add__(self, other: "Money") -> "Money":
        """Add two Money objects."""
        return Money(self._amount + other._amount)

    def __sub__(self, other: "Money") -> "Money":
        """Subtract two Money objects."""
        return Money(self._amount - other._amount)

    def __mul__(self, factor: Union[Decimal, int, float]) -> "Money":
        """Multiply by a number - keeps high precision."""
        return Money(self._amount * Decimal(str(factor)))

    def __truediv__(self, divisor: Union[Decimal, int, float]) -> "Money":
        """Divide by a number - keeps high precision."""
        return Money(self._amount / Decimal(str(divisor)))

    def __neg__(self) -> "Money":
        """Negative money."""
        return Money(-self._amount)

    def __abs__(self) -> "Money":
        """Absolute value."""
        return Money(abs(self._amount))

    def __eq__(self, other: object) -> bool:
        """Compare at 'real money' precision."""
        if not isinstance(other, Money):
            return NotImplemented
        return self.real_amount == other.real_amount

    def __lt__(self, other: "Money") -> bool:
        """Less than comparison at real money precision."""
        return self.real_amount < other.real_amount

    def __le__(self, other: "Money") -> bool:
        """Less than or equal comparison at real money precision."""
        return self.real_amount <= other.real_amount

    def __gt__(self, other: "Money") -> bool:
        """Greater than comparison at real money precision."""
        return self.real_amount > other.real_amount

    def __ge__(self, other: "Money") -> bool:
        """Greater than or equal comparison at real money precision."""
        return self.real_amount >= other.real_amount

    @property
    def raw_amount(self) -> Decimal:
        """Get the high-precision internal amount."""
        return self._amount

    @property
    def real_amount(self) -> Decimal:
        """Get the 'real money' amount rounded to 2 decimal places."""
        return self._amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @property
    def cents(self) -> int:
        """Get real amount in cents."""
        return int(self.real_amount * 100)

    def to_real_money(self) -> "Money":
        """Convert to real money (rounded to 2 decimal places)."""
        return Money(self.real_amount)

    def is_positive(self) -> bool:
        """Check if amount is positive."""
        return self.real_amount > 0

    def is_negative(self) -> bool:
        """Check if amount is negative."""
        return self.real_amount < 0

    def is_zero(self) -> bool:
        """Check if amount is zero."""
        return self.real_amount == 0

    def __str__(self) -> str:
        """Display as real money (2 decimal places)."""
        return f"{self.real_amount:,.2f}"

    def __repr__(self) -> str:
        """Developer representation showing internal precision."""
        return f"Money({self._amount})"

    def debug_precision(self) -> str:
        """Show both internal and real amounts for debugging."""
        return f"Internal: {self._amount}, Real: {self.real_amount}"
