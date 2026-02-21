"""Tests for Loan creation, validation, defaults, and string representation."""

from datetime import datetime

import pytest

from money_warp import InterestRate, Loan, Money, PriceScheduler


def test_loan_creation_basic():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
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

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1), scheduler=PriceScheduler)
    assert loan.scheduler == PriceScheduler


def test_loan_creation_default_disbursement_date():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    # Use a future first due date so default "now" is before it (validation requires disbursement < first due)
    due_dates = [datetime(2030, 2, 1)]

    t_before = datetime.now()
    loan = Loan(principal, rate, due_dates)
    t_after = datetime.now()

    assert t_before <= loan.disbursement_date <= t_after


def test_loan_creation_sorts_due_dates():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 3, 1), datetime(2024, 1, 1), datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2023, 12, 1))
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


def test_loan_creation_disbursement_on_or_after_first_due_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    with pytest.raises(ValueError, match="disbursement_date must be before the first due date"):
        Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 2, 1))

    with pytest.raises(ValueError, match="disbursement_date must be before the first due date"):
        Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 3, 1))


def test_loan_initial_not_paid_off():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    assert not loan.is_paid_off


def test_loan_string_representation():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
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
