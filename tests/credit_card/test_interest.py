"""Tests for interest accrual on unpaid credit card balances."""

from datetime import datetime, timezone

from money_warp import CreditCard, InterestRate, Money, Warp
from money_warp.billing_cycle import MonthlyBillingCycle


def _make_card(**kwargs):
    defaults = {
        "interest_rate": InterestRate("24% a"),
        "billing_cycle": MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        "opening_date": datetime(2024, 1, 1, tzinfo=timezone.utc),
    }
    defaults.update(kwargs)
    return CreditCard(**defaults)


def test_no_interest_when_balance_is_zero():
    card = _make_card()
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        stmts = w.statements
        assert len(stmts) == 2
        assert stmts[1].interest_charged == Money.zero()


def test_interest_charged_on_carried_balance():
    card = _make_card()
    card.purchase(Money("1000.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        stmt2 = w.statements[1]
        assert stmt2.interest_charged.is_positive()


def test_interest_uses_daily_compounding():
    card = _make_card()
    card.purchase(Money("1000.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        stmt2 = w.statements[1]
        days = (datetime(2024, 2, 28, tzinfo=timezone.utc) - datetime(2024, 1, 28, tzinfo=timezone.utc)).days
        expected_interest = InterestRate("24% a").accrue(Money("1000.00"), days)
        assert stmt2.interest_charged == expected_interest


def test_interest_reduced_by_partial_payment():
    card = _make_card()
    card.purchase(Money("1000.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    card.pay(Money("600.00"), datetime(2024, 2, 5, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        stmt2 = w.statements[1]
        days = (datetime(2024, 2, 28, tzinfo=timezone.utc) - datetime(2024, 1, 28, tzinfo=timezone.utc)).days
        expected_interest = InterestRate("24% a").accrue(Money("400.00"), days)
        assert stmt2.interest_charged == expected_interest


def test_no_interest_when_fully_paid_before_next_close():
    card = _make_card()
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    card.pay(Money("500.00"), datetime(2024, 2, 5, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        stmt2 = w.statements[1]
        assert stmt2.interest_charged == Money.zero()


def test_interest_increases_closing_balance():
    card = _make_card()
    card.purchase(Money("1000.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 2, 29, tzinfo=timezone.utc)) as w:
        stmt2 = w.statements[1]
        expected = Money("1000.00") + stmt2.interest_charged + stmt2.fine_charged
        assert stmt2.closing_balance == expected


def test_interest_compounds_across_multiple_periods():
    card = _make_card()
    card.purchase(Money("1000.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 3, 29, tzinfo=timezone.utc)) as w:
        stmts = w.statements
        assert len(stmts) == 3
        assert stmts[1].interest_charged.is_positive()
        assert stmts[2].interest_charged.is_positive()
        assert stmts[2].closing_balance > stmts[1].closing_balance
