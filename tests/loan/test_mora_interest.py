"""Tests for mora interest: extra daily-compounded interest accrued beyond the due date."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money, MoraStrategy, Warp


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


# --- Custom mora interest rate tests ---


def test_mora_rate_defaults_to_base_rate():
    """When mora_interest_rate is not provided, it defaults to interest_rate."""
    rate = InterestRate("6% a")
    loan = Loan(
        Money("10000.00"),
        rate,
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    assert loan.mora_interest_rate is rate


def test_mora_strategy_defaults_to_compound():
    """When mora_strategy is not provided, it defaults to COMPOUND."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    assert loan.mora_strategy == MoraStrategy.COMPOUND


def test_on_time_payment_unaffected_by_custom_mora_rate():
    """A custom mora rate has zero effect when the payment is on time."""
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("24% a")
    disbursement = datetime(2025, 1, 1)
    due_date = datetime(2025, 2, 1)

    loan = Loan(
        Money("10000.00"),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
    )

    daily_base = base_rate.to_daily().as_decimal
    days = (due_date - disbursement).days
    expected_interest = Decimal("10000") * ((1 + daily_base) ** days - 1)

    with Warp(loan, due_date) as warped:
        warped.pay_installment(Money("10500.00"))
        interest_items = [p for p in warped._all_payments if p.category == "actual_interest"]
        mora_items = [p for p in warped._all_payments if p.category == "actual_mora_interest"]

    assert interest_items[0].amount == Money(expected_interest)
    assert len(mora_items) == 0


def test_mora_with_custom_rate_compound_strategy():
    """COMPOUND: mora_rate applied to (principal + regular_interest) for late days."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("12% a")
    disbursement = datetime(2025, 1, 1)
    due_date = datetime(2025, 2, 1)
    payment_date = datetime(2025, 2, 15)

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
        mora_strategy=MoraStrategy.COMPOUND,
    )

    regular_days = (due_date - disbursement).days  # 31
    mora_days = (payment_date - due_date).days  # 14

    daily_base = base_rate.to_daily().as_decimal
    daily_mora = mora_rate.to_daily().as_decimal

    expected_regular = principal * ((1 + daily_base) ** regular_days - 1)
    accumulated = principal + expected_regular
    expected_mora = accumulated * ((1 + daily_mora) ** mora_days - 1)

    with Warp(loan, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        mora_items = [p for p in warped._all_payments if p.category == "actual_mora_interest"]

    assert mora_items[0].amount == Money(expected_mora)


def test_mora_with_custom_rate_simple_strategy():
    """SIMPLE: mora_rate applied to principal only for late days."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("12% a")
    disbursement = datetime(2025, 1, 1)
    due_date = datetime(2025, 2, 1)
    payment_date = datetime(2025, 2, 15)

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
        mora_strategy=MoraStrategy.SIMPLE,
    )

    mora_days = (payment_date - due_date).days  # 14
    daily_mora = mora_rate.to_daily().as_decimal
    expected_mora = principal * ((1 + daily_mora) ** mora_days - 1)

    with Warp(loan, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        mora_items = [p for p in warped._all_payments if p.category == "actual_mora_interest"]

    assert mora_items[0].amount == Money(expected_mora)


def test_simple_vs_compound_mora_compound_produces_more():
    """With the same custom mora rate, COMPOUND produces more mora than SIMPLE."""
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("12% a")
    disbursement = datetime(2025, 1, 1)
    due_date = datetime(2025, 2, 1)
    payment_date = datetime(2025, 2, 15)

    loan_compound = Loan(
        Money("10000.00"),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
        mora_strategy=MoraStrategy.COMPOUND,
    )

    loan_simple = Loan(
        Money("10000.00"),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
        mora_strategy=MoraStrategy.SIMPLE,
    )

    with Warp(loan_compound, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        mora_compound = [p for p in warped._all_payments if p.category == "actual_mora_interest"][0].amount

    with Warp(loan_simple, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        mora_simple = [p for p in warped._all_payments if p.category == "actual_mora_interest"][0].amount

    assert mora_compound > mora_simple


def test_regular_interest_unchanged_regardless_of_mora_rate():
    """The regular interest portion is always computed with the base rate, not the mora rate."""
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("24% a")
    disbursement = datetime(2025, 1, 1)
    due_date = datetime(2025, 2, 1)
    payment_date = datetime(2025, 2, 15)

    regular_days = (due_date - disbursement).days
    daily_base = base_rate.to_daily().as_decimal
    expected_regular = Decimal("10000") * ((1 + daily_base) ** regular_days - 1)

    loan = Loan(
        Money("10000.00"),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
    )

    with Warp(loan, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        interest_items = [p for p in warped._all_payments if p.category == "actual_interest"]

    assert interest_items[0].amount == Money(expected_regular)


@pytest.mark.parametrize(
    "mora_rate_str,strategy",
    [
        ("8% a", MoraStrategy.SIMPLE),
        ("12% a", MoraStrategy.SIMPLE),
        ("24% a", MoraStrategy.SIMPLE),
        ("8% a", MoraStrategy.COMPOUND),
        ("12% a", MoraStrategy.COMPOUND),
        ("24% a", MoraStrategy.COMPOUND),
    ],
)
def test_total_interest_with_custom_mora_rate_matches_manual(mora_rate_str, strategy):
    """Sum of regular + mora matches manual calculation for various rates and strategies."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate(mora_rate_str)
    disbursement = datetime(2025, 1, 1)
    due_date = datetime(2025, 2, 1)
    payment_date = datetime(2025, 2, 15)

    regular_days = (due_date - disbursement).days
    mora_days = (payment_date - due_date).days

    daily_base = base_rate.to_daily().as_decimal
    daily_mora = mora_rate.to_daily().as_decimal

    expected_regular = principal * ((1 + daily_base) ** regular_days - 1)
    if strategy == MoraStrategy.COMPOUND:
        accumulated = principal + expected_regular
        expected_mora = accumulated * ((1 + daily_mora) ** mora_days - 1)
    else:
        expected_mora = principal * ((1 + daily_mora) ** mora_days - 1)

    expected_total = expected_regular + expected_mora

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
        mora_strategy=strategy,
    )

    with Warp(loan, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        all_interest = [p for p in warped._all_payments if p.category in ("actual_interest", "actual_mora_interest")]
        total_interest = sum((p.amount for p in all_interest), Money.zero())

    assert total_interest == Money(expected_total)


# --- accrued_interest / current_balance with custom mora rate ---


def test_accrued_interest_uses_mora_rate_when_past_due():
    """accrued_interest should reflect the mora rate for days beyond the due date."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("24% a")
    disbursement = datetime(2025, 1, 1)
    due_date = datetime(2025, 2, 1)
    check_date = datetime(2025, 2, 15)

    regular_days = (due_date - disbursement).days
    mora_days = (check_date - due_date).days

    daily_base = base_rate.to_daily().as_decimal
    daily_mora = mora_rate.to_daily().as_decimal

    regular = principal * ((1 + daily_base) ** regular_days - 1)
    mora = (principal + regular) * ((1 + daily_mora) ** mora_days - 1)
    expected = regular + mora

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
    )

    with Warp(loan, check_date) as warped:
        assert warped.accrued_interest == Money(expected)


def test_accrued_interest_uses_base_rate_when_not_late():
    """Before the due date, a custom mora rate has no effect on accrued_interest."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("24% a")
    disbursement = datetime(2025, 1, 1)
    due_date = datetime(2025, 2, 1)
    check_date = datetime(2025, 1, 20)

    days = (check_date - disbursement).days
    daily_base = base_rate.to_daily().as_decimal
    expected = principal * ((1 + daily_base) ** days - 1)

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
    )

    with Warp(loan, check_date) as warped:
        assert warped.accrued_interest == Money(expected)


def test_current_balance_reflects_mora_rate_when_past_due():
    """current_balance should include mora-rate interest when past due."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("24% a")
    disbursement = datetime(2025, 1, 1)
    due_date = datetime(2025, 2, 1)
    check_date = datetime(2025, 2, 15)

    regular_days = (due_date - disbursement).days
    mora_days = (check_date - due_date).days

    daily_base = base_rate.to_daily().as_decimal
    daily_mora = mora_rate.to_daily().as_decimal

    regular = principal * ((1 + daily_base) ** regular_days - 1)
    mora = (principal + regular) * ((1 + daily_mora) ** mora_days - 1)
    expected_balance = principal + regular + mora

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
        fine_rate=Decimal("0"),
    )

    with Warp(loan, check_date) as warped:
        assert warped.current_balance == Money(expected_balance)
