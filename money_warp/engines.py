"""Shared engine building blocks for loan products.

Types and classes that are used by multiple product modules
(``loan``, ``billing_cycle_loan``) live here to avoid circular
imports.  The full forward-pass logic and allocation helpers stay
in :mod:`money_warp.loan.engines` (which imports from here).
"""

from datetime import date, datetime, tzinfo
from enum import Enum
from typing import Callable, Optional, Tuple

from .interest_rate import InterestRate
from .money import Money
from .tz import to_date

# ===================================================================
# Mora strategy
# ===================================================================


class MoraStrategy(Enum):
    """Strategy for computing mora (late) interest.

    SIMPLE: mora rate is applied to the outstanding principal only.
    COMPOUND: mora rate is applied to principal + accrued regular interest.
    """

    SIMPLE = "simple"
    COMPOUND = "compound"


# ===================================================================
# Interest calculator
# ===================================================================


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

    def compute_accrued_interest(
        self,
        days: int,
        principal_balance: Money,
        tz: tzinfo,
        due_date: Optional[date] = None,
        last_payment_date: Optional[datetime] = None,
        mora_rate_override: Optional[InterestRate] = None,
    ) -> Tuple[Money, Money]:
        """Compute accrued interest split into regular and mora components.

        Returns (regular_accrued, mora_accrued). All interest is regular when
        due_date is not provided or the payment is not late.

        Args:
            tz: Business timezone for date extraction from datetimes.
            mora_rate_override: When provided, used instead of
                ``self.mora_interest_rate`` for this single computation.
                Existing callers that omit it get the original behaviour.
        """
        mora_rate = mora_rate_override or self.mora_interest_rate

        if due_date is None or last_payment_date is None:
            return self.interest_rate.accrue(principal_balance, days), Money.zero()

        regular_days = (due_date - to_date(last_payment_date, tz)).days

        if regular_days <= 0:
            return Money.zero(), mora_rate.accrue(principal_balance, days)

        if regular_days >= days:
            return self.interest_rate.accrue(principal_balance, days), Money.zero()

        mora_days = days - regular_days
        regular_accrued = self.interest_rate.accrue(principal_balance, regular_days)

        if self.mora_strategy == MoraStrategy.COMPOUND:
            mora_accrued = mora_rate.accrue(principal_balance + regular_accrued, mora_days)
        else:
            mora_accrued = mora_rate.accrue(principal_balance, mora_days)

        return regular_accrued, mora_accrued


# ===================================================================
# Mora rate callback type
# ===================================================================

#: Optional callback that resolves a mora rate override for a given
#: payment event.  Receives the *next_due* date (or ``None`` when all
#: installments are covered) and returns an ``InterestRate`` to use,
#: or ``None`` to fall back to the calculator's default.
MoraRateCallback = Optional[Callable[[Optional[date]], Optional[InterestRate]]]
