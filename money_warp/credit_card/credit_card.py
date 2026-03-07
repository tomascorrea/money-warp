"""CreditCard — revolving credit modeled as a cash-flow state machine."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from ..billing_cycle import BaseBillingCycle, MonthlyBillingCycle
from ..cash_flow import CashFlow, CashFlowItem
from ..interest_rate import InterestRate
from ..money import Money
from ..time_context import TimeContext
from ..tz import tz_aware
from .statement import Statement

_DEBIT_CATEGORIES = frozenset({"purchase", "interest_charge", "fine_charge"})
_CREDIT_CATEGORIES = frozenset({"payment", "refund"})


class CreditCard:
    """Revolving credit instrument with periodic billing statements.

    Transactions (purchases, payments, refunds) are recorded as
    ``CashFlowItem`` objects.  Statements, interest charges, and fines
    all **emerge from the cash flow** — they are never stored as
    independent state.  Billing-cycle processing materialises interest
    and fine items lazily, controlled by an idempotency counter.

    Args:
        interest_rate: Annual rate applied to carried balances.
        billing_cycle: Strategy that generates closing / due dates.
            Defaults to ``MonthlyBillingCycle()``.
        minimum_payment_rate: Fraction of the closing balance required
            as minimum payment (default 0.15 = 15 %).
        minimum_payment_floor: Absolute floor for the minimum payment
            (default $25).
        fine_rate: Fine as fraction of the minimum payment when the
            minimum is not met (default 0.02 = 2 %).
        opening_date: When the card was opened.  Defaults to ``now()``.
        credit_limit: Maximum outstanding balance.  ``None`` means
            unlimited.
    """

    _DEFAULT_MINIMUM_PAYMENT_RATE = Decimal("0.15")
    _DEFAULT_MINIMUM_PAYMENT_FLOOR = Money("25.00")
    _DEFAULT_FINE_RATE = Decimal("0.02")

    @tz_aware
    def __init__(
        self,
        interest_rate: InterestRate,
        billing_cycle: Optional[BaseBillingCycle] = None,
        minimum_payment_rate: Optional[Decimal] = None,
        minimum_payment_floor: Optional[Money] = None,
        fine_rate: Optional[Decimal] = None,
        opening_date: Optional[datetime] = None,
        credit_limit: Optional[Money] = None,
    ) -> None:
        if minimum_payment_rate is None:
            minimum_payment_rate = self._DEFAULT_MINIMUM_PAYMENT_RATE
        if minimum_payment_floor is None:
            minimum_payment_floor = self._DEFAULT_MINIMUM_PAYMENT_FLOOR
        if fine_rate is None:
            fine_rate = self._DEFAULT_FINE_RATE

        if minimum_payment_rate < 0 or minimum_payment_rate > 1:
            raise ValueError("minimum_payment_rate must be between 0 and 1")
        if minimum_payment_floor.is_negative():
            raise ValueError("minimum_payment_floor must be non-negative")
        if fine_rate < 0:
            raise ValueError("fine_rate must be non-negative")
        if credit_limit is not None and (credit_limit.is_negative() or credit_limit.is_zero()):
            raise ValueError("credit_limit must be positive")

        self._time_ctx = TimeContext()

        self.interest_rate = interest_rate
        self.billing_cycle = billing_cycle or MonthlyBillingCycle()
        self.minimum_payment_rate = minimum_payment_rate
        self.minimum_payment_floor = minimum_payment_floor
        self.fine_rate = fine_rate
        self.opening_date = opening_date if opening_date is not None else self._time_ctx.now()
        self.credit_limit = credit_limit

        self._all_items: List[CashFlowItem] = []
        self._cycles_closed: int = 0

    # ------------------------------------------------------------------
    # Time helpers
    # ------------------------------------------------------------------

    def now(self) -> datetime:
        """Current datetime (Warp-aware via shared TimeContext)."""
        return self._time_ctx.now()

    # ------------------------------------------------------------------
    # Transaction methods
    # ------------------------------------------------------------------

    @tz_aware
    def purchase(
        self,
        amount: Money,
        date: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> None:
        """Record a purchase on the card.

        Args:
            amount: Purchase amount (positive).
            date: Transaction date.  Defaults to ``now()``.
            description: Optional merchant / memo.

        Raises:
            ValueError: If *amount* is not positive or exceeds the
                available credit.
        """
        if amount.is_negative() or amount.is_zero():
            raise ValueError("Purchase amount must be positive")
        date = date or self.now()
        self._close_billing_cycles(date)

        if self.credit_limit is not None:
            balance_after = self._raw_balance(date) + amount
            if balance_after > self.credit_limit:
                raise ValueError("Purchase would exceed credit limit")

        self._all_items.append(
            CashFlowItem(
                amount,
                date,
                description or "Purchase",
                "purchase",
                time_context=self._time_ctx,
            )
        )

    @tz_aware
    def pay(
        self,
        amount: Money,
        date: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> None:
        """Record a payment toward the card balance.

        Args:
            amount: Payment amount (positive).
            date: Transaction date.  Defaults to ``now()``.
            description: Optional memo.

        Raises:
            ValueError: If *amount* is not positive.
        """
        if amount.is_negative() or amount.is_zero():
            raise ValueError("Payment amount must be positive")
        date = date or self.now()
        self._close_billing_cycles(date)
        self._all_items.append(
            CashFlowItem(
                amount,
                date,
                description or "Payment",
                "payment",
                time_context=self._time_ctx,
            )
        )

    @tz_aware
    def refund(
        self,
        amount: Money,
        date: Optional[datetime] = None,
        description: Optional[str] = None,
    ) -> None:
        """Record a merchant refund.

        Args:
            amount: Refund amount (positive).
            date: Transaction date.  Defaults to ``now()``.
            description: Optional memo.

        Raises:
            ValueError: If *amount* is not positive.
        """
        if amount.is_negative() or amount.is_zero():
            raise ValueError("Refund amount must be positive")
        date = date or self.now()
        self._close_billing_cycles(date)
        self._all_items.append(
            CashFlowItem(
                amount,
                date,
                description or "Refund",
                "refund",
                time_context=self._time_ctx,
            )
        )

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def current_balance(self) -> Money:
        """Outstanding balance as of ``now()``, after closing due cycles."""
        self._close_billing_cycles(self.now())
        return self._raw_balance(self.now())

    @property
    def available_credit(self) -> Optional[Money]:
        """Remaining credit if a limit is set, else ``None``."""
        if self.credit_limit is None:
            return None
        remaining = self.credit_limit - self.current_balance
        return remaining if remaining.is_positive() else Money.zero()

    @property
    def is_paid_off(self) -> bool:
        """Whether the balance is zero (or overpaid)."""
        bal = self.current_balance
        return bal.is_zero() or bal.is_negative()

    @property
    def statements(self) -> List[Statement]:
        """All closed billing-period statements up to ``now()``."""
        self._close_billing_cycles(self.now())
        return self._build_statements()

    # ------------------------------------------------------------------
    # Cash flow
    # ------------------------------------------------------------------

    def get_cash_flow(self) -> CashFlow:
        """Full cash flow with signed amounts.

        Purchases / interest / fines are positive (credit extended);
        payments / refunds are negative (money returned).
        """
        self._close_billing_cycles(self.now())
        items: List[CashFlowItem] = []
        now = self.now()
        for item in self._all_items:
            if item.datetime > now:
                continue
            sign = Money("1") if item.category in _DEBIT_CATEGORIES else Money("-1")
            items.append(
                CashFlowItem(
                    item.amount * sign,
                    item.datetime,
                    item.description,
                    item.category,
                    time_context=self._time_ctx,
                )
            )
        return CashFlow(items)

    # ------------------------------------------------------------------
    # Warp hook
    # ------------------------------------------------------------------

    def _on_warp(self, target_date: datetime) -> None:
        """Called by Warp after overriding TimeContext."""
        self._close_billing_cycles(target_date)

    # ------------------------------------------------------------------
    # Billing-cycle processing (internal)
    # ------------------------------------------------------------------

    def _close_billing_cycles(self, as_of_date: datetime) -> None:
        """Materialise interest charges and fines for all completed cycles.

        Idempotent: ``_cycles_closed`` tracks how many cycles have
        already been processed so repeated calls are no-ops.
        """
        closing_dates = self.billing_cycle.closing_dates_between(self.opening_date, as_of_date)

        while self._cycles_closed < len(closing_dates):
            idx = self._cycles_closed
            closing_date = closing_dates[idx]

            prev_closing = self.opening_date if idx == 0 else closing_dates[idx - 1]

            prev_balance = self._balance_at(prev_closing)
            payments_in_period = self._sum_category_between("payment", prev_closing, closing_date)
            refunds_in_period = self._sum_category_between("refund", prev_closing, closing_date)
            carried = prev_balance - payments_in_period - refunds_in_period
            if carried.is_negative():
                carried = Money.zero()

            if carried.is_positive():
                days = (closing_date - prev_closing).days
                interest = self.interest_rate.accrue(carried, days)
                self._all_items.append(
                    CashFlowItem(
                        interest,
                        closing_date,
                        f"Interest charge — period {idx + 1}",
                        "interest_charge",
                        time_context=self._time_ctx,
                    )
                )

            if idx > 0:
                self._maybe_apply_fine(closing_dates, idx)

            self._cycles_closed += 1

    def _maybe_apply_fine(self, closing_dates: List[datetime], current_idx: int) -> None:
        """Apply a fine if the previous cycle's minimum payment was not met."""
        prev_closing = closing_dates[current_idx - 1]
        prev_due = self.billing_cycle.due_date_for(prev_closing)

        prev_balance = self._statement_closing_balance(closing_dates, current_idx - 1)
        if prev_balance.is_zero() or prev_balance.is_negative():
            return

        minimum = self._compute_minimum_payment(prev_balance)
        payments_by_due = self._sum_category_between("payment", prev_closing, prev_due)

        if payments_by_due < minimum:
            fine = Money(minimum.raw_amount * self.fine_rate)
            if fine.is_positive():
                self._all_items.append(
                    CashFlowItem(
                        fine,
                        prev_due,
                        f"Late-payment fine — period {current_idx}",
                        "fine_charge",
                        time_context=self._time_ctx,
                    )
                )

    # ------------------------------------------------------------------
    # Statement builder
    # ------------------------------------------------------------------

    def _build_statements(self) -> List[Statement]:
        closing_dates = self.billing_cycle.closing_dates_between(self.opening_date, self.now())
        result: List[Statement] = []

        for idx in range(min(self._cycles_closed, len(closing_dates))):
            closing_date = closing_dates[idx]
            prev_closing = self.opening_date if idx == 0 else closing_dates[idx - 1]

            prev_balance = self._balance_at(prev_closing)
            purchases = self._sum_category_between("purchase", prev_closing, closing_date)
            payments = self._sum_category_between("payment", prev_closing, closing_date)
            refunds = self._sum_category_between("refund", prev_closing, closing_date)
            interest = self._sum_category_between("interest_charge", prev_closing, closing_date)
            fines = self._sum_category_between("fine_charge", prev_closing, closing_date)

            closing_balance = prev_balance + purchases - payments - refunds + interest + fines
            if closing_balance.is_negative():
                closing_balance = Money.zero()

            minimum = self._compute_minimum_payment(closing_balance)
            due_date = self.billing_cycle.due_date_for(closing_date)

            result.append(
                Statement(
                    period_number=idx + 1,
                    opening_date=prev_closing,
                    closing_date=closing_date,
                    due_date=due_date,
                    previous_balance=prev_balance,
                    purchases_total=purchases,
                    payments_total=payments,
                    refunds_total=refunds,
                    interest_charged=interest,
                    fine_charged=fines,
                    closing_balance=closing_balance,
                    minimum_payment=minimum,
                )
            )

        return result

    def _statement_closing_balance(self, closing_dates: List[datetime], idx: int) -> Money:
        """Compute closing balance for a single cycle by index."""
        closing_date = closing_dates[idx]
        prev_closing = closing_dates[idx - 1] if idx > 0 else self.opening_date

        prev_balance = self._balance_at(prev_closing)
        purchases = self._sum_category_between("purchase", prev_closing, closing_date)
        payments = self._sum_category_between("payment", prev_closing, closing_date)
        refunds = self._sum_category_between("refund", prev_closing, closing_date)
        interest = self._sum_category_between("interest_charge", prev_closing, closing_date)
        fines = self._sum_category_between("fine_charge", prev_closing, closing_date)

        balance = prev_balance + purchases - payments - refunds + interest + fines
        return balance if balance.is_positive() else Money.zero()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _raw_balance(self, as_of: datetime) -> Money:
        """Sum of debits minus credits up to *as_of*."""
        total = Money.zero()
        for item in self._all_items:
            if item.datetime > as_of:
                continue
            if item.category in _DEBIT_CATEGORIES:
                total = total + item.amount
            elif item.category in _CREDIT_CATEGORIES:
                total = total - item.amount
        return total

    def _balance_at(self, as_of: datetime) -> Money:
        """Balance at a point in time (does NOT trigger cycle closing)."""
        bal = self._raw_balance(as_of)
        return bal if bal.is_positive() else Money.zero()

    def _sum_category_between(self, category: str, after: datetime, up_to: datetime) -> Money:
        """Sum item amounts for *category* in the half-open interval (after, up_to]."""
        total = Money.zero()
        for item in self._all_items:
            if item.category == category and after < item.datetime <= up_to:
                total = total + item.amount
        return total

    def _compute_minimum_payment(self, closing_balance: Money) -> Money:
        """Minimum payment for a given closing balance."""
        if closing_balance.is_zero() or closing_balance.is_negative():
            return Money.zero()
        proportional = Money(closing_balance.raw_amount * self.minimum_payment_rate)
        floor = self.minimum_payment_floor
        return Money(min(closing_balance.raw_amount, max(proportional.raw_amount, floor.raw_amount)))

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        return f"CreditCard(rate={self.interest_rate}, balance={self.current_balance}, limit={self.credit_limit})"

    def __repr__(self) -> str:
        return (
            f"CreditCard(interest_rate={self.interest_rate!r}, "
            f"billing_cycle={self.billing_cycle!r}, "
            f"minimum_payment_rate={self.minimum_payment_rate!r}, "
            f"fine_rate={self.fine_rate!r}, "
            f"opening_date={self.opening_date!r}, "
            f"credit_limit={self.credit_limit!r})"
        )
