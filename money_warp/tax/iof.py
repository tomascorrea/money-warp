"""IOF (Imposto sobre Operações Financeiras) - Brazilian financial operations tax."""

from datetime import datetime
from decimal import Decimal
from typing import List, Union

from ..money import Money
from ..scheduler.schedule import PaymentSchedule
from .base import BaseTax, TaxInstallmentDetail, TaxResult


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
    """

    def __init__(
        self,
        daily_rate: Union[str, Decimal],
        additional_rate: Union[str, Decimal],
        max_daily_days: int = 365,
    ) -> None:
        self._daily_rate = self._parse_rate(daily_rate)
        self._additional_rate = self._parse_rate(additional_rate)
        self._max_daily_days = max_daily_days

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
            installment_tax = daily_iof + additional_iof

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
            f"max_daily_days={self._max_daily_days})"
        )
