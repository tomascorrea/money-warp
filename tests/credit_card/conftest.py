"""Shared fixtures for credit card tests."""

from datetime import datetime, timezone

import pytest

from money_warp import CreditCard, InterestRate, Money
from money_warp.billing_cycle import MonthlyBillingCycle


@pytest.fixture
def card():
    """A basic credit card opened Jan 1 2024 with closing day 28."""
    return CreditCard(
        interest_rate=InterestRate("24% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def card_with_limit():
    """Credit card with a $5 000 credit limit."""
    return CreditCard(
        interest_rate=InterestRate("24% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        credit_limit=Money("5000.00"),
    )


@pytest.fixture
def card_with_purchases(card):
    """Card with two purchases in the first billing period."""
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc), "Electronics")
    card.purchase(Money("200.00"), datetime(2024, 1, 20, tzinfo=timezone.utc), "Groceries")
    return card
