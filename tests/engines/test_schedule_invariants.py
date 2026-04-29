"""Property-based tests for payment schedule invariants.

These invariants must hold for any principal, interest rate, number of
installments, and scheduler type:

1. Schedule amortization: principal payments sum to the loan principal,
   and the last entry ends at zero balance.
2. Per-row balance identity: beginning_balance - principal = ending_balance,
   and payment = principal + interest for every row.
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
)
from money_warp.engines.constants import BALANCE_TOLERANCE

DISBURSEMENT = datetime(2025, 1, 1, tzinfo=timezone.utc)

principal_st = st.decimals(min_value=1000, max_value=500_000, places=2)
annual_rate_st = st.decimals(min_value=1, max_value=50, places=1)
num_installments_st = st.integers(min_value=1, max_value=12)
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


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
)
@settings(max_examples=200)
def test_schedule_principal_sums_to_loan_principal(principal, annual_rate, num_installments, scheduler):
    """Sum of all principal payments equals the original loan principal."""
    loan = _build_loan(principal, annual_rate, num_installments, scheduler)
    schedule = loan.get_original_schedule()

    assert schedule.total_principal + BALANCE_TOLERANCE >= loan.principal
    assert loan.principal + BALANCE_TOLERANCE >= schedule.total_principal


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
)
@settings(max_examples=200)
def test_schedule_last_entry_ends_at_zero(principal, annual_rate, num_installments, scheduler):
    """The last schedule entry has an ending balance at or near zero."""
    loan = _build_loan(principal, annual_rate, num_installments, scheduler)
    schedule = loan.get_original_schedule()
    last = schedule.entries[-1]

    assert (
        last.ending_balance <= BALANCE_TOLERANCE
    ), f"Last entry ending_balance={last.ending_balance} exceeds tolerance"


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
)
@settings(max_examples=200)
def test_per_row_balance_identity(principal, annual_rate, num_installments, scheduler):
    """For every row: beginning_balance - principal_payment == ending_balance."""
    loan = _build_loan(principal, annual_rate, num_installments, scheduler)
    schedule = loan.get_original_schedule()

    for entry in schedule:
        expected_ending = entry.beginning_balance - entry.principal_payment
        diff = abs(expected_ending.raw_amount - entry.ending_balance.raw_amount)
        assert diff <= BALANCE_TOLERANCE.raw_amount, (
            f"Row {entry.payment_number}: "
            f"{entry.beginning_balance} - {entry.principal_payment} = {expected_ending}, "
            f"but ending_balance={entry.ending_balance}"
        )


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
)
@settings(max_examples=200)
def test_per_row_payment_equals_principal_plus_interest(principal, annual_rate, num_installments, scheduler):
    """For every row: payment_amount == principal_payment + interest_payment."""
    loan = _build_loan(principal, annual_rate, num_installments, scheduler)
    schedule = loan.get_original_schedule()

    for entry in schedule:
        expected_payment = entry.principal_payment + entry.interest_payment
        diff = abs(expected_payment.raw_amount - entry.payment_amount.raw_amount)
        assert diff <= BALANCE_TOLERANCE.raw_amount, (
            f"Row {entry.payment_number}: "
            f"principal({entry.principal_payment}) + interest({entry.interest_payment}) = {expected_payment}, "
            f"but payment_amount={entry.payment_amount}"
        )
