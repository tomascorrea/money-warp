"""Present Value and IRR calculations for cash flows and financial instruments."""

from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional, Tuple, Union

from scipy.optimize import brentq, fsolve  # type: ignore[import]

from .cash_flow import CashFlow
from .interest_rate import InterestRate, YearSize
from .money import Money
from .tz import tz_aware


@tz_aware
def present_value(cash_flow: CashFlow, discount_rate: InterestRate, valuation_date: Optional[datetime] = None) -> Money:
    """
    Calculate the Present Value (PV) of a cash flow stream.

    The Present Value is the sum of all future cash flows discounted back to
    the valuation date using the specified discount rate.

    Formula: PV = Σ(CF_t / (1 + r)^t) where:
    - CF_t = Cash flow at time t
    - r = Discount rate per period
    - t = Time periods from valuation date

    Args:
        cash_flow: The cash flow stream to evaluate
        discount_rate: The discount rate to use for discounting
        valuation_date: Date to discount back to (defaults to earliest cash flow date)

    Returns:
        The present value of the cash flow stream

    Examples:
        >>> from datetime import datetime
        >>> from money_warp import CashFlow, CashFlowItem, Money, InterestRate, present_value
        >>>
        >>> # Create a simple cash flow
        >>> items = [
        ...     CashFlowItem(Money("1000"), datetime(2024, 1, 1), "Initial investment", "investment"),
        ...     CashFlowItem(Money("-1100"), datetime(2024, 12, 31), "Return", "return"),
        ... ]
        >>> cf = CashFlow(items)
        >>>
        >>> # Calculate PV with 5% discount rate
        >>> pv = present_value(cf, InterestRate("5% annual"))
        >>> print(f"Present Value: {pv}")  # Should be close to zero for 10% return vs 5% discount
    """
    if cash_flow.is_empty():
        return Money.zero()

    # Use earliest cash flow date as valuation date if not provided
    if valuation_date is None:
        valuation_date = cash_flow.earliest_datetime()

    # Ensure we have a valid valuation date
    if valuation_date is None:
        raise ValueError("Cannot calculate present value: no cash flows or invalid valuation date")

    # Convert discount rate to daily rate for precise calculations
    daily_rate = discount_rate.to_daily().as_decimal

    total_pv = Money.zero()

    for item in cash_flow.items():
        # Calculate days from valuation date to cash flow date
        days = (item.datetime - valuation_date).days

        if days < 0:
            # Cash flow is in the past relative to valuation date
            # This could happen if valuation_date is after some cash flows
            # We'll treat past cash flows as having zero time value
            days = 0

        # Calculate present value of this cash flow
        # PV = CF / (1 + daily_rate)^days
        if days == 0:
            # No discounting needed for same-day cash flows
            pv_amount = item.amount
        else:
            # Discount the cash flow
            discount_factor = (Decimal("1") + daily_rate) ** Decimal(str(days))
            pv_amount = Money(item.amount.raw_amount / discount_factor)

        total_pv += pv_amount

    return total_pv


def present_value_of_annuity(
    payment_amount: Money, interest_rate: InterestRate, periods: int, payment_timing: str = "end"
) -> Money:
    """
    Calculate the Present Value of an ordinary annuity or annuity due.

    An annuity is a series of equal payments made at regular intervals.

    Formula for ordinary annuity (payments at end of period):
    PV = PMT x [(1 - (1 + r)^(-n)) / r]

    Formula for annuity due (payments at beginning of period):
    PV = PMT x [(1 - (1 + r)^(-n)) / r] x (1 + r)

    Args:
        payment_amount: The amount of each payment
        interest_rate: The interest rate per period
        periods: The number of payment periods
        payment_timing: "end" for ordinary annuity, "begin" for annuity due

    Returns:
        The present value of the annuity

    Examples:
        >>> from money_warp import Money, InterestRate, present_value_of_annuity
        >>>
        >>> # PV of $1000 monthly payments for 12 months at 5% annual
        >>> monthly_rate = InterestRate("5% annual").to_monthly()
        >>> pv = present_value_of_annuity(Money("1000"), monthly_rate, 12)
        >>> print(f"PV of annuity: {pv}")
    """
    if periods <= 0:
        return Money.zero()

    if payment_amount.is_zero():
        return Money.zero()

    # Get the periodic interest rate as decimal
    periodic_rate = interest_rate.as_decimal

    if periodic_rate == 0:
        # Special case: zero interest rate
        # PV = PMT x n
        return payment_amount * periods

    # Calculate PV factor for ordinary annuity
    # PV_factor = (1 - (1 + r)^(-n)) / r
    discount_factor = (Decimal("1") + periodic_rate) ** (-Decimal(str(periods)))
    pv_factor = (Decimal("1") - discount_factor) / periodic_rate

    # Calculate present value
    pv = Money(payment_amount.raw_amount * pv_factor)

    # Adjust for annuity due (payments at beginning of period)
    if payment_timing.lower() in ("begin", "beginning", "due"):
        pv = Money(pv.raw_amount * (Decimal("1") + periodic_rate))

    return pv


def present_value_of_perpetuity(payment_amount: Money, interest_rate: InterestRate) -> Money:
    """
    Calculate the Present Value of a perpetuity.

    A perpetuity is a series of equal payments that continue forever.

    Formula: PV = PMT / r

    Args:
        payment_amount: The amount of each payment
        interest_rate: The interest rate per period

    Returns:
        The present value of the perpetuity

    Raises:
        ValueError: If interest rate is zero or negative

    Examples:
        >>> from money_warp import Money, InterestRate, present_value_of_perpetuity
        >>>
        >>> # PV of $100 annual payments forever at 5%
        >>> pv = present_value_of_perpetuity(Money("100"), InterestRate("5% annual"))
        >>> print(f"PV of perpetuity: {pv}")  # Should be $2000
    """
    if payment_amount.is_zero():
        return Money.zero()

    periodic_rate = interest_rate.as_decimal

    if periodic_rate <= 0:
        raise ValueError("Interest rate must be positive for perpetuity calculations")

    # PV = PMT / r
    return Money(payment_amount.raw_amount / periodic_rate)


def discount_factor(interest_rate: InterestRate, periods: Union[int, Decimal]) -> Decimal:
    """
    Calculate the discount factor for a given interest rate and time periods.

    Formula: DF = 1 / (1 + r)^n

    Args:
        interest_rate: The interest rate per period
        periods: The number of periods (can be fractional)

    Returns:
        The discount factor as a Decimal

    Examples:
        >>> from money_warp import InterestRate, discount_factor
        >>>
        >>> # Discount factor for 5% over 2 years
        >>> df = discount_factor(InterestRate("5% annual"), 2)
        >>> print(f"Discount factor: {df}")  # Should be about 0.907
    """
    if periods == 0:
        return Decimal("1")

    rate = interest_rate.as_decimal
    return Decimal("1") / ((Decimal("1") + rate) ** Decimal(str(periods)))


def _npv_function_factory(
    cash_flow: CashFlow, valuation_date: datetime, year_size: YearSize = YearSize.commercial
) -> Callable[[float], float]:
    """Create NPV function for IRR calculation."""

    def npv_function(rate_decimal: float) -> float:
        """Calculate NPV for a given rate (as decimal). IRR is where this equals zero."""
        # Handle edge cases
        if rate_decimal < -0.99:  # Prevent rates below -99%
            return 1e10
        if rate_decimal > 10.0:  # Prevent rates above 1000%
            return -1e10

        # Convert decimal rate to InterestRate
        # Handle both scalar and array inputs from scipy
        rate_percentage = rate_decimal.item() * 100 if hasattr(rate_decimal, "item") else float(rate_decimal) * 100  # type: ignore[attr-defined]
        test_rate = InterestRate(f"{rate_percentage:.10f}% annual", year_size=year_size)
        npv = present_value(cash_flow, test_rate, valuation_date)
        return float(npv.raw_amount)

    return npv_function


def _find_irr_bracket(npv_function: Callable[[float], float]) -> Tuple[Optional[float], bool]:
    """Find a bracket where NPV changes sign for robust root finding."""
    test_rates = [-0.5, -0.1, 0.01, 0.05, 0.10, 0.15, 0.25, 0.50, 1.0, 2.0]
    npv_values = []

    for rate in test_rates:
        try:
            npv_val = npv_function(rate)
            npv_values.append((rate, npv_val))
        except Exception:
            continue

    # Find a bracket where NPV changes sign
    for i in range(len(npv_values) - 1):
        rate1, npv1 = npv_values[i]
        rate2, npv2 = npv_values[i + 1]

        # Check if NPV changes sign between these two rates
        if npv1 * npv2 < 0:  # Different signs
            try:
                # Use Brent's method for robust root finding
                irr_decimal = brentq(npv_function, rate1, rate2, xtol=1e-8)
            except Exception:
                continue
            else:
                return irr_decimal, True

    return None, False


def internal_rate_of_return(
    cash_flow: CashFlow, guess: Optional[InterestRate] = None, year_size: YearSize = YearSize.commercial
) -> InterestRate:
    """
    Calculate the Internal Rate of Return (IRR) of a cash flow stream.

    The IRR is the discount rate that makes the Net Present Value (NPV) equal to zero.
    It represents the effective annual rate of return of the investment.

    Uses scipy.optimize.fsolve for robust numerical solution.

    Note: To calculate IRR from a specific date, use the Time Machine:
    with Warp(loan, target_date) as warped_loan:
        irr = warped_loan.irr()

    Args:
        cash_flow: The cash flow stream to analyze
        guess: Initial guess for IRR (defaults to 10% annual)
        year_size: Day-count convention (YearSize.commercial for 365 days,
                   YearSize.banker for 360 days)

    Returns:
        The internal rate of return as an InterestRate

    Raises:
        ValueError: If IRR cannot be found (no solution or doesn't converge)

    Examples:
        >>> from datetime import datetime
        >>> from money_warp import CashFlow, CashFlowItem, Money, internal_rate_of_return
        >>>
        >>> # Simple investment: -$1000 now, +$1100 in 1 year
        >>> items = [
        ...     CashFlowItem(Money("-1000"), datetime(2024, 1, 1), "Investment", "investment"),
        ...     CashFlowItem(Money("1100"), datetime(2024, 12, 31), "Return", "return"),
        ... ]
        >>> cf = CashFlow(items)
        >>>
        >>> irr = internal_rate_of_return(cf)
        >>> print(f"IRR: {irr}")  # Should be approximately 10%
    """
    if cash_flow.is_empty():
        raise ValueError("Cannot calculate IRR for empty cash flow")

    # Check if we have both positive and negative cash flows
    has_positive = any(item.amount.is_positive() for item in cash_flow.items())
    has_negative = any(item.amount.is_negative() for item in cash_flow.items())

    if not (has_positive and has_negative):
        raise ValueError("IRR requires both positive and negative cash flows")

    # Use earliest cash flow date as valuation date
    valuation_date = cash_flow.earliest_datetime()
    if valuation_date is None:
        raise ValueError("Cannot calculate IRR: no cash flows")

    # Use 10% as default initial guess
    initial_guess = 0.10 if guess is None else float(guess.as_decimal)

    # Create NPV function
    npv_function = _npv_function_factory(cash_flow, valuation_date, year_size)

    # Try to find a bracket where the function changes sign
    irr_decimal, bracket_found = _find_irr_bracket(npv_function)

    if not bracket_found or irr_decimal is None:
        # Fall back to fsolve with the original guess
        try:
            solution = fsolve(npv_function, initial_guess, full_output=True)
            irr_decimal = solution[0][0]
        except Exception as e:
            raise ValueError(f"IRR calculation failed: {str(e)}") from e

    # Ensure we have a valid solution
    if irr_decimal is None:
        raise ValueError("IRR calculation failed: no solution found")

    # Verify the solution
    final_npv = npv_function(irr_decimal)
    if abs(final_npv) > 500.0:  # Allow for reasonable tolerance in NPV (within $500)
        raise ValueError(f"IRR calculation did not converge: final NPV = {final_npv}")

    # Ensure we have a reasonable solution
    if irr_decimal < -0.99 or irr_decimal > 10.0:  # Between -99% and 1000%
        raise ValueError(f"IRR solution unreasonable: {irr_decimal * 100:.2f}%")

    # Convert back to InterestRate
    irr_percentage = irr_decimal * 100
    return InterestRate(f"{irr_percentage:.8f}% annual", year_size=year_size)


def irr(
    cash_flow: CashFlow, guess: Optional[InterestRate] = None, year_size: YearSize = YearSize.commercial
) -> InterestRate:
    """
    Calculate the Internal Rate of Return (IRR) of a cash flow stream.

    This is a convenience function that calls internal_rate_of_return() with
    default parameters for most common use cases.

    Note: To calculate IRR from a specific date, use the Time Machine:
    with Warp(loan, target_date) as warped_loan:
        irr = warped_loan.irr()

    Args:
        cash_flow: The cash flow stream to analyze
        guess: Initial guess for IRR (defaults to 10% annual)
        year_size: Day-count convention (YearSize.commercial for 365 days,
                   YearSize.banker for 360 days)

    Returns:
        The internal rate of return as an InterestRate

    Examples:
        >>> from datetime import datetime
        >>> from money_warp import CashFlow, CashFlowItem, Money, irr
        >>>
        >>> # Investment analysis
        >>> items = [
        ...     CashFlowItem(Money("-5000"), datetime(2024, 1, 1), "Initial investment", "investment"),
        ...     CashFlowItem(Money("1500"), datetime(2024, 6, 1), "Return 1", "return"),
        ...     CashFlowItem(Money("2000"), datetime(2024, 12, 1), "Return 2", "return"),
        ...     CashFlowItem(Money("2500"), datetime(2025, 6, 1), "Final return", "return"),
        ... ]
        >>> cf = CashFlow(items)
        >>>
        >>> investment_irr = irr(cf)
        >>> print(f"Investment IRR: {investment_irr}")
    """
    return internal_rate_of_return(cash_flow, guess, year_size)


def _calculate_mirr_components(
    cash_flow: CashFlow,
    finance_rate: InterestRate,
    reinvestment_rate: InterestRate,
    valuation_date: datetime,
    latest_date: datetime,
    year_size: YearSize = YearSize.commercial,
) -> Tuple[Money, Money]:
    """Calculate FV of positive flows and PV of negative flows for MIRR."""
    positive_flows = []
    negative_flows = []
    days_per_year = Decimal(str(year_size.value))

    for item in cash_flow.items():
        if item.amount.is_positive():
            positive_flows.append(item)
        elif item.amount.is_negative():
            negative_flows.append(item)

    if not positive_flows or not negative_flows:
        raise ValueError("MIRR requires both positive and negative cash flows")

    # Calculate Future Value of positive cash flows
    fv_positive = Money.zero()
    for item in positive_flows:
        periods_to_end = (latest_date - item.datetime).days / days_per_year
        if periods_to_end >= 0:
            annual_rate = reinvestment_rate.as_decimal
            compound_factor = (Decimal("1") + annual_rate) ** periods_to_end
            fv_positive += Money(item.amount.raw_amount * compound_factor)
        else:
            fv_positive += item.amount

    # Calculate Present Value of negative cash flows
    pv_negative = Money.zero()
    for item in negative_flows:
        periods_from_start = (item.datetime - valuation_date).days / days_per_year
        if periods_from_start >= 0:
            annual_rate = finance_rate.as_decimal
            discount_factor = (Decimal("1") + annual_rate) ** periods_from_start
            pv_negative += Money(item.amount.raw_amount / discount_factor)
        else:
            pv_negative += item.amount

    return fv_positive, pv_negative


def modified_internal_rate_of_return(
    cash_flow: CashFlow,
    finance_rate: InterestRate,
    reinvestment_rate: InterestRate,
    year_size: YearSize = YearSize.commercial,
) -> InterestRate:
    """
    Calculate the Modified Internal Rate of Return (MIRR).

    MIRR addresses some limitations of IRR by using different rates for
    financing negative cash flows and reinvesting positive cash flows.

    Formula: MIRR = (FV of positive flows / PV of negative flows)^(1/n) - 1

    Note: To calculate MIRR from a specific date, use the Time Machine:
    with Warp(loan, target_date) as warped_loan:
        mirr = modified_internal_rate_of_return(warped_loan.generate_expected_cash_flow(), ...)

    Args:
        cash_flow: The cash flow stream to analyze
        finance_rate: Rate for financing negative cash flows
        reinvestment_rate: Rate for reinvesting positive cash flows
        year_size: Day-count convention (YearSize.commercial for 365 days,
                   YearSize.banker for 360 days)

    Returns:
        The modified internal rate of return as an InterestRate

    Examples:
        >>> from datetime import datetime
        >>> from money_warp import CashFlow, CashFlowItem, Money, InterestRate, modified_internal_rate_of_return
        >>>
        >>> # Investment with different financing and reinvestment rates
        >>> items = [
        ...     CashFlowItem(Money("-1000"), datetime(2024, 1, 1), "Investment", "investment"),
        ...     CashFlowItem(Money("300"), datetime(2024, 6, 1), "Return 1", "return"),
        ...     CashFlowItem(Money("400"), datetime(2024, 12, 1), "Return 2", "return"),
        ...     CashFlowItem(Money("500"), datetime(2025, 6, 1), "Return 3", "return"),
        ... ]
        >>> cf = CashFlow(items)
        >>>
        >>> mirr = modified_internal_rate_of_return(
        ...     cf,
        ...     InterestRate("8% annual"),  # Financing rate
        ...     InterestRate("6% annual")   # Reinvestment rate
        ... )
        >>> print(f"MIRR: {mirr}")
    """
    if cash_flow.is_empty():
        raise ValueError("Cannot calculate MIRR for empty cash flow")

    # Use earliest cash flow date as valuation date
    valuation_date = cash_flow.earliest_datetime()
    if valuation_date is None:
        raise ValueError("Cannot calculate MIRR: no cash flows")

    # Find the latest cash flow date for future value calculations
    latest_date = cash_flow.latest_datetime()
    if latest_date is None:
        raise ValueError("Cannot calculate MIRR: no cash flows")

    days_per_year = Decimal(str(year_size.value))
    total_periods_years = (latest_date - valuation_date).days / days_per_year

    if total_periods_years <= 0:
        raise ValueError("MIRR requires cash flows spanning multiple periods")

    # Calculate FV of positive flows and PV of negative flows
    fv_positive, pv_negative = _calculate_mirr_components(
        cash_flow, finance_rate, reinvestment_rate, valuation_date, latest_date, year_size
    )

    # Calculate MIRR: (FV_positive / |PV_negative|)^(1/n) - 1
    if pv_negative.is_zero() or fv_positive.is_zero():
        raise ValueError("Cannot calculate MIRR: zero present value or future value")

    ratio = fv_positive.raw_amount / abs(pv_negative.raw_amount)
    if ratio <= 0:
        raise ValueError("Cannot calculate MIRR: invalid cash flow ratio")

    # MIRR = ratio^(1/years) - 1
    mirr_decimal = ratio ** (Decimal("1") / total_periods_years) - Decimal("1")

    # Convert to percentage and create InterestRate
    mirr_percentage = float(mirr_decimal * 100)
    return InterestRate(f"{mirr_percentage:.6f}% annual", year_size=year_size)
