"""Installment data structure for loan repayment plans."""

from dataclasses import dataclass
from datetime import date
from typing import List, Tuple

from ..money import Money
from ..scheduler import PaymentScheduleEntry
from .settlement import SettlementAllocation

_COVERAGE_TOLERANCE = Money("0.01")


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
    allocations: List[SettlementAllocation]

    @property
    def balance(self) -> Money:
        """The amount still owed to fully settle this installment."""
        total_expected = self.expected_principal + self.expected_interest + self.expected_mora + self.expected_fine
        total_paid = self.principal_paid + self.interest_paid + self.mora_paid + self.fine_paid
        remaining = total_expected - total_paid
        return remaining if remaining.is_positive() else Money.zero()

    @property
    def is_fully_paid(self) -> bool:
        """Whether this installment has been fully settled (within rounding tolerance)."""
        return self.balance <= _COVERAGE_TOLERANCE

    def allocate_from_payment(
        self,
        remaining: Money,
        fine_remaining: Money,
        mora_remaining: Money,
        interest_remaining: Money,
    ) -> Tuple[SettlementAllocation, Money, Money, Money, Money]:
        """Allocate from a single payment amount in priority order.

        Processes fine -> mora -> interest -> principal sequentially,
        each capped by both the installment's remaining obligation and
        the corresponding running cap.

        The running caps prevent over-allocation: during live allocation
        they reflect the loan-level accrual (e.g. the interest discount
        for early payments); during reconstruction they match the
        recorded CashFlowItem totals.

        Args:
            remaining: Unallocated portion of the payment.
            fine_remaining: Remaining fine cap across all installments.
            mora_remaining: Remaining mora cap across all installments.
            interest_remaining: Remaining interest cap across all installments.

        Returns:
            ``(SettlementAllocation, updated_remaining,
            updated_fine_remaining, updated_mora_remaining,
            updated_interest_remaining)``.
        """
        fine_owed = self.expected_fine - self.fine_paid
        fine_alloc = Money(min(fine_owed.raw_amount, remaining.raw_amount, fine_remaining.raw_amount))
        remaining = remaining - fine_alloc
        fine_remaining = fine_remaining - fine_alloc

        mora_owed = self.expected_mora - self.mora_paid
        mora_alloc = Money(min(mora_owed.raw_amount, remaining.raw_amount, mora_remaining.raw_amount))
        remaining = remaining - mora_alloc
        mora_remaining = mora_remaining - mora_alloc

        interest_owed = self.expected_interest - self.interest_paid
        interest_alloc = Money(min(interest_owed.raw_amount, remaining.raw_amount, interest_remaining.raw_amount))
        remaining = remaining - interest_alloc
        interest_remaining = interest_remaining - interest_alloc

        principal_owed = self.expected_principal - self.principal_paid
        reserved = interest_remaining + mora_remaining
        available_for_principal = remaining - reserved if remaining.raw_amount > reserved.raw_amount else Money.zero()
        principal_alloc = Money(min(principal_owed.raw_amount, available_for_principal.raw_amount))
        remaining = remaining - principal_alloc

        total = fine_alloc + mora_alloc + interest_alloc + principal_alloc
        is_covered = total >= (self.balance - _COVERAGE_TOLERANCE)

        allocation = SettlementAllocation(
            installment_number=self.number,
            principal_allocated=principal_alloc,
            interest_allocated=interest_alloc,
            mora_allocated=mora_alloc,
            fine_allocated=fine_alloc,
            is_fully_covered=is_covered,
        )
        return allocation, remaining, fine_remaining, mora_remaining, interest_remaining

    @classmethod
    def from_schedule_entry(
        cls,
        entry: PaymentScheduleEntry,
        allocations: List[SettlementAllocation],
        expected_mora: Money,
        expected_fine: Money,
    ) -> "Installment":
        """Build an Installment from a scheduler's PaymentScheduleEntry.

        Args:
            entry: The schedule entry from the scheduler.
            allocations: SettlementAllocations attributed to this installment.
            expected_mora: Mora interest owed for this installment.
            expected_fine: Fine amount owed for this installment.
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
            expected_mora=expected_mora,
            expected_fine=expected_fine,
            principal_paid=principal_paid,
            interest_paid=interest_paid,
            mora_paid=mora_paid,
            fine_paid=fine_paid,
            allocations=allocations,
        )
