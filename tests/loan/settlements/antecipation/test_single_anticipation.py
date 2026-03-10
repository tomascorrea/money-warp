"""Settlement tests for a single anticipation payment.

With anticipate_payment, interest accrues only up to the payment date
(not the due date), so the borrower gets a discount for paying early.
"""

from datetime import datetime, timezone

from money_warp import Money, Warp


def test_single_anticipation_settlement_totals(three_installment_loan):
    """R$400 on Jan 20 — interest accrues only to Jan 20 (19 days, not 31)."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        settlement = w.anticipate_payment(Money("400.00"))

    assert settlement.interest_paid == Money("6.50")
    assert settlement.principal_paid == Money("393.50")
    assert settlement.fine_paid == Money("0.00")
    assert settlement.mora_paid == Money("0.00")
    assert settlement.remaining_balance == Money("496.72")


def test_single_anticipation_allocation_count(three_installment_loan):
    """Anticipation of R$400 touches 2 installments (principal spills over)."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        settlement = w.anticipate_payment(Money("400.00"))

    assert len(settlement.allocations) == 2


def test_single_anticipation_first_installment(three_installment_loan):
    """First installment is NOT fully covered (discounted interest < scheduled)."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        settlement = w.anticipate_payment(Money("400.00"))

    first = settlement.allocations[0]
    assert first.installment_number == 1
    assert first.principal_allocated == Money("292.99")
    assert first.interest_allocated == Money("6.50")
    assert first.fine_allocated == Money("0.00")
    assert first.mora_allocated == Money("0.00")
    assert first.is_fully_covered is False


def test_single_anticipation_second_installment(three_installment_loan):
    """Second installment gets only leftover principal."""
    with Warp(three_installment_loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        settlement = w.anticipate_payment(Money("400.00"))

    second = settlement.allocations[1]
    assert second.installment_number == 2
    assert second.principal_allocated == Money("100.51")
    assert second.interest_allocated == Money("0.00")
    assert second.fine_allocated == Money("0.00")
    assert second.mora_allocated == Money("0.00")
    assert second.is_fully_covered is False
