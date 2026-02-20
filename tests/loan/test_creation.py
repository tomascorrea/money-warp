"""Tests for Loan creation, validation, defaults, and string representation."""

from datetime import datetime, timedelta

import pytest

from money_warp import InterestRate, Loan, Money, PriceScheduler


def test_loan_creation_basic():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]

    loan = Loan(principal, rate, due_dates)
    assert loan.principal == principal
    assert loan.interest_rate == rate
    assert loan.due_dates == due_dates
    assert loan.scheduler == PriceScheduler  # Default scheduler


def test_loan_creation_with_disbursement_date():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    assert loan.disbursement_date == disbursement_date


def test_loan_creation_with_custom_scheduler():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, scheduler=PriceScheduler)
    assert loan.scheduler == PriceScheduler


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


def test_loan_initial_not_paid_off():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    assert not loan.is_paid_off


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
