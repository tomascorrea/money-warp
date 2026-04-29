"""Settlement tests for a single late payment with fines and mora."""

from datetime import datetime, timezone

from money_warp import Money, Warp


def test_single_late_payment_settlement_totals(loan_with_fine):
    """R$800 payment 15 days after the first due date triggers fine + mora."""
    with Warp(loan_with_fine, datetime(2025, 2, 16, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800.00"))

    assert settlement.fine_paid == Money("6.07")
    assert settlement.mora_paid == Money("5.19")


def test_single_late_payment_allocation_count(loan_with_fine):
    """Late R$800 payment touches all 3 installments."""
    with Warp(loan_with_fine, datetime(2025, 2, 16, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800.00"))

    assert len(settlement.allocations) == 3


def test_single_late_payment_first_installment(loan_with_fine):
    """First installment absorbs fine, mora, interest, and principal — fully covered."""
    with Warp(loan_with_fine, datetime(2025, 2, 16, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800.00"))

    first = settlement.allocations[0]
    assert first.principal_allocated == Money("292.99")
    assert first.interest_allocated == Money("10.63")
    assert first.fine_allocated == Money("6.07")
    assert first.mora_allocated == Money("5.19")
    assert first.is_fully_covered is True


def test_single_late_payment_second_installment(loan_with_fine):
    """Second installment absorbs extra principal from absorption, fully covered."""
    with Warp(loan_with_fine, datetime(2025, 2, 16, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800.00"))

    second = settlement.allocations[1]
    assert second.principal_allocated == Money("303.62")
    assert second.interest_allocated == Money("0.00")
    assert second.fine_allocated == Money("0.00")
    assert second.mora_allocated == Money("0.00")
    assert second.is_fully_covered is True


def test_single_late_payment_third_installment(loan_with_fine):
    """Third installment gets less principal after absorption, not fully covered."""
    with Warp(loan_with_fine, datetime(2025, 2, 16, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800.00"))

    third = settlement.allocations[2]
    assert third.principal_allocated == Money("181.50")
    assert third.interest_allocated == Money("0.00")
    assert third.fine_allocated == Money("0.00")
    assert third.mora_allocated == Money("0.00")
    assert third.is_fully_covered is False
