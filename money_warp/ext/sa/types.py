"""SQLAlchemy TypeDecorators for Money, Rate, and InterestRate."""

from decimal import Decimal
from typing import Any, Optional, Type

from sqlalchemy import JSON, Integer, Numeric, String
from sqlalchemy.types import TypeDecorator

from money_warp.interest_rate import InterestRate
from money_warp.money import Money
from money_warp.rate import CompoundingFrequency, Rate, YearSize

_VALID_MONEY_REPRESENTATIONS = ("raw", "real", "cents")
_VALID_RATE_REPRESENTATIONS = ("string", "json")

_FREQUENCY_TOKEN = {
    CompoundingFrequency.ANNUALLY: "annual",
    CompoundingFrequency.MONTHLY: "monthly",
    CompoundingFrequency.DAILY: "daily",
    CompoundingFrequency.QUARTERLY: "quarterly",
    CompoundingFrequency.SEMI_ANNUALLY: "semi-annual",
}


class MoneyType(TypeDecorator):
    """SQLAlchemy column type for :class:`~money_warp.money.Money`.

    Args:
        representation: Controls storage format.
            ``"raw"`` (default) -- ``Numeric`` column storing ``raw_amount``.
            ``"real"`` -- ``Numeric`` column storing ``real_amount``.
            ``"cents"`` -- ``Integer`` column storing cents.
    """

    impl = Numeric
    cache_ok = True

    def __init__(self, representation: str = "raw") -> None:
        if representation not in _VALID_MONEY_REPRESENTATIONS:
            raise ValueError(
                f"Invalid representation: '{representation}'. Expected one of {_VALID_MONEY_REPRESENTATIONS}"
            )
        self.representation = representation
        super().__init__()

    def load_dialect_impl(self, dialect):
        if self.representation == "cents":
            return dialect.type_descriptor(Integer())
        return dialect.type_descriptor(Numeric(precision=20, scale=10))

    def process_bind_param(self, value, dialect) -> Any:
        if value is None:
            return None
        if isinstance(value, Money):
            if self.representation == "raw":
                return value.raw_amount
            if self.representation == "real":
                return value.real_amount
            return value.cents
        return value

    def process_result_value(self, value: Any, dialect) -> Optional[Money]:
        if value is None:
            return None
        if self.representation == "cents":
            return Money.from_cents(int(value))
        return Money(value)


class RateType(TypeDecorator):
    """SQLAlchemy column type for :class:`~money_warp.rate.Rate`.

    Args:
        representation: Controls storage format.
            ``"string"`` (default) -- ``String`` column like ``"5.250% annual"``.
            ``"json"`` -- ``JSON`` column with full params for lossless round-trip.
        year_size: Default year-size convention for string deserialization.
        precision: Default precision for string deserialization.
        rounding: Default rounding mode for string deserialization.
        str_style: Default str_style for string deserialization.
    """

    RATE_CLASS: Type[Rate] = Rate

    impl = String
    cache_ok = True

    def __init__(
        self,
        representation: str = "string",
        year_size: YearSize = YearSize.commercial,
        precision: int | None = None,
        rounding: str = "ROUND_HALF_UP",
        str_style: str = "long",
    ) -> None:
        if representation not in _VALID_RATE_REPRESENTATIONS:
            raise ValueError(
                f"Invalid representation: '{representation}'. Expected one of {_VALID_RATE_REPRESENTATIONS}"
            )
        self.representation = representation
        self.rate_year_size = year_size
        self.rate_precision = precision
        self.rate_rounding = rounding
        self.rate_str_style = str_style
        super().__init__()

    def load_dialect_impl(self, dialect):
        if self.representation == "json":
            return dialect.type_descriptor(JSON())
        return dialect.type_descriptor(String())

    def process_bind_param(self, value: Optional[Rate], dialect) -> Any:
        if value is None:
            return None

        if self.representation == "string":
            token = _FREQUENCY_TOKEN[value.period]
            return f"{value.as_percentage:.3f}% {token}"

        return {
            "rate": str(value.as_decimal),
            "period": value.period.name.lower(),
            "year_size": value.year_size.value,
            "precision": value._precision,
            "rounding": value._rounding,
            "str_style": value._str_style,
        }

    def process_result_value(self, value: Any, dialect) -> Optional[Rate]:
        if value is None:
            return None

        if self.representation == "string":
            return self._from_string(value)
        return self._from_dict(value)

    def _from_string(self, value: str) -> Rate:
        return self.RATE_CLASS(
            value,
            year_size=self.rate_year_size,
            precision=self.rate_precision,
            rounding=self.rate_rounding,
            str_style=self.rate_str_style,
        )

    def _from_dict(self, value: dict) -> Rate:
        rate = Decimal(str(value["rate"]))
        period = CompoundingFrequency[value["period"].upper()]
        year_size = YearSize(value["year_size"]) if "year_size" in value else self.rate_year_size
        precision = value.get("precision", self.rate_precision)
        rounding = value.get("rounding", self.rate_rounding)
        str_style = value.get("str_style", self.rate_str_style)

        return self.RATE_CLASS(
            rate,
            period=period,
            year_size=year_size,
            precision=precision,
            rounding=rounding,
            str_style=str_style,
        )


class InterestRateType(RateType):
    """SQLAlchemy column type for :class:`~money_warp.interest_rate.InterestRate`.

    Identical to :class:`RateType` but constructs ``InterestRate`` instances,
    which reject negative values.
    """

    RATE_CLASS = InterestRate
