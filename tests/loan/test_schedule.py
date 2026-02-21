"""Tests for Loan amortization schedule generation and edge cases."""

from datetime import datetime, timedelta

from money_warp import InterestRate, Loan, Money


def test_loan_get_amortization_schedule_structure():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    schedule = loan.get_amortization_schedule()

    assert len(schedule) == 2
    assert schedule.total_payments > Money.zero()
    assert schedule.total_interest > Money.zero()
    assert schedule.total_principal == principal


def test_loan_get_amortization_schedule_entries():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    schedule = loan.get_amortization_schedule()

    entry = schedule[0]
    assert entry.payment_number == 1
    assert entry.due_date == datetime(2024, 2, 1)
    assert entry.beginning_balance == principal
    assert entry.payment_amount > Money.zero()
    assert entry.principal_payment > Money.zero()
    assert entry.interest_payment >= Money.zero()
    assert entry.ending_balance == Money.zero()


def test_loan_single_payment_zero_interest():
    principal = Money("10000.00")
    rate = InterestRate("0% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    schedule = loan.get_amortization_schedule()

    # Should equal principal exactly
    assert schedule[0].payment_amount == principal
    assert schedule[0].interest_payment == Money.zero()


def test_loan_very_small_principal():
    principal = Money("0.01")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    cash_flow = loan.generate_expected_cash_flow()

    # Should still generate valid cash flow
    assert len(cash_flow) > 0


def test_loan_high_interest_rate():
    principal = Money("10000.00")
    rate = InterestRate("50% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    schedule = loan.get_amortization_schedule()

    # Should be significantly higher than principal (50% annual for ~30 days)
    payment = schedule[0].payment_amount
    assert payment > Money("10300.00")


def test_loan_many_payments():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    # Create monthly payments for 2 years
    due_dates = [datetime(2024, 1, 1) + timedelta(days=30 * i) for i in range(1, 25)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    cash_flow = loan.generate_expected_cash_flow()

    # Should have 1 disbursement + 24 * 2 (interest, principal) = 49 items
    assert len(cash_flow) == 49

    interest_items = cash_flow.query.filter_by(category="expected_interest").all()
    principal_items = cash_flow.query.filter_by(category="expected_principal").all()
    assert len(interest_items) == 24
    assert len(principal_items) == 24
