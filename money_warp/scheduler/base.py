"""Base scheduler interface for loan payment calculations."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List

from ..interest_rate import InterestRate
from ..money import Money
from .schedule import PaymentSchedule


class BaseScheduler(ABC):
    """
    Abstract base class for all payment schedulers.

    All schedulers should inherit from this and implement the generate_schedule class method.
    """

    @classmethod
    @abstractmethod
    def generate_schedule(
        cls, principal: Money, interest_rate: InterestRate, due_dates: List[datetime], disbursement_date: datetime
    ) -> PaymentSchedule:
        """
        Generate the payment schedule.

        This is the only public method that schedulers need to implement.

        Args:
            principal: The loan amount
            interest_rate: The annual interest rate
            due_dates: List of payment due dates
            disbursement_date: When the loan was disbursed

        Returns:
            PaymentSchedule with all payment details
        """
        pass
