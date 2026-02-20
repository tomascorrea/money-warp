"""Tests for Loan late fees, grace periods, fine calculations, and payment allocation with fines."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money


def test_loan_creation_with_fine_parameters():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, late_fee_rate=Decimal("0.03"), grace_period_days=5)
    assert loan.late_fee_rate == Decimal("0.03")
    assert loan.grace_period_days == 5


def test_loan_creation_with_default_fine_parameters():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    assert loan.late_fee_rate == Decimal("0.02")  # Default 2%
    assert loan.grace_period_days == 0  # Default no grace period


def test_loan_creation_negative_fine_rate_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    with pytest.raises(ValueError, match="Late fee rate must be non-negative"):
        Loan(principal, rate, due_dates, late_fee_rate=Decimal("-0.01"))


def test_loan_creation_negative_grace_period_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    with pytest.raises(ValueError, match="Grace period days must be non-negative"):
        Loan(principal, rate, due_dates, grace_period_days=-1)


def test_loan_initial_fine_properties():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    assert loan.total_fines == Money.zero()
    assert loan.outstanding_fines == Money.zero()
    assert len(loan.fines_applied) == 0


def test_loan_get_expected_payment_amount_valid_date():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates)
    expected_payment = loan.get_expected_payment_amount(datetime(2024, 2, 1))
    assert expected_payment > Money.zero()


def test_loan_get_expected_payment_amount_invalid_date_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    with pytest.raises(ValueError, match="Due date .* is not in loan's due dates"):
        loan.get_expected_payment_amount(datetime(2024, 3, 1))


def test_loan_is_payment_late_within_grace_period():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, grace_period_days=5)
    check_date = datetime(2024, 2, 3)  # 2 days after due date, within grace period
    assert not loan.is_payment_late(datetime(2024, 2, 1), check_date)


def test_loan_is_payment_late_after_grace_period():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, grace_period_days=5)
    check_date = datetime(2024, 2, 7)  # 6 days after due date, past grace period
    assert loan.is_payment_late(datetime(2024, 2, 1), check_date)


def test_loan_is_payment_late_no_grace_period():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, grace_period_days=0)
    check_date = datetime(2024, 2, 2)  # 1 day after due date
    assert loan.is_payment_late(datetime(2024, 2, 1), check_date)


def test_loan_calculate_late_fines_applies_fine():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, late_fee_rate=Decimal("0.02"), grace_period_days=0)
    late_date = datetime(2024, 2, 5)  # 4 days late

    new_fines = loan.calculate_late_fines(late_date)
    assert new_fines > Money.zero()
    assert loan.total_fines == new_fines


def test_loan_calculate_late_fines_correct_amount():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, late_fee_rate=Decimal("0.05"))  # 5% fine
    expected_payment = loan.get_expected_payment_amount(datetime(2024, 2, 1))
    expected_fine = Money(expected_payment.raw_amount * Decimal("0.05"))

    loan.calculate_late_fines(datetime(2024, 2, 5))
    assert loan.total_fines == expected_fine


def test_loan_calculate_late_fines_only_once_per_due_date():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, late_fee_rate=Decimal("0.02"))

    # Apply fines twice for same due date
    first_fines = loan.calculate_late_fines(datetime(2024, 2, 5))
    second_fines = loan.calculate_late_fines(datetime(2024, 2, 10))

    assert first_fines > Money.zero()
    assert second_fines == Money.zero()  # No new fines applied


def test_loan_calculate_late_fines_multiple_due_dates():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates, late_fee_rate=Decimal("0.02"))

    # Both payments are late
    late_date = datetime(2024, 3, 5)
    new_fines = loan.calculate_late_fines(late_date)

    assert new_fines > Money.zero()
    assert len(loan.fines_applied) == 2  # Fines for both due dates


def test_loan_record_payment_allocates_to_fines_first():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, late_fee_rate=Decimal("0.02"))

    # Apply fines first
    loan.calculate_late_fines(datetime(2024, 2, 5))
    initial_fines = loan.outstanding_fines

    # Make payment smaller than fines
    payment_amount = Money(initial_fines.raw_amount / 2)
    loan.record_payment(payment_amount, datetime(2024, 2, 6))

    # Check that payment went to fines
    fine_payments = [p for p in loan._actual_payments if p.category == "actual_fine"]
    assert len(fine_payments) == 1
    assert fine_payments[0].amount == payment_amount


def test_loan_record_payment_allocates_fines_then_principal():
    principal = Money("1000.00")  # Smaller loan for easier testing
    rate = InterestRate("0% a")  # No interest for simplicity
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, late_fee_rate=Decimal("0.10"))  # 10% fine

    # Apply fines
    loan.calculate_late_fines(datetime(2024, 2, 5))
    total_fines = loan.outstanding_fines

    # Make payment that covers fines + some principal
    payment_amount = total_fines + Money("200")
    loan.record_payment(payment_amount, datetime(2024, 2, 6))

    # Check allocations
    fine_payments = [p for p in loan._actual_payments if p.category == "actual_fine"]
    principal_payments = [p for p in loan._actual_payments if p.category == "actual_principal"]

    assert len(fine_payments) == 1
    assert fine_payments[0].amount == total_fines
    assert len(principal_payments) == 1
    assert principal_payments[0].amount == Money("200")


def test_loan_current_balance_includes_outstanding_fines():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, late_fee_rate=Decimal("0.02"))
    initial_balance = loan.current_balance

    # Apply fines
    loan.calculate_late_fines(datetime(2024, 2, 5))
    balance_with_fines = loan.current_balance

    assert balance_with_fines > initial_balance
    assert balance_with_fines == initial_balance + loan.outstanding_fines


def test_loan_is_paid_off_considers_fines():
    principal = Money("1000.00")
    rate = InterestRate("0% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, late_fee_rate=Decimal("0.05"))

    # Make partial payment that doesn't cover full installment
    loan.record_payment(Money("500.00"), datetime(2024, 1, 31))
    assert not loan.is_paid_off  # Should not be paid off yet

    # Now apply fines for insufficient payment
    loan.calculate_late_fines(datetime(2024, 2, 5))

    # Should have fines and still not be paid off
    assert loan.outstanding_fines > Money.zero()
    assert not loan.is_paid_off  # Should not be paid off due to outstanding balance and fines


@pytest.mark.parametrize(
    "fine_rate,expected_multiplier",
    [
        (Decimal("0.01"), Decimal("0.01")),  # 1%
        (Decimal("0.05"), Decimal("0.05")),  # 5%
        (Decimal("0.10"), Decimal("0.10")),  # 10%
    ],
)
def test_loan_fine_calculation_with_different_rates(fine_rate, expected_multiplier):
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, late_fee_rate=fine_rate)
    expected_payment = loan.get_expected_payment_amount(datetime(2024, 2, 1))
    expected_fine = Money(expected_payment.raw_amount * expected_multiplier)

    loan.calculate_late_fines(datetime(2024, 2, 5))
    assert loan.total_fines == expected_fine


@pytest.mark.parametrize(
    "grace_days,check_day,should_be_late",
    [
        (0, 1, True),  # No grace, 1 day late
        (3, 2, False),  # 3-day grace, 2 days after due date
        (3, 4, True),  # 3-day grace, 4 days after due date
        (5, 5, False),  # 5-day grace, exactly at grace boundary
        (5, 6, True),  # 5-day grace, 1 day past grace
    ],
)
def test_loan_grace_period_scenarios(grace_days, check_day, should_be_late):
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_date = datetime(2024, 2, 1)
    due_dates = [due_date]

    loan = Loan(principal, rate, due_dates, grace_period_days=grace_days)
    check_date = due_date + timedelta(days=check_day)

    assert loan.is_payment_late(due_date, check_date) == should_be_late
