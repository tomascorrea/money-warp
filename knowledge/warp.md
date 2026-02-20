# Time Machine (Warp)

`Warp` is a context manager that lets you observe a loan's state at any point in time without modifying the original loan. It implements the core "time-warping" metaphor of the library.

## Design

### Clone-Based Isolation

`Warp.__enter__()` deep-clones the loan via `copy.deepcopy()`. The original loan is never touched. The returned clone has its time source replaced, so all time-dependent methods (balance, payment history, fines) reflect the target date.

### WarpedTime

`WarpedTime` is a simple class whose `now()` returns a fixed datetime. During a warp, the cloned loan's `datetime_func` attribute is swapped from Python's `datetime` class to a `WarpedTime` instance. Every loan method that calls `self.now()` then sees the warped date transparently.

### Nested Warp Prevention

A class variable `Warp._active_warp` tracks whether a warp is already in progress. Attempting to enter a second `Warp` raises `NestedWarpError`. This prevents confusing "time paradox" scenarios where two warps could conflict.

## API

```python
with Warp(loan, "2030-06-15") as future_loan:
    balance = future_loan.current_balance
    schedule = future_loan.get_amortization_schedule()
```

### Date Input

The target date accepts `str`, `date`, or `datetime`:

- **str**: parsed via `datetime.fromisoformat()` (handles `"Z"` suffix)
- **date**: converted to `datetime` using `datetime.combine(d, datetime.min.time())`
- **datetime**: used directly

Invalid strings raise `InvalidDateError`.

### What Happens on Enter

1. Deep-clone the loan
2. Replace `datetime_func` with `WarpedTime(target_date)`
3. Call `calculate_late_fines(target_date)` on the clone (so fines reflect the warped date)
4. Set `Warp._active_warp = self`
5. Return the cloned loan

### What Happens on Exit

1. Clear `Warp._active_warp`

## Constraints

- **No nested warps** — one warp at a time per process
- **Read-only semantics** — while you *can* call `record_payment()` on the cloned loan, those changes only affect the clone and are discarded on exit
- **Performance** — deep-cloning a loan with many recorded payments can be expensive; this is acceptable for analysis use cases
