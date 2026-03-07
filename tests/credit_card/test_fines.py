"""Tests for late-payment fines on credit cards."""

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
        "fine_rate": Decimal("0.02"),
        "opening_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return CreditCard(**defaults)


def test_no_fine_when_minimum_is_met():
    card = _make_card()
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    card.pay(Money("60.00"), datetime(2024, 2, 5, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        stmt2 = w.statements[1]
        assert stmt2.fine_charged == Money.zero()


def test_fine_applied_when_minimum_not_met():
    card = _make_card()
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        stmt2 = w.statements[1]
        minimum = w.statements[0].minimum_payment
        expected_fine = Money(minimum.raw_amount * Decimal("0.02"))
        assert stmt2.fine_charged == expected_fine


def test_fine_increases_balance():
    card = _make_card()
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        stmt2 = w.statements[1]
        assert stmt2.fine_charged.is_positive()
        assert stmt2.closing_balance > Money("500.00")


def test_no_fine_when_balance_is_zero():
    card = _make_card()
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        stmt2 = w.statements[1]
        assert stmt2.fine_charged == Money.zero()


def test_fine_not_applied_for_first_statement():
    card = _make_card()
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        stmt1 = w.statements[0]
        assert stmt1.fine_charged == Money.zero()


def test_partial_payment_below_minimum_triggers_fine():
    card = _make_card()
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    card.pay(Money("10.00"), datetime(2024, 2, 5, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        stmt2 = w.statements[1]
        assert stmt2.fine_charged.is_positive()
