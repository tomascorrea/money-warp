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
- **Accessors:** `as_decimal(precision=None)`, `as_percentage(precision=None)`, `as_float(precision=None)` — all are methods (not properties). When `precision` is given, the result is quantized/rounded to that many decimal places.
- **Conversions:** `to_daily()`, `to_monthly()`, `to_annual()`, `to_periodic_rate(n)`
- **Comparisons:** `==`, `<`, `<=`, `>`, `>=` (via effective annual rate)
- **Year size:** `YearSize.commercial` (365, default) or `YearSize.banker` (360)

Conversion methods use `self.__class__(...)` so `InterestRate.to_monthly()` returns an `InterestRate` and `Rate.to_monthly()` returns a `Rate`.

### Accessor Details

| Method | Return type | No precision | With precision |
|---|---|---|---|
| `as_decimal()` | `Decimal` | Raw stored rate (e.g. `Decimal("0.0525")`) | Quantized via `ROUND_HALF_UP` (or the rate's configured rounding) |
| `as_percentage()` | `Decimal` | Raw percentage (e.g. `Decimal("5.25")`) | Same quantization behaviour |
| `as_float()` | `float` | `float(raw_rate)` | `round(float_value, precision)` |

`as_float(precision)` is a convenience that replaces the verbose `round(float(rate.as_decimal()), n)` pattern commonly needed for JSON serialization and API responses.

## Cross-Type Compatibility

Since `InterestRate` IS-A `Rate`, any function that accepts `Rate` also accepts `InterestRate`. Comparisons work across types: `Rate("-1% annual") < InterestRate("1% annual")`.

## Display Formatting

Both types support configurable display formatting via two constructor parameters:

- **`str_decimals: int = 3`** — controls the number of decimal places in `__str__`. Default 3 gives `"5.250%"`, use 2 for `"5.25%"`, etc.
- **`abbrev_labels: Optional[Dict[CompoundingFrequency, str]] = None`** — partial or full override of the default abbreviation map (`_ABBREV_MAP`). Merged with the defaults so you only pass keys you want to change. Example: `{CompoundingFrequency.MONTHLY: "a.m"}` drops the trailing dot for monthly.

Both parameters propagate through `to_daily()`, `to_monthly()`, and `to_annual()`. They are display-only and do not affect arithmetic, conversions, or equality.

The extensions (SQLAlchemy `RateType`/`InterestRateType` and Marshmallow `RateField`/`InterestRateField`) accept these parameters as column-type / field-level defaults and include them in JSON/dict round-trips.

## Enums and Shared Constants

`YearSize`, `CompoundingFrequency`, and abbreviation maps are defined in `rate.py` and re-exported from `interest_rate.py` for backward compatibility. Imports from either module work.
