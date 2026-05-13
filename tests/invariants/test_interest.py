"""Property-based tests for interest and mora invariants.

6. Interest monotonicity: more days of accrual produces more interest.
7. Mora is zero when payment is on or before the due date.
"""

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from money_warp import InterestRate, Money, Warp

from .strategies import (
    DISBURSEMENT,
    annual_rate_st,
    build_loan,
    make_payment_amount,
    num_installments_st,
    payment_fraction_st,
    principal_st,
    scheduler_st,
)


# ── Invariant 6: Interest monotonicity ──────────────────────────────


@given(
    principal=st.decimals(min_value=100, max_value=500_000, places=2),
    annual_rate=st.decimals(min_value=1, max_value=50, places=1),
    days=st.integers(min_value=1, max_value=365),
)
@settings(max_examples=200)
def test_interest_increases_with_more_days(principal, annual_rate, days):
    """Accruing interest for N+1 days produces strictly more than N days."""
    rate = InterestRate(f"{annual_rate}% a")
    p = Money(str(principal))

    interest_n = rate.accrue(p, days)
    interest_n1 = rate.accrue(p, days + 1)

    assert interest_n1.raw_amount > interest_n.raw_amount, (
        f"Interest for {days + 1} days ({interest_n1.raw_amount}) should exceed "
        f"interest for {days} days ({interest_n.raw_amount})"
    )


@given(
    principal=st.decimals(min_value=100, max_value=500_000, places=2),
    annual_rate=st.decimals(min_value=1, max_value=50, places=1),
    days=st.integers(min_value=1, max_value=365),
)
@settings(max_examples=200)
def test_interest_is_nonnegative(principal, annual_rate, days):
    """Interest accrued is always nonnegative for positive principal and rate."""
    rate = InterestRate(f"{annual_rate}% a")
    p = Money(str(principal))

    interest = rate.accrue(p, days)
    assert (
        not interest.is_negative()
    ), f"Interest should be nonneg but got {interest} for principal={principal}, rate={annual_rate}%, days={days}"


# ── Invariant 7: Mora only after due date ───────────────────────────


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
    payment_fraction=payment_fraction_st,
    days_early=st.integers(min_value=0, max_value=25),
)
@settings(max_examples=200)
def test_mora_is_zero_when_paying_on_or_before_due_date(
    principal, annual_rate, num_installments, scheduler, payment_fraction, days_early
):
    """Paying on or before the due date produces zero mora."""
    loan = build_loan(principal, annual_rate, num_installments, scheduler)
    due_date_dt = datetime(
        loan.due_dates[0].year,
        loan.due_dates[0].month,
        loan.due_dates[0].day,
        tzinfo=timezone.utc,
    )
    pay_dt = due_date_dt - timedelta(days=days_early)
    if pay_dt <= DISBURSEMENT:
        return

    with Warp(loan, pay_dt) as warped:
        amount = make_payment_amount(warped.current_balance, payment_fraction)
        if amount.is_zero() or amount.is_negative():
            return
        settlement = warped.pay_installment(amount)

    assert settlement.mora_paid.is_zero(), (
        "Mora should be zero for payment on/before due date "
        f"but got {settlement.mora_paid} "
        f"(paid {days_early} days early)"
    )
