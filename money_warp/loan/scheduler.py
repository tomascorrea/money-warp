"""Payment scheduler for loan calculations and amortization schedules."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List

from ..cash_flow import CashFlow, CashFlowItem
from ..interest_rate import InterestRate
from ..money import Money


class PaymentScheduler:
    """
    Handles PMT calculations and payment schedule generation for loans.

    Separates the complex financial calculations from the loan state management.
    """

    def __init__(self, principal: Money, interest_rate: InterestRate) -> None:
        """
        Initialize the scheduler with loan parameters.

        Args:
            principal: The loan amount
            interest_rate: The annual interest rate
        """
        self.principal = principal
        self.interest_rate = interest_rate

    def calculate_fixed_payment(self, due_dates: List[datetime], disbursement_date: datetime) -> Money:
        """
        Calculate the fixed payment amount using PMT formula.

        Args:
            due_dates: List of payment due dates
            disbursement_date: When the loan was disbursed

        Returns:
            Fixed payment amount for regular payments
        """
        if len(due_dates) == 1:
            return self._calculate_single_payment(due_dates[0], disbursement_date)

        return self._calculate_pmt_payment(due_dates, disbursement_date)

    def _calculate_single_payment(self, due_date: datetime, disbursement_date: datetime) -> Money:
        """Calculate payment for single-payment loan."""
        days = (due_date - disbursement_date).days
        daily_rate = self.interest_rate.to_daily().as_decimal
        future_value = self.principal.raw_amount * (1 + daily_rate) ** Decimal(str(days))
        return Money(future_value)

    def _calculate_pmt_payment(self, due_dates: List[datetime], disbursement_date: datetime) -> Money:
        """Calculate payment using PMT formula for multiple payments."""
        # Calculate average period for PMT calculation
        total_days = (due_dates[-1] - disbursement_date).days
        num_payments = len(due_dates)
        avg_days_per_payment = total_days / num_payments

        # Convert to periodic rate
        daily_rate = self.interest_rate.to_daily().as_decimal
        periodic_rate = (1 + daily_rate) ** Decimal(str(avg_days_per_payment)) - 1

        # Handle zero interest rate
        if periodic_rate == 0:
            return Money(self.principal.raw_amount / num_payments)

        # PMT formula: P * [r(1+r)^n] / [(1+r)^n - 1]
        numerator = self.principal.raw_amount * periodic_rate * (1 + periodic_rate) ** Decimal(str(num_payments))
        denominator = (1 + periodic_rate) ** Decimal(str(num_payments)) - 1
        payment = numerator / denominator

        return Money(payment)

    def generate_payment_schedule(
        self, due_dates: List[datetime], disbursement_date: datetime, include_disbursement: bool = True
    ) -> CashFlow:
        """
        Generate complete payment schedule with daily compounding.

        Args:
            due_dates: List of payment due dates
            disbursement_date: When the loan was disbursed
            include_disbursement: Whether to include the loan disbursement

        Returns:
            CashFlow with payment schedule
        """
        items = []

        # Add disbursement if requested
        if include_disbursement:
            items.append(CashFlowItem(self.principal, disbursement_date, "Loan disbursement", "disbursement"))

        # Calculate fixed payment amount
        payment_amount = self.calculate_fixed_payment(due_dates, disbursement_date)

        # Generate payment schedule with daily compounding
        remaining_balance = self.principal.raw_amount
        daily_rate = self.interest_rate.to_daily().as_decimal

        for i, due_date in enumerate(due_dates):
            # Calculate days since last payment (or disbursement)
            prev_date = disbursement_date if i == 0 else due_dates[i - 1]

            days = (due_date - prev_date).days

            # Calculate interest for this period
            interest_amount = remaining_balance * ((1 + daily_rate) ** Decimal(str(days)) - 1)

            # For the last payment, pay off remaining balance
            if i == len(due_dates) - 1:
                total_payment = remaining_balance + interest_amount
                principal_payment = remaining_balance
            else:
                total_payment = payment_amount.raw_amount
                principal_payment = total_payment - interest_amount

            # Add payment breakdown items (negative amounts for outflows)
            items.append(CashFlowItem(Money(-interest_amount), due_date, f"Interest payment {i + 1}", "interest"))

            items.append(CashFlowItem(Money(-principal_payment), due_date, f"Principal payment {i + 1}", "principal"))

            # Update remaining balance
            remaining_balance -= principal_payment

            # Ensure we don't go negative due to rounding
            if remaining_balance < 0:
                remaining_balance = 0

        return CashFlow(items)

    def generate_amortization_table(
        self, due_dates: List[datetime], disbursement_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Generate detailed amortization table.

        Args:
            due_dates: List of payment due dates
            disbursement_date: When the loan was disbursed

        Returns:
            List of dictionaries with payment breakdown details
        """
        schedule = []
        remaining_balance = self.principal.raw_amount
        daily_rate = self.interest_rate.to_daily().as_decimal
        payment_amount = self.calculate_fixed_payment(due_dates, disbursement_date)

        for i, due_date in enumerate(due_dates):
            # Calculate days since last payment
            prev_date = disbursement_date if i == 0 else due_dates[i - 1]

            days = (due_date - prev_date).days

            # Calculate interest for this period
            interest_amount = remaining_balance * ((1 + daily_rate) ** Decimal(str(days)) - 1)

            # For the last payment, pay off remaining balance
            if i == len(due_dates) - 1:
                total_payment = remaining_balance + interest_amount
                principal_payment = remaining_balance
            else:
                total_payment = payment_amount.raw_amount
                principal_payment = total_payment - interest_amount

            # Store beginning balance before updating
            beginning_balance = remaining_balance

            # Update remaining balance
            remaining_balance -= principal_payment

            schedule.append(
                {
                    "payment_number": i + 1,
                    "due_date": due_date,
                    "days_in_period": days,
                    "beginning_balance": Money(beginning_balance),
                    "payment_amount": Money(interest_amount + principal_payment),
                    "principal_payment": Money(principal_payment),
                    "interest_payment": Money(interest_amount),
                    "ending_balance": Money(max(0, remaining_balance)),
                }
            )

        return schedule

    def calculate_remaining_schedule(
        self, remaining_balance: Money, remaining_due_dates: List[datetime], calculation_date: datetime
    ) -> CashFlow:
        """
        Calculate remaining payment schedule for a partially paid loan.

        Args:
            remaining_balance: Current outstanding balance
            remaining_due_dates: Remaining payment due dates
            calculation_date: Date to calculate from (usually today)

        Returns:
            CashFlow with remaining payments
        """
        if remaining_balance.is_zero() or not remaining_due_dates:
            return CashFlow.empty()

        # Create a temporary scheduler for the remaining balance
        temp_scheduler = PaymentScheduler(remaining_balance, self.interest_rate)

        # Generate schedule without disbursement (already happened)
        return temp_scheduler.generate_payment_schedule(
            remaining_due_dates, calculation_date, include_disbursement=False
        )
