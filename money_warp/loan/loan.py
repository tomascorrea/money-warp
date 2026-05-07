"""Loan class -- everything emerges from the CashFlow."""

from datetime import date, datetime, tzinfo
from typing import Dict, List, Optional, Type, Union
from zoneinfo import ZoneInfo

from ..base_loan import BaseLoan
from ..cash_flow import CashFlow, CashFlowItem, CashFlowType
from ..engines import (
    InterestCalculator,
    LoanState,
    MoraStrategy,
    compute_state,
)
from ..models import AnticipationResult, Settlement
from ..scheduler import BaseScheduler, PriceScheduler
from ..tax.base import BaseTax, TaxResult
from ..time_context import TimeContext
from ..types.interest_rate import InterestRate
from ..types.money import Money
from ..types.rate import Rate
from ..tz import ensure_aware, get_tz, tz_aware
from ..working_day import EveryDayCalendar, WorkingDayCalendar
from .tvm import loan_calculate_anticipation, loan_irr, loan_present_value


class Loan(BaseLoan):
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
        working_day_calendar: Optional[WorkingDayCalendar] = None,
        tz: Optional[Union[str, tzinfo]] = None,
    ) -> None:
        if not due_dates:
            raise ValueError("At least one due date is required")
        if principal.is_negative() or principal.is_zero():
            raise ValueError("Principal must be positive")
        if grace_period_days < 0:
            raise ValueError("Grace period days must be non-negative")

        resolved_tz = ZoneInfo(tz) if isinstance(tz, str) else (tz or get_tz())
        self._time_ctx = TimeContext(tz=resolved_tz)

        self.principal = principal
        self.interest_rate = interest_rate
        self.mora_interest_rate = mora_interest_rate or interest_rate
        self.mora_strategy = mora_strategy
        self._interest = InterestCalculator(interest_rate, self.mora_interest_rate, mora_strategy)
        self.due_dates = sorted(due_dates)
        self.disbursement_date = (
            disbursement_date if disbursement_date is not None else ensure_aware(self._time_ctx.now())
        )
        if self._time_ctx.to_date(self.disbursement_date) >= self.due_dates[0]:
            raise ValueError("disbursement_date must be before the first due date")
        self.scheduler = scheduler or PriceScheduler
        self.fine_rate = fine_rate if fine_rate is not None else InterestRate("2% annual")
        self.grace_period_days = grace_period_days
        self.payment_tolerance = payment_tolerance if payment_tolerance is not None else Money("0.01")
        self.working_day_calendar: WorkingDayCalendar = working_day_calendar or EveryDayCalendar()
        self.taxes: List[BaseTax] = taxes or []
        self.is_grossed_up = is_grossed_up
        self._tax_cache: Optional[Dict[str, TaxResult]] = None
        self._fine_observation_dates: List[datetime] = []

        self.cashflow = self._build_initial_cashflow()

    # ------------------------------------------------------------------
    # Abstract hook implementations
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
            due_dt = self._time_ctx.to_datetime(entry.due_date)
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
        waive_fines: bool = False,
        waive_mora: bool = False,
        discount: Optional[Money] = None,
    ) -> Settlement:
        """Record a payment. Just one CashFlowItem -- everything else is derived.

        Args:
            amount: Total payment amount (positive value).
            payment_date: When the money moved.
            interest_date: Cutoff date for interest accrual calculation.
                Defaults to payment_date.
            processing_date: Unused, kept for API compatibility.
            description: Optional description of the payment.
            waive_fines: If True, all accumulated fines up to this
                payment are forgiven.  Future fines can still accrue.
            waive_mora: If True, all accrued mora interest up to this
                payment is forgiven.  Future mora can still accrue.
            discount: Flat amount to forgive from obligations before
                allocating the payment.  Follows the same priority as
                payment allocation (fines -> mora -> interest -> principal).

        Returns:
            Settlement describing how the payment was allocated.
        """
        if amount.is_negative() or amount.is_zero():
            raise ValueError("Payment amount must be positive")
        if discount is not None and discount.is_negative():
            raise ValueError("Discount amount must not be negative")

        if interest_date is None:
            interest_date = payment_date

        self.cashflow.add_item(
            CashFlowItem(
                amount,
                payment_date,
                description or f"Payment on {self._time_ctx.to_date(payment_date)}",
                "payment",
                time_context=self._time_ctx,
                interest_date=interest_date,
                waive_fines=waive_fines,
                waive_mora=waive_mora,
                discount=discount,
            )
        )

        return self.settlements[-1]

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
            tz=self._time_ctx.tz,
            fine_observation_dates=self._fine_observation_dates,
            calendar=self.working_day_calendar,
        )

    # ------------------------------------------------------------------
    # Loan-specific: fines_applied setter
    # ------------------------------------------------------------------

    @BaseLoan.fines_applied.setter
    def fines_applied(self, value: Dict[date, Money]) -> None:
        pass

    # ------------------------------------------------------------------
    # Loan-specific: Anticipation
    # ------------------------------------------------------------------

    def anticipate_payment(
        self,
        amount: Money,
        installments: Optional[List[int]] = None,
        description: Optional[str] = None,
        waive_fines: bool = False,
        waive_mora: bool = False,
        discount: Optional[Money] = None,
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
            waive_fines=waive_fines,
            waive_mora=waive_mora,
            discount=discount,
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
    # Loan-specific: Taxes
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
                results[key] = tax.calculate(schedule, self.disbursement_date, self._time_ctx.tz)

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
    # Loan-specific: Cash flow views
    # ------------------------------------------------------------------

    def generate_expected_cash_flow(self) -> CashFlow:
        """Expected cash flow (schedule items only, no payments)."""
        return self.cashflow.filter_by_kind(CashFlowType.EXPECTED)

    # ------------------------------------------------------------------
    # Loan-specific: TVM
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
