"""Tests for CreditCard.get_cash_flow()."""

from datetime import datetime, timezone

from money_warp import Money, Warp


def test_cash_flow_contains_purchase(card):
    card.purchase(Money("100.00"), datetime(2024, 1, 5, tzinfo=timezone.utc), "Test")
    with Warp(card, datetime(2024, 1, 6, tzinfo=timezone.utc)) as w:
        cf = w.get_cash_flow()
        items = list(cf)
        assert len(items) == 1
        assert items[0].amount == Money("100.00")
        assert "purchase" in items[0].category


def test_cash_flow_payment_is_negative(card):
    card.pay(Money("200.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 6, tzinfo=timezone.utc)) as w:
        cf = w.get_cash_flow()
        items = list(cf)
        assert items[0].amount == Money("-200.00")


def test_cash_flow_refund_is_negative(card):
    card.refund(Money("50.00"), datetime(2024, 1, 5, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 6, tzinfo=timezone.utc)) as w:
        cf = w.get_cash_flow()
        items = list(cf)
        assert items[0].amount == Money("-50.00")


def test_cash_flow_includes_interest_charge(card):
    card.purchase(Money("1000.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        cf = w.get_cash_flow()
        interest_items = [i for i in cf if "interest_charge" in i.category]
        assert len(interest_items) >= 1
        assert interest_items[0].amount.is_positive()


def test_cash_flow_includes_fine_charge(card):
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        cf = w.get_cash_flow()
        fine_items = [i for i in cf if "fine_charge" in i.category]
        assert len(fine_items) >= 1
        assert fine_items[0].amount.is_positive()
