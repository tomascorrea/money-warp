"""InterestRate class for non-negative contractual rate handling.

InterestRate is a refinement of Rate that enforces non-negativity — a
correct domain constraint for contractual interest rates (no lender pays
the borrower for the privilege of lending). For signed computed metrics
like IRR and MIRR, use Rate instead.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, Union

from money_warp.money import Money
from money_warp.rate import (
    _ABBREV_MAP,
    _ABBREV_TOKENS,
    _VALID_STR_STYLES,
    CompoundingFrequency,
    Rate,
    YearSize,
)

__all__ = [
    "InterestRate",
    "CompoundingFrequency",
    "YearSize",
    "_ABBREV_MAP",
    "_ABBREV_TOKENS",
    "_VALID_STR_STYLES",
]


class InterestRate(Rate):
    """
    Represents a non-negative contractual interest rate.

    Inherits all conversion and comparison behaviour from Rate, but
    rejects negative values at construction time. Use this type for
    loan terms, discount rates, and other contractual parameters.

    For computed metrics that may be negative (IRR, MIRR), use Rate.
    """

    def __init__(
        self,
        rate: Union[str, Decimal, float],
        period: Optional[CompoundingFrequency] = None,
        as_percentage: bool = False,
        precision: Optional[int] = None,
        rounding: str = ROUND_HALF_UP,
        str_style: str = "long",
        year_size: YearSize = YearSize.commercial,
    ) -> None:
        """
        Create a non-negative interest rate.

        Args:
            rate: Rate as string ("5.25% a", "0.004167 m") or numeric value.
                  Abbreviated formats ("5.25% a.a.", "0.5% a.m.") are also
                  accepted and automatically set str_style to "abbrev".
                  Negative values are rejected.
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

        Raises:
            ValueError: If the rate is negative.
        """
        super().__init__(
            rate,
            period=period,
            as_percentage=as_percentage,
            precision=precision,
            rounding=rounding,
            str_style=str_style,
            year_size=year_size,
        )

        if self._decimal_rate < 0:
            raise ValueError(
                f"Interest rate cannot be negative ({self._decimal_rate}). "
                "Use Rate for signed computed metrics like IRR."
            )

    def accrue(self, principal: Money, days: int) -> Money:
        """
        Compute compound interest accrued on a principal over a number of days.

        Formula: principal * ((1 + daily_rate) ** days - 1)

        Args:
            principal: The principal amount.
            days: Number of days to accrue interest over.

        Returns:
            The accrued interest (not including the principal).
        """
        daily_rate = self.to_daily().as_decimal()
        accrued = principal.raw_amount * ((1 + daily_rate) ** Decimal(str(days)) - 1)
        return Money(accrued)
