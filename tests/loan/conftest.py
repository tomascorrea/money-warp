"""Shared fixtures for loan tests."""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money


@pytest.fixture
def loan_with_all_installments_paid():
    """Create a 3-payment loan and pay every scheduled installment exactly."""
    principal = Money("1000.00")
    rate = InterestRate("5% a")
    due_dates = [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
    ]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 10, 2, tzinfo=timezone.utc))

    schedule = loan.get_original_schedule()
    for entry in schedule:
        payment_dt = datetime(
            entry.due_date.year,
            entry.due_date.month,
            entry.due_date.day,
            tzinfo=timezone.utc,
        )
        loan.record_payment(entry.payment_amount, payment_dt)

    return loan, due_dates


@pytest.fixture
def partial_payment_loan():
    """Loan with a single partial payment recorded on the due date."""
    principal = Money("1000.00")
    rate = InterestRate("5% a")
    payment_date = datetime(2025, 11, 1, tzinfo=timezone.utc)
    due_dates = [payment_date.date()]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 10, 2, tzinfo=timezone.utc))
    loan.record_payment(Money("500.00"), payment_date)

    return loan, principal, payment_date
