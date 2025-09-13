"""Price scheduler for fixed payment loans using PMT calculations."""

from datetime import datetime
from decimal import Decimal
from typing import List

from ..interest_rate import InterestRate
from ..money import Money
from .base import BaseScheduler
from .schedule import PaymentSchedule, PaymentScheduleEntry


class PriceScheduler(BaseScheduler):
    """
    Price scheduler that calculates fixed payments using PMT formula.

    This scheduler creates a fixed payment amount for each period,
    with daily compounding interest calculations.
    """

    @classmethod
    def generate_schedule(
        cls, principal: Money, interest_rate: InterestRate, due_dates: List[datetime], disbursement_date: datetime
    ) -> PaymentSchedule:
        """
        Generate payment schedule with fixed payment amounts.

        Args:
            principal: The loan amount
            interest_rate: The annual interest rate
            due_dates: List of payment due dates
            disbursement_date: When the loan was disbursed

        Returns:
            PaymentSchedule with fixed payment amounts
        """
        if not due_dates:
            raise ValueError("At least one due date is required")

        # Calculate fixed payment amount
        payment_amount = cls._calculate_fixed_payment(principal, interest_rate, due_dates, disbursement_date)

        # Generate schedule entries
        entries = []
        remaining_balance = principal.raw_amount
        daily_rate = interest_rate.to_daily().as_decimal

        for i, due_date in enumerate(due_dates):
            # Calculate days since last payment (or disbursement)
            prev_date = disbursement_date if i == 0 else due_dates[i - 1]
            days = (due_date - prev_date).days

            # Calculate interest for this period
            interest_amount = remaining_balance * ((1 + daily_rate) ** Decimal(str(days)) - 1)

            # Store beginning balance before updating
            beginning_balance = remaining_balance

            # For the last payment, pay off remaining balance
            if i == len(due_dates) - 1:
                total_payment = remaining_balance + interest_amount
                principal_payment = remaining_balance
            else:
                total_payment = payment_amount.raw_amount
                principal_payment = total_payment - interest_amount

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
                ending_balance=Money(max(0, remaining_balance)),
            )
            entries.append(entry)

        return PaymentSchedule(entries=entries)

    @classmethod
    def _calculate_fixed_payment(
        cls, principal: Money, interest_rate: InterestRate, due_dates: List[datetime], disbursement_date: datetime
    ) -> Money:
        """Calculate the fixed payment amount using PMT formula."""
        if len(due_dates) == 1:
            # Single payment loan
            days = (due_dates[0] - disbursement_date).days
            daily_rate = interest_rate.to_daily().as_decimal
            future_value = principal.raw_amount * (1 + daily_rate) ** Decimal(str(days))
            return Money(future_value)

        # Multiple payment loan - use PMT formula
        total_days = (due_dates[-1] - disbursement_date).days
        num_payments = len(due_dates)
        avg_days_per_payment = total_days / num_payments

        # Convert to periodic rate
        daily_rate = interest_rate.to_daily().as_decimal
        periodic_rate = (1 + daily_rate) ** Decimal(str(avg_days_per_payment)) - 1

        # Handle zero interest rate
        if periodic_rate == 0:
            return Money(principal.raw_amount / num_payments)

        # PMT formula: P * [r(1+r)^n] / [(1+r)^n - 1]
        numerator = principal.raw_amount * periodic_rate * (1 + periodic_rate) ** Decimal(str(num_payments))
        denominator = (1 + periodic_rate) ** Decimal(str(num_payments)) - 1
        payment = numerator / denominator

        return Money(payment)
