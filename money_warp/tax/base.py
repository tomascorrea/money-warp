"""Base tax interface for loan tax calculations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List

from ..money import Money
from ..scheduler.schedule import PaymentSchedule


@dataclass
class TaxInstallmentDetail:
    """Tax breakdown for a single installment."""

    payment_number: int
    due_date: datetime
    principal_payment: Money
    tax_amount: Money


@dataclass
class TaxResult:
    """Result of a tax calculation across an entire schedule."""

    total: Money
    per_installment: List[TaxInstallmentDetail]


class BaseTax(ABC):
    """
    Abstract base class for all loan taxes.

    All taxes should inherit from this and implement the calculate method.
    The interface mirrors BaseScheduler: simple, one method, receives what it needs.
    """

    @abstractmethod
    def calculate(
        self,
        schedule: PaymentSchedule,
        disbursement_date: datetime,
    ) -> TaxResult:
        """
        Calculate tax based on the amortization schedule.

        Args:
            schedule: The loan's payment schedule with principal breakdown per installment.
            disbursement_date: When the loan was disbursed.

        Returns:
            TaxResult with total tax and per-installment breakdown.
        """
        ...
