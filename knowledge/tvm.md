# Time Value of Money

MoneyWarp provides present value, IRR, and MIRR functions in `present_value.py`, powered by scipy for numerical root-finding. All functions work with `CashFlow` objects and return `Money` or `Rate` instances. IRR and MIRR return `Rate` (not `InterestRate`) because computed metrics can be negative.

## Present Value Functions

### `present_value(cash_flow, discount_rate: Rate, valuation_date=None) -> Money`

Discounts each item in a cash flow stream back to `valuation_date` (defaults to the earliest cash flow date). Accepts any `Rate` (including `InterestRate`) as the discount rate. Uses daily rate conversion for precision: `PV = sum(CF_t / (1 + r_daily)^days)`. Past cash flows (negative days) are treated as same-day.

This function also serves as NPV — there is no separate `net_present_value` function.

### `present_value_of_annuity(payment_amount, interest_rate, periods, payment_timing="end") -> Money`

Closed-form PV of a stream of equal payments:
- Ordinary annuity (`"end"`): `PMT * [(1 - (1 + r)^(-n)) / r]`
- Annuity due (`"begin"`): multiplied by `(1 + r)`
- Zero rate edge case: `PMT * n`

### `present_value_of_perpetuity(payment_amount, interest_rate) -> Money`

`PMT / r`. Raises `ValueError` if rate is zero or negative.

### `discount_factor(interest_rate: Rate, periods) -> Decimal`

`1 / (1 + r)^n`. Accepts any `Rate` (including `InterestRate`). Returns `Decimal` for precision. Supports fractional periods.

## IRR Functions

### `internal_rate_of_return(cash_flow, guess: Rate=None, year_size=YearSize.commercial) -> Rate`

Finds the rate that makes the NPV of the cash flow equal to zero. Returns a `Rate` (not `InterestRate`) because IRR can be negative when fees or costs erode the effective return. The `guess` parameter accepts any `Rate` (including `InterestRate`).

**Algorithm:**
1. Validate: requires both positive and negative cash flows
2. Bracket: `_find_irr_bracket()` tests candidate rates `[-0.5, -0.1, 0.01, 0.05, 0.10, 0.15, 0.25, 0.50, 1.0, 2.0]` looking for a sign change in NPV. Uses `Rate` internally so negative candidates work correctly.
3. Solve: `scipy.optimize.brentq` (primary), falls back to `scipy.optimize.fsolve` if bracketing fails
4. Validate result: NPV at found rate must be within $500 tolerance; rate must be between -99% and 1000%

The `year_size` parameter controls the day-count convention used for daily rate conversions inside the NPV calculation. `YearSize.commercial` (365, default) or `YearSize.banker` (360). The returned `Rate` carries the same `year_size`.

`irr()` is a convenience alias (also accepts `year_size`).

### `modified_internal_rate_of_return(cash_flow, finance_rate: InterestRate, reinvestment_rate: InterestRate, year_size=YearSize.commercial) -> Rate`

MIRR separates the cost of capital from the reinvestment rate:
- Negative cash flows are discounted at `finance_rate` to get PV
- Positive cash flows are compounded at `reinvestment_rate` to get FV
- `MIRR = (FV / |PV|)^(1/n) - 1` where `n` is in annual periods (`days / year_size.value`)

Input rates (`finance_rate`, `reinvestment_rate`) are `InterestRate` (contractual). The result is a `Rate` because MIRR can theoretically be negative. The `year_size` parameter controls the year-fraction denominator for period calculations.

## Scipy Integration

The library uses scipy rather than a hand-rolled Newton-Raphson because:
- `brentq` is guaranteed to converge when a bracket exists
- `fsolve` handles cases where no clean bracket is found
- Numpy array outputs from scipy solvers are handled via `.item()` conversion

## Loan Sugar Syntax

`loan.present_value()` and `loan.irr()` are convenience methods that generate the loan's expected cash flow and delegate to the module-level functions. Both default to the loan's own interest rate and `loan.now()`, making them time-aware inside a `Warp` context. `loan.irr()` returns a `Rate` (not `InterestRate`) and automatically passes the loan's `interest_rate.year_size` to `internal_rate_of_return`, so loans configured with `YearSize.banker` will compute IRR using 360-day years.
