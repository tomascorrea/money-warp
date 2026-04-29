"""Regression test for contractual interest loss on later installments.

Bug: when a partial payment leaves _next_unpaid_due_date stuck at D1
(because remaining_balance > schedule[0].ending_balance), any subsequent
payment after D1 gets interest_accrued=0 from compute_accrued_interest.
This zero becomes the interest_cap, preventing contractual interest from
being allocated to installments beyond the first.

Scenario (from bug report):
  - 2-installment loan: R$200 at 3.99% monthly
  - D1=2024-11-11, D2=2024-12-11, disbursement=2024-10-11
  - Schedule: inst 1 interest=8.14, inst 2 interest=4.02 (total=12.16)
  - P1  R$50   Jan 10  (partial — both D1 and D2 overdue)
  - P2  R$500  Jan 20  (settles the loan)

Expected: total interest collected across both settlements equals the
total scheduled interest (12.16).  Before the fix, P2 collected 0 interest
and 4.02 was permanently lost.

Because both due dates are past at P1 time, P1 partially collects inst 2's
interest.  P2 collects the remainder.
"""

from datetime import date, datetime

import pytest

from money_warp import InterestRate, Loan, Money, PriceScheduler, Warp


@pytest.fixture
def two_installment_loan():
    """2-installment loan matching the bug report."""
    return Loan(
        principal=Money(200),
        interest_rate=InterestRate("3.99% a.m."),
        due_dates=[date(2024, 11, 11), date(2024, 12, 11)],
        disbursement_date=datetime(2024, 10, 11),
        scheduler=PriceScheduler,
        mora_interest_rate=InterestRate("3.99% a.m."),
        fine_rate=InterestRate("2% a.m."),
    )


@pytest.fixture
def partial_then_full(two_installment_loan):
    """Execute partial payment then full settlement via chained Warp."""
    with Warp(two_installment_loan, datetime(2025, 1, 10)) as w1:
        s1 = w1.pay_installment(Money(50))
        with Warp(w1, datetime(2025, 1, 20)) as w2:
            s2 = w2.pay_installment(Money(500))
            return w2, [s1, s2]


def test_total_interest_equals_scheduled(partial_then_full):
    """Total interest across all settlements equals 16.18 (contractual + accrued)."""
    _, settlements = partial_then_full
    total = settlements[0].interest_paid + settlements[1].interest_paid
    assert total == Money("16.18")


def test_p1_collects_both_installments_interest(partial_then_full):
    """P1 collects all accrued interest (both installments' contractual interest)."""
    _, settlements = partial_then_full
    assert settlements[0].interest_paid == Money("12.16")


def test_p1_first_installment_gets_full_interest(partial_then_full):
    """Inst 1 absorbs all interest in P1 (12.16) via absorption from inst 2's pool."""
    _, settlements = partial_then_full
    a = settlements[0].allocations[0]
    assert a.installment_number == 1
    assert a.interest_allocated == Money("12.16")


def test_p1_has_no_second_installment_allocation(partial_then_full):
    """P1 only covers inst 1 after absorption — no allocation for inst 2."""
    _, settlements = partial_then_full
    inst2_allocs = [a for a in settlements[0].allocations if a.installment_number == 2]
    assert len(inst2_allocs) == 0


def test_p2_collects_remaining_interest(partial_then_full):
    """P2 collects inst 2's contractual interest (4.02), not absorbed by P1."""
    _, settlements = partial_then_full
    assert settlements[1].interest_paid == Money("4.02")


def test_p2_second_installment_gets_full_interest(partial_then_full):
    """Inst 2's allocation in P2 gets its full contractual interest (4.02)."""
    _, settlements = partial_then_full
    inst2_allocs = [a for a in settlements[1].allocations if a.installment_number == 2]
    assert len(inst2_allocs) == 1
    assert inst2_allocs[0].interest_allocated == Money("4.02")


def test_inst2_total_interest_equals_contractual(partial_then_full):
    """Inst 2's total interest across both settlements equals its scheduled amount (4.02)."""
    _, settlements = partial_then_full
    inst2_interest = Money.zero()
    for s in settlements:
        for a in s.allocations:
            if a.installment_number == 2:
                inst2_interest = inst2_interest + a.interest_allocated
    assert inst2_interest == Money("4.02")


def test_loan_is_fully_paid(partial_then_full):
    """After R$550 total the loan should be settled."""
    loan, _ = partial_then_full
    assert loan.is_paid_off is True
