# Timezone Configuration (tz)

The `tz` module centralises all timezone handling for MoneyWarp. It implements a **two-timezone architecture**: all internal datetimes are stored in UTC, while calendar-date extraction uses a **per-loan business timezone** (defaulting to the global `get_tz()`).

## Design Decisions

### Two-Timezone Architecture

The module distinguishes two concerns:

1. **Storage timezone** -- always UTC. `ensure_aware` converts every incoming datetime to UTC before it is stored or used internally.
2. **Business timezone** -- per-loan, stored in `TimeContext.tz`. `to_date(dt, tz)` converts a UTC datetime to the business timezone before extracting the calendar date.

This separation guarantees that a Brazilian user operating in `America/Sao_Paulo` can pass a BRT datetime, have it stored as UTC internally, and still get the correct BRT calendar date when the library computes due dates and day counts.

### Per-Loan Timezone

Each `Loan` and `BillingCycleLoan` carries its own business timezone via `TimeContext.tz`. The `tz` parameter on `__init__` accepts a string (`"America/Sao_Paulo"`) or a `tzinfo` instance; when omitted it defaults to `get_tz()`.

Two loans with different timezones coexist without interference:

```python
brt_loan = Loan(..., tz="America/Sao_Paulo")
tokyo_loan = Loan(..., tz="Asia/Tokyo")
```

The timezone flows from `Loan._time_ctx.tz` into every internal function: engine functions, schedulers, tax, and billing cycle methods all receive `tz` as a **required** parameter. No internal function falls back to the global `_default_tz`.

### UTC Storage via `ensure_aware`

`ensure_aware` handles two cases, both producing UTC:

- **Naive datetimes**: interpreted as being in the global business timezone (`_default_tz`), then converted to UTC. `dt.replace(tzinfo=_default_tz).astimezone(timezone.utc)`.
- **Aware datetimes**: converted to UTC directly via `dt.astimezone(timezone.utc)`.

Example: `datetime(2024, 1, 15, 23, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))` becomes `datetime(2024, 1, 16, 2, 0, tzinfo=UTC)`.

### Business-Date Extraction via `to_date`

`to_date(dt, tz)` converts a datetime to the given timezone before calling `.date()`. The `tz` parameter is **required** -- there is no global fallback. Plain `date` inputs pass through unchanged.

Example: `to_date(datetime(2024, 1, 16, 2, 0, tzinfo=UTC), ZoneInfo("America/Sao_Paulo"))` returns `date(2024, 1, 15)`.

### `to_datetime` Conversion

`to_datetime(d, tz)` creates midnight on date `d` in the given timezone, then converts to UTC. Combined with `to_date`, it round-trips: `to_date(to_datetime(d, tz), tz) == d`.

### Round-Trip Integrity

The pair `ensure_aware` + `to_date` preserves calendar dates:

```
tz = ZoneInfo("America/Sao_Paulo")
stored = ensure_aware(datetime(2024, 1, 15, 22, 0, 0, tzinfo=tz))  # -> UTC
to_date(stored, tz)  # -> date(2024, 1, 15)
```

### `now()` Returns Business Timezone

`now()` returns `datetime.now(_default_tz)` -- the current wall-clock time in the global business timezone. When this value passes through `@tz_aware`, `ensure_aware` converts it to UTC. Library code uses `self._time_ctx.to_date(self.now())` for calendar-date extraction.

### All `.date()` Calls Use `to_date()`

Every `.date()` call on a datetime inside the library has been replaced with `to_date(dt, tz)` (or `self._time_ctx.to_date(dt)` in loan/BCL methods). This ensures consistent business-day extraction.

### Default `disbursement_date` Normalisation

When `disbursement_date` is not provided, both `Loan` and `BillingCycleLoan` wrap the default with `ensure_aware(self._time_ctx.now())` so that the stored value is always UTC.

### Boundary Coercion via Decorator

The `@tz_aware` decorator is applied to public functions and methods that accept datetime arguments. At call time it inspects `BoundArguments` and coerces:

- `datetime` values through `ensure_aware` (-> UTC)
- `list` values whose first element is a `datetime` element-wise

Everything else (including `None` for optional params) passes through untouched. Lists are only coerced when the first element is a `datetime`; `List[date]` arguments (e.g. loan `due_dates`) are left as-is.

Note: `@tz_aware` runs before `self._time_ctx` exists, so it uses `ensure_aware` (which depends on the global `_default_tz` for naive datetime interpretation). The per-loan `tz` is for **date extraction** (`to_date`), not for **naive stamping** (`ensure_aware`). When using multiple timezones, pass timezone-aware datetimes.

### No New Dependencies

Uses `zoneinfo.ZoneInfo` from the standard library (Python 3.9+).

## API Surface

| Symbol | Kind | Description |
|---|---|---|
| `get_tz()` | function | Return the current global business timezone (`tzinfo`) |
| `set_tz(tz)` | function | Set the global business timezone (string or `tzinfo`) |
| `now()` | function | `datetime.now(get_tz())` -- always aware, in business tz |
| `ensure_aware(dt)` | function | Normalise to UTC: naive -> stamp global business tz -> UTC; aware -> UTC |
| `to_date(dt, tz)` | function | Calendar `date` in `tz` from a `datetime`, or pass through `date`. `tz` is required. |
| `to_datetime(d, tz)` | function | Midnight on `d` in `tz`, returned as UTC-aware `datetime`. `tz` is required. |
| `tz_aware` | decorator | Coerce all datetime args to UTC via `ensure_aware` |
| `default_time_source` | instance | `_DefaultTimeSource` whose `.now()` delegates to `now()` |

### TimeContext

| Attribute/Method | Description |
|---|---|
| `TimeContext.tz` | Business timezone for this context (per-loan) |
| `TimeContext.to_date(dt)` | `to_date(dt, self.tz)` |
| `TimeContext.to_datetime(d)` | `to_datetime(d, self.tz)` |
| `TimeContext.now()` | Current time from the source (or warped time) |
| `TimeContext.override(source)` | Replace the time source (used by Warp) |

### Loan / BillingCycleLoan

Both accept `tz: Optional[Union[str, tzinfo]] = None` in their constructors. When omitted, defaults to `get_tz()`. The resolved timezone is stored in `self._time_ctx.tz` and threaded to all internal calls.

## Where `@tz_aware` Is Applied

- `Loan.__init__`, `record_payment`, `is_payment_late`, `present_value`
- `BillingCycleLoan.__init__`, `record_payment`, `is_late`
- `CashFlowItem.__init__`
- All `date_utils` generator functions
- `present_value()` in `present_value.py`

`Warp._parse_date` uses `ensure_aware` for datetime/string inputs and `to_datetime(target_date, tz)` for plain date inputs (using the loan's per-loan timezone).

## Key Learnings / Gotchas

- **`ensure_aware` always returns UTC.** Do not assume the result is in the business timezone. Use `to_date(dt, tz)` to extract business-day dates.
- **Never call `.date()` on a datetime.** Always use `to_date()`. Direct `.date()` calls give UTC dates, which differ from business dates when the loan uses a non-UTC timezone.
- **`to_date` and `to_datetime` require `tz`.** No global fallback. Internal functions get `tz` from their callers; loan methods use `self._time_ctx.tz`.
- Comparing an aware datetime with a naive datetime raises `TypeError`. The decorator guarantees this never happens inside the library.
- `CashFlowQuery._apply_datetime_filter` also calls `ensure_aware` on the filter value.
- For naive datetimes, `ensure_aware` uses `dt.replace(tzinfo=...)` then `.astimezone(UTC)`. The wall-clock interpretation depends on the **global** business timezone (`_default_tz`), not the per-loan timezone.
- `set_tz` controls naive datetime interpretation globally. The per-loan `tz` controls date extraction only.
- Two loans with different timezones can coexist. Each uses its own `TimeContext.tz` without affecting the other.
- Warp interprets plain `date` targets in the loan's per-loan timezone (midnight in that timezone, converted to UTC).
