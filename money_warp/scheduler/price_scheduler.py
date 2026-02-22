"""Price scheduler implementing Progressive Price Schedule (French amortization system)."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

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
        principal: Optional[Decimal] = None,
        daily_interest_rate: Optional[Decimal] = None,
        return_days: Optional[List[int]] = None,
        disbursement_date: Optional[datetime] = None,
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
        pmt = Money(scheduler.calculate_constant_return_pmt()).real_amount

        # Generate schedule entries with step-level rounding.
        # Each intermediate value (interest, principal, balance) is rounded
        # to 2 decimal places before feeding into the next period.
        # The last installment is calculated by difference to guarantee
        # a zero final balance.
        entries = []
        remaining_balance = principal.real_amount

        for i, due_date in enumerate(due_dates):
            prev_date = disbursement_date if i == 0 else due_dates[i - 1]
            days = (due_date - prev_date).days

            beginning_balance = remaining_balance

            interest_amount = Money(
                remaining_balance * ((Decimal("1") + daily_rate) ** Decimal(str(days)) - Decimal("1"))
            ).real_amount

            is_last = i == len(due_dates) - 1
            if is_last:
                principal_payment = remaining_balance
                total_payment = principal_payment + interest_amount
            else:
                total_payment = pmt
                principal_payment = pmt - interest_amount

            remaining_balance = beginning_balance - principal_payment

            entry = PaymentScheduleEntry(
                payment_number=i + 1,
                due_date=due_date,
                days_in_period=days,
                beginning_balance=Money(beginning_balance),
                payment_amount=Money(total_payment),
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
        if self.principal is None:
            raise ValueError("Principal is required for PMT calculation")
        if self.daily_interest_rate is None:
            raise ValueError("Daily interest rate is required for PMT calculation")
        if self.return_days is None:
            raise ValueError("Return days are required for PMT calculation")

        # PMT formula from reference: p / sum(1.0 / (1 + d) ** n for n in return_days)
        denominator = sum(
            (Decimal("1") / (Decimal("1") + self.daily_interest_rate) ** Decimal(str(n)) for n in self.return_days),
            Decimal("0"),
        )

        if denominator.is_zero():
            raise ValueError("Cannot calculate PMT: denominator is zero")

        return self.principal / denominator
