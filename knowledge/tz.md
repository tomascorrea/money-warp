# Timezone Configuration (tz)

The `tz` module centralises all timezone handling for MoneyWarp. It implements a **two-timezone architecture**: all internal datetimes are stored in UTC, while calendar-date extraction uses the configured business timezone (UTC by default).

## Design Decisions

### Two-Timezone Architecture

The module distinguishes two concerns:

1. **Storage timezone** — always UTC. `ensure_aware` converts every incoming datetime to UTC before it is stored or used internally.
2. **Business timezone** — configurable via `set_tz()`, defaults to UTC. `to_date` converts a UTC datetime to the business timezone before extracting the calendar date.

This separation guarantees that a Brazilian user operating in `America/Sao_Paulo` can pass a BRT datetime, have it stored as UTC internally, and still get the correct BRT calendar date when the library computes due dates and day counts.

### UTC Storage via `ensure_aware`

`ensure_aware` handles two cases, both producing UTC:

- **Naive datetimes**: interpreted as being in the business timezone (`_default_tz`), then converted to UTC. `dt.replace(tzinfo=_default_tz).astimezone(timezone.utc)`.
- **Aware datetimes**: converted to UTC directly via `dt.astimezone(timezone.utc)`.

Example: `datetime(2024, 1, 15, 23, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))` becomes `datetime(2024, 1, 16, 2, 0, tzinfo=UTC)`.

### Business-Date Extraction via `to_date`

`to_date` converts a datetime to the business timezone before calling `.date()`. This ensures the extracted date reflects the correct business day. Plain `date` inputs pass through unchanged.

Example with `set_tz("America/Sao_Paulo")`: `to_date(datetime(2024, 1, 16, 2, 0, tzinfo=UTC))` returns `date(2024, 1, 15)` — the correct BRT calendar day.

### Round-Trip Integrity

The pair `ensure_aware` + `to_date` preserves calendar dates:

```
set_tz("America/Sao_Paulo")
naive = datetime(2024, 1, 15, 22, 0, 0)    # interpreted as BRT
stored = ensure_aware(naive)                 # → 2024-01-16 01:00 UTC
to_date(stored)                              # → date(2024, 1, 15) ✓
```

Similarly, `to_datetime(d)` creates midnight in the business timezone then converts to UTC, and `to_date(to_datetime(d))` round-trips back to `d`.

### `now()` Returns Business Timezone

`now()` returns `datetime.now(_default_tz)` — the current wall-clock time in the business timezone. When this value passes through `@tz_aware` (e.g. as a `payment_date` argument), `ensure_aware` converts it to UTC. Library code uses `to_date(self.now())` for calendar-date extraction.

### All `.date()` Calls Use `to_date()`

Every `.date()` call on a datetime inside the library has been replaced with `to_date()`. This ensures consistent business-day extraction regardless of whether the datetime is in UTC (from storage) or business-tz (from `now()`).

### Default `disbursement_date` Normalisation

When `disbursement_date` is not provided, both `Loan` and `BillingCycleLoan` wrap the default with `ensure_aware(self._time_ctx.now())` so that the stored value is always UTC, matching datetimes that pass through `@tz_aware`.

### Boundary Coercion via Decorator

The `@tz_aware` decorator is applied to public functions and methods that accept datetime arguments. At call time it inspects `BoundArguments` and coerces:

- `datetime` values through `ensure_aware` (→ UTC)
- `list` values whose first element is a `datetime` element-wise

Everything else (including `None` for optional params) passes through untouched. Lists are only coerced when the first element is a `datetime`; `List[date]` arguments (e.g. loan `due_dates`) are left as-is.

### No New Dependencies

Uses `zoneinfo.ZoneInfo` from the standard library (Python 3.9+). The project requires Python 3.10+, so no extra package is needed.

## API Surface

| Symbol | Kind | Description |
|---|---|---|
| `get_tz()` | function | Return the current business timezone (`tzinfo`) |
| `set_tz(tz)` | function | Set the business timezone (string or `tzinfo`) |
| `now()` | function | `datetime.now(get_tz())` — always aware, in business tz |
| `ensure_aware(dt)` | function | Normalise to UTC: naive → stamp business tz → UTC; aware → UTC |
| `to_date(dt)` | function | Calendar `date` in the business tz from a `datetime`, or pass through `date` |
| `to_datetime(d)` | function | Midnight on `d` (business tz) as a UTC-aware `datetime` |
| `tz_aware` | decorator | Coerce all datetime args to UTC via `ensure_aware` |
| `default_time_source` | instance | `_DefaultTimeSource` whose `.now()` delegates to `now()` |

## Where `@tz_aware` Is Applied

- `Loan.__init__`, `record_payment`, `is_payment_late`, `present_value`
- `BillingCycleLoan.__init__`, `record_payment`, `is_late`
- `CashFlowItem.__init__`
- All `date_utils` generator functions
- `present_value()` in `present_value.py`

`Warp._parse_date` uses `ensure_aware` directly because the coercion applies to the parsed result rather than to the raw input argument.

## Key Learnings / Gotchas

- **`ensure_aware` always returns UTC.** Do not assume the result is in the business timezone. Use `to_date()` to extract business-day dates.
- **Never call `.date()` on a datetime.** Always use `to_date()`. Direct `.date()` calls give UTC dates, which differ from business dates when `set_tz()` is non-UTC.
- Comparing an aware datetime with a naive datetime raises `TypeError`. The decorator guarantees this never happens inside the library.
- `CashFlowQuery._apply_datetime_filter` also calls `ensure_aware` on the filter value.
- For naive datetimes, `ensure_aware` uses `dt.replace(tzinfo=...)` then `.astimezone(UTC)`. The wall-clock interpretation depends on the configured business timezone.
- `set_tz` should be called once at startup. Changing it mid-flight alters how `to_date` interprets stored UTC datetimes, which could produce inconsistent calendar dates.
- Mixed timezones in comparisons are safe: Python compares aware datetimes by instant regardless of timezone representation.
