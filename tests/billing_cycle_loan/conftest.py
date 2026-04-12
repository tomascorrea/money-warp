"""Shared fixtures for billing-cycle loan tests."""

from datetime import date, datetime, timezone

import pytest

from money_warp import BillingCycleLoan, InterestRate, Money
from money_warp.billing_cycle import MonthlyBillingCycle
from money_warp.engines import MoraStrategy


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
