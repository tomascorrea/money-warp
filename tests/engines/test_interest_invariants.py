"""Property-based tests for interest, mora, and coverage invariants.

6. Interest monotonicity: more days of accrual produces more interest.
7. Covered due date count never decreases as payments are made.
8. Mora is zero when payment is on or before the due date.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from money_warp import (
    InterestRate,
    InvertedPriceScheduler,
    Loan,
    Money,
    PriceScheduler,
    Warp,
)

DISBURSEMENT = datetime(2025, 1, 1, tzinfo=timezone.utc)

principal_st = st.decimals(min_value=1000, max_value=500_000, places=2)
annual_rate_st = st.decimals(min_value=1, max_value=50, places=1)
num_installments_st = st.integers(min_value=2, max_value=12)
payment_fraction_st = st.floats(min_value=0.05, max_value=1.0)
scheduler_st = st.sampled_from([PriceScheduler, InvertedPriceScheduler])


def _build_loan(principal: Decimal, annual_rate: Decimal, num_installments: int, scheduler: type) -> Loan:
    due_dates = [(DISBURSEMENT + timedelta(days=30 * (i + 1))).date() for i in range(num_installments)]
    return Loan(
        Money(str(principal)),
        InterestRate(f"{annual_rate}% a"),
        due_dates,
        disbursement_date=DISBURSEMENT,
        scheduler=scheduler,
    )


def _make_payment_amount(balance: Money, fraction: float) -> Money:
    raw = (balance.raw_amount * Decimal(str(fraction))).quantize(Decimal("0.01"))
    return Money(str(raw))


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
    assert not interest.is_negative(), (
        f"Interest should be nonneg but got {interest} " f"for principal={principal}, rate={annual_rate}%, days={days}"
    )


# ── Invariant 7: Covered due date count monotone ────────────────────


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=st.integers(min_value=2, max_value=8),
    scheduler=scheduler_st,
    payment_days=st.lists(
        st.integers(min_value=20, max_value=400),
        min_size=2,
        max_size=5,
        unique=True,
    ).map(sorted),
    fractions=st.lists(
        st.floats(min_value=0.20, max_value=1.0),
        min_size=5,
        max_size=5,
    ),
)
@settings(max_examples=200)
def test_covered_due_date_count_never_decreases(
    principal, annual_rate, num_installments, scheduler, payment_days, fractions
):
    """As payments are made, the count of covered due dates never goes down."""
    loan = _build_loan(principal, annual_rate, num_installments, scheduler)
    prev_covered = 0

    for i, day_offset in enumerate(payment_days):
        pay_dt = DISBURSEMENT + timedelta(days=day_offset)

        with Warp(loan, pay_dt) as warped:
            balance = warped.current_balance
            if balance.is_zero() or balance.is_negative():
                break
            amount = _make_payment_amount(balance, fractions[i])
            if amount.is_zero() or amount.is_negative():
                continue
            warped.pay_installment(amount)
            covered = warped._covered_due_date_count()

            assert covered >= prev_covered, (
                f"Covered count decreased from {prev_covered} to {covered} "
                f"after payment of {amount} on day {day_offset}"
            )
            prev_covered = covered
        loan = warped


# ── Invariant 8: Mora only after due date ───────────────────────────


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
    loan = _build_loan(principal, annual_rate, num_installments, scheduler)
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
        amount = _make_payment_amount(warped.current_balance, payment_fraction)
        if amount.is_zero() or amount.is_negative():
            return
        settlement = warped.pay_installment(amount)

    assert settlement.mora_paid.is_zero(), (
        f"Mora should be zero for payment on/before due date "
        f"but got {settlement.mora_paid} "
        f"(paid {days_early} days early)"
    )
