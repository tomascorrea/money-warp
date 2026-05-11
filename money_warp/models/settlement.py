"""Settlement data structures for loan payment allocation."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, List

from ..types.money import Money
from .allocation import Allocation

if TYPE_CHECKING:
    from .installment import Installment


def _zero() -> Money:
    return Money.zero()


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
    fines_waived: Money = field(default_factory=_zero)
    mora_waived: Money = field(default_factory=_zero)
    overdue_interest_waived: Money = field(default_factory=_zero)
    discount_applied: Money = field(default_factory=_zero)

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
