"""Tests for Loan expected and actual cash flow generation."""

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


def test_loan_get_actual_cash_flow_empty_initially():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [date(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    actual_cf = loan.get_actual_cash_flow()

    # Should have disbursement + expected payments, but no actual (happened) payments yet
    disbursement_items = actual_cf.query.filter_by(category="disbursement").all()
    happened_interest = actual_cf.query.happened.filter_by(category="interest").all()

    assert len(disbursement_items) == 1
    assert len(happened_interest) == 0


def test_loan_get_actual_cash_flow_includes_payments():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [date(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15, tzinfo=timezone.utc), description="First payment")

    actual_cf = loan.get_actual_cash_flow()

    # Should have expected payments + actual (happened) payments
    happened_interest = actual_cf.query.happened.filter_by(category="interest").all()
    happened_principal = actual_cf.query.happened.filter_by(category="principal").all()

    assert len(happened_interest) >= 1
    assert len(happened_principal) >= 1


def test_loan_get_actual_cash_flow_includes_fines():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [date(2024, 2, 1)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
        grace_period_days=3,
    )

    # Apply fines and make payment
    loan.calculate_late_fines(datetime(2024, 2, 10, tzinfo=timezone.utc))
    loan.record_payment(Money("500"), datetime(2024, 2, 11, tzinfo=timezone.utc))

    actual_cf = loan.get_actual_cash_flow()

    fine_items = actual_cf.query.filter_by(category="fine").all()
    fine_applied_items = [i for i in fine_items if i.is_inflow()]
    fine_payment_items = [i for i in fine_items if i.is_outflow()]

    assert len(fine_applied_items) == 1
    assert len(fine_payment_items) >= 1
