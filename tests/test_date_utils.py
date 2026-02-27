"""Tests for date generation utilities - following project patterns."""

from datetime import datetime, timezone

import pytest

from money_warp import (
    generate_annual_dates,
    generate_biweekly_dates,
    generate_custom_interval_dates,
    generate_monthly_dates,
    generate_quarterly_dates,
    generate_weekly_dates,
)


# Monthly dates tests
def test_generate_monthly_dates_basic():
    start_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    dates = generate_monthly_dates(start_date, 3)
    expected = [
        datetime(2024, 1, 15, tzinfo=timezone.utc),
        datetime(2024, 2, 15, tzinfo=timezone.utc),
        datetime(2024, 3, 15, tzinfo=timezone.utc),
    ]
    assert dates == expected


def test_generate_monthly_dates_handles_end_of_month():
    start_date = datetime(2024, 1, 31, tzinfo=timezone.utc)
    dates = generate_monthly_dates(start_date, 3)
    expected = [
        datetime(2024, 1, 31, tzinfo=timezone.utc),
        datetime(2024, 2, 29, tzinfo=timezone.utc),  # 2024 is leap year, clamped to 29
        datetime(2024, 3, 31, tzinfo=timezone.utc),  # Anchored to original day 31
    ]
    assert dates == expected


def test_generate_monthly_dates_february_leap_year():
    start_date = datetime(2024, 1, 29, tzinfo=timezone.utc)
    dates = generate_monthly_dates(start_date, 3)
    expected = [
        datetime(2024, 1, 29, tzinfo=timezone.utc),
        datetime(2024, 2, 29, tzinfo=timezone.utc),  # 2024 is leap year
        datetime(2024, 3, 29, tzinfo=timezone.utc),
    ]
    assert dates == expected


def test_generate_monthly_dates_february_non_leap_year():
    start_date = datetime(2023, 1, 29, tzinfo=timezone.utc)
    dates = generate_monthly_dates(start_date, 3)
    expected = [
        datetime(2023, 1, 29, tzinfo=timezone.utc),
        datetime(2023, 2, 28, tzinfo=timezone.utc),  # 2023 is not leap year, clamped to 28
        datetime(2023, 3, 29, tzinfo=timezone.utc),  # Anchored to original day 29
    ]
    assert dates == expected


def test_generate_monthly_dates_year_rollover():
    start_date = datetime(2024, 11, 15, tzinfo=timezone.utc)
    dates = generate_monthly_dates(start_date, 3)
    expected = [
        datetime(2024, 11, 15, tzinfo=timezone.utc),
        datetime(2024, 12, 15, tzinfo=timezone.utc),
        datetime(2025, 1, 15, tzinfo=timezone.utc),
    ]
    assert dates == expected


def test_generate_monthly_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_monthly_dates(start_date, 0)


def test_generate_monthly_dates_negative_payments_raises_error():
    start_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_monthly_dates(start_date, -1)


def test_generate_monthly_dates_anchors_day_across_short_months():
    start_date = datetime(2024, 1, 31, tzinfo=timezone.utc)
    dates = generate_monthly_dates(start_date, 6)
    expected = [
        datetime(2024, 1, 31, tzinfo=timezone.utc),
        datetime(2024, 2, 29, tzinfo=timezone.utc),  # Leap year Feb, clamped to 29
        datetime(2024, 3, 31, tzinfo=timezone.utc),  # Back to 31
        datetime(2024, 4, 30, tzinfo=timezone.utc),  # April has 30 days, clamped
        datetime(2024, 5, 31, tzinfo=timezone.utc),  # Back to 31
        datetime(2024, 6, 30, tzinfo=timezone.utc),  # June has 30 days, clamped
    ]
    assert dates == expected


def test_generate_monthly_dates_anchors_day_30_across_february():
    start_date = datetime(2023, 11, 30, tzinfo=timezone.utc)
    dates = generate_monthly_dates(start_date, 5)
    expected = [
        datetime(2023, 11, 30, tzinfo=timezone.utc),
        datetime(2023, 12, 30, tzinfo=timezone.utc),
        datetime(2024, 1, 30, tzinfo=timezone.utc),
        datetime(2024, 2, 29, tzinfo=timezone.utc),  # Leap year Feb, clamped from 30
        datetime(2024, 3, 30, tzinfo=timezone.utc),  # Back to 30
    ]
    assert dates == expected


def test_generate_monthly_dates_single_payment():
    start_date = datetime(2024, 3, 31, tzinfo=timezone.utc)
    dates = generate_monthly_dates(start_date, 1)
    assert dates == [datetime(2024, 3, 31, tzinfo=timezone.utc)]


# Bi-weekly dates tests
def test_generate_biweekly_dates_basic():
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    dates = generate_biweekly_dates(start_date, 4)
    expected = [
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 15, tzinfo=timezone.utc),
        datetime(2024, 1, 29, tzinfo=timezone.utc),
        datetime(2024, 2, 12, tzinfo=timezone.utc),
    ]
    assert dates == expected


def test_generate_biweekly_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_biweekly_dates(start_date, 0)


# Weekly dates tests
def test_generate_weekly_dates_basic():
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    dates = generate_weekly_dates(start_date, 4)
    expected = [
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 8, tzinfo=timezone.utc),
        datetime(2024, 1, 15, tzinfo=timezone.utc),
        datetime(2024, 1, 22, tzinfo=timezone.utc),
    ]
    assert dates == expected


def test_generate_weekly_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_weekly_dates(start_date, 0)


# Quarterly dates tests
def test_generate_quarterly_dates_basic():
    start_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    dates = generate_quarterly_dates(start_date, 4)
    expected = [
        datetime(2024, 1, 15, tzinfo=timezone.utc),
        datetime(2024, 4, 15, tzinfo=timezone.utc),
        datetime(2024, 7, 15, tzinfo=timezone.utc),
        datetime(2024, 10, 15, tzinfo=timezone.utc),
    ]
    assert dates == expected


def test_generate_quarterly_dates_handles_month_lengths():
    start_date = datetime(2024, 1, 31, tzinfo=timezone.utc)
    dates = generate_quarterly_dates(start_date, 4)
    expected = [
        datetime(2024, 1, 31, tzinfo=timezone.utc),
        datetime(2024, 4, 30, tzinfo=timezone.utc),  # April has 30 days, clamped
        datetime(2024, 7, 31, tzinfo=timezone.utc),  # Anchored to original day 31
        datetime(2024, 10, 31, tzinfo=timezone.utc),  # Anchored to original day 31
    ]
    assert dates == expected


def test_generate_quarterly_dates_year_rollover():
    start_date = datetime(2024, 10, 15, tzinfo=timezone.utc)
    dates = generate_quarterly_dates(start_date, 3)
    expected = [
        datetime(2024, 10, 15, tzinfo=timezone.utc),
        datetime(2025, 1, 15, tzinfo=timezone.utc),
        datetime(2025, 4, 15, tzinfo=timezone.utc),
    ]
    assert dates == expected


def test_generate_quarterly_dates_anchors_day_across_short_months():
    start_date = datetime(2024, 1, 31, tzinfo=timezone.utc)
    dates = generate_quarterly_dates(start_date, 5)
    expected = [
        datetime(2024, 1, 31, tzinfo=timezone.utc),
        datetime(2024, 4, 30, tzinfo=timezone.utc),  # April has 30 days, clamped
        datetime(2024, 7, 31, tzinfo=timezone.utc),  # Back to 31
        datetime(2024, 10, 31, tzinfo=timezone.utc),  # Back to 31
        datetime(2025, 1, 31, tzinfo=timezone.utc),  # Back to 31
    ]
    assert dates == expected


def test_generate_quarterly_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_quarterly_dates(start_date, 0)


# Annual dates tests
def test_generate_annual_dates_basic():
    start_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    dates = generate_annual_dates(start_date, 3)
    expected = [
        datetime(2024, 1, 15, tzinfo=timezone.utc),
        datetime(2025, 1, 15, tzinfo=timezone.utc),
        datetime(2026, 1, 15, tzinfo=timezone.utc),
    ]
    assert dates == expected


def test_generate_annual_dates_leap_year_edge_case():
    start_date = datetime(2024, 2, 29, tzinfo=timezone.utc)  # Leap year
    dates = generate_annual_dates(start_date, 3)
    expected = [
        datetime(2024, 2, 29, tzinfo=timezone.utc),
        datetime(2025, 2, 28, tzinfo=timezone.utc),  # 2025 is not leap year, relativedelta handles this
        datetime(2026, 2, 28, tzinfo=timezone.utc),  # 2026 is not leap year
    ]
    assert dates == expected


def test_generate_annual_dates_anchors_day_across_leap_years():
    start_date = datetime(2024, 2, 29, tzinfo=timezone.utc)  # Leap year
    dates = generate_annual_dates(start_date, 5)
    expected = [
        datetime(2024, 2, 29, tzinfo=timezone.utc),
        datetime(2025, 2, 28, tzinfo=timezone.utc),  # Non-leap, clamped to 28
        datetime(2026, 2, 28, tzinfo=timezone.utc),  # Non-leap, clamped to 28
        datetime(2027, 2, 28, tzinfo=timezone.utc),  # Non-leap, clamped to 28
        datetime(2028, 2, 29, tzinfo=timezone.utc),  # Leap year again, back to 29
    ]
    assert dates == expected


def test_generate_annual_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_annual_dates(start_date, 0)


# Custom interval dates tests
def test_generate_custom_interval_dates_basic():
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    dates = generate_custom_interval_dates(start_date, 4, 10)
    expected = [
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 11, tzinfo=timezone.utc),
        datetime(2024, 1, 21, tzinfo=timezone.utc),
        datetime(2024, 1, 31, tzinfo=timezone.utc),
    ]
    assert dates == expected


def test_generate_custom_interval_dates_30_days():
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    dates = generate_custom_interval_dates(start_date, 3, 30)
    expected = [
        datetime(2024, 1, 1, tzinfo=timezone.utc),
        datetime(2024, 1, 31, tzinfo=timezone.utc),
        datetime(2024, 3, 1, tzinfo=timezone.utc),  # 2024 is leap year, Feb has 29 days
    ]
    assert dates == expected


def test_generate_custom_interval_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_custom_interval_dates(start_date, 0, 10)


def test_generate_custom_interval_dates_zero_interval_raises_error():
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Interval days must be positive"):
        generate_custom_interval_dates(start_date, 3, 0)


def test_generate_custom_interval_dates_negative_interval_raises_error():
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="Interval days must be positive"):
        generate_custom_interval_dates(start_date, 3, -1)


# Integration tests with realistic scenarios
def test_monthly_dates_12_month_loan():
    start_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    dates = generate_monthly_dates(start_date, 12)

    assert len(dates) == 12
    assert dates[0] == datetime(2024, 1, 15, tzinfo=timezone.utc)
    assert dates[11] == datetime(2024, 12, 15, tzinfo=timezone.utc)

    # Check all dates are on the 15th (or adjusted for month-end)
    for date in dates:
        assert date.day == 15


def test_biweekly_dates_26_payments_year():
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    dates = generate_biweekly_dates(start_date, 26)

    assert len(dates) == 26
    assert dates[0] == datetime(2024, 1, 1, tzinfo=timezone.utc)

    # Check 14-day intervals
    for i in range(1, len(dates)):
        diff_days = (dates[i] - dates[i - 1]).days
        assert diff_days == 14


def test_quarterly_dates_business_scenario():
    start_date = datetime(2024, 3, 31, tzinfo=timezone.utc)  # End of Q1
    dates = generate_quarterly_dates(start_date, 4)

    expected = [
        datetime(2024, 3, 31, tzinfo=timezone.utc),
        datetime(2024, 6, 30, tzinfo=timezone.utc),  # June has 30 days, clamped
        datetime(2024, 9, 30, tzinfo=timezone.utc),  # September has 30 days, clamped
        datetime(2024, 12, 31, tzinfo=timezone.utc),  # Anchored to original day 31
    ]
    assert dates == expected


def test_annual_dates_long_term_loan():
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    dates = generate_annual_dates(start_date, 30)  # 30-year loan

    assert len(dates) == 30
    assert dates[0] == datetime(2024, 1, 1, tzinfo=timezone.utc)
    assert dates[29] == datetime(2053, 1, 1, tzinfo=timezone.utc)

    # Check all dates are January 1st
    for date in dates:
        assert date.month == 1
        assert date.day == 1
