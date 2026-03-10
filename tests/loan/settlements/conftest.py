"""Shared fixtures for settlement tests."""

from datetime import datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money


@pytest.fixture
def three_installment_loan():
    """3-installment loan: R$890.22 at 15% annual, monthly payments."""
    return Loan(
        Money("890.22"),
        InterestRate("15% annual"),
        [
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            datetime(2025, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
