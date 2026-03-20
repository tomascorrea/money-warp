"""Simplified Loan class that delegates calculations to configurable scheduler."""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Type

from ..cash_flow import CashFlow, CashFlowItem, CashFlowType
from ..interest_rate import InterestRate
from ..money import Money
from ..rate import Rate
from ..scheduler import BaseScheduler, PaymentSchedule, PaymentScheduleEntry, PriceScheduler
from ..tax.base import BaseTax, TaxResult
from ..time_context import TimeContext
from ..tz import to_datetime, tz_aware
from .installment import Installment
from .interest_calculator import InterestCalculator, MoraStrategy
from .settlement import AnticipationResult, Settlement, SettlementAllocation


class Loan:
    """
    Represents a personal loan as a state machine with late payment fine support.

    Delegates complex calculations to a configurable scheduler and focuses on
    state management and tracking actual payments. Supports configurable late
    payment fines with grace periods.

    Features:
    - Flexible payment schedules using configurable schedulers
    - Automatic payment allocation: Fines → Interest → Principal
    - Configurable fines (default 2% of missed payment)
    - Configurable grace periods before fines apply
    - Time-aware fine calculation and application
    - Comprehensive cash flow tracking including fine events

    Examples:
        >>> from money_warp import Loan, Money, InterestRate
        >>> from datetime import date, datetime
        >>> from decimal import Decimal
        >>>
        >>> # Basic loan with default fine settings
        >>> loan = Loan(
        ...     Money("10000"),
        ...     InterestRate("5% annual"),
        ...     [date(2024, 2, 1), date(2024, 3, 1)]
        ... )
        >>>
        >>> # Loan with custom fine settings
        >>> loan = Loan(
        ...     Money("10000"),
        ...     InterestRate("5% annual"),
        ...     [date(2024, 2, 1)],
        ...     fine_rate=Decimal("0.05"),  # 5% fine
        ...     grace_period_days=7  # 7-day grace period
        ... )
        >>>
        >>> # Check for late payments and apply fines
        >>> fines = loan.calculate_late_fines(datetime(2024, 2, 10))
        >>> print(f"Fines applied: {fines}")
        >>>
        >>> # Make payment (automatically allocated to fines first)
        >>> loan.record_payment(Money("500"), datetime(2024, 2, 11))
        >>> print(f"Outstanding fines: {loan.fine_balance}")
    """

    @tz_aware
    def __init__(
        self,
        principal: Money,
        interest_rate: InterestRate,
        due_dates: List[date],
        disbursement_date: Optional[datetime] = None,
        scheduler: Optional[Type[BaseScheduler]] = None,
        fine_rate: Optional[InterestRate] = None,
        grace_period_days: int = 0,
        mora_interest_rate: Optional[InterestRate] = None,
        mora_strategy: MoraStrategy = MoraStrategy.COMPOUND,
        taxes: Optional[List[BaseTax]] = None,
        is_grossed_up: bool = False,
    ) -> None:
        """
        Create a loan with flexible payment schedule.

        Args:
            principal: The loan amount
            interest_rate: The annual interest rate
            due_dates: List of payment due dates (flexible scheduling)
            disbursement_date: When the loan was disbursed (defaults to now). Must be before the first due date.
            scheduler: Scheduler class to use for calculations (defaults to PriceScheduler)
            fine_rate: Fine rate applied to missed payments (defaults to 2% annual)
            grace_period_days: Days after due date before fines apply (defaults to 0)
            mora_interest_rate: Interest rate for mora (late) interest (defaults to interest_rate)
            mora_strategy: How mora interest is computed (defaults to COMPOUND)
            taxes: Optional list of taxes applied to this loan (e.g., IOF)
            is_grossed_up: Whether the principal was grossed up to absorb taxes.
                When True, generate_expected_cash_flow() omits the separate tax entry
                because the tax is already reflected in the higher principal.

        Examples:
            >>> # Basic loan with default 2% fine, no grace period
            >>> loan = Loan(Money("10000"), InterestRate("5% annual"),
            ...            [date(2024, 2, 1)])
            >>>
            >>> # Loan with custom 5% fine and 3-day grace period
            >>> loan = Loan(Money("10000"), InterestRate("5% annual"),
            ...            [date(2024, 2, 1)],
            ...            fine_rate=InterestRate("5% annual"), grace_period_days=3)
            >>>
            >>> # Loan with separate mora interest rate
            >>> loan = Loan(Money("10000"), InterestRate("5% annual"),
            ...            [date(2024, 2, 1)],
            ...            mora_interest_rate=InterestRate("12% annual"))
        """
        # Validate inputs first
        if not due_dates:
            raise ValueError("At least one due date is required")
        if principal.is_negative() or principal.is_zero():
            raise ValueError("Principal must be positive")
        if grace_period_days < 0:
            raise ValueError("Grace period days must be non-negative")

        self._time_ctx = TimeContext()

        self.principal = principal
        self.interest_rate = interest_rate
        self.mora_interest_rate = mora_interest_rate or interest_rate
        self.mora_strategy = mora_strategy
        self._interest = InterestCalculator(interest_rate, self.mora_interest_rate, mora_strategy)
        self.due_dates = sorted(due_dates)
        self.disbursement_date = disbursement_date if disbursement_date is not None else self._time_ctx.now()
        if self.disbursement_date.date() >= self.due_dates[0]:
            raise ValueError("disbursement_date must be before the first due date")
        self.scheduler = scheduler or PriceScheduler
        self.fine_rate = fine_rate if fine_rate is not None else InterestRate("2% annual")
        self.grace_period_days = grace_period_days
        self.taxes: List[BaseTax] = taxes or []
        self.is_grossed_up = is_grossed_up

        # State tracking
        self._all_payments: List[CashFlowItem] = []  # All payments ever made
        self._payment_item_offsets: List[int] = []  # Start index in _all_payments for each payment
        self._actual_schedule_entries: List[PaymentScheduleEntry] = []  # Actual payment history as schedule entries
        self._actual_payment_datetimes: List[datetime] = []  # Full timestamps for each record_payment call
        self.fines_applied: Dict[date, Money] = {}  # Track fines applied per due date
        self._tax_cache: Optional[Dict[str, TaxResult]] = None

    @property
    def _actual_payments(self) -> List[CashFlowItem]:
        """Get actual payments that have occurred up to the current time."""
        current_time = self.now()
        return [payment for payment in self._all_payments if payment.datetime <= current_time]

    @property
    def principal_balance(self) -> Money:
        """Get the current principal balance (original principal minus principal payments)."""
        balance = self.principal

        # Apply all principal payments made up to current time (respecting warped time)
        current_time = self.now()
        for payment in self._all_payments:
            if payment.datetime <= current_time and "principal" in payment.category:
                balance = balance - payment.amount

        # Ensure balance doesn't go negative
        if balance.is_negative():
            balance = Money.zero()

        return balance

    def _accrued_interest_components(self) -> tuple:
        """Return ``(regular, mora)`` accrued interest since last payment.

        Shared computation used by :pyattr:`interest_balance` and
        :pyattr:`mora_interest_balance`.
        """
        days = self.days_since_last_payment()
        principal_bal = self.principal_balance

        if principal_bal.is_positive() and days > 0:
            try:
                due_date = self._next_unpaid_due_date()
            except ValueError:
                due_date = None
            return self._compute_accrued_interest(days, principal_bal, due_date, self.last_payment_date)

        return Money.zero(), Money.zero()

    @property
    def interest_balance(self) -> Money:
        """Regular (non-mora) accrued interest since last payment."""
        return self._accrued_interest_components()[0]

    @property
    def mora_interest_balance(self) -> Money:
        """Mora accrued interest since last payment.

        Respects ``mora_interest_rate`` and ``mora_strategy`` when the
        borrower is past the next unpaid due date.
        """
        return self._accrued_interest_components()[1]

    @property
    def current_balance(self) -> Money:
        """Get the current outstanding balance.

        Equal to ``principal_balance + interest_balance +
        mora_interest_balance + fine_balance``.
        """
        return self.principal_balance + self.interest_balance + self.mora_interest_balance + self.fine_balance

    @property
    def is_paid_off(self) -> bool:
        """Check if the loan is fully paid off, including all fines."""
        return self.current_balance.is_zero() or self.current_balance.is_negative()

    @property
    def last_payment_date(self) -> datetime:
        """Get the date of the last payment made, or disbursement date if no payments."""
        current_time = self.now()
        actual_payments = [payment for payment in self._all_payments if payment.datetime <= current_time]
        return actual_payments[-1].datetime if actual_payments else self.disbursement_date

    @property
    def total_fines(self) -> Money:
        """Get the total amount of fines applied to this loan."""
        if not self.fines_applied:
            return Money.zero()
        return Money(sum(fine.raw_amount for fine in self.fines_applied.values()))

    @property
    def fine_balance(self) -> Money:
        """Unpaid fine amount (total fines applied minus fines paid)."""
        total_fines = self.total_fines

        fines_paid = Money.zero()
        for payment in self._actual_payments:
            if "fine" in payment.category:
                fines_paid = fines_paid + payment.amount

        outstanding = total_fines - fines_paid
        return outstanding if outstanding.is_positive() else Money.zero()

    @property
    def tax_amounts(self) -> Dict[str, TaxResult]:
        """Per-tax results keyed by tax class name. Computed lazily and cached."""
        if self._tax_cache is not None:
            return self._tax_cache

        results: Dict[str, TaxResult] = {}
        if self.taxes:
            schedule = self.get_original_schedule()
            for tax in self.taxes:
                key = type(tax).__name__
                results[key] = tax.calculate(schedule, self.disbursement_date)

        self._tax_cache = results
        return results

    @property
    def total_tax(self) -> Money:
        """Sum of all taxes applied to this loan."""
        amounts = self.tax_amounts
        if not amounts:
            return Money.zero()
        return Money(sum(r.total.raw_amount for r in amounts.values()))

    @property
    def net_disbursement(self) -> Money:
        """Amount the borrower actually receives (principal minus total tax)."""
        return self.principal - self.total_tax

    def now(self) -> datetime:
        """Current datetime (Warp-aware via shared TimeContext)."""
        return self._time_ctx.now()

    def date(self) -> datetime:
        """Current datetime (Warp-aware via shared TimeContext)."""
        return self._time_ctx.now()

    def _on_warp(self, target_date: datetime) -> None:
        """Hook called by Warp after overriding TimeContext."""
        self.calculate_late_fines(target_date)

    @tz_aware
    def days_since_last_payment(self, as_of_date: Optional[datetime] = None) -> int:
        """Get the number of days since the last payment as of a given date (defaults to current time)."""
        if as_of_date is None:
            as_of_date = self.now()
        return (as_of_date.date() - self.last_payment_date.date()).days

    def get_expected_payment_amount(self, due_date: date) -> Money:
        """
        Get the expected payment amount for a specific due date from the original schedule.

        This always references the original loan terms (not the rebuilt schedule),
        which is important for fine calculations.

        Args:
            due_date: The due date to get the expected payment for

        Returns:
            The expected payment amount for that due date

        Raises:
            ValueError: If the due date is not in the loan's due dates
        """
        if due_date not in self.due_dates:
            raise ValueError(f"Due date {due_date} is not in loan's due dates")

        schedule = self.get_original_schedule()

        for entry in schedule:
            if entry.due_date == due_date:
                return entry.payment_amount

        raise ValueError(f"Could not find payment amount for due date {due_date}")

    @tz_aware
    def is_payment_late(self, due_date: date, as_of_date: Optional[datetime] = None) -> bool:
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

        effective_due_date = due_date + timedelta(days=self.grace_period_days)

        return as_of_date.date() > effective_due_date

    @tz_aware
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
                fine_amount = Money(expected_payment.raw_amount * self.fine_rate.as_decimal())

                # Record the fine
                self.fines_applied[due_date] = fine_amount
                new_fines_applied = new_fines_applied + fine_amount

        return new_fines_applied

    def _has_payment_for_due_date(self, due_date: date, as_of_date: datetime) -> bool:
        """
        Check if sufficient payment has been made for a specific due date.

        This checks if the total payment amount (all categories) made on or around
        the due date meets or exceeds the expected installment payment.
        """
        expected_payment = self.get_expected_payment_amount(due_date)

        _payment_categories = frozenset({"principal", "interest", "fine"})
        exact_date_payments = [
            payment
            for payment in self._all_payments
            if payment.datetime.date() == due_date
            and payment.datetime <= as_of_date
            and not payment.category.isdisjoint(_payment_categories)
        ]

        total_paid_on_due_date = sum((payment.amount for payment in exact_date_payments), Money.zero())

        tolerance = Money("0.01")
        if total_paid_on_due_date >= (expected_payment - tolerance):
            return True

        window_start = to_datetime(due_date - timedelta(days=3))
        window_end = min(as_of_date, to_datetime(due_date + timedelta(days=1)))

        window_payments = [
            payment
            for payment in self._all_payments
            if window_start <= payment.datetime <= window_end
            and payment.datetime <= as_of_date
            and not payment.category.isdisjoint(_payment_categories)
        ]

        total_paid_in_window = sum((payment.amount for payment in window_payments), Money.zero())

        tolerance = Money("0.01")
        return total_paid_in_window >= (expected_payment - tolerance)

    @tz_aware
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
            >>> from datetime import date
            >>>
            >>> loan = Loan(Money("10000"), InterestRate("5% annual"),
            ...            [date(2024, 1, 15), date(2024, 2, 15)])
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

        if valuation_date is None:
            valuation_date = self.now()

        # Calculate and return present value
        return present_value(expected_cf, discount_rate, valuation_date)

    def irr(self, guess: Optional[Rate] = None) -> Rate:
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
            The internal rate of return as a Rate (may be negative)

        Examples:
            >>> from money_warp import Loan, Money, InterestRate, Warp
            >>> from datetime import date
            >>>
            >>> loan = Loan(Money("10000"), InterestRate("5% annual"),
            ...            [date(2024, 1, 15), date(2024, 2, 15)])
            >>>
            >>> # Get IRR - should be close to loan's interest rate
            >>> loan_irr = loan.irr()
            >>> print(f"Loan IRR: {loan_irr}")
            >>>
            >>> # Get IRR from a specific date using Time Machine
            >>> with Warp(loan, date(2024, 1, 10)) as warped_loan:
            ...     past_irr = warped_loan.irr()
            >>> print(f"IRR from past perspective: {past_irr}")
        """
        # Import here to avoid circular import
        from ..present_value import internal_rate_of_return

        # Generate expected cash flows (will be time-aware if warped)
        expected_cf = self.generate_expected_cash_flow()

        # Calculate and return IRR
        return internal_rate_of_return(expected_cf, guess, year_size=self.interest_rate.year_size)

    def generate_expected_cash_flow(self) -> CashFlow:
        """
        Generate the expected payment schedule without fines.

        This represents the original loan terms and expected payments.
        Fines are contingent events and are not included in the expected cash flow.
        Use get_actual_cash_flow() to see what actually happened, including fines.

        When taxes are present on a non-grossed-up loan, the full principal is
        the disbursement entry and the tax appears as a separate outflow, so the
        day-0 net equals net_disbursement.  For grossed-up loans the tax is
        already absorbed into the higher principal, so only net_disbursement
        (= requested amount) is emitted with no separate tax entry.

        Returns:
            CashFlow with loan disbursement and expected payment schedule
        """
        items = []
        ctx = self._time_ctx
        expected = CashFlowType.EXPECTED

        total_tax = self.total_tax
        if total_tax.is_positive() and self.is_grossed_up:
            items.append(
                CashFlowItem(
                    self.net_disbursement,
                    self.disbursement_date,
                    "Loan disbursement",
                    "disbursement",
                    kind=expected,
                    time_context=ctx,
                )
            )
        elif total_tax.is_positive():
            items.append(
                CashFlowItem(
                    self.principal,
                    self.disbursement_date,
                    "Loan disbursement",
                    "disbursement",
                    kind=expected,
                    time_context=ctx,
                )
            )
            items.append(
                CashFlowItem(
                    Money(-total_tax.raw_amount),
                    self.disbursement_date,
                    "Tax deducted at disbursement",
                    "tax",
                    kind=expected,
                    time_context=ctx,
                )
            )
        else:
            items.append(
                CashFlowItem(
                    self.principal,
                    self.disbursement_date,
                    "Loan disbursement",
                    "disbursement",
                    kind=expected,
                    time_context=ctx,
                )
            )

        schedule = self.get_original_schedule()

        for entry in schedule:
            due_dt = to_datetime(entry.due_date)
            items.append(
                CashFlowItem(
                    Money(-entry.interest_payment.raw_amount),
                    due_dt,
                    f"Interest payment {entry.payment_number}",
                    "interest",
                    kind=expected,
                    time_context=ctx,
                )
            )
            items.append(
                CashFlowItem(
                    Money(-entry.principal_payment.raw_amount),
                    due_dt,
                    f"Principal payment {entry.payment_number}",
                    "principal",
                    kind=expected,
                    time_context=ctx,
                )
            )

        return CashFlow(items)

    def _compute_interest_snapshot(self, payment_date: datetime, interest_date: datetime) -> tuple:
        """
        Snapshot interest parameters before mutating _all_payments.

        Returns (days, principal_balance, last_pay_date) where days is the
        accrual period from the last payment to interest_date, principal_balance
        is the outstanding principal as of payment_date, and last_pay_date is
        the date of the most recent prior payment (or disbursement_date).
        """
        prior_items = [p for p in self._all_payments if p.datetime <= payment_date]
        last_pay_date = prior_items[-1].datetime if prior_items else self.disbursement_date
        days = (interest_date.date() - last_pay_date.date()).days

        principal_balance = self.principal
        for p in self._all_payments:
            if p.datetime <= payment_date and "principal" in p.category:
                principal_balance = principal_balance - p.amount
        if principal_balance.is_negative():
            principal_balance = Money.zero()

        return days, principal_balance, last_pay_date

    def _compute_accrued_interest(
        self,
        days: int,
        principal_balance: Money,
        due_date: Optional[date],
        last_payment_date: Optional[datetime],
    ) -> tuple:
        """Delegate to InterestCalculator."""
        return self._interest.compute_accrued_interest(days, principal_balance, due_date, last_payment_date)

    def _allocate_payment(
        self,
        amount: Money,
        payment_date: datetime,
        days: int,
        principal_balance: Money,
        description: Optional[str],
        due_date: Optional[date] = None,
        last_payment_date: Optional[datetime] = None,
    ) -> tuple:
        """
        Allocate a payment across fines, interest, mora interest, and principal.

        Returns (fine_paid, interest_paid, mora_paid, principal_paid).
        Appends CashFlowItems to _all_payments as a side effect.
        """
        remaining = amount
        label = description or f"Payment on {payment_date.date()}"

        fine_paid = Money.zero()
        current_fines = self.fine_balance
        if current_fines.is_positive() and remaining.is_positive():
            fine_paid = Money(min(current_fines.raw_amount, remaining.raw_amount))
            self._all_payments.append(
                CashFlowItem(fine_paid, payment_date, f"Fine payment - {label}", "fine", time_context=self._time_ctx)
            )
            remaining = remaining - fine_paid

        interest_paid = Money.zero()
        mora_paid = Money.zero()
        if remaining.is_positive() and principal_balance.is_positive() and days > 0:
            regular_accrued, mora_accrued = self._compute_accrued_interest(
                days,
                principal_balance,
                due_date,
                last_payment_date,
            )
            total_accrued = regular_accrued + mora_accrued
            total_interest_to_pay = Money(min(total_accrued.raw_amount, remaining.raw_amount))

            if total_interest_to_pay.is_positive():
                if total_interest_to_pay >= total_accrued:
                    regular_amount, mora_amount = regular_accrued, mora_accrued
                else:
                    regular_amount = Money(min(regular_accrued.raw_amount, total_interest_to_pay.raw_amount))
                    mora_amount = total_interest_to_pay - regular_amount

                if regular_amount.is_positive():
                    self._all_payments.append(
                        CashFlowItem(
                            regular_amount,
                            payment_date,
                            f"Interest portion - {label}",
                            "interest",
                            time_context=self._time_ctx,
                        )
                    )
                    interest_paid = regular_amount

                if mora_amount.is_positive():
                    self._all_payments.append(
                        CashFlowItem(
                            mora_amount,
                            payment_date,
                            f"Mora interest - {label}",
                            "mora_interest",
                            time_context=self._time_ctx,
                        )
                    )
                    mora_paid = mora_amount

                remaining = remaining - interest_paid - mora_paid

        principal_paid = Money.zero()
        if remaining.is_positive():
            principal_paid = remaining
            self._all_payments.append(
                CashFlowItem(
                    principal_paid,
                    payment_date,
                    f"Principal portion - {label}",
                    "principal",
                    time_context=self._time_ctx,
                )
            )

        return fine_paid, interest_paid, mora_paid, principal_paid

    @tz_aware
    def record_payment(
        self,
        amount: Money,
        payment_date: datetime,
        interest_date: Optional[datetime] = None,
        processing_date: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> Settlement:
        """
        Record an actual payment made on the loan with automatic allocation.

        Payment allocation priority: Fines -> Interest -> Principal

        Args:
            amount: Total payment amount (positive value)
            payment_date: When the money moved
            interest_date: Cutoff date for interest accrual calculation.
                Defaults to payment_date (borrower gets discount for early payment).
            processing_date: When the system recorded the event (audit trail).
                Defaults to self.now().
            description: Optional description of the payment

        Returns:
            Settlement describing how the payment was allocated.
        """
        if amount.is_negative() or amount.is_zero():
            raise ValueError("Payment amount must be positive")

        if interest_date is None:
            interest_date = payment_date
        if processing_date is None:
            processing_date = self.now()

        self.calculate_late_fines(payment_date)

        days, principal_balance, last_pay_date = self._compute_interest_snapshot(payment_date, interest_date)

        try:
            next_due = self._next_unpaid_due_date()
        except ValueError:
            next_due = None

        self._payment_item_offsets.append(len(self._all_payments))

        fine_paid, interest_paid, mora_paid, principal_paid = self._allocate_payment(
            amount,
            payment_date,
            days,
            principal_balance,
            description,
            due_date=next_due,
            last_payment_date=last_pay_date,
        )

        ending_balance = principal_balance - principal_paid
        if ending_balance.is_negative():
            ending_balance = Money.zero()

        payment_number = len(self._actual_schedule_entries) + 1
        self._actual_payment_datetimes.append(payment_date)
        self._actual_schedule_entries.append(
            PaymentScheduleEntry(
                payment_number=payment_number,
                due_date=payment_date.date(),
                days_in_period=days,
                beginning_balance=principal_balance,
                payment_amount=amount - fine_paid,
                principal_payment=principal_paid,
                interest_payment=interest_paid + mora_paid,
                ending_balance=ending_balance,
            )
        )

        allocs_by_number: Dict[int, List[SettlementAllocation]] = {}
        for i in range(payment_number - 1):
            prev = self._compute_settlement(i, allocs_by_number)
            for a in prev.allocations:
                allocs_by_number.setdefault(a.installment_number, []).append(a)

        return self._compute_settlement(payment_number - 1, allocs_by_number)

    def pay_installment(self, amount: Money, description: Optional[str] = None) -> Settlement:
        """
        Pay the next installment.

        Interest accrual depends on timing relative to the due date:
        - Early/on-time: interest accrues up to the due date (no discount).
        - Late: interest accrues up to self.now(), so the borrower pays extra
          interest for the additional days beyond the due date.

        This is the most common payment method and works correctly whether the
        borrower pays early, on time, or late.

        Args:
            amount: Total payment amount (positive value)
            description: Optional description of the payment

        Returns:
            Settlement describing how the payment was allocated.
        """
        payment_date = self.now()
        next_due = self._next_unpaid_due_date()
        interest_date = max(payment_date, to_datetime(next_due))
        return self.record_payment(
            amount,
            payment_date=payment_date,
            interest_date=interest_date,
            description=description,
        )

    def anticipate_payment(
        self,
        amount: Money,
        installments: Optional[List[int]] = None,
        description: Optional[str] = None,
    ) -> Settlement:
        """Make an early payment with interest discount.

        Interest is calculated only up to ``self.now()``, so the borrower
        pays less interest for fewer elapsed days.

        When *installments* is provided (1-based installment numbers),
        the corresponding expected cash-flow items are temporally
        deleted so that ``due_dates`` and future schedules no longer
        include them.

        Args:
            amount: Total payment amount (positive value).
            installments: Optional 1-based installment numbers to remove.
            description: Optional description of the payment.

        Returns:
            Settlement describing how the payment was allocated.
        """
        payment_date = self.now()

        if installments is not None:
            self._delete_expected_items_for(installments, payment_date)

        return self.record_payment(
            amount,
            payment_date=payment_date,
            interest_date=payment_date,
            description=description,
        )

    def calculate_anticipation(self, installments: List[int]) -> AnticipationResult:
        """Calculate the amount to pay today to eliminate specific installments.

        Pure calculation — no side effects on the loan.

        The maths:
            sustainable_balance = PV(kept payments at kept dates)
            anticipation_amount = current_balance - sustainable_balance

        Args:
            installments: 1-based installment numbers to anticipate.

        Returns:
            :class:`AnticipationResult` with the amount and the
            installment objects being removed.

        Raises:
            ValueError: If any number is invalid or already paid.
        """
        from ..present_value import present_value

        original = self.get_original_schedule()
        covered = self._covered_due_date_count()
        total_installments = len(original)

        removed_set = set(installments)
        for num in removed_set:
            if num < 1 or num > total_installments:
                raise ValueError(f"Installment {num} is out of range (1..{total_installments})")
            if num <= covered:
                raise ValueError(f"Installment {num} is already paid")

        kept_items: List[CashFlowItem] = []
        anticipated_installments: List[Installment] = []
        all_installments = self.installments

        for entry in original:
            if entry.payment_number in removed_set:
                anticipated_installments.append(all_installments[entry.payment_number - 1])
                continue
            if entry.payment_number <= covered:
                continue
            kept_items.append(
                CashFlowItem(
                    Money(-entry.payment_amount.raw_amount),
                    to_datetime(entry.due_date),
                    f"Kept payment {entry.payment_number}",
                    "kept_payment",
                )
            )

        if not kept_items:
            return AnticipationResult(
                amount=self.current_balance,
                installments=anticipated_installments,
            )

        kept_cf = CashFlow(kept_items)
        valuation_date = self.now()
        sustainable_balance = present_value(kept_cf, self.interest_rate, valuation_date)
        sustainable_balance = Money(-sustainable_balance.raw_amount)

        anticipation_amount = self.current_balance - sustainable_balance
        if anticipation_amount.is_negative():
            anticipation_amount = Money.zero()

        return AnticipationResult(
            amount=anticipation_amount,
            installments=anticipated_installments,
        )

    def _delete_expected_items_for(self, installments: List[int], effective_date: datetime) -> None:
        """Temporally delete expected cash-flow items for the given installments.

        Scans the expected cash flow for ``expected_interest`` and
        ``expected_principal`` items whose payment number matches one of
        the requested installments and calls ``delete(effective_date)``
        on their underlying :class:`CashFlowItem` containers.
        """
        expected_cf = self.generate_expected_cash_flow()
        removed_set = set(installments)

        for item in expected_cf.raw_items():
            entry = item.resolve()
            if entry is None:
                continue
            if entry.category.isdisjoint({"interest", "principal"}):
                continue
            desc = entry.description or ""
            for num in removed_set:
                if desc.endswith(f" {num}"):
                    item.delete(effective_date)
                    break

    def _extract_payment_items(self, entry_index: int) -> Dict[str, Money]:
        """Extract fine/interest/mora/principal from _all_payments for a given payment event.

        Each record_payment call records its starting offset in
        _payment_item_offsets, so we slice _all_payments directly by position
        rather than relying on datetime boundaries.
        """
        categories = ("fine", "interest", "mora_interest", "principal")
        result: Dict[str, Money] = {c: Money.zero() for c in categories}

        start = self._payment_item_offsets[entry_index]
        end = (
            self._payment_item_offsets[entry_index + 1]
            if entry_index + 1 < len(self._payment_item_offsets)
            else len(self._all_payments)
        )

        for idx in range(start, end):
            item = self._all_payments[idx]
            for cat in categories:
                if cat in item.category:
                    result[cat] = result[cat] + item.amount
                    break

        return result

    def _compute_settlement(
        self,
        entry_index: int,
        allocations_by_number: Dict[int, List[SettlementAllocation]],
    ) -> Settlement:
        """Compute a Settlement for the payment event at entry_index.

        Args:
            entry_index: Index into ``_actual_schedule_entries``.
            allocations_by_number: Per-installment allocations accumulated
                from settlements *before* this one.  Used to build the
                installment snapshot that drives per-installment allocation.
        """
        entry = self._actual_schedule_entries[entry_index]
        items = self._extract_payment_items(entry_index)

        fine_paid = items["fine"]
        interest_paid = items["interest"]
        mora_paid = items["mora_interest"]
        principal_paid = items["principal"]
        payment_amount = fine_paid + interest_paid + mora_paid + principal_paid

        last_pay_date = self.disbursement_date if entry_index == 0 else self._actual_payment_datetimes[entry_index - 1]

        payment_dt = self._actual_payment_datetimes[entry_index]
        installments = self._build_installments_snapshot(
            allocations_by_number,
            entry.beginning_balance,
            payment_dt,
            last_pay_date,
        )
        allocations = self._build_settlement_allocations(
            installments,
            fine_paid,
            mora_paid,
            interest_paid,
            principal_paid,
            entry.ending_balance,
        )

        return Settlement(
            payment_amount=payment_amount,
            payment_date=payment_dt,
            fine_paid=fine_paid,
            interest_paid=interest_paid,
            mora_paid=mora_paid,
            principal_paid=principal_paid,
            remaining_balance=entry.ending_balance,
            allocations=allocations,
        )

    def _build_settlement_allocations(
        self,
        installments: List[Installment],
        fine_paid: Money,
        mora_paid: Money,
        interest_paid: Money,
        principal_paid: Money,
        ending_balance: Money,
    ) -> List[SettlementAllocation]:
        """Distribute a payment's components across installments.

        Each component (fine, mora, interest, principal) is distributed
        as a separate pool.  Iterates through all installments in order;
        fully-paid installments consume nothing and are skipped.

        When the loan is fully paid off (ending_balance ≈ 0), installments
        whose principal is fully covered are marked ``is_fully_covered``
        even if their interest/mora wasn't allocated from this payment.
        """
        loan_fully_paid = ending_balance <= self._COVERAGE_TOLERANCE
        remaining_fine = fine_paid
        remaining_mora = mora_paid
        remaining_interest = interest_paid
        remaining_principal = principal_paid

        allocations: List[SettlementAllocation] = []
        for inst in installments:
            if (
                remaining_fine.is_zero()
                and remaining_mora.is_zero()
                and remaining_interest.is_zero()
                and remaining_principal.is_zero()
            ):
                break

            allocation, remaining_fine, remaining_mora, remaining_interest, remaining_principal = inst.allocate(
                remaining_fine,
                remaining_mora,
                remaining_interest,
                remaining_principal,
            )
            total = (
                allocation.principal_allocated
                + allocation.interest_allocated
                + allocation.mora_allocated
                + allocation.fine_allocated
            )
            if not total.is_positive():
                continue

            if loan_fully_paid and not allocation.is_fully_covered:
                principal_owed = inst.expected_principal - inst.principal_paid
                if allocation.principal_allocated >= (principal_owed - self._COVERAGE_TOLERANCE):
                    allocation = SettlementAllocation(
                        installment_number=allocation.installment_number,
                        principal_allocated=allocation.principal_allocated,
                        interest_allocated=allocation.interest_allocated,
                        mora_allocated=allocation.mora_allocated,
                        fine_allocated=allocation.fine_allocated,
                        is_fully_covered=True,
                    )

            allocations.append(allocation)

        return allocations

    @property
    def settlements(self) -> List[Settlement]:
        """All settlements made on this loan, reconstructed from the cash flow.

        Warp-aware: only includes settlements whose payment_date is at or
        before self.now().
        """
        current_time = self.now()
        allocs_by_number: Dict[int, List[SettlementAllocation]] = {}
        result: List[Settlement] = []
        for i, _entry in enumerate(self._actual_schedule_entries):
            if self._actual_payment_datetimes[i] > current_time:
                break
            settlement = self._compute_settlement(i, allocs_by_number)
            for a in settlement.allocations:
                allocs_by_number.setdefault(a.installment_number, []).append(a)
            result.append(settlement)
        return result

    def _covered_count_for_balance(self, remaining: Money) -> int:
        """How many due dates are covered given a remaining principal balance."""
        original = self.get_original_schedule()
        covered = 0
        for entry in original:
            if remaining <= entry.ending_balance + self._COVERAGE_TOLERANCE:
                covered += 1
            else:
                break
        return covered

    def _build_installments_snapshot(
        self,
        allocations_by_number: Dict[int, List[SettlementAllocation]],
        principal_balance: Money,
        as_of_date: datetime,
        last_payment_date: Optional[datetime] = None,
    ) -> List[Installment]:
        """Build Installment objects from pre-computed allocation data.

        Unlike the ``installments`` property, this does NOT query
        ``self.settlements`` — avoiding the circular dependency when
        called from ``_build_settlement_allocations``.

        Args:
            allocations_by_number: Per-installment allocations accumulated so far.
            principal_balance: Outstanding principal at the point in time.
            as_of_date: Reference date for mora computation.
            last_payment_date: Date of the most recent prior payment (for
                compound mora).  Falls back to ``as_of_date`` when *None*.
        """
        original = self.get_original_schedule()
        covered = self._covered_count_for_balance(principal_balance)

        result: List[Installment] = []
        for i, entry in enumerate(original):
            installment_num = i + 1
            allocs = allocations_by_number.get(installment_num, [])

            expected_fine = self.fines_applied.get(entry.due_date, Money.zero())

            prior_mora = Money(sum(a.mora_allocated.raw_amount for a in allocs))

            if i < covered:
                expected_mora = prior_mora
            elif i == covered and entry.due_date < as_of_date.date():
                if last_payment_date is not None:
                    total_days = (as_of_date.date() - last_payment_date.date()).days
                    _, accrued_mora = self._compute_accrued_interest(
                        total_days,
                        principal_balance,
                        entry.due_date,
                        last_payment_date,
                    )
                else:
                    days_overdue = (as_of_date.date() - entry.due_date).days
                    _, accrued_mora = self._compute_accrued_interest(
                        days_overdue,
                        principal_balance,
                        entry.due_date,
                        to_datetime(entry.due_date),
                    )
                expected_mora = prior_mora + accrued_mora
            else:
                expected_mora = Money.zero()

            result.append(Installment.from_schedule_entry(entry, allocs, expected_mora, expected_fine))

        return result

    @property
    def installments(self) -> List[Installment]:
        """The repayment plan as a list of Installments.

        Built from the original schedule with actual payment allocations
        gathered from settlements. Reflects the current time context
        (Warp-aware): installments show as paid only if the corresponding
        settlements have occurred by self.now().

        Each installment carries expected_mora and expected_fine so its
        balance (and derived is_fully_paid) are self-contained.
        """
        allocations_by_number: Dict[int, List[SettlementAllocation]] = {}
        for settlement in self.settlements:
            for allocation in settlement.allocations:
                num = allocation.installment_number
                if num not in allocations_by_number:
                    allocations_by_number[num] = []
                allocations_by_number[num].append(allocation)

        return self._build_installments_snapshot(
            allocations_by_number,
            self.principal_balance,
            self.now(),
        )

    _COVERAGE_TOLERANCE = Money("0.01")

    def _covered_due_date_count(self) -> int:
        """
        Determine how many due dates have been covered by comparing the remaining
        principal against the original schedule's ending_balance milestones.

        A due date is considered covered when the remaining principal is at or below
        the ending balance that the original schedule expected after that installment.
        A small tolerance absorbs rounding differences between the schedule (which
        rounds at each step) and record_payment (which uses full precision).
        """
        if not self._actual_schedule_entries:
            return 0
        remaining = self._actual_schedule_entries[-1].ending_balance
        original = self.get_original_schedule()
        covered = 0
        for entry in original:
            if remaining <= entry.ending_balance + self._COVERAGE_TOLERANCE:
                covered += 1
            else:
                break
        return covered

    def _next_unpaid_due_date(self) -> date:
        """
        Find the next due date that hasn't been fully paid yet.

        Uses cumulative principal comparison against the original schedule
        to determine coverage, so partial payments, overpayments, and
        multiple anticipations are handled correctly.

        Returns:
            The next unpaid due date

        Raises:
            ValueError: If all due dates have been paid
        """
        covered = self._covered_due_date_count()
        if covered >= len(self.due_dates):
            raise ValueError("All due dates have been paid")
        return self.due_dates[covered]

    def get_actual_cash_flow(self) -> CashFlow:
        """
        Get the actual cash flow combining expected schedule with actual payments made.

        This shows both what was expected and what actually happened for comparison.
        Includes fine applications and fine payments.
        """
        expected_cf = self.generate_expected_cash_flow()
        items = list(expected_cf.raw_items())

        for due_date, fine_amount in self.fines_applied.items():
            items.append(
                CashFlowItem(
                    fine_amount,
                    to_datetime(due_date + timedelta(days=self.grace_period_days + 1)),
                    f"Late payment fine applied for {due_date}",
                    "fine",
                    time_context=self._time_ctx,
                )
            )

        for payment in self._actual_payments:
            items.append(
                CashFlowItem(
                    -payment.amount,
                    payment.datetime,
                    payment.description or f"Actual payment on {payment.datetime.date()}",
                    payment.category,
                    time_context=self._time_ctx,
                )
            )

        return CashFlow(items)

    def get_original_schedule(self) -> PaymentSchedule:
        """
        Get the original amortization schedule as calculated at loan origination.

        This always returns the static schedule based on the original loan terms,
        ignoring any payments that have been made.

        Returns:
            PaymentSchedule based on original loan parameters
        """
        return self.scheduler.generate_schedule(
            self.principal, self.interest_rate, self.due_dates, self.disbursement_date
        )

    def get_amortization_schedule(self) -> PaymentSchedule:
        """
        Get the current amortization schedule merging actual past with projected future.

        Returns a clean, ordered list: recorded payment entries first, then
        projected entries recalculated from the remaining principal and
        remaining due dates with a new PMT.

        If no payments have been made, returns the original schedule.

        Returns:
            PaymentSchedule with past entries followed by projected future entries
        """
        if not self._actual_schedule_entries:
            return self.get_original_schedule()

        actual_entries = list(self._actual_schedule_entries)
        covered = self._covered_due_date_count()

        remaining_due_dates = self.due_dates[covered:]
        if not remaining_due_dates:
            return PaymentSchedule(entries=actual_entries)

        remaining_principal = actual_entries[-1].ending_balance
        if remaining_principal.is_zero() or remaining_principal.is_negative():
            return PaymentSchedule(entries=actual_entries)

        last_payment_date = self._actual_payment_datetimes[-1]
        projected_schedule = self.scheduler.generate_schedule(
            remaining_principal,
            self.interest_rate,
            remaining_due_dates,
            last_payment_date,
        )

        projected_entries = []
        for entry in projected_schedule:
            projected_entries.append(
                PaymentScheduleEntry(
                    payment_number=len(actual_entries) + entry.payment_number,
                    due_date=entry.due_date,
                    days_in_period=entry.days_in_period,
                    beginning_balance=entry.beginning_balance,
                    payment_amount=entry.payment_amount,
                    principal_payment=entry.principal_payment,
                    interest_payment=entry.interest_payment,
                    ending_balance=entry.ending_balance,
                )
            )

        return PaymentSchedule(entries=actual_entries + projected_entries)

    def __str__(self) -> str:
        """String representation of the loan."""
        fine_info = f", fines={self.fine_balance}" if self.fine_balance.is_positive() else ""
        return (
            f"Loan(principal={self.principal}, rate={self.interest_rate}, "
            f"payments={len(self.due_dates)}, balance={self.current_balance}{fine_info})"
        )

    def __repr__(self) -> str:
        """Detailed representation for debugging."""
        return (
            f"Loan(principal={self.principal!r}, interest_rate={self.interest_rate!r}, "
            f"due_dates={self.due_dates!r}, disbursement_date={self.disbursement_date!r}, "
            f"fine_rate={self.fine_rate!r}, grace_period_days={self.grace_period_days!r}, "
            f"mora_interest_rate={self.mora_interest_rate!r}, mora_strategy={self.mora_strategy!r})"
        )
