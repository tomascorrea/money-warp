"""Tests for loan overpayment handling."""

import warnings
from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money, Settlement, Warp


@pytest.fixture
def fully_paid_loan():
    """A 3-payment loan where every scheduled installment is paid exactly."""
    principal = Money("1000.00")
    rate = InterestRate("5% a")
    due_dates = [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
    ]
    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 10, 2, tzinfo=timezone.utc))

    schedule = loan.get_original_schedule()
    for entry in schedule:
        payment_dt = datetime(entry.due_date.year, entry.due_date.month, entry.due_date.day, tzinfo=timezone.utc)
        loan.record_payment(entry.payment_amount, payment_dt)

    return loan


def test_overpaid_is_zero_before_any_overpayment(fully_paid_loan):
    assert fully_paid_loan.overpaid == Money.zero()


def test_overpaid_is_zero_on_unpaid_loan():
    loan = Loan(
        Money("1000.00"),
        InterestRate("5% a"),
        [date(2025, 11, 1)],
        disbursement_date=datetime(2025, 10, 2, tzinfo=timezone.utc),
    )
    assert loan.overpaid == Money.zero()


def test_pay_installment_after_full_repayment_warns(fully_paid_loan):
    with Warp(fully_paid_loan, datetime(2026, 1, 15, tzinfo=timezone.utc)) as warped:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warped.pay_installment(Money("200.00"))

        assert len(caught) == 1
        assert "overpayment" in str(caught[0].message).lower()


def test_pay_installment_after_full_repayment_returns_settlement(fully_paid_loan):
    with Warp(fully_paid_loan, datetime(2026, 1, 15, tzinfo=timezone.utc)) as warped:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            result = warped.pay_installment(Money("200.00"))

        assert isinstance(result, Settlement)
        assert result.payment_amount == Money("200.00")


def test_overpaid_tracks_single_overpayment(fully_paid_loan):
    with Warp(fully_paid_loan, datetime(2026, 1, 15, tzinfo=timezone.utc)) as warped:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            warped.pay_installment(Money("200.00"))

        assert warped.overpaid == Money("200.00")


def test_overpaid_accumulates_multiple_overpayments(fully_paid_loan):
    with Warp(fully_paid_loan, datetime(2026, 1, 15, tzinfo=timezone.utc)) as warped:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            warped.pay_installment(Money("200.00"))
            warped.pay_installment(Money("150.00"))

        assert warped.overpaid == Money("350.00")


def test_overpaid_via_record_payment(fully_paid_loan):
    fully_paid_loan.record_payment(
        Money("300.00"),
        payment_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
    )
    assert fully_paid_loan.overpaid == Money("300.00")


def test_is_paid_off_remains_true_after_overpayment(fully_paid_loan):
    with Warp(fully_paid_loan, datetime(2026, 1, 15, tzinfo=timezone.utc)) as warped:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            warped.pay_installment(Money("100.00"))

        assert warped.is_paid_off is True


def test_principal_balance_stays_zero_after_overpayment(fully_paid_loan):
    with Warp(fully_paid_loan, datetime(2026, 1, 15, tzinfo=timezone.utc)) as warped:
        with warnings.catch_warnings(record=True):
            warnings.simplefilter("always")
            warped.pay_installment(Money("500.00"))

        assert warped.principal_balance == Money.zero()


@pytest.mark.parametrize(
    "overpayment_amount",
    [
        Money("0.01"),
        Money("100.00"),
        Money("9999.99"),
    ],
)
def test_overpaid_exact_amounts(fully_paid_loan, overpayment_amount):
    fully_paid_loan.record_payment(
        overpayment_amount,
        payment_date=datetime(2026, 1, 15, tzinfo=timezone.utc),
    )
    assert fully_paid_loan.overpaid == overpayment_amount
