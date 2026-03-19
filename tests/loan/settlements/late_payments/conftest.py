"""Shared fixtures for late payment settlement tests."""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money


@pytest.fixture
def loan_with_fine():
    """3-installment loan with a 2% fine rate."""
    return Loan(
        Money("890.22"),
        InterestRate("15% annual"),
        [
            date(2025, 2, 1),
            date(2025, 3, 1),
            date(2025, 4, 1),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
    )
