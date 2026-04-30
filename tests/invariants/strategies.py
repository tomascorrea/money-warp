"""Shared Hypothesis strategies and helpers for invariant tests."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypothesis import strategies as st

from money_warp import (
    InterestRate,
    InvertedPriceScheduler,
    Loan,
    Money,
    PriceScheduler,
)

DISBURSEMENT = datetime(2025, 1, 1, tzinfo=timezone.utc)

principal_st = st.decimals(min_value=1000, max_value=500_000, places=2)
annual_rate_st = st.decimals(min_value=1, max_value=50, places=1)
num_installments_st = st.integers(min_value=2, max_value=12)
payment_fraction_st = st.floats(min_value=0.05, max_value=1.0)
scheduler_st = st.sampled_from([PriceScheduler, InvertedPriceScheduler])
days_offset_st = st.integers(min_value=-25, max_value=90)


def build_loan(
    principal: Decimal,
    annual_rate: Decimal,
    num_installments: int,
    scheduler: type,
) -> Loan:
    due_dates = [(DISBURSEMENT + timedelta(days=30 * (i + 1))).date() for i in range(num_installments)]
    return Loan(
        Money(str(principal)),
        InterestRate(f"{annual_rate}% a"),
        due_dates,
        disbursement_date=DISBURSEMENT,
        scheduler=scheduler,
    )


def make_payment_amount(balance: Money, fraction: float) -> Money:
    raw = (balance.raw_amount * Decimal(str(fraction))).quantize(Decimal("0.01"))
    return Money(str(raw))
