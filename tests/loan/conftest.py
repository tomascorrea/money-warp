"""Shared fixtures for loan tests."""

from datetime import datetime

import pytest

from money_warp import InterestRate, Loan, Money


@pytest.fixture
def loan_with_all_installments_paid():
    """Create a 3-payment loan and pay every scheduled installment exactly."""
    principal = Money("1000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2025, 11, 1), datetime(2025, 12, 1), datetime(2026, 1, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 10, 2))

    schedule = loan.get_amortization_schedule()
    for entry in schedule:
        loan.record_payment(entry.payment_amount, entry.due_date)

    return loan, due_dates


@pytest.fixture
def partial_payment_loan():
    """Loan with a single partial payment recorded on the due date."""
    principal = Money("1000.00")
    rate = InterestRate("5% a")
    payment_date = datetime(2025, 11, 1)
    due_dates = [payment_date]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 10, 2))
    loan.record_payment(Money("500.00"), payment_date)

    return loan, principal, payment_date
