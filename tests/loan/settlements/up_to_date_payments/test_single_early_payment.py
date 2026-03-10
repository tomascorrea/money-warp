"""Settlement tests for a single early payment using pay_installment.

With pay_installment, interest accrues up to the due date even when
paying early, so the first installment is fully covered.
"""

from datetime import datetime, timezone

from money_warp import Money, Warp


def test_single_early_payment_settlement_totals(three_installment_loan):
    """R$400 on Jan 20 — interest accrues to the due date (Feb 1)."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("400.00"))

    assert settlement.interest_paid == Money("10.63")
    assert settlement.principal_paid == Money("389.37")
    assert settlement.fine_paid == Money("0.00")
    assert settlement.mora_paid == Money("0.00")
    assert settlement.remaining_balance == Money("500.85")


def test_single_early_payment_allocation_count(three_installment_loan):
    """Early R$400 payment touches 2 installments (principal spills over)."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("400.00"))

    assert len(settlement.allocations) == 2


def test_single_early_payment_first_installment(three_installment_loan):
    """First installment is fully covered (interest to due date + full principal)."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("400.00"))

    first = settlement.allocations[0]
    assert first.installment_number == 1
    assert first.principal_allocated == Money("292.99")
    assert first.interest_allocated == Money("10.63")
    assert first.fine_allocated == Money("0.00")
    assert first.mora_allocated == Money("0.00")
    assert first.is_fully_covered is True


def test_single_early_payment_second_installment(three_installment_loan):
    """Second installment gets only leftover principal."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("400.00"))

    second = settlement.allocations[1]
    assert second.installment_number == 2
    assert second.principal_allocated == Money("96.38")
    assert second.interest_allocated == Money("0.00")
    assert second.fine_allocated == Money("0.00")
    assert second.mora_allocated == Money("0.00")
    assert second.is_fully_covered is False
