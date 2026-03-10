"""Shared fixtures for up-to-date payment settlement tests."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money


@pytest.fixture
def no_fine_loan():
    """3-installment loan with zero fine rate for clean partial-payment tests."""
    return Loan(
        Money("890.22"),
        InterestRate("15% annual"),
        [
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            datetime(2025, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0"),
    )
