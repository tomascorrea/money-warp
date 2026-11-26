"""Interest calculation primitives shared across loan products.

Types and classes used by multiple product modules (``loan``,
``billing_cycle_loan``) live here.  The forward-pass logic and
allocation helpers are in sibling submodules of this package.
"""

from datetime import date, datetime, tzinfo
from decimal import Decimal
from enum import Enum
from typing import Callable, Optional, Tuple

from ..types.interest_rate import InterestRate
from ..types.money import Money
from ..tz import to_date


class MoraStrategy(Enum):
    """Historical base for the grace-period principal slice.

    The mora charge itself does not use this value. Mora is simple
    interest on each overdue installment's payment amount. The enum
    remains on the loan so persisted rows still load.

    It still selects the base of the post-due principal accrual that
    :meth:`InterestCalculator.compute_accrued_interest` returns for
    grace-period reclassification. SIMPLE uses outstanding principal.
    COMPOUND uses principal plus regular interest accrued up to the
    due date.
    """

    SIMPLE = "simple"
    COMPOUND = "compound"


class InterestCalculator:
    """Pure interest math — no mutable state, no time context.

    Holds three immutable rate parameters and computes accrued interest
    split into regular and mora components.
    """

    def __init__(
        self,
        interest_rate: InterestRate,
        mora_interest_rate: InterestRate,
        mora_strategy: MoraStrategy = MoraStrategy.COMPOUND,
    ) -> None:
        self.interest_rate = interest_rate
        self.mora_interest_rate = mora_interest_rate
        self.mora_strategy = mora_strategy

    def simple_mora(
        self,
        amount: Money,
        days: int,
        mora_rate_override: Optional[InterestRate] = None,
    ) -> Money:
        """Simple mora on a fixed amount: ``amount * daily_rate * days``.

        ``days`` is the installment's own lateness. The rate is
        ``mora_rate_override`` when given, otherwise
        ``self.mora_interest_rate``. ``MoraStrategy`` does not change
        the result. Zero days or a zero amount yields zero.
        """
        if days <= 0 or amount.raw_amount == 0:
            return Money.zero()
        rate = mora_rate_override or self.mora_interest_rate
        daily = rate.to_daily().as_decimal()
        return Money(amount.raw_amount * daily * Decimal(days))

    def compute_accrued_interest(
        self,
        days: int,
        principal_balance: Money,
        tz: tzinfo,
        due_date: Optional[date] = None,
        last_payment_date: Optional[datetime] = None,
        mora_rate_override: Optional[InterestRate] = None,
    ) -> Tuple[Money, Money]:
        """Accrue regular interest on outstanding principal.

        Returns ``(regular, post_due_on_principal)``. ``regular`` is
        compound interest at ``interest_rate`` up to ``due_date``.
        ``post_due_on_principal`` is the slice after that date, still
        compounded on the principal balance (``MoraStrategy`` chooses
        whether regular interest accrued up to the due date joins the
        base). Callers add that slice back into regular interest only
        while the payment is inside the grace period. It is not the
        mora charge — mora is :meth:`simple_mora` on each installment.

        All interest is regular when ``due_date`` or
        ``last_payment_date`` is missing.

        Args:
            tz: Business timezone for date extraction from datetimes.
            mora_rate_override: When provided, used instead of
                ``self.mora_interest_rate`` for the post-due principal
                slice only.
        """
        mora_rate = mora_rate_override or self.mora_interest_rate

        if due_date is None or last_payment_date is None:
            return self.interest_rate.accrue(principal_balance, days), Money.zero()

        regular_days = (due_date - to_date(last_payment_date, tz)).days

        if regular_days <= 0:
            return Money.zero(), mora_rate.accrue(principal_balance, days)

        if regular_days >= days:
            return self.interest_rate.accrue(principal_balance, days), Money.zero()

        post_due_days = days - regular_days
        regular_accrued = self.interest_rate.accrue(principal_balance, regular_days)

        if self.mora_strategy == MoraStrategy.COMPOUND:
            post_due = mora_rate.accrue(principal_balance + regular_accrued, post_due_days)
        else:
            post_due = mora_rate.accrue(principal_balance, post_due_days)

        return regular_accrued, post_due


#: Optional callback that resolves a mora rate override for a given
#: payment event.  Receives the *next_due* date (or ``None`` when all
#: installments are covered) and returns an ``InterestRate`` to use,
#: or ``None`` to fall back to the calculator's default.
MoraRateCallback = Optional[Callable[[Optional[date]], Optional[InterestRate]]]
