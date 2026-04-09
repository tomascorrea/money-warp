"""Tests for late payments and fines on billing-cycle loans."""

from datetime import datetime, timezone

from money_warp import Money


def test_late_payment_incurs_mora_and_fine(simple_loan):
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 4, tzinfo=timezone.utc),
    )
    assert s.fine_paid == Money("20.45")
    assert s.mora_paid == Money("18.93")
    assert s.interest_paid == Money("39.38")
    assert s.principal_paid == Money("943.82")


def test_late_payment_remaining_balance(simple_loan):
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 4, tzinfo=timezone.utc),
    )
    assert s.remaining_balance == Money("2056.18")


def test_late_payment_allocation_not_fully_covered(simple_loan):
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 4, tzinfo=timezone.utc),
    )
    assert s.allocations[0].is_fully_covered is False


def test_fines_applied_after_observation(simple_loan):
    fines = simple_loan.calculate_late_fines(datetime(2025, 3, 1, tzinfo=timezone.utc))
    assert fines == Money("20.45")
    assert simple_loan.fine_balance == Money("20.45")
