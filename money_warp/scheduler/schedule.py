"""Payment schedule data structures."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, List

from ..money import Money


@dataclass
class PaymentScheduleEntry:
    """
    Represents a single payment in an amortization schedule.

    This is the standard structure that all schedulers should return.
    """

    payment_number: int
    due_date: datetime
    days_in_period: int
    beginning_balance: Money
    payment_amount: Money
    principal_payment: Money
    interest_payment: Money
    ending_balance: Money

    def __str__(self) -> str:
        """String representation of the payment entry."""
        return (
            f"Payment {self.payment_number}: {self.payment_amount} "
            f"(Principal: {self.principal_payment}, Interest: {self.interest_payment}) "
            f"on {self.due_date.date()}"
        )


@dataclass
class PaymentSchedule:
    """
    Complete payment schedule for a loan.

    Contains all payment entries and summary information.
    """

    entries: List[PaymentScheduleEntry]
    total_payments: Money = field(init=False)
    total_interest: Money = field(init=False)
    total_principal: Money = field(init=False)

    def __post_init__(self) -> None:
        """Calculate totals after initialization."""
        self.total_payments = Money.zero()
        self.total_interest = Money.zero()
        self.total_principal = Money.zero()

        for entry in self.entries:
            self.total_payments += entry.payment_amount
            self.total_interest += entry.interest_payment
            self.total_principal += entry.principal_payment

    def __len__(self) -> int:
        """Number of payments in the schedule."""
        return len(self.entries)

    def __getitem__(self, index: int) -> PaymentScheduleEntry:
        """Get payment entry by index."""
        return self.entries[index]

    def __iter__(self) -> Iterator[PaymentScheduleEntry]:
        """Iterate over payment entries."""
        return iter(self.entries)

    def __str__(self) -> str:
        """String representation of the schedule."""
        return (
            f"PaymentSchedule({len(self.entries)} payments, "
            f"Total: {self.total_payments}, Interest: {self.total_interest})"
        )
