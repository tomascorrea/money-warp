"""Installment data structure for loan repayment plans."""

from dataclasses import dataclass
from datetime import datetime
from typing import List

from ..money import Money
from ..scheduler import PaymentScheduleEntry
from .settlement import SettlementAllocation


@dataclass(frozen=True)
class Installment:
    """A single installment in a loan repayment plan.

    Represents the borrower's obligation for one period: what is expected,
    what has actually been paid, and the detailed per-payment allocations.

    Installments are consequences of the loan -- they describe HOW the
    borrower repays, not what defines the loan itself. The Loan builds
    these on demand as a live snapshot reflecting the current time context.
    """

    number: int
    due_date: datetime
    days_in_period: int
    expected_payment: Money
    expected_principal: Money
    expected_interest: Money
    is_paid: bool
    principal_paid: Money
    interest_paid: Money
    mora_paid: Money
    fine_paid: Money
    allocations: List[SettlementAllocation]

    @classmethod
    def from_schedule_entry(
        cls,
        entry: PaymentScheduleEntry,
        is_paid: bool,
        allocations: List[SettlementAllocation],
    ) -> "Installment":
        """Build an Installment from a scheduler's PaymentScheduleEntry.

        Args:
            entry: The schedule entry from the scheduler.
            is_paid: Whether this installment has been fully paid.
            allocations: SettlementAllocations attributed to this installment.
        """
        principal_paid = Money(sum(a.principal_allocated.raw_amount for a in allocations))
        interest_paid = Money(sum(a.interest_allocated.raw_amount for a in allocations))
        mora_paid = Money(sum(a.mora_allocated.raw_amount for a in allocations))
        fine_paid = Money(sum(a.fine_allocated.raw_amount for a in allocations))

        return cls(
            number=entry.payment_number,
            due_date=entry.due_date,
            days_in_period=entry.days_in_period,
            expected_payment=entry.payment_amount,
            expected_principal=entry.principal_payment,
            expected_interest=entry.interest_payment,
            is_paid=is_paid,
            principal_paid=principal_paid,
            interest_paid=interest_paid,
            mora_paid=mora_paid,
            fine_paid=fine_paid,
            allocations=allocations,
        )
