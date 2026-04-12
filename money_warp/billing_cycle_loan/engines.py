"""Billing-cycle loan engine — product-specific logic only.

Mora rate resolution and statement building live here.
The forward pass and all allocation logic come from
:mod:`money_warp.loan.engines`.  Shared building blocks come from
:mod:`money_warp.engines`.
"""

from datetime import date, datetime, tzinfo
from typing import Dict, List, Optional

from ..billing_cycle import BaseBillingCycle
from ..engines import InterestCalculator, LoanState, MoraRateCallback
from ..engines import compute_state as _compute_state
from ..interest_rate import InterestRate
from ..models import BillingCycleLoanStatement, Settlement
from ..money import Money
from ..scheduler import PaymentSchedule
from ..tz import to_date
from .mora_rate_resolver import MoraRateResolver

# ------------------------------------------------------------------
# Mora rate resolution
# ------------------------------------------------------------------


def resolve_mora_rate(
    due_dates: List[date],
    closing_dates: List[datetime],
    current_due: Optional[date],
    base_mora_rate: InterestRate,
    resolver: Optional[MoraRateResolver],
    tz: tzinfo,
) -> InterestRate:
    """Return the mora rate for the cycle that owns *current_due*.

    Finds the closing date whose due date matches *current_due*,
    then passes it to the resolver.  Falls back to *base_mora_rate*
    when no resolver is provided or the due date cannot be mapped.
    """
    if resolver is None or current_due is None:
        return base_mora_rate

    for i, dd in enumerate(due_dates):
        if dd == current_due and i < len(closing_dates):
            return resolver(to_date(closing_dates[i], tz), base_mora_rate)

    return base_mora_rate


def make_mora_callback(
    due_dates: List[date],
    closing_dates: List[datetime],
    base_mora_rate: InterestRate,
    resolver: Optional[MoraRateResolver],
    tz: tzinfo,
) -> MoraRateCallback:
    """Build a :data:`~money_warp.engines.MoraRateCallback` for the forward pass.

    Returns ``None`` when no resolver is set (the unified
    ``compute_state`` then uses the calculator's default rate).
    """
    if resolver is None:
        return None

    def _callback(next_due: Optional[date]) -> Optional[InterestRate]:
        return resolve_mora_rate(due_dates, closing_dates, next_due, base_mora_rate, resolver, tz)

    return _callback


# ------------------------------------------------------------------
# Forward pass (delegates to unified compute_state)
# ------------------------------------------------------------------


def compute_state(
    principal: Money,
    interest_calc: InterestCalculator,
    schedule: PaymentSchedule,
    due_dates: List[date],
    closing_dates: List[datetime],
    fine_rate: InterestRate,
    grace_period_days: int,
    disbursement_date: datetime,
    payment_entries: list,
    as_of: datetime,
    tz: tzinfo,
    base_mora_rate: InterestRate,
    mora_rate_resolver: Optional[MoraRateResolver] = None,
    fine_observation_dates: Optional[List[datetime]] = None,
) -> LoanState:
    """Forward pass for billing-cycle loans.

    Wraps :func:`money_warp.loan.engines.compute_state` with a
    ``mora_rate_for_event`` callback that resolves the mora rate
    per billing cycle.
    """
    callback = make_mora_callback(due_dates, closing_dates, base_mora_rate, mora_rate_resolver, tz)
    return _compute_state(
        principal=principal,
        interest_calc=interest_calc,
        schedule=schedule,
        due_dates=due_dates,
        fine_rate=fine_rate,
        grace_period_days=grace_period_days,
        disbursement_date=disbursement_date,
        payment_entries=payment_entries,
        as_of=as_of,
        tz=tz,
        fine_observation_dates=fine_observation_dates,
        mora_rate_for_event=callback,
    )


# ------------------------------------------------------------------
# Statement builder
# ------------------------------------------------------------------


def build_statements(
    schedule: PaymentSchedule,
    due_dates: List[date],
    closing_dates: List[datetime],
    billing_cycle: BaseBillingCycle,
    settlements: List[Settlement],
    fines_applied: Dict[date, Money],
    principal: Money,
    base_mora_rate: InterestRate,
    tz: tzinfo,
    mora_rate_resolver: Optional[MoraRateResolver] = None,
) -> List[BillingCycleLoanStatement]:
    """Build one :class:`BillingCycleLoanStatement` per billing period.

    Walks closing dates, maps each to its schedule entry and
    settlements, and produces a statement showing expected vs actual
    activity for the period.
    """
    result: List[BillingCycleLoanStatement] = []
    running_balance = principal

    schedule_by_due: Dict[date, object] = {}
    for entry in schedule:
        schedule_by_due[entry.due_date] = entry

    settlement_by_date: Dict[date, List] = {}
    for s in settlements:
        key = to_date(s.payment_date, tz)
        settlement_by_date.setdefault(key, []).append(s)

    for idx, closing_date in enumerate(closing_dates):
        if idx >= len(due_dates):
            break

        dd = due_dates[idx]
        due_dt = billing_cycle.due_date_for(closing_date)
        entry = schedule_by_due.get(dd)

        expected_payment = entry.payment_amount if entry else Money.zero()
        expected_principal = entry.principal_payment if entry else Money.zero()
        expected_interest = entry.interest_payment if entry else Money.zero()

        mora_rate = resolve_mora_rate(
            due_dates,
            closing_dates,
            dd,
            base_mora_rate,
            mora_rate_resolver,
            tz,
        )

        fine_charged = fines_applied.get(dd, Money.zero())

        prev_closing = closing_dates[idx - 1] if idx > 0 else None
        payments_received = Money.zero()
        mora_charged = Money.zero()
        for s_list in settlement_by_date.values():
            for s in s_list:
                in_period = (prev_closing is None or s.payment_date > prev_closing) and s.payment_date <= closing_date
                if in_period:
                    payments_received = payments_received + s.payment_amount
                    mora_charged = mora_charged + s.mora_paid

        opening_balance = running_balance
        running_balance = running_balance - expected_principal
        if running_balance.is_negative():
            running_balance = Money.zero()

        result.append(
            BillingCycleLoanStatement(
                period_number=idx + 1,
                closing_date=closing_date,
                due_date=due_dt,
                opening_balance=opening_balance,
                expected_payment=expected_payment,
                expected_principal=expected_principal,
                expected_interest=expected_interest,
                mora_rate=mora_rate,
                mora_charged=mora_charged,
                fine_charged=fine_charged,
                payments_received=payments_received,
                closing_balance=running_balance,
            )
        )

    return result
