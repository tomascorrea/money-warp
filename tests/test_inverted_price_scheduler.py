"""Tests for InvertedPriceScheduler (Constant Amortization System)."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from money_warp import InterestRate, InvertedPriceScheduler, Money


@pytest.fixture
def basic_loan_params():
    """Basic loan parameters for testing."""
    return {
        "principal": Money("10000.00"),
        "interest_rate": InterestRate("5% annual"),
        "due_dates": [
            datetime(2024, 1, 15, tzinfo=timezone.utc),
            datetime(2024, 2, 15, tzinfo=timezone.utc),
            datetime(2024, 3, 15, tzinfo=timezone.utc),
        ],
        "disbursement_date": datetime(2023, 12, 16, tzinfo=timezone.utc),
    }


# Basic functionality tests
def test_inverted_price_scheduler_creation(basic_loan_params):
    schedule = InvertedPriceScheduler.generate_schedule(**basic_loan_params)
    assert len(schedule) == 3
    assert schedule[0].payment_number == 1
    assert schedule[2].payment_number == 3


def test_inverted_price_scheduler_empty_due_dates():
    with pytest.raises(ValueError, match="At least one due date is required"):
        InvertedPriceScheduler.generate_schedule(
            Money("10000"), InterestRate("5% annual"), [], datetime(2024, 1, 1, tzinfo=timezone.utc)
        )


# Fixed principal payment tests
def test_inverted_price_scheduler_fixed_principal_payments(basic_loan_params):
    schedule = InvertedPriceScheduler.generate_schedule(**basic_loan_params)

    # Each principal payment should be approximately equal (except last for rounding)
    expected_principal = basic_loan_params["principal"].raw_amount / Decimal("3")

    # First two payments should have fixed principal
    assert abs(schedule[0].principal_payment.raw_amount - expected_principal) < Decimal("0.01")
    assert abs(schedule[1].principal_payment.raw_amount - expected_principal) < Decimal("0.01")

    # Last payment should pay off remaining balance exactly
    assert schedule[2].ending_balance.is_zero()


def test_inverted_price_scheduler_decreasing_total_payments(basic_loan_params):
    schedule = InvertedPriceScheduler.generate_schedule(**basic_loan_params)

    # Total payments should decrease over time (because interest decreases)
    assert schedule[0].payment_amount > schedule[1].payment_amount
    assert schedule[1].payment_amount > schedule[2].payment_amount


def test_inverted_price_scheduler_decreasing_interest_payments(basic_loan_params):
    schedule = InvertedPriceScheduler.generate_schedule(**basic_loan_params)

    # Interest payments should decrease over time (calculated on decreasing balance)
    assert schedule[0].interest_payment > schedule[1].interest_payment
    assert schedule[1].interest_payment > schedule[2].interest_payment


# Balance progression tests
def test_inverted_price_scheduler_balance_progression(basic_loan_params):
    schedule = InvertedPriceScheduler.generate_schedule(**basic_loan_params)

    # Balance should decrease by fixed principal amounts
    assert schedule[0].beginning_balance == basic_loan_params["principal"]
    assert schedule[0].ending_balance < schedule[0].beginning_balance
    assert schedule[1].beginning_balance == schedule[0].ending_balance
    assert schedule[2].beginning_balance == schedule[1].ending_balance
    assert schedule[2].ending_balance.is_zero()


def test_inverted_price_scheduler_total_payments_cover_principal_and_interest(basic_loan_params):
    schedule = InvertedPriceScheduler.generate_schedule(**basic_loan_params)

    total_principal_paid = sum((entry.principal_payment for entry in schedule), Money.zero())
    total_interest_paid = sum((entry.interest_payment for entry in schedule), Money.zero())
    total_paid = sum((entry.payment_amount for entry in schedule), Money.zero())

    # Total principal should equal original loan amount
    assert total_principal_paid == basic_loan_params["principal"]

    # Total paid should equal principal + interest
    assert total_paid == total_principal_paid + total_interest_paid

    # Interest should be positive
    assert total_interest_paid.is_positive()


# Comparison with PriceScheduler tests
def test_inverted_price_scheduler_vs_price_scheduler_interest_comparison(basic_loan_params):
    from money_warp import PriceScheduler

    inverted_schedule = InvertedPriceScheduler.generate_schedule(**basic_loan_params)
    price_schedule = PriceScheduler.generate_schedule(**basic_loan_params)

    inverted_total_interest = sum((entry.interest_payment for entry in inverted_schedule), Money.zero())
    price_total_interest = sum((entry.interest_payment for entry in price_schedule), Money.zero())

    # Inverted Price (SAC) typically pays less total interest due to faster principal reduction
    assert inverted_total_interest < price_total_interest


# Edge case tests
def test_inverted_price_scheduler_single_payment(basic_loan_params):
    single_payment_params = basic_loan_params.copy()
    single_payment_params["due_dates"] = [datetime(2024, 1, 15, tzinfo=timezone.utc)]

    schedule = InvertedPriceScheduler.generate_schedule(**single_payment_params)

    assert len(schedule) == 1
    assert schedule[0].principal_payment == basic_loan_params["principal"]
    assert schedule[0].ending_balance.is_zero()


def test_inverted_price_scheduler_zero_interest_rate():
    schedule = InvertedPriceScheduler.generate_schedule(
        Money("1000"),
        InterestRate("0% annual"),
        [datetime(2024, 1, 15, tzinfo=timezone.utc), datetime(2024, 2, 15, tzinfo=timezone.utc)],
        datetime(2023, 12, 16, tzinfo=timezone.utc),
    )

    # With zero interest, all payments should be principal only
    assert schedule[0].interest_payment.is_zero()
    assert schedule[1].interest_payment.is_zero()
    assert schedule[0].principal_payment == Money("500")
    assert schedule[1].principal_payment == Money("500")


def test_inverted_price_scheduler_irregular_payment_dates():
    schedule = InvertedPriceScheduler.generate_schedule(
        Money("3000"),
        InterestRate("6% annual"),
        [
            datetime(2024, 1, 10, tzinfo=timezone.utc),  # 25 days from disbursement
            datetime(2024, 2, 20, tzinfo=timezone.utc),  # 41 days from previous
            datetime(2024, 4, 5, tzinfo=timezone.utc),  # 45 days from previous
        ],
        datetime(2023, 12, 16, tzinfo=timezone.utc),
    )

    # Should handle irregular dates correctly
    assert len(schedule) == 3
    assert schedule[0].days_in_period == 25
    assert schedule[1].days_in_period == 41
    assert schedule[2].days_in_period == 45

    # Different day counts should result in different interest amounts
    # even with same beginning balance patterns
    assert schedule[0].interest_payment != schedule[1].interest_payment


# High precision tests
def test_inverted_price_scheduler_high_precision_calculations():
    schedule = InvertedPriceScheduler.generate_schedule(
        Money("12345.67"),
        InterestRate("4.321% annual"),
        [datetime(2024, i, 1, tzinfo=timezone.utc) for i in range(1, 13)],  # 12 monthly payments
        datetime(2023, 12, 1, tzinfo=timezone.utc),
    )

    # Should handle high precision without errors
    assert len(schedule) == 12
    assert schedule[-1].ending_balance.is_zero()

    # Total principal should equal original amount
    total_principal = sum((entry.principal_payment for entry in schedule), Money.zero())
    assert abs(total_principal.raw_amount - Decimal("12345.67")) < Decimal("0.01")


# Performance comparison test
def test_inverted_price_scheduler_faster_principal_reduction(basic_loan_params):
    from money_warp import PriceScheduler

    inverted_schedule = InvertedPriceScheduler.generate_schedule(**basic_loan_params)
    price_schedule = PriceScheduler.generate_schedule(**basic_loan_params)

    # After first payment, inverted should have paid more principal
    assert inverted_schedule[0].principal_payment > price_schedule[0].principal_payment

    # After first payment, inverted should have lower remaining balance
    assert inverted_schedule[0].ending_balance < price_schedule[0].ending_balance


# String representation tests
def test_inverted_price_scheduler_schedule_entries_have_string_representation(basic_loan_params):
    schedule = InvertedPriceScheduler.generate_schedule(**basic_loan_params)

    for entry in schedule:
        str_repr = str(entry)
        assert "Payment" in str_repr
        assert str(entry.payment_number) in str_repr
        assert "Principal" in str_repr
        assert "Interest" in str_repr
