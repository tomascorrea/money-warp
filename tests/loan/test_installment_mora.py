"""Mora and fine are charged on each unpaid installment, not on outstanding principal."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money, Warp

_OBSERVATION = datetime(2025, 3, 18, tzinfo=timezone.utc)
_FIRST_DAYS_LATE = 45
_SECOND_DAYS_LATE = 15


@pytest.fixture
def open_commitments():
    """Three installments: 45 days late, 15 days late, and not yet due."""
    return Loan(
        Money("3000.00"),
        InterestRate("12% annual"),
        [date(2025, 2, 1), date(2025, 3, 3), date(2025, 4, 18)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
        mora_interest_rate=InterestRate("12% annual"),
    )


def test_two_overdue_installments_use_their_own_days_and_amounts(open_commitments):
    """Each overdue installment accrues on its own payment amount and its own days late."""
    loan = open_commitments
    schedule = loan.get_original_schedule()
    daily = loan.mora_interest_rate.to_daily().as_decimal()
    first_mora = schedule[0].payment_amount.raw_amount * daily * Decimal(_FIRST_DAYS_LATE)
    second_mora = schedule[1].payment_amount.raw_amount * daily * Decimal(_SECOND_DAYS_LATE)

    with Warp(loan, _OBSERVATION) as warped:
        first = warped.installments[0]
        second = warped.installments[1]
        third = warped.installments[2]
        assert first.expected_mora == Money(first_mora)
        assert second.expected_mora == Money(second_mora)
        assert first.expected_mora != second.expected_mora
        assert warped.mora_interest_balance == first.expected_mora + second.expected_mora + third.expected_mora
        assert warped.principal_balance == Money("3000.00")


def test_installment_not_yet_due_adds_no_fine_and_no_mora(open_commitments):
    """A future installment contributes nothing, and the loan totals are the sums of the overdue ones."""
    loan = open_commitments
    schedule = loan.get_original_schedule()
    fine_rate = loan.fine_rate.as_decimal()
    first_fine = schedule[0].payment_amount.raw_amount * fine_rate
    second_fine = schedule[1].payment_amount.raw_amount * fine_rate

    with Warp(loan, _OBSERVATION) as warped:
        first = warped.installments[0]
        second = warped.installments[1]
        future = warped.installments[2]
        assert future.expected_fine == Money.zero()
        assert future.expected_mora == Money.zero()
        assert future.expected_payment == schedule[2].payment_amount
        assert first.expected_fine == Money(first_fine)
        assert second.expected_fine == Money(second_fine)
        assert warped.fine_balance == first.expected_fine + second.expected_fine


def test_mora_is_linear_on_the_installment_not_compound_on_principal(open_commitments):
    """Mora ignores outstanding principal and InterestRate.accrue."""
    loan = open_commitments
    schedule = loan.get_original_schedule()
    daily = loan.mora_interest_rate.to_daily().as_decimal()
    on_installment = schedule[0].payment_amount.raw_amount * daily * Decimal(_FIRST_DAYS_LATE)
    on_principal = loan.principal.raw_amount * ((1 + daily) ** _FIRST_DAYS_LATE - 1)

    with Warp(loan, _OBSERVATION) as warped:
        first = warped.installments[0]
        assert first.expected_mora == Money(on_installment)
        assert first.expected_mora != Money(on_principal)
        assert first.expected_payment == schedule[0].payment_amount
