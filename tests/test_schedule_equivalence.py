"""Property-based test: Loan and BillingCycleLoan must produce identical schedules.

Both classes delegate to BaseScheduler.generate_schedule() with the same
(principal, interest_rate, due_dates, disbursement_date, tz) tuple.  When a
Loan is built with the due_dates that a BillingCycleLoan derives, the
resulting PaymentSchedule objects must be equal entry-by-entry.
"""

from datetime import datetime, timezone
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from money_warp import (
    BaseScheduler,
    BillingCycleLoan,
    InterestRate,
    InvertedPriceScheduler,
    Loan,
    Money,
    MonthlyBillingCycle,
    PriceScheduler,
)

DISBURSEMENT = datetime(2025, 1, 1, tzinfo=timezone.utc)
START_DATE = datetime(2025, 1, 1, tzinfo=timezone.utc)

principal_st = st.decimals(min_value=1000, max_value=500_000, places=2)
annual_rate_st = st.decimals(min_value=1, max_value=50, places=1)
num_installments_st = st.integers(min_value=1, max_value=12)
closing_day_st = st.integers(min_value=1, max_value=28)
payment_due_days_st = st.integers(min_value=1, max_value=28)
scheduler_st = st.sampled_from([PriceScheduler, InvertedPriceScheduler])


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    closing_day=closing_day_st,
    payment_due_days=payment_due_days_st,
    scheduler=scheduler_st,
)
@settings(max_examples=200)
def test_loan_and_billing_cycle_loan_schedules_are_equal(
    principal: Decimal,
    annual_rate: Decimal,
    num_installments: int,
    closing_day: int,
    payment_due_days: int,
    scheduler: type[BaseScheduler],
) -> None:
    """Schedules produced by Loan and BillingCycleLoan must be identical."""
    billing_cycle = MonthlyBillingCycle(
        closing_day=closing_day,
        payment_due_days=payment_due_days,
    )
    rate = InterestRate(f"{annual_rate}% a")
    amount = Money(str(principal))

    bcl = BillingCycleLoan(
        principal=amount,
        interest_rate=rate,
        billing_cycle=billing_cycle,
        start_date=START_DATE,
        num_installments=num_installments,
        disbursement_date=DISBURSEMENT,
        scheduler=scheduler,
    )

    loan = Loan(
        principal=amount,
        interest_rate=rate,
        due_dates=bcl.due_dates,
        disbursement_date=DISBURSEMENT,
        scheduler=scheduler,
    )

    assert bcl.get_original_schedule() == loan.get_original_schedule()
