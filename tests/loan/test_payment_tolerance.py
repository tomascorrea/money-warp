"""Tests for the accumulated payment_tolerance feature.

The external loan origination system can introduce a 1-cent rounding
error per installment.  The tolerance accumulates with the installment
number so that installment N tolerates N * payment_tolerance.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from money_warp import Installment, InterestRate, Loan, Money, Warp
from money_warp.scheduler import PaymentScheduleEntry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def twelve_installment_loan():
    """12-installment loan with default 1-cent tolerance."""
    due_dates = [
        date(2026, 3, 22), date(2026, 4, 22), date(2026, 5, 22),
        date(2026, 6, 22), date(2026, 7, 22), date(2026, 8, 22),
        date(2026, 9, 22), date(2026, 10, 22), date(2026, 11, 22),
        date(2026, 12, 22), date(2027, 1, 22), date(2027, 2, 22),
    ]
    return Loan(
        Money("10000"),
        InterestRate("1% m"),
        due_dates,
        disbursement_date=datetime(2026, 2, 22, tzinfo=timezone.utc),
    )


@pytest.fixture
def three_installment_loan():
    """3-installment loan for testing tolerance accumulation."""
    return Loan(
        Money("10000"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Loan.payment_tolerance defaults
# ---------------------------------------------------------------------------


def test_default_payment_tolerance_is_one_cent(twelve_installment_loan):
    assert twelve_installment_loan.payment_tolerance == Money("0.01")


def test_custom_payment_tolerance():
    loan = Loan(
        Money("10000"),
        InterestRate("1% m"),
        [date(2026, 3, 22), date(2026, 4, 22)],
        disbursement_date=datetime(2026, 2, 22, tzinfo=timezone.utc),
        payment_tolerance=Money("0.05"),
    )
    assert loan.payment_tolerance == Money("0.05")


def test_zero_tolerance_gives_exact_matching():
    loan = Loan(
        Money("10000"),
        InterestRate("1% m"),
        [date(2026, 3, 22), date(2026, 4, 22)],
        disbursement_date=datetime(2026, 2, 22, tzinfo=timezone.utc),
        payment_tolerance=Money("0"),
    )
    assert loan.payment_tolerance == Money("0")


# ---------------------------------------------------------------------------
# Installment.is_fully_paid -- accumulated tolerance
# ---------------------------------------------------------------------------


def test_installment_carries_loan_payment_tolerance(twelve_installment_loan):
    inst = twelve_installment_loan.installments[0]
    assert inst.payment_tolerance == Money("0.01")


def test_installment_tolerance_scales_with_number():
    entry = PaymentScheduleEntry(
        payment_number=5,
        due_date=date(2025, 6, 1),
        days_in_period=30,
        beginning_balance=Money("5000"),
        payment_amount=Money("1100"),
        principal_payment=Money("1000"),
        interest_payment=Money("100"),
        ending_balance=Money("4000"),
    )
    inst = Installment.from_schedule_entry(
        entry,
        allocations=[],
        expected_mora=Money.zero(),
        expected_fine=Money.zero(),
        payment_tolerance=Money("0.01"),
    )
    assert inst.is_fully_paid is False
    assert inst.balance == Money("1100")


def test_installment_1_tolerates_one_cent():
    entry = PaymentScheduleEntry(
        payment_number=1,
        due_date=date(2025, 2, 1),
        days_in_period=31,
        beginning_balance=Money("10000"),
        payment_amount=Money("100.01"),
        principal_payment=Money("90.01"),
        interest_payment=Money("10.00"),
        ending_balance=Money("9909.99"),
    )
    from money_warp.loan.allocation import Allocation

    alloc = Allocation(
        installment_number=1,
        principal_allocated=Money("90.01"),
        interest_allocated=Money("10.00"),
        mora_allocated=Money.zero(),
        fine_allocated=Money.zero(),
        is_fully_covered=True,
    )
    inst = Installment.from_schedule_entry(
        entry,
        allocations=[alloc],
        expected_mora=Money.zero(),
        expected_fine=Money("0.01"),
        payment_tolerance=Money("0.01"),
    )
    assert inst.balance == Money("0.01")
    assert inst.is_fully_paid is True


def test_installment_1_rejects_two_cent_gap():
    entry = PaymentScheduleEntry(
        payment_number=1,
        due_date=date(2025, 2, 1),
        days_in_period=31,
        beginning_balance=Money("10000"),
        payment_amount=Money("100.02"),
        principal_payment=Money("90.02"),
        interest_payment=Money("10.00"),
        ending_balance=Money("9909.98"),
    )
    from money_warp.loan.allocation import Allocation

    alloc = Allocation(
        installment_number=1,
        principal_allocated=Money("90.02"),
        interest_allocated=Money("10.00"),
        mora_allocated=Money.zero(),
        fine_allocated=Money.zero(),
        is_fully_covered=True,
    )
    inst = Installment.from_schedule_entry(
        entry,
        allocations=[alloc],
        expected_mora=Money.zero(),
        expected_fine=Money("0.02"),
        payment_tolerance=Money("0.01"),
    )
    assert inst.balance == Money("0.02")
    assert inst.is_fully_paid is False


def test_installment_12_tolerates_twelve_cents():
    entry = PaymentScheduleEntry(
        payment_number=12,
        due_date=date(2026, 1, 22),
        days_in_period=31,
        beginning_balance=Money("900"),
        payment_amount=Money("900.12"),
        principal_payment=Money("890.12"),
        interest_payment=Money("10.00"),
        ending_balance=Money("0.00"),
    )
    from money_warp.loan.allocation import Allocation

    alloc = Allocation(
        installment_number=12,
        principal_allocated=Money("890.12"),
        interest_allocated=Money("10.00"),
        mora_allocated=Money.zero(),
        fine_allocated=Money.zero(),
        is_fully_covered=True,
    )
    inst = Installment.from_schedule_entry(
        entry,
        allocations=[alloc],
        expected_mora=Money.zero(),
        expected_fine=Money("0.12"),
        payment_tolerance=Money("0.01"),
    )
    assert inst.balance == Money("0.12")
    assert inst.is_fully_paid is True


def test_installment_12_rejects_thirteen_cents():
    entry = PaymentScheduleEntry(
        payment_number=12,
        due_date=date(2026, 1, 22),
        days_in_period=31,
        beginning_balance=Money("900"),
        payment_amount=Money("900.13"),
        principal_payment=Money("890.13"),
        interest_payment=Money("10.00"),
        ending_balance=Money("0.00"),
    )
    from money_warp.loan.allocation import Allocation

    alloc = Allocation(
        installment_number=12,
        principal_allocated=Money("890.13"),
        interest_allocated=Money("10.00"),
        mora_allocated=Money.zero(),
        fine_allocated=Money.zero(),
        is_fully_covered=True,
    )
    inst = Installment.from_schedule_entry(
        entry,
        allocations=[alloc],
        expected_mora=Money.zero(),
        expected_fine=Money("0.13"),
        payment_tolerance=Money("0.01"),
    )
    assert inst.balance == Money("0.13")
    assert inst.is_fully_paid is False


# ---------------------------------------------------------------------------
# Loan.is_paid_off -- loan-level tolerance
# ---------------------------------------------------------------------------


def test_is_paid_off_after_full_repayment(three_installment_loan):
    schedule = three_installment_loan.get_original_schedule()
    for entry in schedule:
        three_installment_loan.record_payment(
            entry.payment_amount,
            datetime(entry.due_date.year, entry.due_date.month, entry.due_date.day, tzinfo=timezone.utc),
        )
    assert three_installment_loan.is_paid_off is True


def test_is_paid_off_tolerates_accumulated_error(twelve_installment_loan):
    schedule = twelve_installment_loan.get_original_schedule()
    with Warp(twelve_installment_loan, datetime(2027, 3, 1, tzinfo=timezone.utc)) as warped:
        for entry in schedule:
            warped.record_payment(
                entry.payment_amount,
                datetime(entry.due_date.year, entry.due_date.month, entry.due_date.day, tzinfo=timezone.utc),
            )
        assert warped.is_paid_off is True


# ---------------------------------------------------------------------------
# Custom tolerance -- larger than default
# ---------------------------------------------------------------------------


def test_custom_tolerance_propagates_to_installments():
    loan = Loan(
        Money("10000"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        payment_tolerance=Money("0.05"),
    )
    for inst in loan.installments:
        assert inst.payment_tolerance == Money("0.05")


# ---------------------------------------------------------------------------
# Zero tolerance -- exact matching
# ---------------------------------------------------------------------------


def test_zero_tolerance_installment_requires_exact_payment():
    entry = PaymentScheduleEntry(
        payment_number=1,
        due_date=date(2025, 2, 1),
        days_in_period=31,
        beginning_balance=Money("10000"),
        payment_amount=Money("100.00"),
        principal_payment=Money("90.00"),
        interest_payment=Money("10.00"),
        ending_balance=Money("9900"),
    )
    from money_warp.loan.allocation import Allocation

    alloc = Allocation(
        installment_number=1,
        principal_allocated=Money("90.00"),
        interest_allocated=Money("10.00"),
        mora_allocated=Money.zero(),
        fine_allocated=Money.zero(),
        is_fully_covered=True,
    )
    inst_exact = Installment.from_schedule_entry(
        entry,
        allocations=[alloc],
        expected_mora=Money.zero(),
        expected_fine=Money.zero(),
        payment_tolerance=Money("0"),
    )
    assert inst_exact.balance.is_zero()
    assert inst_exact.is_fully_paid is True

    alloc_short = Allocation(
        installment_number=1,
        principal_allocated=Money("89.99"),
        interest_allocated=Money("10.00"),
        mora_allocated=Money.zero(),
        fine_allocated=Money.zero(),
        is_fully_covered=False,
    )
    inst_short = Installment.from_schedule_entry(
        entry,
        allocations=[alloc_short],
        expected_mora=Money.zero(),
        expected_fine=Money.zero(),
        payment_tolerance=Money("0"),
    )
    assert inst_short.balance == Money("0.01")
    assert inst_short.is_fully_paid is False
