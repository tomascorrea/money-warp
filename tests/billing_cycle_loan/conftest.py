"""Shared fixtures for billing-cycle loan tests (BCL-specific only; common fixtures in tests/conftest.py)."""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from money_warp import BillingCycleLoan, InterestRate, Money, PriceScheduler
from money_warp.billing_cycle import MonthlyBillingCycle
from money_warp.engines import MoraStrategy

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def billing_cycle():
    """Monthly billing cycle: closes on the 28th, due 15 days later."""
    return MonthlyBillingCycle(closing_day=28, payment_due_days=15)


@pytest.fixture
def simple_loan(billing_cycle):
    """3-installment billing-cycle loan, no mora resolver.

    Principal: 3000, Rate: 12% annual, Start: 2025-01-01.
    Closing dates: Jan 28, Feb 28, Mar 28.
    Due dates: Feb 12, Mar 15, Apr 12.
    Disbursement: 2025-01-01.
    """
    return BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=billing_cycle,
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def variable_mora_loan(billing_cycle):
    """3-installment loan with a variable mora resolver.

    The resolver doubles the base mora rate for any cycle closing
    after Feb 28, simulating an external index jump.
    """

    def resolver(ref_date: date, base: InterestRate) -> InterestRate:
        if ref_date > date(2025, 2, 28):
            return InterestRate(f"{base.as_decimal() * 2 * 100}% a")
        return base

    return BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=billing_cycle,
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        mora_interest_rate=InterestRate("12% a"),
        mora_rate_resolver=resolver,
        mora_strategy=MoraStrategy.COMPOUND,
    )


@pytest.fixture
def make_late_waiver_loan():
    """Factory for the loan from the late-payment-shortens-next-period bug report.

    4 monthly installments at 79.380% a.a., principal R$667.45, due on the 25th
    starting Dec 2025.  Returns a fresh loan each call so a single test can
    build the same loan twice and compare scenarios.
    """

    def _build() -> BillingCycleLoan:
        return BillingCycleLoan(
            principal=Money("667.45"),
            interest_rate=InterestRate("79.380% a.a."),
            billing_cycle=MonthlyBillingCycle(
                due_dates=[
                    date(2025, 12, 25),
                    date(2026, 1, 25),
                    date(2026, 2, 25),
                    date(2026, 3, 25),
                ],
            ),
            start_date=datetime(2025, 11, 24, tzinfo=SAO_PAULO),
            num_installments=4,
            disbursement_date=datetime(2025, 11, 24, tzinfo=SAO_PAULO),
            scheduler=PriceScheduler,
            fine_rate=InterestRate("2% a.m."),
        )

    return _build
