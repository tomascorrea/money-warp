"""InterestRate class for safe rate handling and conversions."""

import math
import re
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Union


class CompoundingFrequency(Enum):
    """Frequency of compounding per year."""

    DAILY = 365
    MONTHLY = 12
    QUARTERLY = 4
    SEMI_ANNUALLY = 2
    ANNUALLY = 1
    CONTINUOUS = float("inf")


class InterestRate:
    """
    Represents an interest rate with explicit decimal/percentage handling.

    Eliminates confusion between 0.05 and 5% by requiring explicit creation
    methods and providing clear conversions between different compounding
    frequencies.
    """

    _decimal_rate: Decimal
    _percentage_rate: Decimal
    period: CompoundingFrequency

    def __init__(
        self,
        rate: Union[str, Decimal, float],
        period: Optional[CompoundingFrequency] = None,
        as_percentage: bool = False,
    ) -> None:
        """
        Create an interest rate.

        Args:
            rate: Rate as string ("5.25% a", "0.004167 m") or numeric value
            period: Compounding frequency (required if rate is numeric)
            as_percentage: If True and rate is numeric, treat as percentage
        """
        if isinstance(rate, str):
            # Parse string format
            parsed_rate = self._parse_rate_string(rate)
            self._decimal_rate = parsed_rate["decimal_rate"]  # type: ignore[assignment]
            self._percentage_rate = parsed_rate["percentage_rate"]  # type: ignore[assignment]
            self.period = parsed_rate["period"]  # type: ignore[assignment]
        else:
            # Numeric rate - period is required
            if period is None:
                raise ValueError("period is required when rate is numeric")

            rate_decimal = Decimal(str(rate))
            if as_percentage:
                self._decimal_rate = rate_decimal / 100
                self._percentage_rate = rate_decimal
            else:
                self._decimal_rate = rate_decimal
                self._percentage_rate = rate_decimal * 100

            self.period = period

    def _parse_rate_string(self, rate_string: str) -> Dict[str, Union[Decimal, CompoundingFrequency]]:
        """
        Parse rate string format.

        Format: "<value> <frequency>" where:
        - value: number with optional % (e.g., "5.25%", "0.0525")
        - frequency: a/annual, m/monthly, d/daily, q/quarterly, s/semi-annual

        Examples:
        - "5.25% a" or "5.25% annual" = 5.25% annually
        - "0.004167 m" or "0.004167 monthly" = 0.004167 monthly (decimal)
        - "2.5% q" or "2.5% quarterly" = 2.5% quarterly
        """
        # Clean up the string
        rate_string = rate_string.strip().lower()

        # Parse the pattern: number (with optional %) + space + frequency
        pattern = r"^([0-9]+\.?[0-9]*)(%?)\s+(a|annual|m|monthly|d|daily|q|quarterly|s|semi-annual)$"
        match = re.match(pattern, rate_string)

        if not match:
            raise ValueError(
                f"Invalid rate format: '{rate_string}'. "
                "Expected format: '<value> <frequency>' "
                "(e.g., '5.25% a', '0.004167 monthly', '2.5% quarterly')"
            )

        value_str, percent_sign, freq_str = match.groups()

        # Parse the value
        value = Decimal(value_str)
        is_percentage = bool(percent_sign)

        # Parse the frequency
        frequency_map = {
            "a": CompoundingFrequency.ANNUALLY,
            "annual": CompoundingFrequency.ANNUALLY,
            "m": CompoundingFrequency.MONTHLY,
            "monthly": CompoundingFrequency.MONTHLY,
            "d": CompoundingFrequency.DAILY,
            "daily": CompoundingFrequency.DAILY,
            "q": CompoundingFrequency.QUARTERLY,
            "quarterly": CompoundingFrequency.QUARTERLY,
            "s": CompoundingFrequency.SEMI_ANNUALLY,
            "semi-annual": CompoundingFrequency.SEMI_ANNUALLY,
        }

        frequency = frequency_map[freq_str]

        # Calculate decimal and percentage rates
        if is_percentage:
            decimal_rate = value / 100
            percentage_rate = value
        else:
            decimal_rate = value
            percentage_rate = value * 100

        return {
            "decimal_rate": decimal_rate,
            "percentage_rate": percentage_rate,
            "period": frequency,
        }

    @property
    def as_decimal(self) -> Decimal:
        """Get as decimal (0.05 = 5%)."""
        return self._decimal_rate

    @property
    def as_percentage(self) -> Decimal:
        """Get as percentage (5.0 = 5%)."""
        return self._percentage_rate

    def to_daily(self) -> "InterestRate":
        """Convert to daily rate."""
        if self.period == CompoundingFrequency.DAILY:
            return self

        # Convert to effective annual, then to daily
        effective_annual = self._to_effective_annual()
        daily_rate = (1 + effective_annual) ** (Decimal("1") / Decimal("365")) - 1

        return InterestRate(daily_rate, CompoundingFrequency.DAILY, as_percentage=False)

    def to_monthly(self) -> "InterestRate":
        """Convert to monthly rate."""
        if self.period == CompoundingFrequency.MONTHLY:
            return self

        effective_annual = self._to_effective_annual()
        monthly_rate = (1 + effective_annual) ** (Decimal("1") / Decimal("12")) - 1

        return InterestRate(monthly_rate, CompoundingFrequency.MONTHLY, as_percentage=False)

    def to_annual(self) -> "InterestRate":
        """Convert to annual rate."""
        if self.period == CompoundingFrequency.ANNUALLY:
            return self

        return InterestRate(
            self._to_effective_annual(),
            CompoundingFrequency.ANNUALLY,
            as_percentage=False,
        )

    def to_periodic_rate(self, num_periods: int) -> Decimal:
        """
        Convert to periodic rate for given number of periods per year.

        Args:
            num_periods: Number of periods per year (e.g., 12 for monthly)

        Returns:
            Decimal: Periodic rate as decimal
        """
        if self.period.value == num_periods:
            return self._decimal_rate

        # Convert to effective annual, then to desired frequency
        effective_annual = self._to_effective_annual()
        return (1 + effective_annual) ** (Decimal("1") / Decimal(str(num_periods))) - 1

    def _to_effective_annual(self) -> Decimal:
        """Convert any rate to effective annual rate."""
        if self.period == CompoundingFrequency.ANNUALLY:
            return self._decimal_rate

        # Formula: (1 + r)^n - 1, where r is the periodic rate and n is periods per year
        n = self.period.value
        if n == float("inf"):  # Continuous compounding
            # e^r - 1, where r is the continuous rate
            return Decimal(str(math.e)) ** self._decimal_rate - 1

        # For periodic rates: compound the periodic rate for the full year
        return (1 + self._decimal_rate) ** Decimal(str(n)) - 1

    def __str__(self) -> str:
        """Clear string representation."""
        return f"{self._percentage_rate:.3f}% {self.period.name.lower()}"

    def __repr__(self) -> str:
        """Developer representation."""
        return f"InterestRate({self._decimal_rate}, {self.period})"

    def __eq__(self, other: object) -> bool:
        """Compare rates by converting to effective annual."""
        if not isinstance(other, InterestRate):
            return NotImplemented
        return abs(self._to_effective_annual() - other._to_effective_annual()) < Decimal("0.0000001")

    def __lt__(self, other: "InterestRate") -> bool:
        """Less than comparison using effective annual rates."""
        return self._to_effective_annual() < other._to_effective_annual()

    def __le__(self, other: "InterestRate") -> bool:
        """Less than or equal comparison using effective annual rates."""
        return self._to_effective_annual() <= other._to_effective_annual()

    def __gt__(self, other: "InterestRate") -> bool:
        """Greater than comparison using effective annual rates."""
        return self._to_effective_annual() > other._to_effective_annual()

    def __ge__(self, other: "InterestRate") -> bool:
        """Greater than or equal comparison using effective annual rates."""
        return self._to_effective_annual() >= other._to_effective_annual()
