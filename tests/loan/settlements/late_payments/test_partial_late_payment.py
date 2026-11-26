"""Settlement tests for consecutive partial late payments on the same installment.

Scenario: 2 partial late payments where installment 1 remains uncovered after P1,
so both payments allocate mora to the same installment. This is the trigger
condition for the mora reconciliation bug (expected_mora must include prior
mora allocations, not just the current-period accrual).

Payment timeline:
  P1  R$100  Feb 16  (15 days late — partial, inst 1 stays uncovered)
  P2  R$300  Mar 15  (inst 1 still first uncovered, has prior mora)
"""

from datetime import datetime, timezone

import pytest

from money_warp import Money, Warp


@pytest.fixture
def partial_late_settlements(loan_with_fine):
    """Execute 2 partial late payments via chained Warp contexts."""
    with Warp(loan_with_fine, datetime(2025, 2, 16, tzinfo=timezone.utc)) as w1:
        s1 = w1.pay_installment(Money("100.00"))
        with Warp(w1, datetime(2025, 3, 15, tzinfo=timezone.utc)) as w2:
            s2 = w2.pay_installment(Money("300.00"))
            return w2, [s1, s2]


# --- Payment 1: R$100 on Feb 16 (partial late) ---


def test_p1_settlement_totals(partial_late_settlements):
    """P1 pays fine, mora, interest; remainder goes to principal."""
    _, settlements = partial_late_settlements
    assert settlements[0].fine_paid == Money("6.07")
    assert settlements[0].mora_paid == Money("1.74")
    assert settlements[0].interest_paid == Money("10.63")
    assert settlements[0].principal_paid == Money("81.55")
    assert settlements[0].remaining_balance == Money("808.67")


def test_p1_allocation_count(partial_late_settlements):
    """P1 only touches installment 1 (partial coverage)."""
    _, settlements = partial_late_settlements
    assert len(settlements[0].allocations) == 1


def test_p1_first_installment(partial_late_settlements):
    """Inst 1 absorbs all of P1 but is NOT fully covered."""
    _, settlements = partial_late_settlements
    a = settlements[0].allocations[0]
    assert a.installment_number == 1
    assert a.principal_allocated == Money("81.55")
    assert a.interest_allocated == Money("10.63")
    assert a.fine_allocated == Money("6.07")
    assert a.mora_allocated == Money("1.74")
    assert a.is_fully_covered is False


def test_p1_mora_reconciliation(partial_late_settlements):
    """P1 mora totals reconcile with per-installment allocations."""
    _, settlements = partial_late_settlements
    s = settlements[0]
    assert s.mora_paid == Money(sum(a.mora_allocated.raw_amount for a in s.allocations))


# --- Payment 2: R$300 on Mar 15 (inst 1 still uncovered, has prior mora) ---


def test_p2_settlement_totals(partial_late_settlements):
    """P2 pays fine, mora, contractual interest for inst 2, and principal."""
    _, settlements = partial_late_settlements
    assert settlements[1].fine_paid == Money("6.07")
    assert settlements[1].mora_paid == Money("4.77")
    assert settlements[1].interest_paid == Money("6.44")
    assert settlements[1].principal_paid == Money("282.72")
    assert settlements[1].remaining_balance == Money("525.95")


def test_p2_allocation_count(partial_late_settlements):
    """P2 touches 2 installments (finishes inst 1, starts inst 2)."""
    _, settlements = partial_late_settlements
    assert len(settlements[1].allocations) == 2


def test_p2_first_installment(partial_late_settlements):
    """Inst 1 receives the mora still owed on it and the remaining principal."""
    _, settlements = partial_late_settlements
    a = settlements[1].allocations[0]
    assert a.installment_number == 1
    assert a.principal_allocated == Money("211.44")
    assert a.interest_allocated == Money("0.00")
    assert a.fine_allocated == Money("0.00")
    assert a.mora_allocated == Money("3.14")
    assert a.is_fully_covered is True


def test_p2_second_installment(partial_late_settlements):
    """Inst 2 is already late, so it receives its own mora plus interest, fine, and principal."""
    _, settlements = partial_late_settlements
    a = settlements[1].allocations[1]
    assert a.installment_number == 2
    assert a.principal_allocated == Money("71.28")
    assert a.interest_allocated == Money("6.44")
    assert a.fine_allocated == Money("6.07")
    assert a.mora_allocated == Money("1.63")
    assert a.is_fully_covered is False


def test_p2_mora_reconciliation(partial_late_settlements):
    """P2 mora totals reconcile — the core invariant this scenario guards."""
    _, settlements = partial_late_settlements
    s = settlements[1]
    assert s.mora_paid == Money(sum(a.mora_allocated.raw_amount for a in s.allocations))


def test_p2_all_components_reconcile(partial_late_settlements):
    """Every settlement component equals the sum of its per-installment allocations."""
    _, settlements = partial_late_settlements
    s = settlements[1]
    assert s.fine_paid == Money(sum(a.fine_allocated.raw_amount for a in s.allocations))
    assert s.interest_paid == Money(sum(a.interest_allocated.raw_amount for a in s.allocations))
    assert s.mora_paid == Money(sum(a.mora_allocated.raw_amount for a in s.allocations))
    assert s.principal_paid == Money(sum(a.principal_allocated.raw_amount for a in s.allocations))
