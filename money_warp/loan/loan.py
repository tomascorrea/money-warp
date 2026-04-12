"""Loan class -- everything emerges from the CashFlow."""

import warnings
from datetime import date, datetime
from typing import Dict, List, Optional, Type

from ..cash_flow import CashFlow, CashFlowItem, CashFlowType
from ..engines import (
    InterestCalculator,
    LoanState,
    MoraStrategy,
    apply_tolerance_adjustment,
    build_installments,
    compute_state,
    covered_due_date_count,
    is_payment_late,
)
from ..interest_rate import InterestRate
from ..money import Money
from ..rate import Rate
from ..scheduler import BaseScheduler, PaymentSchedule, PaymentScheduleEntry, PriceScheduler
from ..tax.base import BaseTax, TaxResult
from ..time_context import TimeContext
from ..tz import to_datetime, tz_aware
from .installment import Installment
from .settlement import AnticipationResult, Settlement
from .tvm import loan_calculate_anticipation, loan_irr, loan_present_value


class Loan:
    """Represents a personal loan where everything emerges from the CashFlow.

    The CashFlow is the single source of truth. Expected items (the
    amortization schedule) and actual payments both live in one CashFlow.
    Settlements, installment views, balances, and fines are all derived
    on demand -- nothing is decomposed or stored at payment time.

    Payment allocation priority: Fine -> Mora Interest -> Interest -> Principal.
    Installment 1 is fully addressed before installment 2.

    Examples:
        >>> from money_warp import Loan, Money, InterestRate
        >>> from datetime import date, datetime
        >>>
        >>> loan = Loan(
        ...     Money("10000"),
        ...     InterestRate("5% annual"),
        ...     [date(2024, 2, 1), date(2024, 3, 1)]
        ... )
        >>>
        >>> loan.record_payment(Money("500"), datetime(2024, 2, 1))
        >>> print(f"Balance: {loan.current_balance}")
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
        payment_tolerance: Optional[Money] = None,
    ) -> None:
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
        self.payment_tolerance = payment_tolerance if payment_tolerance is not None else Money("0.01")
        self.taxes: List[BaseTax] = taxes or []
        self.is_grossed_up = is_grossed_up
        self._tax_cache: Optional[Dict[str, TaxResult]] = None
        self._fine_observation_dates: List[datetime] = []

        self.cashflow = self._build_initial_cashflow()

    # ------------------------------------------------------------------
    # CashFlow construction
    # ------------------------------------------------------------------

    def _build_initial_cashflow(self) -> CashFlow:
        """Build the initial CashFlow with expected items from the schedule."""
        items: List[CashFlowItem] = []
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

    # ------------------------------------------------------------------
    # Payment recording
    # ------------------------------------------------------------------

    @tz_aware
    def record_payment(
        self,
        amount: Money,
        payment_date: datetime,
        interest_date: Optional[datetime] = None,
        processing_date: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> Settlement:
        """Record a payment. Just one CashFlowItem -- everything else is derived.

        Args:
            amount: Total payment amount (positive value).
            payment_date: When the money moved.
            interest_date: Cutoff date for interest accrual calculation.
                Defaults to payment_date.
            processing_date: Unused, kept for API compatibility.
            description: Optional description of the payment.

        Returns:
            Settlement describing how the payment was allocated.
        """
        if amount.is_negative() or amount.is_zero():
            raise ValueError("Payment amount must be positive")

        if interest_date is None:
            interest_date = payment_date

        self.cashflow.add_item(
            CashFlowItem(
                amount,
                payment_date,
                description or f"Payment on {payment_date.date()}",
                "payment",
                time_context=self._time_ctx,
                interest_date=interest_date,
            )
        )

        return self.settlements[-1]

    def pay_installment(self, amount: Money, description: Optional[str] = None) -> Settlement:
        """Pay the next installment.

        Interest accrual depends on timing:
        - Early/on-time: interest accrues up to the due date.
        - Late: interest accrues up to self.now().

        When all installments are already paid the payment is recorded
        as an overpayment (no interest accrual) and a warning is issued.

        After recording the payment, if the principal balance drifts from
        the schedule's expected ending balance by a small amount (within
        ``payment_tolerance``), a tolerance adjustment CashFlowItem is
        added to the cashflow to prevent rounding drift from compounding.
        """
        payment_date = self.now()

        if self._covered_due_date_count() >= len(self.due_dates):
            warnings.warn(
                f"All installments already paid. Recording {amount} as overpayment.",
                stacklevel=2,
            )
            return self.record_payment(
                amount,
                payment_date=payment_date,
                interest_date=payment_date,
                description=description or "Overpayment",
            )

        next_due = self._next_unpaid_due_date()
        interest_date = max(payment_date, to_datetime(next_due))
        settlement = self.record_payment(
            amount,
            payment_date=payment_date,
            interest_date=interest_date,
            description=description,
        )

        schedule = self.get_original_schedule()
        for entry in schedule:
            if entry.due_date == next_due:
                apply_tolerance_adjustment(
                    self.cashflow,
                    entry,
                    settlement,
                    payment_date,
                    interest_date,
                    self.payment_tolerance,
                    len(self.due_dates),
                    self._time_ctx,
                )
                break

        return settlement

    def anticipate_payment(
        self,
        amount: Money,
        installments: Optional[List[int]] = None,
        description: Optional[str] = None,
    ) -> Settlement:
        """Make an early payment with interest discount.

        Interest is calculated only up to self.now(), so the borrower
        pays less interest for fewer elapsed days.

        When *installments* is provided (1-based), the corresponding
        expected cash-flow items are temporally deleted.
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
        """Temporally delete expected cash-flow items for the given installments."""
        removed_set = set(installments)
        for item in self.cashflow.raw_items():
            entry = item.resolve()
            if entry is None or entry.kind != CashFlowType.EXPECTED:
                continue
            if entry.category.isdisjoint({"interest", "principal"}):
                continue
            desc = entry.description or ""
            for num in removed_set:
                if desc.endswith(f" {num}"):
                    item.delete(effective_date)
                    break

    # ------------------------------------------------------------------
    # Derived state (computed from CashFlow)
    # ------------------------------------------------------------------

    def _compute_state(self) -> LoanState:
        """Run the forward pass over all payments to derive loan state."""
        return compute_state(
            self.principal,
            self._interest,
            self.get_original_schedule(),
            self.due_dates,
            self.fine_rate,
            self.grace_period_days,
            self.disbursement_date,
            self._payment_entries(),
            self.now(),
            fine_observation_dates=self._fine_observation_dates,
        )

    def _payment_entries(self) -> list:
        """Payment CashFlowEntry objects from the cashflow, sorted by datetime."""
        entries = [e for e in self.cashflow.items() if "payment" in e.category]
        return sorted(entries, key=lambda e: e.datetime)

    # ------------------------------------------------------------------
    # Settlements and installments
    # ------------------------------------------------------------------

    @property
    def settlements(self) -> List[Settlement]:
        """All settlements (derived from CashFlow)."""
        return self._compute_state().settlements

    @property
    def installments(self) -> List[Installment]:
        """The repayment plan as Installment objects (derived from CashFlow)."""
        state = self._compute_state()
        return build_installments(
            self.get_original_schedule(),
            state.settlements,
            state.fines_applied,
            state.principal_balance,
            self.now(),
            self._interest,
            state.last_accrual_end,
        )

    # ------------------------------------------------------------------
    # Balance properties
    # ------------------------------------------------------------------

    @property
    def principal_balance(self) -> Money:
        """Outstanding principal (derived from CashFlow)."""
        return self._compute_state().principal_balance

    def _accrued_interest_components(self) -> tuple:
        """Return (regular, mora) accrued interest since last payment."""
        state = self._compute_state()
        days = (self.now().date() - state.last_accrual_end.date()).days

        if state.principal_balance.is_positive() and days > 0:
            covered = covered_due_date_count(state.principal_balance, self.get_original_schedule())
            next_due = self.due_dates[covered] if covered < len(self.due_dates) else None
            return self._interest.compute_accrued_interest(
                days,
                state.principal_balance,
                next_due,
                state.last_accrual_end,
            )

        return Money.zero(), Money.zero()

    @property
    def interest_balance(self) -> Money:
        """Regular (non-mora) accrued interest since last payment."""
        return self._accrued_interest_components()[0]

    @property
    def mora_interest_balance(self) -> Money:
        """Mora accrued interest since last payment."""
        return self._accrued_interest_components()[1]

    @property
    def fine_balance(self) -> Money:
        """Unpaid fine amount (derived from CashFlow)."""
        state = self._compute_state()
        total_fines = (
            Money(sum(f.raw_amount for f in state.fines_applied.values())) if state.fines_applied else Money.zero()
        )
        outstanding = total_fines - state.fines_paid_total
        return outstanding if outstanding.is_positive() else Money.zero()

    @property
    def current_balance(self) -> Money:
        """Total outstanding balance (principal + interest + mora + fines)."""
        return self.principal_balance + self.interest_balance + self.mora_interest_balance + self.fine_balance

    @property
    def is_paid_off(self) -> bool:
        """Whether the loan is fully paid off."""
        return self.current_balance.is_zero() or self.current_balance.is_negative()

    @property
    def overpaid(self) -> Money:
        """Total amount paid beyond the loan's obligations (derived from CashFlow)."""
        return self._compute_state().overpaid

    # ------------------------------------------------------------------
    # Fine-related properties and methods
    # ------------------------------------------------------------------

    @property
    def fines_applied(self) -> Dict[date, Money]:
        """Fine amounts applied per due date (derived from CashFlow)."""
        return self._compute_state().fines_applied

    @fines_applied.setter
    def fines_applied(self, value: Dict[date, Money]) -> None:
        pass

    @property
    def total_fines(self) -> Money:
        """Total amount of fines applied."""
        fines = self.fines_applied
        if not fines:
            return Money.zero()
        return Money(sum(f.raw_amount for f in fines.values()))

    @tz_aware
    def is_payment_late(self, due_date: date, as_of_date: Optional[datetime] = None) -> bool:
        """Check if a payment is late considering the grace period."""
        check = as_of_date if as_of_date is not None else self.now()
        return is_payment_late(due_date, self.grace_period_days, check)

    def _on_warp(self, target_date: datetime) -> None:
        """Hook called by Warp after overriding TimeContext."""
        self._fine_observation_dates.append(target_date)

    def calculate_late_fines(self, as_of_date: Optional[datetime] = None) -> Money:
        """Compute and record fine observations as of a date.

        Appends the observation date so that subsequent property queries
        include fines for due dates overdue at that point.

        Returns the amount of NEW fines applied (zero if already applied).
        """
        as_of = as_of_date if as_of_date is not None else self.now()
        old_total = self.total_fines
        self._fine_observation_dates.append(as_of)
        new_total = self.total_fines
        return new_total - old_total

    # ------------------------------------------------------------------
    # Payment info
    # ------------------------------------------------------------------

    @property
    def last_payment_date(self) -> datetime:
        """Date of the last payment, or disbursement date if none."""
        return self._compute_state().last_payment_date

    def now(self) -> datetime:
        """Current datetime (Warp-aware via shared TimeContext)."""
        return self._time_ctx.now()

    def days_since_last_payment(self) -> int:
        """Days since the last payment (Warp-aware)."""
        return (self.now().date() - self.last_payment_date.date()).days

    def _covered_due_date_count(self) -> int:
        """How many due dates have been covered by payments."""
        return covered_due_date_count(self.principal_balance, self.get_original_schedule())

    def _next_unpaid_due_date(self) -> date:
        """Find the next due date that hasn't been fully paid.

        Raises:
            ValueError: If all due dates have been paid.
        """
        covered = self._covered_due_date_count()
        if covered >= len(self.due_dates):
            raise ValueError("All due dates have been paid")
        return self.due_dates[covered]

    # ------------------------------------------------------------------
    # Taxes
    # ------------------------------------------------------------------

    @property
    def tax_amounts(self) -> Dict[str, TaxResult]:
        """Per-tax results keyed by tax class name. Computed lazily."""
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

    def get_expected_payment_amount(self, due_date: date) -> Money:
        """Get the expected payment amount for a specific due date."""
        schedule = self.get_original_schedule()
        for entry in schedule:
            if entry.due_date == due_date:
                return entry.payment_amount
        raise ValueError(f"Due date {due_date} is not in loan's due dates")

    # ------------------------------------------------------------------
    # Schedule
    # ------------------------------------------------------------------

    def get_original_schedule(self) -> PaymentSchedule:
        """The original amortization schedule (static, ignores payments)."""
        return self.scheduler.generate_schedule(
            self.principal,
            self.interest_rate,
            self.due_dates,
            self.disbursement_date,
        )

    def get_amortization_schedule(self) -> PaymentSchedule:
        """Current schedule: recorded past entries + projected future."""
        state = self._compute_state()
        if not state.settlements:
            return self.get_original_schedule()

        actual_entries: List[PaymentScheduleEntry] = []
        prev_balance = self.principal
        prev_date = self.disbursement_date

        for i, s in enumerate(state.settlements):
            days = (s.payment_date.date() - prev_date.date()).days
            actual_entries.append(
                PaymentScheduleEntry(
                    payment_number=i + 1,
                    due_date=s.payment_date.date(),
                    days_in_period=days,
                    beginning_balance=prev_balance,
                    payment_amount=s.interest_paid + s.mora_paid + s.principal_paid,
                    principal_payment=s.principal_paid,
                    interest_payment=s.interest_paid + s.mora_paid,
                    ending_balance=s.remaining_balance,
                )
            )
            prev_balance = s.remaining_balance
            prev_date = s.payment_date

        covered = covered_due_date_count(state.principal_balance, self.get_original_schedule())
        remaining_due_dates = self.due_dates[covered:]
        if not remaining_due_dates:
            return PaymentSchedule(entries=actual_entries)

        if state.principal_balance.is_zero() or state.principal_balance.is_negative():
            return PaymentSchedule(entries=actual_entries)

        projected_schedule = self.scheduler.generate_schedule(
            state.principal_balance,
            self.interest_rate,
            remaining_due_dates,
            state.last_payment_date,
        )

        projected_entries: List[PaymentScheduleEntry] = []
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

    # ------------------------------------------------------------------
    # Cash flow views
    # ------------------------------------------------------------------

    def generate_expected_cash_flow(self) -> CashFlow:
        """Expected cash flow (schedule items only, no payments)."""
        return self.cashflow.filter_by_kind(CashFlowType.EXPECTED)

    # ------------------------------------------------------------------
    # TVM
    # ------------------------------------------------------------------

    @tz_aware
    def present_value(
        self,
        discount_rate: Optional[InterestRate] = None,
        valuation_date: Optional[datetime] = None,
    ) -> Money:
        """Present Value of the loan's expected cash flows."""
        return loan_present_value(self, discount_rate, valuation_date)

    def irr(self, guess: Optional[Rate] = None) -> Rate:
        """Internal Rate of Return of the loan's expected cash flows."""
        return loan_irr(self, guess)

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        fine_info = f", fines={self.fine_balance}" if self.fine_balance.is_positive() else ""
        return (
            f"Loan(principal={self.principal}, rate={self.interest_rate}, "
            f"payments={len(self.due_dates)}, balance={self.current_balance}{fine_info})"
        )

    def __repr__(self) -> str:
        return (
            f"Loan(principal={self.principal!r}, interest_rate={self.interest_rate!r}, "
            f"due_dates={self.due_dates!r}, disbursement_date={self.disbursement_date!r}, "
            f"fine_rate={self.fine_rate!r}, grace_period_days={self.grace_period_days!r}, "
            f"mora_interest_rate={self.mora_interest_rate!r}, mora_strategy={self.mora_strategy!r})"
        )
