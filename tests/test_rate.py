"""Tests for the Rate base class — signed, general-purpose financial rates."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from money_warp import (
    CashFlow,
    CashFlowItem,
    InterestRate,
    Money,
    Rate,
    YearSize,
    internal_rate_of_return,
    irr,
)
from money_warp.rate import CompoundingFrequency


# ---------------------------------------------------------------------------
# Creation — positive, negative, zero
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rate_str,expected_decimal",
    [
        ("5.25% a", Decimal("0.0525")),
        ("-2.5% a", Decimal("-0.025")),
        ("0% a", Decimal("0")),
        ("-0.5% a.m.", Decimal("-0.005")),
        ("10% monthly", Decimal("0.10")),
        ("-10% monthly", Decimal("-0.10")),
    ],
)
def test_rate_creation_from_string(rate_str, expected_decimal):
    rate = Rate(rate_str)
    assert rate.as_decimal() == expected_decimal


def test_rate_creation_negative_numeric():
    rate = Rate(-0.05, CompoundingFrequency.ANNUALLY)
    assert rate.as_decimal() == Decimal("-0.05")


def test_rate_creation_negative_numeric_as_percentage():
    rate = Rate(-5, CompoundingFrequency.ANNUALLY, as_percentage=True)
    assert rate.as_decimal() == Decimal("-0.05")


def test_rate_creation_zero_numeric():
    rate = Rate(0, CompoundingFrequency.ANNUALLY)
    assert rate.as_decimal() == Decimal("0")


def test_rate_creation_positive_numeric():
    rate = Rate(0.10, CompoundingFrequency.ANNUALLY)
    assert rate.as_decimal() == Decimal("0.1")


# ---------------------------------------------------------------------------
# String parsing — negative values
# ---------------------------------------------------------------------------


def test_rate_negative_string_percentage():
    rate = Rate("-3.5% annual")
    assert rate.as_percentage() == Decimal("-3.5")


def test_rate_negative_string_decimal():
    rate = Rate("-0.035 annual")
    assert rate.as_decimal() == Decimal("-0.035")


def test_rate_negative_string_abbreviated():
    rate = Rate("-1.25% a.a.")
    assert rate.as_percentage() == Decimal("-1.25")
    assert rate.period == CompoundingFrequency.ANNUALLY


# ---------------------------------------------------------------------------
# String parsing — invalid formats still rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "invalid_string",
    [
        "abc% a",
        "5.25",
        "",
        "5.25%a",
    ],
)
def test_rate_string_parsing_invalid_format(invalid_string):
    with pytest.raises(ValueError, match="Invalid rate format"):
        Rate(invalid_string)


def test_rate_numeric_requires_period():
    with pytest.raises(ValueError, match="period is required"):
        Rate(0.05)


# ---------------------------------------------------------------------------
# Period conversions — negative rates
# ---------------------------------------------------------------------------


def test_rate_negative_annual_to_monthly():
    rate = Rate("-12% annual")
    monthly = rate.to_monthly()
    assert monthly.period == CompoundingFrequency.MONTHLY
    assert monthly.as_decimal() < 0


def test_rate_negative_annual_to_daily():
    rate = Rate("-5% annual")
    daily = rate.to_daily()
    assert daily.period == CompoundingFrequency.DAILY
    assert daily.as_decimal() < 0


def test_rate_negative_monthly_to_annual():
    rate = Rate("-1% monthly")
    annual = rate.to_annual()
    assert annual.period == CompoundingFrequency.ANNUALLY
    assert annual.as_decimal() < 0


def test_rate_conversion_preserves_class_for_rate():
    rate = Rate("5% annual")
    assert type(rate.to_monthly()) is Rate


def test_rate_conversion_preserves_class_for_interest_rate():
    rate = InterestRate("5% annual")
    assert type(rate.to_monthly()) is InterestRate


# ---------------------------------------------------------------------------
# Comparisons — Rate vs Rate, Rate vs InterestRate
# ---------------------------------------------------------------------------


def test_rate_equality_same_values():
    assert Rate("5% annual") == Rate("5% annual")


def test_rate_equality_negative():
    assert Rate("-3% annual") == Rate("-3% annual")


def test_rate_less_than():
    assert Rate("-5% annual") < Rate("5% annual")


def test_rate_greater_than():
    assert Rate("10% annual") > Rate("-10% annual")


def test_rate_equality_cross_type():
    assert Rate("5% annual") == InterestRate("5% annual")


def test_rate_comparison_cross_type():
    assert Rate("-1% annual") < InterestRate("1% annual")


# ---------------------------------------------------------------------------
# Display — __str__ and __repr__
# ---------------------------------------------------------------------------


def test_rate_str_negative():
    rate = Rate("-2.5% annual")
    assert str(rate) == "-2.500% annually"


def test_rate_str_positive():
    rate = Rate("5.25% a")
    assert str(rate) == "5.250% annually"


def test_rate_repr_uses_class_name():
    rate = Rate(0.05, CompoundingFrequency.ANNUALLY)
    assert repr(rate).startswith("Rate(")


def test_interest_rate_repr_uses_class_name():
    rate = InterestRate(0.05, CompoundingFrequency.ANNUALLY)
    assert repr(rate).startswith("InterestRate(")


# ---------------------------------------------------------------------------
# Subclass relationship
# ---------------------------------------------------------------------------


def test_interest_rate_is_subclass_of_rate():
    assert issubclass(InterestRate, Rate)


def test_interest_rate_instance_is_rate():
    rate = InterestRate("5% annual")
    assert isinstance(rate, Rate)


# ---------------------------------------------------------------------------
# InterestRate rejects negatives
# ---------------------------------------------------------------------------


def test_interest_rate_rejects_negative_string():
    with pytest.raises(ValueError, match="Interest rate cannot be negative"):
        InterestRate("-5% annual")


def test_interest_rate_rejects_negative_numeric():
    with pytest.raises(ValueError, match="Interest rate cannot be negative"):
        InterestRate(-0.05, CompoundingFrequency.ANNUALLY)


def test_interest_rate_rejects_negative_percentage():
    with pytest.raises(ValueError, match="Interest rate cannot be negative"):
        InterestRate(-5, CompoundingFrequency.ANNUALLY, as_percentage=True)


def test_interest_rate_allows_zero():
    rate = InterestRate("0% annual")
    assert rate.as_decimal() == Decimal("0")


# ---------------------------------------------------------------------------
# IRR returns Rate, not InterestRate
# ---------------------------------------------------------------------------


def test_irr_returns_rate_type():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "out"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "in"),
    ]
    cf = CashFlow(items)
    result = irr(cf)
    assert isinstance(result, Rate)
    assert type(result) is Rate


def test_irr_accepts_rate_as_guess():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "out"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "in"),
    ]
    cf = CashFlow(items)
    guess = Rate("8% annual")
    result = internal_rate_of_return(cf, guess=guess)
    assert isinstance(result, Rate)


def test_irr_accepts_interest_rate_as_guess():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Investment", "out"),
        CashFlowItem(Money("1100"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Return", "in"),
    ]
    cf = CashFlow(items)
    guess = InterestRate("8% annual")
    result = internal_rate_of_return(cf, guess=guess)
    assert isinstance(result, Rate)


# ---------------------------------------------------------------------------
# Negative IRR scenario — fees erode return below zero
# ---------------------------------------------------------------------------


def test_irr_negative_result_when_fees_erode_return():
    items = [
        CashFlowItem(Money("-1000"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Disbursement", "out"),
        CashFlowItem(Money("50"), datetime(2024, 1, 1, tzinfo=timezone.utc), "Fee deducted upfront", "fee"),
        CashFlowItem(Money("900"), datetime(2024, 12, 31, tzinfo=timezone.utc), "Repayment", "in"),
    ]
    cf = CashFlow(items)
    result = irr(cf)
    assert isinstance(result, Rate)
    assert result.as_decimal() < 0


# ---------------------------------------------------------------------------
# Year size propagation
# ---------------------------------------------------------------------------


def test_rate_year_size_propagates_through_conversion():
    rate = Rate("5% annual", year_size=YearSize.banker)
    daily = rate.to_daily()
    assert daily.year_size == YearSize.banker


def test_rate_year_size_default_is_commercial():
    rate = Rate("5% annual")
    assert rate.year_size == YearSize.commercial


# ---------------------------------------------------------------------------
# as_decimal(precision) tests
# ---------------------------------------------------------------------------


def test_rate_as_decimal_no_precision_returns_raw_value():
    rate = Rate("5.25% annual")
    assert rate.as_decimal() == Decimal("0.0525")


def test_rate_as_decimal_with_precision_quantizes():
    rate = Rate("5.25% annual")
    assert rate.as_decimal(2) == Decimal("0.05")


def test_rate_as_decimal_precision_four_places():
    rate = Rate(Decimal("0.12345678"), CompoundingFrequency.MONTHLY)
    assert rate.as_decimal(4) == Decimal("0.1235")


def test_rate_as_decimal_precision_zero():
    rate = Rate("5.25% annual")
    assert rate.as_decimal(0) == Decimal("0")


def test_rate_as_decimal_precision_high():
    rate = Rate(Decimal("0.123456789012"), CompoundingFrequency.ANNUALLY)
    assert rate.as_decimal(10) == Decimal("0.1234567890")


@pytest.mark.parametrize(
    "rate_value,precision,expected",
    [
        ("5.25% annual", None, Decimal("0.0525")),
        ("5.25% annual", 1, Decimal("0.1")),
        ("5.25% annual", 2, Decimal("0.05")),
        ("5.25% annual", 4, Decimal("0.0525")),
        ("5.25% annual", 6, Decimal("0.052500")),
    ],
)
def test_rate_as_decimal_parametrized(rate_value, precision, expected):
    rate = Rate(rate_value)
    assert rate.as_decimal(precision) == expected


# ---------------------------------------------------------------------------
# as_percentage(precision) tests
# ---------------------------------------------------------------------------


def test_rate_as_percentage_no_precision_returns_raw_value():
    rate = Rate("5.25% annual")
    assert rate.as_percentage() == Decimal("5.25")


def test_rate_as_percentage_with_precision_quantizes():
    rate = Rate("5.256% annual")
    assert rate.as_percentage(2) == Decimal("5.26")


def test_rate_as_percentage_precision_zero():
    rate = Rate("5.25% annual")
    assert rate.as_percentage(0) == Decimal("5")


@pytest.mark.parametrize(
    "rate_value,precision,expected",
    [
        ("5.25% annual", None, Decimal("5.25")),
        ("5.25% annual", 1, Decimal("5.3")),
        ("5.25% annual", 2, Decimal("5.25")),
        ("5.25% annual", 4, Decimal("5.2500")),
    ],
)
def test_rate_as_percentage_parametrized(rate_value, precision, expected):
    rate = Rate(rate_value)
    assert rate.as_percentage(precision) == expected


# ---------------------------------------------------------------------------
# as_float(precision) tests
# ---------------------------------------------------------------------------


def test_rate_as_float_returns_float_type():
    rate = Rate("5.25% annual")
    assert isinstance(rate.as_float(), float)


def test_rate_as_float_no_precision():
    rate = Rate("5.25% annual")
    assert rate.as_float() == 0.0525


def test_rate_as_float_with_precision():
    rate = Rate("5.25% annual")
    assert rate.as_float(2) == 0.05


def test_rate_as_float_precision_four():
    rate = Rate(Decimal("0.12345678"), CompoundingFrequency.MONTHLY)
    assert rate.as_float(4) == 0.1235


def test_rate_as_float_precision_zero():
    rate = Rate("5.25% annual")
    assert rate.as_float(0) == 0.0


@pytest.mark.parametrize(
    "rate_value,precision,expected",
    [
        ("5.25% annual", None, 0.0525),
        ("5.25% annual", 1, 0.1),
        ("5.25% annual", 2, 0.05),
        ("5.25% annual", 4, 0.0525),
    ],
)
def test_rate_as_float_parametrized(rate_value, precision, expected):
    rate = Rate(rate_value)
    assert rate.as_float(precision) == expected


def test_rate_as_float_negative_rate():
    rate = Rate("-5.25% annual")
    assert rate.as_float() == -0.0525


def test_rate_as_float_negative_rate_with_precision():
    rate = Rate("-5.25% annual")
    assert rate.as_float(2) == -0.05


def test_rate_as_float_zero_rate():
    rate = Rate("0% annual")
    assert rate.as_float() == 0.0


# ---------------------------------------------------------------------------
# str_decimals tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "str_decimals,expected",
    [
        (0, "5% annually"),
        (1, "5.2% annually"),
        (2, "5.25% annually"),
        (3, "5.250% annually"),
        (5, "5.25000% annually"),
    ],
)
def test_rate_str_decimals_long_style(str_decimals, expected):
    rate = Rate("5.25% annual", str_decimals=str_decimals)
    assert str(rate) == expected


@pytest.mark.parametrize(
    "str_decimals,expected",
    [
        (0, "5% a.a."),
        (2, "5.25% a.a."),
        (3, "5.250% a.a."),
    ],
)
def test_rate_str_decimals_abbrev_style(str_decimals, expected):
    rate = Rate("5.25% a.a.", str_decimals=str_decimals)
    assert str(rate) == expected


def test_rate_str_decimals_default_is_three():
    rate = Rate("5.25% annual")
    assert str(rate) == "5.250% annually"


def test_rate_str_decimals_negative_rate():
    rate = Rate("-2.5% annual", str_decimals=2)
    assert str(rate) == "-2.50% annually"


def test_rate_str_decimals_propagates_to_monthly():
    rate = Rate("12% annual", str_decimals=2)
    monthly = rate.to_monthly()
    assert str(monthly).endswith("% monthly")
    assert len(str(monthly).split("%")[0].split(".")[-1]) == 2


def test_rate_str_decimals_propagates_to_annual():
    rate = Rate("1% monthly", str_decimals=4)
    annual = rate.to_annual()
    assert str(annual).endswith("% annually")
    assert len(str(annual).split("%")[0].split(".")[-1]) == 4


def test_rate_str_decimals_propagates_to_daily():
    rate = Rate("12% annual", str_decimals=5)
    daily = rate.to_daily()
    assert str(daily).endswith("% daily")
    assert len(str(daily).split("%")[0].split(".")[-1]) == 5


# ---------------------------------------------------------------------------
# abbrev_labels tests
# ---------------------------------------------------------------------------


def test_rate_abbrev_labels_override_single_label():
    rate = Rate(
        0.05,
        CompoundingFrequency.MONTHLY,
        str_style="abbrev",
        abbrev_labels={CompoundingFrequency.MONTHLY: "a.m"},
    )
    assert str(rate) == "5.000% a.m"


def test_rate_abbrev_labels_override_all_labels():
    labels = {
        CompoundingFrequency.ANNUALLY: "a.a",
        CompoundingFrequency.MONTHLY: "a.m",
        CompoundingFrequency.DAILY: "a.d",
        CompoundingFrequency.QUARTERLY: "a.t",
        CompoundingFrequency.SEMI_ANNUALLY: "a.s",
    }
    rate = Rate(0.05, CompoundingFrequency.ANNUALLY, str_style="abbrev", abbrev_labels=labels)
    assert str(rate) == "5.000% a.a"


def test_rate_abbrev_labels_partial_override_keeps_defaults():
    rate = Rate(
        0.05,
        CompoundingFrequency.ANNUALLY,
        str_style="abbrev",
        abbrev_labels={CompoundingFrequency.MONTHLY: "a.m"},
    )
    assert str(rate) == "5.000% a.a."


def test_rate_abbrev_labels_none_uses_defaults():
    rate = Rate(0.05, CompoundingFrequency.MONTHLY, str_style="abbrev")
    assert str(rate) == "5.000% a.m."


def test_rate_abbrev_labels_combined_with_str_decimals():
    rate = Rate(
        "3.99% a.m.",
        str_decimals=2,
        abbrev_labels={CompoundingFrequency.MONTHLY: "a.m"},
    )
    assert str(rate) == "3.99% a.m"


def test_rate_abbrev_labels_does_not_affect_long_style():
    rate = Rate(
        0.05,
        CompoundingFrequency.MONTHLY,
        str_style="long",
        abbrev_labels={CompoundingFrequency.MONTHLY: "per.month"},
    )
    assert str(rate) == "5.000% monthly"


def test_rate_abbrev_labels_propagates_to_monthly():
    labels = {CompoundingFrequency.MONTHLY: "a.m"}
    rate = Rate("12% a.a.", abbrev_labels=labels)
    monthly = rate.to_monthly()
    assert str(monthly) == f"{monthly.as_percentage():.3f}% a.m"


def test_rate_abbrev_labels_propagates_to_annual():
    labels = {CompoundingFrequency.ANNUALLY: "a.a"}
    rate = Rate("1% a.m.", abbrev_labels=labels)
    annual = rate.to_annual()
    assert str(annual).endswith("% a.a")


def test_rate_abbrev_labels_propagates_to_daily():
    labels = {CompoundingFrequency.DAILY: "a.d"}
    rate = Rate("12% a.a.", abbrev_labels=labels)
    daily = rate.to_daily()
    assert str(daily).endswith("% a.d")
