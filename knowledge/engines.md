# Engines Package

The `money_warp/engines/` package contains all stateless computation logic shared across loan products (`Loan`, `BillingCycleLoan`). Product-specific wiring lives in each product's own `engines.py` module.

## Overview

Before this package existed, shared computation lived in `money_warp/loan/engines.py`, forcing `BillingCycleLoan` to import from a sibling product's internals. The package structure separates concerns into focused submodules while providing a single import path via `__init__.py`.

## Design Decisions

**Package over single file**: The shared engine logic is ~700 lines spanning interest calculation, allocation, fines, and the forward pass. A package with 4 submodules (~80-350 lines each) keeps each file focused.

**Domain types stay in `loan/`**: `Allocation`, `Installment`, and `Settlement` remain in `money_warp/loan/` even though both products use them. Moving them would be a larger refactoring with more breakage. The engines submodules import these types directly from the submodules (e.g., `from ..loan.settlement import Settlement`), not through `loan/__init__.py`.

**Lazy `Loan` import in `loan/__init__.py`**: To break the circular import chain (`engines/__init__` -> `loan.installment` -> `loan.__init__` -> `loan.loan` -> `engines`), the `Loan` class is loaded lazily via PEP 562 `__getattr__`. All data types (`Allocation`, `Installment`, `Settlement`) load eagerly since they have no engine dependencies.

**Backward-compatible `loan/engines.py`**: The old `money_warp.loan.engines` module is kept as a pure re-export shim so existing code continues to work without changes.

## Submodules

### `interest.py`
`InterestCalculator`, `MoraStrategy` (enum), `MoraRateCallback` (type alias). Pure interest math with no dependencies on loan domain types.

### `fines.py`
`is_payment_late`, `compute_fines_at`. Late-payment detection and fine calculation. Also defines `_BALANCE_TOLERANCE` (sub-cent threshold for rounding comparisons).

### `allocation.py`
`allocate_payment` (loan-level priority: fine -> mora -> interest -> principal), `distribute_into_installments` (maps totals to per-installment reporting), `allocate_payment_into_installments` (combines both steps). Imports `Allocation` and `Installment` from `loan/`.

### `forward_pass.py`
`LoanState` (frozen dataclass), `compute_state` (unified forward pass), `build_installments`, `covered_due_date_count`, `apply_tolerance_adjustment`. The largest submodule -- orchestrates fines, allocation, and installment snapshots into a single chronological replay.

## Import Patterns

Both products now import shared engine logic from `money_warp.engines`:

```python
# loan/loan.py
from ..engines import InterestCalculator, LoanState, MoraStrategy, ...

# billing_cycle_loan/billing_cycle_loan.py
from ..engines import InterestCalculator, LoanState, MoraStrategy, ...
from .engines import build_statements, compute_state  # product-specific
```

Product-specific engines only contain wiring unique to that product:
- `billing_cycle_loan/engines.py`: mora rate resolution, `compute_state` wrapper (adds mora callback), statement building.

## Key Learnings / Gotchas

- **Circular imports with `loan/__init__.py`**: Any engines submodule that imports a type from `loan/` triggers `loan/__init__.py`. If that init eagerly imports `Loan` (which imports from `engines`), the circular chain breaks Python. The PEP 562 `__getattr__` pattern for `Loan` is the fix.
- **Import order in `__init__.py`**: The re-export order in `engines/__init__.py` doesn't need to match the dependency order -- Python handles submodule loading correctly as long as no circular chain exists.
- **`_BALANCE_TOLERANCE`**: Defined in `fines.py` but also used by `forward_pass.py` (for `covered_due_date_count`). Imported cross-submodule via `from .fines import _BALANCE_TOLERANCE`.
