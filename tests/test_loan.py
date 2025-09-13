"""Tests for Loan class - following project patterns."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money


# Loan Creation Tests
def test_loan_creation_basic():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]

    loan = Loan(principal, rate, due_dates)
    assert loan.principal == principal
    assert loan.interest_rate == rate
    assert loan.due_dates == due_dates


def test_loan_creation_with_disbursement_date():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    assert loan.disbursement_date == disbursement_date


def test_loan_creation_default_disbursement_date():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    expected_disbursement = datetime(2024, 2, 1) - timedelta(days=30)
    assert loan.disbursement_date == expected_disbursement


def test_loan_creation_sorts_due_dates():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 3, 1), datetime(2024, 1, 1), datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    expected_sorted = [datetime(2024, 1, 1), datetime(2024, 2, 1), datetime(2024, 3, 1)]
    assert loan.due_dates == expected_sorted


# Loan Validation Tests
def test_loan_creation_empty_due_dates_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")

    with pytest.raises(ValueError, match="At least one due date is required"):
        Loan(principal, rate, [])


def test_loan_creation_zero_principal_raises_error():
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    with pytest.raises(ValueError, match="Principal must be positive"):
        Loan(Money.zero(), rate, due_dates)


def test_loan_creation_negative_principal_raises_error():
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    with pytest.raises(ValueError, match="Principal must be positive"):
        Loan(Money("-1000.00"), rate, due_dates)


# Loan State Tests
def test_loan_initial_current_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    assert loan.current_balance == principal


def test_loan_initial_not_paid_off():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    assert not loan.is_paid_off


# PMT Calculation Tests
def test_loan_calculate_payment_amount_single_payment():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    disbursement_date = datetime(2024, 1, 1)
    due_dates = [datetime(2024, 12, 31)]  # 365 days later

    loan = Loan(principal, rate, due_dates, disbursement_date)
    payment = loan.calculate_payment_amount()

    # Should be approximately 10000 * (1.05) = 10500
    assert payment > Money("10400.00")
    assert payment < Money("10600.00")


def test_loan_calculate_payment_amount_zero_interest():
    principal = Money("10000.00")
    rate = InterestRate("0% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]

    loan = Loan(principal, rate, due_dates)
    payment = loan.calculate_payment_amount()

    # Should be exactly principal / number of payments
    expected = Money("3333.33")  # 10000 / 3
    assert abs(payment.real_amount - expected.real_amount) < Decimal("0.01")


def test_loan_calculate_payment_amount_multiple_payments():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]

    loan = Loan(principal, rate, due_dates)
    payment = loan.calculate_payment_amount()

    # Should be reasonable payment amount
    assert payment > Money("3300.00")
    assert payment < Money("3400.00")


# Expected Cash Flow Tests
def test_loan_generate_expected_cash_flow_includes_disbursement():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    # Should have disbursement as first item
    disbursement_items = cash_flow.query.filter_by(category="disbursement").all()
    assert len(disbursement_items) == 1
    assert disbursement_items[0].amount == principal


def test_loan_generate_expected_cash_flow_has_payment_breakdown():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    # Should have interest and principal items (no separate payment item)
    interest_items = cash_flow.query.filter_by(category="interest").all()
    principal_items = cash_flow.query.filter_by(category="principal").all()

    assert len(interest_items) == 1
    assert len(principal_items) == 1


def test_loan_generate_expected_cash_flow_multiple_payments():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    # Should have 1 disbursement + 3 interest + 3 principal = 7 items
    assert len(cash_flow) == 7

    interest_items = cash_flow.query.filter_by(category="interest").all()
    principal_items = cash_flow.query.filter_by(category="principal").all()
    assert len(interest_items) == 3
    assert len(principal_items) == 3


def test_loan_generate_expected_cash_flow_net_zero():
    principal = Money("10000.00")
    rate = InterestRate("0% a")  # Zero interest for simplicity
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    # Net should be close to zero (disbursement + payments)
    net = cash_flow.net_present_value()
    assert abs(net.real_amount) < Decimal("0.01")


# Payment Recording Tests
def test_loan_record_payment_updates_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15))

    assert loan.current_balance == Money("5000.00")


def test_loan_record_payment_multiple_payments():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan.record_payment(Money("3000.00"), datetime(2024, 1, 15))
    loan.record_payment(Money("2000.00"), datetime(2024, 1, 20))

    assert loan.current_balance == Money("5000.00")


def test_loan_record_payment_overpayment_zeros_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan.record_payment(Money("15000.00"), datetime(2024, 1, 15))

    assert loan.current_balance == Money.zero()
    assert loan.is_paid_off


def test_loan_record_payment_negative_amount_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)

    with pytest.raises(ValueError, match="Payment amount must be positive"):
        loan.record_payment(Money("-1000.00"), datetime(2024, 1, 15))


# Actual Cash Flow Tests
def test_loan_get_actual_cash_flow_empty_initially():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    actual_cf = loan.get_actual_cash_flow()

    # Should only have disbursement
    assert len(actual_cf) == 1
    assert actual_cf[0].category == "disbursement"


def test_loan_get_actual_cash_flow_includes_payments():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15), "First payment")

    actual_cf = loan.get_actual_cash_flow()

    # Should have disbursement + 1 payment
    assert len(actual_cf) == 2

    payment_items = actual_cf.query.filter_by(category="actual_payment").all()
    assert len(payment_items) == 1
    assert payment_items[0].amount == Money("-5000.00")  # Outflow


# Remaining Cash Flow Tests
def test_loan_get_remaining_cash_flow_paid_off_loan():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan.record_payment(Money("15000.00"), datetime(2024, 1, 15))  # Overpay

    remaining_cf = loan.get_remaining_cash_flow()
    assert remaining_cf.is_empty()


def test_loan_get_remaining_cash_flow_partial_payment():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15))

    remaining_cf = loan.get_remaining_cash_flow()

    # Should have remaining payments (no disbursement)
    disbursement_items = remaining_cf.query.filter_by(category="disbursement").all()
    assert len(disbursement_items) == 0

    # Should have some payment items
    assert len(remaining_cf) > 0


# Amortization Schedule Tests
def test_loan_get_amortization_schedule_structure():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates)
    schedule = loan.get_amortization_schedule()

    assert len(schedule) == 2

    # Check first payment structure
    payment1 = schedule[0]
    required_keys = {
        "payment_number",
        "due_date",
        "days_in_period",
        "beginning_balance",
        "payment_amount",
        "principal_payment",
        "interest_payment",
        "ending_balance",
    }
    assert set(payment1.keys()) == required_keys


def test_loan_get_amortization_schedule_decreasing_balance():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates)
    schedule = loan.get_amortization_schedule()

    # Balance should decrease with each payment
    assert schedule[0]["beginning_balance"] > schedule[1]["beginning_balance"]
    assert schedule[1]["ending_balance"] < schedule[0]["beginning_balance"]


def test_loan_get_amortization_schedule_final_balance_zero():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates)
    schedule = loan.get_amortization_schedule()

    # Final balance should be zero or very close
    final_balance = schedule[-1]["ending_balance"]
    assert final_balance.real_amount < Decimal("0.01")


# String Representation Tests
def test_loan_string_representation():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan_str = str(loan)

    assert "10,000.00" in loan_str
    assert "5.000%" in loan_str
    assert "payments=1" in loan_str


def test_loan_repr_representation():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    loan_repr = repr(loan)

    assert "Loan(" in loan_repr
    assert "principal=Money(10000.00)" in loan_repr
    assert "2024, 2, 1" in loan_repr


# Edge Case Tests
def test_loan_single_payment_zero_interest():
    principal = Money("10000.00")
    rate = InterestRate("0% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    payment = loan.calculate_payment_amount()

    # Should equal principal exactly
    assert payment == principal


def test_loan_very_small_principal():
    principal = Money("0.01")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    # Should still generate valid cash flow
    assert len(cash_flow) > 0
    assert cash_flow.query.filter_by(category="disbursement").first().amount == principal


def test_loan_high_interest_rate():
    principal = Money("10000.00")
    rate = InterestRate("50% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    payment = loan.calculate_payment_amount()

    # Should be significantly higher than principal (50% annual for ~30 days)
    assert payment > Money("10300.00")


def test_loan_many_payments():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    # Create monthly payments for 2 years
    due_dates = [datetime(2024, 1, 1) + timedelta(days=30 * i) for i in range(1, 25)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    # Should have 1 disbursement + 24 * 2 (interest, principal) = 49 items
    assert len(cash_flow) == 49

    interest_items = cash_flow.query.filter_by(category="interest").all()
    principal_items = cash_flow.query.filter_by(category="principal").all()
    assert len(interest_items) == 24
    assert len(principal_items) == 24
