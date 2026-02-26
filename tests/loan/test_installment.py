"""Tests for Installment — the public-facing repayment plan view."""

from datetime import datetime
from decimal import Decimal

import pytest

from money_warp import Installment, InterestRate, Loan, Money


@pytest.fixture
def simple_loan():
    """3-installment loan with Price scheduler."""
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [
        datetime(2025, 2, 1),
        datetime(2025, 3, 1),
        datetime(2025, 4, 1),
    ]
    return Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 1, 1))


def test_installments_count_matches_due_dates(simple_loan):
    assert len(simple_loan.installments) == 3


def test_installments_numbers_are_sequential(simple_loan):
    numbers = [inst.number for inst in simple_loan.installments]
    assert numbers == [1, 2, 3]


def test_installments_due_dates_match_loan(simple_loan):
    dates = [inst.due_date for inst in simple_loan.installments]
    assert dates == simple_loan.due_dates


def test_installment_expected_payment_is_positive(simple_loan):
    assert all(inst.expected_payment.is_positive() for inst in simple_loan.installments)


def test_installment_expected_principal_plus_interest_equals_payment(simple_loan):
    for inst in simple_loan.installments:
        total = inst.expected_principal + inst.expected_interest
        assert abs(total.raw_amount - inst.expected_payment.raw_amount) < Decimal("0.02")


def test_installments_all_unpaid_before_any_payment(simple_loan):
    assert all(not inst.is_paid for inst in simple_loan.installments)


def test_installments_paid_amounts_zero_before_any_payment(simple_loan):
    for inst in simple_loan.installments:
        assert inst.principal_paid.is_zero()
        assert inst.interest_paid.is_zero()
        assert inst.mora_paid.is_zero()
        assert inst.fine_paid.is_zero()


def test_installments_allocations_empty_before_any_payment(simple_loan):
    for inst in simple_loan.installments:
        assert inst.allocations == []


def test_first_installment_is_paid_after_covering_payment(simple_loan):
    schedule = simple_loan.get_original_schedule()
    simple_loan.record_payment(schedule[0].payment_amount, schedule[0].due_date)

    assert simple_loan.installments[0].is_paid is True
    assert simple_loan.installments[1].is_paid is False


def test_first_installment_has_allocations_after_payment(simple_loan):
    schedule = simple_loan.get_original_schedule()
    simple_loan.record_payment(schedule[0].payment_amount, schedule[0].due_date)

    allocs = simple_loan.installments[0].allocations
    assert len(allocs) == 1
    assert allocs[0].installment_number == 1


def test_installment_principal_paid_reflects_actual_payment(simple_loan):
    schedule = simple_loan.get_original_schedule()
    simple_loan.record_payment(schedule[0].payment_amount, schedule[0].due_date)

    inst = simple_loan.installments[0]
    assert inst.principal_paid.is_positive()
    assert inst.interest_paid.is_positive()


def test_all_installments_paid_after_full_repayment(simple_loan):
    schedule = simple_loan.get_original_schedule()
    for entry in schedule:
        simple_loan.record_payment(entry.payment_amount, entry.due_date)

    assert all(inst.is_paid for inst in simple_loan.installments)


def test_partial_payment_does_not_mark_installment_paid(simple_loan):
    simple_loan.record_payment(Money("100.00"), datetime(2025, 2, 1))

    assert simple_loan.installments[0].is_paid is False


def test_partial_payment_shows_principal_paid(simple_loan):
    simple_loan.record_payment(Money("100.00"), datetime(2025, 2, 1))

    inst = simple_loan.installments[0]
    assert inst.principal_paid.is_positive() or inst.interest_paid.is_positive()
    assert len(inst.allocations) == 1


@pytest.mark.parametrize("installment_index", [0, 1, 2])
def test_installment_days_in_period_is_positive(simple_loan, installment_index):
    assert simple_loan.installments[installment_index].days_in_period > 0


def test_from_schedule_entry_creates_correct_installment():
    from money_warp.scheduler import PaymentScheduleEntry

    entry = PaymentScheduleEntry(
        payment_number=1,
        due_date=datetime(2025, 2, 1),
        days_in_period=31,
        beginning_balance=Money("10000"),
        payment_amount=Money("3400"),
        principal_payment=Money("3200"),
        interest_payment=Money("200"),
        ending_balance=Money("6800"),
    )
    inst = Installment.from_schedule_entry(entry, is_paid=False, allocations=[])

    assert inst.number == 1
    assert inst.due_date == datetime(2025, 2, 1)
    assert inst.days_in_period == 31
    assert inst.expected_payment == Money("3400")
    assert inst.expected_principal == Money("3200")
    assert inst.expected_interest == Money("200")
    assert inst.is_paid is False
    assert inst.allocations == []
