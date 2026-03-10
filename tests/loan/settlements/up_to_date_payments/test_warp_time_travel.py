"""Settlement tests for Warp time-travel visibility.

Scenario: pay the first installment on its due date, then warp backward
and forward to verify that settlements are only visible when now() >= payment_date.

Payment timeline:
  P1  R$303.62  Feb 01  (1st due date)

Warp targets:
  Jan 15  (past — before the payment)  → installment 1 is NOT paid
  Mar 01  (future — 2nd due date)      → installment 1 IS paid, allocation visible
"""

from datetime import datetime, timezone

import pytest

from money_warp import Money, Warp


@pytest.fixture
def loan_with_first_payment(three_installment_loan):
    """Pay the first installment at its due date, return the warp context."""
    schedule = three_installment_loan.get_original_schedule()
    with Warp(three_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(schedule[0].payment_amount)
        return w, settlement


# --- Warp to the past: Jan 15 ---


@pytest.fixture
def past_warp(loan_with_first_payment):
    """Warp back to Jan 15 — before the payment was made."""
    w, _ = loan_with_first_payment
    with Warp(w, datetime(2025, 1, 15, tzinfo=timezone.utc)) as w_past:
        return w_past


def test_past_no_settlements_visible(past_warp):
    assert len(past_warp.settlements) == 0


def test_past_principal_balance_unchanged(past_warp):
    assert past_warp.principal_balance == Money("890.22")


def test_past_first_installment_not_paid(past_warp):
    assert past_warp.installments[0].is_fully_paid is False


def test_past_first_installment_no_principal_paid(past_warp):
    assert past_warp.installments[0].principal_paid == Money("0.00")


def test_past_first_installment_no_interest_paid(past_warp):
    assert past_warp.installments[0].interest_paid == Money("0.00")


# --- Warp to the future: Mar 1 (2nd due date) ---


@pytest.fixture
def future_warp(loan_with_first_payment):
    """Warp forward to Mar 1 — the second installment's due date."""
    w, _ = loan_with_first_payment
    with Warp(w, datetime(2025, 3, 1, tzinfo=timezone.utc)) as w_future:
        return w_future


def test_future_one_settlement_visible(future_warp):
    assert len(future_warp.settlements) == 1


def test_future_principal_balance_after_first_payment(future_warp):
    assert future_warp.principal_balance == Money("597.23")


def test_future_first_installment_paid(future_warp):
    assert future_warp.installments[0].is_fully_paid is True


def test_future_first_installment_principal(future_warp):
    assert future_warp.installments[0].principal_paid == Money("292.99")


def test_future_first_installment_interest(future_warp):
    assert future_warp.installments[0].interest_paid == Money("10.63")


def test_future_second_installment_not_paid(future_warp):
    assert future_warp.installments[1].is_fully_paid is False


def test_future_third_installment_not_paid(future_warp):
    assert future_warp.installments[2].is_fully_paid is False
