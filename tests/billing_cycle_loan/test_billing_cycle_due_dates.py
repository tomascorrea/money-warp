"""Tests for BaseBillingCycle.due_dates_between."""

from datetime import date, datetime, timezone

from money_warp.billing_cycle import MonthlyBillingCycle


def test_derived_due_dates_from_closing_dates():
    bc = MonthlyBillingCycle(closing_day=28, payment_due_days=15)
    result = bc.due_dates_between(
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 4, 30, tzinfo=timezone.utc),
        timezone.utc,
    )
    assert result == [
        date(2025, 2, 12),
        date(2025, 3, 15),
        date(2025, 4, 12),
        date(2025, 5, 13),
    ]


def test_explicit_due_dates_override():
    explicit = [date(2025, 2, 10), date(2025, 3, 10), date(2025, 4, 10)]
    bc = MonthlyBillingCycle(closing_day=28, payment_due_days=15, due_dates=explicit)
    result = bc.due_dates_between(
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 4, 30, tzinfo=timezone.utc),
        timezone.utc,
    )
    assert result == [date(2025, 2, 10), date(2025, 3, 10), date(2025, 4, 10)]


def test_explicit_due_dates_filtered_by_range():
    explicit = [date(2025, 2, 10), date(2025, 3, 10), date(2025, 4, 10)]
    bc = MonthlyBillingCycle(closing_day=28, payment_due_days=15, due_dates=explicit)
    result = bc.due_dates_between(
        datetime(2025, 2, 15, tzinfo=timezone.utc),
        datetime(2025, 3, 15, tzinfo=timezone.utc),
        timezone.utc,
    )
    assert result == [date(2025, 3, 10)]


def test_explicit_due_dates_sorted():
    unsorted = [date(2025, 4, 10), date(2025, 2, 10), date(2025, 3, 10)]
    bc = MonthlyBillingCycle(closing_day=28, payment_due_days=15, due_dates=unsorted)
    result = bc.due_dates_between(
        datetime(2025, 1, 1, tzinfo=timezone.utc),
        datetime(2025, 5, 1, tzinfo=timezone.utc),
        timezone.utc,
    )
    assert result == [date(2025, 2, 10), date(2025, 3, 10), date(2025, 4, 10)]


def test_no_explicit_due_dates_returns_none():
    bc = MonthlyBillingCycle(closing_day=28, payment_due_days=15)
    assert bc._explicit_due_dates is None
