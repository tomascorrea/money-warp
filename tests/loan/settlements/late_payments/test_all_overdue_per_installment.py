"""Settlement tests for per-installment allocation when all installments are overdue.

Scenario:
  - 6-installment loan (Mar-Aug 2025), all overdue by Aug 15
  - Single partial payment equal to one scheduled installment amount (354.34)
  - Loan-level allocation prioritises: fines -> mora -> interest -> principal
  - Absorption pulls fines, mora, and interest from later installments' pools
    into inst 1, so only one allocation is created (all money goes to inst 1)
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
    """All six installments' fines are paid (loan-level priority: fines first)."""
    _, s = overdue_settlement
    assert s.fine_paid == Money("42.52")


def test_settlement_mora_paid(overdue_settlement):
    """Full accrued mora goes to inst 1."""
    _, s = overdue_settlement
    assert s.mora_paid == Money("108.21")


def test_settlement_interest_paid(overdue_settlement):
    """Interest covers all six installments' contractual interest (loan-level)."""
    _, s = overdue_settlement
    assert s.interest_paid == Money("126.06")


def test_settlement_principal_paid(overdue_settlement):
    """Principal is the residual after all fines, mora, and interest."""
    _, s = overdue_settlement
    assert s.principal_paid == Money("77.55")


def test_settlement_remaining_balance(overdue_settlement):
    _, s = overdue_settlement
    assert s.remaining_balance == Money("1922.45")


def test_single_installment_receives_allocation(overdue_settlement):
    """Absorption funnels all money into inst 1 — only one allocation created."""
    _, s = overdue_settlement
    assert len(s.allocations) == 1
    assert s.allocations[0].installment_number == 1


def test_first_installment_allocation_breakdown(overdue_settlement):
    """Inst 1 absorbs all fines, mora, interest, and residual principal."""
    _, s = overdue_settlement
    a = s.allocations[0]
    assert a.fine_allocated == Money("42.52")
    assert a.mora_allocated == Money("108.21")
    assert a.interest_allocated == Money("126.06")
    assert a.principal_allocated == Money("77.55")
    assert a.is_fully_covered is False


def test_fine_balance_after_payment(overdue_settlement):
    """All fines are paid because loan-level allocation settles fines first."""
    loan, _ = overdue_settlement
    assert loan.fine_balance == Money("0.00")
