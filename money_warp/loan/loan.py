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
from .engines.fine_tracker import FineTracker, _get_expected_payment
from .engines.interest_calculator import InterestCalculator, MoraStrategy
from .engines.payment_ledger import PaymentLedger
from .engines.settlement_engine import SettlementEngine
from .installment import Installment
from .settlement import AnticipationResult, Settlement, SettlementAllocation
from .tvm import loan_calculate_anticipation, loan_irr, loan_present_value


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
        self._fines = FineTracker(self.fine_rate, grace_period_days, self._time_ctx)
        self.taxes: List[BaseTax] = taxes or []
        self.is_grossed_up = is_grossed_up

        # Shared payment CashFlow — single source of truth for payment items
        self._payment_cf = CashFlow.empty()
        self._ledger = PaymentLedger(self._payment_cf, self._time_ctx)
        self._settlements_engine = SettlementEngine(self._interest)
        self._tax_cache: Optional[Dict[str, TaxResult]] = None

    @property
    def principal_balance(self) -> Money:
        """Get the current principal balance (original principal minus principal payments)."""
        return self._ledger.principal_balance(self.principal)

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
            return self._interest.compute_accrued_interest(days, principal_bal, due_date, self.last_payment_date)

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
        return self._ledger.last_payment_date(self.disbursement_date)

    @property
    def fines_applied(self) -> Dict[date, Money]:
        """Fine amounts applied per due date (delegates to FineTracker)."""
        return self._fines.fines_applied

    @fines_applied.setter
    def fines_applied(self, value: Dict[date, Money]) -> None:
        self._fines.fines_applied = value

    @property
    def total_fines(self) -> Money:
        """Get the total amount of fines applied to this loan."""
        return self._fines.total_fines

    @property
    def fine_balance(self) -> Money:
        """Unpaid fine amount (total fines applied minus fines paid)."""
        return self._fines.fine_balance(self._ledger.actual_payment_items)

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

    def _on_warp(self, target_date: datetime) -> None:
        """Hook called by Warp after overriding TimeContext."""
        self.calculate_late_fines()

    def days_since_last_payment(self) -> int:
        """Get the number of days since the last payment (Warp-aware via TimeContext)."""
        return (self.now().date() - self.last_payment_date.date()).days

    def get_expected_payment_amount(self, due_date: date) -> Money:
        """Get the expected payment amount for a specific due date from the original schedule."""
        return _get_expected_payment(due_date, self.due_dates, self.get_original_schedule())

    @tz_aware
    def is_payment_late(self, due_date: date, as_of_date: Optional[datetime] = None) -> bool:
        """Check if a payment is late considering the grace period."""
        return self._fines.is_payment_late(due_date, as_of_date)

    def calculate_late_fines(self, as_of_date: Optional[datetime] = None) -> Money:
        """Calculate and apply late payment fines for any new late payments."""
        return self._fines.calculate_late_fines(
            self.due_dates, self.get_original_schedule(), self._ledger.all_payment_items, as_of=as_of_date
        )

    @tz_aware
    def present_value(
        self, discount_rate: Optional[InterestRate] = None, valuation_date: Optional[datetime] = None
    ) -> Money:
        """Calculate the Present Value of the loan's expected cash flows."""
        return loan_present_value(self, discount_rate, valuation_date)

    def irr(self, guess: Optional[Rate] = None) -> Rate:
        """Calculate the Internal Rate of Return (IRR) of the loan's expected cash flows."""
        return loan_irr(self, guess)

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

        Payment allocation priority (per installment):
        Fine -> Mora Interest -> Interest -> Principal.
        Installment 1 is fully addressed before installment 2.

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

        days, principal_balance, last_pay_date = self._ledger.compute_interest_snapshot(
            payment_date, interest_date, self.principal, self.disbursement_date
        )

        try:
            next_due = self._next_unpaid_due_date()
        except ValueError:
            next_due = None

        interest_accrued, mora_accrued = self._interest.compute_accrued_interest(
            days, principal_balance, next_due, last_pay_date
        )

        installments = self._build_pre_settlement_installments(principal_balance, payment_date, last_pay_date)

        ending_balance = principal_balance
        fine_paid, mora_paid, interest_paid, principal_paid, _ = SettlementEngine.allocate_payment_per_installment(
            amount,
            installments,
            ending_balance,
            fine_cap=self.fine_balance,
            interest_cap=interest_accrued,
            mora_cap=mora_accrued,
        )

        settlement_num, ending_balance = self._ledger.record_allocation(
            fine_paid,
            mora_paid,
            interest_paid,
            principal_paid,
            payment_date,
            days,
            principal_balance,
            description,
        )

        allocs_by_number: Dict[int, List[SettlementAllocation]] = {}
        schedule = self.get_original_schedule()
        for i in range(settlement_num - 1):
            prev = self._settlements_engine.compute_settlement(
                i, allocs_by_number, self._ledger, schedule, self.fines_applied, self.disbursement_date
            )
            for a in prev.allocations:
                allocs_by_number.setdefault(a.installment_number, []).append(a)

        return self._settlements_engine.compute_settlement(
            settlement_num - 1, allocs_by_number, self._ledger, schedule, self.fines_applied, self.disbursement_date
        )

    def _build_pre_settlement_installments(
        self,
        principal_balance: Money,
        payment_date: datetime,
        last_payment_date: Optional[datetime],
    ) -> List[Installment]:
        """Build an installment snapshot reflecting all prior settlements.

        Called *before* a new payment is recorded so that
        :meth:`SettlementEngine.allocate_payment_per_installment` can
        determine per-installment obligations.
        """
        allocs_by_number: Dict[int, List[SettlementAllocation]] = {}
        schedule = self.get_original_schedule()
        for i in range(self._ledger.settlement_count):
            prev = self._settlements_engine.compute_settlement(
                i, allocs_by_number, self._ledger, schedule, self.fines_applied, self.disbursement_date
            )
            for a in prev.allocations:
                allocs_by_number.setdefault(a.installment_number, []).append(a)

        return self._settlements_engine.build_installments_snapshot(
            allocs_by_number,
            principal_balance,
            payment_date,
            self.get_original_schedule(),
            self.fines_applied,
            last_payment_date=last_payment_date,
        )

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
        """Calculate the amount to pay today to eliminate specific installments."""
        return loan_calculate_anticipation(self, installments)

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

    @property
    def settlements(self) -> List[Settlement]:
        """All settlements made on this loan (Warp-aware)."""
        return self._settlements_engine.all_settlements(
            self._ledger,
            self.get_original_schedule(),
            self.fines_applied,
            self.disbursement_date,
            self.now(),
        )

    @property
    def installments(self) -> List[Installment]:
        """The repayment plan as Installment objects (Warp-aware)."""
        return self._settlements_engine.all_installments(
            self.settlements,
            self.principal_balance,
            self.now(),
            self.get_original_schedule(),
            self.fines_applied,
        )

    def _covered_due_date_count(self) -> int:
        """How many due dates have been covered by payments so far."""
        snapshots = self._ledger.snapshots
        if not snapshots:
            return 0
        remaining = snapshots[-1].ending_balance
        return SettlementEngine.covered_due_date_count(remaining, self.get_original_schedule())

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

        for payment in self._ledger.actual_payment_items:
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
        if not self._ledger.actual_schedule_entries():
            return self.get_original_schedule()

        actual_entries = list(self._ledger.actual_schedule_entries())
        covered = self._covered_due_date_count()

        remaining_due_dates = self.due_dates[covered:]
        if not remaining_due_dates:
            return PaymentSchedule(entries=actual_entries)

        remaining_principal = actual_entries[-1].ending_balance
        if remaining_principal.is_zero() or remaining_principal.is_negative():
            return PaymentSchedule(entries=actual_entries)

        last_payment_date = self._ledger.actual_payment_datetimes()[-1]
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
