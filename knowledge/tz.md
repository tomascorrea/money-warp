# Timezone Configuration (tz)

The `tz` module centralises all timezone handling for MoneyWarp. Every datetime produced or stored by the library is timezone-aware and normalised to the configured timezone (UTC by default).

## Design Decisions

### UTC by Default, Configurable

The module-level default timezone starts as `timezone.utc`. Callers can change it globally with `set_tz("America/Sao_Paulo")` or `set_tz(some_tzinfo)`. The change affects `now()`, `ensure_aware()`, `to_date()`, and the `tz_aware` decorator — all of which read `get_tz()` at call time.

The configured timezone acts as the **business timezone** — the timezone in which calendar dates are interpreted. All internal datetimes are stored in this timezone so that `.date()` extractions yield the correct business day.

### Timezone Normalisation in `ensure_aware`

`ensure_aware` handles two cases:

- **Naive datetimes**: stamped with the configured timezone via `dt.replace(tzinfo=...)`. Wall-clock time is preserved; the datetime is interpreted as being in the configured timezone.
- **Aware datetimes**: converted to the configured timezone via `dt.astimezone(get_tz())`. The instant is preserved; wall-clock time adjusts to reflect the configured timezone.

This means a `datetime` in any timezone can be passed to any library entry point and it will be normalised automatically. For example, `datetime(2024, 1, 15, 23, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))` becomes `datetime(2024, 1, 16, 2, 0, tzinfo=UTC)` when the library is configured for UTC.

### Timezone-Aware Date Extraction in `to_date`

`to_date` converts a datetime to the configured timezone before extracting the calendar date. This ensures the extracted date reflects the correct business day even if the datetime originates from a different timezone. Plain `date` inputs pass through unchanged.

### Boundary Coercion via Decorator

Rather than scattering `ensure_aware()` calls in every method body, the `@tz_aware` decorator is applied to public functions and methods that accept datetime arguments. At call time it inspects `BoundArguments` and coerces:

- `datetime` values through `ensure_aware`
- `list` values whose first element is a `datetime` element-wise

Everything else (including `None` for optional params) passes through untouched. Lists are only coerced when the first element is a `datetime`; `List[date]` arguments (e.g. loan `due_dates`) are left as-is. This keeps method bodies free of boilerplate.

### No New Dependencies

Uses `zoneinfo.ZoneInfo` from the standard library (Python 3.9+). The project requires Python 3.10+, so no extra package is needed.

## API Surface

| Symbol | Kind | Description |
|---|---|---|
| `get_tz()` | function | Return the current default `tzinfo` |
| `set_tz(tz)` | function | Set the default timezone (string or `tzinfo`) |
| `now()` | function | `datetime.now(get_tz())` — always aware |
| `ensure_aware(dt)` | function | Naive: stamp with configured tz; aware: convert to configured tz |
| `to_date(dt)` | function | Calendar `date` in the configured tz from a `datetime`, or pass through `date` |
| `to_datetime(d)` | function | Midnight on `d` as a timezone-aware `datetime` (via `ensure_aware`) |
| `tz_aware` | decorator | Coerce all datetime args of the decorated callable |
| `default_time_source` | instance | `_DefaultTimeSource` whose `.now()` delegates to `now()` |

## Where `@tz_aware` Is Applied

- `Loan.__init__`, `record_payment`, `days_since_last_payment`, `is_payment_late`, `calculate_late_fines`, `present_value`, `get_expected_payment_amount`
- `CashFlowItem.__init__`
- All `date_utils` generator functions
- `present_value()` in `present_value.py`

`Warp._parse_date` uses `ensure_aware` directly because the coercion applies to the parsed result rather than to the raw input argument.

## Key Learnings / Gotchas

- Comparing an aware datetime with a naive datetime raises `TypeError` in Python. The decorator and boundary coercion guarantee this never happens inside the library, but external callers who compare library-returned datetimes with their own naive datetimes will hit this.
- `CashFlowQuery._apply_datetime_filter` also calls `ensure_aware` on the filter value to protect against naive filter inputs.
- For naive datetimes, `ensure_aware` uses `dt.replace(tzinfo=...)`, which stamps the timezone without converting. This is correct for the intended semantics: "treat this naive datetime as being in the configured timezone."
- For aware datetimes, `ensure_aware` uses `dt.astimezone(...)`, which preserves the instant and adjusts wall-clock time. A datetime that is Jan 15 23:00 in Sao Paulo becomes Jan 16 02:00 in UTC — the `.date()` shifts accordingly.
- `set_tz` should be called once at startup. Changing it mid-flight alters how `to_date` and `ensure_aware` interpret datetimes, which could produce inconsistent results if objects were created under a different timezone.
