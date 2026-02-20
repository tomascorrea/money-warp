# Time Value of Money

MoneyWarp provides present value, IRR, and MIRR functions in `present_value.py`, powered by scipy for numerical root-finding. All functions work with `CashFlow` objects and return `Money` or `InterestRate` instances.

## Present Value Functions

### `present_value(cash_flow, discount_rate, valuation_date=None) -> Money`

Discounts each item in a cash flow stream back to `valuation_date` (defaults to the earliest cash flow date). Uses daily rate conversion for precision: `PV = sum(CF_t / (1 + r_daily)^days)`. Past cash flows (negative days) are treated as same-day.

This function also serves as NPV — there is no separate `net_present_value` function.

### `present_value_of_annuity(payment_amount, interest_rate, periods, payment_timing="end") -> Money`

Closed-form PV of a stream of equal payments:
- Ordinary annuity (`"end"`): `PMT * [(1 - (1 + r)^(-n)) / r]`
- Annuity due (`"begin"`): multiplied by `(1 + r)`
- Zero rate edge case: `PMT * n`

### `present_value_of_perpetuity(payment_amount, interest_rate) -> Money`

`PMT / r`. Raises `ValueError` if rate is zero or negative.

### `discount_factor(interest_rate, periods) -> Decimal`

`1 / (1 + r)^n`. Returns `Decimal` for precision. Supports fractional periods.

## IRR Functions

### `internal_rate_of_return(cash_flow, guess=None) -> InterestRate`

Finds the rate that makes the NPV of the cash flow equal to zero.

**Algorithm:**
1. Validate: requires both positive and negative cash flows
2. Bracket: `_find_irr_bracket()` tests candidate rates `[-0.5, -0.1, 0.01, 0.05, 0.10, 0.15, 0.25, 0.50, 1.0, 2.0]` looking for a sign change in NPV
3. Solve: `scipy.optimize.brentq` (primary), falls back to `scipy.optimize.fsolve` if bracketing fails
4. Validate result: NPV at found rate must be within $500 tolerance; rate must be between -99% and 1000%

`irr()` is a convenience alias.

### `modified_internal_rate_of_return(cash_flow, finance_rate, reinvestment_rate) -> InterestRate`

MIRR separates the cost of capital from the reinvestment rate:
- Negative cash flows are discounted at `finance_rate` to get PV
- Positive cash flows are compounded at `reinvestment_rate` to get FV
- `MIRR = (FV / |PV|)^(1/n) - 1` where `n` is in annual periods (`days / 365.25`)

## Scipy Integration

The library uses scipy rather than a hand-rolled Newton-Raphson because:
- `brentq` is guaranteed to converge when a bracket exists
- `fsolve` handles cases where no clean bracket is found
- Numpy array outputs from scipy solvers are handled via `.item()` conversion

## Loan Sugar Syntax

`loan.present_value()` and `loan.irr()` are convenience methods that generate the loan's expected cash flow and delegate to the module-level functions. Both default to the loan's own interest rate and `loan.now()`, making them time-aware inside a `Warp` context.
