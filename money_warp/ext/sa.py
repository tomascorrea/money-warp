"""SQLAlchemy custom types for Money, Rate, and InterestRate, plus bridge
decorators for loan/settlement models.

Requires the ``sa`` extra::

    pip install money-warp[sa]
"""

from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional, Type

from sqlalchemy import JSON, Integer, Numeric, String, func, select
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.types import TypeDecorator

from money_warp.interest_rate import InterestRate
from money_warp.loan import Loan, MoraStrategy
from money_warp.money import Money
from money_warp.rate import CompoundingFrequency, Rate, YearSize
from money_warp.tz import ensure_aware, now
from money_warp.warp import WarpedTime

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


def _parse_due_dates(raw: List[str]) -> List[datetime]:
    """Convert a JSON list of ISO date strings to timezone-aware datetimes."""
    return [ensure_aware(datetime.fromisoformat(d)) for d in raw]


def _reconstruct_current_balance(instance, as_of, meta):
    """Rebuild a money_warp Loan from SA fields, replay settlements, return current_balance.

    Manipulates the Loan's time context directly (via WarpedTime) instead
    of entering a Warp context manager, so this can safely be called from
    inside an existing Warp block.
    """
    principal_val = getattr(instance, meta["principal"])
    ir_val = getattr(instance, meta["interest_rate"], None)
    dd_val = getattr(instance, meta["due_dates"], None)
    db_val = getattr(instance, meta["disbursement_date"], None)

    if ir_val is None or dd_val is None or db_val is None:
        return None

    kwargs: dict = {}

    fine_rate_val = getattr(instance, meta["fine_rate"], None)
    if fine_rate_val is not None:
        kwargs["fine_rate"] = fine_rate_val

    gp_val = getattr(instance, meta["grace_period_days"], None)
    if gp_val is not None:
        kwargs["grace_period_days"] = gp_val

    mora_ir_val = getattr(instance, meta["mora_interest_rate"], None)
    if mora_ir_val is not None:
        kwargs["mora_interest_rate"] = mora_ir_val

    mora_strat_val = getattr(instance, meta["mora_strategy"], None)
    if mora_strat_val is not None:
        if isinstance(mora_strat_val, str):
            kwargs["mora_strategy"] = MoraStrategy[mora_strat_val]
        else:
            kwargs["mora_strategy"] = mora_strat_val

    loan = Loan(
        principal_val,
        ir_val,
        _parse_due_dates(dd_val),
        disbursement_date=db_val,
        **kwargs,
    )

    items = getattr(instance, meta["settlements"])
    settlement_meta = type(items[0])._money_warp_bridge_meta if items else None

    for item in items:
        loan.record_payment(
            getattr(item, settlement_meta["amount"]),
            getattr(item, settlement_meta["date"]),
        )

    as_of_aware = ensure_aware(as_of)
    loan._time_ctx.override(WarpedTime(as_of_aware))
    loan.calculate_late_fines(as_of_aware)

    return loan.current_balance


def loan_bridge(
    principal: str = "principal",
    settlements: str = "settlements",
    interest_rate: str = "interest_rate",
    due_dates: str = "due_dates",
    disbursement_date: str = "disbursement_date",
    fine_rate: str = "fine_rate",
    grace_period_days: str = "grace_period_days",
    mora_interest_rate: str = "mora_interest_rate",
    mora_strategy: str = "mora_strategy",
):
    """Add ``balance_at(date)`` and ``balance`` to a loan model.

    Both are SQL-queryable via :mod:`sqlalchemy.ext.hybrid`.

    ``balance_at(date)``
        When the loan model has ``interest_rate``, ``due_dates``, and
        ``disbursement_date``, reconstructs a full
        :class:`~money_warp.loan.Loan`, replays settlements, and returns
        ``current_balance`` (principal + accrued interest + fines).
        Falls back to the last settlement's ``remaining_balance`` (or
        ``principal``) when those fields are absent.

    ``balance``
        Convenience property equivalent to ``balance_at(now())``.

    All parameter names default to conventional column names. If your
    model follows the naming convention, ``@loan_bridge()`` with no
    arguments works.

    The settlement model **must** be decorated with
    :func:`settlement_bridge` so that this decorator can discover which
    columns hold balance, date, and amount.

    Args:
        principal: Attribute name for the principal amount.
        settlements: Relationship name pointing to the settlement model.
        interest_rate: Attribute name for the interest rate.
        due_dates: Attribute name for the JSON list of due dates.
        disbursement_date: Attribute name for the disbursement date.
        fine_rate: Attribute name for the fine rate.
        grace_period_days: Attribute name for the grace period in days.
        mora_interest_rate: Attribute name for the mora interest rate.
        mora_strategy: Attribute name for the mora strategy.
    """

    def decorator(cls):
        _meta = {
            "principal": principal,
            "settlements": settlements,
            "interest_rate": interest_rate,
            "due_dates": due_dates,
            "disbursement_date": disbursement_date,
            "fine_rate": fine_rate,
            "grace_period_days": grace_period_days,
            "mora_interest_rate": mora_interest_rate,
            "mora_strategy": mora_strategy,
        }

        @hybrid_method
        def balance_at(self, as_of):
            reconstructed = _reconstruct_current_balance(self, as_of, _meta)
            if reconstructed is not None:
                return reconstructed

            items = getattr(self, _meta["settlements"])
            if not items:
                return getattr(self, _meta["principal"])
            s_meta = type(items[0])._money_warp_bridge_meta
            hit = _find_last_settlement_before(items, as_of, s_meta)
            if hit is not None:
                return getattr(hit, s_meta["balance"])
            return getattr(self, _meta["principal"])

        @balance_at.expression
        def balance_at(cls, as_of):
            info = _resolve_settlement_info(cls, _meta["settlements"])
            return func.coalesce(
                select(info["balance_col"])
                .where(info["fk_col"] == info["pk_col"])
                .where(info["date_col"] <= as_of)
                .order_by(info["date_col"].desc())
                .limit(1)
                .correlate(cls)
                .scalar_subquery(),
                getattr(cls, _meta["principal"]),
            )

        @hybrid_property
        def balance(self):
            return self.balance_at(now())

        @balance.expression
        def balance(cls):
            return cls.balance_at(func.now())

        cls._money_warp_bridge_meta = _meta
        cls.balance_at = balance_at
        cls.balance = balance
        return cls

    return decorator
