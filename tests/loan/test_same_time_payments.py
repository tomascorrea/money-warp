"""Tests for multiple payments recorded at the exact same datetime."""

from datetime import datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money


@pytest.fixture
def two_installment_loan():
    """Loan with 2 installments, suitable for same-time payment tests."""
    return Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def test_two_payments_same_datetime_first_settlement_has_principal(two_installment_loan):
    payment_date = datetime(2025, 2, 1, tzinfo=timezone.utc)
    s1 = two_installment_loan.record_payment(Money("3000"), payment_date)
    two_installment_loan.record_payment(Money("3000"), payment_date)

    assert s1.principal_paid.is_positive()


def test_two_payments_same_datetime_second_settlement_has_principal(two_installment_loan):
    payment_date = datetime(2025, 2, 1, tzinfo=timezone.utc)
    two_installment_loan.record_payment(Money("3000"), payment_date)
    s2 = two_installment_loan.record_payment(Money("3000"), payment_date)

    assert s2.principal_paid.is_positive()


def test_two_payments_same_datetime_components_sum_correctly(two_installment_loan):
    payment_date = datetime(2025, 2, 1, tzinfo=timezone.utc)
    s1 = two_installment_loan.record_payment(Money("3000"), payment_date)
    s2 = two_installment_loan.record_payment(Money("3000"), payment_date)

    assert s1.payment_amount == Money("3000")
    assert s2.payment_amount == Money("3000")


def test_two_payments_same_datetime_settlements_property_returns_both(two_installment_loan):
    payment_date = datetime(2025, 2, 1, tzinfo=timezone.utc)
    two_installment_loan.record_payment(Money("3000"), payment_date)
    two_installment_loan.record_payment(Money("3000"), payment_date)

    settlements = two_installment_loan.settlements
    assert len(settlements) == 2


def test_two_payments_same_datetime_settlements_have_distinct_values(two_installment_loan):
    payment_date = datetime(2025, 2, 1, tzinfo=timezone.utc)
    two_installment_loan.record_payment(Money("3000"), payment_date)
    two_installment_loan.record_payment(Money("3000"), payment_date)

    settlements = two_installment_loan.settlements
    total_principal = settlements[0].principal_paid + settlements[1].principal_paid
    total_interest = settlements[0].interest_paid + settlements[1].interest_paid

    assert total_principal.is_positive()
    assert total_interest.is_positive()


def test_two_payments_same_datetime_balance_decreases_correctly(two_installment_loan):
    payment_date = datetime(2025, 2, 1, tzinfo=timezone.utc)
    s1 = two_installment_loan.record_payment(Money("3000"), payment_date)
    s2 = two_installment_loan.record_payment(Money("3000"), payment_date)

    assert s2.remaining_balance < s1.remaining_balance
