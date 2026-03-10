"""Settlement tests for a late second payment following an early first payment."""

from datetime import datetime, timezone

from money_warp import Money, Warp


def test_late_after_early_settlement_totals(three_installment_loan):
    """R$300 on Mar 15 after an early R$400 on Jan 20.

    Fines are applied for both due dates (Feb 1 and Mar 1) because
    the early payment window doesn't cover either.
    """
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("400.00"))

        with Warp(w, datetime(2025, 3, 15, tzinfo=timezone.utc)) as w2:
            settlement = w2.pay_installment(Money("300.00"))

    assert settlement.fine_paid == Money("12.14")
    assert settlement.mora_paid == Money("2.73")
    assert settlement.interest_paid == Money("7.73")
    assert settlement.principal_paid == Money("277.39")
    assert settlement.remaining_balance == Money("223.46")


def test_late_after_early_allocation_count(three_installment_loan):
    """Second late payment touches 3 installments."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("400.00"))

        with Warp(w, datetime(2025, 3, 15, tzinfo=timezone.utc)) as w2:
            settlement = w2.pay_installment(Money("300.00"))

    assert len(settlement.allocations) == 3


def test_late_after_early_first_installment(three_installment_loan):
    """Inst 1 gets its fine only (interest + principal already covered by early payment)."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("400.00"))

        with Warp(w, datetime(2025, 3, 15, tzinfo=timezone.utc)) as w2:
            settlement = w2.pay_installment(Money("300.00"))

    first = settlement.allocations[0]
    assert first.installment_number == 1
    assert first.principal_allocated == Money("0.00")
    assert first.interest_allocated == Money("0.00")
    assert first.fine_allocated == Money("6.07")
    assert first.mora_allocated == Money("0.00")
    assert first.is_fully_covered is True


def test_late_after_early_second_installment(three_installment_loan):
    """Inst 2 gets its fine, mora, full interest, and partial principal."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("400.00"))

        with Warp(w, datetime(2025, 3, 15, tzinfo=timezone.utc)) as w2:
            settlement = w2.pay_installment(Money("300.00"))

    second = settlement.allocations[1]
    assert second.installment_number == 2
    assert second.principal_allocated == Money("200.80")
    assert second.interest_allocated == Money("6.44")
    assert second.fine_allocated == Money("6.07")
    assert second.mora_allocated == Money("2.73")
    assert second.is_fully_covered is True


def test_late_after_early_third_installment(three_installment_loan):
    """Inst 3 gets leftover principal and partial interest."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("400.00"))

        with Warp(w, datetime(2025, 3, 15, tzinfo=timezone.utc)) as w2:
            settlement = w2.pay_installment(Money("300.00"))

    third = settlement.allocations[2]
    assert third.installment_number == 3
    assert third.principal_allocated == Money("76.59")
    assert third.interest_allocated == Money("1.29")
    assert third.fine_allocated == Money("0.00")
    assert third.mora_allocated == Money("0.00")
    assert third.is_fully_covered is False
