"""Settlement tests for many small partial payments across installments.

Scenario: 6 payments of varying amounts, all on or before due dates.
Loan uses zero fine rate to isolate partial-payment allocation behavior.

Payment timeline:
  P1  R$100  Jan 25  (early, before 1st due date)
  P2  R$100  Jan 30  (early, before 1st due date)
  P3  R$110  Feb 01  (on 1st due date — completes inst 1)
  P4  R$200  Feb 15  (between 1st and 2nd due dates)
  P5  R$200  Mar 01  (on 2nd due date — completes inst 2)
  P6  R$200  Apr 01  (on 3rd due date — inst 3 remains partially unpaid)
"""

from datetime import datetime, timezone

import pytest

from money_warp import Money, Warp


@pytest.fixture
def six_partial_settlements(no_fine_loan):
    """Execute 6 partial payments via chained Warp contexts."""
    with Warp(no_fine_loan, datetime(2025, 1, 25, tzinfo=timezone.utc)) as w1:
        s1 = w1.pay_installment(Money("100.00"))
        with Warp(w1, datetime(2025, 1, 30, tzinfo=timezone.utc)) as w2:
            s2 = w2.pay_installment(Money("100.00"))
            with Warp(w2, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w3:
                s3 = w3.pay_installment(Money("110.00"))
                with Warp(w3, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w4:
                    s4 = w4.pay_installment(Money("200.00"))
                    with Warp(w4, datetime(2025, 3, 1, tzinfo=timezone.utc)) as w5:
                        s5 = w5.pay_installment(Money("200.00"))
                        with Warp(w5, datetime(2025, 4, 1, tzinfo=timezone.utc)) as w6:
                            s6 = w6.pay_installment(Money("200.00"))
                            return w6, [s1, s2, s3, s4, s5, s6]


# --- No fines or mora in any payment ---


@pytest.mark.parametrize("payment_index", [0, 1, 2, 3, 4, 5])
def test_partial_payment_no_fines(six_partial_settlements, payment_index):
    """Every payment has zero fines (all on or before due dates, zero fine rate)."""
    _, settlements = six_partial_settlements
    assert settlements[payment_index].fine_paid == Money("0.00")


@pytest.mark.parametrize("payment_index", [0, 1, 2, 3, 4, 5])
def test_partial_payment_no_mora(six_partial_settlements, payment_index):
    """Every payment has zero mora (all on or before due dates)."""
    _, settlements = six_partial_settlements
    assert settlements[payment_index].mora_paid == Money("0.00")


# --- Payment 1: R$100 on Jan 25 ---


def test_p1_settlement_totals(six_partial_settlements):
    """First payment: interest to due date (10.63), rest to principal."""
    _, settlements = six_partial_settlements
    assert settlements[0].interest_paid == Money("10.63")
    assert settlements[0].principal_paid == Money("89.37")


def test_p1_first_installment(six_partial_settlements):
    """Inst 1 gets all of P1 — not yet fully covered."""
    _, settlements = six_partial_settlements
    a = settlements[0].allocations[0]
    assert a.installment_number == 1
    assert a.principal_allocated == Money("89.37")
    assert a.interest_allocated == Money("10.63")
    assert a.is_fully_covered is False


# --- Payment 2: R$100 on Jan 30 ---


def test_p2_settlement_totals(six_partial_settlements):
    """Second payment: small interest for 5-day period, rest to principal."""
    _, settlements = six_partial_settlements
    assert settlements[1].interest_paid == Money("2.15")
    assert settlements[1].principal_paid == Money("97.85")


def test_p2_allocation_count(six_partial_settlements):
    """P2 touches 2 installments (inst 1 principal + inst 2 interest spillover)."""
    _, settlements = six_partial_settlements
    assert len(settlements[1].allocations) == 2


def test_p2_first_installment(six_partial_settlements):
    """Inst 1 gets principal portion — still not fully covered."""
    _, settlements = six_partial_settlements
    a = settlements[1].allocations[0]
    assert a.installment_number == 1
    assert a.principal_allocated == Money("97.85")
    assert a.interest_allocated == Money("0.00")
    assert a.is_fully_covered is False


# --- Payment 3: R$110 on Feb 1 (completes installment 1) ---


def test_p3_completes_installment_one(six_partial_settlements):
    """P3 on the first due date finishes off installment 1."""
    _, settlements = six_partial_settlements
    first_alloc = settlements[2].allocations[0]
    assert first_alloc.installment_number == 1
    assert first_alloc.principal_allocated == Money("105.77")
    assert first_alloc.is_fully_covered is True


# --- Payment 4: R$200 on Feb 15 ---


def test_p4_settlement_totals(six_partial_settlements):
    """P4 between due dates: 6.40 interest, 193.60 principal."""
    _, settlements = six_partial_settlements
    assert settlements[3].interest_paid == Money("6.40")
    assert settlements[3].principal_paid == Money("193.60")


def test_p4_allocation_count(six_partial_settlements):
    """P4 touches inst 2 (principal+interest) and inst 3 (interest spillover)."""
    _, settlements = six_partial_settlements
    assert len(settlements[3].allocations) == 2


def test_p4_second_installment(six_partial_settlements):
    """Inst 2 gets bulk of P4 — not yet fully covered."""
    _, settlements = six_partial_settlements
    a = settlements[3].allocations[0]
    assert a.installment_number == 2
    assert a.principal_allocated == Money("193.60")
    assert a.interest_allocated == Money("3.75")
    assert a.is_fully_covered is False


# --- Payment 5: R$200 on Mar 1 (completes installment 2) ---


def test_p5_completes_installment_two(six_partial_settlements):
    """P5 on the second due date finishes off installment 2."""
    _, settlements = six_partial_settlements
    first_alloc = settlements[4].allocations[0]
    assert first_alloc.installment_number == 2
    assert first_alloc.principal_allocated == Money("99.89")
    assert first_alloc.is_fully_covered is True


# --- Payment 6: R$200 on Apr 1 (inst 3 remains partially unpaid) ---


def test_p6_third_installment_not_covered(six_partial_settlements):
    """Inst 3 gets all of P6 plus interest spill — still NOT fully covered."""
    _, settlements = six_partial_settlements
    a = settlements[5].allocations[0]
    assert a.installment_number == 3
    assert a.principal_allocated == Money("197.59")
    assert a.interest_allocated == Money("2.41")
    assert a.is_fully_covered is False


# --- Final state ---


def test_final_installment_one_paid(six_partial_settlements):
    """Installment 1 is fully paid after all 6 payments."""
    loan, _ = six_partial_settlements
    assert loan.installments[0].is_fully_paid is True


def test_final_installment_two_paid(six_partial_settlements):
    """Installment 2 is fully paid after all 6 payments."""
    loan, _ = six_partial_settlements
    assert loan.installments[1].is_fully_paid is True


def test_final_installment_three_not_paid(six_partial_settlements):
    """Installment 3 still has a remaining balance (R$910 < total owed)."""
    loan, _ = six_partial_settlements
    assert loan.installments[2].is_fully_paid is False
    assert loan.installments[2].balance == Money("0.87")
