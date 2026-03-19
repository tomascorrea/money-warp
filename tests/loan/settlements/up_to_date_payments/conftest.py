"""Shared fixtures for up-to-date payment settlement tests."""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money


@pytest.fixture
def no_fine_loan():
    """3-installment loan with zero fine rate for clean partial-payment tests."""
    return Loan(
        Money("890.22"),
        InterestRate("15% annual"),
        [
            date(2025, 2, 1),
            date(2025, 3, 1),
            date(2025, 4, 1),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("0% annual"),
    )
