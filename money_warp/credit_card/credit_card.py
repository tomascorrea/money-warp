"""CreditCard — revolving credit modeled as a cash-flow state machine."""

from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from ..billing_cycle import BaseBillingCycle, MonthlyBillingCycle, Statement
from ..cash_flow import CashFlow, CashFlowEntry, CashFlowItem
from ..interest_rate import InterestRate
from ..money import Money
from ..time_context import TimeContext
from ..tz import tz_aware

_DEBIT_CATEGORIES = frozenset({"purchase", "interest_charge", "fine_charge"})
_CREDIT_CATEGORIES = frozenset({"payment", "refund"})


class CreditCard:
    """Revolving credit instrument with periodic billing statements.

    The credit card **is** a cash flow.  Transactions (purchases,
    payments, refunds) are added directly to the underlying
    :class:`CashFlow`.  Statements, interest charges, and fines all
    **emerge from that cash flow** — they are never stored as
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
        fine_rate: Fine rate applied to the minimum payment when the
            minimum is not met (default 2% annual).
        opening_date: When the card was opened.  Defaults to ``now()``.
        credit_limit: Maximum outstanding balance.  ``None`` means
            unlimited.
    """

    _DEFAULT_MINIMUM_PAYMENT_RATE = Decimal("0.15")
    _DEFAULT_MINIMUM_PAYMENT_FLOOR = Money("25.00")
    _DEFAULT_FINE_RATE = InterestRate("2% annual")

    @tz_aware
    def __init__(
        self,
        interest_rate: InterestRate,
        billing_cycle: Optional[BaseBillingCycle] = None,
        minimum_payment_rate: Optional[Decimal] = None,
        minimum_payment_floor: Optional[Money] = None,
        fine_rate: Optional[InterestRate] = None,
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

        self.cash_flow = CashFlow()
        self._cycles_closed: int = 0
        self._last_closing_balance: Money = Money.zero()

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

        if self.credit_limit is not None:
            balance_after = self._raw_balance() + amount
            if balance_after > self.credit_limit:
                raise ValueError("Purchase would exceed credit limit")

        self.cash_flow.add_item(
            CashFlowItem(
                amount,
                date,
                description or "Purchase",
                "purchase",
                time_context=self._time_ctx,
                effective_date=date,
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
        self.cash_flow.add_item(
            CashFlowItem(
                amount,
                date,
                description or "Payment",
                "payment",
                time_context=self._time_ctx,
                effective_date=date,
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
        self.cash_flow.add_item(
            CashFlowItem(
                amount,
                date,
                description or "Refund",
                "refund",
                time_context=self._time_ctx,
                effective_date=date,
            )
        )

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def current_balance(self) -> Money:
        """Outstanding balance as of ``now()``, after closing due cycles."""
        self._close_billing_cycles()
        return self._raw_balance()

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

    def get_cash_flow(self) -> List[CashFlowEntry]:
        """Return a signed cash-flow view of all resolved transactions.

        Debits (purchases, interest, fines) are positive.
        Credits (payments, refunds) are negated to negative.
        Items are sorted by datetime.
        """
        self._close_billing_cycles()
        result = []
        for entry in self.cash_flow.items():
            if not entry.category.isdisjoint(_CREDIT_CATEGORIES):
                entry = replace(entry, amount=-entry.amount)
            result.append(entry)
        return sorted(result, key=lambda e: e.datetime)

    @property
    def statements(self) -> List[Statement]:
        """All closed billing-period statements up to ``now()``."""
        self._close_billing_cycles()
        return self.billing_cycle.build_statements(
            self.cash_flow,
            self.opening_date,
            self.now(),
            self.minimum_payment_rate,
            self.minimum_payment_floor,
        )

    # ------------------------------------------------------------------
    # Warp hook
    # ------------------------------------------------------------------

    def _on_warp(self, target_date: datetime) -> None:
        """Called by Warp after overriding TimeContext."""
        self._close_billing_cycles()

    # ------------------------------------------------------------------
    # Billing-cycle processing (internal)
    # ------------------------------------------------------------------

    def _close_billing_cycles(self) -> None:
        """Materialise interest charges and fines for all completed cycles.

        Idempotent: ``_cycles_closed`` tracks how many cycles have
        already been processed so repeated calls are no-ops.  Balance is
        carried forward iteratively via ``_last_closing_balance``.
        """
        closing_dates = self.billing_cycle.closing_dates_between(self.opening_date, self.now())
        running_balance = self._last_closing_balance

        while self._cycles_closed < len(closing_dates):
            idx = self._cycles_closed
            closing_date = closing_dates[idx]
            prev_closing = self.opening_date if idx == 0 else closing_dates[idx - 1]

            purchases = self._sum_category_between("purchase", prev_closing, closing_date)
            payments = self._sum_category_between("payment", prev_closing, closing_date)
            refunds = self._sum_category_between("refund", prev_closing, closing_date)

            carried = running_balance - payments - refunds
            if carried.is_negative():
                carried = Money.zero()

            interest = Money.zero()
            if carried.is_positive():
                days = (closing_date - prev_closing).days
                interest = self.interest_rate.accrue(carried, days)
                self.cash_flow.add_item(
                    CashFlowItem(
                        interest,
                        closing_date,
                        f"Interest charge — period {idx + 1}",
                        "interest_charge",
                        time_context=self._time_ctx,
                        effective_date=closing_date,
                    )
                )

            fine = Money.zero()
            if idx > 0:
                fine = self._maybe_apply_fine(closing_dates, idx, running_balance)

            running_balance = running_balance + purchases - payments - refunds + interest + fine
            if running_balance.is_negative():
                running_balance = Money.zero()

            self._cycles_closed += 1
            self._last_closing_balance = running_balance

    def _maybe_apply_fine(
        self,
        closing_dates: List[datetime],
        current_idx: int,
        prev_closing_balance: Money,
    ) -> Money:
        """Apply a fine if the previous cycle's minimum payment was not met.

        Returns the fine amount (``Money.zero()`` when no fine applies).
        """
        if prev_closing_balance.is_zero() or prev_closing_balance.is_negative():
            return Money.zero()

        prev_closing = closing_dates[current_idx - 1]
        prev_due = self.billing_cycle.due_date_for(prev_closing)

        minimum = self.billing_cycle.compute_minimum_payment(
            prev_closing_balance,
            self.minimum_payment_rate,
            self.minimum_payment_floor,
        )
        payments_by_due = self._sum_category_between("payment", prev_closing, prev_due)

        if payments_by_due < minimum:
            fine = Money(minimum.raw_amount * self.fine_rate.as_decimal())
            if fine.is_positive():
                self.cash_flow.add_item(
                    CashFlowItem(
                        fine,
                        prev_due,
                        f"Late-payment fine — period {current_idx}",
                        "fine_charge",
                        time_context=self._time_ctx,
                        effective_date=prev_due,
                    )
                )
                return fine
        return Money.zero()

    # ------------------------------------------------------------------
    # Cash-flow query helpers
    # ------------------------------------------------------------------

    def _raw_balance(self) -> Money:
        """Sum of debits minus credits (resolved items only)."""
        debits = (
            self.cash_flow.query.filter_by(predicate=lambda i: not i.category.isdisjoint(_DEBIT_CATEGORIES))
        ).sum_amounts()
        credit_total = (
            self.cash_flow.query.filter_by(predicate=lambda i: not i.category.isdisjoint(_CREDIT_CATEGORIES))
        ).sum_amounts()
        return debits - credit_total

    def _sum_category_between(self, category: str, after: datetime, up_to: datetime) -> Money:
        """Sum item amounts for *category* in the half-open interval (after, up_to]."""
        return (
            self.cash_flow.query.filter_by(category=category)
            .filter_by(datetime__gt=after, datetime__lte=up_to)
            .sum_amounts()
        )

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
