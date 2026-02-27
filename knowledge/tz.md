# Timezone Configuration (tz)

The `tz` module centralises all timezone handling for MoneyWarp. Every datetime produced or stored by the library is timezone-aware.

## Design Decisions

### UTC by Default, Configurable

The module-level default timezone starts as `timezone.utc`. Callers can change it globally with `set_tz("America/Sao_Paulo")` or `set_tz(some_tzinfo)`. The change affects `now()`, `ensure_aware()`, and the `tz_aware` decorator — all of which read `get_tz()` at call time.

### Boundary Coercion via Decorator

Rather than scattering `ensure_aware()` calls in every method body, the `@tz_aware` decorator is applied to public functions and methods that accept datetime arguments. At call time it inspects `BoundArguments` and coerces:

- `datetime` values through `ensure_aware`
- `list` values whose first element is a `datetime` element-wise

Everything else (including `None` for optional params) passes through untouched. This keeps method bodies free of boilerplate.

### No New Dependencies

Uses `zoneinfo.ZoneInfo` from the standard library (Python 3.9+). The project requires Python 3.10+, so no extra package is needed.

## API Surface

| Symbol | Kind | Description |
|---|---|---|
| `get_tz()` | function | Return the current default `tzinfo` |
| `set_tz(tz)` | function | Set the default timezone (string or `tzinfo`) |
| `now()` | function | `datetime.now(get_tz())` — always aware |
| `ensure_aware(dt)` | function | Attach default tz to naive dt; pass aware dt through |
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
- `ensure_aware` uses `dt.replace(tzinfo=...)`, which stamps the timezone without converting. This is correct for the intended semantics: "treat this naive datetime as being in the configured timezone."
