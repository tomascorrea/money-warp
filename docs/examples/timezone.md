# Timezone Handling 🌐

MoneyWarp uses timezone-aware datetimes throughout the library. By default, all datetimes are treated as **UTC**. You can change this default globally, and naive datetimes passed to any API are silently coerced to the configured timezone.

## Why Timezone-Aware?

Mixing naive and aware datetimes in Python raises `TypeError` on comparison. By enforcing awareness everywhere, MoneyWarp avoids this class of bugs entirely. Financial calculations — especially across jurisdictions — benefit from unambiguous timestamps.

## Default Timezone

```python
from money_warp import get_tz, now

# The default is UTC
print(get_tz())  # datetime.timezone.utc

# now() always returns a timezone-aware datetime
current = now()
print(current)  # e.g. 2024-06-15 14:30:00+00:00
```

## Changing the Default

Use `set_tz()` with an IANA timezone name or a `tzinfo` object:

```python
from money_warp import set_tz, get_tz, now

# IANA timezone name (uses zoneinfo.ZoneInfo internally)
set_tz("America/Sao_Paulo")
print(get_tz())  # zoneinfo.ZoneInfo(key='America/Sao_Paulo')
print(now())     # e.g. 2024-06-15 11:30:00-03:00

# Fixed UTC offset
from datetime import timezone, timedelta
set_tz(timezone(timedelta(hours=5, minutes=30)))
print(now())     # e.g. 2024-06-15 20:00:00+05:30

# Reset to UTC
set_tz("UTC")
```

## Naive Datetime Coercion

Naive datetimes (without `tzinfo`) are accepted everywhere. The library attaches the current default timezone automatically:

```python
from datetime import datetime
from money_warp import ensure_aware, set_tz

# With default UTC
dt = ensure_aware(datetime(2024, 6, 15))
print(dt)  # 2024-06-15 00:00:00+00:00

# Already-aware datetimes pass through unchanged
from datetime import timezone
aware_dt = datetime(2024, 6, 15, tzinfo=timezone.utc)
print(ensure_aware(aware_dt))  # 2024-06-15 00:00:00+00:00 (unchanged)

# With a different default timezone
set_tz("America/New_York")
dt = ensure_aware(datetime(2024, 6, 15))
print(dt)  # 2024-06-15 00:00:00-04:00

set_tz("UTC")  # reset
```

## Using with Loans and Cash Flows

You don't need to explicitly call `ensure_aware()` — all public APIs handle it automatically. Naive datetimes work as input for convenience:

```python
from datetime import datetime
from money_warp import Loan, Money, InterestRate, generate_monthly_dates

# Naive datetimes are silently coerced to UTC
loan = Loan(
    Money("10000"),
    InterestRate("5% a"),
    generate_monthly_dates(datetime(2024, 2, 1), 12),
    disbursement_date=datetime(2024, 1, 1),
)

# All stored datetimes are now timezone-aware
print(loan.disbursement_date)  # 2024-01-01 00:00:00+00:00
print(loan.due_dates[0])       # 2024-02-01 00:00:00+00:00
```

The same applies to `CashFlowItem`, `Warp`, `record_payment`, and all other datetime-accepting APIs.

## The `@tz_aware` Decorator

Under the hood, MoneyWarp uses a `@tz_aware` decorator on public API methods. This decorator inspects function arguments and converts any `datetime` (or `list[datetime]`) to timezone-aware before the function body runs.

You can use it in your own code if you integrate with MoneyWarp:

```python
from datetime import datetime
from money_warp import tz_aware

@tz_aware
def process_payment(amount: float, payment_date: datetime) -> str:
    # payment_date is guaranteed to be timezone-aware here
    return f"Processed {amount} at {payment_date}"

# Naive datetime is coerced automatically
result = process_payment(100.0, datetime(2024, 6, 15))
print(result)  # Processed 100.0 at 2024-06-15 00:00:00+00:00
```

## Testing Tips

When writing tests against MoneyWarp, you can either:

1. **Use naive datetimes** — they are coerced automatically, so your test setup stays clean
2. **Use explicit `tzinfo=timezone.utc`** — for clarity and to match the stored values exactly

```python
from datetime import datetime, timezone

# Both approaches work for input
loan = Loan(Money("1000"), InterestRate("5% a"), [datetime(2024, 2, 1)])
loan = Loan(Money("1000"), InterestRate("5% a"), [datetime(2024, 2, 1, tzinfo=timezone.utc)])

# For assertions, use aware datetimes to match stored values
assert loan.due_dates[0] == datetime(2024, 2, 1, tzinfo=timezone.utc)
```

## Public API

| Function | Description |
|---|---|
| `get_tz()` | Returns the current default `tzinfo` |
| `set_tz(tz)` | Sets the default timezone (string or `tzinfo`) |
| `now()` | Returns `datetime.now()` in the configured timezone |
| `ensure_aware(dt)` | Coerces a naive datetime; passes aware datetimes through |
| `tz_aware` | Decorator that coerces `datetime` arguments automatically |
