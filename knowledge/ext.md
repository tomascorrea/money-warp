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

## SQLAlchemy (`ext/sa.py`)

Custom SQLAlchemy `TypeDecorator` column types and bridge decorators for loan/settlement models.

**Install:** `pip install money-warp[sa]` (adds `sqlalchemy >= 2.0`).

### MoneyType

`TypeDecorator` storing `Money` instances. Configurable `representation` parameter:

| Representation | Column type | Bind (Money -> DB) | Result (DB -> Money) |
|----------------|-------------|---------------------|----------------------|
| `"raw"` (default) | `Numeric(20,10)` | `money.raw_amount` | `Money(value)` |
| `"real"` | `Numeric(20,10)` | `money.real_amount` | `Money(value)` |
| `"cents"` | `Integer` | `money.cents` | `Money.from_cents(value)` |

`process_bind_param` also accepts raw `Decimal`/`int`/`float` values (passthrough) so that SQL expression comparisons like `LoanRecord.balance > Decimal("1000")` work without wrapping in `Money`.

### RateType

`TypeDecorator` storing `Rate` instances. Configurable `representation` parameter:

| Representation | Column type | Example stored value |
|----------------|-------------|--------------------------------------|
| `"string"` (default) | `String` | `"5.250% annual"` |
| `"json"` | `JSON` | `{"rate": "0.0525", "period": "annually", ...}` |

Same deserialization knobs as the Marshmallow `RateField`: `year_size`, `precision`, `rounding`, `str_style`.

### InterestRateType

Subclass of `RateType` with `RATE_CLASS = InterestRate`. Same representations, constructs `InterestRate` on load (rejects negative values).

### settlement_bridge

Class decorator that stores column metadata on a settlement model:

```python
@settlement_bridge(balance="remaining_balance", date="payment_date", amount="amount")
```

All params have defaults matching the names above — `@settlement_bridge()` with no args works if you follow the convention. Stores a `_money_warp_bridge_meta` dict on the class.

### loan_bridge

Class decorator that adds `balance_at(date)` hybrid method and `balance` hybrid property:

```python
@loan_bridge(principal="principal", settlements="settlements")
```

Stores `_money_warp_bridge_meta` on the loan class with `{"principal": ..., "settlements": ...}`.

**`balance_at(date)`** (hybrid_method):
- **Python side:** returns `remaining_balance` from the last settlement whose date is `<= date`, or `principal` if none qualify. Uses `ensure_aware()` for tz-safe comparison.
- **SQL side:** correlated subquery with `WHERE payment_date <= :date` and `COALESCE` fallback to principal.

**`balance`** (hybrid_property):
- **Python side:** delegates to `self.balance_at(now())`.
- **SQL side:** delegates to `cls.balance_at(func.now())`.

The settlement model must be decorated with `@settlement_bridge` — `@loan_bridge` reads `_money_warp_bridge_meta` from the relationship target at query time. Raises `TypeError` if missing.

## Design Decisions

- **`RATE_CLASS` pattern:** Both Marshmallow and SA extensions use `RATE_CLASS` on the Rate field/type. `InterestRateField`/`InterestRateType` override this to `InterestRate`, avoiding code duplication.
- **Parseable string serialization:** String mode uses `_FREQUENCY_TOKEN` mapping instead of `str(rate)` because `Rate.__str__()` outputs `"annually"` / `"semi_annually"` which the Rate parser does not accept. The mapping outputs parser-compatible tokens like `"annual"` and `"semi-annual"`. Both extensions duplicate this mapping (each is self-contained).
- **Private attribute access:** Dict/JSON serialization reads `value._precision`, `value._rounding`, `value._str_style` since there are no public getters. Acceptable because these are first-party extensions.
- **Optional dependencies:** Each extension is declared optional in `pyproject.toml` under `[tool.poetry.extras]`. Importing without the dependency installed raises `ImportError`.
- **Two-decorator bridge pattern:** `@settlement_bridge` stores metadata, `@loan_bridge` reads it. Both store `_money_warp_bridge_meta` (namespaced to avoid collisions). This keeps each model self-describing and avoids passing settlement column names through the loan decorator.
- **`balance_at` + `balance` pattern:** `balance_at(date)` is a `hybrid_method` that accepts a date param. `balance` is a `hybrid_property` that delegates to `balance_at(now())` / `balance_at(func.now())`. The SQL expression introspects the relationship at query time to discover the FK, balance column, and date column from `_money_warp_bridge_meta`.

## Key Gotchas

- String round-trip loses some precision: the percentage rate is formatted with 3 decimal places (`:.3f`). Rates with more than 3 decimal digits in the percentage form should use dict/json representation for lossless round-trips.
- `None` handling: all fields/types pass through `None` in both directions (returns `None`).
- **SQLite precision:** SQLite stores `Numeric` as floating-point internally. Very high-precision raw amounts (> ~10 significant digits) may lose precision. Use PostgreSQL or MySQL for production.
- **SQL expression type asymmetry:** The `balance` hybrid_property returns `Money` on instances but raw `Numeric` in SQL expressions. Filter comparisons use `Decimal`, not `Money`: `LoanRecord.balance > Decimal("1000")`.
