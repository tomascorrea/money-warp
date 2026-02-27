"""Tests for Warp time machine context manager."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from money_warp import InterestRate, InvalidDateError, Loan, Money, NestedWarpError, Warp


@pytest.fixture
def sample_loan():
    """Create a sample loan for testing."""
    principal = Money("10000.00")
    interest_rate = InterestRate("5% annual")
    due_dates = [
        datetime(2024, 1, 15, tzinfo=timezone.utc),
        datetime(2024, 2, 15, tzinfo=timezone.utc),
        datetime(2024, 3, 15, tzinfo=timezone.utc),
    ]
    return Loan(principal, interest_rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))


# Date parsing tests
@pytest.mark.parametrize(
    "date_input,expected_year",
    [
        ("2030-01-15", 2030),
        (datetime(2030, 1, 15, tzinfo=timezone.utc), 2030),
        (date(2030, 1, 15), 2030),
    ],
)
def test_warp_date_parsing_valid_formats(sample_loan, date_input, expected_year):
    warp = Warp(sample_loan, date_input)
    assert warp.target_date.year == expected_year


def test_warp_date_parsing_invalid_format_raises_error(sample_loan):
    with pytest.raises(InvalidDateError):
        Warp(sample_loan, 12345)  # Invalid type


def test_warp_date_parsing_invalid_string_raises_error(sample_loan):
    with pytest.raises(InvalidDateError):
        Warp(sample_loan, "not-a-date")


# Basic context manager functionality
def test_warp_context_manager_basic_functionality(sample_loan):
    target_date = "2030-01-15"

    with Warp(sample_loan, target_date) as warped_loan:
        # Should return a loan object
        assert isinstance(warped_loan, Loan)
        # Should be a different object (cloned)
        assert warped_loan is not sample_loan


def test_warp_context_manager_clones_loan(sample_loan):
    target_date = "2030-01-15"
    original_balance = sample_loan.current_balance

    with Warp(sample_loan, target_date) as warped_loan:
        # Modify the warped loan
        warped_loan._current_balance = Money("5000.00")

    # Original loan should be unchanged
    assert sample_loan.current_balance == original_balance


# Nested warp detection
def test_warp_nested_contexts_raise_error(sample_loan):
    with Warp(sample_loan, "2030-01-15"), pytest.raises(NestedWarpError):
        Warp(sample_loan, "2035-01-15")


def test_warp_sequential_contexts_work(sample_loan):
    # Sequential warps should work fine
    with Warp(sample_loan, "2030-01-15") as warp1:
        balance1 = warp1.current_balance

    with Warp(sample_loan, "2035-01-15") as warp2:
        balance2 = warp2.current_balance

    # Should complete without errors
    assert isinstance(balance1, Money)
    assert isinstance(balance2, Money)


# Time-aware functionality tests
def test_warp_overrides_current_datetime(sample_loan):
    target_date = datetime(2030, 6, 15, 14, 30, 0, tzinfo=timezone.utc)

    with Warp(sample_loan, target_date) as warped_loan:
        # The warped loan should return the target date as current time
        assert warped_loan.now() == target_date


def test_warp_filters_future_payments(sample_loan):
    # Add some payments to the loan
    sample_loan.record_payment(Money("500"), datetime(2024, 1, 10, tzinfo=timezone.utc), description="Early payment")
    sample_loan.record_payment(Money("600"), datetime(2024, 2, 10, tzinfo=timezone.utc), description="Regular payment")
    sample_loan.record_payment(Money("700"), datetime(2024, 3, 10, tzinfo=timezone.utc), description="Final payment")

    # Warp to a date between the first and second payment
    target_date = datetime(2024, 1, 20, tzinfo=timezone.utc)

    with Warp(sample_loan, target_date) as warped_loan:
        # Should only have the first payment
        assert len(warped_loan._actual_payments) == 2  # Interest + principal portions of first payment

        # All payments should be before or on target date
        for payment in warped_loan._actual_payments:
            assert payment.datetime <= target_date


def test_warp_recalculates_balance_from_filtered_payments(sample_loan):
    # Capture balance at a specific date for consistent comparison
    target_date = datetime(2024, 1, 5, tzinfo=timezone.utc)
    with Warp(sample_loan, target_date) as warped_loan:
        original_balance = warped_loan.current_balance

    # Add a payment after the target date
    sample_loan.record_payment(Money("1000"), datetime(2024, 1, 10, tzinfo=timezone.utc), description="Payment")
    balance_after_payment = sample_loan.current_balance

    # Warp back to before the payment was made
    with Warp(sample_loan, target_date) as warped_loan:
        # Balance should be back to original (no payments applied)
        assert warped_loan.current_balance == original_balance

    # Original loan should still have the payment applied
    assert sample_loan.current_balance == balance_after_payment


def test_warp_days_since_last_payment_uses_warped_time(sample_loan):
    # Add a payment
    payment_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    sample_loan.record_payment(Money("500"), payment_date, description="Test payment")

    # Warp to 10 days after the payment
    target_date = datetime(2024, 1, 25, tzinfo=timezone.utc)

    with Warp(sample_loan, target_date) as warped_loan:
        # Should calculate days from warped time, not real current time
        days = warped_loan.days_since_last_payment()
        assert days == 10  # 10 days between payment and target date


def test_warp_to_past_ignores_future_payments():
    # Create loan with payments at different dates
    loan = Loan(
        Money("10000"),
        InterestRate("5% annual"),
        [
            datetime(2024, 1, 15, tzinfo=timezone.utc),
            datetime(2024, 2, 15, tzinfo=timezone.utc),
            datetime(2024, 3, 15, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    # Add payments
    loan.record_payment(Money("500"), datetime(2024, 1, 10, tzinfo=timezone.utc), description="Payment 1")
    loan.record_payment(Money("600"), datetime(2024, 2, 10, tzinfo=timezone.utc), description="Payment 2")
    loan.record_payment(Money("700"), datetime(2024, 3, 10, tzinfo=timezone.utc), description="Payment 3")

    # Warp to middle date
    with Warp(loan, datetime(2024, 2, 5, tzinfo=timezone.utc)) as warped_loan:
        # Should only have first payment (2 items: interest + principal)
        assert len(warped_loan._actual_payments) == 2

        # Check that it's the first payment
        payment_dates = [p.datetime for p in warped_loan._actual_payments]
        assert all(d == datetime(2024, 1, 10, tzinfo=timezone.utc) for d in payment_dates)


def test_warp_to_future_keeps_all_past_payments():
    # Disable fines so payments produce interest/mora + principal only.
    # Payment 1 (Jan 10) is early -> interest + principal = 2 items
    # Payment 2 (Feb 10) is late vs Jan 15 due date -> interest + mora + principal = 3 items
    loan = Loan(
        Money("10000"),
        InterestRate("5% annual"),
        [datetime(2024, 1, 15, tzinfo=timezone.utc), datetime(2024, 2, 15, tzinfo=timezone.utc)],
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0"),
    )

    loan.record_payment(Money("500"), datetime(2024, 1, 10, tzinfo=timezone.utc), description="Payment 1")
    loan.record_payment(Money("600"), datetime(2024, 2, 10, tzinfo=timezone.utc), description="Payment 2")

    # Warp to future date — both past payments must be visible (5 items: 2 + 3)
    with Warp(loan, datetime(2025, 1, 1, tzinfo=timezone.utc)) as warped_loan:
        assert len(warped_loan._actual_payments) == 5


# String representations
def test_warp_string_representation():
    loan = Loan(
        Money("1000"),
        InterestRate("5% annual"),
        [datetime(2024, 1, 1, tzinfo=timezone.utc)],
        disbursement_date=datetime(2023, 12, 1, tzinfo=timezone.utc),
    )
    warp = Warp(loan, "2030-01-15")

    str_repr = str(warp)
    assert "2030-01-15" in str_repr
    assert "Warp" in str_repr


def test_warp_repr_representation():
    loan = Loan(
        Money("1000"),
        InterestRate("5% annual"),
        [datetime(2024, 1, 1, tzinfo=timezone.utc)],
        disbursement_date=datetime(2023, 12, 1, tzinfo=timezone.utc),
    )
    warp = Warp(loan, "2030-01-15")

    repr_str = repr(warp)
    assert "Warp" in repr_str
    assert "2030-01-15" in repr_str
