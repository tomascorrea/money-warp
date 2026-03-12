"""Marshmallow custom fields for Money, Rate, and InterestRate.

Requires the ``marshmallow`` extra::

    pip install money-warp[marshmallow]
"""

from decimal import Decimal
from typing import Dict, Optional

from marshmallow import fields

from money_warp.interest_rate import InterestRate
from money_warp.money import Money
from money_warp.rate import CompoundingFrequency, Rate, YearSize

__all__ = [
    "MoneyField",
    "RateField",
    "InterestRateField",
]

_VALID_MONEY_REPRESENTATIONS = ("raw", "real", "cents", "float")
_VALID_RATE_REPRESENTATIONS = ("string", "dict")

_FREQUENCY_TOKEN = {
    CompoundingFrequency.ANNUALLY: "annual",
    CompoundingFrequency.MONTHLY: "monthly",
    CompoundingFrequency.DAILY: "daily",
    CompoundingFrequency.QUARTERLY: "quarterly",
    CompoundingFrequency.SEMI_ANNUALLY: "semi-annual",
}


class MoneyField(fields.Field):
    """Marshmallow field for :class:`~money_warp.money.Money`.

    Args:
        representation: Controls serialization format.
            ``"raw"`` (default) -- full-precision ``raw_amount`` as string.
            ``"real"`` -- rounded ``real_amount`` as string.
            ``"cents"`` -- integer cents.
            ``"float"`` -- rounded ``real_amount`` as a Python float.
    """

    default_error_messages = {
        "invalid": "Not a valid monetary amount.",
    }

    def __init__(self, representation: str = "raw", **kwargs) -> None:
        super().__init__(**kwargs)
        if representation not in _VALID_MONEY_REPRESENTATIONS:
            raise ValueError(
                f"Invalid representation: '{representation}'. Expected one of {_VALID_MONEY_REPRESENTATIONS}"
            )
        self.representation = representation

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        if not isinstance(value, Money):
            raise self.make_error("invalid")

        if self.representation == "raw":
            return str(value.raw_amount)
        if self.representation == "real":
            return str(value.real_amount)
        if self.representation == "float":
            return float(value.real_amount)
        return value.cents

    def _deserialize(self, value, attr, data, **kwargs):
        if value is None:
            return None
        try:
            if self.representation == "cents":
                result = Money.from_cents(int(value))
            elif self.representation == "float":
                result = Money(str(value))
            else:
                result = Money(value)
        except Exception as exc:
            raise self.make_error("invalid") from exc
        else:
            return result


class RateField(fields.Field):
    """Marshmallow field for :class:`~money_warp.rate.Rate`.

    Args:
        representation: Controls serialization format.
            ``"string"`` (default) -- human-readable string like ``"5.250% monthly"``.
            ``"dict"`` -- dict with all params needed to reconstruct the Rate.
        year_size: Default year-size convention for string deserialization.
        precision: Default precision for string deserialization.
        rounding: Default rounding mode for string deserialization.
        str_style: Default str_style for string deserialization.
        str_decimals: Default decimal places for string serialization.
        abbrev_labels: Default abbreviation label overrides for deserialization.
    """

    RATE_CLASS = Rate

    default_error_messages = {
        "invalid": "Not a valid rate.",
        "invalid_dict": "Expected a dict with at least 'rate' and 'period' keys.",
    }

    def __init__(
        self,
        representation: str = "string",
        year_size: YearSize = YearSize.commercial,
        precision: int | None = None,
        rounding: str = "ROUND_HALF_UP",
        str_style: str = "long",
        str_decimals: int = 3,
        abbrev_labels: Optional[Dict[CompoundingFrequency, str]] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if representation not in _VALID_RATE_REPRESENTATIONS:
            raise ValueError(
                f"Invalid representation: '{representation}'. Expected one of {_VALID_RATE_REPRESENTATIONS}"
            )
        self.representation = representation
        self.rate_year_size = year_size
        self.rate_precision = precision
        self.rate_rounding = rounding
        self.rate_str_style = str_style
        self.rate_str_decimals = str_decimals
        self.rate_abbrev_labels = abbrev_labels

    def _serialize(self, value, attr, obj, **kwargs):
        if value is None:
            return None
        if not isinstance(value, Rate):
            raise self.make_error("invalid")

        if self.representation == "string":
            token = _FREQUENCY_TOKEN[value.period]
            decimals = getattr(value, "_str_decimals", 3)
            return f"{value.as_percentage():.{decimals}f}% {token}"

        abbrev_labels = getattr(value, "_abbrev_labels", None)
        serialized_labels = {k.name.lower(): v for k, v in abbrev_labels.items()} if abbrev_labels else None
        return {
            "rate": str(value.as_decimal()),
            "period": value.period.name.lower(),
            "year_size": value.year_size.value,
            "precision": value._precision,
            "rounding": value._rounding,
            "str_style": value._str_style,
            "str_decimals": getattr(value, "_str_decimals", 3),
            "abbrev_labels": serialized_labels,
        }

    def _deserialize(self, value, attr, data, **kwargs):
        if value is None:
            return None

        if self.representation == "string":
            return self._deserialize_string(value)
        return self._deserialize_dict(value)

    def _deserialize_string(self, value):
        try:
            result = self.RATE_CLASS(
                value,
                year_size=self.rate_year_size,
                precision=self.rate_precision,
                rounding=self.rate_rounding,
                str_style=self.rate_str_style,
                str_decimals=self.rate_str_decimals,
                abbrev_labels=self.rate_abbrev_labels,
            )
        except Exception as exc:
            raise self.make_error("invalid") from exc
        else:
            return result

    def _deserialize_dict(self, value):
        if not isinstance(value, dict):
            raise self.make_error("invalid_dict")

        try:
            rate = Decimal(str(value["rate"]))
            period = CompoundingFrequency[value["period"].upper()]
        except (KeyError, TypeError, ValueError) as exc:
            raise self.make_error("invalid_dict") from exc

        try:
            year_size = YearSize(value["year_size"]) if "year_size" in value else self.rate_year_size
            precision = value.get("precision", self.rate_precision)
            rounding = value.get("rounding", self.rate_rounding)
            str_style = value.get("str_style", self.rate_str_style)
            str_decimals = value.get("str_decimals", self.rate_str_decimals)

            raw_labels = value.get("abbrev_labels")
            if raw_labels:
                abbrev_labels = {CompoundingFrequency[k.upper()]: v for k, v in raw_labels.items()}
            else:
                abbrev_labels = self.rate_abbrev_labels

            result = self.RATE_CLASS(
                rate,
                period=period,
                year_size=year_size,
                precision=precision,
                rounding=rounding,
                str_style=str_style,
                str_decimals=str_decimals,
                abbrev_labels=abbrev_labels,
            )
        except Exception as exc:
            raise self.make_error("invalid") from exc
        else:
            return result


class InterestRateField(RateField):
    """Marshmallow field for :class:`~money_warp.interest_rate.InterestRate`.

    Identical to :class:`RateField` but constructs ``InterestRate`` instances,
    which reject negative values.
    """

    RATE_CLASS = InterestRate

    default_error_messages = {
        **RateField.default_error_messages,
        "invalid": "Not a valid interest rate.",
    }
