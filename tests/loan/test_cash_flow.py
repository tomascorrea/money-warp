"""Tests for Loan expected and actual cash flow generation."""

from datetime import datetime
from decimal import Decimal

from money_warp import InterestRate, Loan, Money


def test_loan_generate_expected_cash_flow_includes_disbursement():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    cash_flow = loan.generate_expected_cash_flow()

    disbursement_items = cash_flow.query.filter_by(category="expected_disbursement").all()
    assert len(disbursement_items) == 1
    assert disbursement_items[0].amount == principal


def test_loan_generate_expected_cash_flow_has_payment_breakdown():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    cash_flow = loan.generate_expected_cash_flow()

    interest_items = cash_flow.query.filter_by(category="expected_interest").all()
    principal_items = cash_flow.query.filter_by(category="expected_principal").all()

    assert len(interest_items) == 1
    assert len(principal_items) == 1


def test_loan_generate_expected_cash_flow_multiple_payments():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    cash_flow = loan.generate_expected_cash_flow()

    # Should have 1 disbursement + 3 interest + 3 principal = 7 items
    assert len(cash_flow) == 7

    interest_items = cash_flow.query.filter_by(category="expected_interest").all()
    principal_items = cash_flow.query.filter_by(category="expected_principal").all()
    assert len(interest_items) == 3
    assert len(principal_items) == 3


def test_loan_generate_expected_cash_flow_net_zero():
    principal = Money("10000.00")
    rate = InterestRate("0% a")  # Zero interest for simplicity
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    cash_flow = loan.generate_expected_cash_flow()

    # Net should be close to zero (disbursement + payments)
    net = cash_flow.net_present_value()
    assert abs(net.real_amount) < Decimal("0.01")


def test_loan_get_actual_cash_flow_empty_initially():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    actual_cf = loan.get_actual_cash_flow()

    # Should have disbursement + expected payments, but no actual payments yet
    disbursement_items = actual_cf.query.filter_by(category="expected_disbursement").all()
    actual_payment_items = actual_cf.query.filter_by(category="actual_interest").all()

    assert len(disbursement_items) == 1
    assert len(actual_payment_items) == 0


def test_loan_get_actual_cash_flow_includes_payments():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15), description="First payment")

    actual_cf = loan.get_actual_cash_flow()

    # Should have expected payments + actual payments
    actual_interest_items = actual_cf.query.filter_by(category="actual_interest").all()
    actual_principal_items = actual_cf.query.filter_by(category="actual_principal").all()

    assert len(actual_interest_items) >= 1
    assert len(actual_principal_items) >= 1


def test_loan_get_actual_cash_flow_includes_fines():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1),
        fine_rate=Decimal("0.02"),
        grace_period_days=3,
    )

    # Apply fines and make payment
    loan.calculate_late_fines(datetime(2024, 2, 10))
    loan.record_payment(Money("500"), datetime(2024, 2, 11))

    actual_cf = loan.get_actual_cash_flow()

    # Check for fine application and fine payment items
    fine_applied_items = actual_cf.query.filter_by(category="fine_applied").all()
    fine_payment_items = actual_cf.query.filter_by(category="actual_fine").all()

    assert len(fine_applied_items) == 1
    assert len(fine_payment_items) >= 1
