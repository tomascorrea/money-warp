"""Settlement data structures for loan payment allocation."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, List

from ..money import Money
from .allocation import Allocation

if TYPE_CHECKING:
    from .installment import Installment


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
    allocations: List[Allocation]

    @property
    def total_paid(self) -> Money:
        """Sum of all payment components (fine + interest + mora + principal)."""
        return self.fine_paid + self.interest_paid + self.mora_paid + self.principal_paid


@dataclass(frozen=True)
class AnticipationResult:
    """Result of an anticipation calculation.

    Returned by :meth:`Loan.calculate_anticipation`. Contains the amount
    the borrower should pay today and the installments being removed.
    """

    amount: Money
    installments: List["Installment"]
