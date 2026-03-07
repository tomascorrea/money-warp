"""Tests for CreditCard.refund()."""

from datetime import datetime, timezone

import pytest

from money_warp import Money, Warp


def test_refund_reduces_balance(card_with_purchases):
    card = card_with_purchases
    card.refund(Money("200.00"), datetime(2024, 1, 22, tzinfo=timezone.utc), "Return groceries")
    with Warp(card, datetime(2024, 1, 23, tzinfo=timezone.utc)) as w:
        assert w._raw_balance(w.now()) == Money("500.00")


def test_refund_zero_amount_raises(card):
    with pytest.raises(ValueError, match="Refund amount must be positive"):
        card.refund(Money("0.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))


def test_refund_stores_category(card):
    card.refund(Money("50.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))
    assert card._all_items[0].category == "refund"
