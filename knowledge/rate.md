# Rate vs InterestRate vs Percentage

MoneyWarp distinguishes between three rate-like types based on domain semantics. The first two model **temporal** rates (rates per unit of time); the third models a **non-temporal** percentage applied flat over a value.

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

## Percentage (non-temporal, `percentage.py`)

`Percentage` is a separate type — **not** a subclass of `Rate` / `InterestRate` — for non-negative percentages applied flat over a value, with no temporal dimension and no compounding. Typical examples: MDR (partner rate), late-payment fines (`fine_rate`), IOF flat components, and similar value-based fees.

**When to use:** any rate where the operation is `valor × taxa` and ends there — no period, no capitalization, no equivalence between monthly and annual.

### Why a separate type (and not `CompoundingFrequency.FLAT`)

The original proposal was to add a `FLAT` member to `CompoundingFrequency` and make `to_daily`/`to_monthly`/`accrue` raise `ValueError` when the period was `FLAT`. That approach was rejected:

- **Liskov violation:** an `InterestRate(period=FLAT)` that rejects `to_daily/to_monthly` is not substitutable for a regular `InterestRate`. Any caller that received `InterestRate` and called `to_*` would crash at runtime.
- **Footgun in runtime, not compile-time:** the type checker would still offer `to_daily`, `accrue`, etc. on a flat rate. The error would only surface in production.
- **Comparison ambiguity:** `flat 5%` vs `monthly 5%` via `_to_effective_annual` has no defined semantics.
- **Conceptual:** "interest rate" is a quantity per unit of time by mathematical definition. A flat percentage is not an interest rate — it is just a percentage applied over a value.

A separate type makes the type checker (mypy/IDE) block `pct.to_daily()`, `pct.accrue(...)`, and `pct.apply(...)` before runtime, with no need for a runtime guard.

### Construction is string-only

`Percentage` accepts **only** strings of the form `"<number>%"`. Numeric inputs and bare strings without `%` are rejected:

```python
Percentage("5%")          # OK → 0.05
Percentage("5.5%")        # OK → 0.055
Percentage("0%")          # OK → 0
Percentage(5)             # TypeError — numeric not accepted
Percentage(0.05)          # TypeError — numeric not accepted
Percentage("5")           # ValueError — missing '%'
Percentage("0.05")        # ValueError — missing '%'
Percentage("-5%")         # ValueError — negative not allowed
Percentage("5% a.a.")     # ValueError — temporal suffix → use Rate/InterestRate
```

The reason: `Percentage(5)` is ambiguous (is it `5%` or `500%`?). The literal `%` in the string is the only unambiguous contract. This intentionally differs from `Rate`/`InterestRate`, which accept both numeric and string forms via `as_percentage=True`.

### API is intentionally minimal

| Method | Returns | Notes |
|---|---|---|
| `as_decimal(precision=None)` | `Decimal` | `Percentage("5%").as_decimal()` → `Decimal("0.05")` |
| `as_percentage(precision=None)` | `Decimal` | `Percentage("5%").as_percentage()` → `Decimal("5")` |

There is **no** `apply(money)`, `as_float`, `to_daily`, `to_monthly`, `to_annual`, `to_periodic_rate`, `accrue`, or `_to_effective_annual`. Application over `Money` is the consumer's responsibility:

```python
mdr = Percentage("5%")
fee = Money(amount.raw_amount * mdr.as_decimal())
```

This keeps the boundary between "I have a percentage" and "I'm computing a fee in money" visible at every call site.

### Display

- `__str__`: canonical `"5.00%"` (round-trip stable: `Percentage(str(p)) == p`).
- `__repr__`: `Percentage('5.00%')`.
- `str_decimals` constructor kwarg controls the number of decimal places in `__str__`. Default is `2` (matches typical financial display); use `4` or more for high-precision percentages.

### Comparisons

`Percentage` supports `==`, `<`, `<=`, `>`, `>=`, `__hash__` between two `Percentage` instances. Cross-comparison with `Rate` / `InterestRate` returns `NotImplemented` from the `Percentage` side (so `==` is `False`); ordering then falls through to `Rate.__gt__` etc. and currently raises `AttributeError` because `Rate` does not type-check its operand. The net effect is the desired one — they cannot be compared — but the exact exception is not specified.

### Quick decision table

| Case | Type | Justification |
|---|---|---|
| MDR (partner rate) | `Percentage` | Applied once over the operation amount. No capitalization, no period. |
| Fine (`fine_rate`) | `Percentage` | Applied once over the overdue amount. No capitalization. |
| IOF flat component | `Percentage` | Percentage applied once over the value. |
| Contractual interest rate | `InterestRate` | Has a temporal dimension, capitalizes, ≥ 0. |
| Late-payment interest rate | `InterestRate` | Capitalizes over days of delay. |
| IRR / MIRR | `Rate` | Computed metric, may be negative, has a temporal dimension. |
