"""Tests for InterestRate class - following project patterns."""

from decimal import Decimal

import pytest

from money_warp.interest_rate import CompoundingFrequency, InterestRate, YearSize
from money_warp.money import Money


# String parsing tests
@pytest.mark.parametrize(
    "rate_string,expected_decimal,expected_percentage,expected_frequency",
    [
        # Percentage formats with short abbreviations
        ("5.25% a", Decimal("0.0525"), Decimal("5.25"), CompoundingFrequency.ANNUALLY),
        ("0.5% m", Decimal("0.005"), Decimal("0.5"), CompoundingFrequency.MONTHLY),
        ("2.75% q", Decimal("0.0275"), Decimal("2.75"), CompoundingFrequency.QUARTERLY),
        ("0.0137% d", Decimal("0.000137"), Decimal("0.0137"), CompoundingFrequency.DAILY),
        ("3% s", Decimal("0.03"), Decimal("3.0"), CompoundingFrequency.SEMI_ANNUALLY),
        # Percentage formats with full words
        ("5.25% annual", Decimal("0.0525"), Decimal("5.25"), CompoundingFrequency.ANNUALLY),
        ("0.5% monthly", Decimal("0.005"), Decimal("0.5"), CompoundingFrequency.MONTHLY),
        ("2.75% quarterly", Decimal("0.0275"), Decimal("2.75"), CompoundingFrequency.QUARTERLY),
        ("0.0137% daily", Decimal("0.000137"), Decimal("0.0137"), CompoundingFrequency.DAILY),
        ("3% semi-annual", Decimal("0.03"), Decimal("3.0"), CompoundingFrequency.SEMI_ANNUALLY),
        # Decimal formats with short abbreviations
        ("0.0525 a", Decimal("0.0525"), Decimal("5.25"), CompoundingFrequency.ANNUALLY),
        ("0.004167 m", Decimal("0.004167"), Decimal("0.4167"), CompoundingFrequency.MONTHLY),
        ("0.0275 q", Decimal("0.0275"), Decimal("2.75"), CompoundingFrequency.QUARTERLY),
        ("0.000137 d", Decimal("0.000137"), Decimal("0.0137"), CompoundingFrequency.DAILY),
        ("0.03 s", Decimal("0.03"), Decimal("3.0"), CompoundingFrequency.SEMI_ANNUALLY),
        # Decimal formats with full words
        ("0.0525 annual", Decimal("0.0525"), Decimal("5.25"), CompoundingFrequency.ANNUALLY),
        ("0.004167 monthly", Decimal("0.004167"), Decimal("0.4167"), CompoundingFrequency.MONTHLY),
        ("0.0275 quarterly", Decimal("0.0275"), Decimal("2.75"), CompoundingFrequency.QUARTERLY),
        ("0.000137 daily", Decimal("0.000137"), Decimal("0.0137"), CompoundingFrequency.DAILY),
        ("0.03 semi-annual", Decimal("0.03"), Decimal("3.0"), CompoundingFrequency.SEMI_ANNUALLY),
    ],
)
def test_interest_rate_string_parsing(rate_string, expected_decimal, expected_percentage, expected_frequency):
    rate = InterestRate(rate_string)
    assert rate.as_decimal == expected_decimal


def test_interest_rate_string_parsing_stores_percentage():
    rate = InterestRate("5.25% a")
    assert rate.as_percentage == Decimal("5.25")


def test_interest_rate_string_parsing_stores_frequency():
    rate = InterestRate("5.25% monthly")
    assert rate.period == CompoundingFrequency.MONTHLY


# String parsing edge cases
def test_interest_rate_string_parsing_with_extra_spaces():
    rate = InterestRate("  5.25%   a  ")
    assert rate.as_decimal == Decimal("0.0525")


def test_interest_rate_string_parsing_case_insensitive():
    rate = InterestRate("5.25% ANNUAL")
    assert rate.as_decimal == Decimal("0.0525")


def test_interest_rate_string_parsing_mixed_case():
    rate = InterestRate("5.25% Monthly")
    assert rate.period == CompoundingFrequency.MONTHLY


# String parsing error cases
@pytest.mark.parametrize(
    "invalid_string",
    [
        "5.25",  # Missing frequency
        "% a",  # Missing value
        "5.25% x",  # Invalid frequency
        "abc% a",  # Invalid number
        "5.25 % a",  # Space before %
        "5.25%a",  # Missing space
        "",  # Empty string
        "5.25% annual extra",  # Extra text
        "5.25%% a",  # Double %
        "-5.25% a",  # Negative (not supported in regex)
    ],
)
def test_interest_rate_string_parsing_invalid_format(invalid_string):
    with pytest.raises(ValueError, match="Invalid rate format"):
        InterestRate(invalid_string)


# Numeric creation tests (backward compatibility)
def test_interest_rate_numeric_creation_decimal():
    rate = InterestRate(0.0525, CompoundingFrequency.ANNUALLY)
    assert rate.as_decimal == Decimal("0.0525")


def test_interest_rate_numeric_creation_percentage():
    rate = InterestRate(5.25, CompoundingFrequency.ANNUALLY, as_percentage=True)
    assert rate.as_decimal == Decimal("0.0525")


def test_interest_rate_numeric_creation_stores_frequency():
    rate = InterestRate(0.05, CompoundingFrequency.MONTHLY)
    assert rate.period == CompoundingFrequency.MONTHLY


def test_interest_rate_numeric_creation_missing_period_raises_error():
    with pytest.raises(ValueError, match="period is required when rate is numeric"):
        InterestRate(0.05)


# Mixed creation tests
def test_interest_rate_string_vs_numeric_equivalent():
    string_rate = InterestRate("5.25% a")
    numeric_rate = InterestRate(5.25, CompoundingFrequency.ANNUALLY, as_percentage=True)
    assert string_rate.as_decimal == numeric_rate.as_decimal
    assert string_rate.period == numeric_rate.period


# Conversion tests
def test_interest_rate_to_monthly_from_annual():
    annual_rate = InterestRate("6% a")
    monthly_rate = annual_rate.to_monthly()
    # Should be approximately 0.4868% monthly
    assert abs(monthly_rate.as_percentage - Decimal("0.4868")) < Decimal("0.001")


def test_interest_rate_to_monthly_returns_monthly_frequency():
    annual_rate = InterestRate("6% a")
    monthly_rate = annual_rate.to_monthly()
    assert monthly_rate.period == CompoundingFrequency.MONTHLY


def test_interest_rate_to_daily_from_annual():
    annual_rate = InterestRate("5% a")
    daily_rate = annual_rate.to_daily()
    # Should be approximately 0.0134% daily
    assert abs(daily_rate.as_percentage - Decimal("0.0134")) < Decimal("0.001")


def test_interest_rate_to_daily_returns_daily_frequency():
    annual_rate = InterestRate("5% a")
    daily_rate = annual_rate.to_daily()
    assert daily_rate.period == CompoundingFrequency.DAILY


def test_interest_rate_to_annual_from_monthly():
    monthly_rate = InterestRate("0.5% m")
    annual_rate = monthly_rate.to_annual()
    # Should be approximately 6.17% annually (0.5% compounded 12 times)
    assert abs(annual_rate.as_percentage - Decimal("6.17")) < Decimal("0.01")


def test_interest_rate_to_annual_returns_annual_frequency():
    monthly_rate = InterestRate("0.5% m")
    annual_rate = monthly_rate.to_annual()
    assert annual_rate.period == CompoundingFrequency.ANNUALLY


def test_interest_rate_same_frequency_conversion_returns_self():
    rate = InterestRate("5% m")
    monthly_rate = rate.to_monthly()
    assert monthly_rate is rate


def test_interest_rate_to_periodic_rate_monthly():
    annual_rate = InterestRate("6% a")
    periodic_rate = annual_rate.to_periodic_rate(12)
    # Should be approximately 0.004868 monthly
    assert abs(periodic_rate - Decimal("0.004868")) < Decimal("0.000001")


def test_interest_rate_to_periodic_rate_same_frequency():
    monthly_rate = InterestRate("0.5% m")
    periodic_rate = monthly_rate.to_periodic_rate(12)
    assert periodic_rate == monthly_rate.as_decimal


# Comparison tests
def test_interest_rate_equality_same_effective_rate():
    rate1 = InterestRate("6% a")
    rate2 = InterestRate("0.486755% m")  # More precise monthly equivalent of 6% annual
    # These should be approximately equal when converted to effective annual
    assert rate1 == rate2


def test_interest_rate_equality_exact_same_rate():
    rate1 = InterestRate("5% a")
    rate2 = InterestRate("5% a")
    assert rate1 == rate2


def test_interest_rate_less_than_comparison():
    rate1 = InterestRate("5% a")
    rate2 = InterestRate("6% a")
    assert rate1 < rate2


def test_interest_rate_greater_than_comparison():
    rate1 = InterestRate("6% a")
    rate2 = InterestRate("5% a")
    assert rate1 > rate2


def test_interest_rate_less_than_or_equal():
    rate1 = InterestRate("5% a")
    rate2 = InterestRate("6% a")
    rate3 = InterestRate("5% a")
    assert rate1 <= rate2
    assert rate1 <= rate3


def test_interest_rate_greater_than_or_equal():
    rate1 = InterestRate("6% a")
    rate2 = InterestRate("5% a")
    rate3 = InterestRate("6% a")
    assert rate1 >= rate2
    assert rate1 >= rate3


# Display tests
def test_interest_rate_string_representation():
    rate = InterestRate("5.25% a")
    assert str(rate) == "5.250% annually"


def test_interest_rate_string_representation_monthly():
    rate = InterestRate("0.5% m")
    assert str(rate) == "0.500% monthly"


def test_interest_rate_repr_representation():
    rate = InterestRate("5% a")
    repr_str = repr(rate)
    assert "InterestRate(0.05" in repr_str
    assert "CompoundingFrequency.ANNUALLY" in repr_str


# Property tests
def test_interest_rate_as_decimal_property():
    rate = InterestRate("5.25% a")
    assert rate.as_decimal == Decimal("0.0525")


def test_interest_rate_as_percentage_property():
    rate = InterestRate("0.0525 a")
    assert rate.as_percentage == Decimal("5.25")


def test_interest_rate_period_property():
    rate = InterestRate("5% q")
    assert rate.period == CompoundingFrequency.QUARTERLY


# Edge case tests
def test_interest_rate_zero_rate():
    rate = InterestRate("0% a")
    assert rate.as_decimal == Decimal("0.0")
    assert rate.as_percentage == Decimal("0.0")


def test_interest_rate_very_high_rate():
    rate = InterestRate("50% a")
    assert rate.as_decimal == Decimal("0.5")
    assert rate.as_percentage == Decimal("50.0")


def test_interest_rate_very_small_rate():
    rate = InterestRate("0.01% a")
    assert rate.as_decimal == Decimal("0.0001")
    assert rate.as_percentage == Decimal("0.01")


def test_interest_rate_daily_compounding():
    rate = InterestRate("5% d")
    assert rate.period == CompoundingFrequency.DAILY


def test_interest_rate_continuous_compounding():
    rate = InterestRate(5.0, CompoundingFrequency.CONTINUOUS, as_percentage=True)
    annual_rate = rate.to_annual()
    # For continuous compounding: e^r - 1
    # 5% continuous should be approximately 5.127% effective annual
    assert abs(annual_rate.as_percentage - Decimal("5.127")) < Decimal("0.001")


# Conversion accuracy tests
def test_interest_rate_round_trip_conversion():
    original = InterestRate("6% a")
    monthly = original.to_monthly()
    back_to_annual = monthly.to_annual()
    # Should be very close to original (allowing for small rounding differences)
    assert abs(original.as_percentage - back_to_annual.as_percentage) < Decimal("0.01")


def test_interest_rate_compound_frequency_enum_values():
    assert CompoundingFrequency.DAILY.value == 365
    assert CompoundingFrequency.MONTHLY.value == 12
    assert CompoundingFrequency.QUARTERLY.value == 4
    assert CompoundingFrequency.SEMI_ANNUALLY.value == 2
    assert CompoundingFrequency.ANNUALLY.value == 1


# Additional string parsing tests for comprehensive coverage
@pytest.mark.parametrize(
    "rate_string,expected_decimal",
    [
        # Integer values
        ("5% a", Decimal("0.05")),
        ("10% m", Decimal("0.1")),
        ("1 a", Decimal("1")),
        ("0 m", Decimal("0")),
        # Decimal values with different precision
        ("5.0% a", Decimal("0.05")),
        ("5.00% a", Decimal("0.05")),
        ("5.123% a", Decimal("0.05123")),
        ("0.1234567 m", Decimal("0.1234567")),
        # Very small and large values
        ("0.001% a", Decimal("0.00001")),
        ("100% a", Decimal("1.0")),
        ("0.000001 d", Decimal("0.000001")),
    ],
)
def test_interest_rate_string_parsing_precision(rate_string, expected_decimal):
    rate = InterestRate(rate_string)
    assert rate.as_decimal == expected_decimal


def test_interest_rate_string_parsing_all_frequencies():
    # Test all supported frequency abbreviations
    frequencies = {
        "a": CompoundingFrequency.ANNUALLY,
        "m": CompoundingFrequency.MONTHLY,
        "d": CompoundingFrequency.DAILY,
        "q": CompoundingFrequency.QUARTERLY,
        "s": CompoundingFrequency.SEMI_ANNUALLY,
    }

    for abbrev, expected_freq in frequencies.items():
        rate = InterestRate(f"5% {abbrev}")
        assert rate.period == expected_freq


def test_interest_rate_string_parsing_all_full_words():
    # Test all supported full word frequencies
    frequencies = {
        "annual": CompoundingFrequency.ANNUALLY,
        "monthly": CompoundingFrequency.MONTHLY,
        "daily": CompoundingFrequency.DAILY,
        "quarterly": CompoundingFrequency.QUARTERLY,
        "semi-annual": CompoundingFrequency.SEMI_ANNUALLY,
    }

    for word, expected_freq in frequencies.items():
        rate = InterestRate(f"5% {word}")
        assert rate.period == expected_freq


# --- Precision tests ---


def test_precision_none_preserves_full_precision():
    rate = InterestRate("1% m")
    annual = rate._to_effective_annual()
    assert annual == (1 + Decimal("0.01")) ** 12 - 1


def test_precision_quantizes_effective_annual():
    rate = InterestRate("1% m", precision=6)
    assert rate._to_effective_annual() == Decimal("0.126825")


def test_precision_propagates_to_daily_conversion():
    rate = InterestRate("1% m", precision=6)
    daily = rate.to_daily()
    expected_daily = (1 + Decimal("0.126825")) ** (Decimal(1) / Decimal(365)) - 1
    assert daily.as_decimal == expected_daily


def test_precision_propagates_to_monthly_conversion():
    rate = InterestRate("5% a", precision=4)
    monthly = rate.to_monthly()
    assert monthly._precision == 4


def test_rounding_mode_round_down():
    from decimal import ROUND_DOWN

    rate = InterestRate("1% m", precision=6, rounding=ROUND_DOWN)
    annual = rate._to_effective_annual()
    assert annual == Decimal("0.126825")


def test_precision_does_not_alter_stored_rate():
    rate = InterestRate("1% m", precision=6)
    assert rate.as_decimal == Decimal("0.01")


# --- str_style tests ---


# Abbreviated string parsing
@pytest.mark.parametrize(
    "rate_string,expected_decimal,expected_percentage,expected_frequency",
    [
        ("5.25% a.a.", Decimal("0.0525"), Decimal("5.25"), CompoundingFrequency.ANNUALLY),
        ("0.5% a.m.", Decimal("0.005"), Decimal("0.5"), CompoundingFrequency.MONTHLY),
        ("0.0137% a.d.", Decimal("0.000137"), Decimal("0.0137"), CompoundingFrequency.DAILY),
        ("2.75% a.t.", Decimal("0.0275"), Decimal("2.75"), CompoundingFrequency.QUARTERLY),
        ("3% a.s.", Decimal("0.03"), Decimal("3.0"), CompoundingFrequency.SEMI_ANNUALLY),
        ("0.0525 a.a.", Decimal("0.0525"), Decimal("5.25"), CompoundingFrequency.ANNUALLY),
        ("0.004167 a.m.", Decimal("0.004167"), Decimal("0.4167"), CompoundingFrequency.MONTHLY),
    ],
)
def test_interest_rate_abbreviated_string_parsing(
    rate_string, expected_decimal, expected_percentage, expected_frequency
):
    rate = InterestRate(rate_string)
    assert rate.as_decimal == expected_decimal


def test_interest_rate_abbreviated_parsing_stores_percentage():
    rate = InterestRate("5.25% a.a.")
    assert rate.as_percentage == Decimal("5.25")


def test_interest_rate_abbreviated_parsing_stores_frequency():
    rate = InterestRate("0.5% a.m.")
    assert rate.period == CompoundingFrequency.MONTHLY


# Auto-detection of str_style from abbreviated input
def test_interest_rate_abbreviated_input_auto_sets_abbrev_style():
    rate = InterestRate("5% a.a.")
    assert str(rate) == "5.000% a.a."


def test_interest_rate_long_input_keeps_long_style():
    rate = InterestRate("5% a")
    assert str(rate) == "5.000% annually"


# Explicit str_style on numeric constructor
@pytest.mark.parametrize(
    "frequency,expected_label",
    [
        (CompoundingFrequency.ANNUALLY, "a.a."),
        (CompoundingFrequency.MONTHLY, "a.m."),
        (CompoundingFrequency.DAILY, "a.d."),
        (CompoundingFrequency.QUARTERLY, "a.t."),
        (CompoundingFrequency.SEMI_ANNUALLY, "a.s."),
    ],
)
def test_interest_rate_str_style_abbrev_numeric_constructor(frequency, expected_label):
    rate = InterestRate(0.05, frequency, str_style="abbrev")
    assert str(rate) == f"5.000% {expected_label}"


def test_interest_rate_str_style_long_numeric_constructor():
    rate = InterestRate(0.05, CompoundingFrequency.ANNUALLY, str_style="long")
    assert str(rate) == "5.000% annually"


# Round-trip: parse abbreviated -> str outputs abbreviated
@pytest.mark.parametrize(
    "rate_string,expected_str",
    [
        ("5.25% a.a.", "5.250% a.a."),
        ("0.5% a.m.", "0.500% a.m."),
        ("0.0137% a.d.", "0.014% a.d."),
        ("2.75% a.t.", "2.750% a.t."),
        ("3% a.s.", "3.000% a.s."),
    ],
)
def test_interest_rate_abbreviated_round_trip(rate_string, expected_str):
    rate = InterestRate(rate_string)
    assert str(rate) == expected_str


# Style propagation through conversions
def test_interest_rate_abbrev_style_propagates_to_monthly():
    rate = InterestRate("6% a.a.")
    monthly = rate.to_monthly()
    assert "a.m." in str(monthly)


def test_interest_rate_abbrev_style_propagates_to_daily():
    rate = InterestRate("6% a.a.")
    daily = rate.to_daily()
    assert "a.d." in str(daily)


def test_interest_rate_abbrev_style_propagates_to_annual():
    rate = InterestRate("0.5% a.m.")
    annual = rate.to_annual()
    assert "a.a." in str(annual)


def test_interest_rate_long_style_propagates_to_monthly():
    rate = InterestRate("6% a")
    monthly = rate.to_monthly()
    assert "monthly" in str(monthly)


# Invalid str_style
def test_interest_rate_invalid_str_style_raises_error():
    with pytest.raises(ValueError, match="Invalid str_style"):
        InterestRate(0.05, CompoundingFrequency.ANNUALLY, str_style="invalid")


# Default str_style is "long"
def test_interest_rate_default_str_style_is_long():
    rate = InterestRate(0.05, CompoundingFrequency.ANNUALLY)
    assert str(rate) == "5.000% annually"


# --- YearSize tests ---


def test_year_size_enum_values():
    assert YearSize.banker.value == 360
    assert YearSize.commercial.value == 365


def test_year_size_default_is_commercial():
    rate = InterestRate("10% a")
    assert rate.year_size == YearSize.commercial


def test_year_size_banker_stored_on_creation():
    rate = InterestRate("10% a", year_size=YearSize.banker)
    assert rate.year_size == YearSize.banker


def test_year_size_banker_to_daily_uses_360():
    rate = InterestRate("10% a", year_size=YearSize.banker)
    daily = rate.to_daily()
    expected = (1 + Decimal("0.10")) ** (Decimal("1") / Decimal("360")) - 1
    assert daily.as_decimal == expected


def test_year_size_commercial_to_daily_uses_365():
    rate = InterestRate("10% a", year_size=YearSize.commercial)
    daily = rate.to_daily()
    expected = (1 + Decimal("0.10")) ** (Decimal("1") / Decimal("365")) - 1
    assert daily.as_decimal == expected


def test_year_size_banker_daily_rate_higher_than_commercial():
    banker = InterestRate("10% a", year_size=YearSize.banker).to_daily()
    commercial = InterestRate("10% a", year_size=YearSize.commercial).to_daily()
    assert banker.as_decimal > commercial.as_decimal


def test_year_size_banker_daily_to_annual_round_trip():
    original = InterestRate("10% a", year_size=YearSize.banker)
    daily = original.to_daily()
    back = daily.to_annual()
    assert abs(back.as_percentage - Decimal("10")) < Decimal("0.0001")


def test_year_size_banker_effective_annual_from_daily():
    daily_rate = (1 + Decimal("0.10")) ** (Decimal("1") / Decimal("360")) - 1
    rate = InterestRate(daily_rate, CompoundingFrequency.DAILY, year_size=YearSize.banker)
    annual = rate.to_annual()
    assert abs(annual.as_percentage - Decimal("10")) < Decimal("0.001")


def test_year_size_propagates_to_daily():
    rate = InterestRate("10% a", year_size=YearSize.banker)
    daily = rate.to_daily()
    assert daily.year_size == YearSize.banker


def test_year_size_propagates_to_monthly():
    rate = InterestRate("10% a", year_size=YearSize.banker)
    monthly = rate.to_monthly()
    assert monthly.year_size == YearSize.banker


def test_year_size_propagates_to_annual():
    rate = InterestRate("1% m", year_size=YearSize.banker)
    annual = rate.to_annual()
    assert annual.year_size == YearSize.banker


def test_year_size_banker_to_periodic_rate_short_circuits_360():
    daily_dec = Decimal("0.000265")
    rate = InterestRate(daily_dec, CompoundingFrequency.DAILY, year_size=YearSize.banker)
    assert rate.to_periodic_rate(360) == daily_dec


def test_year_size_commercial_to_periodic_rate_short_circuits_365():
    daily_dec = Decimal("0.000261")
    rate = InterestRate(daily_dec, CompoundingFrequency.DAILY, year_size=YearSize.commercial)
    assert rate.to_periodic_rate(365) == daily_dec


def test_year_size_banker_accrue_30_days():
    rate = InterestRate("10% a", year_size=YearSize.banker)
    principal = Money("1000")
    accrued = rate.accrue(principal, 30)
    daily = (1 + Decimal("0.10")) ** (Decimal("1") / Decimal("360")) - 1
    expected = Decimal("1000") * ((1 + daily) ** Decimal("30") - 1)
    assert accrued.real_amount == Money(expected).real_amount


def test_year_size_commercial_accrue_30_days():
    rate = InterestRate("10% a", year_size=YearSize.commercial)
    principal = Money("1000")
    accrued = rate.accrue(principal, 30)
    daily = (1 + Decimal("0.10")) ** (Decimal("1") / Decimal("365")) - 1
    expected = Decimal("1000") * ((1 + daily) ** Decimal("30") - 1)
    assert accrued.real_amount == Money(expected).real_amount


def test_year_size_banker_accrue_higher_than_commercial():
    principal = Money("1000")
    banker_accrued = InterestRate("10% a", year_size=YearSize.banker).accrue(principal, 30)
    commercial_accrued = InterestRate("10% a", year_size=YearSize.commercial).accrue(principal, 30)
    assert banker_accrued > commercial_accrued


def test_year_size_repr_shows_banker():
    rate = InterestRate("10% a", year_size=YearSize.banker)
    assert "year_size=" in repr(rate)
    assert "YearSize.banker" in repr(rate)


def test_year_size_repr_omits_commercial():
    rate = InterestRate("10% a", year_size=YearSize.commercial)
    assert "year_size" not in repr(rate)


def test_year_size_string_parsing_with_banker():
    rate = InterestRate("5.25% a.a.", year_size=YearSize.banker)
    assert rate.year_size == YearSize.banker
    assert rate.as_decimal == Decimal("0.0525")
