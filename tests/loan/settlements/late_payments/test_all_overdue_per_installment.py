"""Settlement tests for per-installment allocation when all installments are overdue.

Regression test for the original bug: when ALL installments are overdue, the
old code would spread fines across all 6 installments before touching mora or
interest.  The correct behaviour is to process each installment sequentially:
fine -> mora -> interest -> principal for inst 1 BEFORE any allocation to inst 2.

Scenario:
  - 6-installment loan (Mar-Aug 2025), all overdue by Aug 15
  - Single partial payment equal to one scheduled installment amount (354.34)
  - Inst 1 should absorb fine, mora, interest, and partial principal
  - Inst 2+ should receive NOTHING because inst 1 was not fully settled

This proves that inst 1's mora interest takes priority over inst 2's fine.
"""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money, MoraStrategy, Warp


@pytest.fixture
def all_overdue_loan():
    """6-installment loan where every due date is past."""
    return Loan(
        Money("2000"),
        InterestRate("24% annual"),
        [
            date(2025, 3, 1),
            date(2025, 4, 1),
            date(2025, 5, 1),
            date(2025, 6, 1),
            date(2025, 7, 1),
            date(2025, 8, 1),
        ],
        disbursement_date=datetime(2025, 2, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
        grace_period_days=0,
        mora_interest_rate=InterestRate("12% annual"),
        mora_strategy=MoraStrategy.COMPOUND,
    )


@pytest.fixture
def overdue_settlement(all_overdue_loan):
    """Pay one scheduled installment amount when everything is overdue."""
    payment_date = datetime(2025, 8, 15, tzinfo=timezone.utc)
    with Warp(all_overdue_loan, payment_date) as warped:
        settlement = warped.record_payment(Money("354.34"), payment_date)
        return warped, settlement


def test_settlement_fine_paid(overdue_settlement):
    """Only inst 1's fine (7.09) is paid — not all 6 overdue fines."""
    _, s = overdue_settlement
    assert s.fine_paid == Money("7.09")


def test_settlement_mora_paid(overdue_settlement):
    """Full accrued mora goes to inst 1."""
    _, s = overdue_settlement
    assert s.mora_paid == Money("108.21")


def test_settlement_interest_paid(overdue_settlement):
    _, s = overdue_settlement
    assert s.interest_paid == Money("33.28")


def test_settlement_principal_paid(overdue_settlement):
    """The remainder after fine + mora + interest goes to principal."""
    _, s = overdue_settlement
    assert s.principal_paid == Money("205.77")


def test_settlement_remaining_balance(overdue_settlement):
    _, s = overdue_settlement
    assert s.remaining_balance == Money("1794.23")


def test_only_first_installment_receives_allocation(overdue_settlement):
    """The per-installment order means only inst 1 gets anything."""
    _, s = overdue_settlement
    assert len(s.allocations) == 1
    assert s.allocations[0].installment_number == 1


def test_first_installment_allocation_breakdown(overdue_settlement):
    _, s = overdue_settlement
    a = s.allocations[0]
    assert a.fine_allocated == Money("7.09")
    assert a.mora_allocated == Money("108.21")
    assert a.interest_allocated == Money("33.28")
    assert a.principal_allocated == Money("205.77")
    assert a.is_fully_covered is False


def test_fine_balance_after_payment(overdue_settlement):
    """Five installments' fines remain unpaid."""
    loan, _ = overdue_settlement
    assert loan.fine_balance == Money("35.43")
