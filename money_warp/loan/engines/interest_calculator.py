"""Stateless interest computation split into regular and mora components."""

from datetime import date, datetime
from enum import Enum
from typing import Optional, Tuple

from ...interest_rate import InterestRate
from ...money import Money


class MoraStrategy(Enum):
    """Strategy for computing mora (late) interest.

    SIMPLE: mora rate is applied to the outstanding principal only.
    COMPOUND: mora rate is applied to principal + accrued regular interest.
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

    def compute_accrued_interest(
        self,
        days: int,
        principal_balance: Money,
        due_date: Optional[date] = None,
        last_payment_date: Optional[datetime] = None,
    ) -> Tuple[Money, Money]:
        """Compute accrued interest split into regular and mora components.

        Returns (regular_accrued, mora_accrued). All interest is regular when
        due_date is not provided or the payment is not late. Uses
        ``mora_interest_rate`` and ``mora_strategy`` for the mora portion.
        """
        if due_date is None or last_payment_date is None:
            return self.interest_rate.accrue(principal_balance, days), Money.zero()

        regular_days = (due_date - last_payment_date.date()).days

        if regular_days <= 0:
            return Money.zero(), self.mora_interest_rate.accrue(principal_balance, days)

        if regular_days >= days:
            return self.interest_rate.accrue(principal_balance, days), Money.zero()

        mora_days = days - regular_days
        regular_accrued = self.interest_rate.accrue(principal_balance, regular_days)

        if self.mora_strategy == MoraStrategy.COMPOUND:
            mora_accrued = self.mora_interest_rate.accrue(principal_balance + regular_accrued, mora_days)
        else:
            mora_accrued = self.mora_interest_rate.accrue(principal_balance, mora_days)

        return regular_accrued, mora_accrued
