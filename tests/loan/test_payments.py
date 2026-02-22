"""Tests for Loan payment recording, full/partial payment scenarios."""

from datetime import datetime, timedelta

import pytest

from money_warp import InterestRate, Loan, Money, Warp


def test_loan_record_payment_updates_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15))

    # Balance should be reduced by principal portion
    assert loan.current_balance < principal


def test_loan_record_payment_creates_interest_and_principal_items():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15))

    # Should have created interest and principal payment items
    assert len(loan._actual_payments) == 2

    # Check categories
    categories = [payment.category for payment in loan._actual_payments]
    assert "actual_interest" in categories
    assert "actual_principal" in categories


def test_loan_record_payment_updates_last_payment_date():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    payment_date = datetime(2024, 1, 15)

    assert loan.last_payment_date == disbursement_date

    loan.record_payment(Money("5000.00"), payment_date)
    assert loan.last_payment_date == payment_date


def test_loan_record_payment_multiple_payments():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    loan.record_payment(Money("3000.00"), datetime(2024, 1, 15))
    loan.record_payment(Money("2000.00"), datetime(2024, 1, 20))

    assert loan.current_balance < principal


def test_loan_record_payment_overpayment_zeros_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    loan.record_payment(Money("15000.00"), datetime(2024, 1, 15))

    assert loan.current_balance == Money.zero()
    assert loan.is_paid_off


def test_loan_record_payment_negative_amount_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))

    with pytest.raises(ValueError, match="Payment amount must be positive"):
        loan.record_payment(Money("-1000.00"), datetime(2024, 1, 15))


def test_loan_record_payment_zero_amount_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))

    with pytest.raises(ValueError, match="Payment amount must be positive"):
        loan.record_payment(Money.zero(), datetime(2024, 1, 15))


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


def test_loan_accrued_interest_zero_after_all_installments_paid(loan_with_all_installments_paid):
    """No interest should accrue after the final installment is paid on its due date."""
    loan, due_dates = loan_with_all_installments_paid

    with Warp(loan, due_dates[-1]) as warped_loan:
        assert warped_loan.accrued_interest == Money.zero()


def test_loan_no_outstanding_fines_after_on_time_installments(loan_with_all_installments_paid):
    """No fines should exist when every installment is paid on its due date."""
    loan, due_dates = loan_with_all_installments_paid

    with Warp(loan, due_dates[-1]) as warped_loan:
        assert warped_loan.outstanding_fines == Money.zero()


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
        datetime(2025, 11, 1),
        datetime(2025, 12, 1),
        datetime(2026, 1, 1),
        datetime(2026, 2, 1),
        datetime(2026, 3, 1),
        datetime(2026, 4, 1),
        datetime(2026, 5, 1),
        datetime(2026, 6, 1),
        datetime(2026, 7, 1),
        datetime(2026, 8, 1),
        datetime(2026, 9, 1),
        datetime(2026, 10, 1),
    ]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 10, 2))

    schedule = loan.get_amortization_schedule()
    for entry in schedule:
        loan.record_payment(entry.payment_amount, entry.due_date)

    with Warp(loan, due_dates[-1]) as warped_loan:
        assert warped_loan.current_balance <= Money("0.01")


def test_loan_principal_balance_reduced_at_payment_date_with_warp(partial_payment_loan):
    """Warp to payment date must show a principal balance lower than original."""
    loan, principal, payment_date = partial_payment_loan

    with Warp(loan, payment_date) as warped_loan:
        assert warped_loan.principal_balance < principal


def test_loan_accrued_interest_non_negative_at_payment_date_with_warp(partial_payment_loan):
    """Accrued interest at the payment date must be non-negative."""
    loan, _, payment_date = partial_payment_loan

    with Warp(loan, payment_date) as warped_loan:
        assert warped_loan.accrued_interest >= Money.zero()


def test_loan_current_balance_equals_components_at_payment_date_with_warp(partial_payment_loan):
    """current_balance must equal principal_balance + accrued_interest at payment date."""
    loan, _, payment_date = partial_payment_loan

    with Warp(loan, payment_date) as warped_loan:
        assert warped_loan.current_balance == warped_loan.principal_balance + warped_loan.accrued_interest


def test_loan_interest_accrues_after_partial_payment_with_warp(partial_payment_loan):
    """Interest must continue accruing on the remaining principal after a partial payment."""
    loan, _, payment_date = partial_payment_loan

    with Warp(loan, payment_date + timedelta(days=5)) as warped_loan:
        assert warped_loan.accrued_interest > Money.zero()
