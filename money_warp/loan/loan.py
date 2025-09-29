"""Simplified Loan class that delegates calculations to configurable scheduler."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Type

from ..cash_flow import CashFlow, CashFlowItem
from ..interest_rate import InterestRate
from ..money import Money
from ..scheduler import BaseScheduler, PaymentSchedule, PriceScheduler


class Loan:
    """
    Represents a personal loan as a state machine.

    Delegates complex calculations to a configurable scheduler and focuses on
    state management and tracking actual payments.
    """

    datetime_func = datetime

    def __init__(
        self,
        principal: Money,
        interest_rate: InterestRate,
        due_dates: List[datetime],
        disbursement_date: Optional[datetime] = None,
        scheduler: Optional[Type[BaseScheduler]] = None,
    ) -> None:
        """
        Create a loan with flexible payment schedule.

        Args:
            principal: The loan amount
            interest_rate: The annual interest rate
            due_dates: List of payment due dates (flexible scheduling)
            disbursement_date: When the loan was disbursed (defaults to first due date - 30 days)
            scheduler: Scheduler class to use for calculations (defaults to PriceScheduler)
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
        self.scheduler = scheduler or PriceScheduler

        # State tracking
        self._all_payments: List[CashFlowItem] = []  # All payments ever made

    @property
    def _actual_payments(self) -> List[CashFlowItem]:
        """Get actual payments that have occurred up to the current time."""
        current_time = self.now()
        return [payment for payment in self._all_payments if payment.datetime <= current_time]

    @property
    def current_balance(self) -> Money:
        """Get the current outstanding balance based on payments up to now."""
        balance = self.principal

        # Apply all principal payments made up to current time
        for payment in self._actual_payments:
            if payment.category in ("actual_principal", "principal"):
                balance = balance - payment.amount

        # Ensure balance doesn't go negative
        if balance.is_negative():
            balance = Money.zero()

        return balance

    @property
    def is_paid_off(self) -> bool:
        """Check if the loan is fully paid off."""
        return self.current_balance.is_zero() or self.current_balance.is_negative()

    @property
    def last_payment_date(self) -> datetime:
        """Get the date of the last payment made, or disbursement date if no payments."""
        return self._actual_payments[-1].datetime if self._actual_payments else self.disbursement_date

    def now(self) -> datetime:
        """Get the current datetime. Can be overridden for time travel scenarios."""
        return self.datetime_func.now()

    def date(self) -> datetime:
        """Get the current datetime. Can be overridden for time travel scenarios."""
        return self.datetime_func.now()

    def days_since_last_payment(self, as_of_date: Optional[datetime] = None) -> int:
        """Get the number of days since the last payment as of a given date (defaults to current time)."""
        if as_of_date is None:
            as_of_date = self.now()
        return (as_of_date - self.last_payment_date).days

    def present_value(
        self, discount_rate: Optional[InterestRate] = None, valuation_date: Optional[datetime] = None
    ) -> Money:
        """
        Calculate the Present Value of the loan's expected cash flows.

        This is a convenience method that generates the expected cash flow
        and calculates its present value. By default, uses the loan's own
        interest rate as the discount rate.

        Args:
            discount_rate: The discount rate to use (defaults to loan's interest rate)
            valuation_date: Date to discount back to (defaults to current time)

        Returns:
            The present value of the loan's expected cash flows

        Examples:
            >>> from money_warp import Loan, Money, InterestRate
            >>> from datetime import datetime
            >>>
            >>> loan = Loan(Money("10000"), InterestRate("5% annual"),
            ...            [datetime(2024, 1, 15), datetime(2024, 2, 15)])
            >>>
            >>> # Get present value using loan's own rate (should be close to zero)
            >>> pv = loan.present_value()
            >>> print(f"Loan PV at its own rate: {pv}")
            >>>
            >>> # Get present value using different discount rate
            >>> pv = loan.present_value(InterestRate("8% annual"))
            >>> print(f"Loan PV at 8%: {pv}")
        """
        # Import here to avoid circular import
        from ..present_value import present_value

        # Use loan's interest rate as default discount rate
        if discount_rate is None:
            discount_rate = self.interest_rate

        # Generate expected cash flows
        expected_cf = self.generate_expected_cash_flow()

        # Use current time as default valuation date
        if valuation_date is None:
            valuation_date = self.now()

        # Calculate and return present value
        return present_value(expected_cf, discount_rate, valuation_date)

    def irr(self, guess: Optional[InterestRate] = None) -> InterestRate:
        """
        Calculate the Internal Rate of Return (IRR) of the loan's expected cash flows.

        This is a convenience method that generates the expected cash flow
        and calculates its IRR. The IRR represents the effective rate of return
        of the loan from the borrower's perspective.

        Note: To calculate IRR from a specific date, use the Time Machine:
        with Warp(loan, target_date) as warped_loan:
            irr = warped_loan.irr()

        Args:
            guess: Initial guess for IRR (defaults to 10% annual)

        Returns:
            The internal rate of return of the loan's expected cash flows

        Examples:
            >>> from money_warp import Loan, Money, InterestRate, Warp
            >>> from datetime import datetime
            >>>
            >>> loan = Loan(Money("10000"), InterestRate("5% annual"),
            ...            [datetime(2024, 1, 15), datetime(2024, 2, 15)])
            >>>
            >>> # Get IRR - should be close to loan's interest rate
            >>> loan_irr = loan.irr()
            >>> print(f"Loan IRR: {loan_irr}")
            >>>
            >>> # Get IRR from a specific date using Time Machine
            >>> with Warp(loan, datetime(2024, 1, 10)) as warped_loan:
            ...     past_irr = warped_loan.irr()
            >>> print(f"IRR from past perspective: {past_irr}")
        """
        # Import here to avoid circular import
        from ..present_value import internal_rate_of_return

        # Generate expected cash flows (will be time-aware if warped)
        expected_cf = self.generate_expected_cash_flow()

        # Calculate and return IRR
        return internal_rate_of_return(expected_cf, guess)

    def generate_expected_cash_flow(self) -> CashFlow:
        """
        Generate the expected payment schedule.

        Returns:
            CashFlow with loan disbursement and payment schedule
        """
        items = []

        # Add disbursement
        items.append(CashFlowItem(self.principal, self.disbursement_date, "Loan disbursement", "disbursement"))

        # Generate schedule using our method
        schedule = self.get_amortization_schedule()

        # Convert schedule entries to CashFlow items
        for entry in schedule:
            # Add payment breakdown items (negative amounts for outflows)
            items.append(
                CashFlowItem(
                    Money(-entry.interest_payment.raw_amount),
                    entry.due_date,
                    f"Interest payment {entry.payment_number}",
                    "interest",
                )
            )

            items.append(
                CashFlowItem(
                    Money(-entry.principal_payment.raw_amount),
                    entry.due_date,
                    f"Principal payment {entry.payment_number}",
                    "principal",
                )
            )

        return CashFlow(items)

    def record_payment(self, amount: Money, payment_date: datetime, description: Optional[str] = None) -> None:
        """
        Record an actual payment made on the loan with automatic interest/principal allocation.

        Args:
            amount: Total payment amount (positive value)
            payment_date: When the payment was made
            description: Optional description of the payment
        """
        if amount.is_negative() or amount.is_zero():
            raise ValueError("Payment amount must be positive")

        # Calculate accrued interest since last payment or disbursement
        days = self.days_since_last_payment(payment_date)
        daily_rate = self.interest_rate.to_daily().as_decimal

        # Calculate interest on current balance
        accrued_interest = self.current_balance.raw_amount * ((1 + daily_rate) ** Decimal(str(days)) - 1)

        # Interest portion is the minimum of accrued interest and payment amount
        interest_portion = Money(min(accrued_interest, amount.raw_amount))
        principal_portion = amount - interest_portion

        # Record the payment components
        if interest_portion.is_positive():
            self._all_payments.append(
                CashFlowItem(
                    interest_portion,
                    payment_date,
                    f"Interest portion - {description or f'Payment on {payment_date.date()}'}",
                    "actual_interest",
                )
            )

        if principal_portion.is_positive():
            self._all_payments.append(
                CashFlowItem(
                    principal_portion,
                    payment_date,
                    f"Principal portion - {description or f'Payment on {payment_date.date()}'}",
                    "actual_principal",
                )
            )

        # Balance is now calculated dynamically from payments

    def get_actual_cash_flow(self) -> CashFlow:
        """
        Get the actual cash flow combining expected schedule with actual payments made.

        This shows both what was expected and what actually happened for comparison.
        """
        # Start with expected cash flow
        expected_cf = self.generate_expected_cash_flow()
        items = list(expected_cf.items())

        # Add actual payments made
        for payment in self._actual_payments:
            items.append(
                CashFlowItem(
                    -payment.amount,  # Convert to outflow
                    payment.datetime,
                    payment.description or f"Actual payment on {payment.datetime.date()}",
                    payment.category,  # Keep original category (actual_interest, actual_principal)
                )
            )

        return CashFlow(items)

    def get_amortization_schedule(self) -> PaymentSchedule:
        """
        Get detailed amortization schedule using the scheduler.

        Returns:
            PaymentSchedule with all payment details
        """
        return self.scheduler.generate_schedule(
            self.principal, self.interest_rate, self.due_dates, self.disbursement_date
        )

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
