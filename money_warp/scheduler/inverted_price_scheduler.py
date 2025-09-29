"""Inverted Price scheduler implementing Constant Amortization System (SAC)."""

from datetime import datetime
from decimal import Decimal
from typing import List

from ..interest_rate import InterestRate
from ..money import Money
from .base import BaseScheduler
from .schedule import PaymentSchedule, PaymentScheduleEntry


class InvertedPriceScheduler(BaseScheduler):
    """
    Inverted Price scheduler implementing Constant Amortization System (SAC).

    This scheduler calculates a fixed principal payment amount for each period
    and adds variable interest calculated on the outstanding balance. This results
    in decreasing total payments over time.

    Key characteristics:
    - Fixed principal payment each period
    - Variable interest payment (decreases over time)
    - Variable total payment (decreases over time)
    - Faster debt reduction compared to Price scheduler
    """

    @classmethod
    def generate_schedule(
        cls, principal: Money, interest_rate: InterestRate, due_dates: List[datetime], disbursement_date: datetime
    ) -> PaymentSchedule:
        """
        Generate Constant Amortization Schedule with fixed principal payments.

        Args:
            principal: The loan amount
            interest_rate: The annual interest rate
            due_dates: List of payment due dates
            disbursement_date: When the loan was disbursed

        Returns:
            PaymentSchedule with fixed principal amounts and variable total payments
        """
        if not due_dates:
            raise ValueError("At least one due date is required")

        # Calculate fixed principal payment per period
        fixed_principal_payment = principal.raw_amount / Decimal(str(len(due_dates)))

        # Get daily interest rate
        daily_rate = interest_rate.to_daily().as_decimal

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

            # Principal payment is fixed (except possibly last payment to handle rounding)
            if i == len(due_dates) - 1:
                # Last payment: use remaining balance to ensure zero final balance
                principal_payment = remaining_balance
            else:
                principal_payment = fixed_principal_payment

            # Total payment is principal + interest
            total_payment = principal_payment + interest_amount

            # Update remaining balance
            remaining_balance -= principal_payment

            # Create schedule entry
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
