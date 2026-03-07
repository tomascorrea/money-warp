"""Tests for CreditCard + Warp integration."""

from datetime import datetime, timezone

import pytest

from money_warp import CreditCard, InterestRate, Money, NestedWarpError, Warp
from money_warp.billing_cycle import MonthlyBillingCycle


def _make_card():
    return CreditCard(
        interest_rate=InterestRate("24% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        opening_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


def test_warp_returns_credit_card_clone():
    card = _make_card()
    with Warp(card, datetime(2024, 6, 1, tzinfo=timezone.utc)) as warped:
        assert isinstance(warped, CreditCard)
        assert warped is not card


def test_warp_overrides_now():
    card = _make_card()
    target = datetime(2024, 6, 15, tzinfo=timezone.utc)
    with Warp(card, target) as warped:
        assert warped.now() == target


def test_warp_does_not_mutate_original():
    card = _make_card()
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))

    original_items_count = len(card.cash_flow.raw_items())
    with Warp(card, datetime(2024, 3, 1, tzinfo=timezone.utc)) as warped:
        _ = warped.current_balance

    assert len(card.cash_flow.raw_items()) == original_items_count


def test_warp_closes_billing_cycles():
    card = _make_card()
    card.purchase(Money("1000.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 3, 1, tzinfo=timezone.utc)) as warped:
        assert len(warped.statements) == 2


def test_warp_balance_includes_interest():
    card = _make_card()
    card.purchase(Money("1000.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))
    with Warp(card, datetime(2024, 3, 1, tzinfo=timezone.utc)) as warped:
        assert warped.current_balance > Money("1000.00")


def test_nested_warp_same_card_raises():
    card = _make_card()
    with Warp(card, datetime(2024, 3, 1, tzinfo=timezone.utc)), pytest.raises(NestedWarpError):
        Warp(card, datetime(2024, 6, 1, tzinfo=timezone.utc))


def test_sequential_warps_allowed():
    card = _make_card()
    card.purchase(Money("500.00"), datetime(2024, 1, 10, tzinfo=timezone.utc))

    with Warp(card, datetime(2024, 2, 1, tzinfo=timezone.utc)) as w1:
        bal1 = w1.current_balance

    with Warp(card, datetime(2024, 4, 1, tzinfo=timezone.utc)) as w2:
        bal2 = w2.current_balance

    assert bal2 > bal1


def test_warp_credit_card_and_loan_concurrently():
    from money_warp import Loan

    card = _make_card()
    loan = Loan(
        Money("10000"),
        InterestRate("5% annual"),
        [datetime(2024, 2, 1, tzinfo=timezone.utc)],
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(card, datetime(2024, 6, 1, tzinfo=timezone.utc)) as wc, Warp(
        loan, datetime(2024, 6, 1, tzinfo=timezone.utc)
    ) as wl:
        assert isinstance(wc, CreditCard)
        assert isinstance(wl, Loan)
