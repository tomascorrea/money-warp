"""BillingCycleLoan -- fixed amortization with billing-cycle payment timing."""

from datetime import date, datetime, tzinfo
from typing import List, Optional, Type, Union
from zoneinfo import ZoneInfo

from ..base_loan import BaseLoan
from ..billing_cycle import BaseBillingCycle
from ..cash_flow import CashFlow, CashFlowItem, CashFlowType
from ..engines import (
    InterestCalculator,
    LoanState,
    MoraStrategy,
)
from ..models import DEFAULT_BALANCE_TOLERANCE, BillingCycleLoanStatement, Settlement
from ..scheduler import BaseScheduler, PriceScheduler
from ..time_context import TimeContext
from ..types.interest_rate import InterestRate
from ..types.money import Money
from ..tz import ensure_aware, get_tz, tz_aware
from ..working_day import EveryDayCalendar, WorkingDayCalendar
from .engines import build_statements, compute_state, resolve_mora_rate
from .mora_rate_resolver import MoraRateResolver


class BillingCycleLoan(BaseLoan):
    """Loan with fixed amortization and credit-card-like billing cycles.

    Combines a traditional amortization schedule (Price / SAC) with
    billing-cycle timing (monthly close + due date) and a mora
    interest rate that can change per cycle via a callable resolver.

    The CashFlow is the single source of truth, just like ``Loan``.
    Settlements, installments, balances, and fines are all derived on
    demand by a forward pass.

    Args:
        principal: Loan principal amount (must be positive).
        interest_rate: Annual contractual interest rate.
        billing_cycle: Billing cycle factory that generates closing and
            due dates.
        start_date: Start of the first billing period.  Closing dates
            are generated after this date.
        num_installments: Number of installments in the amortization.
        disbursement_date: When funds are released.  Defaults to
            ``now()``.  Must be before the first due date.
        scheduler: Amortization strategy.  Defaults to
            :class:`PriceScheduler`.
        fine_rate: Rate for computing fines on missed payments.
            Defaults to ``2% annual``.
        grace_period_days: Days after due date before fines apply.
        mora_interest_rate: Base mora rate.  Defaults to
            *interest_rate*.
        mora_rate_resolver: Optional callable that adjusts the base
            mora rate per billing cycle.  Receives
            ``(closing_date, base_mora_rate)`` and returns the
            effective ``InterestRate`` for that cycle.
        mora_strategy: How mora interest compounds.  Defaults to
            :attr:`MoraStrategy.COMPOUND`.
    """

    @tz_aware
    def __init__(
        self,
        principal: Money,
        interest_rate: InterestRate,
        billing_cycle: BaseBillingCycle,
        start_date: datetime,
        num_installments: int,
        disbursement_date: Optional[datetime] = None,
        scheduler: Optional[Type[BaseScheduler]] = None,
        fine_rate: Optional[InterestRate] = None,
        grace_period_days: int = 0,
        mora_interest_rate: Optional[InterestRate] = None,
        mora_rate_resolver: Optional[MoraRateResolver] = None,
        mora_strategy: MoraStrategy = MoraStrategy.COMPOUND,
        payment_tolerance: Optional[Money] = None,
        balance_tolerance: Optional[Money] = None,
        working_day_calendar: Optional[WorkingDayCalendar] = None,
        tz: Optional[Union[str, tzinfo]] = None,
    ) -> None:
        if principal.is_negative() or principal.is_zero():
            raise ValueError("Principal must be positive")
        if num_installments < 1:
            raise ValueError("num_installments must be at least 1")
        if grace_period_days < 0:
            raise ValueError("Grace period days must be non-negative")

        resolved_tz = ZoneInfo(tz) if isinstance(tz, str) else (tz or get_tz())
        self._time_ctx = TimeContext(tz=resolved_tz)

        self.principal = principal
        self.interest_rate = interest_rate
        self.billing_cycle = billing_cycle
        self.start_date = start_date
        self.num_installments = num_installments
        self.mora_interest_rate = mora_interest_rate or interest_rate
        self.mora_rate_resolver = mora_rate_resolver
        self.mora_strategy = mora_strategy
        self.scheduler = scheduler or PriceScheduler
        self.fine_rate = fine_rate if fine_rate is not None else InterestRate("2% annual")
        self.grace_period_days = grace_period_days
        self.payment_tolerance = payment_tolerance if payment_tolerance is not None else Money("0.01")
        self.balance_tolerance = balance_tolerance if balance_tolerance is not None else DEFAULT_BALANCE_TOLERANCE
        self.working_day_calendar: WorkingDayCalendar = working_day_calendar or EveryDayCalendar()

        self._interest = InterestCalculator(
            interest_rate,
            self.mora_interest_rate,
            mora_strategy,
        )
        self._fine_observation_dates: List[datetime] = []

        self._closing_dates = self._derive_closing_dates()
        self.due_dates = self._derive_due_dates()

        self.disbursement_date = (
            disbursement_date if disbursement_date is not None else ensure_aware(self._time_ctx.now())
        )
        if self._time_ctx.to_date(self.disbursement_date) >= self.due_dates[0]:
            raise ValueError("disbursement_date must be before the first due date")

        self.cashflow = self._build_initial_cashflow()

    # ------------------------------------------------------------------
    # Date derivation (BCL-specific)
    # ------------------------------------------------------------------

    def _derive_closing_dates(self) -> List[datetime]:
        """Generate closing dates from the billing cycle.

        When explicit due dates are set on the billing cycle, each
        closing date is chosen as the latest one on or before the
        corresponding due date.  This keeps ``closing_dates[i]``
        aligned with ``due_dates[i]`` — a requirement for mora-rate
        resolution and statement building.
        """
        from dateutil.relativedelta import relativedelta

        far_end = self.start_date + relativedelta(months=self.num_installments + 2)

        explicit = self.billing_cycle.explicit_due_dates
        if explicit is not None:
            target = explicit[: self.num_installments]
            earliest_due_dt = self._time_ctx.to_datetime(target[0])
            search_start = min(self.start_date, earliest_due_dt - relativedelta(months=1))
            all_dates = self.billing_cycle.closing_dates_between(search_start, far_end)
        else:
            all_dates = self.billing_cycle.closing_dates_between(self.start_date, far_end)

        if explicit is not None:
            selected: List[datetime] = []
            for dd in target:
                match = None
                for cd in all_dates:
                    if self._time_ctx.to_date(cd) <= dd:
                        match = cd
                    else:
                        break
                if match is not None and match not in selected:
                    selected.append(match)
            if len(selected) != len(target):
                raise ValueError(
                    "Could not find a closing date for each explicit due date: "
                    f"expected {len(target)}, found {len(selected)}"
                )
            return selected

        return all_dates[: self.num_installments]

    def _derive_due_dates(self) -> List[date]:
        """Derive payment due dates from the billing cycle."""
        from dateutil.relativedelta import relativedelta

        last_closing = self._closing_dates[-1] if self._closing_dates else self.start_date
        search_end = last_closing + relativedelta(months=1)
        explicit = self.billing_cycle.due_dates_between(self.start_date, search_end, self._time_ctx.tz)
        if explicit:
            return explicit[: self.num_installments]

        return [self._time_ctx.to_date(self.billing_cycle.due_date_for(cd)) for cd in self._closing_dates]

    @property
    def closing_dates(self) -> List[datetime]:
        """Closing dates for each billing period."""
        return list(self._closing_dates)

    # ------------------------------------------------------------------
    # Abstract hook implementations
    # ------------------------------------------------------------------

    def _build_initial_cashflow(self) -> CashFlow:
        """Build the initial CashFlow with expected items from the schedule."""
        items: List[CashFlowItem] = []
        ctx = self._time_ctx
        expected = CashFlowType.EXPECTED

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
        description: Optional[str] = None,
        waive_fines: bool = False,
        waive_mora: bool = False,
        waive_overdue_interest: bool = False,
        discount: Optional[Money] = None,
    ) -> Settlement:
        """Record a payment and return the derived settlement."""
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
                waive_overdue_interest=waive_overdue_interest,
                discount=discount,
            )
        )

        return self.settlements[-1]

    def _compute_state(self) -> LoanState:
        """Run the forward pass with per-cycle mora rate resolution."""
        return compute_state(
            self.principal,
            self._interest,
            self.get_original_schedule(),
            self.due_dates,
            self._closing_dates,
            self.fine_rate,
            self.grace_period_days,
            self.disbursement_date,
            self._payment_entries(),
            self.now(),
            tz=self._time_ctx.tz,
            base_mora_rate=self.mora_interest_rate,
            mora_rate_resolver=self.mora_rate_resolver,
            fine_observation_dates=self._fine_observation_dates,
            calendar=self.working_day_calendar,
            balance_tolerance=self.balance_tolerance,
        )

    def _resolve_mora_rate_for_due(self, next_due: Optional[date]) -> Optional[InterestRate]:
        """Resolve per-cycle mora rate via the billing cycle's resolver."""
        return resolve_mora_rate(
            self.due_dates,
            self._closing_dates,
            next_due,
            self.mora_interest_rate,
            self.mora_rate_resolver,
            self._time_ctx.tz,
        )

    # ------------------------------------------------------------------
    # BCL-specific: late-check alias
    # ------------------------------------------------------------------

    def is_late(self, due_date: date, as_of_date: Optional[datetime] = None) -> bool:
        """Check if a payment is late considering the grace period."""
        return self.is_payment_late(due_date, as_of_date)

    # ------------------------------------------------------------------
    # BCL-specific: Statements
    # ------------------------------------------------------------------

    @property
    def statements(self) -> List[BillingCycleLoanStatement]:
        """Billing-period statements (one per cycle)."""
        state = self._compute_state()
        return build_statements(
            self.get_original_schedule(),
            self.due_dates,
            self._closing_dates,
            self.billing_cycle,
            state.settlements,
            state.fines_applied,
            self.principal,
            self.mora_interest_rate,
            tz=self._time_ctx.tz,
            mora_rate_resolver=self.mora_rate_resolver,
        )

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        fine_info = f", fines={self.fine_balance}" if self.fine_balance.is_positive() else ""
        return (
            f"BillingCycleLoan(principal={self.principal}, rate={self.interest_rate}, "
            f"payments={self.num_installments}, balance={self.current_balance}{fine_info})"
        )

    def __repr__(self) -> str:
        return (
            f"BillingCycleLoan(principal={self.principal!r}, "
            f"interest_rate={self.interest_rate!r}, "
            f"billing_cycle={self.billing_cycle!r}, "
            f"num_installments={self.num_installments!r}, "
            f"mora_interest_rate={self.mora_interest_rate!r}, "
            f"mora_strategy={self.mora_strategy!r})"
        )
