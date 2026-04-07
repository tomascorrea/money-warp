"""Tests for BillingCycleLoan amortization schedule."""

from money_warp import Money


def test_original_schedule_payment_amounts(simple_loan):
    schedule = simple_loan.get_original_schedule()
    assert schedule[0].payment_amount == Money("1022.58")
    assert schedule[1].payment_amount == Money("1022.58")
    assert schedule[2].payment_amount == Money("1022.58")


def test_original_schedule_principal_interest_split(simple_loan):
    schedule = simple_loan.get_original_schedule()
    assert schedule[0].principal_payment == Money("983.20")
    assert schedule[0].interest_payment == Money("39.38")
    assert schedule[1].principal_payment == Money("1003.07")
    assert schedule[1].interest_payment == Money("19.51")
    assert schedule[2].principal_payment == Money("1013.73")
    assert schedule[2].interest_payment == Money("8.85")


def test_original_schedule_ending_balance(simple_loan):
    schedule = simple_loan.get_original_schedule()
    assert schedule[0].ending_balance == Money("2016.80")
    assert schedule[1].ending_balance == Money("1013.73")
    assert schedule[2].ending_balance == Money("0.00")
