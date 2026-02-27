"""Tests for Internal Rate of Return (IRR) calculations."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from money_warp import (
    CashFlow,
    CashFlowItem,
    InterestRate,
    Money,
    YearSize,
    internal_rate_of_return,
    irr,
    modified_internal_rate_of_return,
)


@pytest.fixture
def simple_investment():
    """Simple investment: -$1000 now, +$1100 in 1 year (10% return)."""
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "return"),
    ]
    return CashFlow(items)


@pytest.fixture
def multi_period_investment():
    """Multi-period investment with irregular returns."""
    items = [
        CashFlowItem(Money("-5000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Initial investment", "investment"),
        CashFlowItem(Money("1500"), datetime(2024, 6, 1, tzinfo=timezone.utc), "Return 1", "return"),
        CashFlowItem(Money("2000"), datetime(2024, 12, 1, tzinfo=timezone.utc), "Return 2", "return"),
        CashFlowItem(Money("2500"), datetime(2025, 6, 1, tzinfo=timezone.utc), "Final return", "return"),
    ]
    return CashFlow(items)


# Basic IRR tests
def test_irr_simple_investment(simple_investment):
    calculated_irr = irr(simple_investment)

    # Should be approximately 10% (1100/1000 - 1 = 0.10)
    expected_rate = 10.0
    actual_rate = float(calculated_irr.as_decimal * 100)

    assert abs(actual_rate - expected_rate) < 0.1  # Within 0.1%


def test_internal_rate_of_return_simple_investment(simple_investment):
    calculated_irr = internal_rate_of_return(simple_investment)

    # Should be approximately 10%
    expected_rate = 10.0
    actual_rate = float(calculated_irr.as_decimal * 100)

    assert abs(actual_rate - expected_rate) < 0.1


def test_irr_multi_period_investment(multi_period_investment):
    calculated_irr = irr(multi_period_investment)

    # Should return a valid InterestRate
    assert isinstance(calculated_irr, InterestRate)
    # Should be positive (profitable investment)
    assert calculated_irr.as_decimal > 0


def test_irr_with_time_machine_for_specific_date(simple_investment):
    # Instead of valuation_date parameter, use Time Machine
    # This test shows the Time Machine approach for IRR from specific dates
    from money_warp import Loan, Warp

    # Create a loan to demonstrate Time Machine IRR
    loan = Loan(
        Money("1000"),
        InterestRate("10% annual"),
        [datetime(2024, 12, 31, tzinfo=timezone.utc)],
        datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    # Get IRR from different time perspectives using Time Machine
    normal_irr = loan.irr()

    with Warp(loan, datetime(2024, 6, 1, tzinfo=timezone.utc)) as warped_loan:
        mid_year_irr = warped_loan.irr()

    # Both should be valid InterestRates
    assert isinstance(normal_irr, InterestRate)
    assert isinstance(mid_year_irr, InterestRate)


def test_irr_with_custom_guess(simple_investment):
    guess = InterestRate("5% annual")
    calculated_irr = irr(simple_investment, guess=guess)

    # Should still converge to approximately 10%
    expected_rate = 10.0
    actual_rate = float(calculated_irr.as_decimal * 100)

    assert abs(actual_rate - expected_rate) < 0.1


# Edge cases and error conditions
def test_irr_empty_cash_flow():
    empty_cf = CashFlow.empty()

    with pytest.raises(ValueError, match="Cannot calculate IRR for empty cash flow"):
        irr(empty_cf)


def test_irr_only_positive_cash_flows():
    items = [
        CashFlowItem(Money("1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Positive 1", "income"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Positive 2", "income"),
    ]
    cf = CashFlow(items)

    with pytest.raises(ValueError, match="IRR requires both positive and negative cash flows"):
        irr(cf)


def test_irr_only_negative_cash_flows():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Negative 1", "expense"),
        CashFlowItem(Money("-1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Negative 2", "expense"),
    ]
    cf = CashFlow(items)

    with pytest.raises(ValueError, match="IRR requires both positive and negative cash flows"):
        irr(cf)


def test_irr_zero_npv_case():
    # Create a cash flow where NPV is exactly zero at a known rate
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(
            Money("1050"), datetime(2024, 7, 1, tzinfo=timezone.utc), "Return", "return"
        ),  # 6 months, ~10% annual
    ]
    cf = CashFlow(items)

    calculated_irr = irr(cf)

    # Should find a valid IRR
    assert isinstance(calculated_irr, InterestRate)
    assert calculated_irr.as_decimal > 0


# Precision and convergence tests
def test_irr_high_precision():
    # Test with high precision requirements
    items = [
        CashFlowItem(Money("-1000.00"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(
            Money("1051.27"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "return"
        ),  # Exactly 5.127%
    ]
    cf = CashFlow(items)

    calculated_irr = internal_rate_of_return(cf)

    # Should be very close to 5.127%
    expected_rate = 5.127
    actual_rate = float(calculated_irr.as_decimal * 100)

    assert abs(actual_rate - expected_rate) < 0.001


def test_irr_scipy_convergence():
    # Test that scipy provides robust convergence
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "return"),
    ]
    cf = CashFlow(items)

    # Should converge reliably with scipy
    calculated_irr = internal_rate_of_return(cf)

    expected_rate = 10.0
    actual_rate = float(calculated_irr.as_decimal * 100)

    assert abs(actual_rate - expected_rate) < 0.001  # Very precise with scipy


def test_irr_complex_cash_flow():
    # More complex cash flow with multiple periods
    items = [
        CashFlowItem(Money("-10000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Initial investment", "investment"),
        CashFlowItem(Money("2000"), datetime(2024, 3, 1, tzinfo=timezone.utc), "Q1 return", "return"),
        CashFlowItem(Money("-1000"), datetime(2024, 6, 1, tzinfo=timezone.utc), "Additional investment", "investment"),
        CashFlowItem(Money("3000"), datetime(2024, 9, 1, tzinfo=timezone.utc), "Q3 return", "return"),
        CashFlowItem(Money("8000"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Final return", "return"),
    ]
    cf = CashFlow(items)

    calculated_irr = irr(cf)

    # Should find a valid IRR for complex cash flow
    assert isinstance(calculated_irr, InterestRate)


# Modified IRR (MIRR) tests
def test_mirr_basic():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("300"), datetime(2024, 6, 1, tzinfo=timezone.utc), "Return 1", "return"),
        CashFlowItem(Money("400"), datetime(2024, 12, 1, tzinfo=timezone.utc), "Return 2", "return"),
        CashFlowItem(Money("500"), datetime(2025, 6, 1, tzinfo=timezone.utc), "Return 3", "return"),
    ]
    cf = CashFlow(items)

    finance_rate = InterestRate("8% annual")
    reinvestment_rate = InterestRate("6% annual")

    mirr = modified_internal_rate_of_return(cf, finance_rate, reinvestment_rate)

    assert isinstance(mirr, InterestRate)
    assert mirr.as_decimal > 0  # Should be positive


def test_mirr_empty_cash_flow():
    empty_cf = CashFlow.empty()

    with pytest.raises(ValueError, match="Cannot calculate MIRR for empty cash flow"):
        modified_internal_rate_of_return(empty_cf, InterestRate("8% annual"), InterestRate("6% annual"))


def test_mirr_only_positive_flows():
    items = [
        CashFlowItem(Money("1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Positive", "income"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Positive", "income"),
    ]
    cf = CashFlow(items)

    with pytest.raises(ValueError, match="MIRR requires both positive and negative cash flows"):
        modified_internal_rate_of_return(cf, InterestRate("8% annual"), InterestRate("6% annual"))


def test_mirr_same_date_flows():
    # All cash flows on same date (no time span)
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1100"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Return", "return"),
    ]
    cf = CashFlow(items)

    with pytest.raises(ValueError, match="MIRR requires cash flows spanning multiple periods"):
        modified_internal_rate_of_return(cf, InterestRate("8% annual"), InterestRate("6% annual"))


def test_mirr_different_rates():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("600"), datetime(2024, 6, 1, tzinfo=timezone.utc), "Return 1", "return"),
        CashFlowItem(Money("600"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return 2", "return"),
    ]
    cf = CashFlow(items)

    # Test with different financing and reinvestment rates
    mirr_high_finance = modified_internal_rate_of_return(cf, InterestRate("12% annual"), InterestRate("4% annual"))
    mirr_low_finance = modified_internal_rate_of_return(cf, InterestRate("4% annual"), InterestRate("4% annual"))

    # Both should be valid
    assert isinstance(mirr_high_finance, InterestRate)
    assert isinstance(mirr_low_finance, InterestRate)


# Integration with other functions
def test_irr_vs_present_value_consistency():
    """Test that IRR and present value are consistent (NPV should be ~0 at IRR)."""
    from money_warp import present_value

    items = [
        CashFlowItem(Money("-2000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1100"), datetime(2024, 6, 1, tzinfo=timezone.utc), "Return 1", "return"),
        CashFlowItem(Money("1200"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return 2", "return"),
    ]
    cf = CashFlow(items)

    # Calculate IRR
    calculated_irr = irr(cf)

    # Calculate NPV using the IRR as discount rate
    npv_at_irr = present_value(cf, calculated_irr, datetime(2024, 1, 1, tzinfo=timezone.utc))

    # NPV at IRR should be very close to zero
    assert abs(npv_at_irr.raw_amount) < Decimal("1.0")  # Within $1


# Performance and edge cases
def test_irr_very_small_cash_flows():
    items = [
        CashFlowItem(Money("-0.01"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Tiny investment", "investment"),
        CashFlowItem(Money("0.011"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Tiny return", "return"),
    ]
    cf = CashFlow(items)

    calculated_irr = irr(cf)

    # Should still work with very small amounts
    expected_rate = 10.0  # 0.011/0.01 - 1 = 0.10
    actual_rate = float(calculated_irr.as_decimal * 100)

    assert abs(actual_rate - expected_rate) < 1.0  # Within 1% (precision may be lower for tiny amounts)


def test_irr_very_large_cash_flows():
    items = [
        CashFlowItem(Money("-1000000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Large investment", "investment"),
        CashFlowItem(Money("1100000"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Large return", "return"),
    ]
    cf = CashFlow(items)

    calculated_irr = irr(cf)

    # Should work with large amounts
    expected_rate = 10.0
    actual_rate = float(calculated_irr.as_decimal * 100)

    assert abs(actual_rate - expected_rate) < 0.1


# String representation and debugging
def test_irr_result_string_representation():
    """Test that IRR results have proper string representations."""
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "return"),
    ]
    cf = CashFlow(items)

    calculated_irr = irr(cf)

    # Should have meaningful string representation
    irr_str = str(calculated_irr)
    assert "%" in irr_str
    assert "annual" in irr_str.lower()

    # Should be convertible to float
    rate_as_float = float(calculated_irr.as_decimal)
    assert 0.05 < rate_as_float < 0.20  # Between 5% and 20% is reasonable


# Year size tests
def test_irr_banker_year_differs_from_commercial():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "return"),
    ]
    cf = CashFlow(items)

    irr_commercial = irr(cf, year_size=YearSize.commercial)
    irr_banker = irr(cf, year_size=YearSize.banker)

    assert irr_commercial.as_decimal != irr_banker.as_decimal


def test_irr_banker_year_returns_banker_year_size():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "return"),
    ]
    cf = CashFlow(items)

    calculated_irr = irr(cf, year_size=YearSize.banker)

    assert calculated_irr.year_size == YearSize.banker


def test_irr_commercial_year_returns_commercial_year_size():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "return"),
    ]
    cf = CashFlow(items)

    calculated_irr = irr(cf, year_size=YearSize.commercial)

    assert calculated_irr.year_size == YearSize.commercial


def test_irr_default_year_size_is_commercial():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "return"),
    ]
    cf = CashFlow(items)

    calculated_irr = irr(cf)

    assert calculated_irr.year_size == YearSize.commercial


def test_irr_banker_year_npv_at_irr_is_zero():
    from money_warp import present_value

    items = [
        CashFlowItem(Money("-2000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1100"), datetime(2024, 6, 1, tzinfo=timezone.utc), "Return 1", "return"),
        CashFlowItem(Money("1200"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return 2", "return"),
    ]
    cf = CashFlow(items)

    calculated_irr = irr(cf, year_size=YearSize.banker)
    npv_at_irr = present_value(cf, calculated_irr, datetime(2024, 1, 1, tzinfo=timezone.utc))

    assert abs(npv_at_irr.raw_amount) < Decimal("1.0")


def test_internal_rate_of_return_with_banker_year():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "return"),
    ]
    cf = CashFlow(items)

    calculated_irr = internal_rate_of_return(cf, year_size=YearSize.banker)

    assert calculated_irr.year_size == YearSize.banker
    assert calculated_irr.as_decimal > 0


def test_mirr_banker_year_differs_from_commercial():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("300"), datetime(2024, 6, 1, tzinfo=timezone.utc), "Return 1", "return"),
        CashFlowItem(Money("400"), datetime(2024, 12, 1, tzinfo=timezone.utc), "Return 2", "return"),
        CashFlowItem(Money("500"), datetime(2025, 6, 1, tzinfo=timezone.utc), "Return 3", "return"),
    ]
    cf = CashFlow(items)

    finance_rate = InterestRate("8% annual")
    reinvestment_rate = InterestRate("6% annual")

    mirr_commercial = modified_internal_rate_of_return(cf, finance_rate, reinvestment_rate)
    mirr_banker = modified_internal_rate_of_return(cf, finance_rate, reinvestment_rate, year_size=YearSize.banker)

    assert mirr_commercial.as_decimal != mirr_banker.as_decimal


def test_mirr_banker_year_returns_banker_year_size():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "investment"),
        CashFlowItem(Money("300"), datetime(2024, 6, 1, tzinfo=timezone.utc), "Return 1", "return"),
        CashFlowItem(Money("400"), datetime(2024, 12, 1, tzinfo=timezone.utc), "Return 2", "return"),
        CashFlowItem(Money("500"), datetime(2025, 6, 1, tzinfo=timezone.utc), "Return 3", "return"),
    ]
    cf = CashFlow(items)

    mirr = modified_internal_rate_of_return(
        cf, InterestRate("8% annual"), InterestRate("6% annual"), year_size=YearSize.banker
    )

    assert mirr.year_size == YearSize.banker
