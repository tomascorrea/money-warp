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

## SQLAlchemy (`ext/sa/`)

Custom SQLAlchemy `TypeDecorator` column types and bridge decorators for loan/settlement models.

**Install:** `pip install money-warp[sa]` (adds `sqlalchemy >= 2.0`).

### Package layout

```
money_warp/ext/sa/
  __init__.py   -- re-exports for backward compatibility
  types.py      -- MoneyType, RateType, InterestRateType
  bridge.py     -- settlement_bridge, loan_bridge, _load_money_warp_loan, CTE SQL expression
```

All public symbols are re-exported from `__init__.py`, so `from money_warp.ext.sa import MoneyType, loan_bridge` continues to work.

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
| `"string"` (default) | `String` | `"5.250% annual"` or `"5.250% a.a."` |
| `"json"` | `JSON` | `{"rate": "0.0525", "period": "annually", ...}` |

String serialization respects the Rate's `str_style`: rates with `str_style="abbrev"` are stored with abbreviated tokens (e.g., `"5.250% a.a."`), while `str_style="long"` (the default) uses long tokens (e.g., `"5.250% annual"`). Deserialization handles both formats transparently since `Rate(...)` parses both.

Same deserialization knobs as the Marshmallow `RateField`: `year_size`, `precision`, `rounding`, `str_style`.

### InterestRateType

Subclass of `RateType` with `RATE_CLASS = InterestRate`. Same representations, constructs `InterestRate` on load (rejects negative values).

### settlement_bridge

Class decorator that stores column metadata on a settlement model:

```python
@settlement_bridge(
    balance="remaining_balance",
    date="payment_date",
    amount="amount",
    interest_date="interest_date",
    processing_date="processing_date",
)
```

All params have defaults matching the names above — `@settlement_bridge()` with no args works if you follow the convention. Stores a `_money_warp_bridge_meta` dict on the class.

The `interest_date` and `processing_date` columns are optional on the model. When absent or `None`, `record_payment` uses its own defaults (`interest_date` defaults to `payment_date`, `processing_date` defaults to `self.now()`).

### loan_bridge

Class decorator that adds `balance_at(date)` hybrid method, `balance` hybrid property, and `_load_money_warp_loan(as_of)` method:

```python
@loan_bridge()  # all params default to conventional column names
```

All parameter names default to their conventional column names: `principal`, `settlements`, `interest_rate`, `due_dates`, `disbursement_date`, `fine_rate`, `grace_period_days`, `mora_interest_rate`, `mora_strategy`.

Stores `_money_warp_bridge_meta` on the loan class with all field mappings.

**`_load_money_warp_loan()`** (instance method, no parameters):
- Reads `_money_warp_bridge_meta` from `type(self)`.
- Reconstructs a full `money_warp.Loan` from stored fields, replays settlements with per-payment time warping (loan's `_time_ctx` is overridden to each payment's date before `record_payment`).
- Passes all three dates from settlement metadata: `payment_date`, `interest_date`, `processing_date` (optional ones skipped when `None`).
- Always returns a `Loan` or raises `ValueError` if any required field (`interest_rate`, `due_dates`, `disbursement_date`) is `None`.
- Never returns `None`.

**`balance_at(date)`** (hybrid_method):
- **Python side:** Calls `self._load_money_warp_loan()` to get a reconstructed `Loan`, then uses `Warp(loan, as_of)` context manager to get the balance. Returns exact `Money` value including accrued interest, fines, and mora.
- **SQL side:** CTE-based expression that computes `principal_balance + regular_interest + mora_interest + fines`. Falls back to `COALESCE(remaining_balance, principal)` when `interest_rate` JSON is NULL (defensive guard).

**`balance`** (hybrid_property):
- **Python side:** delegates to `self.balance_at(now())`.
- **SQL side:** delegates to `cls.balance_at(func.now())`.

The settlement model must be decorated with `@settlement_bridge` — `@loan_bridge` reads `_money_warp_bridge_meta` from the relationship target at query time. Raises `TypeError` if missing.

### CTE-based SQL expression architecture

The SQL side of `balance_at` uses nested CTEs (`nesting=True`) inside a single scalar subquery. Each CTE builds on the previous, keeping the computation readable:

| CTE | Purpose |
|-----|---------|
| `loan_state` | `COALESCE(last_remaining_balance, principal)` and `COALESCE(last_payment_date, disbursement_date)`. Uses scalar subqueries so it always returns 1 row even with no settlements. |
| `daily_rates` | Converts rates of any period to daily via `_daily_rate_expr`. Handles all `CompoundingFrequency` values for both JSON and string column representations. NULL mora rate coalesces to 0. |
| `time_split` | Computes `total_days` and finds `next_due` date after last payment via `json_each(due_dates)`. |
| `day_split` | Splits total days into `regular_days` and `mora_days` at the next-due boundary. |
| `accrued` | `regular_interest` (compound on principal) and `mora_interest` (COMPOUND or SIMPLE branching via `mora_strategy`). |
| `late_fines` | Counts late installments (`past_grace_count - settlement_count`), estimates PMT, applies fine rate. |
| Final SELECT | `principal_balance + regular_interest + mora_interest + fines`. |

NULL guard: Falls back to `COALESCE(remaining_balance, principal)` when no rate is present. The check depends on representation: JSON uses `json_extract(interest_rate, '$.rate') IS NULL`; string uses `interest_rate IS NULL`.

### Rate conversion helpers

Private helpers in `bridge.py` convert stored rates to daily rates in SQL, mirroring `Rate._to_effective_annual()` and `Rate.to_daily()`. They support both JSON and string column representations.

**Column introspection:** `_get_rate_col_info(cls, attr_name)` reads the `InterestRateType` from the model's column to determine `representation` ("json" or "string") and `default_year_size`. This happens once at expression-build time — no SQL-side format detection.

**Param extraction:** `_extract_rate_params(rate_col, representation, default_year_size)` returns `(decimal_rate, period, year_size)` as SQL expressions:
- JSON: uses `json_extract` for all three values.
- String: parses `"5.250% annual"` via `SUBSTR`/`INSTR`, divides the percentage by 100; uses the column type's `default_year_size` since the string format does not embed year size.

**Period mapping:** `_periods_per_year_expr(period, year_size, representation)` builds a SQL `CASE` generated from `CompoundingFrequency` — no hardcoded magic numbers. Period names differ by representation (JSON: `"annually"`, `"semi_annually"`; string: both long tokens like `"annual"`, `"semi-annual"` and abbreviated tokens like `"a.a."`, `"a.s."` from `_ABBREV_MAP`). Each frequency generates CASE branches for all its recognized tokens. `CONTINUOUS` is excluded (handled separately via `exp()`). `DAILY` uses `year_size` instead of a fixed value.

**Conversion:** `_effective_annual_expr(rate_col, representation, default_year_size)` and `_daily_rate_expr(rate_col, representation, default_year_size)` combine the above. Both are used by the `daily_rates` CTE for `interest_rate` and `mora_interest_rate` columns. The `continuous` period uses `func.exp()` which requires the SQLite math extension (available in Python 3.11+ / SQLite 3.35+).

**NULL guard:** `_has_rate(rate_col, representation)` returns a SQL expression that is NULL when no parseable rate is present. For JSON: checks `json_extract(rate_col, '$.rate')`; for string: checks the column itself.

## Design Decisions

- **`RATE_CLASS` pattern:** Both Marshmallow and SA extensions use `RATE_CLASS` on the Rate field/type. `InterestRateField`/`InterestRateType` override this to `InterestRate`, avoiding code duplication.
- **Parseable string serialization:** String mode uses `_FREQUENCY_TOKEN` (long tokens) or `_ABBREV_MAP` (abbreviated tokens) depending on the Rate's `str_style`. This avoids using `str(rate)` directly because `Rate.__str__()` outputs `"annually"` / `"semi_annually"` which the Rate parser does not accept. The mapping outputs parser-compatible tokens like `"annual"` / `"semi-annual"` or `"a.a."` / `"a.s."`. Both extensions duplicate the long-token mapping (each is self-contained); `_ABBREV_MAP` is imported from `money_warp.rate`.
- **Private attribute access:** Dict/JSON serialization reads `value._precision`, `value._rounding`, `value._str_style` since there are no public getters. Acceptable because these are first-party extensions.
- **Optional dependencies:** Each extension is declared optional in `pyproject.toml` under `[tool.poetry.extras]`. Importing without the dependency installed raises `ImportError`.
- **Two-decorator bridge pattern:** `@settlement_bridge` stores metadata, `@loan_bridge` reads it. Both store `_money_warp_bridge_meta` (namespaced to avoid collisions). This keeps each model self-describing and avoids passing settlement column names through the loan decorator.
- **`_load_money_warp_loan` always raises or returns:** The method never returns `None`. If required fields are missing, it raises `ValueError` with a clear message. This makes calling code simpler (no `None` checks) and forces data completeness at the model level.
- **Per-loan Warp nesting:** `Warp` tracks active loans by `id(loan)` in a class-level `_active_loans: set`. Warping different `Loan` objects concurrently is allowed, but warping the same `Loan` twice is still blocked with `NestedWarpError`. This enables `balance_at` to use `Warp` internally (it creates a fresh Loan via `_load_money_warp_loan()`, so `id()` is different from any outer-warped loan).
- **Per-payment time warping during replay:** When `_load_money_warp_loan` replays settlements, the loan's `_time_ctx` is overridden to each payment's date via `WarpedTime(pdate)`. This ensures `self.now()` inside `record_payment` returns the correct historical time, affecting late fine calculations and the `processing_date` default.
- **Phantom fine prevention:** `balance_at` clears `fines_applied` on the reconstructed loan before passing it to `Warp`. Without this, fines charged during replay of future settlements would persist when warping to an earlier date (e.g., a fine from a Mar 15 settlement would appear at Jan 15). Clearing forces `Warp.calculate_late_fines(as_of)` to recompute fines purely from the point-in-time state, matching the SQL CTE which computes fines based on settlements and due dates visible at `as_of`.
- **CTE nesting:** `nesting=True` keeps CTEs inside the scalar subquery so correlation to the outer `loans` table works correctly with SQLAlchemy + SQLite.
- **`loan_state` uses scalar subqueries:** Instead of `SELECT FROM last_settlement_cte` (which returns 0 rows when no settlements exist), `loan_state` uses inline scalar subqueries with `COALESCE`. This guarantees exactly 1 row regardless of settlement presence.
- **Cartesian product warnings:** The final SELECT joins multiple single-row CTEs without explicit join conditions. SQLAlchemy warns about cartesian products, but this is intentional and correct since each CTE produces exactly 1 row.
- **`balance_at` + `balance` pattern:** `balance_at(date)` is a `hybrid_method` that accepts a date param. `balance` is a `hybrid_property` that delegates to `balance_at(now())` / `balance_at(func.now())`.
- **Package split rationale:** `types.py` contains pure column type descriptors (no business logic). `bridge.py` contains the loan/settlement decorators and the Loan reconstruction engine. Separation makes each file focused and testable.

## Key Gotchas

- String round-trip loses some precision: the percentage rate is formatted with 3 decimal places (`:.3f`). Rates with more than 3 decimal digits in the percentage form should use dict/json representation for lossless round-trips.
- `None` handling: all type fields pass through `None` in both directions (returns `None`).
- **SQLite precision:** SQLite stores `Numeric` as floating-point internally. Very high-precision raw amounts (> ~10 significant digits) may lose precision. Use PostgreSQL or MySQL for production.
- **SQL expression type asymmetry:** The `balance` hybrid_property returns `Money` on instances but raw `Numeric` in SQL expressions. Filter comparisons use `Decimal`, not `Money`: `LoanRecord.balance > Decimal("1000")`.
- **SQL vs Python precision:** The SQL CTE expression uses float64 arithmetic while Python uses `Decimal`. For exact comparisons in tests, use approximate matching (e.g., `pytest.approx`) when comparing SQL results against Python `balance_at`.
- **JSON NULL vs SQL NULL:** SQLAlchemy's `JSON` type stores Python `None` as the string `'null'` rather than SQL `NULL`. For JSON representation, the NULL guard checks `json_extract(interest_rate, '$.rate') IS NULL` which correctly handles both cases since `json_extract('null', '$.rate')` returns NULL.
- **Mora rate NULL handling:** When `mora_interest_rate` is NULL, the helper functions cascade NULL through `pow()`. The `daily_rates` CTE coalesces the mora daily rate to 0.0 to prevent this from nullifying the entire expression.
- **Data-driven period mapping:** The SQL `CASE` branches in `_periods_per_year_expr` are generated from the `CompoundingFrequency` enum, `_FREQUENCY_TOKEN`, and `_ABBREV_MAP`. Each frequency maps to a list of recognized tokens (long and abbreviated). Adding a new `CompoundingFrequency` member and its tokens automatically extends both JSON and string SQL support.
- **String representation year_size limitation:** The string format (e.g., `"5.250% annual"`) does not embed `year_size`. The SQL helpers use the `rate_year_size` default from the column's `InterestRateType` definition. If different rates on the same column need different year sizes, use JSON representation instead.
- **Continuous compounding in string format:** `CompoundingFrequency.CONTINUOUS` is not in `_FREQUENCY_TOKEN` and cannot be serialized as a string. Use JSON representation for continuous rates.
