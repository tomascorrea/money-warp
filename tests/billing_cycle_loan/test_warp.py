"""Tests for Warp (time travel) integration with BillingCycleLoan."""

from datetime import datetime, timezone

from money_warp import Money, Warp


def test_warp_produces_correct_type(simple_loan):
    with Warp(simple_loan, "2025-06-01") as warped:
        assert type(warped).__name__ == "BillingCycleLoan"


def test_warp_materialises_fines(simple_loan):
    with Warp(simple_loan, "2025-06-01") as warped:
        assert warped.total_fines == Money("61.35")
        assert warped.fine_balance == Money("61.35")


def test_warp_does_not_mutate_original(simple_loan):
    original_balance = simple_loan.fine_balance
    with Warp(simple_loan, "2025-06-01") as warped:
        _ = warped.fine_balance
    assert simple_loan.fine_balance == original_balance


def test_warp_principal_unchanged_without_payments(simple_loan):
    with Warp(simple_loan, "2025-06-01") as warped:
        assert warped.principal_balance == Money("3000.00")


def test_warp_with_payments(simple_loan):
    simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 2, 12, tzinfo=timezone.utc),
    )
    with Warp(simple_loan, "2025-06-01") as warped:
        assert warped.principal_balance == Money("2016.80")
        assert warped.total_fines == Money("40.90")
