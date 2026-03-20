"""Payment recording and querying over a shared CashFlow."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from ..cash_flow import CashFlow, CashFlowItem
from ..money import Money
from ..scheduler import PaymentScheduleEntry
from ..time_context import TimeContext
from .interest_calculator import InterestCalculator

_ITEM_CATEGORIES = ("fine", "interest", "mora_interest", "principal")


@dataclass(frozen=True)
class SettlementSnapshot:
    """Minimal per-settlement metadata captured at recording time.

    These values cannot be derived from the CashFlow alone because they
    depend on the interest_date / principal_balance at the exact moment
    the payment was recorded.
    """

    payment_date: datetime
    days_in_period: int
    beginning_balance: Money
    ending_balance: Money


class PaymentLedger:
    """Records payments as tagged CashFlowItems and answers queries.

    Replaces the four parallel lists that Loan used to maintain:

    * ``_all_payments``            → ``self._cf`` items tagged ``settlement:N``
    * ``_payment_item_offsets``    → category-tag queries
    * ``_actual_schedule_entries`` → ``self._snapshots`` (lightweight)
    * ``_actual_payment_datetimes``→ derived from snapshot.payment_date
    """

    def __init__(self, cash_flow: CashFlow, time_context: TimeContext) -> None:
        self._cf = cash_flow
        self._time_ctx = time_context
        self._settlement_count: int = 0
        self._snapshots: List[SettlementSnapshot] = []

    def now(self) -> datetime:
        return self._time_ctx.now()

    # ------------------------------------------------------------------
    # Query helpers  (replace _all_payments, _actual_payments, etc.)
    # ------------------------------------------------------------------

    @property
    def all_payment_items(self) -> List:
        """All payment entries ever recorded (resolved CashFlowEntry objects)."""
        return self._cf.items()

    @property
    def actual_payment_items(self) -> List:
        """Payment entries visible at the current time."""
        now = self.now()
        return [e for e in self._cf.items() if e.datetime <= now]

    @property
    def settlement_count(self) -> int:
        return self._settlement_count

    @property
    def snapshots(self) -> List[SettlementSnapshot]:
        return list(self._snapshots)

    def snapshot(self, index: int) -> SettlementSnapshot:
        return self._snapshots[index]

    def items_for_settlement(self, settlement_number: int) -> Dict[str, Money]:
        """Amounts by category for a given settlement (1-based)."""
        tag = f"settlement:{settlement_number}"
        items = self._cf.query.filter_by(category=tag).all()
        result: Dict[str, Money] = {c: Money.zero() for c in _ITEM_CATEGORIES}
        for item in items:
            for cat in _ITEM_CATEGORIES:
                if cat in item.category:
                    result[cat] = result[cat] + item.amount
                    break
        return result

    def principal_balance(self, original_principal: Money) -> Money:
        """Outstanding principal as of now()."""
        balance = original_principal
        now = self.now()
        for entry in self._cf.items():
            if entry.datetime <= now and "principal" in entry.category:
                balance = balance - entry.amount
        if balance.is_negative():
            return Money.zero()
        return balance

    def last_payment_date(self, disbursement_date: datetime) -> datetime:
        """Datetime of the most recent payment, or disbursement_date."""
        actual = self.actual_payment_items
        return actual[-1].datetime if actual else disbursement_date

    def actual_payment_datetimes(self) -> List[datetime]:
        """Payment dates for each settlement, in order."""
        return [s.payment_date for s in self._snapshots]

    def actual_schedule_entries(self) -> List[PaymentScheduleEntry]:
        """Backward-compatible schedule entries derived from snapshots."""
        entries: List[PaymentScheduleEntry] = []
        for i, snap in enumerate(self._snapshots):
            settlement_num = i + 1
            amounts = self.items_for_settlement(settlement_num)
            interest_paid = amounts["interest"] + amounts["mora_interest"]
            principal_paid = amounts["principal"]
            payment_amount = amounts["interest"] + amounts["mora_interest"] + amounts["principal"]
            entries.append(
                PaymentScheduleEntry(
                    payment_number=settlement_num,
                    due_date=snap.payment_date.date(),
                    days_in_period=snap.days_in_period,
                    beginning_balance=snap.beginning_balance,
                    payment_amount=payment_amount,
                    principal_payment=principal_paid,
                    interest_payment=interest_paid,
                    ending_balance=snap.ending_balance,
                )
            )
        return entries

    # ------------------------------------------------------------------
    # Interest snapshot (pre-payment computation)
    # ------------------------------------------------------------------

    def compute_interest_snapshot(
        self,
        payment_date: datetime,
        interest_date: datetime,
        original_principal: Money,
        disbursement_date: datetime,
    ) -> Tuple[int, Money, Optional[datetime]]:
        """Compute (days, principal_balance, last_payment_date) for a new payment.

        Scans the CashFlow to determine the principal balance and the date
        of the most recent prior payment.
        """
        all_items = self.all_payment_items
        prior_items = [p for p in all_items if p.datetime <= payment_date]
        last_pay_date: Optional[datetime] = prior_items[-1].datetime if prior_items else disbursement_date
        days = (interest_date.date() - last_pay_date.date()).days

        principal_balance = original_principal
        for p in all_items:
            if p.datetime <= payment_date and "principal" in p.category:
                principal_balance = principal_balance - p.amount
        if principal_balance.is_negative():
            principal_balance = Money.zero()

        return days, principal_balance, last_pay_date

    # ------------------------------------------------------------------
    # Payment allocation  (replaces Loan._allocate_payment)
    # ------------------------------------------------------------------

    def allocate_payment(
        self,
        amount: Money,
        payment_date: datetime,
        days: int,
        principal_balance: Money,
        description: Optional[str],
        interest_calc: InterestCalculator,
        fine_balance: Money,
        due_date: Optional[date] = None,
        last_payment_date: Optional[datetime] = None,
    ) -> Tuple[int, Money, Money, Money, Money, Money]:
        """Allocate a payment and write tagged CashFlowItems to the shared CashFlow.

        Returns (settlement_number, fine_paid, interest_paid, mora_paid,
        principal_paid, ending_balance).
        """
        self._settlement_count += 1
        settlement_num = self._settlement_count
        tag = f"settlement:{settlement_num}"

        remaining = amount
        label = description or f"Payment on {payment_date.date()}"

        fine_paid = Money.zero()
        if fine_balance.is_positive() and remaining.is_positive():
            fine_paid = Money(min(fine_balance.raw_amount, remaining.raw_amount))
            self._cf.add_item(
                CashFlowItem(
                    fine_paid,
                    payment_date,
                    f"Fine payment - {label}",
                    frozenset({"fine", tag}),
                    time_context=self._time_ctx,
                )
            )
            remaining = remaining - fine_paid

        interest_paid = Money.zero()
        mora_paid = Money.zero()
        if remaining.is_positive() and principal_balance.is_positive() and days > 0:
            regular_accrued, mora_accrued = interest_calc.compute_accrued_interest(
                days, principal_balance, due_date, last_payment_date
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
                    self._cf.add_item(
                        CashFlowItem(
                            regular_amount,
                            payment_date,
                            f"Interest portion - {label}",
                            frozenset({"interest", tag}),
                            time_context=self._time_ctx,
                        )
                    )
                    interest_paid = regular_amount

                if mora_amount.is_positive():
                    self._cf.add_item(
                        CashFlowItem(
                            mora_amount,
                            payment_date,
                            f"Mora interest - {label}",
                            frozenset({"mora_interest", tag}),
                            time_context=self._time_ctx,
                        )
                    )
                    mora_paid = mora_amount

                remaining = remaining - interest_paid - mora_paid

        principal_paid = Money.zero()
        if remaining.is_positive():
            principal_paid = remaining
            self._cf.add_item(
                CashFlowItem(
                    principal_paid,
                    payment_date,
                    f"Principal portion - {label}",
                    frozenset({"principal", tag}),
                    time_context=self._time_ctx,
                )
            )

        ending_balance = principal_balance - principal_paid
        if ending_balance.is_negative():
            ending_balance = Money.zero()

        self._snapshots.append(
            SettlementSnapshot(
                payment_date=payment_date,
                days_in_period=days,
                beginning_balance=principal_balance,
                ending_balance=ending_balance,
            )
        )

        return settlement_num, fine_paid, interest_paid, mora_paid, principal_paid, ending_balance
