"""IOF (Imposto sobre Operações Financeiras) - Brazilian financial operations tax."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Union

from ..money import Money
from ..scheduler.schedule import PaymentSchedule
from .base import BaseTax, TaxInstallmentDetail, TaxResult


class IOFRounding(Enum):
    """Rounding strategy for IOF component aggregation.

    PRECISE: sum high-precision daily and additional components, round once
        per installment.  This is the mathematically purer approach.
    PER_COMPONENT: round each component (daily, additional) to 2 decimal
        places before summing.  Matches the behavior of common Brazilian
        lending platforms.
    """

    PRECISE = "precise"
    PER_COMPONENT = "per_component"


class IOF(BaseTax):
    """
    Brazilian IOF tax on loan operations.

    IOF has two components applied to each installment's principal payment:
    - Daily rate: applied per day from disbursement to payment date (capped at max_daily_days)
    - Additional rate: flat percentage applied once per installment

    Args:
        daily_rate: Daily IOF rate as decimal or string (e.g., Decimal("0.000082") or "0.0082%")
        additional_rate: Additional flat IOF rate as decimal or string (e.g., Decimal("0.0038") or "0.38%")
        max_daily_days: Maximum number of days for daily rate calculation (default 365)
        rounding: Rounding strategy for component aggregation (default PRECISE)
    """

    def __init__(
        self,
        daily_rate: Union[str, Decimal],
        additional_rate: Union[str, Decimal],
        max_daily_days: int = 365,
        rounding: IOFRounding = IOFRounding.PRECISE,
    ) -> None:
        self._daily_rate = self._parse_rate(daily_rate)
        self._additional_rate = self._parse_rate(additional_rate)
        self._max_daily_days = max_daily_days
        self._rounding = rounding

    @staticmethod
    def _parse_rate(rate: Union[str, Decimal]) -> Decimal:
        """Parse a rate from string (with optional %) or Decimal."""
        if isinstance(rate, Decimal):
            return rate
        rate = rate.strip()
        if rate.endswith("%"):
            return Decimal(rate[:-1]) / 100
        return Decimal(rate)

    @property
    def daily_rate(self) -> Decimal:
        """The daily IOF rate as a decimal."""
        return self._daily_rate

    @property
    def additional_rate(self) -> Decimal:
        """The additional flat IOF rate as a decimal."""
        return self._additional_rate

    @property
    def max_daily_days(self) -> int:
        """Maximum days for daily rate calculation."""
        return self._max_daily_days

    @property
    def rounding(self) -> IOFRounding:
        """The rounding strategy used for component aggregation."""
        return self._rounding

    def calculate(
        self,
        schedule: PaymentSchedule,
        disbursement_date: datetime,
    ) -> TaxResult:
        """
        Calculate IOF for each installment in the schedule.

        For each installment:
            days = min(days_from_disbursement_to_due_date, max_daily_days)
            daily_iof = principal_payment * daily_rate * days
            additional_iof = principal_payment * additional_rate
            installment_tax = daily_iof + additional_iof
        """
        details: List[TaxInstallmentDetail] = []
        total = Money.zero()

        for entry in schedule:
            days = min(
                (entry.due_date - disbursement_date).days,
                self._max_daily_days,
            )
            principal_raw = entry.principal_payment.raw_amount

            daily_iof = Money(principal_raw * self._daily_rate * days)
            additional_iof = Money(principal_raw * self._additional_rate)

            if self._rounding == IOFRounding.PER_COMPONENT:
                installment_tax = (Money(daily_iof.real_amount) + Money(additional_iof.real_amount)).to_real_money()
            else:
                installment_tax = (daily_iof + additional_iof).to_real_money()

            details.append(
                TaxInstallmentDetail(
                    payment_number=entry.payment_number,
                    due_date=entry.due_date,
                    principal_payment=entry.principal_payment,
                    tax_amount=installment_tax,
                )
            )
            total = total + installment_tax

        return TaxResult(total=total, per_installment=details)

    def __repr__(self) -> str:
        return (
            f"IOF(daily_rate={self._daily_rate}, "
            f"additional_rate={self._additional_rate}, "
            f"max_daily_days={self._max_daily_days}, "
            f"rounding={self._rounding})"
        )


class IndividualIOF(IOF):
    """IOF for Pessoa Fisica (PF) -- individual/natural person borrowers.

    Pre-configured with the standard PF rates:
    - Daily rate: 0.0082% (0.000082)
    - Additional rate: 0.38% (0.0038)

    All parameters can be overridden if the rates change by regulation.
    """

    DEFAULT_DAILY_RATE = Decimal("0.000082")
    DEFAULT_ADDITIONAL_RATE = Decimal("0.0038")

    def __init__(
        self,
        daily_rate: Union[str, Decimal] = DEFAULT_DAILY_RATE,
        additional_rate: Union[str, Decimal] = DEFAULT_ADDITIONAL_RATE,
        max_daily_days: int = 365,
        rounding: IOFRounding = IOFRounding.PRECISE,
    ) -> None:
        super().__init__(daily_rate, additional_rate, max_daily_days, rounding)


class CorporateIOF(IOF):
    """IOF for Pessoa Juridica (PJ) -- legal entity/company borrowers.

    Pre-configured with the standard PJ rates:
    - Daily rate: 0.0041% (0.000041)
    - Additional rate: 0.38% (0.0038)

    All parameters can be overridden if the rates change by regulation.
    """

    DEFAULT_DAILY_RATE = Decimal("0.000041")
    DEFAULT_ADDITIONAL_RATE = Decimal("0.0038")

    def __init__(
        self,
        daily_rate: Union[str, Decimal] = DEFAULT_DAILY_RATE,
        additional_rate: Union[str, Decimal] = DEFAULT_ADDITIONAL_RATE,
        max_daily_days: int = 365,
        rounding: IOFRounding = IOFRounding.PRECISE,
    ) -> None:
        super().__init__(daily_rate, additional_rate, max_daily_days, rounding)
