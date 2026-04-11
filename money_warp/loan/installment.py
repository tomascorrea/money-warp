"""Installment data structure for loan repayment plans."""

from dataclasses import dataclass
from datetime import date
from typing import List

from ..money import Money
from ..scheduler import PaymentScheduleEntry
from .allocation import Allocation


@dataclass(frozen=True)
class Installment:
    """A single installment in a loan repayment plan.

    Represents the borrower's obligation for one period: what is expected,
    what has actually been paid, and the detailed per-payment allocations.

    Installments are derived views -- the Loan builds them on demand
    from the CashFlow and the schedule.
    """

    number: int
    due_date: date
    days_in_period: int
    expected_payment: Money
    expected_principal: Money
    expected_interest: Money
    expected_mora: Money
    expected_fine: Money
    principal_paid: Money
    interest_paid: Money
    mora_paid: Money
    fine_paid: Money
    payment_tolerance: Money
    allocations: List[Allocation]

    @property
    def balance(self) -> Money:
        """The amount still owed to fully settle this installment."""
        total_expected = self.expected_principal + self.expected_interest + self.expected_mora + self.expected_fine
        total_paid = self.principal_paid + self.interest_paid + self.mora_paid + self.fine_paid
        remaining = total_expected - total_paid
        return remaining if remaining.is_positive() else Money.zero()

    @property
    def is_fully_paid(self) -> bool:
        """Whether this installment has been fully settled.

        Tolerance accumulates with the installment number to account for
        per-installment rounding errors from external origination systems.
        """
        return self.balance <= self.payment_tolerance * self.number

    @classmethod
    def from_schedule_entry(
        cls,
        entry: PaymentScheduleEntry,
        allocations: List[Allocation],
        expected_mora: Money,
        expected_fine: Money,
        payment_tolerance: Money,
    ) -> "Installment":
        """Build an Installment from a scheduler's PaymentScheduleEntry."""
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
            expected_mora=expected_mora,
            expected_fine=expected_fine,
            principal_paid=principal_paid,
            interest_paid=interest_paid,
            mora_paid=mora_paid,
            fine_paid=fine_paid,
            allocations=allocations,
            payment_tolerance=payment_tolerance,
        )
