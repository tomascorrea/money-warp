"""Tests for Settlement — the result of applying a payment to a loan."""

from datetime import datetime
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money, Settlement, SettlementAllocation, Warp


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


# --- record_payment returns Settlement ---


def test_record_payment_returns_settlement(simple_loan):
    result = simple_loan.record_payment(Money("3500"), datetime(2025, 2, 1))
    assert isinstance(result, Settlement)


def test_pay_installment_returns_settlement(simple_loan):
    with Warp(simple_loan, datetime(2025, 2, 1)) as warped:
        schedule = warped.get_original_schedule()
        result = warped.pay_installment(schedule[0].payment_amount)
        assert isinstance(result, Settlement)


def test_anticipate_payment_returns_settlement(simple_loan):
    with Warp(simple_loan, datetime(2025, 1, 20)) as warped:
        result = warped.anticipate_payment(Money("3500"))
        assert isinstance(result, Settlement)


# --- Settlement fields ---


def test_settlement_payment_amount_matches_input(simple_loan):
    settlement = simple_loan.record_payment(Money("5000"), datetime(2025, 2, 1))
    assert settlement.payment_amount == Money("5000")


def test_settlement_payment_date_matches_input(simple_loan):
    date = datetime(2025, 2, 1)
    settlement = simple_loan.record_payment(Money("5000"), date)
    assert settlement.payment_date == date


def test_settlement_components_sum_to_payment_amount(simple_loan):
    settlement = simple_loan.record_payment(Money("5000"), datetime(2025, 2, 1))
    total = settlement.fine_paid + settlement.interest_paid + settlement.mora_paid + settlement.principal_paid
    assert abs(total.raw_amount - settlement.payment_amount.raw_amount) < Decimal("0.02")


def test_settlement_remaining_balance_after_first_payment(simple_loan):
    settlement = simple_loan.record_payment(Money("5000"), datetime(2025, 2, 1))
    assert settlement.remaining_balance.is_positive()
    assert settlement.remaining_balance < simple_loan.principal


def test_settlement_no_fines_on_time_payment(simple_loan):
    settlement = simple_loan.record_payment(Money("5000"), datetime(2025, 2, 1))
    assert settlement.fine_paid.is_zero()


def test_settlement_no_mora_on_time_payment(simple_loan):
    settlement = simple_loan.record_payment(Money("5000"), datetime(2025, 2, 1))
    assert settlement.mora_paid.is_zero()


# --- Settlement allocations ---


def test_settlement_has_allocations(simple_loan):
    settlement = simple_loan.record_payment(Money("5000"), datetime(2025, 2, 1))
    assert len(settlement.allocations) >= 1


def test_settlement_allocation_installment_number(simple_loan):
    settlement = simple_loan.record_payment(Money("3500"), datetime(2025, 2, 1))
    assert settlement.allocations[0].installment_number == 1


def test_settlement_allocation_is_settlement_allocation_type(simple_loan):
    settlement = simple_loan.record_payment(Money("3500"), datetime(2025, 2, 1))
    assert isinstance(settlement.allocations[0], SettlementAllocation)


# --- Single installment coverage ---


def test_exact_payment_covers_single_installment(simple_loan):
    schedule = simple_loan.get_original_schedule()
    settlement = simple_loan.record_payment(schedule[0].payment_amount, schedule[0].due_date)

    assert len(settlement.allocations) == 1
    assert settlement.allocations[0].installment_number == 1
    assert settlement.allocations[0].is_fully_covered is True


def test_exact_payment_principal_allocated_matches_expected(simple_loan):
    schedule = simple_loan.get_original_schedule()
    settlement = simple_loan.record_payment(schedule[0].payment_amount, schedule[0].due_date)

    expected_principal = schedule[0].principal_payment
    assert abs(settlement.allocations[0].principal_allocated.raw_amount - expected_principal.raw_amount) < Decimal(
        "0.02"
    )


# --- Partial payment ---


def test_partial_payment_does_not_fully_cover_installment(simple_loan):
    settlement = simple_loan.record_payment(Money("100"), datetime(2025, 2, 1))

    assert len(settlement.allocations) == 1
    assert settlement.allocations[0].is_fully_covered is False


def test_partial_payment_principal_allocated_less_than_expected(simple_loan):
    schedule = simple_loan.get_original_schedule()
    settlement = simple_loan.record_payment(Money("100"), datetime(2025, 2, 1))

    assert settlement.allocations[0].principal_allocated < schedule[0].principal_payment


# --- Overpayment covering multiple installments ---


def test_large_payment_covers_multiple_installments(simple_loan):
    schedule = simple_loan.get_original_schedule()
    large_amount = schedule[0].payment_amount + schedule[1].payment_amount
    settlement = simple_loan.record_payment(large_amount, datetime(2025, 2, 1))

    assert len(settlement.allocations) >= 2
    assert settlement.allocations[0].installment_number == 1
    assert settlement.allocations[1].installment_number == 2


def test_large_payment_first_installment_fully_covered(simple_loan):
    schedule = simple_loan.get_original_schedule()
    large_amount = schedule[0].payment_amount + schedule[1].payment_amount
    settlement = simple_loan.record_payment(large_amount, datetime(2025, 2, 1))

    assert settlement.allocations[0].is_fully_covered is True


def test_full_repayment_in_one_payment(simple_loan):
    total = sum(
        (e.payment_amount for e in simple_loan.get_original_schedule()),
        Money.zero(),
    )
    settlement = simple_loan.record_payment(total, datetime(2025, 2, 1))

    assert settlement.remaining_balance <= Money("0.02")
    assert all(a.is_fully_covered for a in settlement.allocations)


# --- Sequential payments ---


def test_second_payment_allocates_to_next_installment(simple_loan):
    schedule = simple_loan.get_original_schedule()
    simple_loan.record_payment(schedule[0].payment_amount, schedule[0].due_date)
    settlement2 = simple_loan.record_payment(schedule[1].payment_amount, schedule[1].due_date)

    assert settlement2.allocations[0].installment_number == 2


# --- Late payment with fines and mora ---


def test_late_payment_settlement_includes_fine():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2025, 2, 1)]
    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 1, 1))

    late_date = datetime(2025, 2, 15)
    schedule = loan.get_original_schedule()
    settlement = loan.record_payment(
        schedule[0].payment_amount + Money("500"),
        late_date,
        interest_date=late_date,
    )

    assert settlement.fine_paid.is_positive()


def test_late_payment_settlement_includes_mora():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2025, 2, 1)]
    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 1, 1))

    late_date = datetime(2025, 2, 15)
    settlement = loan.record_payment(
        Money("11000"),
        late_date,
        interest_date=late_date,
    )

    assert settlement.mora_paid.is_positive()


def test_late_payment_fine_allocated_to_installment():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2025, 2, 1)]
    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2025, 1, 1))

    late_date = datetime(2025, 2, 15)
    settlement = loan.record_payment(
        Money("11000"),
        late_date,
        interest_date=late_date,
    )

    assert settlement.allocations[0].fine_allocated.is_positive()


# --- settlements property ---


def test_settlements_property_returns_all_settlements(simple_loan):
    schedule = simple_loan.get_original_schedule()
    for entry in schedule:
        simple_loan.record_payment(entry.payment_amount, entry.due_date)

    assert len(simple_loan.settlements) == 3


def test_settlements_property_empty_before_any_payment(simple_loan):
    assert simple_loan.settlements == []


def test_settlements_property_matches_record_payment_results(simple_loan):
    schedule = simple_loan.get_original_schedule()
    returned = simple_loan.record_payment(schedule[0].payment_amount, schedule[0].due_date)

    from_property = simple_loan.settlements[0]

    assert returned.payment_amount == from_property.payment_amount
    assert returned.principal_paid == from_property.principal_paid
    assert returned.interest_paid == from_property.interest_paid


# --- Warp awareness ---


def test_settlements_respect_warp_time(simple_loan):
    schedule = simple_loan.get_original_schedule()
    for entry in schedule:
        simple_loan.record_payment(entry.payment_amount, entry.due_date)

    with Warp(simple_loan, datetime(2025, 2, 15)) as warped:
        assert len(warped.settlements) == 1

    with Warp(simple_loan, datetime(2025, 3, 15)) as warped:
        assert len(warped.settlements) == 2


def test_installments_is_paid_respects_warp(simple_loan):
    schedule = simple_loan.get_original_schedule()
    for entry in schedule:
        simple_loan.record_payment(entry.payment_amount, entry.due_date)

    with Warp(simple_loan, datetime(2025, 2, 15)) as warped:
        assert warped.installments[0].is_paid is True
        assert warped.installments[1].is_paid is False

    with Warp(simple_loan, datetime(2025, 1, 15)) as warped:
        assert all(not inst.is_paid for inst in warped.installments)
