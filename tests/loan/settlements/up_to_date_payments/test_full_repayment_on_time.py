"""Settlement tests for paying all installments exactly on their due dates.

Scenario: 3 payments matching the scheduled amounts, each on the due date.
This is the "golden path" — no fines, no mora, interest matches the
original schedule exactly, and every installment is fully covered.

Payment timeline:
  P1  R$303.62  Feb 01  (1st due date)
  P2  R$303.62  Mar 01  (2nd due date)
  P3  R$303.63  Apr 01  (3rd due date)
"""

from datetime import datetime, timezone

import pytest

from money_warp import Money, Warp


@pytest.fixture
def on_time_full_repayment(three_installment_loan):
    """Pay each installment at its due date for the scheduled amount."""
    schedule = three_installment_loan.get_original_schedule()
    with Warp(three_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w1:
        s1 = w1.pay_installment(schedule[0].payment_amount)
        with Warp(w1, datetime(2025, 3, 1, tzinfo=timezone.utc)) as w2:
            s2 = w2.pay_installment(schedule[1].payment_amount)
            with Warp(w2, datetime(2025, 4, 1, tzinfo=timezone.utc)) as w3:
                s3 = w3.pay_installment(schedule[2].payment_amount)
                return w3, [s1, s2, s3]


# --- No fines or mora in any payment ---


@pytest.mark.parametrize("payment_index", [0, 1, 2])
def test_on_time_no_fines(on_time_full_repayment, payment_index):
    _, settlements = on_time_full_repayment
    assert settlements[payment_index].fine_paid == Money("0.00")


@pytest.mark.parametrize("payment_index", [0, 1, 2])
def test_on_time_no_mora(on_time_full_repayment, payment_index):
    _, settlements = on_time_full_repayment
    assert settlements[payment_index].mora_paid == Money("0.00")


# --- Each payment touches exactly one installment ---


@pytest.mark.parametrize("payment_index", [0, 1, 2])
def test_on_time_single_allocation(on_time_full_repayment, payment_index):
    """Each scheduled payment maps to exactly one installment."""
    _, settlements = on_time_full_repayment
    assert len(settlements[payment_index].allocations) == 1


# --- Payment 1: Feb 1 ---


def test_p1_interest(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[0].interest_paid == Money("10.63")


def test_p1_principal(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[0].principal_paid == Money("292.99")


def test_p1_remaining_balance(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[0].remaining_balance == Money("597.23")


def test_p1_installment_covered(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[0].allocations[0].is_fully_covered is True


# --- Payment 2: Mar 1 ---


def test_p2_interest(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[1].interest_paid == Money("6.44")


def test_p2_principal(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[1].principal_paid == Money("297.18")


def test_p2_remaining_balance(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[1].remaining_balance == Money("300.05")


def test_p2_installment_covered(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[1].allocations[0].is_fully_covered is True


# --- Payment 3: Apr 1 ---


def test_p3_interest(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[2].interest_paid == Money("3.58")


def test_p3_principal(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[2].principal_paid == Money("300.05")


def test_p3_remaining_balance(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[2].remaining_balance == Money("0.00")


def test_p3_installment_covered(on_time_full_repayment):
    _, settlements = on_time_full_repayment
    assert settlements[2].allocations[0].is_fully_covered is True


# --- Final state: all installments paid ---


@pytest.mark.parametrize("installment_index", [0, 1, 2])
def test_all_installments_fully_paid(on_time_full_repayment, installment_index):
    loan, _ = on_time_full_repayment
    assert loan.installments[installment_index].is_fully_paid is True


def test_final_balance_zero(on_time_full_repayment):
    loan, _ = on_time_full_repayment
    assert loan.principal_balance == Money("0.00")
