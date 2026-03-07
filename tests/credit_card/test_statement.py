"""Tests for CreditCard statement generation."""

from datetime import datetime, timezone
from decimal import Decimal

from money_warp import CreditCard, InterestRate, Money, Warp
from money_warp.billing_cycle import MonthlyBillingCycle


def test_no_statements_before_first_closing(card):
    with Warp(card, datetime(2024, 1, 10, tzinfo=timezone.utc)) as w:
        assert w.statements == []


def test_single_statement_after_first_closing(card_with_purchases):
    card = card_with_purchases
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        stmts = w.statements
        assert len(stmts) == 1
        assert stmts[0].period_number == 1


def test_statement_totals_match_transactions(card_with_purchases):
    card = card_with_purchases
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        stmt = w.statements[0]
        assert stmt.purchases_total == Money("700.00")
        assert stmt.payments_total == Money.zero()
        assert stmt.refunds_total == Money.zero()


def test_statement_closing_balance_first_period(card_with_purchases):
    card = card_with_purchases
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        stmt = w.statements[0]
        assert stmt.closing_balance == Money("700.00")


def test_statement_previous_balance_first_period(card_with_purchases):
    card = card_with_purchases
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        stmt = w.statements[0]
        assert stmt.previous_balance == Money.zero()


def test_statement_minimum_payment_proportional():
    card = CreditCard(
        interest_rate=InterestRate("24% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        minimum_payment_rate=Decimal("0.10"),
        minimum_payment_floor=Money("25.00"),
        opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    card.purchase(Money("1000.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        stmt = w.statements[0]
        assert stmt.minimum_payment == Money("100.00")


def test_statement_minimum_payment_floor_applied():
    card = CreditCard(
        interest_rate=InterestRate("24% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        minimum_payment_rate=Decimal("0.10"),
        minimum_payment_floor=Money("25.00"),
        opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    card.purchase(Money("100.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        stmt = w.statements[0]
        assert stmt.minimum_payment == Money("25.00")


def test_statement_minimum_payment_capped_at_balance():
    card = CreditCard(
        interest_rate=InterestRate("24% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        minimum_payment_floor=Money("25.00"),
        opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    card.purchase(Money("10.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        stmt = w.statements[0]
        assert stmt.minimum_payment == Money("10.00")


def test_statement_due_date():
    card = CreditCard(
        interest_rate=InterestRate("24% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    card.purchase(Money("100.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        stmt = w.statements[0]
        assert stmt.due_date.month == 2
        assert stmt.due_date.day == 12


def test_two_statements_after_two_cycles(card_with_purchases):
    card = card_with_purchases
    with Warp(card, datetime(2024, 3, 1, tzinfo=timezone.utc)) as w:
        assert len(w.statements) == 2


def test_statement_with_payment_in_period():
    card = CreditCard(
        interest_rate=InterestRate("24% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    card.pay(Money("200.00"), datetime(2024, 1, 20, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 1, 29, tzinfo=timezone.utc)) as w:
        stmt = w.statements[0]
        assert stmt.purchases_total == Money("500.00")
        assert stmt.payments_total == Money("200.00")
        assert stmt.closing_balance == Money("300.00")
