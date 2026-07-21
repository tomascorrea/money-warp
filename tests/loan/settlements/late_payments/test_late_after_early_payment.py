"""Settlement tests for a late second payment following an early first payment."""

from datetime import datetime, timezone

from money_warp import Money, Warp


def test_late_after_early_settlement_totals(three_installment_loan):
    """R$300 on Mar 15 after an early R$400 on Jan 20.

    Installment 1 was fully prepaid, so it is exempt from fines
    (issue #102); only the Mar 1 due date is fined.
    """
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("400.00"))

        with Warp(w, datetime(2025, 3, 15, tzinfo=timezone.utc)) as w2:
            settlement = w2.pay_installment(Money("300.00"))

    assert settlement.fine_paid == Money("6.07")
    assert settlement.mora_paid == Money("2.72")
    assert settlement.interest_paid == Money("5.40")
    assert settlement.principal_paid == Money("285.81")
    assert settlement.remaining_balance == Money("215.04")


def test_late_after_early_allocation_count(three_installment_loan):
    """Second late payment touches installments 2 and 3 only."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("400.00"))

        with Warp(w, datetime(2025, 3, 15, tzinfo=timezone.utc)) as w2:
            settlement = w2.pay_installment(Money("300.00"))

    assert len(settlement.allocations) == 2


def test_late_after_early_no_allocation_to_prepaid_first(three_installment_loan):
    """Inst 1 was fully prepaid and fine-exempt, so the late payment never touches it."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("400.00"))

        with Warp(w, datetime(2025, 3, 15, tzinfo=timezone.utc)) as w2:
            settlement = w2.pay_installment(Money("300.00"))

    assert 1 not in [a.installment_number for a in settlement.allocations]


def test_late_after_early_second_installment(three_installment_loan):
    """Inst 2 gets its fine, mora, full interest, and principal — fully covered via absorption."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("400.00"))

        with Warp(w, datetime(2025, 3, 15, tzinfo=timezone.utc)) as w2:
            settlement = w2.pay_installment(Money("300.00"))

    second = settlement.allocations[0]
    assert second.installment_number == 2
    assert second.principal_allocated == Money("201.84")
    assert second.interest_allocated == Money("5.40")
    assert second.fine_allocated == Money("6.07")
    assert second.mora_allocated == Money("2.72")
    assert second.is_fully_covered is True


def test_late_after_early_third_installment(three_installment_loan):
    """Inst 3 gets leftover principal only."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("400.00"))

        with Warp(w, datetime(2025, 3, 15, tzinfo=timezone.utc)) as w2:
            settlement = w2.pay_installment(Money("300.00"))

    third = settlement.allocations[1]
    assert third.installment_number == 3
    assert third.principal_allocated == Money("83.97")
    assert third.interest_allocated == Money("0.00")
    assert third.fine_allocated == Money("0.00")
    assert third.mora_allocated == Money("0.00")
    assert third.is_fully_covered is False
