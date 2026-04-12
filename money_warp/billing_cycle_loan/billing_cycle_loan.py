"""BillingCycleLoan -- fixed amortization with billing-cycle payment timing."""

import warnings
from datetime import date, datetime, tzinfo
from typing import Dict, List, Optional, Type, Union
from zoneinfo import ZoneInfo

from ..billing_cycle import BaseBillingCycle
from ..cash_flow import CashFlow, CashFlowItem, CashFlowType
from ..engines import (
    InterestCalculator,
    LoanState,
    MoraStrategy,
    apply_tolerance_adjustment,
    build_installments,
    covered_due_date_count,
    is_payment_late,
)
from ..interest_rate import InterestRate
from ..models import BillingCycleLoanStatement, Installment, Settlement
from ..money import Money
from ..scheduler import BaseScheduler, PaymentSchedule, PaymentScheduleEntry, PriceScheduler
from ..time_context import TimeContext
from ..tz import ensure_aware, get_tz, tz_aware
from .engines import build_statements, compute_state, resolve_mora_rate
from .mora_rate_resolver import MoraRateResolver


class BillingCycleLoan:
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
    # Date derivation
    # ------------------------------------------------------------------

    def _derive_closing_dates(self) -> List[datetime]:
        """Generate closing dates from the billing cycle."""
        from dateutil.relativedelta import relativedelta

        far_end = self.start_date + relativedelta(months=self.num_installments + 2)
        all_dates = self.billing_cycle.closing_dates_between(self.start_date, far_end)
        return all_dates[: self.num_installments]

    def _derive_due_dates(self) -> List[date]:
        """Derive payment due dates from the billing cycle.

        When the billing cycle has explicit due dates, use a wide
        enough end boundary so that due dates falling after the last
        closing date (the normal case -- due = close + offset) are
        not accidentally excluded.
        """
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
    # CashFlow construction
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

    # ------------------------------------------------------------------
    # Payment recording
    # ------------------------------------------------------------------

    @tz_aware
    def record_payment(
        self,
        amount: Money,
        payment_date: datetime,
        interest_date: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> Settlement:
        """Record a payment and return the derived settlement.

        Args:
            amount: Payment amount (must be positive).
            payment_date: When the money moved.
            interest_date: Cutoff for interest accrual.  Defaults to
                *payment_date*.
            description: Optional description.
        """
        if amount.is_negative() or amount.is_zero():
            raise ValueError("Payment amount must be positive")

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
            )
        )

        return self.settlements[-1]

    def pay_installment(self, amount: Money, description: Optional[str] = None) -> Settlement:
        """Pay the next installment.

        Interest accrual depends on timing:

        - Early / on-time: accrues up to the due date.
        - Late: accrues up to ``now()`` (mora kicks in).

        When all installments are already paid the payment is recorded
        as an overpayment.

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
        interest_date = max(payment_date, self._time_ctx.to_datetime(next_due))
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

    # ------------------------------------------------------------------
    # Derived state
    # ------------------------------------------------------------------

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
        )

    def _payment_entries(self) -> list:
        """Payment CashFlowEntry objects, sorted by datetime."""
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
        """Installment view (derived from CashFlow)."""
        state = self._compute_state()
        return build_installments(
            self.get_original_schedule(),
            state.settlements,
            state.fines_applied,
            state.principal_balance,
            self.now(),
            self._interest,
            state.last_accrual_end,
            tz=self._time_ctx.tz,
        )

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
    # Balance properties
    # ------------------------------------------------------------------

    @property
    def principal_balance(self) -> Money:
        """Outstanding principal."""
        return self._compute_state().principal_balance

    def _accrued_interest_components(self) -> tuple:
        """Return (regular, mora) accrued since last payment."""
        state = self._compute_state()
        days = (self._time_ctx.to_date(self.now()) - self._time_ctx.to_date(state.last_accrual_end)).days

        if state.principal_balance.is_positive() and days > 0:
            covered = covered_due_date_count(
                state.principal_balance,
                self.get_original_schedule(),
            )
            next_due = self.due_dates[covered] if covered < len(self.due_dates) else None

            mora_rate = resolve_mora_rate(
                self.due_dates,
                self._closing_dates,
                next_due,
                self.mora_interest_rate,
                self.mora_rate_resolver,
                self._time_ctx.tz,
            )
            return self._interest.compute_accrued_interest(
                days,
                state.principal_balance,
                self._time_ctx.tz,
                next_due,
                state.last_accrual_end,
                mora_rate_override=mora_rate,
            )

        return Money.zero(), Money.zero()

    @property
    def interest_balance(self) -> Money:
        """Regular accrued interest since last payment."""
        return self._accrued_interest_components()[0]

    @property
    def mora_interest_balance(self) -> Money:
        """Mora accrued interest since last payment."""
        return self._accrued_interest_components()[1]

    @property
    def fine_balance(self) -> Money:
        """Unpaid fines."""
        state = self._compute_state()
        total_fines = (
            Money(sum(f.raw_amount for f in state.fines_applied.values())) if state.fines_applied else Money.zero()
        )
        outstanding = total_fines - state.fines_paid_total
        return outstanding if outstanding.is_positive() else Money.zero()

    @property
    def current_balance(self) -> Money:
        """Total outstanding balance."""
        return self.principal_balance + self.interest_balance + self.mora_interest_balance + self.fine_balance

    @property
    def is_paid_off(self) -> bool:
        """Whether the loan is fully paid off."""
        return self.current_balance.is_zero() or self.current_balance.is_negative()

    @property
    def overpaid(self) -> Money:
        """Total amount paid beyond obligations."""
        return self._compute_state().overpaid

    # ------------------------------------------------------------------
    # Fine-related
    # ------------------------------------------------------------------

    @property
    def fines_applied(self) -> Dict[date, Money]:
        """Fine amounts applied per due date."""
        return self._compute_state().fines_applied

    @property
    def total_fines(self) -> Money:
        """Total fines applied."""
        fines = self.fines_applied
        if not fines:
            return Money.zero()
        return Money(sum(f.raw_amount for f in fines.values()))

    @tz_aware
    def is_late(self, due_date: date, as_of_date: Optional[datetime] = None) -> bool:
        """Check if a payment is late considering the grace period."""
        check = as_of_date if as_of_date is not None else self.now()
        return is_payment_late(due_date, self.grace_period_days, check, self._time_ctx.tz)

    def _on_warp(self, target_date: datetime) -> None:
        """Hook called by Warp after overriding TimeContext."""
        self._fine_observation_dates.append(target_date)

    def calculate_late_fines(self, as_of_date: Optional[datetime] = None) -> Money:
        """Compute and record fine observations as of a date.

        Returns the amount of NEW fines applied.
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
        """Current datetime (Warp-aware)."""
        return self._time_ctx.now()

    def days_since_last_payment(self) -> int:
        """Days since the last payment."""
        return (self._time_ctx.to_date(self.now()) - self._time_ctx.to_date(self.last_payment_date)).days

    def _covered_due_date_count(self) -> int:
        return covered_due_date_count(self.principal_balance, self.get_original_schedule())

    def _next_unpaid_due_date(self) -> date:
        covered = self._covered_due_date_count()
        if covered >= len(self.due_dates):
            raise ValueError("All due dates have been paid")
        return self.due_dates[covered]

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
            self._time_ctx.tz,
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
            days = (self._time_ctx.to_date(s.payment_date) - self._time_ctx.to_date(prev_date)).days
            actual_entries.append(
                PaymentScheduleEntry(
                    payment_number=i + 1,
                    due_date=self._time_ctx.to_date(s.payment_date),
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
            self._time_ctx.tz,
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
