"""Tests for CreditCard.pay()."""

from datetime import datetime, timezone

import pytest

from money_warp import Money, Warp


def test_payment_reduces_balance(card_with_purchases):
    card = card_with_purchases
    card.pay(Money("300.00"), datetime(2024, 1, 25, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 26, tzinfo=timezone.utc)) as w:
        assert w._raw_balance() == Money("400.00")


def test_full_payment_zeroes_balance(card_with_purchases):
    card = card_with_purchases
    card.pay(Money("700.00"), datetime(2024, 1, 25, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 26, tzinfo=timezone.utc)) as w:
        assert w._raw_balance() == Money("0.00")


def test_payment_zero_amount_raises(card):
    with pytest.raises(ValueError, match="Payment amount must be positive"):
        card.pay(Money("0.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))


def test_payment_negative_amount_raises(card):
    with pytest.raises(ValueError, match="Payment amount must be positive"):
        card.pay(Money("-50.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))


def test_payment_stores_category(card):
    card.pay(Money("100.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))
    assert card.cash_flow.raw_items()[0].category == "payment"
