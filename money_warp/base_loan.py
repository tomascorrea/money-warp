"""BaseLoan ABC -- shared implementation for Loan and BillingCycleLoan.

All balance properties, payment methods (except ``record_payment``),
settlement logic, fine tracking, schedule queries, and Warp hooks live
here.  Subclasses provide ``_compute_state``, ``_build_initial_cashflow``,
and ``record_payment``.  Per-cycle mora rate resolution is handled via the
``_resolve_mora_rate_for_due`` hook.
"""

import warnings
from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple, Type

from .cash_flow import CashFlow
from .engines import (
    InterestCalculator,
    LoanState,
    MoraStrategy,
    apply_tolerance_adjustment,
    build_installments,
    is_payment_late,
    principal_covered_count,
)
from .models import Installment, Settlement
from .scheduler import BaseScheduler, PaymentSchedule, PaymentScheduleEntry
from .time_context import TimeContext
from .types.interest_rate import InterestRate
from .types.money import Money
from .tz import tz_aware
from .working_day import WorkingDayCalendar, effective_penalty_due_date


class BaseLoan(ABC):
    """Abstract base for loan products.

    Subclasses must set the following attributes during ``__init__``:

    - ``_time_ctx``: :class:`TimeContext`
    - ``principal``: :class:`Money`
    - ``interest_rate``: :class:`InterestRate`
    - ``mora_interest_rate``: :class:`InterestRate`
    - ``mora_strategy``: :class:`MoraStrategy`
    - ``_interest``: :class:`InterestCalculator`
    - ``due_dates``: ``List[date]``
    - ``disbursement_date``: ``datetime``
    - ``scheduler``: ``Type[BaseScheduler]``
    - ``fine_rate``: :class:`InterestRate`
    - ``grace_period_days``: ``int``
    - ``payment_tolerance``: :class:`Money`
    - ``working_day_calendar``: :class:`WorkingDayCalendar`
    - ``_fine_observation_dates``: ``List[datetime]``
    - ``cashflow``: :class:`CashFlow`
    """

    _time_ctx: TimeContext
    principal: Money
    interest_rate: InterestRate
    mora_interest_rate: InterestRate
    mora_strategy: MoraStrategy
    _interest: InterestCalculator
    due_dates: List[date]
    disbursement_date: datetime
    scheduler: Type[BaseScheduler]
    fine_rate: InterestRate
    grace_period_days: int
    payment_tolerance: Money
    working_day_calendar: WorkingDayCalendar
    _fine_observation_dates: List[datetime]
    cashflow: CashFlow

    # ------------------------------------------------------------------
    # Abstract hooks
    # ------------------------------------------------------------------

    @abstractmethod
    def _compute_state(self) -> LoanState:
        """Run the forward pass and return derived loan state."""

    @abstractmethod
    def _build_initial_cashflow(self) -> CashFlow:
        """Build the initial CashFlow with expected items from the schedule."""

    @abstractmethod
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
        """Record a payment and return the derived settlement.

        Subclasses may extend the signature (e.g. ``Loan`` adds
        ``processing_date``).
        """

    # ------------------------------------------------------------------
    # Mora rate hook (override in subclasses with per-cycle resolution)
    # ------------------------------------------------------------------

    def _resolve_mora_rate_for_due(self, next_due: Optional[date]) -> Optional[InterestRate]:
        """Return the mora rate override for *next_due*, or ``None`` for the default.

        ``Loan`` returns ``None`` (uses the calculator's fixed rate).
        ``BillingCycleLoan`` overrides this to call ``resolve_mora_rate``
        with the per-cycle resolver.
        """
        return None

    # ------------------------------------------------------------------
    # Payment methods
    # ------------------------------------------------------------------

    def pay_installment(
        self,
        amount: Money,
        description: Optional[str] = None,
        waive_fines: bool = False,
        waive_mora: bool = False,
        waive_overdue_interest: bool = False,
        discount: Optional[Money] = None,
    ) -> Settlement:
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

        if self._principal_covered_count() >= len(self.due_dates):
            warnings.warn(
                f"All installments already paid. Recording {amount} as overpayment.",
                stacklevel=2,
            )
            return self.record_payment(
                amount,
                payment_date=payment_date,
                interest_date=payment_date,
                description=description or "Overpayment",
                waive_fines=waive_fines,
                waive_mora=waive_mora,
                waive_overdue_interest=waive_overdue_interest,
                discount=discount,
            )

        next_due = self._next_unpaid_due_date()
        interest_date = max(payment_date, self._time_ctx.to_datetime(next_due))
        settlement = self.record_payment(
            amount,
            payment_date=payment_date,
            interest_date=interest_date,
            description=description,
            waive_fines=waive_fines,
            waive_mora=waive_mora,
            waive_overdue_interest=waive_overdue_interest,
            discount=discount,
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
    # Derived state helpers
    # ------------------------------------------------------------------

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
            tz=self._time_ctx.tz,
            calendar=self.working_day_calendar,
            grace_period_days=self.grace_period_days,
        )

    # ------------------------------------------------------------------
    # Balance properties
    # ------------------------------------------------------------------

    @property
    def principal_balance(self) -> Money:
        """Outstanding principal (derived from CashFlow)."""
        return self._compute_state().principal_balance

    def _accrued_interest_components(self) -> Tuple[Money, Money, Money]:
        """Return ``(regular, mora, overdue)`` accrued interest since last payment.

        Uses ``_resolve_mora_rate_for_due`` to obtain the per-cycle
        mora rate override (``None`` for ``Loan``, resolved rate for
        ``BillingCycleLoan``).

        The *overdue* component is the portion of *regular* that accrued
        past the contract due date.  It is a subset of *regular*, not an
        additional charge.
        """
        state = self._compute_state()
        days = (self._time_ctx.to_date(self.now()) - self._time_ctx.to_date(state.last_accrual_end)).days

        if state.principal_balance.is_positive() and days > 0:
            covered = principal_covered_count(state.principal_balance, self.get_original_schedule())
            next_due = self.due_dates[covered] if covered < len(self.due_dates) else None
            penalty_next_due = effective_penalty_due_date(next_due, self.working_day_calendar) if next_due else None
            mora_rate = self._resolve_mora_rate_for_due(next_due)
            regular, mora = self._interest.compute_accrued_interest(
                days,
                state.principal_balance,
                self._time_ctx.tz,
                penalty_next_due,
                state.last_accrual_end,
                mora_rate_override=mora_rate,
            )

            if next_due and not is_payment_late(
                next_due, self.grace_period_days, self.now(), self._time_ctx.tz, self.working_day_calendar
            ):
                regular = regular + mora
                mora = Money.zero()

            overdue = Money.zero()
            if next_due:
                due_days = max(0, (next_due - self._time_ctx.to_date(state.last_accrual_end)).days)
                if due_days < days:
                    capped = self._interest.interest_rate.accrue(state.principal_balance, due_days)
                    excess = regular - capped
                    if excess.is_positive():
                        overdue = excess

            return regular, mora, overdue

        return Money.zero(), Money.zero(), Money.zero()

    @property
    def interest_balance(self) -> Money:
        """Regular (non-mora) accrued interest since last payment."""
        return self._accrued_interest_components()[0]

    @property
    def mora_interest_balance(self) -> Money:
        """Mora accrued interest since last payment."""
        return self._accrued_interest_components()[1]

    @property
    def overdue_interest_balance(self) -> Money:
        """Regular interest accrued past the contract due date (subset of interest_balance)."""
        return self._accrued_interest_components()[2]

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
    def settlement_balance(self) -> Money:
        """Amount needed to cover the next installment via ``pay_installment``.

        Computes fines + mora + interest (accrued to ``max(now, next_due)``)
        + the next installment's scheduled principal.  Matches the interest
        cutoff that ``pay_installment`` uses internally.

        For single-installment or last-installment loans this equals the
        full payoff amount.  For multi-installment loans with more than one
        installment remaining, this is less than ``current_balance``.
        """
        state = self._compute_state()
        if not state.principal_balance.is_positive():
            return Money.zero()

        schedule = self.get_original_schedule()
        covered = principal_covered_count(state.principal_balance, schedule)
        if covered >= len(self.due_dates):
            return Money.zero()

        next_due = self.due_dates[covered]
        next_entry = schedule.entries[covered]

        now_date = self._time_ctx.to_date(self.now())
        interest_cutoff = max(now_date, next_due)
        days = (interest_cutoff - self._time_ctx.to_date(state.last_accrual_end)).days

        if days > 0:
            penalty_next_due = effective_penalty_due_date(next_due, self.working_day_calendar)
            mora_rate = self._resolve_mora_rate_for_due(next_due)
            regular, mora = self._interest.compute_accrued_interest(
                days,
                state.principal_balance,
                self._time_ctx.tz,
                penalty_next_due,
                state.last_accrual_end,
                mora_rate_override=mora_rate,
            )
        else:
            regular, mora = Money.zero(), Money.zero()

        total_fines = (
            Money(sum(f.raw_amount for f in state.fines_applied.values())) if state.fines_applied else Money.zero()
        )
        fine = total_fines - state.fines_paid_total
        if fine.is_negative():
            fine = Money.zero()

        return fine + mora + regular + next_entry.principal_payment

    @property
    def is_paid_off(self) -> bool:
        """Whether the loan is fully paid off."""
        if self.current_balance.is_zero() or self.current_balance.is_negative():
            return True
        return self._all_installments_covered()

    def _all_installments_covered(self) -> bool:
        """True when every installment has at least one fully-covered allocation.

        Handles the case where schedule divergence leaves a small
        positive balance but all per-installment allocations pass the
        tolerance-based ``is_fully_covered`` check.

        Guarded by a residual cap proportional to the number of
        installments so a large balance is never silently accepted.
        """
        installments = self.installments
        if not installments:
            return False
        n = len(self.due_dates)
        max_residual = self.payment_tolerance * n * n
        if self.current_balance > max_residual:
            return False
        return all(any(a.is_fully_covered for a in inst.allocations) for inst in installments)

    @property
    def overpaid(self) -> Money:
        """Total amount paid beyond the loan's obligations (derived from CashFlow)."""
        return self._compute_state().overpaid

    # ------------------------------------------------------------------
    # Fine-related
    # ------------------------------------------------------------------

    @property
    def fines_applied(self) -> Dict[date, Money]:
        """Fine amounts applied per due date (derived from CashFlow)."""
        return self._compute_state().fines_applied

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
        return is_payment_late(due_date, self.grace_period_days, check, self._time_ctx.tz, self.working_day_calendar)

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
        return (self._time_ctx.to_date(self.now()) - self._time_ctx.to_date(self.last_payment_date)).days

    def _principal_covered_count(self) -> int:
        """How many installments have principal covered (schedule milestones)."""
        return principal_covered_count(self.principal_balance, self.get_original_schedule())

    def _next_unpaid_due_date(self) -> date:
        """Find the next due date that hasn't been fully paid.

        Raises:
            ValueError: If all due dates have been paid.
        """
        covered = self._principal_covered_count()
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

        covered = principal_covered_count(state.principal_balance, self.get_original_schedule())
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
