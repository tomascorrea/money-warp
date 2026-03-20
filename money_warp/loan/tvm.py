"""Time-value-of-money convenience functions for Loan objects.

These live in a separate module to avoid the circular import between
``money_warp.loan`` and ``money_warp.present_value``.
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from ..cash_flow import CashFlow, CashFlowItem
from ..interest_rate import InterestRate
from ..money import Money
from ..present_value import internal_rate_of_return, present_value
from ..rate import Rate
from ..tz import to_datetime, tz_aware

if TYPE_CHECKING:
    from .loan import Loan


@tz_aware
def loan_present_value(
    loan: "Loan",
    discount_rate: Optional[InterestRate] = None,
    valuation_date: Optional[datetime] = None,
) -> Money:
    """Calculate the Present Value of a loan's expected cash flows.

    Args:
        loan: The loan to value.
        discount_rate: Discount rate (defaults to loan's interest rate).
        valuation_date: Date to discount back to (defaults to loan.now()).

    Returns:
        The present value of the loan's expected cash flows.
    """
    if discount_rate is None:
        discount_rate = loan.interest_rate

    expected_cf = loan.generate_expected_cash_flow()

    if valuation_date is None:
        valuation_date = loan.now()

    return present_value(expected_cf, discount_rate, valuation_date)


def loan_irr(loan: "Loan", guess: Optional[Rate] = None) -> Rate:
    """Calculate the Internal Rate of Return of a loan's expected cash flows.

    Args:
        loan: The loan to compute IRR for.
        guess: Initial guess (defaults to 10% annual).

    Returns:
        The IRR as a Rate (may be negative).
    """
    expected_cf = loan.generate_expected_cash_flow()
    return internal_rate_of_return(expected_cf, guess, year_size=loan.interest_rate.year_size)


def loan_calculate_anticipation(
    loan: "Loan",
    installments: List[int],
) -> "AnticipationResult":
    """Calculate the amount to pay today to eliminate specific installments.

    Pure calculation with no side effects on the loan.

    Args:
        loan: The loan to calculate anticipation for.
        installments: 1-based installment numbers to anticipate.

    Returns:
        AnticipationResult with the amount and the installments being removed.

    Raises:
        ValueError: If any number is invalid or already paid.
    """
    from .settlement import AnticipationResult

    original = loan.get_original_schedule()
    covered = loan._covered_due_date_count()
    total_installments = len(original)

    removed_set = set(installments)
    for num in removed_set:
        if num < 1 or num > total_installments:
            raise ValueError(f"Installment {num} is out of range (1..{total_installments})")
        if num <= covered:
            raise ValueError(f"Installment {num} is already paid")

    kept_items: List[CashFlowItem] = []
    anticipated_installments = []
    all_installments = loan.installments

    for entry in original:
        if entry.payment_number in removed_set:
            anticipated_installments.append(all_installments[entry.payment_number - 1])
            continue
        if entry.payment_number <= covered:
            continue
        kept_items.append(
            CashFlowItem(
                Money(-entry.payment_amount.raw_amount),
                to_datetime(entry.due_date),
                f"Kept payment {entry.payment_number}",
                "kept_payment",
            )
        )

    if not kept_items:
        return AnticipationResult(
            amount=loan.current_balance,
            installments=anticipated_installments,
        )

    kept_cf = CashFlow(kept_items)
    valuation_date = loan.now()
    sustainable_balance = present_value(kept_cf, loan.interest_rate, valuation_date)
    sustainable_balance = Money(-sustainable_balance.raw_amount)

    anticipation_amount = loan.current_balance - sustainable_balance
    if anticipation_amount.is_negative():
        anticipation_amount = Money.zero()

    return AnticipationResult(
        amount=anticipation_amount,
        installments=anticipated_installments,
    )
