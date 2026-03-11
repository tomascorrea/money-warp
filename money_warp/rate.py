"""Rate class for general-purpose rate handling and conversions.

Rate is the base type for all financial rates. It supports signed values
(positive and negative), making it suitable for computed metrics like IRR
and MIRR. For contractual interest rates that must be non-negative, use
InterestRate instead.
"""

import math
import re
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Dict, Optional, Union


class YearSize(Enum):
    """Number of days that constitute one year for rate conversions."""

    banker = 360
    commercial = 365


class CompoundingFrequency(Enum):
    """Frequency of compounding per year."""

    DAILY = 365
    MONTHLY = 12
    QUARTERLY = 4
    SEMI_ANNUALLY = 2
    ANNUALLY = 1
    CONTINUOUS = float("inf")


_VALID_STR_STYLES = ("long", "abbrev")

_ABBREV_MAP = {
    CompoundingFrequency.ANNUALLY: "a.a.",
    CompoundingFrequency.MONTHLY: "a.m.",
    CompoundingFrequency.DAILY: "a.d.",
    CompoundingFrequency.QUARTERLY: "a.t.",
    CompoundingFrequency.SEMI_ANNUALLY: "a.s.",
}

_ABBREV_TOKENS = {v: k for k, v in _ABBREV_MAP.items()}


class Rate:
    """
    General-purpose financial rate with explicit decimal/percentage handling.

    Supports signed values (positive and negative), period conversions, and
    string parsing. Use this type for computed metrics like IRR and MIRR.
    For contractual interest rates that must be non-negative, use InterestRate.
    """

    _decimal_rate: Decimal
    _percentage_rate: Decimal
    period: CompoundingFrequency
    _precision: Optional[int]
    _rounding: str
    _year_size: YearSize

    def __init__(
        self,
        rate: Union[str, Decimal, float],
        period: Optional[CompoundingFrequency] = None,
        as_percentage: bool = False,
        precision: Optional[int] = None,
        rounding: str = ROUND_HALF_UP,
        str_style: str = "long",
        year_size: YearSize = YearSize.commercial,
        str_decimals: int = 3,
        abbrev_labels: Optional[Dict[CompoundingFrequency, str]] = None,
    ) -> None:
        """
        Create a rate.

        Args:
            rate: Rate as string ("5.25% a", "-2.5% a", "0.004167 m") or
                  numeric value. Abbreviated formats ("5.25% a.a.") are also
                  accepted and automatically set str_style to "abbrev".
            period: Compounding frequency (required if rate is numeric)
            as_percentage: If True and rate is numeric, treat as percentage
            precision: Number of decimal places for the effective annual rate
                       during conversions. None keeps full precision.
            rounding: Rounding mode from the decimal module (e.g. ROUND_HALF_UP,
                      ROUND_DOWN). Only used when precision is set.
            str_style: Controls period notation in __str__. "long" outputs the
                       full name (e.g. "annually"), "abbrev" outputs the
                       abbreviated form (e.g. "a.a.").
            year_size: Day-count convention for daily conversions.
                       YearSize.commercial (365) or YearSize.banker (360).
            str_decimals: Number of decimal places for the percentage in
                          __str__. Default 3 gives "5.250%".
            abbrev_labels: Partial or full override of the default abbreviation
                           map. Merged with _ABBREV_MAP so you only need to
                           pass the keys you want to change. Example:
                           ``{CompoundingFrequency.MONTHLY: "a.m"}`` removes
                           the trailing dot for monthly only.
        """
        if str_style not in _VALID_STR_STYLES:
            raise ValueError(f"Invalid str_style: '{str_style}'. Expected one of {_VALID_STR_STYLES}")

        self._precision = precision
        self._rounding = rounding
        self._str_style = str_style
        self._year_size = year_size
        self._str_decimals = str_decimals
        self._abbrev_labels = abbrev_labels
        self._abbrev_map: Dict[CompoundingFrequency, str] = {**_ABBREV_MAP, **(abbrev_labels or {})}

        if isinstance(rate, str):
            parsed_rate = self._parse_rate_string(rate)
            self._decimal_rate = parsed_rate["decimal_rate"]  # type: ignore[assignment]
            self._percentage_rate = parsed_rate["percentage_rate"]  # type: ignore[assignment]
            self.period = parsed_rate["period"]  # type: ignore[assignment]
        else:
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
        - value: number with optional leading minus and optional % suffix
        - frequency: a/annual, m/monthly, d/daily, q/quarterly, s/semi-annual,
                     or abbreviated: a.a., a.m., a.d., a.t., a.s.

        Examples:
        - "5.25% a" or "5.25% annual" = 5.25% annually
        - "-2.5% a" = -2.5% annually (negative, valid for computed metrics)
        - "0.004167 m" or "0.004167 monthly" = 0.004167 monthly (decimal)
        - "2.5% q" or "2.5% quarterly" = 2.5% quarterly
        - "5.25% a.a." = 5.25% annually (abbreviated, sets str_style="abbrev")
        """
        rate_string = rate_string.strip().lower()

        long_freqs = r"a|annual|m|monthly|d|daily|q|quarterly|s|semi-annual"
        abbrev_freqs = r"a\.a\.|a\.m\.|a\.d\.|a\.t\.|a\.s\."
        pattern = rf"^(-?[0-9]+\.?[0-9]*)(%?)\s+({abbrev_freqs}|{long_freqs})$"
        match = re.match(pattern, rate_string)

        if not match:
            raise ValueError(
                f"Invalid rate format: '{rate_string}'. "
                "Expected format: '<value> <frequency>' "
                "(e.g., '5.25% a', '0.004167 monthly', '2.5% a.a.')"
            )

        value_str, percent_sign, freq_str = match.groups()

        value = Decimal(value_str)
        is_percentage = bool(percent_sign)

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

        if freq_str in _ABBREV_TOKENS:
            frequency = _ABBREV_TOKENS[freq_str]
            self._str_style = "abbrev"
        else:
            frequency = frequency_map[freq_str]

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

    def as_decimal(self, precision: Optional[int] = None) -> Decimal:
        """Get as decimal (0.05 = 5%).

        Args:
            precision: Number of decimal places. None returns the raw value.

        Returns:
            The rate as a Decimal, optionally quantized.
        """
        if precision is None:
            return self._decimal_rate
        return self._decimal_rate.quantize(Decimal(10) ** -precision, rounding=self._rounding)

    def as_percentage(self, precision: Optional[int] = None) -> Decimal:
        """Get as percentage (5.0 = 5%).

        Args:
            precision: Number of decimal places. None returns the raw value.

        Returns:
            The rate as a percentage Decimal, optionally quantized.
        """
        if precision is None:
            return self._percentage_rate
        return self._percentage_rate.quantize(Decimal(10) ** -precision, rounding=self._rounding)

    def as_float(self, precision: Optional[int] = None) -> float:
        """Get as a float (0.05 = 5%).

        Args:
            precision: Number of decimal places to round to. None returns
                       the unrounded float conversion.

        Returns:
            The rate as a float, optionally rounded.
        """
        value = float(self._decimal_rate)
        if precision is None:
            return value
        return round(value, precision)

    @property
    def year_size(self) -> YearSize:
        """Day-count convention used for daily conversions."""
        return self._year_size

    @property
    def _periods_per_year(self) -> Union[int, float]:
        """Number of compounding periods per year, respecting year_size for daily."""
        if self.period == CompoundingFrequency.DAILY:
            return self._year_size.value
        return self.period.value

    def to_daily(self) -> "Rate":
        """Convert to daily rate."""
        if self.period == CompoundingFrequency.DAILY:
            return self

        effective_annual = self._to_effective_annual()
        days = Decimal(str(self._year_size.value))
        daily_rate = (1 + effective_annual) ** (Decimal("1") / days) - 1

        return self.__class__(
            daily_rate,
            CompoundingFrequency.DAILY,
            precision=self._precision,
            rounding=self._rounding,
            str_style=self._str_style,
            year_size=self._year_size,
            str_decimals=self._str_decimals,
            abbrev_labels=self._abbrev_labels,
        )

    def to_monthly(self) -> "Rate":
        """Convert to monthly rate."""
        if self.period == CompoundingFrequency.MONTHLY:
            return self

        effective_annual = self._to_effective_annual()
        monthly_rate = (1 + effective_annual) ** (Decimal("1") / Decimal("12")) - 1

        return self.__class__(
            monthly_rate,
            CompoundingFrequency.MONTHLY,
            precision=self._precision,
            rounding=self._rounding,
            str_style=self._str_style,
            year_size=self._year_size,
            str_decimals=self._str_decimals,
            abbrev_labels=self._abbrev_labels,
        )

    def to_annual(self) -> "Rate":
        """Convert to annual rate."""
        if self.period == CompoundingFrequency.ANNUALLY:
            return self

        return self.__class__(
            self._to_effective_annual(),
            CompoundingFrequency.ANNUALLY,
            precision=self._precision,
            rounding=self._rounding,
            str_style=self._str_style,
            year_size=self._year_size,
            str_decimals=self._str_decimals,
            abbrev_labels=self._abbrev_labels,
        )

    def to_periodic_rate(self, num_periods: int) -> Decimal:
        """
        Convert to periodic rate for given number of periods per year.

        Args:
            num_periods: Number of periods per year (e.g., 12 for monthly)

        Returns:
            Decimal: Periodic rate as decimal
        """
        if self._periods_per_year == num_periods:
            return self._decimal_rate

        effective_annual = self._to_effective_annual()
        return (1 + effective_annual) ** (Decimal("1") / Decimal(str(num_periods))) - 1

    def _quantize(self, value: Decimal) -> Decimal:
        """Apply precision rounding if configured, otherwise return unchanged."""
        if self._precision is None:
            return value
        return value.quantize(Decimal(10) ** -self._precision, rounding=self._rounding)

    def _to_effective_annual(self) -> Decimal:
        """Convert any rate to effective annual rate."""
        if self.period == CompoundingFrequency.ANNUALLY:
            return self._quantize(self._decimal_rate)

        n = self._periods_per_year
        if n == float("inf"):  # Continuous compounding
            return self._quantize(Decimal(str(math.e)) ** self._decimal_rate - 1)

        return self._quantize((1 + self._decimal_rate) ** Decimal(str(n)) - 1)

    def __str__(self) -> str:
        """Clear string representation."""
        label = self._abbrev_map[self.period] if self._str_style == "abbrev" else self.period.name.lower()
        return f"{self._percentage_rate:.{self._str_decimals}f}% {label}"

    def __repr__(self) -> str:
        """Developer representation."""
        base = f"{self.__class__.__name__}({self._decimal_rate}, {self.period}"
        if self._precision is not None:
            base += f", precision={self._precision}, rounding={self._rounding!r}"
        if self._year_size != YearSize.commercial:
            base += f", year_size={self._year_size!r}"
        return base + ")"

    def __eq__(self, other: object) -> bool:
        """Compare rates by converting to effective annual."""
        if not isinstance(other, Rate):
            return NotImplemented
        if self._precision != other._precision or self._rounding != other._rounding:
            return False
        return abs(self._to_effective_annual() - other._to_effective_annual()) < Decimal("0.0000001")

    def __lt__(self, other: "Rate") -> bool:
        """Less than comparison using effective annual rates."""
        return self._to_effective_annual() < other._to_effective_annual()

    def __le__(self, other: "Rate") -> bool:
        """Less than or equal comparison using effective annual rates."""
        return self._to_effective_annual() <= other._to_effective_annual()

    def __gt__(self, other: "Rate") -> bool:
        """Greater than comparison using effective annual rates."""
        return self._to_effective_annual() > other._to_effective_annual()

    def __ge__(self, other: "Rate") -> bool:
        """Greater than or equal comparison using effective annual rates."""
        return self._to_effective_annual() >= other._to_effective_annual()
