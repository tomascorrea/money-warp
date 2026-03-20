"""Tests for Loan payment recording, full/partial payment scenarios."""

from datetime import date, datetime, timedelta, timezone

import pytest

from money_warp import InterestRate, Loan, Money, Warp


def test_loan_record_payment_updates_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [date(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))

    # Balance should be reduced by principal portion
    assert loan.current_balance < principal


def test_loan_record_payment_creates_interest_and_principal_items():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [date(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))

    # Should have created interest and principal payment items
    assert len(loan._actual_payments) == 2

    # Check categories
    assert any("interest" in p.category for p in loan._actual_payments)
    assert any("principal" in p.category for p in loan._actual_payments)


def test_loan_record_payment_updates_last_payment_date():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [date(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    payment_date = datetime(2024, 1, 15, tzinfo=timezone.utc)

    assert loan.last_payment_date == disbursement_date

    loan.record_payment(Money("5000.00"), payment_date)
    assert loan.last_payment_date == payment_date


def test_loan_record_payment_multiple_payments():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [date(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    loan.record_payment(Money("3000.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))
    loan.record_payment(Money("2000.00"), datetime(2024, 1, 20, tzinfo=timezone.utc))

    assert loan.current_balance < principal


def test_loan_record_payment_overpayment_zeros_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [date(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    loan.record_payment(Money("15000.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))

    assert loan.current_balance == Money.zero()
    assert loan.is_paid_off


def test_loan_record_payment_negative_amount_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [date(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))

    with pytest.raises(ValueError, match="Payment amount must be positive"):
        loan.record_payment(Money("-1000.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))


def test_loan_record_payment_zero_amount_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [date(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))

    with pytest.raises(ValueError, match="Payment amount must be positive"):
        loan.record_payment(Money.zero(), datetime(2024, 1, 15, tzinfo=timezone.utc))


def test_loan_current_balance_zero_after_all_installments_paid(loan_with_all_installments_paid):
    """Paying every scheduled installment must result in a zero current balance."""
    loan, due_dates = loan_with_all_installments_paid

    with Warp(loan, due_dates[-1]) as warped_loan:
        assert warped_loan.current_balance == Money.zero()


def test_loan_principal_balance_zero_after_all_installments_paid(loan_with_all_installments_paid):
    """Paying every scheduled installment must fully retire the principal."""
    loan, due_dates = loan_with_all_installments_paid

    with Warp(loan, due_dates[-1]) as warped_loan:
        assert warped_loan.principal_balance == Money.zero()


def test_loan_interest_balance_zero_after_all_installments_paid(loan_with_all_installments_paid):
    """No interest should accrue after the final installment is paid on its due date."""
    loan, due_dates = loan_with_all_installments_paid

    with Warp(loan, due_dates[-1]) as warped_loan:
        assert warped_loan.interest_balance == Money.zero()
        assert warped_loan.mora_interest_balance == Money.zero()


def test_loan_no_fine_balance_after_on_time_installments(loan_with_all_installments_paid):
    """No fines should exist when every installment is paid on its due date."""
    loan, due_dates = loan_with_all_installments_paid

    with Warp(loan, due_dates[-1]) as warped_loan:
        assert warped_loan.fine_balance == Money.zero()


def test_loan_balance_zero_when_payments_recorded_beyond_real_time():
    """
    Regression test: recording all installments (some in the future relative to real
    time) must still produce a zero balance.  The bug was that days_since_last_payment
    used self.now() as the filter, making previously-recorded future payments invisible
    and therefore computing too many interest days for subsequent payments.

    The schedule rounds at each step while record_payment uses full precision,
    so a sub-cent residual (at most 1 cent) is expected.
    """
    principal = Money("1000.00")
    rate = InterestRate("5% a")
    due_dates = [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 2, 1),
        date(2026, 3, 1),
        date(2026, 4, 1),
        date(2026, 5, 1),
        date(2026, 6, 1),
        date(2026, 7, 1),
        date(2026, 8, 1),
        date(2026, 9, 1),
        date(2026, 10, 1),
    ]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 10, 2, tzinfo=timezone.utc))

    schedule = loan.get_amortization_schedule()
    for entry in schedule:
        payment_dt = datetime(
            entry.due_date.year,
            entry.due_date.month,
            entry.due_date.day,
            tzinfo=timezone.utc,
        )
        loan.record_payment(entry.payment_amount, payment_dt)

    with Warp(loan, due_dates[-1]) as warped_loan:
        assert warped_loan.current_balance <= Money("0.01")


def test_loan_principal_balance_reduced_at_payment_date_with_warp(partial_payment_loan):
    """Warp to payment date must show a principal balance lower than original."""
    loan, principal, payment_date = partial_payment_loan

    with Warp(loan, payment_date) as warped_loan:
        assert warped_loan.principal_balance < principal


def test_loan_interest_balance_non_negative_at_payment_date_with_warp(partial_payment_loan):
    """Interest balance at the payment date must be non-negative."""
    loan, _, payment_date = partial_payment_loan

    with Warp(loan, payment_date) as warped_loan:
        assert warped_loan.interest_balance >= Money.zero()


def test_loan_current_balance_equals_components_at_payment_date_with_warp(partial_payment_loan):
    """current_balance must equal sum of four component balances at payment date."""
    loan, _, payment_date = partial_payment_loan

    with Warp(loan, payment_date) as warped_loan:
        expected = (
            warped_loan.principal_balance
            + warped_loan.interest_balance
            + warped_loan.mora_interest_balance
            + warped_loan.fine_balance
        )
        assert warped_loan.current_balance == expected


def test_loan_interest_accrues_after_partial_payment_with_warp(partial_payment_loan):
    """Interest must continue accruing on the remaining principal after a partial payment."""
    loan, _, payment_date = partial_payment_loan

    with Warp(loan, payment_date + timedelta(days=5)) as warped_loan:
        total_interest = warped_loan.interest_balance + warped_loan.mora_interest_balance
        assert total_interest > Money.zero()
