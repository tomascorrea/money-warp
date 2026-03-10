"""Shared fixtures for late payment settlement tests."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money


@pytest.fixture
def loan_with_fine():
    """3-installment loan with a 2% fine rate."""
    return Loan(
        Money("890.22"),
        InterestRate("15% annual"),
        [
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            datetime(2025, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
    )
