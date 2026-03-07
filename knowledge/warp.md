# Time Machine (Warp)

`Warp` is a context manager that lets you observe any financial instrument's state at any point in time without modifying the original. It implements the core "time-warping" metaphor of the library.

## Design

### Generic via Duck Typing

Warp accepts any object that exposes a `_time_ctx` attribute (a `TimeContext`). After deep-cloning and overriding the time context, it calls `_on_warp(target_date)` if the method exists. This hook lets each instrument prepare for the warped date:

- `Loan._on_warp` → `calculate_late_fines(target_date)`
- `CreditCard._on_warp` → `_close_billing_cycles(target_date)`

No base class or protocol is required — pure duck typing.

### Clone-Based Isolation

`Warp.__enter__()` deep-clones the target via `copy.deepcopy()`. The original is never touched. The returned clone has its time source replaced, so all time-dependent methods (balance, payment history, fines, statements) reflect the target date.

### WarpedTime

`WarpedTime` is a simple class whose `now()` returns a fixed timezone-aware datetime. During a warp, the clone's `TimeContext` is overridden with a `WarpedTime` instance. Every method that calls `self.now()` then sees the warped date transparently.

### Nested Warp Prevention

A class variable `Warp._active_targets` tracks warped objects by `id()`. Attempting to warp the same object twice raises `NestedWarpError`. Different objects (e.g. a Loan and a CreditCard) can be warped concurrently.

## API

```python
with Warp(loan, "2030-06-15") as future_loan:
    balance = future_loan.current_balance

with Warp(credit_card, "2030-06-15") as future_card:
    stmts = future_card.statements
```

### Backward Compatibility

`original_loan` and `warped_loan` are preserved as properties aliasing `_original` and `_warped`.

### Date Input

The target date accepts `str`, `date`, or `datetime`:

- **str**: parsed via `datetime.fromisoformat()` (handles `"Z"` suffix), then made aware via `ensure_aware`
- **date**: converted to `datetime` using `datetime.combine(d, datetime.min.time())`, then made aware
- **datetime**: passed through `ensure_aware` (naive datetimes get the configured default timezone)

All parsed dates are guaranteed timezone-aware. Invalid strings raise `InvalidDateError`.

### What Happens on Enter

1. Deep-clone the target object
2. Override `_time_ctx` with `WarpedTime(target_date)`
3. Call `_on_warp(target_date)` if the method exists
4. Track the original by `id()` in `_active_targets`
5. Return the clone

### What Happens on Exit

1. Remove from `_active_targets`
2. Discard the clone

## Constraints

- **No nested warps on the same object** — different objects can be warped concurrently
- **Read-only semantics** — mutations on the clone are discarded on exit
- **Performance** — deep-cloning an object with many items can be expensive; acceptable for analysis use cases
