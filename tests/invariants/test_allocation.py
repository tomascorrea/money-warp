"""Property-based tests for allocation invariants.

These invariants must hold for any payment on any loan:

4. All settlement components (fine, mora, interest, principal) are nonneg.
   Components sum exactly to the payment amount.
"""

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from money_warp import Settlement, Warp

from strategies import (
    DISBURSEMENT,
    annual_rate_st,
    build_loan,
    make_payment_amount,
    num_installments_st,
    payment_fraction_st,
    principal_st,
    scheduler_st,
)


def _assert_components_nonneg(settlement: Settlement) -> None:
    """All four payment components must be nonnegative."""
    assert not settlement.fine_paid.is_negative(), f"fine_paid is negative: {settlement.fine_paid}"
    assert not settlement.mora_paid.is_negative(), f"mora_paid is negative: {settlement.mora_paid}"
    assert not settlement.interest_paid.is_negative(), f"interest_paid is negative: {settlement.interest_paid}"
    assert not settlement.principal_paid.is_negative(), f"principal_paid is negative: {settlement.principal_paid}"


def _assert_components_sum_to_payment(settlement: Settlement) -> None:
    """Components must sum exactly to the payment amount."""
    assert (
        settlement.total_paid == settlement.payment_amount
    ), f"Component sum {settlement.total_paid} != payment {settlement.payment_amount}"


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
    payment_fraction=payment_fraction_st,
    days_offset=st.integers(min_value=-25, max_value=90),
)
@settings(max_examples=200)
def test_single_payment_components_nonneg_and_sum(
    principal, annual_rate, num_installments, scheduler, payment_fraction, days_offset
):
    """Single payment: all components nonneg and sum to payment amount."""
    loan = build_loan(principal, annual_rate, num_installments, scheduler)
    due_date_dt = datetime(
        loan.due_dates[0].year,
        loan.due_dates[0].month,
        loan.due_dates[0].day,
        tzinfo=timezone.utc,
    )
    pay_dt = due_date_dt + timedelta(days=days_offset)
    if pay_dt <= DISBURSEMENT:
        return

    with Warp(loan, pay_dt) as warped:
        amount = make_payment_amount(warped.current_balance, payment_fraction)
        if amount.is_zero() or amount.is_negative():
            return
        settlement = warped.pay_installment(amount)

    _assert_components_nonneg(settlement)
    _assert_components_sum_to_payment(settlement)


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
        st.floats(min_value=0.10, max_value=1.0),
        min_size=5,
        max_size=5,
    ),
)
@settings(max_examples=200)
def test_multiple_payments_all_components_nonneg_and_sum(
    principal, annual_rate, num_installments, scheduler, payment_days, fractions
):
    """Multiple payments: every settlement has nonneg components that sum correctly."""
    loan = build_loan(principal, annual_rate, num_installments, scheduler)

    all_settlements = []
    for i, day_offset in enumerate(payment_days):
        pay_dt = DISBURSEMENT + timedelta(days=day_offset)

        with Warp(loan, pay_dt) as warped:
            balance = warped.current_balance
            if balance.is_zero() or balance.is_negative():
                break
            amount = make_payment_amount(balance, fractions[i])
            if amount.is_zero() or amount.is_negative():
                continue
            all_settlements.append(warped.pay_installment(amount))
        loan = warped

    for settlement in all_settlements:
        _assert_components_nonneg(settlement)
        _assert_components_sum_to_payment(settlement)
