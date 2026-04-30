"""Property-based tests for balance invariants.

These invariants must hold for any loan, any payment amounts, and any timing:

3. Principal balance is never negative after payments.
5. Every installment's balance is nonneg; is_fully_paid implies balance == 0.
"""

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from money_warp import Warp

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


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
    payment_days=st.lists(
        st.integers(min_value=20, max_value=400),
        min_size=1,
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
def test_principal_balance_never_negative(principal, annual_rate, num_installments, scheduler, payment_days, fractions):
    """After any sequence of payments, principal balance is never negative."""
    loan = build_loan(principal, annual_rate, num_installments, scheduler)

    for i, day_offset in enumerate(payment_days):
        pay_dt = DISBURSEMENT + timedelta(days=day_offset)

        with Warp(loan, pay_dt) as warped:
            balance = warped.current_balance
            if balance.is_zero() or balance.is_negative():
                break
            amount = make_payment_amount(balance, fractions[i])
            if amount.is_zero() or amount.is_negative():
                continue
            warped.pay_installment(amount)

            assert not warped.principal_balance.is_negative(), (
                f"Principal balance went negative ({warped.principal_balance}) "
                f"after payment of {amount} on day {day_offset}"
            )
        loan = warped


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
    payment_fraction=payment_fraction_st,
    days_offset=st.integers(min_value=-25, max_value=90),
)
@settings(max_examples=200)
def test_installment_balance_nonneg_and_consistency(
    principal, annual_rate, num_installments, scheduler, payment_fraction, days_offset
):
    """Every installment balance is nonneg; is_fully_paid implies balance == 0."""
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
        warped.pay_installment(amount)

        for inst in warped.installments:
            assert not inst.balance.is_negative(), f"Installment #{inst.number} has negative balance: {inst.balance}"
            if inst.is_fully_paid:
                assert (
                    inst.balance.is_zero()
                ), f"Installment #{inst.number} is_fully_paid=True but balance={inst.balance}"
