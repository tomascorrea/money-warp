"""Simplified Loan class that delegates calculations to PaymentScheduler."""

from datetime import datetime, timedelta
from typing import List, Optional

from ..cash_flow import CashFlow, CashFlowItem
from ..interest_rate import InterestRate
from ..money import Money
from .scheduler import PaymentScheduler


class Loan:
    """
    Represents a personal loan as a state machine.

    Delegates complex calculations to PaymentScheduler and focuses on
    state management and tracking actual payments.
    """

    def __init__(
        self,
        principal: Money,
        interest_rate: InterestRate,
        due_dates: List[datetime],
        disbursement_date: Optional[datetime] = None,
    ) -> None:
        """
        Create a loan with flexible payment schedule.

        Args:
            principal: The loan amount
            interest_rate: The annual interest rate
            due_dates: List of payment due dates (flexible scheduling)
            disbursement_date: When the loan was disbursed (defaults to first due date - 30 days)
        """
        # Validate inputs first
        if not due_dates:
            raise ValueError("At least one due date is required")
        if principal.is_negative() or principal.is_zero():
            raise ValueError("Principal must be positive")

        self.principal = principal
        self.interest_rate = interest_rate
        self.due_dates = sorted(due_dates)  # Ensure dates are sorted
        self.disbursement_date = disbursement_date or (self.due_dates[0] - timedelta(days=30))

        # Create scheduler for calculations
        self._scheduler = PaymentScheduler(principal, interest_rate)

        # State tracking
        self._actual_payments: List[CashFlowItem] = []
        self._current_balance = principal

    @property
    def current_balance(self) -> Money:
        """Get the current outstanding balance."""
        return self._current_balance

    @property
    def is_paid_off(self) -> bool:
        """Check if the loan is fully paid off."""
        return self._current_balance.is_zero() or self._current_balance.is_negative()

    def calculate_payment_amount(self) -> Money:
        """
        Calculate the fixed payment amount using the scheduler.

        Returns:
            Fixed payment amount for regular payments
        """
        return self._scheduler.calculate_fixed_payment(self.due_dates, self.disbursement_date)

    def generate_expected_cash_flow(self) -> CashFlow:
        """
        Generate the expected payment schedule.

        Returns:
            CashFlow with loan disbursement and payment schedule
        """
        return self._scheduler.generate_payment_schedule(
            self.due_dates, self.disbursement_date, include_disbursement=True
        )

    def record_payment(self, amount: Money, payment_date: datetime, description: Optional[str] = None) -> None:
        """
        Record an actual payment made on the loan.

        Args:
            amount: Payment amount (positive value)
            payment_date: When the payment was made
            description: Optional description of the payment
        """
        if amount.is_negative():
            raise ValueError("Payment amount must be positive")

        # Record the payment
        payment_item = CashFlowItem(
            amount, payment_date, description or f"Payment on {payment_date.date()}", "actual_payment"
        )
        self._actual_payments.append(payment_item)

        # Update current balance (simplified - in reality would need interest calculation)
        self._current_balance = self._current_balance - amount

        # Ensure balance doesn't go negative
        if self._current_balance.is_negative():
            self._current_balance = Money.zero()

    def get_actual_cash_flow(self) -> CashFlow:
        """Get the cash flow of actual payments made."""
        items = []

        # Add disbursement
        items.append(CashFlowItem(self.principal, self.disbursement_date, "Loan disbursement", "disbursement"))

        # Add actual payments (as negative amounts for outflows)
        for payment in self._actual_payments:
            items.append(
                CashFlowItem(
                    -payment.amount, payment.datetime, payment.description, payment.category  # Convert to outflow
                )
            )

        return CashFlow(items)

    def get_remaining_cash_flow(self) -> CashFlow:
        """
        Generate the remaining payment schedule based on current balance.

        Returns:
            CashFlow with remaining payments to be made
        """
        if self.is_paid_off:
            return CashFlow.empty()

        # Find remaining due dates
        now = datetime.now()
        remaining_dates = [date for date in self.due_dates if date > now]

        if not remaining_dates:
            # All due dates have passed, but balance remains
            # Create a single payment due immediately
            remaining_dates = [now]

        # Use scheduler to calculate remaining payments
        return self._scheduler.calculate_remaining_schedule(self._current_balance, remaining_dates, now)

    def get_amortization_schedule(self) -> List[dict]:
        """
        Get detailed amortization schedule using the scheduler.

        Returns:
            List of dictionaries with payment breakdown details
        """
        return self._scheduler.generate_amortization_table(self.due_dates, self.disbursement_date)

    def __str__(self) -> str:
        """String representation of the loan."""
        return (
            f"Loan(principal={self.principal}, rate={self.interest_rate}, "
            f"payments={len(self.due_dates)}, balance={self.current_balance})"
        )

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"Loan(principal={self.principal!r}, interest_rate={self.interest_rate!r}, "
            f"due_dates={self.due_dates!r}, disbursement_date={self.disbursement_date!r})"
        )
