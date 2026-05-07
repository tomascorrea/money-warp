"""Tests for the Percentage class — non-temporal, non-compounding percentages."""

from decimal import Decimal

import pytest

from money_warp import CompoundingFrequency, InterestRate, Money, Percentage, Rate


# ===========================================================================
# Construction — accepted string formats
# ===========================================================================


@pytest.mark.parametrize(
    "rate_string,expected_decimal",
    [
        ("5%", Decimal("0.05")),
        ("5.5%", Decimal("0.055")),
        ("0.5%", Decimal("0.005")),
        ("5.000%", Decimal("0.05")),
        ("100%", Decimal("1")),
        ("0%", Decimal("0")),
        ("6.123%", Decimal("0.06123")),
    ],
)
def test_percentage_construction_valid_string(rate_string, expected_decimal):
    """Strings of the form '<n>%' should construct correctly."""
    p = Percentage(rate_string)
    assert p.as_decimal() == expected_decimal


def test_percentage_construction_with_extra_spaces():
    """Surrounding whitespace is tolerated."""
    p = Percentage("  5%  ")
    assert p.as_decimal() == Decimal("0.05")


def test_percentage_zero_allowed():
    """Zero is a valid (and useful) percentage — represents 'no fee'."""
    p = Percentage("0%")
    assert p.as_decimal() == Decimal("0")


# ===========================================================================
# Construction — rejected numeric inputs (the core design decision)
# ===========================================================================


@pytest.mark.parametrize(
    "numeric_input",
    [5, 0.05, 0, Decimal("0.05"), Decimal("5")],
    ids=["int_5", "float_0.05", "int_0", "decimal_0.05", "decimal_5"],
)
def test_percentage_rejects_numeric_input(numeric_input):
    """Numeric inputs are rejected to avoid the '5' vs '0.05' ambiguity."""
    with pytest.raises(TypeError, match="requires a string"):
        Percentage(numeric_input)


# ===========================================================================
# Construction — rejected string formats
# ===========================================================================


@pytest.mark.parametrize(
    "invalid_string",
    [
        "5",
        "0.05",
        "5.5",
        "5 %",
        "abc",
        "",
        "%",
        "%5",
        "5%%",
        "5percent",
    ],
)
def test_percentage_rejects_string_without_pct_suffix(invalid_string):
    """Bare numbers and malformed strings are rejected."""
    with pytest.raises(ValueError, match="Invalid Percentage format"):
        Percentage(invalid_string)


def test_percentage_rejects_negative_string():
    """Negative percentages are rejected (no leading minus accepted)."""
    with pytest.raises(ValueError):
        Percentage("-5%")


@pytest.mark.parametrize(
    "temporal_string",
    [
        "5% a",
        "5% annual",
        "5% m",
        "5% monthly",
        "5% d",
        "5% daily",
        "5% q",
        "5% quarterly",
        "5% s",
        "5% semi-annual",
        "5% a.a.",
        "5% a.m.",
        "5% a.d.",
        "5% a.t.",
        "5% a.s.",
        "5% A.A.",  # case-insensitive detection
    ],
)
def test_percentage_rejects_temporal_string_with_helpful_error(temporal_string):
    """Temporal suffixes get a pointed error pointing at Rate/InterestRate."""
    with pytest.raises(ValueError, match="cannot parse temporal rate"):
        Percentage(temporal_string)


# ===========================================================================
# Accessors
# ===========================================================================


def test_percentage_as_decimal_basic():
    assert Percentage("5%").as_decimal() == Decimal("0.05")


def test_percentage_as_percentage_basic():
    assert Percentage("5%").as_percentage() == Decimal("5")


def test_percentage_as_decimal_with_explicit_precision():
    p = Percentage("6.123%")
    assert p.as_decimal(2) == Decimal("0.06")


def test_percentage_as_percentage_with_explicit_precision():
    p = Percentage("6.125%")
    assert p.as_percentage(2) == Decimal("6.13")


def test_percentage_as_decimal_with_constructor_precision():
    p = Percentage("6.123%", precision=2)
    assert p.as_decimal() == Decimal("0.06")


def test_percentage_as_percentage_with_constructor_precision():
    p = Percentage("6.125%", precision=2)
    assert p.as_percentage() == Decimal("6.13")


def test_percentage_explicit_precision_overrides_constructor():
    p = Percentage("6.123%", precision=2)
    assert p.as_decimal(4) == Decimal("0.0612")


# ===========================================================================
# API minimality — what the type intentionally does NOT have
# ===========================================================================


@pytest.mark.parametrize(
    "missing_method",
    ["to_daily", "to_monthly", "to_annual", "to_periodic_rate", "_to_effective_annual", "accrue", "apply", "as_float"],
)
def test_percentage_does_not_have_temporal_or_application_methods(missing_method):
    """Compile-time absence: callers can't reach for these on a Percentage.

    This is the key value of the separate-class design — the type checker
    blocks `pct.to_daily()` / `pct.accrue(...)` / `pct.apply(...)` before
    runtime, without any need for a runtime guard.
    """
    p = Percentage("5%")
    assert not hasattr(p, missing_method)


# ===========================================================================
# String / repr — round-trip and formatting
# ===========================================================================


def test_percentage_str_default_two_decimals():
    assert str(Percentage("5%")) == "5.00%"


@pytest.mark.parametrize(
    "str_decimals,expected",
    [
        (0, "5%"),
        (1, "5.0%"),
        (2, "5.00%"),
        (3, "5.000%"),
        (5, "5.00000%"),
    ],
)
def test_percentage_str_decimals_respected(str_decimals, expected):
    assert str(Percentage("5%", str_decimals=str_decimals)) == expected


def test_percentage_repr_basic():
    assert repr(Percentage("5%")) == "Percentage('5.00%')"


def test_percentage_repr_includes_precision_when_set():
    assert "precision=4" in repr(Percentage("5%", precision=4))


def test_percentage_repr_includes_str_decimals_when_non_default():
    assert "str_decimals=4" in repr(Percentage("5%", str_decimals=4))


def test_percentage_string_round_trip():
    original = Percentage("5%")
    parsed = Percentage(str(original))
    assert parsed == original


def test_percentage_string_round_trip_within_str_decimals():
    """Round-trip is stable for values that fit in the configured str_decimals.

    The default `str_decimals=2` formats the canonical string with 2 decimals,
    so values up to that precision round-trip exactly.
    """
    original = Percentage("6.12%")
    parsed = Percentage(str(original))
    assert parsed == original


def test_percentage_string_round_trip_high_precision_with_matching_str_decimals():
    """For higher-precision values, set `str_decimals` to match the precision."""
    original = Percentage("6.123%", str_decimals=4)
    parsed = Percentage(str(original), str_decimals=4)
    assert parsed == original


def test_percentage_str_truncates_beyond_str_decimals():
    """When the value has more precision than `str_decimals`, `__str__` rounds.

    This is a deliberate tradeoff: the default 2-decimal display matches typical
    financial UIs. For lossless round-trip of high-precision values, configure
    `str_decimals` to cover the precision you need.
    """
    p = Percentage("6.129%")  # decimal_rate = 0.06129
    assert str(p) == "6.13%"  # rounded to 2 decimals via ROUND_HALF_UP


# ===========================================================================
# Comparisons
# ===========================================================================


def test_percentage_equality_same_value():
    assert Percentage("5%") == Percentage("5%")


def test_percentage_equality_equivalent_strings():
    assert Percentage("5%") == Percentage("5.000%")


def test_percentage_inequality_different_value():
    assert Percentage("5%") != Percentage("6%")


def test_percentage_ordering_lt():
    assert Percentage("5%") < Percentage("6%")


def test_percentage_ordering_le():
    assert Percentage("5%") <= Percentage("5%")
    assert Percentage("5%") <= Percentage("6%")


def test_percentage_ordering_gt():
    assert Percentage("6%") > Percentage("5%")


def test_percentage_ordering_ge():
    assert Percentage("5%") >= Percentage("5%")
    assert Percentage("6%") >= Percentage("5%")


def test_percentage_hash_equal_for_equal_values():
    assert hash(Percentage("5%")) == hash(Percentage("5.000%"))


def test_percentage_hashable_in_set():
    """Percentages should work as dict keys / set members."""
    s = {Percentage("5%"), Percentage("5.000%"), Percentage("6%")}
    assert len(s) == 2


# ===========================================================================
# Cross-type comparisons return NotImplemented (== is False, ordering raises)
# ===========================================================================


def test_percentage_not_equal_to_rate():
    """Cross-type equality returns NotImplemented, which Python evaluates as False."""
    assert Percentage("5%") != Rate("5% a.a.")


def test_percentage_not_equal_to_interest_rate():
    assert Percentage("5%") != InterestRate("5% a.a.")


def test_percentage_not_equal_to_decimal():
    assert Percentage("5%") != Decimal("0.05")


def test_percentage_ordering_with_rate_raises():
    """Cross-type ordering fails — Percentage and Rate live in different dimensions.

    Percentage returns NotImplemented; Rate's reflected operator then tries
    to call ``_to_effective_annual`` on the Percentage and fails. Either way,
    the consumer cannot compare them — which is the desired contract.
    """
    with pytest.raises((TypeError, AttributeError)):
        _ = Percentage("5%") < Rate("5% a.a.")


def test_percentage_ordering_with_interest_rate_raises():
    with pytest.raises((TypeError, AttributeError)):
        _ = Percentage("5%") < InterestRate("5% a.a.")


# ===========================================================================
# Typical usage pattern — manual application over Money
# ===========================================================================


def test_percentage_typical_usage_with_money():
    """Spec example: MDR applied over a transaction amount.

    Percentage exposes no `apply` method by design — the consumer does the
    multiplication explicitly so the boundary between 'I have a percentage'
    and 'I'm computing a fee in money' stays visible.
    """
    mdr = Percentage("5%")
    amount = Money("1000")
    fee = Money(amount.raw_amount * mdr.as_decimal())
    assert fee == Money("50")


def test_percentage_zero_application_returns_zero():
    pct = Percentage("0%")
    amount = Money("1000")
    fee = Money(amount.raw_amount * pct.as_decimal())
    assert fee == Money("0")


def test_percentage_application_preserves_full_precision():
    pct = Percentage("0.05%")
    amount = Money("123.456789")
    fee = Money(amount.raw_amount * pct.as_decimal())
    expected = Decimal("123.456789") * Decimal("0.0005")
    assert fee.raw_amount == expected


# ===========================================================================
# Frequency enum sanity check — Percentage has no period concept
# ===========================================================================


def test_percentage_does_not_expose_period_attribute():
    """Percentage is intentionally period-less; it should not carry a period."""
    p = Percentage("5%")
    assert not hasattr(p, "period")


def test_percentage_unrelated_to_compounding_frequency():
    """CompoundingFrequency is for Rate/InterestRate; Percentage doesn't use it."""
    p = Percentage("5%")
    for freq in CompoundingFrequency:
        assert getattr(p, "period", None) != freq
