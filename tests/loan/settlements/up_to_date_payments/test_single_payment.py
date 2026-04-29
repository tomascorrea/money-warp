"""Settlement tests for a single on-time payment."""

from datetime import datetime, timezone

from money_warp import Money, Warp


def test_on_time_single_payment_schedule(three_installment_loan):
    """Original schedule has 3 installments of ~R$303.62."""
    original_schedule = three_installment_loan.get_original_schedule()

    assert original_schedule[0].payment_amount == Money("303.62")
    assert original_schedule[1].payment_amount == Money("303.62")
    assert original_schedule[2].payment_amount == Money("303.63")


def test_on_time_single_payment_allocation_count(three_installment_loan):
    """R$800 on the first due date touches all 3 installments."""
    with Warp(three_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800.00"))

    assert len(settlement.allocations) == 3


def test_on_time_single_payment_first_installment(three_installment_loan):
    """First installment is fully covered: principal + interest."""
    with Warp(three_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800.00"))

    first = settlement.allocations[0]
    assert first.principal_allocated == Money("292.99")
    assert first.interest_allocated == Money("10.63")
    assert first.fine_allocated == Money("0.00")
    assert first.mora_allocated == Money("0.00")
    assert first.is_fully_covered is True


def test_on_time_single_payment_second_installment(three_installment_loan):
    """Second installment fully covered via absorption from later pools."""
    with Warp(three_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800.00"))

    second = settlement.allocations[1]
    assert second.principal_allocated == Money("303.62")
    assert second.interest_allocated == Money("0.00")
    assert second.fine_allocated == Money("0.00")
    assert second.mora_allocated == Money("0.00")
    assert second.is_fully_covered is True


def test_on_time_single_payment_third_installment(three_installment_loan):
    """Third installment receives reduced principal after absorption, not fully covered."""
    with Warp(three_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("800.00"))

    third = settlement.allocations[2]
    assert third.principal_allocated == Money("192.76")
    assert third.interest_allocated == Money("0.00")
    assert third.fine_allocated == Money("0.00")
    assert third.mora_allocated == Money("0.00")
    assert third.is_fully_covered is False
