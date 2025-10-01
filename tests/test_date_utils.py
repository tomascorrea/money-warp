"""Tests for date generation utilities - following project patterns."""

from datetime import datetime

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
    start_date = datetime(2024, 1, 15)
    dates = generate_monthly_dates(start_date, 3)
    expected = [
        datetime(2024, 1, 15),
        datetime(2024, 2, 15),
        datetime(2024, 3, 15),
    ]
    assert dates == expected


def test_generate_monthly_dates_handles_end_of_month():
    # Test that relativedelta handles end-of-month correctly
    start_date = datetime(2024, 1, 31)
    dates = generate_monthly_dates(start_date, 3)
    expected = [
        datetime(2024, 1, 31),
        datetime(2024, 2, 29),  # 2024 is leap year, Feb has 29 days
        datetime(2024, 3, 29),  # Maintains the adjusted day from February
    ]
    assert dates == expected


def test_generate_monthly_dates_february_leap_year():
    start_date = datetime(2024, 1, 29)
    dates = generate_monthly_dates(start_date, 3)
    expected = [
        datetime(2024, 1, 29),
        datetime(2024, 2, 29),  # 2024 is leap year
        datetime(2024, 3, 29),
    ]
    assert dates == expected


def test_generate_monthly_dates_february_non_leap_year():
    start_date = datetime(2023, 1, 29)
    dates = generate_monthly_dates(start_date, 3)
    expected = [
        datetime(2023, 1, 29),
        datetime(2023, 2, 28),  # 2023 is not leap year, Feb has 28 days
        datetime(2023, 3, 28),  # Maintains the adjusted day from February
    ]
    assert dates == expected


def test_generate_monthly_dates_year_rollover():
    start_date = datetime(2024, 11, 15)
    dates = generate_monthly_dates(start_date, 3)
    expected = [
        datetime(2024, 11, 15),
        datetime(2024, 12, 15),
        datetime(2025, 1, 15),
    ]
    assert dates == expected


def test_generate_monthly_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 15)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_monthly_dates(start_date, 0)


def test_generate_monthly_dates_negative_payments_raises_error():
    start_date = datetime(2024, 1, 15)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_monthly_dates(start_date, -1)


# Bi-weekly dates tests
def test_generate_biweekly_dates_basic():
    start_date = datetime(2024, 1, 1)
    dates = generate_biweekly_dates(start_date, 4)
    expected = [
        datetime(2024, 1, 1),
        datetime(2024, 1, 15),
        datetime(2024, 1, 29),
        datetime(2024, 2, 12),
    ]
    assert dates == expected


def test_generate_biweekly_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 1)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_biweekly_dates(start_date, 0)


# Weekly dates tests
def test_generate_weekly_dates_basic():
    start_date = datetime(2024, 1, 1)
    dates = generate_weekly_dates(start_date, 4)
    expected = [
        datetime(2024, 1, 1),
        datetime(2024, 1, 8),
        datetime(2024, 1, 15),
        datetime(2024, 1, 22),
    ]
    assert dates == expected


def test_generate_weekly_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 1)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_weekly_dates(start_date, 0)


# Quarterly dates tests
def test_generate_quarterly_dates_basic():
    start_date = datetime(2024, 1, 15)
    dates = generate_quarterly_dates(start_date, 4)
    expected = [
        datetime(2024, 1, 15),
        datetime(2024, 4, 15),
        datetime(2024, 7, 15),
        datetime(2024, 10, 15),
    ]
    assert dates == expected


def test_generate_quarterly_dates_handles_month_lengths():
    # Test that relativedelta handles different month lengths correctly
    start_date = datetime(2024, 1, 31)
    dates = generate_quarterly_dates(start_date, 4)
    expected = [
        datetime(2024, 1, 31),
        datetime(2024, 4, 30),  # April has 30 days, relativedelta handles this
        datetime(2024, 7, 30),  # Stays consistent with April's adjustment
        datetime(2024, 10, 30),
    ]
    assert dates == expected


def test_generate_quarterly_dates_year_rollover():
    start_date = datetime(2024, 10, 15)
    dates = generate_quarterly_dates(start_date, 3)
    expected = [
        datetime(2024, 10, 15),
        datetime(2025, 1, 15),
        datetime(2025, 4, 15),
    ]
    assert dates == expected


def test_generate_quarterly_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 15)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_quarterly_dates(start_date, 0)


# Annual dates tests
def test_generate_annual_dates_basic():
    start_date = datetime(2024, 1, 15)
    dates = generate_annual_dates(start_date, 3)
    expected = [
        datetime(2024, 1, 15),
        datetime(2025, 1, 15),
        datetime(2026, 1, 15),
    ]
    assert dates == expected


def test_generate_annual_dates_leap_year_edge_case():
    start_date = datetime(2024, 2, 29)  # Leap year
    dates = generate_annual_dates(start_date, 3)
    expected = [
        datetime(2024, 2, 29),
        datetime(2025, 2, 28),  # 2025 is not leap year, relativedelta handles this
        datetime(2026, 2, 28),  # 2026 is not leap year
    ]
    assert dates == expected


def test_generate_annual_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 15)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_annual_dates(start_date, 0)


# Custom interval dates tests
def test_generate_custom_interval_dates_basic():
    start_date = datetime(2024, 1, 1)
    dates = generate_custom_interval_dates(start_date, 4, 10)
    expected = [
        datetime(2024, 1, 1),
        datetime(2024, 1, 11),
        datetime(2024, 1, 21),
        datetime(2024, 1, 31),
    ]
    assert dates == expected


def test_generate_custom_interval_dates_30_days():
    start_date = datetime(2024, 1, 1)
    dates = generate_custom_interval_dates(start_date, 3, 30)
    expected = [
        datetime(2024, 1, 1),
        datetime(2024, 1, 31),
        datetime(2024, 3, 1),  # 2024 is leap year, Feb has 29 days
    ]
    assert dates == expected


def test_generate_custom_interval_dates_zero_payments_raises_error():
    start_date = datetime(2024, 1, 1)
    with pytest.raises(ValueError, match="Number of payments must be positive"):
        generate_custom_interval_dates(start_date, 0, 10)


def test_generate_custom_interval_dates_zero_interval_raises_error():
    start_date = datetime(2024, 1, 1)
    with pytest.raises(ValueError, match="Interval days must be positive"):
        generate_custom_interval_dates(start_date, 3, 0)


def test_generate_custom_interval_dates_negative_interval_raises_error():
    start_date = datetime(2024, 1, 1)
    with pytest.raises(ValueError, match="Interval days must be positive"):
        generate_custom_interval_dates(start_date, 3, -1)


# Integration tests with realistic scenarios
def test_monthly_dates_12_month_loan():
    start_date = datetime(2024, 1, 15)
    dates = generate_monthly_dates(start_date, 12)

    assert len(dates) == 12
    assert dates[0] == datetime(2024, 1, 15)
    assert dates[11] == datetime(2024, 12, 15)

    # Check all dates are on the 15th (or adjusted for month-end)
    for date in dates:
        assert date.day == 15


def test_biweekly_dates_26_payments_year():
    start_date = datetime(2024, 1, 1)
    dates = generate_biweekly_dates(start_date, 26)

    assert len(dates) == 26
    assert dates[0] == datetime(2024, 1, 1)

    # Check 14-day intervals
    for i in range(1, len(dates)):
        diff_days = (dates[i] - dates[i - 1]).days
        assert diff_days == 14


def test_quarterly_dates_business_scenario():
    start_date = datetime(2024, 3, 31)  # End of Q1
    dates = generate_quarterly_dates(start_date, 4)

    expected = [
        datetime(2024, 3, 31),
        datetime(2024, 6, 30),  # June has 30 days, so adjusted from 31
        datetime(2024, 9, 30),  # Maintains the adjusted day from June
        datetime(2024, 12, 30),  # Maintains the adjusted day
    ]
    assert dates == expected


def test_annual_dates_long_term_loan():
    start_date = datetime(2024, 1, 1)
    dates = generate_annual_dates(start_date, 30)  # 30-year loan

    assert len(dates) == 30
    assert dates[0] == datetime(2024, 1, 1)
    assert dates[29] == datetime(2053, 1, 1)

    # Check all dates are January 1st
    for date in dates:
        assert date.month == 1
        assert date.day == 1
