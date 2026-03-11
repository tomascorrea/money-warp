"""Tests for CreditCard creation and validation."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from money_warp import CreditCard, InterestRate, Money
from money_warp.billing_cycle import MonthlyBillingCycle


def test_credit_card_creation_with_defaults():
    card = CreditCard(
        interest_rate=InterestRate("24% a"),
        opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    assert card.interest_rate == InterestRate("24% a")
    assert card.minimum_payment_rate == Decimal("0.15")


def test_credit_card_creation_with_custom_billing_cycle():
    cycle = MonthlyBillingCycle(closing_day=15, payment_due_days=10)
    card = CreditCard(
        interest_rate=InterestRate("18% a"),
        billing_cycle=cycle,
        opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    assert card.billing_cycle is cycle


def test_credit_card_creation_with_credit_limit():
    card = CreditCard(
        interest_rate=InterestRate("24% a"),
        credit_limit=Money("5000.00"),
        opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    assert card.credit_limit == Money("5000.00")


def test_credit_card_creation_invalid_minimum_payment_rate():
    with pytest.raises(ValueError, match="minimum_payment_rate must be between 0 and 1"):
        CreditCard(
            interest_rate=InterestRate("24% a"),
            minimum_payment_rate=Decimal("1.5"),
            opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )


def test_credit_card_creation_negative_fine_rate():
    with pytest.raises(ValueError, match="Interest rate cannot be negative"):
        CreditCard(
            interest_rate=InterestRate("24% a"),
            fine_rate=InterestRate("-1% annual"),
            opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )


def test_credit_card_creation_zero_credit_limit():
    with pytest.raises(ValueError, match="credit_limit must be positive"):
        CreditCard(
            interest_rate=InterestRate("24% a"),
            credit_limit=Money("0.00"),
            opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )


def test_credit_card_initial_balance_is_zero(card):
    assert card._raw_balance() == Money.zero()
