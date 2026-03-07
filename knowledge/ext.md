# Extensions (`money_warp/ext/`)

The `ext` package provides opt-in integrations with third-party serialization libraries. Each integration lives in its own module and requires an optional dependency.

## Marshmallow (`ext/marshmallow.py`)

Custom Marshmallow fields for `Money`, `Rate`, and `InterestRate`.

**Install:** `pip install money-warp[marshmallow]` (adds `marshmallow >= 3.20`).

### MoneyField

Serializes/deserializes `Money` instances. Configurable `representation` parameter:

| Representation | Serialized type | Serialize logic           | Deserialize logic      |
|----------------|-----------------|---------------------------|------------------------|
| `"raw"` (default) | `str`       | `str(money.raw_amount)`   | `Money(value)`         |
| `"real"`       | `str`           | `str(money.real_amount)`  | `Money(value)`         |
| `"cents"`      | `int`           | `money.cents`             | `Money.from_cents(value)` |

### RateField

Serializes/deserializes `Rate` instances. Configurable `representation` parameter:

| Representation    | Serialized type | Example output                                     |
|-------------------|-----------------|----------------------------------------------------|
| `"string"` (default) | `str`       | `"5.250% annual"`                                  |
| `"dict"`          | `dict`          | `{"rate": "0.0525", "period": "annually", ...}`    |

**String mode** outputs a parseable format (`"5.250% annual"`) that feeds directly back into `Rate(...)`. Field-level defaults (`year_size`, `precision`, `rounding`, `str_style`) are applied on deserialization.

**Dict mode** captures all constructor params (`rate`, `period`, `year_size`, `precision`, `rounding`, `str_style`) for lossless reconstruction.

### InterestRateField

Inherits from `RateField` with `RATE_CLASS = InterestRate`. Same representations, but constructs `InterestRate` on deserialization (rejects negative values).

## Design Decisions

- **`RATE_CLASS` pattern:** `RateField` uses `self.RATE_CLASS(...)` to construct instances. `InterestRateField` overrides this to `InterestRate`, avoiding code duplication.
- **Parseable string serialization:** String mode uses `_FREQUENCY_TOKEN` mapping instead of `str(rate)` because `Rate.__str__()` outputs `"annually"` / `"semi_annually"` which the Rate parser does not accept. The mapping outputs parser-compatible tokens like `"annual"` and `"semi-annual"`.
- **Private attribute access:** Dict serialization reads `value._precision`, `value._rounding`, `value._str_style` since there are no public getters. Acceptable because this is a first-party extension.
- **Optional dependency:** Marshmallow is declared optional in `pyproject.toml` under `[tool.poetry.extras]`. Importing `money_warp.ext.marshmallow` without marshmallow installed raises `ImportError`.

## Key Gotchas

- String round-trip loses some precision: the percentage rate is formatted with 3 decimal places (`:.3f`). Rates with more than 3 decimal digits in the percentage form should use dict representation for lossless round-trips.
- `None` handling: all fields pass through `None` in both serialize and deserialize (returns `None`).
