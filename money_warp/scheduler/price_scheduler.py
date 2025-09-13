"""Price scheduler implementing Progressive Price Schedule (French amortization system)."""

from datetime import datetime
from decimal import Decimal
from typing import List

from ..interest_rate import InterestRate
from ..money import Money
from .base import BaseScheduler
from .schedule import PaymentSchedule, PaymentScheduleEntry


class PriceScheduler(BaseScheduler):
    """
    Price scheduler implementing Progressive Price Schedule (French amortization system).

    This scheduler calculates a fixed payment amount (PMT) and then allocates each payment
    between interest and principal. Interest is calculated on the outstanding balance,
    and the remainder goes to principal reduction.

    Based on the reference implementation from cartaorobbin/loan-calculator.
    """

    def __init__(
        self,
        principal: Decimal = None,
        daily_interest_rate: Decimal = None,
        return_days: List[int] = None,
        disbursement_date: datetime = None,
    ):
        """Initialize the scheduler with loan parameters."""
        self.principal = principal
        self.daily_interest_rate = daily_interest_rate
        self.return_days = return_days
        self.disbursement_date = disbursement_date

    @classmethod
    def generate_schedule(
        cls, principal: Money, interest_rate: InterestRate, due_dates: List[datetime], disbursement_date: datetime
    ) -> PaymentSchedule:
        """
        Generate Progressive Price Schedule with fixed payment amounts.

        Args:
            principal: The loan amount
            interest_rate: The annual interest rate
            due_dates: List of payment due dates
            disbursement_date: When the loan was disbursed

        Returns:
            PaymentSchedule with fixed payment amounts and interest/principal allocation
        """
        if not due_dates:
            raise ValueError("At least one due date is required")

        # Calculate return days (days from disbursement to each payment)
        return_days = [(due_date - disbursement_date).days for due_date in due_dates]

        # Calculate PMT using the reference formula
        daily_rate = interest_rate.to_daily().as_decimal

        # Create an instance with the loan parameters
        scheduler = cls(principal.raw_amount, daily_rate, return_days, disbursement_date)
        pmt = scheduler.calculate_constant_return_pmt()

        # Generate schedule entries
        entries = []
        remaining_balance = principal.raw_amount

        for i, due_date in enumerate(due_dates):
            # Calculate days since last payment (or disbursement)
            prev_date = disbursement_date if i == 0 else due_dates[i - 1]
            days = (due_date - prev_date).days

            # Store beginning balance
            beginning_balance = remaining_balance

            # Calculate interest for this period using compound daily interest
            # Interest = balance * ((1 + daily_rate)^days - 1)
            interest_amount = remaining_balance * ((Decimal("1") + daily_rate) ** Decimal(str(days)) - Decimal("1"))

            # Principal payment is PMT minus interest
            principal_payment = pmt - interest_amount

            # Update remaining balance
            remaining_balance -= principal_payment

            # Create schedule entry
            entry = PaymentScheduleEntry(
                payment_number=i + 1,
                due_date=due_date,
                days_in_period=days,
                beginning_balance=Money(beginning_balance),
                payment_amount=Money(pmt),
                principal_payment=Money(principal_payment),
                interest_payment=Money(interest_amount),
                ending_balance=Money(max(Decimal("0"), remaining_balance)),
            )
            entries.append(entry)

        return PaymentSchedule(entries=entries)

    def calculate_constant_return_pmt(self) -> Decimal:
        """
        Calculate PMT using the reference formula from loan-calculator.

        PMT = principal / sum(1 / (1 + daily_rate)^n for n in return_days)

        Returns:
            The fixed payment amount (PMT)
        """
        # PMT formula from reference: p / sum(1.0 / (1 + d) ** n for n in return_days)
        denominator = sum(
            Decimal("1") / (Decimal("1") + self.daily_interest_rate) ** Decimal(str(n)) for n in self.return_days
        )

        if denominator.is_zero():
            raise ValueError("Cannot calculate PMT: denominator is zero")

        return self.principal / denominator
