# Engines Package

The `money_warp/engines/` package contains all stateless computation logic shared across loan products (`Loan`, `BillingCycleLoan`). Product-specific wiring lives in each product's own `engines.py` module.

## Overview

Before this package existed, shared computation lived in `money_warp/loan/engines.py`, forcing `BillingCycleLoan` to import from a sibling product's internals. The package structure separates concerns into focused submodules while providing a single import path via `__init__.py`.

## Design Decisions

**Package over single file**: The shared engine logic is ~700 lines spanning interest calculation, allocation, fines, and the forward pass. A package with 4 submodules (~80-350 lines each) keeps each file focused.

**Domain types live in `models/`**: `Allocation`, `Installment`, `Settlement`, `AnticipationResult`, and `BillingCycleLoanStatement` live in `money_warp/models/`. This eliminates the circular dependency that previously existed between `engines/` and `loan/`. Both `engines/` and product packages (`loan/`, `billing_cycle_loan/`) import types from `models/`, keeping the dependency graph acyclic. Product `__init__.py` files re-export the types for backward compatibility (e.g., `from money_warp.loan import Settlement` still works).

**Backward-compatible `loan/engines.py`**: The old `money_warp.loan.engines` module is kept as a pure re-export shim so existing code continues to work without changes.

## Submodules

### `interest.py`
`InterestCalculator`, `MoraStrategy` (enum), `MoraRateCallback` (type alias). Pure interest math with no dependencies on loan domain types. `compute_accrued_interest` requires a `tz: tzinfo` parameter for business-date extraction via `to_date`.

### `fines.py`
`is_payment_late`, `compute_fines_at`. Late-payment detection and fine calculation. Both functions require a `tz: tzinfo` parameter and a `calendar: WorkingDayCalendar` parameter for penalty due-date adjustment (non-working day deferral). `_has_payment_near` accepts an optional `schedule_due_date` to separate the payment window date from the schedule lookup date. Also imports `BALANCE_TOLERANCE` from `constants.py`.

### `constants.py`
`BALANCE_TOLERANCE` -- sub-cent threshold for rounding comparisons, shared across submodules.

### `allocation.py`
`allocate_payment` (loan-level priority: fine -> mora -> interest -> principal), `distribute_into_installments` (maps totals to per-installment reporting), `allocate_payment_into_installments` (combines both steps). Imports `Allocation` and `Installment` from `models/`. No `tz` parameter needed (operates on Money amounts only).

`distribute_into_installments` enforces sequential coverage: money never flows to a newer installment while an older one is not fully covered. When an installment's per-component allocation does not cover its remaining balance, `_absorb` pulls from the remaining component pools (fine -> mora -> interest -> principal) up to the shortfall. After residual and coverage-fixup post-processing, `_enforce_sequential_coverage` walks allocations in order and forces `is_fully_covered=False` on any allocation that follows an uncovered one.

### `forward_pass.py`
`LoanState` (frozen dataclass), `compute_state` (unified forward pass), `build_installments`, `covered_due_date_count`, `apply_tolerance_adjustment`. The largest submodule -- orchestrates fines, allocation, and installment snapshots into a single chronological replay. `compute_state` and `build_installments` require a `tz: tzinfo` parameter and a `calendar: WorkingDayCalendar` parameter; all internal `.date()` calls use `to_date(dt, tz)` for correct business-day extraction. The calendar adjusts the mora boundary via `effective_penalty_due_date(next_due, calendar)` before passing to `compute_accrued_interest`.

## Import Patterns

Both products now import shared engine logic from `money_warp.engines`:

```python
# loan/loan.py
from ..engines import InterestCalculator, LoanState, MoraStrategy, ...

# billing_cycle_loan/billing_cycle_loan.py
from ..engines import InterestCalculator, LoanState, MoraStrategy, ...
from .engines import build_statements, compute_state  # product-specific
```

Domain types come from `money_warp.models`:

```python
# engines/forward_pass.py
from ..models.allocation import Allocation
from ..models.installment import Installment
from ..models.settlement import Settlement

# loan/loan.py
from ..models import AnticipationResult, Installment, Settlement
```

Product-specific engines only contain wiring unique to that product:
- `billing_cycle_loan/engines.py`: mora rate resolution, `compute_state` wrapper (adds mora callback), statement building.

## Invariant Tests

Property-based invariant tests live in `tests/invariants/`, not `tests/engines/`. This is intentional: these tests verify cross-cutting domain invariants that exercise the full stack (Loan/BCL + Warp + engines), not individual engine functions.

| File | Invariants |
|------|-----------|
| `test_schedule.py` | (1-2) Amortization sums to principal, ends at zero; per-row balance and payment identities |
| `test_balance.py` | (3, 5) Principal balance never negative; installment balances nonneg; `is_fully_paid` implies zero |
| `test_allocation.py` | (4) Settlement components nonneg and sum to payment amount |
| `test_allocation_completeness.py` | Per-component allocation sums match settlement totals across all installments |
| `test_interest.py` | (6-8) Interest monotonicity; covered due-date count non-decreasing; zero mora on/before due date |
| `test_sequential_coverage.py` | Coverage flags monotonically ordered; no money leaks past uncovered installments |

Shared Hypothesis strategies and helpers (`build_loan`, `make_payment_amount`, etc.) live in `tests/invariants/strategies.py`. The `conftest.py` adds the directory to `sys.path` so test files can import strategies directly.

## Key Learnings / Gotchas

- **Import order in `__init__.py`**: The re-export order in `engines/__init__.py` doesn't need to match the dependency order -- Python handles submodule loading correctly as long as no circular chain exists.
- **`BALANCE_TOLERANCE`**: Defined in `constants.py` and imported by `fines.py`, `forward_pass.py`, and `allocation.py`.
- **`tz` parameter threading**: All engine functions that extract calendar dates from datetimes require an explicit `tz: tzinfo` parameter. No function falls back to a global timezone. Loan/BCL callers pass `self._time_ctx.tz`.
- **`calendar` parameter threading**: All penalty-related engine functions (`compute_fines_at`, `compute_state`, `build_installments`) accept a `WorkingDayCalendar` parameter. The default is `EveryDayCalendar()` (all days working). Loan/BCL callers pass `self.working_day_calendar`.
- **Sequential coverage invariant**: `distribute_into_installments` guarantees that `is_fully_covered` flags are monotonically ordered and that no money leaks past an uncovered installment. The shortfall absorption pulls from remaining pools to fill the oldest uncovered installment before any money flows to newer ones. This applies to all payment types including anticipation (early payments), where the interest discount creates a shortfall that is filled from the principal pool.
