"""Settlement tests for late payments that span installment boundaries.

Scenario: 2 large late payments (R$500 each) that each cross into the
next installment's principal, while also paying fines and mora.

Payment timeline:
  P1  R$500  Feb 16  (15 days late on inst 1 — covers inst 1 fully, spills into inst 2)
  P2  R$500  Apr 15  (past both inst 2 and inst 3 due dates — covers everything, loan paid off)
"""

from datetime import datetime, timezone

import pytest

from money_warp import Money, Warp


@pytest.fixture
def late_cross_settlements(loan_with_fine):
    """Execute 2 large late payments via chained Warp contexts."""
    with Warp(loan_with_fine, datetime(2025, 2, 16, tzinfo=timezone.utc)) as w1:
        s1 = w1.pay_installment(Money("500.00"))
        with Warp(w1, datetime(2025, 4, 15, tzinfo=timezone.utc)) as w2:
            s2 = w2.pay_installment(Money("500.00"))
            return w2, [s1, s2]


# --- Payment 1: R$500 on Feb 16 (15 days late) ---


def test_p1_settlement_totals(late_cross_settlements):
    """P1 pays fine (6.07), mora (5.19), interest (10.63), rest to principal."""
    _, settlements = late_cross_settlements
    assert settlements[0].fine_paid == Money("6.07")
    assert settlements[0].mora_paid == Money("5.19")
    assert settlements[0].interest_paid == Money("10.63")
    assert settlements[0].principal_paid == Money("478.11")
    assert settlements[0].remaining_balance == Money("412.11")


def test_p1_allocation_count(late_cross_settlements):
    """P1 spans 2 installments."""
    _, settlements = late_cross_settlements
    assert len(settlements[0].allocations) == 2


def test_p1_first_installment(late_cross_settlements):
    """Inst 1 absorbs fine, mora, interest, and principal — fully covered."""
    _, settlements = late_cross_settlements
    a = settlements[0].allocations[0]
    assert a.installment_number == 1
    assert a.principal_allocated == Money("292.99")
    assert a.interest_allocated == Money("10.63")
    assert a.fine_allocated == Money("6.07")
    assert a.mora_allocated == Money("5.19")
    assert a.is_fully_covered is True


def test_p1_second_installment(late_cross_settlements):
    """Inst 2 gets excess principal only — not yet covered."""
    _, settlements = late_cross_settlements
    a = settlements[0].allocations[1]
    assert a.installment_number == 2
    assert a.principal_allocated == Money("185.12")
    assert a.interest_allocated == Money("0.00")
    assert a.fine_allocated == Money("0.00")
    assert a.mora_allocated == Money("0.00")
    assert a.is_fully_covered is False


# --- Payment 2: R$500 on Apr 15 (past all due dates) ---


def test_p2_settlement_totals(late_cross_settlements):
    """P2 has fines for 2 due dates, mora, contractual interest for inst 3, and pays off the loan."""
    _, settlements = late_cross_settlements
    assert settlements[1].fine_paid == Money("12.15")
    assert settlements[1].mora_paid == Money("7.20")
    assert settlements[1].interest_paid == Money("5.64")
    assert settlements[1].principal_paid == Money("475.02")
    assert settlements[1].remaining_balance == Money("0.00")


def test_p2_allocation_count(late_cross_settlements):
    """P2 spans 2 installments (inst 2 and inst 3)."""
    _, settlements = late_cross_settlements
    assert len(settlements[1].allocations) == 2


def test_p2_second_installment(late_cross_settlements):
    """Inst 2 gets its fine, mora, contractual interest, and remaining principal — covered."""
    _, settlements = late_cross_settlements
    a = settlements[1].allocations[0]
    assert a.installment_number == 2
    assert a.principal_allocated == Money("112.06")
    assert a.interest_allocated == Money("5.64")
    assert a.fine_allocated == Money("6.07")
    assert a.mora_allocated == Money("7.20")
    assert a.is_fully_covered is True


def test_p2_third_installment(late_cross_settlements):
    """Inst 3 gets its fine, full principal, and spill — covered (loan fully paid)."""
    _, settlements = late_cross_settlements
    a = settlements[1].allocations[1]
    assert a.installment_number == 3
    assert a.principal_allocated == Money("362.96")
    assert a.interest_allocated == Money("0.00")
    assert a.fine_allocated == Money("6.07")
    assert a.mora_allocated == Money("0.00")
    assert a.is_fully_covered is True


# --- Final state ---


def test_final_loan_fully_paid(late_cross_settlements):
    """Loan principal is fully paid off."""
    loan, _ = late_cross_settlements
    assert loan.principal_balance == Money("0.00")


def test_final_installment_one_paid(late_cross_settlements):
    """Installment 1 is fully paid."""
    loan, _ = late_cross_settlements
    assert loan.installments[0].is_fully_paid is True
