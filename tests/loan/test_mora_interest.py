"""Tests for mora interest: simple interest on the installment payment amount."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money, MoraStrategy, Warp


def test_late_payment_produces_separate_mora_interest_item():
    """Paying after the due date should produce both interest and mora_interest items."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("10500.00"))
        settlement = warped.settlements[-1]

    assert settlement.interest_paid != Money.zero()
    assert settlement.mora_paid != Money.zero()


def test_mora_interest_is_simple_on_the_installment_amount():
    """Mora is payment amount × daily mora rate × days late, not compound interest on principal."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    daily_rate = InterestRate("6% a").to_daily().as_decimal()
    regular_interest = Decimal("10000") * ((1 + daily_rate) ** 31 - 1)
    payment_amount = loan.get_original_schedule()[0].payment_amount.raw_amount
    expected_mora = payment_amount * daily_rate * Decimal(14)

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("10500.00"))
        settlement = warped.settlements[-1]

    assert settlement.interest_paid == Money(regular_interest)
    assert settlement.mora_paid == Money(expected_mora)


def test_regular_interest_matches_scheduled_interest():
    """The regular interest portion of a late payment equals the originally scheduled interest."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    scheduled_interest = loan.get_original_schedule()[0].interest_payment

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("10500.00"))
        settlement = warped.settlements[-1]

    assert settlement.interest_paid == scheduled_interest


@pytest.mark.parametrize(
    "late_days",
    [1, 7, 14, 30],
)
def test_total_interest_on_late_payment_matches_manual_calculation(late_days):
    """Regular interest compounds to the due date; mora is linear on the installment amount."""
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_date = date(2025, 2, 1)
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)

    loan = Loan(principal, rate, [due_date], disbursement_date=disbursement)
    payment_date = due_date + timedelta(days=late_days)
    regular_days = (due_date - disbursement.date()).days

    daily_rate = rate.to_daily().as_decimal()
    expected_regular = Decimal("10000") * ((1 + daily_rate) ** regular_days - 1)
    payment_amount = loan.get_original_schedule()[0].payment_amount.raw_amount
    expected_mora = payment_amount * daily_rate * Decimal(late_days)

    with Warp(loan, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        settlement = warped.settlements[-1]

    assert settlement.interest_paid == Money(expected_regular)
    assert settlement.mora_paid == Money(expected_mora)


def test_on_time_payment_produces_no_mora_interest_item():
    """On-time payment should only produce interest, no mora."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("10500.00"))
        settlement = warped.settlements[-1]

    assert settlement.interest_paid != Money.zero()
    assert settlement.mora_paid == Money.zero()


def test_early_payment_produces_no_mora_interest_item():
    """anticipate_payment before the due date should produce no mora item."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan, datetime(2025, 1, 15, tzinfo=timezone.utc)) as warped:
        warped.anticipate_payment(Money("5000.00"))
        settlement = warped.settlements[-1]

    assert settlement.mora_paid == Money.zero()


def test_on_time_interest_unchanged():
    """On-time payment still charges interest exactly up to the due date (regression guard)."""
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_date = date(2025, 2, 1)
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)

    loan = Loan(principal, rate, [due_date], disbursement_date=disbursement)
    days_to_due = (due_date - disbursement.date()).days

    daily_rate = rate.to_daily().as_decimal()
    expected_interest = Decimal("10000") * ((1 + daily_rate) ** days_to_due - 1)

    with Warp(loan, due_date) as warped:
        warped.pay_installment(Money("10500.00"))
        settlement = warped.settlements[-1]

    assert settlement.interest_paid == Money(expected_interest)


# --- Custom mora interest rate tests ---


def test_mora_rate_defaults_to_base_rate():
    """When mora_interest_rate is not provided, it defaults to interest_rate."""
    rate = InterestRate("6% a")
    loan = Loan(
        Money("10000.00"),
        rate,
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    assert loan.mora_interest_rate is rate


def test_mora_strategy_defaults_to_compound():
    """When mora_strategy is not provided, it defaults to COMPOUND."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    assert loan.mora_strategy == MoraStrategy.COMPOUND


def test_on_time_payment_unaffected_by_custom_mora_rate():
    """A custom mora rate has zero effect when the payment is on time."""
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("24% a")
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)
    due_date = date(2025, 2, 1)

    loan = Loan(
        Money("10000.00"),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
    )

    daily_base = base_rate.to_daily().as_decimal()
    days = (due_date - disbursement.date()).days
    expected_interest = Decimal("10000") * ((1 + daily_base) ** days - 1)

    with Warp(loan, due_date) as warped:
        warped.pay_installment(Money("10500.00"))
        settlement = warped.settlements[-1]

    assert settlement.interest_paid == Money(expected_interest)
    assert settlement.mora_paid == Money.zero()


def test_mora_with_custom_rate_compound_strategy():
    """COMPOUND no longer changes mora: the charge is simple interest on the installment amount."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("12% a")
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)
    due_date = date(2025, 2, 1)
    payment_date = datetime(2025, 2, 15, tzinfo=timezone.utc)

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
        mora_strategy=MoraStrategy.COMPOUND,
    )

    mora_days = (payment_date.date() - due_date).days
    daily_mora = mora_rate.to_daily().as_decimal()
    payment_amount = loan.get_original_schedule()[0].payment_amount.raw_amount
    expected_mora = payment_amount * daily_mora * Decimal(mora_days)

    with Warp(loan, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        settlement = warped.settlements[-1]

    assert settlement.mora_paid == Money(expected_mora)


def test_mora_with_custom_rate_simple_strategy():
    """SIMPLE no longer compounds on principal: mora is linear on the installment amount."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("12% a")
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)
    due_date = date(2025, 2, 1)
    payment_date = datetime(2025, 2, 15, tzinfo=timezone.utc)

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
        mora_strategy=MoraStrategy.SIMPLE,
    )

    mora_days = (payment_date.date() - due_date).days
    daily_mora = mora_rate.to_daily().as_decimal()
    payment_amount = loan.get_original_schedule()[0].payment_amount.raw_amount
    expected_mora = payment_amount * daily_mora * Decimal(mora_days)

    with Warp(loan, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        settlement = warped.settlements[-1]

    assert settlement.mora_paid == Money(expected_mora)


def test_simple_vs_compound_mora_produce_the_same_charge():
    """MoraStrategy does not change the installment mora charge."""
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("12% a")
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)
    due_date = date(2025, 2, 1)
    payment_date = datetime(2025, 2, 15, tzinfo=timezone.utc)

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
        mora_compound = warped.settlements[-1].mora_paid

    with Warp(loan_simple, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        mora_simple = warped.settlements[-1].mora_paid

    assert mora_compound == mora_simple


def test_regular_interest_unchanged_regardless_of_mora_rate():
    """The regular interest portion is always computed with the base rate, not the mora rate."""
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("24% a")
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)
    due_date = date(2025, 2, 1)
    payment_date = datetime(2025, 2, 15, tzinfo=timezone.utc)

    regular_days = (due_date - disbursement.date()).days
    daily_base = base_rate.to_daily().as_decimal()
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
        settlement = warped.settlements[-1]

    assert settlement.interest_paid == Money(expected_regular)


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
    """Regular stays on the base rate; mora is linear on the installment amount for every strategy."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate(mora_rate_str)
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)
    due_date = date(2025, 2, 1)
    payment_date = datetime(2025, 2, 15, tzinfo=timezone.utc)

    regular_days = (due_date - disbursement.date()).days
    mora_days = (payment_date.date() - due_date).days

    daily_base = base_rate.to_daily().as_decimal()
    daily_mora = mora_rate.to_daily().as_decimal()

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
        mora_strategy=strategy,
    )

    expected_regular = principal * ((1 + daily_base) ** regular_days - 1)
    payment_amount = loan.get_original_schedule()[0].payment_amount.raw_amount
    expected_mora = payment_amount * daily_mora * Decimal(mora_days)
    expected_total = expected_regular + expected_mora

    with Warp(loan, payment_date) as warped:
        warped.pay_installment(Money("11000.00"))
        settlement = warped.settlements[-1]
        total_interest = settlement.interest_paid + settlement.mora_paid

    assert total_interest == Money(expected_total)


# --- interest_balance / mora_interest_balance with custom mora rate ---


def test_interest_and_mora_balance_uses_mora_rate_when_past_due():
    """interest_balance stays on the base rate; mora_interest_balance uses the mora rate linearly."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("24% a")
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)
    due_date = date(2025, 2, 1)
    check_date = datetime(2025, 2, 15, tzinfo=timezone.utc)

    regular_days = (due_date - disbursement.date()).days
    mora_days = (check_date.date() - due_date).days

    daily_base = base_rate.to_daily().as_decimal()
    daily_mora = mora_rate.to_daily().as_decimal()

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
    )

    expected_regular = principal * ((1 + daily_base) ** regular_days - 1)
    payment_amount = loan.get_original_schedule()[0].payment_amount.raw_amount
    expected_mora = payment_amount * daily_mora * Decimal(mora_days)

    with Warp(loan, check_date) as warped:
        assert warped.interest_balance == Money(expected_regular)
        assert warped.mora_interest_balance == Money(expected_mora)


def test_interest_balance_uses_base_rate_when_not_late():
    """Before the due date, a custom mora rate has no effect on interest_balance."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("24% a")
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)
    due_date = date(2025, 2, 1)
    check_date = datetime(2025, 1, 20, tzinfo=timezone.utc)

    days = (check_date.date() - disbursement.date()).days
    daily_base = base_rate.to_daily().as_decimal()
    expected = principal * ((1 + daily_base) ** days - 1)

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
    )

    with Warp(loan, check_date) as warped:
        assert warped.interest_balance == Money(expected)
        assert warped.mora_interest_balance == Money.zero()


def test_current_balance_reflects_mora_rate_when_past_due():
    """current_balance should include mora-rate interest when past due."""
    principal = Decimal("10000")
    base_rate = InterestRate("6% a")
    mora_rate = InterestRate("24% a")
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)
    due_date = date(2025, 2, 1)
    check_date = datetime(2025, 2, 15, tzinfo=timezone.utc)

    regular_days = (due_date - disbursement.date()).days
    mora_days = (check_date.date() - due_date).days

    daily_base = base_rate.to_daily().as_decimal()
    daily_mora = mora_rate.to_daily().as_decimal()

    loan = Loan(
        Money(principal),
        base_rate,
        [due_date],
        disbursement_date=disbursement,
        mora_interest_rate=mora_rate,
        fine_rate=InterestRate("0% annual"),
    )

    regular = principal * ((1 + daily_base) ** regular_days - 1)
    payment_amount = loan.get_original_schedule()[0].payment_amount.raw_amount
    mora = payment_amount * daily_mora * Decimal(mora_days)
    expected_balance = principal + regular + mora

    with Warp(loan, check_date) as warped:
        assert warped.current_balance == Money(expected_balance)
