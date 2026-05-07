"""Shared fixtures available to all test directories."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from money_warp import (
    BillingCycleLoan,
    BrazilianWorkingDayCalendar,
    InterestRate,
    Loan,
    Money,
    MonthlyBillingCycle,
    PriceScheduler,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


# ------------------------------------------------------------------
# Loan fixtures
# ------------------------------------------------------------------


@pytest.fixture
def single_installment_loan():
    """Single-installment Loan: 10k principal, 10% a.m., due Dec 20."""
    return Loan(
        principal=Money("10000"),
        interest_rate=InterestRate("10% a.m."),
        due_dates=[date(2025, 12, 20)],
        disbursement_date=datetime(2025, 11, 20, tzinfo=timezone.utc),
        scheduler=PriceScheduler,
    )


@pytest.fixture
def multi_installment_loan():
    """3-installment Loan: 10k principal, 5% a.m., due Dec/Jan/Feb 20."""
    return Loan(
        principal=Money("10000"),
        interest_rate=InterestRate("5% a.m."),
        due_dates=[date(2025, 12, 20), date(2026, 1, 20), date(2026, 2, 20)],
        disbursement_date=datetime(2025, 11, 20, tzinfo=timezone.utc),
        scheduler=PriceScheduler,
    )


# ------------------------------------------------------------------
# BillingCycleLoan fixtures
# ------------------------------------------------------------------


@pytest.fixture
def single_bcl():
    """Single-installment BCL: 946.62 principal, 4.99% a.m., due Nov 20."""
    return BillingCycleLoan(
        principal=Money("946.62"),
        interest_rate=InterestRate("4.99% a.m."),
        billing_cycle=MonthlyBillingCycle(due_dates=[date(2025, 11, 20)]),
        start_date=datetime(2025, 10, 21, tzinfo=SAO_PAULO),
        num_installments=1,
        disbursement_date=datetime(2025, 10, 21, tzinfo=SAO_PAULO),
        scheduler=PriceScheduler,
        mora_interest_rate=InterestRate("4.99% a.m."),
        fine_rate=InterestRate("2% a.m."),
        tz=SAO_PAULO,
        working_day_calendar=BrazilianWorkingDayCalendar(),
    )


@pytest.fixture
def multi_bcl():
    """3-installment BCL: 10k principal, 5% a.m., due Dec/Jan/Feb 20."""
    return BillingCycleLoan(
        principal=Money("10000"),
        interest_rate=InterestRate("5% a.m."),
        billing_cycle=MonthlyBillingCycle(
            due_dates=[date(2025, 12, 20), date(2026, 1, 20), date(2026, 2, 20)]
        ),
        start_date=datetime(2025, 11, 20, tzinfo=SAO_PAULO),
        num_installments=3,
        disbursement_date=datetime(2025, 11, 20, tzinfo=SAO_PAULO),
        scheduler=PriceScheduler,
        tz=SAO_PAULO,
    )
