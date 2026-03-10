"""Settlement tests for payments that span installment boundaries.

Scenario: 2 large payments (R$500 and R$400) that each cover more
than one installment's principal, demonstrating how the allocation
distributes excess across boundaries.

Payment timeline:
  P1  R$500  Feb 01  (covers inst 1 fully + spills into inst 2)
  P2  R$400  Mar 01  (covers inst 2 partial + spills into inst 3)
"""

from datetime import datetime, timezone

import pytest

from money_warp import Money, Warp


@pytest.fixture
def cross_installment_settlements(no_fine_loan):
    """Execute 2 large payments via chained Warp contexts."""
    with Warp(no_fine_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w1:
        s1 = w1.pay_installment(Money("500.00"))
        with Warp(w1, datetime(2025, 3, 1, tzinfo=timezone.utc)) as w2:
            s2 = w2.pay_installment(Money("400.00"))
            return w2, [s1, s2]


# --- No fines or mora ---


@pytest.mark.parametrize("payment_index", [0, 1])
def test_cross_installment_no_fines(cross_installment_settlements, payment_index):
    _, settlements = cross_installment_settlements
    assert settlements[payment_index].fine_paid == Money("0.00")


@pytest.mark.parametrize("payment_index", [0, 1])
def test_cross_installment_no_mora(cross_installment_settlements, payment_index):
    _, settlements = cross_installment_settlements
    assert settlements[payment_index].mora_paid == Money("0.00")


# --- Payment 1: R$500 on Feb 1 (spans inst 1 → inst 2) ---


def test_p1_settlement_totals(cross_installment_settlements):
    """P1 pays full scheduled interest (10.63) and 489.37 principal."""
    _, settlements = cross_installment_settlements
    assert settlements[0].interest_paid == Money("10.63")
    assert settlements[0].principal_paid == Money("489.37")
    assert settlements[0].remaining_balance == Money("400.85")


def test_p1_allocation_count(cross_installment_settlements):
    """P1 spans 2 installments."""
    _, settlements = cross_installment_settlements
    assert len(settlements[0].allocations) == 2


def test_p1_first_installment_fully_covered(cross_installment_settlements):
    """Inst 1 fully covered: scheduled interest + full principal."""
    _, settlements = cross_installment_settlements
    a = settlements[0].allocations[0]
    assert a.installment_number == 1
    assert a.principal_allocated == Money("292.99")
    assert a.interest_allocated == Money("10.63")
    assert a.is_fully_covered is True


def test_p1_second_installment_partial(cross_installment_settlements):
    """Inst 2 gets excess principal (196.38), not fully covered."""
    _, settlements = cross_installment_settlements
    a = settlements[0].allocations[1]
    assert a.installment_number == 2
    assert a.principal_allocated == Money("196.38")
    assert a.interest_allocated == Money("0.00")
    assert a.is_fully_covered is False


# --- Payment 2: R$400 on Mar 1 (spans inst 2 → inst 3) ---


def test_p2_settlement_totals(cross_installment_settlements):
    """P2 accrues less interest (4.32) because prior principal reduction."""
    _, settlements = cross_installment_settlements
    assert settlements[1].interest_paid == Money("4.32")
    assert settlements[1].principal_paid == Money("395.68")
    assert settlements[1].remaining_balance == Money("5.17")


def test_p2_allocation_count(cross_installment_settlements):
    """P2 spans 2 installments."""
    _, settlements = cross_installment_settlements
    assert len(settlements[1].allocations) == 2


def test_p2_second_installment(cross_installment_settlements):
    """Inst 2 gets remaining principal (100.80) and partial interest (4.32)."""
    _, settlements = cross_installment_settlements
    a = settlements[1].allocations[0]
    assert a.installment_number == 2
    assert a.principal_allocated == Money("100.80")
    assert a.interest_allocated == Money("4.32")
    assert a.is_fully_covered is False


def test_p2_third_installment(cross_installment_settlements):
    """Inst 3 gets excess principal (294.88), not fully covered."""
    _, settlements = cross_installment_settlements
    a = settlements[1].allocations[1]
    assert a.installment_number == 3
    assert a.principal_allocated == Money("294.88")
    assert a.interest_allocated == Money("0.00")
    assert a.is_fully_covered is False


# --- Final state ---


def test_final_installment_one_paid(cross_installment_settlements):
    """Installment 1 is fully paid."""
    loan, _ = cross_installment_settlements
    assert loan.installments[0].is_fully_paid is True


def test_final_installment_two_not_paid(cross_installment_settlements):
    """Installment 2 has remaining interest (actual accrual < scheduled)."""
    loan, _ = cross_installment_settlements
    assert loan.installments[1].is_fully_paid is False
    assert loan.installments[1].balance == Money("2.12")


def test_final_installment_three_not_paid(cross_installment_settlements):
    """Installment 3 still owes interest + partial principal."""
    loan, _ = cross_installment_settlements
    assert loan.installments[2].is_fully_paid is False
    assert loan.installments[2].balance == Money("8.75")
