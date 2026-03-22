"""Regression tests for sub-cent balance residual after full repayment.

When full-precision interest differs from the schedule's 2dp interest,
a sub-cent gap can remain on the principal.  Before the fix,
is_fully_covered / is_fully_paid returned True while is_paid_off
returned False — an impossible state for consumer code.

See: https://github.com/.../issues/... (sub-cent balance inconsistency)
"""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money


def _utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


@pytest.fixture
def single_installment_irrational_interest():
    """Single-installment loan whose daily rate is non-terminating."""
    principal = Money("267.65")
    rate = InterestRate("67.458% a")
    due = date(2025, 11, 10)
    disbursement = datetime(2025, 10, 10, tzinfo=timezone.utc)
    return Loan(principal, rate, [due], disbursement_date=disbursement)


@pytest.fixture
def two_installment_irrational_interest():
    """Two-installment loan whose daily rate is non-terminating."""
    principal = Money("500.00")
    rate = InterestRate("67.458% a")
    due_dates = [date(2025, 11, 10), date(2025, 12, 10)]
    disbursement = datetime(2025, 10, 10, tzinfo=timezone.utc)
    return Loan(principal, rate, due_dates, disbursement_date=disbursement)


def test_single_installment_is_paid_off_after_exact_scheduled_payment(
    single_installment_irrational_interest,
):
    loan = single_installment_irrational_interest
    schedule = loan.get_original_schedule()
    loan.record_payment(schedule[0].payment_amount, _utc(schedule[0].due_date))

    assert loan.is_paid_off is True


def test_single_installment_remaining_balance_is_zero(
    single_installment_irrational_interest,
):
    loan = single_installment_irrational_interest
    schedule = loan.get_original_schedule()
    settlement = loan.record_payment(schedule[0].payment_amount, _utc(schedule[0].due_date))

    assert settlement.remaining_balance == Money.zero()


def test_single_installment_allocation_is_fully_covered(
    single_installment_irrational_interest,
):
    loan = single_installment_irrational_interest
    schedule = loan.get_original_schedule()
    settlement = loan.record_payment(schedule[0].payment_amount, _utc(schedule[0].due_date))

    assert settlement.allocations[0].is_fully_covered is True


def test_single_installment_is_fully_paid(
    single_installment_irrational_interest,
):
    loan = single_installment_irrational_interest
    schedule = loan.get_original_schedule()
    loan.record_payment(schedule[0].payment_amount, _utc(schedule[0].due_date))

    assert loan.installments[0].is_fully_paid is True


def test_single_installment_all_consistency_flags_agree(
    single_installment_irrational_interest,
):
    loan = single_installment_irrational_interest
    schedule = loan.get_original_schedule()
    settlement = loan.record_payment(schedule[0].payment_amount, _utc(schedule[0].due_date))

    assert settlement.allocations[0].is_fully_covered is True
    assert loan.installments[0].is_fully_paid is True
    assert loan.is_paid_off is True
    assert settlement.remaining_balance == Money.zero()
    assert loan.principal_balance == Money.zero()


def test_two_installments_is_paid_off_after_sequential_payments(
    two_installment_irrational_interest,
):
    loan = two_installment_irrational_interest
    schedule = loan.get_original_schedule()

    loan.record_payment(schedule[0].payment_amount, _utc(schedule[0].due_date))
    loan.record_payment(schedule[1].payment_amount, _utc(schedule[1].due_date))

    assert loan.is_paid_off is True


def test_two_installments_remaining_balance_is_zero_after_final_payment(
    two_installment_irrational_interest,
):
    loan = two_installment_irrational_interest
    schedule = loan.get_original_schedule()

    loan.record_payment(schedule[0].payment_amount, _utc(schedule[0].due_date))
    settlement = loan.record_payment(schedule[1].payment_amount, _utc(schedule[1].due_date))

    assert settlement.remaining_balance == Money.zero()


def test_two_installments_all_consistency_flags_agree(
    two_installment_irrational_interest,
):
    loan = two_installment_irrational_interest
    schedule = loan.get_original_schedule()

    loan.record_payment(schedule[0].payment_amount, _utc(schedule[0].due_date))
    settlement = loan.record_payment(schedule[1].payment_amount, _utc(schedule[1].due_date))

    assert all(a.is_fully_covered for a in settlement.allocations)
    assert all(inst.is_fully_paid for inst in loan.installments)
    assert loan.is_paid_off is True
    assert settlement.remaining_balance == Money.zero()
    assert loan.principal_balance == Money.zero()


def test_partial_payment_leaves_loan_unpaid(
    single_installment_irrational_interest,
):
    loan = single_installment_irrational_interest
    schedule = loan.get_original_schedule()
    half = Money(schedule[0].payment_amount.raw_amount / 2)
    settlement = loan.record_payment(half, _utc(schedule[0].due_date))

    assert loan.is_paid_off is False
    assert settlement.remaining_balance.is_positive()
    assert settlement.allocations[0].is_fully_covered is False
