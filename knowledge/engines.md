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
`is_payment_late`, `compute_fines_at`. Late-payment detection and fine calculation. Both functions require a `tz: tzinfo` parameter and a `calendar: WorkingDayCalendar` parameter for penalty due-date adjustment (non-working day deferral). `_has_payment_near` accepts an optional `schedule_due_date` to separate the payment window date from the schedule lookup date. Also imports `BALANCE_TOLERANCE` from `constants.py`. `compute_fines_at` accepts an optional `settled_due_dates: Set[date]` — due dates whose principal is already covered by strictly earlier payments are exempt from new fine creation (must be computed before allocating the current event; dues after `as_of` are ignored). `compute_state` passes covered dues on or before the event business date.

### `constants.py`
`BALANCE_TOLERANCE` -- sub-cent threshold for rounding comparisons, shared across submodules.

### `allocation.py`
`allocate_payment` (loan-level priority: fine -> mora -> interest -> principal), `distribute_into_installments` (maps totals to per-installment reporting), `allocate_payment_into_installments` (combines both steps), and the internal `_InstallmentExpectation` value object. Imports `Allocation` from `models/`. No `tz` parameter needed (operates on Money amounts only).

`_InstallmentExpectation` is a lightweight bag of per-installment primitives (`expected_*`, `*_paid`, `due_date`, `balance_tolerance`) with `balance` / `is_fully_paid` properties that match the public `Installment`. The allocator consumes this internal type only — `Installment` (a downstream projection of settlements + schedule) is never read by the forward pass. This keeps `compute_state` strictly downstream of the cashflow, with the public installment view sitting *after* settlements in the data flow.

`distribute_into_installments` walks expectations oldest-first. When an installment's per-component allocation does not cover its remaining balance, `_absorb` pulls from the remaining component pools (fine -> mora -> interest -> principal) up to the shortfall. Allocations are emitted with a provisional `is_fully_covered=False`; the real value is assigned in a single pass at the end of `compute_state` against the final `Installment` view. The "no principal leak" invariant is enforced by the oldest-first principal flow itself and is asserted in `tests/invariants/test_sequential_coverage.py`. Flag *monotonicity* (no True after False) is not enforced: when an earlier installment runs out of mora pool but its principal is covered, a later installment can legitimately be fully covered.

### `forward_pass.py`
`LoanState` (frozen dataclass), `compute_state` (unified forward pass), `build_installments`, `principal_covered_count`, `fully_covered_count`, `apply_tolerance_adjustment`. The largest submodule -- orchestrates fines, expectations, allocation, and final coverage labeling into a single chronological replay. `compute_state` and `build_installments` require a `tz: tzinfo` parameter and a `calendar: WorkingDayCalendar` parameter; all internal `.date()` calls use `to_date(dt, tz)` for correct business-day extraction. The calendar adjusts the mora boundary via `effective_penalty_due_date(next_due, calendar)` before passing to `compute_accrued_interest`.

Two helpers build per-installment views:
- `_build_expectations` returns `_InstallmentExpectation` records consumed by the allocator inside the forward-pass loop. Single source of waiver-aware `expected_fine` / `expected_mora` math.
- `_build_installments_snapshot` delegates to `_build_expectations` and wraps each result via `Installment.from_schedule_entry`. Used only to produce the public `Installment` view (in `build_installments` and the final coverage pass), never as an internal cap source.

After the forward-pass loop finishes, `_finalize_settlements_coverage` runs once: it builds the final `Installment[]` via `_build_installments_snapshot` and overwrites every `Allocation.is_fully_covered` flag to match the corresponding `Installment.is_fully_paid`. This is the single writer for that flag.

Two coverage functions exist for different purposes:
- `principal_covered_count(remaining_balance, schedule)` -- counts how many installments have their principal covered based on the remaining balance vs the schedule's ending balances. Used internally by `compute_state` for payment targeting and by `_build_expectations` / `_build_installments_snapshot` for mora/fine capping.
- `fully_covered_count(installments)` -- counts consecutive installments where all obligations (principal, interest, mora, fine) are met. Available for external queries but not used in the forward pass due to circular-dependency constraints with installment construction.

**Waiver handling in `compute_state`**: When a payment entry has `waive_fines=True`, the forward pass adds the outstanding fine balance to `fines_paid_total` (marking fines as settled) and sets `fine_cap` to zero so no payment amount flows to fines. When `waive_mora=True`, `mora_cap` is set to zero. When `waive_overdue_interest=True`, `_compute_overdue_interest_waiver` caps `regular` at the amount accrued up to the due date, and `_skipped_contractual_interest` is zeroed out so that interest from later installments does not inflate the cap. The waived amounts are recorded in the `Settlement` via `fines_waived`, `mora_waived`, and `overdue_interest_waived` fields. Waiver flags are also forwarded to `_build_expectations` so that `expected_fine` and `expected_mora` on each `_InstallmentExpectation` (and, via delegation, on the final `Installment` snapshot) reflect the effective obligation (capped at prior paid amounts when waived). Without this, `Installment.balance` remains inflated and `is_fully_covered` returns `False` despite the payment covering all non-waived obligations.

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
- **Unidirectional data flow**: `CashFlow` and the static schedule feed `compute_state`, which emits `Settlement[]`. The public `Installment` view is a projection built downstream of those settlements (by `build_installments` at query time, and once at the end of `compute_state` for the final coverage pass). The forward-pass loop never reads `Installment` back as an input — it consumes `_InstallmentExpectation` (a lightweight cap-input type derived from `schedule`, `allocs_by_number`, `fines_applied`, and accrued mora). Restoring this unidirectional flow removed the chicken-and-egg between "compute the next settlement" and "build the installment view" and eliminated two of the three coverage-flag reconciliation passes.
- **Sequential coverage invariant**: `distribute_into_installments` guarantees that no money leaks past an uncovered installment. The shortfall absorption pulls from remaining pools to fill the oldest uncovered installment before any money flows to newer ones. This applies to all payment types including anticipation (early payments), where the interest discount creates a shortfall that is filled from the principal pool. `is_fully_covered` flag *monotonicity* is not enforced (see the `distribute_into_installments` notes above).
- **`_skipped_contractual_interest` and waivers**: `_skipped_contractual_interest` adds unpaid contractual interest from later installments whose due dates fall within the accrual window. When `waive_overdue_interest=True`, this must be zeroed out -- otherwise the skipped amount bypasses the waiver and inflates `interest_cap`, causing extra interest to eat into principal on multi-installment loans. Operates on `List[_InstallmentExpectation]` (uses `expected_interest`, `interest_paid`, `due_date`).
- **`_prior_underpaid_interest` and waiver targets**: When a late payment with waivers (`waive_mora`, `waive_overdue_interest`, or `discount`) causes `principal_covered_count` to consider an installment "covered" while its interest is still owed, `_prior_underpaid_interest` captures the missing contractual interest and adds it to `interest_cap`. Only targets installments that (a) were the target of a waiver-affected payment (tracked in a `waiver_targets` set), and (b) have `principal_paid > expected_principal` (strictly overcovered). The anticipation filter (b) prevents false positives where interest is legitimately lower due to early principal reduction. Also operates on `List[_InstallmentExpectation]`.
- **Expectation caps must match waiver flags**: `_build_expectations` accepts `waive_fines` and `waive_mora` flags. When active, `expected_fine` / `expected_mora` are capped at prior paid amounts (nothing new owed). Because `_build_installments_snapshot` delegates to `_build_expectations`, the public `Installment` view automatically inherits the same caps — there is one source of waiver math. Without this, `Installment.balance` would include waived mora/fine while the allocation engine zeroes them, causing `is_fully_covered` to return `False` on late payments with waivers.
- **Expectation mora rate must match loan-level mora rate**: `_build_expectations` (and therefore `_build_installments_snapshot` and `build_installments`) accept an optional `mora_rate_for_event: MoraRateCallback`. When provided, the resolved per-cycle rate is passed as `mora_rate_override` to `compute_accrued_interest` so `expected_mora` on the expectation (and on the projected `Installment`) uses the same rate as the loan-level allocation in `compute_state`. `BaseLoan.installments` wires its `_resolve_mora_rate_for_due` hook into `build_installments` so `Loan` (no override -> `None`) and `BillingCycleLoan` (per-cycle resolver) stay consistent.
- **Single coverage writer**: `Allocation.is_fully_covered` is written in exactly one place: `_finalize_settlements_coverage` at the end of `compute_state`. The allocator emits `is_fully_covered=False` provisionally inside the loop, and the final pass overwrites every flag against the final `Installment` view (`is_fully_paid`). `BaseLoan.pay_installment` plays along by re-fetching `self.settlements[-2]` after a tolerance event fires (the tolerance settlement is appended at `[-1]`; the original payment's settlement sits at `[-2]` thanks to stable-sorted equal-timestamp events). No in-place mutation of allocations happens anywhere.
- **`Installment.balance` collapses sub-cent residuals**: residuals within the installment's `balance_tolerance` return as `Money.zero()`, so `Installment.is_fully_paid` and `Allocation.is_fully_covered` agree on rounding artifacts that the tolerance-adjustment mechanism absorbs.
- **`balance_tolerance` is a loan-level setting**: `Loan` and `BillingCycleLoan` accept a `balance_tolerance: Optional[Money]` constructor parameter (default `Money("0.01")` via `DEFAULT_BALANCE_TOLERANCE`, defined in `models/installment.py` and re-exported as the engine-wide `BALANCE_TOLERANCE` so there is a single source of truth). The value lives on `BaseLoan.balance_tolerance` and is threaded through every engine function that takes tolerance-based decisions (`compute_state`, `_build_expectations`, `_build_installments_snapshot`, `build_installments`, `distribute_into_installments`, `allocate_payment_into_installments`, `_finalize_settlements_coverage`, `principal_covered_count`, `fully_covered_count`, `_prior_underpaid_interest`, `_accrual_end_with_waiver_cap`, `compute_fines_at` / `_has_payment_near`). Each function defaults to the engine-wide `BALANCE_TOLERANCE` so existing callers stay working; the loan attribute is what end users override. `Installment.from_schedule_entry` carries the value into the constructed installment via the `balance_tolerance` field, and `_InstallmentExpectation` carries it on its own field.
- **`balance_tolerance` couples `is_fully_paid` with fine detection**: `_has_payment_near` accepts the same tolerance to decide whether a sub-cent underpayment near a due date should still suppress a fine. Lifting `balance_tolerance` on a loan therefore both relaxes "is this installment fully paid?" and relaxes "should this due date receive a fine?" — they share one knob by design.
- **Settled due dates are fine-exempt (retroactive fine bug)**: `_has_payment_near` compares cash near the due date against the original schedule face, so a settlement accepted as full coverage under `waive_overdue_interest` / `discount` (cash below face) — or a full prepayment outside the ±3/+1-day window — used to get a retroactive fine at a later observation date, reopening the installment and cascading shortfall/mora into later cycles. `compute_state` now passes `settled_due_dates` (due dates covered per `principal_covered_count` from strictly earlier payments, **restricted to dues on or before the event's business date**) to `compute_fines_at`, which skips fine creation for them. `compute_fines_at` also drops any settled dues after `as_of`, so anticipation cannot mark not-yet-due installments as settled under the warped clock. Ordering is load-bearing: coverage is computed **before** the current event's payment is allocated, so the fine born at the first late event (even when the late payment itself is that event) is never masked. The exemption inherits `principal_covered_count`'s definition of coverage — if that counter is wrong, the exemption is wrong with it.
- **Coverage function naming**: The old `covered_due_date_count` was renamed to `principal_covered_count` to clarify it checks principal only. `fully_covered_count` was added to check all obligations but is not used in `compute_state` because expectation building still depends on principal-only coverage (mora/fine caps look at `principal_covered_count`). A future refactoring of `_build_expectations` to separate coverage from mora/fine capping would allow using `fully_covered_count` in the forward pass.
- **Fully-paid installment skip in allocation**: `distribute_into_installments` skips installments where `is_fully_paid` is True or `balance <= BALANCE_TOLERANCE`. Without this guard, component-level rounding mismatches (e.g., principal overpaid by R$0.01, interest underpaid by R$0.01) cause the per-component checks to find "owed" amounts on an installment whose aggregate balance is zero. This leaks money from the payment pool, shorting the next installment. The tolerance-aware check is consistent with `fully_covered_count`.
- **`last_accrual_end` cap under `waive_overdue_interest`**: After each payment the forward pass calls `_accrual_end_with_waiver_cap`. When `waive_overdue_interest=True` and **this payment advanced `principal_covered_count`** (it finished the principal of one or more installments), `last_accrual_end` is capped at `due_dates[new_covered - 1]` instead of advancing to the late payment timestamp. Without this cap, paying installment N one day late with the waiver shortens installment N+1's contractual interest period by the late days, drifting the principal/interest split and leaving sub-cent residuals that prevent `is_paid_off`. Invariant: paying the scheduled installment N days late with `waive_fines + waive_mora + waive_overdue_interest` produces the same per-installment principal/interest split as paying on time.
- **Snap requires advancing the covered count (same-cycle partials bug)**: The snap must NOT fire on a payment that leaves `principal_covered_count` unchanged. Before this predicate existed, a partial payment with `waive_overdue_interest=True` on the open installment snapped `last_accrual_end` back to the *previously* covered installment's due date (that due date satisfied `new_covered > 0` even though this payment covered nothing new). A follow-up partial in the same cycle then re-accrued regular interest over the whole prior window, double-charging contractual interest and shorting principal (`amort_gap`), which later surfaced as bogus mora/fine on an installment that was paid in full by amount. With the predicate, two same-cycle partials with the waiver allocate exactly the same interest/principal as one batched payment (`pay_installment(A) + pay_installment(B) == pay_installment(A+B)`).
- **Same-instant follow-ups keep the snapped end**: The synthetic items added by `apply_tolerance_adjustment` propagate `waive_overdue_interest` from the originating payment and share its timestamp. They never advance the covered count themselves, so under the predicate above they would default to the late timestamp and silently undo the snap the originating payment just applied. `_accrual_end_with_waiver_cap` therefore receives the previous payment's datetime and accrual end: a waiver payment at or before the previous payment's timestamp that does not advance coverage keeps the previous `last_accrual_end` unchanged.
