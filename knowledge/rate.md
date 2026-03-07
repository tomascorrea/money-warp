# Rate vs InterestRate

MoneyWarp distinguishes between two rate types based on domain semantics.

## Rate (base type, `rate.py`)

`Rate` is a signed, general-purpose financial rate. It supports positive, negative, and zero values, making it the correct type for computed metrics like IRR and MIRR where the result may be negative (e.g., when fees erode the effective return below zero).

**When to use:** return values from `irr()`, `internal_rate_of_return()`, `modified_internal_rate_of_return()`, discount rates passed to `present_value()` and `discount_factor()`, or any context where the rate is a computed output rather than a contractual input.

## InterestRate (refinement, `interest_rate.py`)

`InterestRate` inherits from `Rate` and adds a single constraint: the rate must be non-negative. This models the domain truth that a contractual interest rate — the cost a lender charges for lending money — cannot be negative.

**When to use:** loan terms (`Loan.interest_rate`, `Loan.mora_interest_rate`), scheduler inputs, annuity/perpetuity calculations, MIRR input rates (`finance_rate`, `reinvestment_rate`), or any context where the rate represents a contractual parameter.

`InterestRate` also provides the `accrue(principal, days)` method for computing compound interest — a concept that belongs exclusively to contractual rates.

## Shared Behaviour

Both types share the same conversion, comparison, and display logic (inherited from `Rate`):

- **String parsing:** `"5.25% a"`, `"0.5% a.m."`, `"-2.5% annual"` (negatives only valid for `Rate`)
- **Conversions:** `to_daily()`, `to_monthly()`, `to_annual()`, `to_periodic_rate(n)`
- **Comparisons:** `==`, `<`, `<=`, `>`, `>=` (via effective annual rate)
- **Year size:** `YearSize.commercial` (365, default) or `YearSize.banker` (360)

Conversion methods use `self.__class__(...)` so `InterestRate.to_monthly()` returns an `InterestRate` and `Rate.to_monthly()` returns a `Rate`.

## Cross-Type Compatibility

Since `InterestRate` IS-A `Rate`, any function that accepts `Rate` also accepts `InterestRate`. Comparisons work across types: `Rate("-1% annual") < InterestRate("1% annual")`.

## Enums and Shared Constants

`YearSize`, `CompoundingFrequency`, and abbreviation maps are defined in `rate.py` and re-exported from `interest_rate.py` for backward compatibility. Imports from either module work.
