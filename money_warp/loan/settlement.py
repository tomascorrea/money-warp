"""Settlement data structures for loan payment allocation."""

from dataclasses import dataclass
from datetime import datetime
from typing import List

from ..money import Money


@dataclass(frozen=True)
class SettlementAllocation:
    """Breakdown of a payment's allocation to a single installment.

    Each allocation shows how much principal, interest, mora, and fine
    from a payment were attributed to a specific installment.
    """

    installment_number: int
    principal_allocated: Money
    interest_allocated: Money
    mora_allocated: Money
    fine_allocated: Money
    is_fully_covered: bool


@dataclass(frozen=True)
class Settlement:
    """Result of applying a payment to a loan.

    Captures the full allocation of a single payment across fines,
    interest, mora interest, and principal, along with per-installment
    detail showing which installments were covered.
    """

    payment_amount: Money
    payment_date: datetime
    fine_paid: Money
    interest_paid: Money
    mora_paid: Money
    principal_paid: Money
    remaining_balance: Money
    allocations: List[SettlementAllocation]
