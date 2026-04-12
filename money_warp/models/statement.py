"""Billing-cycle loan statement — one per billing period."""

from dataclasses import dataclass
from datetime import datetime

from ..interest_rate import InterestRate
from ..money import Money


@dataclass(frozen=True)
class BillingCycleLoanStatement:
    """Snapshot of a single billing period for a billing-cycle loan.

    Combines the amortization schedule view (expected principal /
    interest) with the actual payment activity and any mora / fine
    charges for the period.
    """

    period_number: int
    closing_date: datetime
    due_date: datetime
    opening_balance: Money
    expected_payment: Money
    expected_principal: Money
    expected_interest: Money
    mora_rate: InterestRate
    mora_charged: Money
    fine_charged: Money
    payments_received: Money
    closing_balance: Money
