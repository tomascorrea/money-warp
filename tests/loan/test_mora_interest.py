"""Tests for mora interest: extra daily-compounded interest accrued beyond the due date."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money, Warp


def test_late_payment_produces_separate_mora_interest_item():
    """Paying after the due date should produce both actual_interest and actual_mora_interest items."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    with Warp(loan, datetime(2025, 2, 15)) as warped:
        warped.pay_installment(Money("10500.00"))
        interest_items = [p for p in warped._all_payments if p.category == "actual_interest"]
        mora_items = [p for p in warped._all_payments if p.category == "actual_mora_interest"]

    assert len(interest_items) == 1
    assert len(mora_items) == 1


def test_mora_interest_equals_difference_between_total_and_regular():
    """Mora interest = total compound interest - regular interest up to the due date."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    daily_rate = InterestRate("6% a").to_daily().as_decimal
    regular_interest = Decimal("10000") * ((1 + daily_rate) ** 31 - 1)
    total_interest = Decimal("10000") * ((1 + daily_rate) ** 45 - 1)
    expected_mora = total_interest - regular_interest

    with Warp(loan, datetime(2025, 2, 15)) as warped:
        warped.pay_installment(Money("10500.00"))
        interest_items = [p for p in warped._all_payments if p.category == "actual_interest"]
        mora_items = [p for p in warped._all_payments if p.category == "actual_mora_interest"]

    assert interest_items[0].amount == Money(regular_interest)
    assert mora_items[0].amount == Money(expected_mora)


def test_regular_interest_matches_scheduled_interest():
    """The regular interest portion of a late payment equals the originally scheduled interest."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    scheduled_interest = loan.get_original_schedule()[0].interest_payment

    with Warp(loan, datetime(2025, 2, 15)) as warped:
        warped.pay_installment(Money("10500.00"))
        interest_items = [p for p in warped._all_payments if p.category == "actual_interest"]

    assert interest_items[0].amount == scheduled_interest


@pytest.mark.parametrize(
    "late_days",
    [1, 7, 14, 30],
)
def test_total_interest_on_late_payment_matches_manual_calculation(late_days):
    """Sum of regular + mora matches daily-compounded accrual from disbursement to payment date."""
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_date = datetime(2025, 2, 1)
    disbursement = datetime(2025, 1, 1)

    loan = Loan(principal, rate, [due_date], disbursement_date=disbursement)
    payment_date = due_date + timedelta(days=late_days)
    total_days = (payment_date - disbursement).days

    daily_rate = rate.to_daily().as_decimal
    expected_total = Decimal("10000") * ((1 + daily_rate) ** total_days - 1)

    with Warp(loan, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        all_interest = [p for p in warped._all_payments if p.category in ("actual_interest", "actual_mora_interest")]
        total_interest = sum((p.amount for p in all_interest), Money.zero())

    assert total_interest == Money(expected_total)


def test_on_time_payment_produces_no_mora_interest_item():
    """On-time payment should only produce actual_interest, no mora."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    with Warp(loan, datetime(2025, 2, 1)) as warped:
        warped.pay_installment(Money("10500.00"))
        interest_items = [p for p in warped._all_payments if p.category == "actual_interest"]
        mora_items = [p for p in warped._all_payments if p.category == "actual_mora_interest"]

    assert len(interest_items) == 1
    assert len(mora_items) == 0


def test_early_payment_produces_no_mora_interest_item():
    """anticipate_payment before the due date should produce no mora item."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    with Warp(loan, datetime(2025, 1, 15)) as warped:
        warped.anticipate_payment(Money("5000.00"))
        mora_items = [p for p in warped._all_payments if p.category == "actual_mora_interest"]

    assert len(mora_items) == 0


def test_on_time_interest_unchanged():
    """On-time payment still charges interest exactly up to the due date (regression guard)."""
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_date = datetime(2025, 2, 1)
    disbursement = datetime(2025, 1, 1)

    loan = Loan(principal, rate, [due_date], disbursement_date=disbursement)
    days_to_due = (due_date - disbursement).days

    daily_rate = rate.to_daily().as_decimal
    expected_interest = Decimal("10000") * ((1 + daily_rate) ** days_to_due - 1)

    with Warp(loan, due_date) as warped:
        warped.pay_installment(Money("10500.00"))
        interest_items = [p for p in warped._all_payments if p.category == "actual_interest"]

    assert interest_items[0].amount == Money(expected_interest)
