"""Simplified Loan class that delegates calculations to configurable scheduler."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Type

from ..cash_flow import CashFlow, CashFlowItem
from ..interest_rate import InterestRate
from ..money import Money
from ..scheduler import BaseScheduler, PaymentSchedule, PriceScheduler


class Loan:
    """
    Represents a personal loan as a state machine with late payment fine support.

    Delegates complex calculations to a configurable scheduler and focuses on
    state management and tracking actual payments. Supports configurable late
    payment fines with grace periods.

    Features:
    - Flexible payment schedules using configurable schedulers
    - Automatic payment allocation: Fines → Interest → Principal
    - Configurable late payment fines (default 2% of missed payment)
    - Configurable grace periods before fines apply
    - Time-aware fine calculation and application
    - Comprehensive cash flow tracking including fine events

    Examples:
        >>> from money_warp import Loan, Money, InterestRate
        >>> from datetime import datetime
        >>> from decimal import Decimal
        >>>
        >>> # Basic loan with default fine settings
        >>> loan = Loan(
        ...     Money("10000"),
        ...     InterestRate("5% annual"),
        ...     [datetime(2024, 2, 1), datetime(2024, 3, 1)]
        ... )
        >>>
        >>> # Loan with custom fine settings
        >>> loan = Loan(
        ...     Money("10000"),
        ...     InterestRate("5% annual"),
        ...     [datetime(2024, 2, 1)],
        ...     late_fee_rate=Decimal("0.05"),  # 5% fine
        ...     grace_period_days=7  # 7-day grace period
        ... )
        >>>
        >>> # Check for late payments and apply fines
        >>> fines = loan.calculate_late_fines(datetime(2024, 2, 10))
        >>> print(f"Fines applied: {fines}")
        >>>
        >>> # Make payment (automatically allocated to fines first)
        >>> loan.record_payment(Money("500"), datetime(2024, 2, 11))
        >>> print(f"Outstanding fines: {loan.outstanding_fines}")
    """

    datetime_func = datetime

    def __init__(
        self,
        principal: Money,
        interest_rate: InterestRate,
        due_dates: List[datetime],
        disbursement_date: Optional[datetime] = None,
        scheduler: Optional[Type[BaseScheduler]] = None,
        late_fee_rate: Optional[Decimal] = None,
        grace_period_days: int = 0,
    ) -> None:
        """
        Create a loan with flexible payment schedule.

        Args:
            principal: The loan amount
            interest_rate: The annual interest rate
            due_dates: List of payment due dates (flexible scheduling)
            disbursement_date: When the loan was disbursed (defaults to first due date - 30 days)
            scheduler: Scheduler class to use for calculations (defaults to PriceScheduler)
            late_fee_rate: Late payment fee as decimal (defaults to 0.02 for 2%)
            grace_period_days: Days before late fees apply (defaults to 0)

        Examples:
            >>> # Basic loan with default 2% late fee, no grace period
            >>> loan = Loan(Money("10000"), InterestRate("5% annual"),
            ...            [datetime(2024, 2, 1)])
            >>>
            >>> # Loan with custom 5% late fee and 3-day grace period
            >>> loan = Loan(Money("10000"), InterestRate("5% annual"),
            ...            [datetime(2024, 2, 1)],
            ...            late_fee_rate=Decimal("0.05"), grace_period_days=3)
        """
        # Validate inputs first
        if not due_dates:
            raise ValueError("At least one due date is required")
        if principal.is_negative() or principal.is_zero():
            raise ValueError("Principal must be positive")
        if late_fee_rate is not None and late_fee_rate < 0:
            raise ValueError("Late fee rate must be non-negative")
        if grace_period_days < 0:
            raise ValueError("Grace period days must be non-negative")

        self.principal = principal
        self.interest_rate = interest_rate
        self.due_dates = sorted(due_dates)  # Ensure dates are sorted
        self.disbursement_date = disbursement_date or (self.due_dates[0] - timedelta(days=30))
        self.scheduler = scheduler or PriceScheduler
        self.late_fee_rate = late_fee_rate if late_fee_rate is not None else Decimal("0.02")
        self.grace_period_days = grace_period_days

        # State tracking
        self._all_payments: List[CashFlowItem] = []  # All payments ever made
        self.fines_applied: Dict[datetime, Money] = {}  # Track fines applied per due date

    @property
    def _actual_payments(self) -> List[CashFlowItem]:
        """Get actual payments that have occurred up to the current time."""
        current_time = self.now()
        return [payment for payment in self._all_payments if payment.datetime <= current_time]

    @property
    def current_balance(self) -> Money:
        """Get the current outstanding balance based on payments up to now, including fines."""
        # Start with principal balance
        balance = self.principal

        # Apply all principal payments made up to current time
        for payment in self._actual_payments:
            if payment.category in ("actual_principal", "principal"):
                balance = balance - payment.amount

        # Add outstanding fines to the balance (only fines that have been explicitly applied)
        balance = balance + self.outstanding_fines

        # Ensure balance doesn't go negative
        if balance.is_negative():
            balance = Money.zero()

        return balance

    @property
    def is_paid_off(self) -> bool:
        """Check if the loan is fully paid off, including all fines."""
        return self.current_balance.is_zero() or self.current_balance.is_negative()

    @property
    def last_payment_date(self) -> datetime:
        """Get the date of the last payment made, or disbursement date if no payments."""
        return self._actual_payments[-1].datetime if self._actual_payments else self.disbursement_date

    @property
    def total_fines(self) -> Money:
        """Get the total amount of fines applied to this loan."""
        if not self.fines_applied:
            return Money.zero()
        return Money(sum(fine.raw_amount for fine in self.fines_applied.values()))

    @property
    def outstanding_fines(self) -> Money:
        """Get the current unpaid fine amount."""
        total_fines = self.total_fines

        # Calculate how much of the fines have been paid
        fines_paid = Money.zero()
        for payment in self._actual_payments:
            if payment.category == "actual_fine":
                fines_paid = fines_paid + payment.amount

        outstanding = total_fines - fines_paid
        return outstanding if outstanding.is_positive() else Money.zero()

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

    def get_expected_payment_amount(self, due_date: datetime) -> Money:
        """
        Get the expected payment amount for a specific due date.

        Args:
            due_date: The due date to get the expected payment for

        Returns:
            The expected payment amount for that due date

        Raises:
            ValueError: If the due date is not in the loan's due dates
        """
        if due_date not in self.due_dates:
            raise ValueError(f"Due date {due_date} is not in loan's due dates")

        # Get the amortization schedule
        schedule = self.get_amortization_schedule()

        # Find the entry for this due date
        for entry in schedule:
            if entry.due_date == due_date:
                return entry.payment_amount

        # This shouldn't happen if due_date is valid, but just in case
        raise ValueError(f"Could not find payment amount for due date {due_date}")

    def is_payment_late(self, due_date: datetime, as_of_date: Optional[datetime] = None) -> bool:
        """
        Check if a payment is late considering the grace period.

        Args:
            due_date: The payment due date to check
            as_of_date: The date to check against (defaults to current time)

        Returns:
            True if the payment is late (past due date + grace period), False otherwise
        """
        if as_of_date is None:
            as_of_date = self.now()

        # Calculate the effective due date including grace period
        effective_due_date = due_date + timedelta(days=self.grace_period_days)

        return as_of_date > effective_due_date

    def calculate_late_fines(self, as_of_date: Optional[datetime] = None) -> Money:
        """
        Calculate and apply late payment fines for any new late payments.

        Args:
            as_of_date: The date to calculate fines as of (defaults to current time)

        Returns:
            The total amount of new fines applied
        """
        if as_of_date is None:
            as_of_date = self.now()

        new_fines_applied = Money.zero()

        # Check each due date for late payments
        for due_date in self.due_dates:
            # Skip if we've already applied a fine for this due date
            if due_date in self.fines_applied:
                continue

            # Skip if payment is not yet late
            if not self.is_payment_late(due_date, as_of_date):
                continue

            # Check if payment has been made for this due date
            payment_made = self._has_payment_for_due_date(due_date, as_of_date)

            if not payment_made:
                # Apply fine: percentage of expected payment amount
                expected_payment = self.get_expected_payment_amount(due_date)
                fine_amount = Money(expected_payment.raw_amount * self.late_fee_rate)

                # Record the fine
                self.fines_applied[due_date] = fine_amount
                new_fines_applied = new_fines_applied + fine_amount

        return new_fines_applied

    def _has_payment_for_due_date(self, due_date: datetime, as_of_date: datetime) -> bool:
        """
        Check if sufficient payment has been made for a specific due date.

        This is a simplified check - in a more complex system, you might want
        to track payments against specific due dates more precisely.
        """
        expected_payment = self.get_expected_payment_amount(due_date)

        # Get all payments made up to the as_of_date that are on or after the due date
        relevant_payments = [
            payment
            for payment in self._actual_payments
            if payment.datetime >= due_date
            and payment.datetime <= as_of_date
            and payment.category in ("actual_principal", "actual_interest")
        ]

        total_paid = sum((payment.amount for payment in relevant_payments), Money.zero())

        # Consider payment made if we've received at least the expected amount
        return total_paid >= expected_payment

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
        Generate the expected payment schedule without fines.

        This represents the original loan terms and expected payments.
        Fines are contingent events and are not included in the expected cash flow.
        Use get_actual_cash_flow() to see what actually happened, including fines.

        Returns:
            CashFlow with loan disbursement and expected payment schedule
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
        Record an actual payment made on the loan with automatic allocation.

        Payment allocation priority: Fines → Interest → Principal

        Args:
            amount: Total payment amount (positive value)
            payment_date: When the payment was made
            description: Optional description of the payment
        """
        if amount.is_negative() or amount.is_zero():
            raise ValueError("Payment amount must be positive")

        # Calculate any new late fines first
        self.calculate_late_fines(payment_date)

        remaining_amount = amount

        # Step 1: Allocate to outstanding fines first
        outstanding_fines = self.outstanding_fines
        if outstanding_fines.is_positive() and remaining_amount.is_positive():
            fine_payment = Money(min(outstanding_fines.raw_amount, remaining_amount.raw_amount))

            self._all_payments.append(
                CashFlowItem(
                    fine_payment,
                    payment_date,
                    f"Fine payment - {description or f'Payment on {payment_date.date()}'}",
                    "actual_fine",
                )
            )

            remaining_amount = remaining_amount - fine_payment

        # Step 2: Allocate to accrued interest
        if remaining_amount.is_positive():
            # Calculate accrued interest since last payment or disbursement
            days = self.days_since_last_payment(payment_date)
            daily_rate = self.interest_rate.to_daily().as_decimal

            # Calculate interest on principal balance (excluding fines for interest calculation)
            principal_balance = self.principal
            for payment in self._actual_payments:
                if payment.category in ("actual_principal", "principal"):
                    principal_balance = principal_balance - payment.amount

            if principal_balance.is_positive():
                accrued_interest = principal_balance.raw_amount * ((1 + daily_rate) ** Decimal(str(days)) - 1)
                interest_portion = Money(min(accrued_interest, remaining_amount.raw_amount))

                if interest_portion.is_positive():
                    self._all_payments.append(
                        CashFlowItem(
                            interest_portion,
                            payment_date,
                            f"Interest portion - {description or f'Payment on {payment_date.date()}'}",
                            "actual_interest",
                        )
                    )

                    remaining_amount = remaining_amount - interest_portion

        # Step 3: Allocate remaining amount to principal
        if remaining_amount.is_positive():
            self._all_payments.append(
                CashFlowItem(
                    remaining_amount,
                    payment_date,
                    f"Principal portion - {description or f'Payment on {payment_date.date()}'}",
                    "actual_principal",
                )
            )

    def get_actual_cash_flow(self) -> CashFlow:
        """
        Get the actual cash flow combining expected schedule with actual payments made.

        This shows both what was expected and what actually happened for comparison.
        Includes fine applications and fine payments.
        """
        # Start with expected cash flow
        expected_cf = self.generate_expected_cash_flow()
        items = list(expected_cf.items())

        # Add fine application events (these are like additional loan amounts)
        for due_date, fine_amount in self.fines_applied.items():
            items.append(
                CashFlowItem(
                    fine_amount,  # Positive amount (increases what borrower owes)
                    due_date + timedelta(days=self.grace_period_days + 1),  # Applied after grace period
                    f"Late payment fine applied for {due_date.date()}",
                    "fine_applied",
                )
            )

        # Add actual payments made
        for payment in self._actual_payments:
            items.append(
                CashFlowItem(
                    -payment.amount,  # Convert to outflow
                    payment.datetime,
                    payment.description or f"Actual payment on {payment.datetime.date()}",
                    payment.category,  # Keep original category (actual_interest, actual_principal, actual_fine)
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
        fine_info = f", fines={self.outstanding_fines}" if self.outstanding_fines.is_positive() else ""
        return (
            f"Loan(principal={self.principal}, rate={self.interest_rate}, "
            f"payments={len(self.due_dates)}, balance={self.current_balance}{fine_info})"
        )

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"Loan(principal={self.principal!r}, interest_rate={self.interest_rate!r}, "
            f"due_dates={self.due_dates!r}, disbursement_date={self.disbursement_date!r}, "
            f"late_fee_rate={self.late_fee_rate!r}, grace_period_days={self.grace_period_days!r})"
        )
