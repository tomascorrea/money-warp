"""Base billing cycle abstraction for periodic statement generation."""

from abc import ABC, abstractmethod
from datetime import date, datetime, tzinfo
from decimal import Decimal
from typing import List, Optional

from ..cash_flow import CashFlow
from ..money import Money
from ..tz import to_date
from .statement import Statement


class BaseBillingCycle(ABC):
    """Abstract factory for billing cycle date generation and statement building.

    Subclasses define how statement closing dates and payment due dates
    are derived.  The credit card uses whichever implementation is
    injected at construction time — same pattern as ``BaseScheduler``
    on the Loan.

    Statement building is concrete: it relies on the abstract date
    methods and the cash-flow query API, so it works for every
    implementation.

    Args:
        due_dates: Optional explicit due dates.  When provided, these
            override the dates that would be computed from closing dates
            via :meth:`due_date_for`.  Useful when the payment schedule
            has non-standard due dates that don't follow the closing-day
            offset rule.
    """

    def __init__(self, due_dates: Optional[List[date]] = None) -> None:
        self._explicit_due_dates: Optional[List[date]] = sorted(due_dates) if due_dates else None

    @abstractmethod
    def closing_dates_between(self, start: datetime, end: datetime) -> List[datetime]:
        """Return closing dates for all *complete* cycles in [start, end].

        The first closing date is the earliest one strictly after *start*.
        The last closing date is the latest one at or before *end*.
        """

    @abstractmethod
    def due_date_for(self, closing_date: datetime) -> datetime:
        """Payment due date for a given statement closing date."""

    def due_dates_between(self, start: datetime, end: datetime, tz: tzinfo) -> List[date]:
        """Return payment due dates for all cycles in ``[start, end]``.

        When explicit *due_dates* were provided at construction, returns
        those falling strictly after *start* and at or before *end*.
        Otherwise derives them from :meth:`closing_dates_between` and
        :meth:`due_date_for`.
        """
        if self._explicit_due_dates is not None:
            start_d = to_date(start, tz)
            end_d = to_date(end, tz)
            return [d for d in self._explicit_due_dates if start_d < d <= end_d]

        closing_dates = self.closing_dates_between(start, end)
        return [to_date(self.due_date_for(cd), tz) for cd in closing_dates]

    # ------------------------------------------------------------------
    # Statement building
    # ------------------------------------------------------------------

    def build_statements(
        self,
        cash_flow: CashFlow,
        opening_date: datetime,
        end_date: datetime,
        minimum_payment_rate: Decimal,
        minimum_payment_floor: Money,
    ) -> List[Statement]:
        """Build statements for all closed cycles in [opening_date, end_date].

        Iterates the closing dates, slices the *cash_flow* by period,
        and produces a :class:`Statement` for each one.  Balance is
        carried forward iteratively across periods.
        """
        closing_dates = self.closing_dates_between(opening_date, end_date)
        result: List[Statement] = []
        running_balance = Money.zero()

        for idx, closing_date in enumerate(closing_dates):
            prev_closing = opening_date if idx == 0 else closing_dates[idx - 1]

            prev_balance = running_balance
            purchases = self._sum_category(cash_flow, "purchase", prev_closing, closing_date)
            payments = self._sum_category(cash_flow, "payment", prev_closing, closing_date)
            refunds = self._sum_category(cash_flow, "refund", prev_closing, closing_date)
            interest = self._sum_category(cash_flow, "interest_charge", prev_closing, closing_date)
            fines = self._sum_category(cash_flow, "fine_charge", prev_closing, closing_date)

            closing_balance = prev_balance + purchases - payments - refunds + interest + fines
            if closing_balance.is_negative():
                closing_balance = Money.zero()

            minimum = self.compute_minimum_payment(
                closing_balance,
                minimum_payment_rate,
                minimum_payment_floor,
            )
            due_date = self.due_date_for(closing_date)

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
            running_balance = closing_balance

        return result

    @staticmethod
    def compute_minimum_payment(
        closing_balance: Money,
        rate: Decimal,
        floor: Money,
    ) -> Money:
        """Minimum payment for a given closing balance."""
        if closing_balance.is_zero() or closing_balance.is_negative():
            return Money.zero()
        proportional = Money(closing_balance.raw_amount * rate)
        return Money(min(closing_balance.raw_amount, max(proportional.raw_amount, floor.raw_amount)))

    @staticmethod
    def _sum_category(
        cash_flow: CashFlow,
        category: str,
        after: datetime,
        up_to: datetime,
    ) -> Money:
        """Sum item amounts for *category* in the half-open interval (after, up_to]."""
        return (
            cash_flow.query.filter_by(category=category)
            .filter_by(datetime__gt=after, datetime__lte=up_to)
            .sum_amounts()
        )
