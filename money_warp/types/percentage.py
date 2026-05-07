"""Percentage class for non-temporal, non-compounding percentages.

A :class:`Percentage` represents a non-negative percentage applied directly
over a value, with no temporal dimension and no compounding. Typical examples
are MDR (partner rate), late-payment fines/multas, and similar value-based
fees.

:class:`Percentage` is intentionally **not** related to
:class:`~money_warp.types.rate.Rate` or :class:`~money_warp.types.interest_rate.InterestRate`:
those types model temporal rates with period conversions
(``to_daily``, ``to_monthly``, ...). A percentage has no period to convert
*to*, so the absence of those methods is part of the contract — it forces
callers (and the type checker) to be explicit about which kind of value they
hold.

Construction is intentionally restricted to strings of the form ``"<n>%"``
to eliminate the classic ``5`` vs ``0.05`` ambiguity. The literal ``%`` is
part of the contract and the only unambiguous way to express a percentage
to the constructor.
"""

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

__all__ = ["Percentage"]

# Accepts "<n>%" with optional decimal part. Negative values are rejected
# at the parser level (no leading minus accepted) and again at construction
# as a belt-and-suspenders guard.
_STRING_PATTERN = re.compile(r"^([0-9]+(?:\.[0-9]+)?)%$")

# Common temporal suffixes used by Rate/InterestRate. We detect them in the
# parser to surface a pointed error message instead of a generic "invalid
# format" — those rates belong to a different type. Whitespace before the
# suffix is optional so '5%a.a.' (no space) still triggers the helpful error.
_TEMPORAL_SUFFIX_PATTERN = re.compile(
    r"\s*(a|annual|m|monthly|d|daily|q|quarterly|s|semi-annual|a\.[amdts]\.)\s*$",
    re.IGNORECASE,
)


class Percentage:
    """A non-negative percentage applied flat over a value.

    Construction accepts **only** strings in the format ``"<number>%"``.
    Numeric inputs and strings without ``%`` are rejected to eliminate the
    classic ``5`` vs ``0.05`` ambiguity.

    Args:
        rate: Percentage as a string in the format ``"<number>%"``
            (e.g. ``"5%"``, ``"5.5%"``, ``"0.5%"``, ``"5.000%"``).
        precision: Default number of decimal places used by
            :meth:`as_decimal` / :meth:`as_percentage` when no explicit
            precision is passed at call time. ``None`` keeps full precision.
        rounding: Rounding mode from the :mod:`decimal` module
            (e.g. ``ROUND_HALF_UP``, ``ROUND_DOWN``). Used only when
            *precision* is set.
        str_decimals: Number of decimal places for the percentage in
            :meth:`__str__`. Default ``2`` gives ``"5.00%"``.

    Raises:
        TypeError: If *rate* is not a string.
        ValueError: If the string is not a valid percentage format,
            contains a temporal suffix (use :class:`Rate`/:class:`InterestRate`
            for those), or represents a negative value.

    Examples:
        >>> p = Percentage("5%")
        >>> p.as_decimal()
        Decimal('0.05')
        >>> p.as_percentage()
        Decimal('5')
        >>> str(p)
        '5.00%'
    """

    _decimal_rate: Decimal
    _percentage_rate: Decimal
    _precision: Optional[int]
    _rounding: str
    _str_decimals: int

    def __init__(
        self,
        rate: str,
        precision: Optional[int] = None,
        rounding: str = ROUND_HALF_UP,
        str_decimals: int = 2,
    ) -> None:
        if not isinstance(rate, str):
            raise TypeError(
                f"Percentage requires a string in the format '<number>%' (got {type(rate).__name__}). "
                "Numeric inputs are rejected to avoid the '5' vs '0.05' ambiguity. "
                "Pass '5%' instead of 5 or 0.05."
            )

        self._precision = precision
        self._rounding = rounding
        self._str_decimals = str_decimals

        decimal_rate, percentage_rate = self._parse_rate_string(rate)
        self._decimal_rate = decimal_rate
        self._percentage_rate = percentage_rate

        # Belt-and-suspenders: the regex already rejects a leading minus, but
        # we double-check here to keep the invariant explicit.
        if self._decimal_rate < 0:
            raise ValueError(
                f"Percentage cannot be negative ({self._decimal_rate}). "
                "Percentage models contractual fees applied over a value "
                "(MDR, multas, ...) — these are non-negative by definition."
            )

    # -- parsing ----------------------------------------------------------

    @staticmethod
    def _parse_rate_string(rate_string: str) -> tuple[Decimal, Decimal]:
        """Parse a percentage string into ``(decimal_rate, percentage_rate)``.

        Rejects:
        - Strings without a literal ``%`` suffix.
        - Strings with temporal suffixes (``annual``, ``monthly``, ``a.a.``,
          ...) — those belong to :class:`~money_warp.types.rate.Rate` /
          :class:`~money_warp.types.interest_rate.InterestRate`.
        - Negative values (no leading ``-`` allowed).
        """
        cleaned = rate_string.strip()

        if _TEMPORAL_SUFFIX_PATTERN.search(cleaned):
            raise ValueError(
                f"Percentage cannot parse temporal rate '{rate_string}'. "
                "Percentage is for non-temporal value-based percentages "
                "(MDR, multas). Use Rate or InterestRate for temporal rates."
            )

        match = _STRING_PATTERN.match(cleaned)
        if not match:
            raise ValueError(
                f"Invalid Percentage format: '{rate_string}'. "
                "Expected a string in the format '<number>%' (e.g. '5%', '5.5%', '0.5%'). "
                "Bare numbers and decimals without '%' are rejected on purpose to avoid "
                "the '5' vs '0.05' ambiguity."
            )

        value = Decimal(match.group(1))
        return value / 100, value

    # -- accessors --------------------------------------------------------

    def as_decimal(self, precision: Optional[int] = None) -> Decimal:
        """Return the percentage as a decimal (``0.05`` for ``5%``).

        Args:
            precision: Number of decimal places. ``None`` falls back to the
                ``precision`` passed at construction; if both are ``None``,
                the raw value is returned without quantization.
        """
        return self._quantize(self._decimal_rate, precision)

    def as_percentage(self, precision: Optional[int] = None) -> Decimal:
        """Return the percentage as a percentage value (``5`` for ``5%``).

        Args:
            precision: Number of decimal places. ``None`` falls back to the
                ``precision`` passed at construction; if both are ``None``,
                the raw value is returned without quantization.
        """
        return self._quantize(self._percentage_rate, precision)

    def _quantize(self, value: Decimal, precision: Optional[int]) -> Decimal:
        effective = precision if precision is not None else self._precision
        if effective is None:
            return value
        return value.quantize(Decimal(10) ** -effective, rounding=self._rounding)

    # -- display ----------------------------------------------------------

    def __str__(self) -> str:
        """Canonical string representation: ``"5.00%"``.

        Round-trips through ``Percentage(str(p))``.
        """
        return f"{self._percentage_rate:.{self._str_decimals}f}%"

    def __repr__(self) -> str:
        base = f"Percentage({str(self)!r}"
        if self._precision is not None:
            base += f", precision={self._precision}, rounding={self._rounding!r}"
        if self._str_decimals != 2:
            base += f", str_decimals={self._str_decimals}"
        return base + ")"

    # -- comparisons ------------------------------------------------------
    #
    # Comparisons are intentionally limited to Percentage-vs-Percentage.
    # Cross comparisons with Rate / InterestRate return NotImplemented (so
    # `==` is False and ordering raises TypeError) — they live in different
    # semantic dimensions and any cross-type ordering would be misleading.

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Percentage):
            return NotImplemented
        # Tolerance mirrors Rate.__eq__ so equal-by-value percentages compare
        # equal regardless of construction precision.
        return abs(self._decimal_rate - other._decimal_rate) < Decimal("0.0000001")

    def __hash__(self) -> int:
        # Percentages are value objects; equal-by-decimal percentages should
        # hash the same. We round to seven decimal places to mirror __eq__'s
        # tolerance.
        return hash(("Percentage", self._decimal_rate.quantize(Decimal("0.0000001"))))

    def __lt__(self, other: "Percentage") -> bool:
        if not isinstance(other, Percentage):
            return NotImplemented
        return self._decimal_rate < other._decimal_rate

    def __le__(self, other: "Percentage") -> bool:
        if not isinstance(other, Percentage):
            return NotImplemented
        return self._decimal_rate <= other._decimal_rate

    def __gt__(self, other: "Percentage") -> bool:
        if not isinstance(other, Percentage):
            return NotImplemented
        return self._decimal_rate > other._decimal_rate

    def __ge__(self, other: "Percentage") -> bool:
        if not isinstance(other, Percentage):
            return NotImplemented
        return self._decimal_rate >= other._decimal_rate
