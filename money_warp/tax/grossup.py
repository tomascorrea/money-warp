"""Grossup calculation using scipy.optimize.brentq bracketed root-finding."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from scipy.optimize import brentq  # type: ignore[import]

from ..interest_rate import InterestRate
from ..money import Money
from ..scheduler.base import BaseScheduler
from .base import BaseTax

if TYPE_CHECKING:
    from ..loan.loan import Loan


class GrossupResult:
    """Result of a grossup calculation.

    Carries the grossed-up principal, the original requested amount, the
    computed tax, and all the parameters needed to construct a Loan via
    the convenience method ``to_loan()``.

    Attributes:
        principal: The grossed-up principal (loan amount including financed tax).
        requested_amount: The amount the borrower actually receives.
        total_tax: Total tax computed on the grossed-up principal.
    """

    def __init__(
        self,
        principal: Money,
        requested_amount: Money,
        total_tax: Money,
        interest_rate: InterestRate,
        due_dates: list[datetime],
        disbursement_date: datetime,
        scheduler: type[BaseScheduler],
        taxes: list[BaseTax],
    ) -> None:
        self.principal = principal
        self.requested_amount = requested_amount
        self.total_tax = total_tax
        self._interest_rate = interest_rate
        self._due_dates = due_dates
        self._disbursement_date = disbursement_date
        self._scheduler = scheduler
        self._taxes = taxes

    def to_loan(self, **loan_kwargs: Any) -> Loan:
        """Create a Loan from this grossup result.

        All schedule parameters (principal, interest_rate, due_dates,
        disbursement_date, scheduler, taxes) are forwarded automatically.
        Pass any additional Loan keyword arguments (fine_rate,
        grace_period_days, mora_interest_rate, mora_strategy) via
        ``loan_kwargs``.

        Returns:
            A fully configured Loan with the grossed-up principal.
        """
        # Lazy import to break the circular dependency between
        # tax.grossup -> loan.loan -> tax.base
        from ..loan.loan import Loan

        return Loan(
            principal=self.principal,
            interest_rate=self._interest_rate,
            due_dates=self._due_dates,
            disbursement_date=self._disbursement_date,
            scheduler=self._scheduler,
            taxes=self._taxes,
            **loan_kwargs,
        )

    def __repr__(self) -> str:
        return (
            f"GrossupResult(principal={self.principal!r}, "
            f"requested_amount={self.requested_amount!r}, "
            f"total_tax={self.total_tax!r})"
        )


def _compute_total_tax(
    principal: Money,
    interest_rate: InterestRate,
    due_dates: list[datetime],
    disbursement_date: datetime,
    scheduler: type[BaseScheduler],
    taxes: list[BaseTax],
) -> Money:
    """Compute the total tax for a given principal."""
    schedule = scheduler.generate_schedule(principal, interest_rate, due_dates, disbursement_date)
    total = Money.zero()
    for tax in taxes:
        total = total + tax.calculate(schedule, disbursement_date).total
    return total


def grossup(
    requested_amount: Money,
    interest_rate: InterestRate,
    due_dates: list[datetime],
    disbursement_date: datetime,
    scheduler: type[BaseScheduler],
    taxes: list[BaseTax],
) -> GrossupResult:
    """
    Compute the grossed-up principal so that principal - total_tax = requested_amount.

    The borrower wants to receive ``requested_amount``. Taxes are calculated on
    the loan principal, which must be larger to compensate. Uses
    ``scipy.optimize.brentq`` (bracketed bisection) to find the root of
    ``f(p) = p - requested_amount - tax(p) = 0``.

    ``brentq`` is preferred over ``fsolve`` because the objective function has
    a staircase shape (cent-level rounding in schedule/tax computation makes it
    non-smooth), which can cause ``fsolve``'s numerical Jacobian to stall.

    Args:
        requested_amount: The net amount the borrower wants to receive.
        interest_rate: The loan interest rate.
        due_dates: Payment due dates.
        disbursement_date: When the loan is disbursed.
        scheduler: Scheduler class for generating the amortization schedule.
        taxes: List of taxes to finance into the principal.

    Returns:
        GrossupResult with the grossed-up principal, tax breakdown, and a
        ``to_loan()`` convenience method.

    Raises:
        ValueError: If requested_amount is not positive, no taxes provided,
                    or the solver fails to converge.
    """
    if not requested_amount.is_positive():
        raise ValueError("requested_amount must be positive")
    if not taxes:
        raise ValueError("At least one tax is required for grossup")

    requested_raw = float(requested_amount.raw_amount)

    def objective(p: float) -> float:
        principal = Money(Decimal(str(p)))
        tax = _compute_total_tax(principal, interest_rate, due_dates, disbursement_date, scheduler, taxes)
        return p - requested_raw - float(tax.raw_amount)

    lower = requested_raw
    upper = requested_raw * 2

    try:
        solved_p = brentq(objective, lower, upper, xtol=1e-4)
    except ValueError as exc:
        raise ValueError(f"Grossup solver did not converge: {exc}") from exc

    solved_principal = Money(Decimal(str(solved_p)))
    total_tax = _compute_total_tax(solved_principal, interest_rate, due_dates, disbursement_date, scheduler, taxes)

    return GrossupResult(
        principal=solved_principal,
        requested_amount=requested_amount,
        total_tax=total_tax,
        interest_rate=interest_rate,
        due_dates=due_dates,
        disbursement_date=disbursement_date,
        scheduler=scheduler,
        taxes=taxes,
    )


def grossup_loan(
    requested_amount: Money,
    interest_rate: InterestRate,
    due_dates: list[datetime],
    disbursement_date: datetime,
    scheduler: type[BaseScheduler],
    taxes: list[BaseTax],
    **loan_kwargs: Any,
) -> Loan:
    """
    Compute a grossed-up loan in a single call.

    Sugar for ``grossup(...).to_loan(**loan_kwargs)``. The borrower wants to
    receive ``requested_amount``; this function finds the principal that
    satisfies ``principal - tax = requested_amount`` and returns a fully
    configured Loan.

    Args:
        requested_amount: The net amount the borrower wants to receive.
        interest_rate: The loan interest rate.
        due_dates: Payment due dates.
        disbursement_date: When the loan is disbursed.
        scheduler: Scheduler class for generating the amortization schedule.
        taxes: List of taxes to finance into the principal.
        **loan_kwargs: Extra keyword arguments forwarded to the Loan constructor
            (e.g. fine_rate, grace_period_days, mora_interest_rate, mora_strategy).

    Returns:
        A Loan with the grossed-up principal and taxes attached.
    """
    result = grossup(
        requested_amount=requested_amount,
        interest_rate=interest_rate,
        due_dates=due_dates,
        disbursement_date=disbursement_date,
        scheduler=scheduler,
        taxes=taxes,
    )
    return result.to_loan(**loan_kwargs)
