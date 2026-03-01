"""Tests for Installment — the public-facing repayment plan view."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from money_warp import Installment, InterestRate, Loan, Money, Warp


@pytest.fixture
def simple_loan():
    """3-installment loan with Price scheduler."""
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [
        datetime(2025, 2, 1, tzinfo=timezone.utc),
        datetime(2025, 3, 1, tzinfo=timezone.utc),
        datetime(2025, 4, 1, tzinfo=timezone.utc),
    ]
    return Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc))


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
    assert all(not inst.is_fully_paid for inst in simple_loan.installments)


def test_installments_paid_amounts_zero_before_any_payment(simple_loan):
    for inst in simple_loan.installments:
        assert inst.principal_paid.is_zero()
        assert inst.interest_paid.is_zero()
        assert inst.mora_paid.is_zero()
        assert inst.fine_paid.is_zero()


def test_installments_allocations_empty_before_any_payment(simple_loan):
    for inst in simple_loan.installments:
        assert inst.allocations == []


def test_first_installment_is_fully_paid_after_covering_payment(simple_loan):
    schedule = simple_loan.get_original_schedule()
    simple_loan.record_payment(schedule[0].payment_amount, schedule[0].due_date)

    assert simple_loan.installments[0].is_fully_paid is True
    assert simple_loan.installments[1].is_fully_paid is False


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

    assert all(inst.is_fully_paid for inst in simple_loan.installments)


def test_partial_payment_does_not_mark_installment_paid(simple_loan):
    simple_loan.record_payment(Money("100.00"), datetime(2025, 2, 1, tzinfo=timezone.utc))

    assert simple_loan.installments[0].is_fully_paid is False


def test_partial_payment_shows_principal_paid(simple_loan):
    simple_loan.record_payment(Money("100.00"), datetime(2025, 2, 1, tzinfo=timezone.utc))

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
        due_date=datetime(2025, 2, 1, tzinfo=timezone.utc),
        days_in_period=31,
        beginning_balance=Money("10000"),
        payment_amount=Money("3400"),
        principal_payment=Money("3200"),
        interest_payment=Money("200"),
        ending_balance=Money("6800"),
    )
    inst = Installment.from_schedule_entry(
        entry,
        allocations=[],
        expected_mora=Money.zero(),
        expected_fine=Money.zero(),
    )

    assert inst.number == 1
    assert inst.due_date == datetime(2025, 2, 1, tzinfo=timezone.utc)
    assert inst.days_in_period == 31
    assert inst.expected_payment == Money("3400")
    assert inst.expected_principal == Money("3200")
    assert inst.expected_interest == Money("200")
    assert inst.is_fully_paid is False
    assert inst.allocations == []


# --- balance tests ---


def test_balance_equals_expected_payment_before_any_payment(simple_loan):
    with Warp(simple_loan, datetime(2025, 1, 15, tzinfo=timezone.utc)) as warped:
        inst = warped.installments[0]

    assert inst.balance == inst.expected_payment


def test_balance_is_zero_after_full_payment(simple_loan):
    schedule = simple_loan.get_original_schedule()
    simple_loan.record_payment(schedule[0].payment_amount, schedule[0].due_date)

    with Warp(simple_loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        assert warped.installments[0].balance.is_zero()


def test_balance_decreases_after_partial_payment(simple_loan):
    with Warp(simple_loan, datetime(2025, 1, 15, tzinfo=timezone.utc)) as warped:
        balance_before = warped.installments[0].balance

    simple_loan.record_payment(Money("100.00"), datetime(2025, 2, 1, tzinfo=timezone.utc))

    with Warp(simple_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        balance_after = warped.installments[0].balance

    assert balance_after < balance_before


def test_is_fully_paid_true_when_balance_is_zero(simple_loan):
    schedule = simple_loan.get_original_schedule()
    simple_loan.record_payment(schedule[0].payment_amount, schedule[0].due_date)

    with Warp(simple_loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        assert warped.installments[0].balance.is_zero()
        assert warped.installments[0].is_fully_paid is True


def test_is_fully_paid_false_when_balance_positive(simple_loan):
    with Warp(simple_loan, datetime(2025, 1, 15, tzinfo=timezone.utc)) as warped:
        assert warped.installments[0].balance.is_positive()
        assert warped.installments[0].is_fully_paid is False


# --- expected_mora tests ---


def test_expected_mora_zero_before_due_date(simple_loan):
    with Warp(simple_loan, datetime(2025, 1, 15, tzinfo=timezone.utc)) as warped:
        assert all(inst.expected_mora.is_zero() for inst in warped.installments)


def test_expected_mora_positive_when_overdue():
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1, tzinfo=timezone.utc)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        assert warped.installments[0].expected_mora.is_positive()


def test_expected_mora_equals_mora_paid_after_late_settlement():
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1, tzinfo=timezone.utc)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("11000.00"))
        inst = warped.installments[0]

    assert inst.expected_mora == inst.mora_paid


def test_expected_mora_only_on_first_uncovered_installment():
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    with Warp(loan, datetime(2025, 3, 15, tzinfo=timezone.utc)) as warped:
        assert warped.installments[0].expected_mora.is_positive()
        assert warped.installments[1].expected_mora.is_zero()


# --- expected_fine tests ---


def test_expected_fine_zero_when_no_fines(simple_loan):
    with Warp(simple_loan, datetime(2025, 1, 15, tzinfo=timezone.utc)) as warped:
        assert all(inst.expected_fine.is_zero() for inst in warped.installments)


def test_expected_fine_reflects_applied_fine():
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1, tzinfo=timezone.utc)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        inst = warped.installments[0]

    assert inst.expected_fine.is_positive()


def test_balance_includes_fine():
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1, tzinfo=timezone.utc)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        inst = warped.installments[0]

    assert inst.balance > inst.expected_payment


def test_balance_includes_mora():
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1, tzinfo=timezone.utc)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        inst = warped.installments[0]

    assert inst.balance > inst.expected_payment
