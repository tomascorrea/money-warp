"""Tests for BillingCycleLoan payment settlements."""

from datetime import datetime, timezone

from money_warp import Money


def test_on_time_payment_first_installment(simple_loan):
    s = simple_loan.record_payment(
        Money("1022.58"), datetime(2025, 2, 12, tzinfo=timezone.utc),
    )
    assert s.fine_paid == Money("0.00")
    assert s.mora_paid == Money("0.00")
    assert s.interest_paid == Money("39.38")
    assert s.principal_paid == Money("983.20")
    assert s.remaining_balance == Money("2016.80")


def test_on_time_payment_all_installments(simple_loan):
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 2, 12, tzinfo=timezone.utc))
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 3, 15, tzinfo=timezone.utc))
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 4, 12, tzinfo=timezone.utc))

    assert simple_loan.is_paid_off is True
    assert len(simple_loan.settlements) == 3


def test_on_time_second_settlement_values(simple_loan):
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 2, 12, tzinfo=timezone.utc))
    s2 = simple_loan.record_payment(
        Money("1022.58"), datetime(2025, 3, 15, tzinfo=timezone.utc),
    )
    assert s2.fine_paid == Money("0.00")
    assert s2.mora_paid == Money("0.00")
    assert s2.interest_paid == Money("19.51")
    assert s2.principal_paid == Money("1003.07")


def test_on_time_third_settlement_values(simple_loan):
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 2, 12, tzinfo=timezone.utc))
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 3, 15, tzinfo=timezone.utc))
    s3 = simple_loan.record_payment(
        Money("1022.58"), datetime(2025, 4, 12, tzinfo=timezone.utc),
    )
    assert s3.fine_paid == Money("0.00")
    assert s3.mora_paid == Money("0.00")
    assert s3.interest_paid == Money("8.85")
    assert s3.principal_paid == Money("1013.73")


def test_allocation_installment_numbers(simple_loan):
    s = simple_loan.record_payment(
        Money("1022.58"), datetime(2025, 2, 12, tzinfo=timezone.utc),
    )
    assert len(s.allocations) == 1
    assert s.allocations[0].installment_number == 1
    assert s.allocations[0].is_fully_covered is True
