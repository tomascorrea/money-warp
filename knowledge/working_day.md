# Working Day Calendar

The `working_day` module provides a pluggable calendar system for determining working days and adjusting penalty due dates when they fall on non-working days.

## Overview

Brazilian banking regulation requires that boleto (payment slip) due dates falling on non-working days be deferred to the next working day for penalty purposes. The `WorkingDayCalendar` protocol and its implementations enable this behavior across both `Loan` and `BillingCycleLoan`.

## Design Decisions

**Protocol-based extensibility**: `WorkingDayCalendar` is a `@runtime_checkable` Protocol with two methods (`is_working_day`, `next_working_day`). Any class implementing these methods satisfies the protocol without explicit inheritance.

**Always-present calendar (no None checks)**: Every loan has a `working_day_calendar` attribute. The default is `EveryDayCalendar` where every day is a working day — this preserves original behavior without `None` guards in the engine functions.

**Penalty-only adjustment**: The calendar adjusts due dates **only for penalty evaluation** (fines and mora boundary). Schedule amounts, coverage counting, installment structure, and due date lists use the original dates. This keeps the financial schedule contractually correct.

**Mora boundary adjustment**: The effective penalty due date is used as the boundary between regular and mora interest in `compute_accrued_interest`. Days before the effective due date accrue regular interest; days after accrue mora.

**Grace period applies after effective due date**: The grace period (for fines) is applied to the effective penalty due date, not the original. If a due date is Saturday (effective Monday) with 1-day grace, fines apply from Wednesday onward.

## API Surface

### Protocol

```python
class WorkingDayCalendar(Protocol):
    def is_working_day(self, d: date) -> bool: ...
    def next_working_day(self, d: date) -> date: ...
```

### Implementations

| Class | Behavior |
|---|---|
| `EveryDayCalendar` | All days are working days. Default for loans. |
| `WeekendCalendar` | Sat/Sun are non-working. No holidays. |
| `BrazilianWorkingDayCalendar(extra_holidays=None)` | Weekends + 13 national holidays (9 fixed + 4 movable from Easter) + optional extra dates for state/municipal holidays. |

### Helper

```python
effective_penalty_due_date(due_date: date, calendar: WorkingDayCalendar) -> date
```

Returns `due_date` if it's a working day, otherwise `calendar.next_working_day(due_date)`.

### Loan/BillingCycleLoan Parameter

```python
Loan(..., working_day_calendar=BrazilianWorkingDayCalendar())
BillingCycleLoan(..., working_day_calendar=WeekendCalendar())
```

## Key Learnings / Gotchas

- `BrazilianWorkingDayCalendar` computes movable holidays from Easter using `dateutil.easter`. Results are cached per year.
- The `_has_payment_near` function in fines.py uses a separate `schedule_due_date` parameter for schedule lookups when the payment window is centered on the effective date. This ensures the expected payment amount is found correctly.
- The `EveryDayCalendar.next_working_day` returns `d + 1 day` (always tomorrow) — needed to satisfy the protocol but never reached via `effective_penalty_due_date` since `is_working_day` always returns True.
- Brazilian national holidays include Black Consciousness Day (Nov 20), made a national holiday in 2024.
