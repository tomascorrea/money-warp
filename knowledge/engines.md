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
`allocate_payment` (loan-level priority: fine -> mora -> interest -> principal), `distribute_into_installments` (maps totals to per-installment reporting), `allocate_payment_into_installments` (combines both steps). Takes the `PaymentSchedule` so coverage can be computed against the post-payment ending balances. Imports `Allocation` and `Installment` from `models/`. No `tz` parameter needed (operates on Money amounts only).

`distribute_into_installments` walks installments oldest-first. When an installment's per-component allocation does not cover its remaining balance, `_absorb` pulls from the remaining component pools (fine -> mora -> interest -> principal) up to the shortfall. After residual post-processing, `_finalize_coverage` recomputes every allocation's `is_fully_covered` from the post-payment per-installment view — by construction this equals `Installment.is_fully_paid` for the targeted installment, regardless of payment timing, anticipation, waivers, or per-cycle mora rate. Flag *monotonicity* (no True after False) is not enforced: when an earlier installment runs out of mora pool but its principal is covered, a later installment can legitimately be fully covered. The real "no money leak" invariant is enforced by the oldest-first principal flow itself and is asserted in `tests/invariants/test_sequential_coverage.py`.

### `forward_pass.py`
`LoanState` (frozen dataclass), `compute_state` (unified forward pass), `build_installments`, `principal_covered_count`, `fully_covered_count`, `apply_tolerance_adjustment`. The largest submodule -- orchestrates fines, allocation, and installment snapshots into a single chronological replay. `compute_state` and `build_installments` require a `tz: tzinfo` parameter and a `calendar: WorkingDayCalendar` parameter; all internal `.date()` calls use `to_date(dt, tz)` for correct business-day extraction. The calendar adjusts the mora boundary via `effective_penalty_due_date(next_due, calendar)` before passing to `compute_accrued_interest`.

Two coverage functions exist for different purposes:
- `principal_covered_count(remaining_balance, schedule)` -- counts how many installments have their principal covered based on the remaining balance vs the schedule's ending balances. Used internally by `compute_state` for payment targeting and by `_build_installments_snapshot` for mora/fine capping.
- `fully_covered_count(installments)` -- counts consecutive installments where all obligations (principal, interest, mora, fine) are met. Available for external queries but not used in the forward pass due to circular-dependency constraints with installment construction.

**Waiver handling in `compute_state`**: When a payment entry has `waive_fines=True`, the forward pass adds the outstanding fine balance to `fines_paid_total` (marking fines as settled) and sets `fine_cap` to zero so no payment amount flows to fines. When `waive_mora=True`, `mora_cap` is set to zero. When `waive_overdue_interest=True`, `_compute_overdue_interest_waiver` caps `regular` at the amount accrued up to the due date, and `_skipped_contractual_interest` is zeroed out so that interest from later installments does not inflate the cap. The waived amounts are recorded in the `Settlement` via `fines_waived`, `mora_waived`, and `overdue_interest_waived` fields. Waiver flags are also forwarded to `_build_installments_snapshot` so that `expected_fine` and `expected_mora` on the installment snapshot reflect the effective obligation (capped at prior paid amounts when waived). Without this, `Installment.balance` remains inflated and `is_fully_covered` returns `False` despite the payment covering all non-waived obligations.

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
| `test_interest.py` | (6-7) Interest monotonicity / nonnegative; zero mora on/before due date |
| `test_sequential_coverage.py` | No principal leaks past a principal-uncovered installment |
| `test_coverage_consistency.py` | `Allocation.is_fully_covered` agrees with `Installment.is_fully_paid` for the targeted installment |

Shared Hypothesis strategies and helpers (`build_loan`, `make_payment_amount`, etc.) live in `tests/invariants/strategies.py`. The `conftest.py` adds the directory to `sys.path` so test files can import strategies directly.

## Key Learnings / Gotchas

- **Import order in `__init__.py`**: The re-export order in `engines/__init__.py` doesn't need to match the dependency order -- Python handles submodule loading correctly as long as no circular chain exists.
- **`BALANCE_TOLERANCE`**: Defined in `constants.py` and imported by `fines.py`, `forward_pass.py`, and `allocation.py`.
- **`tz` parameter threading**: All engine functions that extract calendar dates from datetimes require an explicit `tz: tzinfo` parameter. No function falls back to a global timezone. Loan/BCL callers pass `self._time_ctx.tz`.
- **`calendar` parameter threading**: All penalty-related engine functions (`compute_fines_at`, `compute_state`, `build_installments`) accept a `WorkingDayCalendar` parameter. The default is `EveryDayCalendar()` (all days working). Loan/BCL callers pass `self.working_day_calendar`.
- **Sequential coverage invariant**: `distribute_into_installments` guarantees that `is_fully_covered` flags are monotonically ordered and that no money leaks past an uncovered installment. The shortfall absorption pulls from remaining pools to fill the oldest uncovered installment before any money flows to newer ones. This applies to all payment types including anticipation (early payments), where the interest discount creates a shortfall that is filled from the principal pool.
- **`_skipped_contractual_interest` and waivers**: `_skipped_contractual_interest` adds unpaid contractual interest from later installments whose due dates fall within the accrual window. When `waive_overdue_interest=True`, this must be zeroed out -- otherwise the skipped amount bypasses the waiver and inflates `interest_cap`, causing extra interest to eat into principal on multi-installment loans.
- **`_prior_underpaid_interest` and waiver targets**: When a late payment with waivers (`waive_mora`, `waive_overdue_interest`, or `discount`) causes `principal_covered_count` to consider an installment "covered" while its interest is still owed, `_prior_underpaid_interest` captures the missing contractual interest and adds it to `interest_cap`. Only targets installments that (a) were the target of a waiver-affected payment (tracked in a `waiver_targets` set), and (b) have `principal_paid > expected_principal` (strictly overcovered). The anticipation filter (b) prevents false positives where interest is legitimately lower due to early principal reduction.
- **Installment snapshot expectations must match waiver caps**: `_build_installments_snapshot` accepts `waive_fines` and `waive_mora` flags. When active, `expected_fine` / `expected_mora` are capped at prior paid amounts (nothing new owed). Without this, `Installment.balance` includes waived mora/fine while the allocation engine zeroes them, causing `is_fully_covered` to return `False` on late payments with waivers.
- **Snapshot mora rate must match loan-level mora rate**: `_build_installments_snapshot` and `build_installments` accept an optional `mora_rate_for_event: MoraRateCallback`. When provided, the resolved per-cycle rate is passed as `mora_rate_override` to `compute_accrued_interest` so the snapshot's `expected_mora` uses the same rate as the loan-level allocation in `compute_state`. `BaseLoan.installments` wires its `_resolve_mora_rate_for_due` hook into `build_installments` so `Loan` (no override -> `None`) and `BillingCycleLoan` (per-cycle resolver) stay consistent. Without this, a BCL with a per-cycle mora resolver underestimates `Installment.balance`, and `Allocation.is_fully_covered=True` can ship alongside `Installment.is_fully_paid=False` for the same installment.
- **Coverage is decided from the post-payment installment view**: `_finalize_coverage` replaces the old `_apply_coverage_fixup` plus `_enforce_sequential_coverage`. After per-component allocation runs, every allocation's `is_fully_covered` is recomputed as "would the targeted installment's balance be within `BALANCE_TOLERANCE` after this allocation is applied?". This pins the labelling directly to `Installment.is_fully_paid` and makes the user-facing invariant hold by construction. `compute_state` then runs `_reconcile_coverage_with_final_state` over the full settlements list, re-projecting earlier allocations against the *final* snapshot — necessary because `_accrual_end_with_waiver_cap` can snap `last_accrual_end` mid-replay and change a previously-decided installment's `expected_mora`. `BaseLoan.pay_installment` mutates the returned settlement's allocations after `apply_tolerance_adjustment` adds a synthetic event, so the value the caller receives matches the live `Installment.is_fully_paid` view immediately after the call.
- **`Installment.balance` collapses sub-cent residuals**: residuals within `BALANCE_TOLERANCE` (R$0.01) return as `Money.zero()`, so `Installment.is_fully_paid` and `Allocation.is_fully_covered` agree on rounding artifacts that the tolerance-adjustment mechanism absorbs.
- **Coverage function naming**: The old `covered_due_date_count` was renamed to `principal_covered_count` to clarify it checks principal only. `fully_covered_count` was added to check all obligations but is not used in `compute_state` because installment expectations depend on coverage (circular dependency). A future refactoring of `_build_installments_snapshot` to separate coverage from mora/fine capping would allow using `fully_covered_count` in the forward pass.
- **Fully-paid installment skip in allocation**: `distribute_into_installments` skips installments where `is_fully_paid` is True or `balance <= BALANCE_TOLERANCE`. Without this guard, component-level rounding mismatches (e.g., principal overpaid by R$0.01, interest underpaid by R$0.01) cause the per-component checks to find "owed" amounts on an installment whose aggregate balance is zero. This leaks money from the payment pool, shorting the next installment. The tolerance-aware check is consistent with `fully_covered_count`.
- **`last_accrual_end` cap under `waive_overdue_interest`**: After each payment the forward pass calls `_accrual_end_with_waiver_cap`. When `waive_overdue_interest=True` and at least one installment is fully covered, `last_accrual_end` is capped at `due_dates[new_covered - 1]` instead of advancing to the late payment timestamp. Without this cap, paying installment N one day late with the waiver shortens installment N+1's contractual interest period by the late days, drifting the principal/interest split and leaving sub-cent residuals that prevent `is_paid_off`. The cap also applies to the synthetic items added by `apply_tolerance_adjustment`, which now propagate `waive_overdue_interest` from the originating payment so a tolerance event scheduled at the actual late timestamp does not silently undo the cap. Invariant: paying the scheduled installment N days late with `waive_fines + waive_mora + waive_overdue_interest` produces the same per-installment principal/interest split as paying on time.
- **Partial-payment-with-waiver limitation (intentional)**: The cap above only triggers once an installment is fully covered (`new_covered > 0`). Partial payments late with `waive_overdue_interest=True` keep the current behaviour and the next installment's interest period continues to start at the actual payment timestamp. Snapping unconditionally would cause a follow-up partial payment without waivers to silently accrue extra mora days; that "spooky action at a distance" is worse than the small drift it would fix, and partial-payment-with-waiver scenarios are essentially renegotiations whose semantics deserve a separate design pass.
