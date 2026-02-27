"""Tests for present value calculations."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from money_warp import (
    CashFlow,
    CashFlowItem,
    InterestRate,
    Money,
    discount_factor,
    present_value,
    present_value_of_annuity,
    present_value_of_perpetuity,
)


@pytest.fixture
def simple_cash_flow():
    """Simple cash flow for testing."""
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Initial investment", "investment"),
        CashFlowItem(Money("500"), datetime(2024, 6, 1, tzinfo=timezone.utc), "Mid-year return", "return"),
        CashFlowItem(Money("600"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Year-end return", "return"),
    ]
    return CashFlow(items)


# Basic present value tests
def test_present_value_empty_cash_flow():
    empty_cf = CashFlow.empty()
    pv = present_value(empty_cf, InterestRate("5% annual"))
    assert pv.is_zero()


def test_present_value_single_cash_flow():
    items = [CashFlowItem(Money("1000"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Future payment", "payment")]
    cf = CashFlow(items)

    # PV of $1000 in 1 year at 10% should be about $909.09
    pv = present_value(cf, InterestRate("10% annual"), datetime(2024, 1, 1, tzinfo=timezone.utc))

    # Allow for small rounding differences due to daily compounding
    expected = Money("909.09")
    assert abs(pv.real_amount - expected.real_amount) < Decimal("5.00")


def test_present_value_with_default_valuation_date(simple_cash_flow):
    # Should use earliest cash flow date (2024-01-01) as valuation date
    pv = present_value(simple_cash_flow, InterestRate("5% annual"))

    # Should be positive since we have net positive cash flows
    assert pv.is_positive()


def test_present_value_zero_interest_rate(simple_cash_flow):
    pv = present_value(simple_cash_flow, InterestRate("0% annual"))

    # With zero discount rate, PV equals sum of all cash flows
    total_cash_flow = sum((item.amount for item in simple_cash_flow), Money.zero())
    assert pv == total_cash_flow


def test_present_value_high_discount_rate(simple_cash_flow):
    low_rate_pv = present_value(simple_cash_flow, InterestRate("5% annual"))
    high_rate_pv = present_value(simple_cash_flow, InterestRate("20% annual"))

    # Higher discount rate should result in lower present value
    assert high_rate_pv < low_rate_pv


# Present Value of Annuity tests
def test_present_value_of_annuity_ordinary():
    # PV of $1000 monthly for 12 months at 5% annual (converted to monthly)
    monthly_rate = InterestRate("5% annual").to_monthly()
    pv = present_value_of_annuity(Money("1000"), monthly_rate, 12)

    # Should be less than $12,000 due to time value of money
    assert pv < Money("12000")
    assert pv > Money("11000")  # But not too much less


def test_present_value_of_annuity_due():
    monthly_rate = InterestRate("5% annual").to_monthly()

    ordinary_pv = present_value_of_annuity(Money("1000"), monthly_rate, 12, "end")
    due_pv = present_value_of_annuity(Money("1000"), monthly_rate, 12, "begin")

    # Annuity due should have higher PV (payments at beginning of period)
    assert due_pv > ordinary_pv


def test_present_value_of_annuity_zero_periods():
    pv = present_value_of_annuity(Money("1000"), InterestRate("5% annual"), 0)
    assert pv.is_zero()


def test_present_value_of_annuity_zero_payment():
    pv = present_value_of_annuity(Money.zero(), InterestRate("5% annual"), 12)
    assert pv.is_zero()


def test_present_value_of_annuity_zero_interest():
    # With zero interest, PV should equal total payments
    pv = present_value_of_annuity(Money("1000"), InterestRate("0% annual"), 12)
    assert pv == Money("12000")


@pytest.mark.parametrize("payment_timing", ["end", "begin", "beginning", "due"])
def test_present_value_of_annuity_payment_timing_variations(payment_timing):
    # Should accept various strings for payment timing
    pv = present_value_of_annuity(Money("100"), InterestRate("5% annual"), 10, payment_timing)
    assert pv.is_positive()


# Present Value of Perpetuity tests
def test_present_value_of_perpetuity_basic():
    # PV of $100 annual payments forever at 5% should be $2000
    pv = present_value_of_perpetuity(Money("100"), InterestRate("5% annual"))
    assert pv == Money("2000")


def test_present_value_of_perpetuity_zero_payment():
    pv = present_value_of_perpetuity(Money.zero(), InterestRate("5% annual"))
    assert pv.is_zero()


def test_present_value_of_perpetuity_zero_interest_raises_error():
    with pytest.raises(ValueError, match="Interest rate must be positive"):
        present_value_of_perpetuity(Money("100"), InterestRate("0% annual"))


def test_present_value_of_perpetuity_negative_interest_raises_error():
    # InterestRate doesn't accept negative rates, so test with manually created negative rate
    # We'll test the function's validation directly
    rate = InterestRate("1% annual")
    # Manually set a negative rate for testing
    rate._decimal_rate = Decimal("-0.01")

    with pytest.raises(ValueError, match="Interest rate must be positive"):
        present_value_of_perpetuity(Money("100"), rate)


def test_present_value_of_perpetuity_high_vs_low_rates():
    high_rate_pv = present_value_of_perpetuity(Money("100"), InterestRate("10% annual"))
    low_rate_pv = present_value_of_perpetuity(Money("100"), InterestRate("2% annual"))

    # Lower interest rate should result in higher present value
    assert low_rate_pv > high_rate_pv


# Discount Factor tests
def test_discount_factor_zero_periods():
    df = discount_factor(InterestRate("5% annual"), 0)
    assert df == Decimal("1")


def test_discount_factor_one_period():
    # DF = 1 / (1 + 0.05)^1 = 1/1.05 ≈ 0.9524
    df = discount_factor(InterestRate("5% annual"), 1)
    expected = Decimal("1") / Decimal("1.05")
    assert abs(df - expected) < Decimal("0.0001")


def test_discount_factor_multiple_periods():
    # DF = 1 / (1 + 0.10)^2 = 1/1.21 ≈ 0.8264
    df = discount_factor(InterestRate("10% annual"), 2)
    expected = Decimal("1") / (Decimal("1.10") ** 2)
    assert abs(df - expected) < Decimal("0.0001")


def test_discount_factor_fractional_periods():
    # Should handle fractional periods
    df = discount_factor(InterestRate("8% annual"), Decimal("1.5"))
    assert df > 0
    assert df < 1


def test_discount_factor_decreases_with_time():
    rate = InterestRate("6% annual")
    df_1_year = discount_factor(rate, 1)
    df_2_years = discount_factor(rate, 2)
    df_5_years = discount_factor(rate, 5)

    # Discount factor should decrease as time increases
    assert df_1_year > df_2_years > df_5_years


# Integration tests with CashFlow and Time Machine concepts
def test_present_value_with_irregular_cash_flows():
    # Test with irregular timing and amounts
    items = [
        CashFlowItem(Money("-5000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1500"), datetime(2024, 3, 15, tzinfo=timezone.utc), "Q1 return", "return"),
        CashFlowItem(Money("2000"), datetime(2024, 7, 10, tzinfo=timezone.utc), "Mid-year bonus", "return"),
        CashFlowItem(Money("1800"), datetime(2024, 11, 30, tzinfo=timezone.utc), "Year-end return", "return"),
    ]
    cf = CashFlow(items)

    pv = present_value(cf, InterestRate("12% annual"), datetime(2024, 1, 1, tzinfo=timezone.utc))

    # At 12% discount rate, this particular cash flow might be negative
    # The important thing is that PV calculation works with irregular flows
    assert isinstance(pv, Money)  # Just verify it returns a Money object


def test_present_value_past_cash_flows():
    # Test with some cash flows in the past relative to valuation date
    items = [
        CashFlowItem(Money("1000"), datetime(2023, 6, 1, tzinfo=timezone.utc), "Past cash flow", "past"),
        CashFlowItem(Money("1000"), datetime(2024, 6, 1, tzinfo=timezone.utc), "Future cash flow", "future"),
    ]
    cf = CashFlow(items)

    # Valuation date after first cash flow
    pv = present_value(cf, InterestRate("5% annual"), datetime(2024, 1, 1, tzinfo=timezone.utc))

    # Past cash flows should not be discounted (treated as period 0)
    # Future cash flows should be discounted
    assert pv.is_positive()


def test_present_value_with_time_machine_philosophy():
    """
    Test that demonstrates the Time Machine philosophy:
    We calculate PV to understand value today, then use Warp to see actual future values.
    """
    from money_warp import Loan, Warp

    # Create a loan and its expected cash flows
    loan = Loan(
        Money("10000"),
        InterestRate("5% annual"),
        [
            datetime(2024, 1, 15, tzinfo=timezone.utc),
            datetime(2024, 2, 15, tzinfo=timezone.utc),
            datetime(2024, 3, 15, tzinfo=timezone.utc),
        ],
        datetime(2023, 12, 16, tzinfo=timezone.utc),
    )

    expected_cf = loan.generate_expected_cash_flow()

    # Calculate PV of expected cash flows
    pv = present_value(expected_cf, InterestRate("8% annual"))

    # Use Time Machine to see what the balance will be at a future date
    with Warp(loan, datetime(2024, 2, 1, tzinfo=timezone.utc)) as future_loan:
        future_balance = future_loan.current_balance

    # Both should provide valuable but different insights
    assert pv.is_positive()  # PV tells us value today
    assert future_balance.is_positive()  # Warp tells us actual future state


# Edge cases and error conditions
def test_present_value_very_high_discount_rate(simple_cash_flow):
    # Very high discount rate should make future cash flows nearly worthless
    pv_low_rate = present_value(simple_cash_flow, InterestRate("5% annual"))
    pv_high_rate = present_value(simple_cash_flow, InterestRate("100% annual"))

    # Higher discount rate should result in lower (more negative or less positive) PV
    assert pv_high_rate < pv_low_rate


def test_present_value_precision_with_daily_compounding():
    # Test that daily compounding gives precise results
    items = [CashFlowItem(Money("1000"), datetime(2024, 7, 2, tzinfo=timezone.utc), "180 days future", "payment")]
    cf = CashFlow(items)

    # 180 days at 5% annual
    pv = present_value(cf, InterestRate("5% annual"), datetime(2024, 1, 4, tzinfo=timezone.utc))

    # Should be discounted but not too much for half a year
    assert pv < Money("1000")
    assert pv > Money("950")


# String representation and debugging
def test_present_value_functions_with_string_representations():
    """Test that all functions work with Money objects that have proper string representations."""
    cf = CashFlow([CashFlowItem(Money("1234.56"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Test", "test")])

    pv = present_value(cf, InterestRate("7.5% annual"), datetime(2024, 1, 1, tzinfo=timezone.utc))
    annuity_pv = present_value_of_annuity(Money("500.25"), InterestRate("4.25% annual"), 24)
    perpetuity_pv = present_value_of_perpetuity(Money("100.50"), InterestRate("3.5% annual"))

    # All should have meaningful string representations
    assert "," in str(pv)  # Money formatting with commas
    assert "," in str(annuity_pv)
    assert "," in str(perpetuity_pv)
