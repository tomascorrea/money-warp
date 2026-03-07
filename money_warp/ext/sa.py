"""SQLAlchemy custom types for Money, Rate, and InterestRate, plus bridge
decorators for loan/settlement models.

Requires the ``sa`` extra::

    pip install money-warp[sa]
"""

from decimal import Decimal
from typing import Any, Optional, Type

from sqlalchemy import JSON, Integer, Numeric, String, func, select
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.types import TypeDecorator

from money_warp.interest_rate import InterestRate
from money_warp.money import Money
from money_warp.rate import CompoundingFrequency, Rate, YearSize
from money_warp.tz import ensure_aware, now

__all__ = [
    "MoneyType",
    "RateType",
    "InterestRateType",
    "settlement_bridge",
    "loan_bridge",
]

_VALID_MONEY_REPRESENTATIONS = ("raw", "real", "cents")
_VALID_RATE_REPRESENTATIONS = ("string", "json")

_FREQUENCY_TOKEN = {
    CompoundingFrequency.ANNUALLY: "annual",
    CompoundingFrequency.MONTHLY: "monthly",
    CompoundingFrequency.DAILY: "daily",
    CompoundingFrequency.QUARTERLY: "quarterly",
    CompoundingFrequency.SEMI_ANNUALLY: "semi-annual",
}


# ---------------------------------------------------------------------------
# TypeDecorators
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Bridge decorators
# ---------------------------------------------------------------------------

_BRIDGE_META_ATTR = "_money_warp_bridge_meta"


def settlement_bridge(
    balance: str = "remaining_balance",
    date: str = "payment_date",
    amount: str = "amount",
):
    """Mark a settlement model with column metadata for :func:`loan_bridge`.

    Stores a ``_money_warp_bridge_meta`` dict on the class so that
    ``@loan_bridge`` can discover which columns hold the remaining
    balance, payment date, and payment amount.

    All parameters have sensible defaults. If your columns follow the
    naming convention, ``@settlement_bridge()`` with no arguments works.

    Args:
        balance: Attribute name for the remaining balance after settlement.
        date: Attribute name for the payment/settlement date.
        amount: Attribute name for the payment amount.
    """

    def decorator(cls):
        cls._money_warp_bridge_meta = {
            "balance": balance,
            "date": date,
            "amount": amount,
        }
        return cls

    return decorator


def _resolve_settlement_info(cls, settlements_attr):
    """Introspect the settlement relationship to extract column references."""
    rel = getattr(cls, settlements_attr).property
    target_model = rel.mapper.class_

    if not hasattr(target_model, _BRIDGE_META_ATTR):
        raise TypeError(
            f"{target_model.__name__} must be decorated with "
            "@settlement_bridge so that @loan_bridge can "
            "discover its column metadata."
        )

    meta = target_model._money_warp_bridge_meta
    return {
        "balance_col": getattr(target_model, meta["balance"]),
        "date_col": getattr(target_model, meta["date"]),
        "fk_col": list(rel.remote_side)[0],
        "pk_col": list(rel.local_columns)[0],
    }


def _find_last_settlement_before(items, as_of, meta):
    """Return the last settlement whose date is ``<= as_of``, or ``None``."""
    as_of_aware = ensure_aware(as_of)
    last_before = None
    for item in items:
        if ensure_aware(getattr(item, meta["date"])) <= as_of_aware:
            last_before = item
        else:
            break
    return last_before


def loan_bridge(
    principal: str,
    settlements: str,
):
    """Add ``balance_at(date)`` and ``balance`` to a loan model.

    Both are SQL-queryable via :mod:`sqlalchemy.ext.hybrid`.

    ``balance_at(date)``
        Returns the remaining balance as of *date* — the
        ``remaining_balance`` from the last settlement whose payment
        date is ``<= date``, falling back to ``principal`` when there
        are no settlements before that date.

    ``balance``
        Convenience property equivalent to ``balance_at(now())``.

    The settlement model **must** be decorated with
    :func:`settlement_bridge` so that this decorator can discover which
    columns hold balance, date, and amount.

    Args:
        principal: Attribute name on the loan model for the principal
            amount (``MoneyType`` column used as fallback).
        settlements: Relationship name pointing to the settlement model.
    """

    def decorator(cls):
        _settlements_attr = settlements
        _principal_attr = principal

        @hybrid_method
        def balance_at(self, as_of):
            items = getattr(self, _settlements_attr)
            if not items:
                return getattr(self, _principal_attr)
            meta = type(items[0])._money_warp_bridge_meta
            hit = _find_last_settlement_before(items, as_of, meta)
            if hit is not None:
                return getattr(hit, meta["balance"])
            return getattr(self, _principal_attr)

        @balance_at.expression
        def balance_at(cls, as_of):
            info = _resolve_settlement_info(cls, _settlements_attr)
            return func.coalesce(
                select(info["balance_col"])
                .where(info["fk_col"] == info["pk_col"])
                .where(info["date_col"] <= as_of)
                .order_by(info["date_col"].desc())
                .limit(1)
                .correlate(cls)
                .scalar_subquery(),
                getattr(cls, _principal_attr),
            )

        @hybrid_property
        def balance(self):
            return self.balance_at(now())

        @balance.expression
        def balance(cls):
            return cls.balance_at(func.now())

        cls._money_warp_bridge_meta = {
            "principal": _principal_attr,
            "settlements": _settlements_attr,
        }
        cls.balance_at = balance_at
        cls.balance = balance
        return cls

    return decorator
