"""Tests for MonthlyBillingCycle."""

from datetime import datetime, timezone

import pytest

from money_warp.billing_cycle import MonthlyBillingCycle

# --- Creation tests ---


def test_monthly_billing_cycle_default_parameters():
    cycle = MonthlyBillingCycle()
    assert cycle.closing_day == 1
    assert cycle.payment_due_days == 15


def test_monthly_billing_cycle_custom_parameters():
    cycle = MonthlyBillingCycle(closing_day=28, payment_due_days=10)
    assert cycle.closing_day == 28


@pytest.mark.parametrize("bad_day", [0, -1, 29, 31, 100])
def test_monthly_billing_cycle_invalid_closing_day(bad_day):
    with pytest.raises(ValueError, match="closing_day must be between 1 and 28"):
        MonthlyBillingCycle(closing_day=bad_day)


def test_monthly_billing_cycle_invalid_payment_due_days():
    with pytest.raises(ValueError, match="payment_due_days must be at least 1"):
        MonthlyBillingCycle(payment_due_days=0)


# --- closing_dates_between tests ---


def test_closing_dates_single_month():
    cycle = MonthlyBillingCycle(closing_day=15)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 20, tzinfo=timezone.utc)
    dates = cycle.closing_dates_between(start, end)
    assert len(dates) == 1
    assert dates[0].day == 15
    assert dates[0].month == 1


def test_closing_dates_multiple_months():
    cycle = MonthlyBillingCycle(closing_day=28)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 4, 30, tzinfo=timezone.utc)
    dates = cycle.closing_dates_between(start, end)
    assert len(dates) == 4
    assert [d.month for d in dates] == [1, 2, 3, 4]


def test_closing_dates_start_on_closing_day_excludes_same_day():
    cycle = MonthlyBillingCycle(closing_day=15)
    start = datetime(2024, 1, 15, 23, 59, 59, tzinfo=timezone.utc)
    end = datetime(2024, 3, 20, tzinfo=timezone.utc)
    dates = cycle.closing_dates_between(start, end)
    assert dates[0].month == 2


def test_closing_dates_empty_when_no_complete_cycle():
    cycle = MonthlyBillingCycle(closing_day=28)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 10, tzinfo=timezone.utc)
    dates = cycle.closing_dates_between(start, end)
    assert dates == []


def test_closing_dates_year_boundary():
    cycle = MonthlyBillingCycle(closing_day=1)
    start = datetime(2024, 11, 15, tzinfo=timezone.utc)
    end = datetime(2025, 2, 15, tzinfo=timezone.utc)
    dates = cycle.closing_dates_between(start, end)
    assert len(dates) == 3
    assert dates[0].month == 12
    assert dates[1].year == 2025
    assert dates[1].month == 1
    assert dates[2].month == 2


# --- due_date_for tests ---


def test_due_date_default_offset():
    cycle = MonthlyBillingCycle(closing_day=28, payment_due_days=15)
    closing = datetime(2024, 1, 28, tzinfo=timezone.utc)
    due = cycle.due_date_for(closing)
    assert due.month == 2
    assert due.day == 12


def test_due_date_custom_offset():
    cycle = MonthlyBillingCycle(closing_day=1, payment_due_days=10)
    closing = datetime(2024, 3, 1, tzinfo=timezone.utc)
    due = cycle.due_date_for(closing)
    assert due.day == 11
    assert due.month == 3


# --- repr ---


def test_monthly_billing_cycle_repr():
    cycle = MonthlyBillingCycle(closing_day=5, payment_due_days=20)
    assert "5" in repr(cycle)
    assert "20" in repr(cycle)
