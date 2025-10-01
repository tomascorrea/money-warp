"""Date generation utilities for creating payment schedules."""

from datetime import datetime, timedelta
from typing import List

from dateutil.relativedelta import relativedelta


def generate_monthly_dates(start_date: datetime, num_payments: int) -> List[datetime]:
    """
    Generate a list of monthly payment due dates.

    Args:
        start_date: The starting date (first payment date)
        num_payments: Number of monthly payments to generate

    Returns:
        List of datetime objects representing monthly due dates

    Examples:
        >>> from datetime import datetime
        >>> dates = generate_monthly_dates(datetime(2024, 1, 15), 3)
        >>> # Returns [2024-01-15, 2024-02-15, 2024-03-15]
    """
    if num_payments <= 0:
        raise ValueError("Number of payments must be positive")

    dates = []
    current_date = start_date

    for _ in range(num_payments):
        dates.append(current_date)
        current_date += relativedelta(months=1)

    return dates


def generate_biweekly_dates(start_date: datetime, num_payments: int) -> List[datetime]:
    """
    Generate a list of bi-weekly (every 14 days) payment due dates.

    Args:
        start_date: The starting date (first payment date)
        num_payments: Number of bi-weekly payments to generate

    Returns:
        List of datetime objects representing bi-weekly due dates

    Examples:
        >>> from datetime import datetime
        >>> dates = generate_biweekly_dates(datetime(2024, 1, 1), 4)
        >>> # Returns [2024-01-01, 2024-01-15, 2024-01-29, 2024-02-12]
    """
    if num_payments <= 0:
        raise ValueError("Number of payments must be positive")

    dates = []
    current_date = start_date

    for _ in range(num_payments):
        dates.append(current_date)
        current_date += timedelta(days=14)

    return dates


def generate_weekly_dates(start_date: datetime, num_payments: int) -> List[datetime]:
    """
    Generate a list of weekly payment due dates.

    Args:
        start_date: The starting date (first payment date)
        num_payments: Number of weekly payments to generate

    Returns:
        List of datetime objects representing weekly due dates

    Examples:
        >>> from datetime import datetime
        >>> dates = generate_weekly_dates(datetime(2024, 1, 1), 4)
        >>> # Returns [2024-01-01, 2024-01-08, 2024-01-15, 2024-01-22]
    """
    if num_payments <= 0:
        raise ValueError("Number of payments must be positive")

    dates = []
    current_date = start_date

    for _ in range(num_payments):
        dates.append(current_date)
        current_date += timedelta(days=7)

    return dates


def generate_quarterly_dates(start_date: datetime, num_payments: int) -> List[datetime]:
    """
    Generate a list of quarterly payment due dates.

    Args:
        start_date: The starting date (first payment date)
        num_payments: Number of quarterly payments to generate

    Returns:
        List of datetime objects representing quarterly due dates

    Examples:
        >>> from datetime import datetime
        >>> dates = generate_quarterly_dates(datetime(2024, 1, 15), 4)
        >>> # Returns [2024-01-15, 2024-04-15, 2024-07-15, 2024-10-15]
    """
    if num_payments <= 0:
        raise ValueError("Number of payments must be positive")

    dates = []
    current_date = start_date

    for _ in range(num_payments):
        dates.append(current_date)
        current_date += relativedelta(months=3)

    return dates


def generate_annual_dates(start_date: datetime, num_payments: int) -> List[datetime]:
    """
    Generate a list of annual payment due dates.

    Args:
        start_date: The starting date (first payment date)
        num_payments: Number of annual payments to generate

    Returns:
        List of datetime objects representing annual due dates

    Examples:
        >>> from datetime import datetime
        >>> dates = generate_annual_dates(datetime(2024, 1, 15), 3)
        >>> # Returns [2024-01-15, 2025-01-15, 2026-01-15]
    """
    if num_payments <= 0:
        raise ValueError("Number of payments must be positive")

    dates = []
    current_date = start_date

    for _ in range(num_payments):
        dates.append(current_date)
        current_date += relativedelta(years=1)

    return dates


def generate_custom_interval_dates(start_date: datetime, num_payments: int, interval_days: int) -> List[datetime]:
    """
    Generate a list of payment due dates with custom day intervals.

    Args:
        start_date: The starting date (first payment date)
        num_payments: Number of payments to generate
        interval_days: Number of days between payments

    Returns:
        List of datetime objects representing due dates

    Examples:
        >>> from datetime import datetime
        >>> dates = generate_custom_interval_dates(datetime(2024, 1, 1), 4, 10)
        >>> # Returns payments every 10 days: [2024-01-01, 2024-01-11, 2024-01-21, 2024-01-31]
    """
    if num_payments <= 0:
        raise ValueError("Number of payments must be positive")

    if interval_days <= 0:
        raise ValueError("Interval days must be positive")

    dates = []
    current_date = start_date

    for _ in range(num_payments):
        dates.append(current_date)
        current_date += timedelta(days=interval_days)

    return dates
