"""Tests for Money class - following project patterns."""

from decimal import Decimal

import pytest

from money_warp.money import Money


# Creation tests
@pytest.mark.parametrize(
    "amount,expected",
    [
        ("100.50", Decimal("100.50")),
        (100, Decimal("100.00")),
        (Decimal("100.50"), Decimal("100.50")),
        (100.50, Decimal("100.50")),
    ],
)
def test_money_creation_from_various_types(amount, expected):
    money = Money(amount)
    assert money.real_amount == expected


def test_money_creation_zero_class_method():
    money = Money.zero()
    assert money.real_amount == Decimal("0.00")


def test_money_creation_zero_is_zero():
    money = Money.zero()
    assert money.is_zero()


def test_money_creation_from_cents():
    money = Money.from_cents(12345)
    assert money.real_amount == Decimal("123.45")


# Precision tests
def test_money_high_precision_internal_storage():
    money = Money("100.123456789")
    assert money.raw_amount == Decimal("100.123456789")


def test_money_real_amount_rounds_to_two_decimals():
    money = Money("100.123456789")
    assert money.real_amount == Decimal("100.12")


@pytest.mark.parametrize(
    "amount,expected",
    [
        ("100.125", Decimal("100.13")),  # Round up
        ("100.124", Decimal("100.12")),  # Round down
        ("100.115", Decimal("100.12")),  # Round up
    ],
)
def test_money_precision_rounding(amount, expected):
    money = Money(amount)
    assert money.real_amount == expected


def test_money_debug_precision_shows_both_amounts():
    money = Money("100.123456")
    debug_str = money.debug_precision()
    assert "Internal: 100.123456" in debug_str


def test_money_debug_precision_shows_real_amount():
    money = Money("100.123456")
    debug_str = money.debug_precision()
    assert "Real: 100.12" in debug_str


# Arithmetic tests
def test_money_addition_basic_amounts():
    money1 = Money("100.50")
    money2 = Money("50.25")
    result = money1 + money2
    assert result.real_amount == Decimal("150.75")


def test_money_subtraction_basic_amounts():
    money1 = Money("100.50")
    money2 = Money("50.25")
    result = money1 - money2
    assert result.real_amount == Decimal("50.25")


def test_money_multiplication_by_integer():
    money = Money("100.00")
    result = money * 2
    assert result.real_amount == Decimal("200.00")


def test_money_multiplication_by_decimal():
    money = Money("100.00")
    result = money * Decimal("1.5")
    assert result.real_amount == Decimal("150.00")


def test_money_division_by_integer():
    money = Money("100.00")
    result = money / 2
    assert result.real_amount == Decimal("50.00")


def test_money_division_maintains_high_precision():
    money = Money("100.00")
    result = money / 3
    assert result.raw_amount == Decimal("100.00") / 3


def test_money_division_rounds_real_amount():
    money = Money("100.00")
    result = money / 3
    assert result.real_amount == Decimal("33.33")


def test_money_negation():
    money = Money("100.50")
    result = -money
    assert result.real_amount == Decimal("-100.50")


def test_money_absolute_value():
    money = Money("-100.50")
    result = abs(money)
    assert result.real_amount == Decimal("100.50")


# Comparison tests
def test_money_equality_same_amounts():
    money1 = Money("100.50")
    money2 = Money("100.50")
    assert money1 == money2


def test_money_equality_with_precision_difference():
    money1 = Money("100.501")  # Rounds to 100.50
    money2 = Money("100.504")  # Rounds to 100.50
    assert money1 == money2


def test_money_less_than_comparison():
    money1 = Money("100.00")
    money2 = Money("100.50")
    assert money1 < money2


def test_money_greater_than_comparison():
    money1 = Money("100.50")
    money2 = Money("100.00")
    assert money1 > money2


def test_money_less_than_or_equal_smaller():
    money1 = Money("100.00")
    money2 = Money("100.50")
    assert money1 <= money2


def test_money_less_than_or_equal_equal():
    money1 = Money("100.00")
    money2 = Money("100.00")
    assert money1 <= money2


def test_money_greater_than_or_equal_larger():
    money1 = Money("100.50")
    money2 = Money("100.00")
    assert money1 >= money2


def test_money_greater_than_or_equal_equal():
    money1 = Money("100.50")
    money2 = Money("100.50")
    assert money1 >= money2


# Property tests
def test_money_cents_property_conversion():
    money = Money("123.45")
    assert money.cents == 12345


def test_money_is_positive():
    money = Money("100.50")
    assert money.is_positive()


def test_money_is_negative():
    money = Money("-100.50")
    assert money.is_negative()


def test_money_is_zero():
    money = Money("0.00")
    assert money.is_zero()


def test_money_to_real_money_raw_amount():
    money = Money("100.123456")
    real_money = money.to_real_money()
    assert real_money.raw_amount == Decimal("100.12")


def test_money_to_real_money_real_amount():
    money = Money("100.123456")
    real_money = money.to_real_money()
    assert real_money.real_amount == Decimal("100.12")


# Display tests
@pytest.mark.parametrize(
    "amount,expected",
    [
        ("1234.56", "1,234.56"),
        ("0.00", "0.00"),
        ("999999.99", "999,999.99"),
    ],
)
def test_money_string_representation(amount, expected):
    money = Money(amount)
    assert str(money) == expected


def test_money_repr_representation():
    money = Money("100.123")
    assert repr(money) == "Money(100.123)"


# Edge case tests
def test_money_very_large_amount():
    money = Money("999999999.99")
    assert money.real_amount == Decimal("999999999.99")


def test_money_very_small_amount_rounds_to_zero():
    money = Money("0.001")
    assert money.real_amount == Decimal("0.00")


def test_money_negative_zero_is_zero():
    money = Money("-0.00")
    assert money.is_zero()


def test_money_compound_operations_precision():
    money = Money("100.00")
    result = money / 3 * 3
    # Due to precision, might not be exactly 100.00 but should be close
    assert abs(result.real_amount - Decimal("100.00")) <= Decimal("0.01")
