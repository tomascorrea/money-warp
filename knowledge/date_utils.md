# Date Utils

Date generation utilities for creating payment schedules. All functions live in `money_warp/date_utils.py` and are re-exported from `money_warp.__init__`.

## Design Decisions

### Anchored Date Arithmetic

Monthly, quarterly, and annual generators compute each date as an offset from the **original start date**, not from the previous result. This prevents day-of-month drift when a short month clamps the day.

**Pattern:** `start_date + relativedelta(months=i)` (not `current += relativedelta(months=1)`)

**Why it matters:** Chaining `relativedelta` from the previous date loses the original day-of-month after a short month:
- Chained: Jan 31 → Feb 29 → Mar 29 → Apr 29 (day drifts from 31 to 29)
- Anchored: Jan 31 → Feb 29 → Mar 31 → Apr 30 (each date remembers "31st")

This applies to all `relativedelta`-based generators:
- `generate_monthly_dates` — `start_date + relativedelta(months=i)`
- `generate_quarterly_dates` — `start_date + relativedelta(months=3*i)`
- `generate_annual_dates` — `start_date + relativedelta(years=i)`

Fixed-day generators (`biweekly`, `weekly`, `custom_interval`) use `timedelta(days=N)` and are unaffected — day drift is not possible with fixed day counts.

### Validation

All generators raise `ValueError` for non-positive `num_payments`. `generate_custom_interval_dates` also validates `interval_days > 0`.

## API Surface

| Function | Interval | Engine |
|---|---|---|
| `generate_monthly_dates(start, n)` | 1 month | `relativedelta`, anchored |
| `generate_biweekly_dates(start, n)` | 14 days | `timedelta` |
| `generate_weekly_dates(start, n)` | 7 days | `timedelta` |
| `generate_quarterly_dates(start, n)` | 3 months | `relativedelta`, anchored |
| `generate_annual_dates(start, n)` | 1 year | `relativedelta`, anchored |
| `generate_custom_interval_dates(start, n, days)` | N days | `timedelta` |

All return `List[datetime]` with the first element equal to `start_date`.

## Key Learnings

### Day-of-month drift in chained relativedelta (fixed 2026-02-23)

**Symptom:** Starting from Jan 31, the monthly generator produced `[Jan 31, Feb 29, Mar 29, Apr 29, ...]` instead of `[Jan 31, Feb 29, Mar 31, Apr 30, ...]`. The day "drifted" to 29 after February's clamping and never recovered.

**Root cause:** Each date was computed as `current_date += relativedelta(months=1)`, chaining from the previous result. After February clamped 31→29, all subsequent months used 29 as their starting day.

**Fix:** Compute each date as `start_date + relativedelta(months=i)` so `relativedelta` always sees the original day (31) and clamps per-month independently.

**Lesson:** When generating periodic dates with `relativedelta`, always anchor offsets to the original start date. Chaining accumulates clamping errors. The same fix was applied to quarterly and annual generators.
