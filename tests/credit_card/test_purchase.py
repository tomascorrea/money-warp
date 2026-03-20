"""Tests for CreditCard.purchase()."""

from datetime import datetime, timezone

import pytest

from money_warp import Money, Warp


def test_purchase_increases_balance(card):
    card.purchase(Money("100.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 6, tzinfo=timezone.utc)) as w:
        assert w._raw_balance() == Money("100.00")


def test_multiple_purchases_accumulate(card):
    card.purchase(Money("100.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))
    card.purchase(Money("250.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 11, tzinfo=timezone.utc)) as w:
        assert w._raw_balance() == Money("350.00")


def test_purchase_zero_amount_raises(card):
    with pytest.raises(ValueError, match="Purchase amount must be positive"):
        card.purchase(Money("0.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))


def test_purchase_negative_amount_raises(card):
    with pytest.raises(ValueError, match="Purchase amount must be positive"):
        card.purchase(Money("-50.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))


def test_purchase_exceeding_credit_limit_raises(card_with_limit):
    with pytest.raises(ValueError, match="exceed credit limit"):
        card_with_limit.purchase(Money("5001.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))


def test_purchase_within_credit_limit_succeeds(card_with_limit):
    card_with_limit.purchase(Money("4999.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))
    with Warp(card_with_limit, datetime(2024, 1, 6, tzinfo=timezone.utc)) as w:
        assert w._raw_balance() == Money("4999.00")


def test_purchase_stores_description(card):
    card.purchase(Money("50.00"), datetime(2024, 1, 5, tzinfo=timezone.utc), "Coffee shop")
    assert card.cash_flow.raw_items()[0].description == "Coffee shop"


def test_purchase_stores_category(card):
    card.purchase(Money("50.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))
    assert "purchase" in card.cash_flow.raw_items()[0].category
