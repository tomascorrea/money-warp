"""Bridge decorators that connect SQLAlchemy models to money-warp's Loan engine.

``@settlement_bridge`` marks a settlement model with column metadata.
``@loan_bridge`` adds ``balance_at(date)`` and ``balance`` hybrid
properties that delegate to a reconstructed :class:`~money_warp.loan.Loan`.
"""

from datetime import date, datetime
from typing import List, Union

from sqlalchemy import Float, String, case, cast, column, func, literal, select
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property

from money_warp.ext.sa.compat import (
    mw_greatest,
    mw_instr,
    mw_json_array_length,
    mw_json_array_values,
    mw_json_extract,
    mw_julianday,
)
from money_warp.ext.sa.types import _FREQUENCY_TOKEN
from money_warp.loan import Loan, MoraStrategy
from money_warp.rate import _ABBREV_MAP, CompoundingFrequency
from money_warp.tz import ensure_aware, now
from money_warp.warp import Warp, WarpedTime

_BRIDGE_META_ATTR = "_money_warp_bridge_meta"

_REQUIRED_LOAN_FIELDS = ("interest_rate", "due_dates", "disbursement_date")


# ---------------------------------------------------------------------------
# settlement_bridge
# ---------------------------------------------------------------------------


def settlement_bridge(
    balance: str = "remaining_balance",
    date: str = "payment_date",
    amount: str = "amount",
    interest_date: str = "interest_date",
    processing_date: str = "processing_date",
    intention: str = "intention",
):
    """Mark a settlement model with column metadata for :func:`loan_bridge`.

    Stores a ``_money_warp_bridge_meta`` dict on the class so that
    ``@loan_bridge`` can discover which columns hold the remaining
    balance, payment date, payment amount, interest date, processing
    date, and payment intention.

    All parameters have sensible defaults.  If your columns follow the
    naming convention, ``@settlement_bridge()`` with no arguments works.

    The ``interest_date`` and ``processing_date`` columns are optional
    on the model.  When absent or ``None``,
    :meth:`~money_warp.loan.Loan.record_payment` uses its own defaults.

    The ``intention`` column is a JSON object that declares which payment
    method was used when the settlement was created.  Recognized shapes::

        {"method": "record_payment"}
        {"method": "pay_installment"}
        {"method": "anticipate_payment", "installments": [1, 2]}

    When the attribute is absent on the model,
    ``{"method": "record_payment"}`` is assumed for backward
    compatibility.

    Args:
        balance: Attribute name for the remaining balance after settlement.
        date: Attribute name for the payment/settlement date.
        amount: Attribute name for the payment amount.
        interest_date: Attribute name for the interest accrual cutoff date.
        processing_date: Attribute name for the audit-trail processing date.
        intention: Attribute name for the payment intention JSON object.
    """

    def decorator(cls):
        cls._money_warp_bridge_meta = {
            "balance": balance,
            "date": date,
            "amount": amount,
            "interest_date": interest_date,
            "processing_date": processing_date,
            "intention": intention,
        }
        return cls

    return decorator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _parse_due_dates(raw: List[Union[str, date, datetime]]) -> List[datetime]:
    """Convert a list of due dates to timezone-aware datetimes.

    Accepts ISO strings (raw ``JSON`` column), :class:`~datetime.date`
    objects (from :class:`~money_warp.ext.sa.types.DueDatesType`), or
    :class:`~datetime.datetime` objects.
    """
    result: List[datetime] = []
    for d in raw:
        if isinstance(d, datetime):
            result.append(ensure_aware(d))
        elif isinstance(d, date):
            result.append(ensure_aware(datetime(d.year, d.month, d.day)))
        else:
            result.append(ensure_aware(datetime.fromisoformat(d)))
    return result


def _collect_optional_loan_kwargs(instance, meta):
    """Gather optional Loan constructor kwargs from the SA instance."""
    kwargs: dict = {}

    for key in ("fine_rate", "grace_period_days", "mora_interest_rate"):
        val = getattr(instance, meta[key], None)
        if val is not None:
            kwargs[key] = val

    mora_strat_val = getattr(instance, meta["mora_strategy"], None)
    if mora_strat_val is not None:
        kwargs["mora_strategy"] = MoraStrategy[mora_strat_val] if isinstance(mora_strat_val, str) else mora_strat_val

    return kwargs


_DEFAULT_INTENTION = {"method": "record_payment"}


def _replay_settlements(loan, items):
    """Replay recorded settlements onto *loan*, warping time per payment.

    Dispatches to the correct payment method based on the ``intention``
    JSON stored on each settlement item:

    - ``"record_payment"`` (default): explicit dates via ``record_payment``.
    - ``"pay_installment"``: delegates to ``loan.pay_installment`` which
      computes ``interest_date = max(now, next_due)`` internally.
    - ``"anticipate_payment"``: delegates to ``loan.anticipate_payment``
      with optional installment numbers from the JSON.

    When the ``intention`` attribute is absent on the model, falls back
    to ``record_payment`` for backward compatibility.
    """
    if not items:
        return

    s_meta = type(items[0])._money_warp_bridge_meta
    for item in items:
        pdate = ensure_aware(getattr(item, s_meta["date"]))
        loan._time_ctx.override(WarpedTime(pdate))

        amount = getattr(item, s_meta["amount"])
        raw_intention = getattr(item, s_meta["intention"], _DEFAULT_INTENTION)
        method = raw_intention.get("method", "record_payment")

        if method == "pay_installment":
            loan.pay_installment(amount)
        elif method == "anticipate_payment":
            installments = raw_intention.get("installments")
            loan.anticipate_payment(amount, installments=installments)
        else:
            rp_kwargs: dict = {}
            idate = getattr(item, s_meta["interest_date"], None)
            if idate is not None:
                rp_kwargs["interest_date"] = idate
            proc_date = getattr(item, s_meta["processing_date"], None)
            if proc_date is not None:
                rp_kwargs["processing_date"] = proc_date

            loan.record_payment(amount, pdate, **rp_kwargs)


def _load_money_warp_loan_impl(self):
    """Reconstruct a :class:`~money_warp.loan.Loan` from SQLAlchemy model fields.

    Reads all loan parameters from the instance via its
    ``_money_warp_bridge_meta``, replays recorded settlements (warping
    the loan's time context to each payment date for accurate replay),
    and returns the hydrated Loan.

    Returns:
        A ``Loan`` with all historical payments replayed.

    Raises:
        ValueError: If any required field (``interest_rate``,
            ``due_dates``, ``disbursement_date``) is ``None``.
    """
    meta = type(self)._money_warp_bridge_meta

    for field_name in _REQUIRED_LOAN_FIELDS:
        attr = meta[field_name]
        if getattr(self, attr, None) is None:
            raise ValueError(
                f"Cannot reconstruct Loan: '{attr}' is None on "
                f"{type(self).__name__}. All of {_REQUIRED_LOAN_FIELDS} "
                "are required."
            )

    loan = Loan(
        getattr(self, meta["principal"]),
        getattr(self, meta["interest_rate"]),
        _parse_due_dates(getattr(self, meta["due_dates"])),
        disbursement_date=getattr(self, meta["disbursement_date"]),
        **_collect_optional_loan_kwargs(self, meta),
    )

    _replay_settlements(loan, getattr(self, meta["settlements"]))

    return loan


# ---------------------------------------------------------------------------
# SQL helpers — rate conversion
# ---------------------------------------------------------------------------

# Period-name lookups derived from CompoundingFrequency, keyed by representation.
# JSON uses freq.name.lower(); string accepts both long tokens from
# _FREQUENCY_TOKEN ("annual") and abbreviated tokens from _ABBREV_MAP ("a.a.").
_PERIOD_NAMES: dict[str, dict[CompoundingFrequency, list[str]]] = {
    "json": {freq: [freq.name.lower()] for freq in CompoundingFrequency},
    "string": {freq: [_FREQUENCY_TOKEN[freq], _ABBREV_MAP[freq]] for freq in _FREQUENCY_TOKEN},
}


def _get_rate_col_info(cls, attr_name):
    """Introspect a rate column's type to get ``(representation, default_year_size)``."""
    col_type = getattr(cls, attr_name).property.columns[0].type
    representation = getattr(col_type, "representation", "json")
    year_size = getattr(col_type, "rate_year_size", None)
    default_year_size = float(year_size.value) if year_size is not None else 365.0
    return representation, default_year_size


def _extract_rate_params(rate_col, representation, default_year_size):
    """Extract ``(decimal_rate, period, year_size)`` as SQL expressions.

    For JSON: reads ``$.rate``, ``$.period``, ``$.year_size`` via ``json_extract``.
    For string: parses ``"5.250% annual"`` via ``SUBSTR``/``INSTR``; uses
    *default_year_size* since the string format does not embed year size.
    """
    if representation == "json":
        rate = cast(mw_json_extract(rate_col, "rate"), Float)
        period = mw_json_extract(rate_col, "period")
        year_size = cast(mw_json_extract(rate_col, "year_size"), Float)
    else:
        pct_pos = mw_instr(rate_col, "%")
        rate = cast(func.substr(rate_col, 1, pct_pos - 1), Float) / 100.0
        period = func.trim(func.substr(rate_col, pct_pos + 1))
        year_size = default_year_size
    return rate, period, year_size


def _periods_per_year_expr(period, year_size, representation):
    """Map a period name to its periods-per-year value in SQL.

    Generated from :class:`CompoundingFrequency` — no hardcoded magic numbers.
    ``CONTINUOUS`` is excluded (handled separately via ``exp()``).
    Each frequency may have multiple recognized tokens (long and abbreviated).
    """
    names = _PERIOD_NAMES[representation]
    branches = []
    for freq in CompoundingFrequency:
        if freq == CompoundingFrequency.CONTINUOUS:
            continue
        freq_names = names.get(freq)
        if not freq_names:
            continue
        n = year_size if freq == CompoundingFrequency.DAILY else float(freq.value)
        for name in freq_names:
            branches.append((period == name, n))
    return case(*branches, else_=1.0)


def _effective_annual_from_params(rate, period, n, representation):
    """Apply the effective-annual formula to pre-extracted SQL params.

    Mirrors :meth:`Rate._to_effective_annual`.
    """
    continuous_names = _PERIOD_NAMES[representation].get(CompoundingFrequency.CONTINUOUS, [])
    return case(
        (period.in_(continuous_names), func.exp(rate) - 1.0),
        else_=func.pow(1.0 + rate, n) - 1.0,
    )


def _effective_annual_expr(rate_col, representation, default_year_size):
    """SQL expression converting any stored rate to effective annual."""
    rate, period, year_size = _extract_rate_params(rate_col, representation, default_year_size)
    n = _periods_per_year_expr(period, year_size, representation)
    return _effective_annual_from_params(rate, period, n, representation)


def _daily_rate_expr(rate_col, representation, default_year_size):
    """SQL expression for the daily rate from a stored rate column.

    Returns the stored rate directly when the period is already daily;
    otherwise converts through the effective annual rate.
    Mirrors :meth:`Rate.to_daily`.
    """
    rate, period, year_size = _extract_rate_params(rate_col, representation, default_year_size)
    n = _periods_per_year_expr(period, year_size, representation)
    eff_annual = _effective_annual_from_params(rate, period, n, representation)

    daily_names = _PERIOD_NAMES[representation].get(CompoundingFrequency.DAILY, [])
    return case(
        (period.in_(daily_names), rate),
        else_=func.pow(1.0 + eff_annual, 1.0 / year_size) - 1.0,
    )


def _has_rate(rate_col, representation):
    """SQL expression that is NULL when no parseable rate is present."""
    if representation == "json":
        return cast(mw_json_extract(rate_col, "rate"), Float)
    return rate_col


def _fine_rate_decimal_expr(cls, meta_key):
    """SQL expression extracting the fine rate's decimal value.

    The ``fine_rate`` column is expected to be an ``InterestRateType``
    (string or JSON).  The decimal rate is extracted with the same
    helpers used for ``interest_rate`` and ``mora_interest_rate``.
    """
    col = getattr(cls, meta_key)
    repr_, default_ys = _get_rate_col_info(cls, meta_key)
    rate, _period, _year_size = _extract_rate_params(col, repr_, default_ys)
    return rate


# ---------------------------------------------------------------------------
# SQL expression (CTE-based)
# ---------------------------------------------------------------------------


_COMPONENT_ALL = "all"
_COMPONENT_PRINCIPAL = "principal"
_COMPONENT_INTEREST = "interest"
_COMPONENT_MORA = "mora_interest"
_COMPONENT_FINES = "fines"


def _build_sql_balance_expression(cls, as_of, meta, component=_COMPONENT_ALL):
    """Build a CTE-based SQL expression for a balance component.

    Uses nested CTEs (``nesting=True``) inside a single scalar subquery
    so that each computation step is named and readable.  Falls back to
    ``COALESCE(remaining_balance, principal)`` for the principal component
    or ``0`` for other components when the interest rate is NULL.

    Args:
        cls: The SQLAlchemy model class.
        as_of: The date expression to compute the balance at.
        meta: Bridge metadata dict mapping logical names to column names.
        component: Which balance component to return.  One of
            ``_COMPONENT_ALL`` (sum, default), ``_COMPONENT_PRINCIPAL``,
            ``_COMPONENT_INTEREST``, ``_COMPONENT_MORA``, ``_COMPONENT_FINES``.
    """
    info = _resolve_settlement_info(cls, meta["settlements"])
    pr_col = getattr(cls, meta["principal"])
    ir_col = getattr(cls, meta["interest_rate"])
    dd_col = getattr(cls, meta["due_dates"])
    db_col = getattr(cls, meta["disbursement_date"])
    fr_col = _fine_rate_decimal_expr(cls, meta["fine_rate"])
    gp_col = getattr(cls, meta["grace_period_days"])
    mir_col = getattr(cls, meta["mora_interest_rate"])
    ms_col = getattr(cls, meta["mora_strategy"])

    ir_repr, ir_ys = _get_rate_col_info(cls, meta["interest_rate"])
    mir_repr, mir_ys = _get_rate_col_info(cls, meta["mora_interest_rate"])

    # -- CTE 1: loan_state -------------------------------------------------
    last_balance_sq = (
        select(info["balance_col"])
        .where(info["fk_col"] == info["pk_col"])
        .where(info["date_col"] <= as_of)
        .order_by(info["date_col"].desc())
        .limit(1)
        .correlate(cls)
        .scalar_subquery()
    )
    last_date_sq = (
        select(info["date_col"])
        .where(info["fk_col"] == info["pk_col"])
        .where(info["date_col"] <= as_of)
        .order_by(info["date_col"].desc())
        .limit(1)
        .correlate(cls)
        .scalar_subquery()
    )
    loan_state = (
        select(
            func.coalesce(last_balance_sq, pr_col).label("principal_balance"),
            func.coalesce(last_date_sq, db_col).label("last_pay_date"),
        )
        .correlate(cls)
        .cte("loan_state", nesting=True)
    )

    # -- CTE 2: daily_rates ------------------------------------------------
    daily_rates = (
        select(
            _daily_rate_expr(ir_col, ir_repr, ir_ys).label("daily_rate"),
            func.coalesce(_daily_rate_expr(mir_col, mir_repr, mir_ys), 0.0).label("mora_daily_rate"),
        )
        .correlate(cls)
        .cte("daily_rates", nesting=True)
    )

    # -- CTE 3: time_split -------------------------------------------------
    je_next = mw_json_array_values(dd_col).table_valued(column("value", String))
    next_due_sq = (
        select(func.min(je_next.c.value))
        .where(mw_julianday(je_next.c.value) > mw_julianday(loan_state.c.last_pay_date))
        .correlate(cls)
        .scalar_subquery()
    )

    total_days_expr = mw_greatest(
        0,
        mw_julianday(as_of) - mw_julianday(loan_state.c.last_pay_date),
    )

    time_split = (
        select(
            total_days_expr.label("total_days"),
            next_due_sq.label("next_due"),
            loan_state.c.last_pay_date,
        )
        .correlate(cls)
        .cte("time_split", nesting=True)
    )

    # -- CTE 4: day_split --------------------------------------------------
    regular_days_expr = case(
        (time_split.c.next_due.is_(None), time_split.c.total_days),
        (
            mw_julianday(time_split.c.next_due) >= mw_julianday(as_of),
            time_split.c.total_days,
        ),
        else_=mw_greatest(
            0,
            mw_julianday(time_split.c.next_due) - mw_julianday(time_split.c.last_pay_date),
        ),
    )

    day_split = (
        select(
            regular_days_expr.label("regular_days"),
            mw_greatest(0, time_split.c.total_days - regular_days_expr).label("mora_days"),
        )
        .correlate(cls)
        .cte("day_split", nesting=True)
    )

    # -- CTE 5: accrued ----------------------------------------------------
    reg_interest = loan_state.c.principal_balance * (
        func.pow(1.0 + daily_rates.c.daily_rate, day_split.c.regular_days) - 1.0
    )

    mora_interest_compound = (loan_state.c.principal_balance + reg_interest) * (
        func.pow(1.0 + daily_rates.c.mora_daily_rate, day_split.c.mora_days) - 1.0
    )
    mora_interest_simple = loan_state.c.principal_balance * (
        func.pow(1.0 + daily_rates.c.mora_daily_rate, day_split.c.mora_days) - 1.0
    )

    accrued = (
        select(
            reg_interest.label("regular_interest"),
            case(
                (ms_col == "COMPOUND", mora_interest_compound),
                else_=mora_interest_simple,
            ).label("mora_interest"),
        )
        .select_from(loan_state.join(daily_rates, literal(True)).join(day_split, literal(True)))
        .correlate(cls)
        .cte("accrued", nesting=True)
    )

    # -- CTE 6: late_fines -------------------------------------------------
    settlement_count = (
        select(func.count())
        .where(info["fk_col"] == info["pk_col"])
        .where(info["date_col"] <= as_of)
        .correlate(cls)
        .scalar_subquery()
    )

    je_grace = mw_json_array_values(dd_col).table_valued(column("value", String))
    past_grace_count = (
        select(func.count())
        .where(mw_julianday(je_grace.c.value) + func.coalesce(gp_col, 0) < mw_julianday(as_of))
        .correlate(cls)
        .scalar_subquery()
    )

    num_inst = cast(mw_json_array_length(dd_col), Float)

    je_max = mw_json_array_values(dd_col).table_valued(column("value", String))
    max_due_sq = select(func.max(je_max.c.value)).correlate(cls).scalar_subquery()

    avg_period = case(
        (num_inst <= 1, 30.0),
        else_=(mw_julianday(max_due_sq) - mw_julianday(db_col)) / num_inst,
    )
    periodic_rate = func.pow(1.0 + daily_rates.c.daily_rate, avg_period) - 1.0
    pmt = pr_col * periodic_rate / (1.0 - func.pow(1.0 + periodic_rate, -num_inst))
    late_count = mw_greatest(0, past_grace_count - settlement_count)

    late_fines = (
        select(
            (func.coalesce(fr_col, 0) * pmt * late_count).label("total_fines"),
        )
        .select_from(daily_rates)
        .correlate(cls)
        .cte("late_fines", nesting=True)
    )

    # -- Final SELECT: pick requested component ----------------------------
    _component_expr = {
        _COMPONENT_PRINCIPAL: loan_state.c.principal_balance,
        _COMPONENT_INTEREST: accrued.c.regular_interest,
        _COMPONENT_MORA: accrued.c.mora_interest,
        _COMPONENT_FINES: late_fines.c.total_fines,
        _COMPONENT_ALL: (
            loan_state.c.principal_balance
            + accrued.c.regular_interest
            + accrued.c.mora_interest
            + late_fines.c.total_fines
        ),
    }

    target_expr = _component_expr[component]

    full_sq = (
        select(target_expr.label("result"))
        .select_from(loan_state.join(accrued, literal(True)).join(late_fines, literal(True)))
        .correlate(cls)
        .scalar_subquery()
    )

    # -- Fallback when rate is NULL ----------------------------------------
    simple_fallback = (
        func.coalesce(last_balance_sq, pr_col) if component in (_COMPONENT_ALL, _COMPONENT_PRINCIPAL) else literal(0.0)
    )

    rate_present = _has_rate(ir_col, ir_repr)
    return case(
        (rate_present.is_(None), simple_fallback),
        else_=full_sq,
    )


# ---------------------------------------------------------------------------
# Hybrid method/property factory
# ---------------------------------------------------------------------------


def _attach_balance_hybrid(cls, meta, name, loan_attr, component):
    """Attach a ``{name}_at`` hybrid_method and ``{name}`` hybrid_property to *cls*.

    Python side: reconstruct Loan via Warp, read *loan_attr*.
    SQL side: delegate to ``_build_sql_balance_expression`` with *component*.
    """

    @hybrid_method
    def _at_method(self, as_of):
        loan = self._load_money_warp_loan()
        loan.fines_applied = {}
        with Warp(loan, as_of) as warped:
            return getattr(warped, loan_attr)

    @_at_method.expression
    def _at_method(cls, as_of):
        return _build_sql_balance_expression(cls, as_of, meta, component)

    @hybrid_property
    def _prop(self):
        return getattr(self, f"{name}_at")(now())

    @_prop.expression
    def _prop(cls):
        return getattr(cls, f"{name}_at")(func.now())

    setattr(cls, f"{name}_at", _at_method)
    setattr(cls, name, _prop)


# ---------------------------------------------------------------------------
# loan_bridge
# ---------------------------------------------------------------------------


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
    """Add balance hybrid methods/properties to a loan model.

    Adds the following to the decorated class:

    ``_load_money_warp_loan()``
        Reconstructs a :class:`~money_warp.loan.Loan` from the model's
        stored fields and replays settlements.

    **Total balance:**

    - ``balance_at(date)`` -- total outstanding balance at *date*.
    - ``balance`` -- convenience property for ``balance_at(now())``.

    **Component balances (each has an ``_at(date)`` method and a property):**

    - ``principal_balance_at`` / ``principal_balance``
    - ``interest_balance_at`` / ``interest_balance``
    - ``mora_interest_balance_at`` / ``mora_interest_balance``
    - ``fine_balance_at`` / ``fine_balance``

    On the Python side each method reconstructs the Loan via Warp and
    reads the corresponding property.  On the SQL side each delegates to
    ``_build_sql_balance_expression`` with the matching component.

    The settlement model **must** be decorated with
    :func:`settlement_bridge`.

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

        # -- total balance (special: reads current_balance) ----------------
        _attach_balance_hybrid(cls, _meta, "balance", "current_balance", _COMPONENT_ALL)

        # -- component balances --------------------------------------------
        _COMPONENTS = [
            ("principal_balance", _COMPONENT_PRINCIPAL),
            ("interest_balance", _COMPONENT_INTEREST),
            ("mora_interest_balance", _COMPONENT_MORA),
            ("fine_balance", _COMPONENT_FINES),
        ]
        for name, comp in _COMPONENTS:
            _attach_balance_hybrid(cls, _meta, name, name, comp)

        cls._money_warp_bridge_meta = _meta
        cls._load_money_warp_loan = _load_money_warp_loan_impl
        return cls

    return decorator
