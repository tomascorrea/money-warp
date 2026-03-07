"""Tests for minimum payment calculation and is_minimum_met."""

from datetime import datetime, timezone
from decimal import Decimal

from money_warp import CreditCard, InterestRate, Money, Warp
from money_warp.billing_cycle import MonthlyBillingCycle


def _make_card(**kwargs):
    defaults = {
        "interest_rate": InterestRate("24% a"),
        "billing_cycle": MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        "minimum_payment_rate": Decimal("0.10"),
        "minimum_payment_floor": Money("25.00"),
        "opening_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return CreditCard(**defaults)


def test_minimum_payment_is_rate_times_balance():
    card = _make_card()
    card.purchase(Money("1000.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        assert w.statements[0].minimum_payment == Money("100.00")


def test_minimum_payment_uses_floor_when_rate_is_too_low():
    card = _make_card()
    card.purchase(Money("100.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        assert w.statements[0].minimum_payment == Money("25.00")


def test_minimum_payment_capped_at_closing_balance():
    card = _make_card()
    card.purchase(Money("10.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        assert w.statements[0].minimum_payment == Money("10.00")


def test_minimum_payment_zero_when_no_balance():
    card = _make_card()
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        assert w.statements[0].minimum_payment == Money.zero()


def test_is_minimum_met_true_when_payment_exceeds_minimum():
    card = _make_card()
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    card.pay(Money("100.00"), datetime(2024, 1, 25, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        assert w.statements[0].is_minimum_met is True


def test_is_minimum_met_false_when_payment_below_minimum():
    card = _make_card()
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    card.pay(Money("10.00"), datetime(2024, 1, 25, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        assert w.statements[0].is_minimum_met is False
