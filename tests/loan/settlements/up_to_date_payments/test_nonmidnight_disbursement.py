"""Settlement tests for a loan with non-midnight disbursement time.

Regression: when disbursement_date has a non-midnight time component
(e.g. 19:53), the settlement engine used datetime subtraction to count
accrual days while the scheduler used date subtraction.  This caused a
1-day shortfall in interest, preventing the first installment from being
marked as fully covered.
"""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money, Warp


@pytest.fixture
def nonmidnight_loan():
    """4-installment loan disbursed at 19:53 UTC (non-midnight)."""
    return Loan(
        Money("1011.02"),
        InterestRate("180.96% a.a."),
        [
            date(2026, 4, 12),
            date(2026, 5, 12),
            date(2026, 6, 12),
            date(2026, 7, 12),
        ],
        disbursement_date=datetime(2026, 3, 6, 19, 53, 0, tzinfo=timezone.utc),
        mora_interest_rate=InterestRate("15% a.m."),
    )


def test_schedule_first_period_is_37_days(nonmidnight_loan):
    """The schedule counts 37 calendar days from March 6 to April 12."""
    schedule = nonmidnight_loan.get_original_schedule()
    assert schedule[0].days_in_period == 37


def test_settlement_interest_matches_schedule(nonmidnight_loan):
    """Settlement interest for the first installment matches the schedule."""
    with Warp(nonmidnight_loan, datetime(2026, 3, 6, 19, 53, 0, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800"))

    assert settlement.interest_paid == Money("111.62")
    assert settlement.allocations[0].interest_allocated == Money("111.62")

    schedule = nonmidnight_loan.get_original_schedule()
    assert schedule[0].interest_payment == Money("111.62")


def test_first_installment_fully_covered(nonmidnight_loan):
    """First installment is fully covered despite non-midnight disbursement."""
    with Warp(nonmidnight_loan, datetime(2026, 3, 6, 19, 53, 0, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800"))

    first = settlement.allocations[0]
    assert first.principal_allocated == Money("206.14")
    assert first.interest_allocated == Money("111.62")
    assert first.mora_allocated == Money("0.00")
    assert first.fine_allocated == Money("0.00")
    assert first.is_fully_covered is True


def test_settlement_totals(nonmidnight_loan):
    """Settlement-level totals for the 800 payment."""
    with Warp(nonmidnight_loan, datetime(2026, 3, 6, 19, 53, 0, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800"))

    assert settlement.interest_paid == Money("111.62")
    assert settlement.mora_paid == Money("0.00")
    assert settlement.fine_paid == Money("0.00")
    assert settlement.principal_paid == Money("688.38")
    assert settlement.remaining_balance == Money("322.64")


def test_allocation_count(nonmidnight_loan):
    """Payment of 800 touches 3 of the 4 installments."""
    with Warp(nonmidnight_loan, datetime(2026, 3, 6, 19, 53, 0, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800"))

    assert len(settlement.allocations) == 3


def test_second_installment_allocation(nonmidnight_loan):
    """Second installment receives full scheduled principal, not fully covered."""
    with Warp(nonmidnight_loan, datetime(2026, 3, 6, 19, 53, 0, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800"))

    second = settlement.allocations[1]
    assert second.principal_allocated == Money("246.43")
    assert second.interest_allocated == Money("0.00")
    assert second.is_fully_covered is False


def test_third_installment_allocation(nonmidnight_loan):
    """Third installment receives remaining principal."""
    with Warp(nonmidnight_loan, datetime(2026, 3, 6, 19, 53, 0, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800"))

    third = settlement.allocations[2]
    assert third.principal_allocated == Money("235.81")
    assert third.interest_allocated == Money("0.00")
    assert third.is_fully_covered is False
