"""Tests for Loan expected cash flow generation."""

from datetime import date, datetime, timezone
from decimal import Decimal

from money_warp import InterestRate, Loan, Money


def test_loan_generate_expected_cash_flow_includes_disbursement():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [date(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    cash_flow = loan.generate_expected_cash_flow()

    disbursement_items = cash_flow.query.filter_by(category="disbursement").all()
    assert len(disbursement_items) == 1
    assert disbursement_items[0].amount == principal


def test_loan_generate_expected_cash_flow_has_payment_breakdown():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [date(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    cash_flow = loan.generate_expected_cash_flow()

    interest_items = cash_flow.query.filter_by(category="interest").all()
    principal_items = cash_flow.query.filter_by(category="principal").all()

    assert len(interest_items) == 1
    assert len(principal_items) == 1


def test_loan_generate_expected_cash_flow_multiple_payments():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [
        date(2024, 2, 1),
        date(2024, 3, 1),
        date(2024, 4, 1),
    ]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
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
    due_dates = [date(2024, 2, 1), date(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    cash_flow = loan.generate_expected_cash_flow()

    # Net should be close to zero (disbursement + payments)
    net = cash_flow.net_present_value()
    assert abs(net.real_amount) < Decimal("0.01")
