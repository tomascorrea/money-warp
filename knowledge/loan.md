# Loan

The `Loan` class models a personal loan where **everything emerges from the CashFlow**. A single `CashFlow` instance is the source of truth — it contains both expected items (the amortization schedule) and actual payments. Settlements, installment views, balances, and fines are all derived on demand by a forward pass over the cashflow. Nothing is decomposed or stored at payment time.

## Architecture

The Loan delegates computation to two focused components in `engines.py`:

- **`InterestCalculator`** — stateless interest math (regular + mora split). Holds `interest_rate`, `mora_interest_rate`, `mora_strategy`.
- **Pure functions** — compute all derived state. Key exports:
  - `compute_state(...)` — the forward pass that produces a `LoanState` (settlements, principal balance, fines applied, fines paid total, last payment date).
  - `build_installments(...)` — builds `Installment` objects from settlements + schedule.
  - `compute_fines_at(...)` — determines which due dates should have fines applied.
  - `allocate_payment(...)` — loan-level allocation (fine -> mora -> interest -> principal).
  - `distribute_into_installments(...)` — maps loan-level totals to per-installment allocations for reporting.
  - `allocate_payment_into_installments(...)` — convenience wrapper that calls both of the above.
  - `covered_due_date_count(...)` — how many due dates are covered given a remaining balance.
  - `is_payment_late(...)` — grace-period-aware lateness check.
- **TVM functions** (`tvm.py`) — standalone `loan_present_value`, `loan_irr`, `loan_calculate_anticipation`.

**Removed components:** `PaymentLedger` and `FineTracker` no longer exist. Their responsibilities were absorbed into the forward pass in `engines.py`.

### CashFlow-Emergence Philosophy

- `record_payment` appends **one** `CashFlowItem` (category `"payment"`) to `self.cashflow`. No fines, no decomposition, no allocation at write time.
- All financial state is derived by `_compute_state()`, which calls `settlement_engine.compute_state`. This performs a single chronological forward pass over all payment events and fine observation dates.
- Balance properties, settlements, installments, and fines are `@property` methods that invoke `_compute_state()` and return the relevant slice.

### Fine Observation Dates

Fines are event-driven. The `Loan` maintains `_fine_observation_dates: List[datetime]` — explicit timestamps at which fine calculations should be triggered during the forward pass. These are appended by:

- `_on_warp(target_date)` — called by Warp after overriding TimeContext.
- `calculate_late_fines(as_of_date)` — explicit fine observation.

The forward pass merges payment events with fine observation dates into a sorted timeline. At each event, `compute_fines_at` checks which due dates are overdue and uncovered (using a temporal-proximity window, not balance-based coverage).

## Constructor Parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `principal` | `Money` | required | Must be positive |
| `interest_rate` | `InterestRate` | required | Annual rate |
| `due_dates` | `List[date]` | required | Sorted automatically (calendar due dates) |
| `disbursement_date` | `Optional[datetime]` | now | When funds are released; must be strictly before first due date |
| `scheduler` | `Optional[Type[BaseScheduler]]` | `PriceScheduler` | Amortization strategy |
| `fine_rate` | `Optional[InterestRate]` | `InterestRate("2% annual")` | Fine rate applied to expected payment |
| `grace_period_days` | `int` | `0` | Days after due date before fines apply |
| `mora_interest_rate` | `Optional[InterestRate]` | `interest_rate` | Rate used for mora (late) interest; defaults to the base rate |
| `mora_strategy` | `MoraStrategy` | `COMPOUND` | How mora interest is computed (see Mora Strategy below) |
| `payment_tolerance` | `Optional[Money]` | `Money("0.01")` | Per-installment rounding error tolerance (see Payment Tolerance below) |

## Payment Tolerance

External loan origination systems may introduce a small rounding error per installment (typically 1 cent in the PMT calculation). This error **accumulates** across installments -- installment N can be off by up to N times the per-installment error.

The `payment_tolerance` parameter controls the per-installment error unit. The effective tolerance scales with the installment number:

- **`Installment.is_fully_paid`**: `self.balance <= payment_tolerance * self.number`
- **`Loan.is_paid_off`**: `current_balance <= payment_tolerance * len(due_dates)`

This means installment 1 on a 24-installment loan tolerates 1 cent, while installment 24 tolerates 24 cents (at the default tolerance).

The tolerance is threaded through the settlement engine (`compute_state`), where it also controls the principal snap-to-zero threshold and coverage fixup checks.

Pass `payment_tolerance=Money("0")` for exact-match behavior. Pass a larger value (e.g., `Money("0.02")`) if the external system has a larger rounding error.

## Three-Date Payment Model

Every payment carries three dates via the `CashFlowEntry`:

| Date | Meaning | Default |
|---|---|---|
| `payment_date` | When the money moved (stored as `CashFlowEntry.datetime`) | Required |
| `interest_date` | Cutoff for interest accrual calculation (stored as `CashFlowEntry.interest_date`) | `payment_date` |
| `processing_date` | Unused, kept for API compatibility | N/A |

The **interest_date** controls how many days of interest are charged. Fewer days = less interest = discount for the borrower. This decouples "when money arrived" from "how much interest to charge."

## Payment Methods

### Sugar Methods (Public API)

Neither method takes a date parameter — they use `self.now()` (which respects `Warp` context for time travel).

- **`pay_installment(amount, description=None)`** — the common case. Records payment at `self.now()` and calculates interest up to `max(self.now(), next_due_date)`. Works correctly for all three timing scenarios:
  - **Early payment** (before due date): interest accrues up to the due date. The borrower pays the full scheduled interest — no discount. The installment is fully covered if the amount is sufficient.
  - **On-time payment**: interest matches the scheduled amount exactly.
  - **Late payment**: interest accrues up to `self.now()`, so the borrower pays extra interest (mora) for the days beyond the due date. Late fines are also applied automatically.

  A large payment naturally covers the current installment **and** eats into future installments — the per-installment allocation and `covered_due_date_count()` handle this without special-casing.

- **`anticipate_payment(amount, installments=None, description=None)`** — early payment **with interest discount**. Records payment at `self.now()` and calculates interest only up to `self.now()` (fewer days = less interest charged). When `installments` is provided (1-based numbers), the corresponding expected cash-flow items are temporally deleted via `CashFlowItem.delete()`.

### Early Payment vs Anticipation

| | `pay_installment` (early payment) | `anticipate_payment` (anticipation) |
|---|---|---|
| **Interest accrual** | Up to the **due date** | Up to the **payment date** |
| **Discount** | None — borrower pays scheduled interest | Yes — fewer days = less interest |
| **Installment status** | Fully covered (if amount sufficient) | NOT fully covered (interest < scheduled) |
| **Use case** | Borrower wants to pay ahead of time, no discount expected | Borrower negotiates early payoff with reduced interest |
| **Test folder** | `up_to_date_payments/` | `antecipation/` |

- **`calculate_anticipation(installments)`** — pure calculation (no side effects). Returns an `AnticipationResult(amount, installments)` with the PV-based amount the borrower must pay today to eliminate specific installments.

### Explicit-Date Method

- **`record_payment(amount, payment_date, interest_date=None, processing_date=None, description=None)`** — full control over all dates. Appends one `CashFlowItem` to `self.cashflow` and returns the latest derived `Settlement`.

### Payment Allocation

Payment allocation uses a two-step process:

1. **Loan-level allocation** (`allocate_payment`): determines the totals — how much of the payment goes to fines, mora, interest, and principal. Priority: fine -> mora -> interest -> principal. All accrued fines and interest are settled before any principal.
2. **Per-installment distribution** (`distribute_into_installments`): maps those totals to individual installments for reporting. Walks installments sequentially — installment 1 absorbs what it can, then installment 2, etc.

This means all fines across all installments are paid before any mora, all mora before any interest, and all interest before any principal. Within each component, installments are filled in order.

## Forward Pass: `compute_state`

The central algorithm in `engines.compute_state`. It processes a merged timeline of payment events and fine observation dates in chronological order:

1. For each event (payment or fine observation), compute fines using only previously processed payments.
2. For payment events:
   a. Compute interest (regular + mora) since last payment.
   b. Build installment snapshot reflecting all prior allocations.
   c. Add skipped contractual interest for periods beyond the current due-date boundary.
   d. Run two-step allocation (`allocate_payment_into_installments`): loan-level math, then per-installment distribution.
   e. Update running principal, fines paid total, and allocation history.
   f. Create a `Settlement` object.
3. Return `LoanState` with all settlements and running state.

### Post-Distribution Adjustments

After distributing loan-level totals into per-installment allocations, two adjustments run:

1. **Residual** (`_apply_residual`): ensures `sum(allocations.X) == X_total` for each component. Loan-level accrual can exceed what installments absorb (rounding, partial periods, overpayment); the residual is added to the last allocation.
2. **Coverage fixup** (`_apply_coverage_fixup`): if the post-payment balance is within tolerance of zero, any allocation whose principal was fully allocated is marked `is_fully_covered = True`.

## Dynamic Amortization Schedule

### `get_amortization_schedule()`

Returns a clean, ordered list of `PaymentScheduleEntry` records. Past entries come first (reflecting actual settlements), followed by projected entries (recalculated from remaining principal).

### `get_original_schedule()`

Always returns the static schedule based on original loan terms, ignoring any payments.

## Schedulers

All schedulers implement `BaseScheduler.generate_schedule(principal, interest_rate, due_dates, disbursement_date) -> PaymentSchedule`.

### PriceScheduler (French Amortization)

Fixed total payment per period. The PMT is computed as `principal / sum(1 / (1 + daily_rate)^n)`.

#### Matching external systems with `InterestRate` precision

`InterestRate` supports `precision: int` and `rounding: str` parameters to reproduce truncated rate behaviour from external systems.

### InvertedPriceScheduler (Constant Amortization System / SAC)

Fixed principal payment per period (`principal / number_of_payments`). Interest is computed on the outstanding balance.

## Late Payments

### Fines

- `compute_fines_at` scans all due dates up to the observation time, applies one fine per missed due date (never duplicated).
- `_has_payment_near` implements a temporal window check: a due date is considered "covered" if sufficient payment was made within a small window (3 days before to 1 day after). This replaces the old balance-based coverage check.
- `calculate_late_fines(as_of_date)` appends to `_fine_observation_dates` and returns the **delta** of new fines only.
- Fine amounts are calculated from the **original** schedule.

### Mora Interest

When `pay_installment` is called after the due date, `interest_date = max(self.now(), next_due_date)` causes interest to accrue beyond the due date. The `InterestCalculator.compute_accrued_interest` method splits interest into regular and mora components.

### Mora Strategy (`MoraStrategy` enum)

**`MoraStrategy.COMPOUND`** (default): mora rate applied to `principal + regular_interest`.
**`MoraStrategy.SIMPLE`**: mora rate applied to `principal` only.

## Balance Properties

All derived from `_compute_state()`:

| Property | Type | Meaning |
|---|---|---|
| `principal_balance` | `Money` | Outstanding principal |
| `interest_balance` | `Money` | Regular accrued interest since last payment |
| `mora_interest_balance` | `Money` | Mora accrued interest (days beyond due date) |
| `fine_balance` | `Money` | Unpaid fines (total applied minus fines paid) |
| `current_balance` | `Money` | Sum of all four components |
| `overpaid` | `Money` | Total amount paid beyond the loan's obligations |

## Overpayment

When a payment exceeds the loan's total obligations (principal + interest + mora + fines), the excess is tracked as **overpaid**. This is accumulated in `LoanState.overpaid` during the forward pass: whenever `running_principal` goes negative after subtracting `principal_paid`, the absolute value of the negative amount is added to the overpaid accumulator before snapping the principal to zero.

### `pay_installment` after full repayment

`pay_installment` no longer raises `ValueError` when all due dates are covered. Instead it issues `warnings.warn(...)` and records the payment with `interest_date = payment_date` (no interest accrual). The payment flows through the normal engine pipeline and the excess is captured via `Loan.overpaid`.

### `record_payment` overpayment

`record_payment` has always accepted payments after full repayment (it just adds a CashFlowItem). The engine now correctly tracks the excess via `LoanState.overpaid`.

## Installments and Settlements

### Design Philosophy

A loan is **not** a group of installments. Installments are a **consequence** of the loan terms plus a repayment strategy (scheduler). Settlements are a **consequence** of making a payment. Both are derived views computed from the cashflow, not stored state.

### Installment (`loan.installments`)

A frozen dataclass built by `build_installments` from settlements + schedule. Warp-aware.

Fields: `number`, `due_date`, `days_in_period`, `expected_payment`, `expected_principal`, `expected_interest`, `expected_mora`, `expected_fine`, `principal_paid`, `interest_paid`, `mora_paid`, `fine_paid`, `allocations`.

- `balance` — amount still owed to fully settle this installment.
- `is_fully_paid` — `True` when `balance` is within tolerance of zero.

Per-installment allocation is a reporting view produced by `engines.distribute_into_installments` (not on the Installment class).

### Settlement (`loan.settlements`)

A frozen dataclass capturing how a single payment was allocated. Derived by the forward pass.

Fields: `payment_amount`, `payment_date`, `fine_paid`, `interest_paid`, `mora_paid`, `principal_paid`, `remaining_balance`, `allocations`.

### Allocation

Defined in `loan/allocation.py`. Fields: `installment_number`, `principal_allocated`, `interest_allocated`, `mora_allocated`, `fine_allocated`, `is_fully_covered`.

Shared between Settlement (forward view) and Installment (reverse view).

### LoanState

Internal dataclass returned by `compute_state`: `settlements`, `principal_balance`, `fines_applied`, `fines_paid_total`, `last_payment_date`, `last_accrual_end`, `overpaid`.

- `last_payment_date` — when money last moved (user-facing via `Loan.last_payment_date`).
- `last_accrual_end` — end of the last interest accrual period (`max(payment_date, interest_date)`). Used internally for interest computation and installment snapshot building. Prevents double-counting when `interest_date > payment_date`.

## Cash Flow

`loan.cashflow` is the single source of truth -- a `CashFlow` containing both expected items (schedule) and actual payment items. Allocation detail (fine, interest, mora, principal breakdown) is available through `loan.settlements`, not the cashflow.

- `generate_expected_cash_flow()` — convenience filter returning expected schedule items only.

### CashFlowItem Categories

| Category | Kind | Meaning |
|---|---|---|
| `"disbursement"` | EXPECTED | Loan disbursement |
| `"tax"` | EXPECTED | Tax deducted at disbursement |
| `"interest"` | EXPECTED | Scheduled interest payment |
| `"principal"` | EXPECTED | Scheduled principal payment |
| `"payment"` | HAPPENED | Actual payment (allocation derived via `loan.settlements`) |

## TVM Sugar

- `loan.present_value(discount_rate=None, valuation_date=None)` — defaults to the loan's own rate and `loan.now()`.
- `loan.irr(guess=None)` — IRR of the expected cash flow.

## Key Learnings

### Balance residual after full repayment (fixed 2026-02-20)

**Symptom:** After paying all scheduled installments, a residual balance of ~$103.36 persisted on a $10,000 loan.

**Root cause:** `record_payment` computed interest days via `self.days_since_last_payment(payment_date)`, which filtered payments by `self.now()` (real wall-clock time). When installments were recorded sequentially for future dates, previously-recorded future payments were invisible.

**Fix:** Pre-compute `days` and `principal_balance` at the top of `record_payment` using `payment_date` as the filter, before any internal state is mutated.

**Lesson:** Any method that reads loan state and then mutates it must snapshot the relevant values first.

### Due date coverage uses cumulative principal, not payment count (fixed 2026-02-20)

**Fix:** `covered_due_date_count()` compares the remaining principal against the original schedule's `ending_balance` milestones. A due date is covered when remaining principal is at or below that entry's ending balance.

**Lesson:** Avoid coupling "number of events" to "progress through a schedule." Use the financial state (principal balance) as the source of truth.

### Late payments undercharged interest (fixed 2026-02-20)

**Fix:** `interest_date = max(self.now(), next_due_date)` in `pay_installment`. Late payments now accrue interest up to `self.now()`.

### Payment allocation simplified to two-step process (refactored 2026-03-23)

**Previous design:** Single-pass per-installment loop with running caps, a principal reservation (hold back money from inst 1's principal to fund inst 2's interest/mora), spill redistribution, and reconciliation. The reservation created a hybrid priority that was neither purely per-installment nor purely loan-level.

**New design:** Two-step process. `allocate_payment` determines loan-level totals (fine -> mora -> interest -> principal) with four `min()` calls. `distribute_into_installments` maps those totals to installments sequentially for reporting.

**Behavioral change:** All fines and interest across all installments are settled before any principal. For heavily overdue loans, this charges more fines/interest per payment and reduces principal more slowly. Previously, only installments reached during the per-installment walk received fines.

**What was removed:** `allocate_payment_into_installment` (per-installment function with caps and reservation), `_compute_spill` (redistributed over-reserved money), `_reconcile_allocations` (patched drift from spill). Replaced by `_apply_residual` (simpler, handles only one direction of drift) and `_apply_coverage_fixup`.

**Lesson:** When a "per-installment" loop needs a reservation to fund later installments, it's implicitly doing loan-level allocation. Making the loan-level step explicit eliminates the reservation and its cascading cleanup machinery.

### Sub-cent precision loss in allocation loop (fixed 2026-03-20)

**Fix:** Use `raw_amount` comparisons in the allocation loop instead of `Money`'s 2dp-rounded methods. Sub-cent allocations are included in component totals; `_apply_residual` adjusts the last allocation to match.

**Lesson:** `Money`'s `real_amount`-based comparisons are correct for business display but dangerous in accounting loops where sub-cent values compound.

### Contractual interest lost for later installments (fixed 2026-03-22)

**Fix:** `_skipped_contractual_interest` sums unpaid contractual interest for installments past `next_due` and up to `cutoff`. The forward pass uses `interest_cap = regular + skipped` to ensure later periods' contractual interest is included.

### is_fully_covered used pre-payment balance (fixed 2026-03-22)

**Symptom:** When a single payment fully paid off the loan, some allocations had `is_fully_covered = False` even though the loan's remaining balance was zero. This happened because the interest cap prevented full interest allocation to later installments (their interest hadn't accrued yet), and the coverage check failed since `total_allocated < installment.balance`.

**Root cause:** The allocation function checked `ending_balance <= tolerance` at the **start**, using the pre-payment principal. For a payment that fully pays off the loan, the pre-payment balance is the full remaining principal, so this check was always `False`. The override that corrects `is_fully_covered` when principal is fully covered never activated.

**Fix:** Moved the override to a post-loop fixup. After the allocation loop and spillover handling, compute `post_balance = ending_balance - principal_total`. If `post_balance <= tolerance`, iterate through allocations and fix `is_fully_covered` for any installment whose principal was fully allocated (within tolerance).

**Lesson:** When a boolean flag depends on the outcome of the allocation, it must be evaluated after the allocation completes, not before. Pre-payment state is only useful for pre-conditions; coverage determination requires post-payment state.

### Sub-cent principal residual left loan in impossible state (fixed 2026-03-22)

**Symptom:** After paying the exact scheduled amount, `is_fully_covered` and `is_fully_paid` returned `True` but `is_paid_off` returned `False` and `remaining_balance` showed a sub-cent residual (0.005--0.012). Consumer code marked all installments as PAID but never marked the loan as SETTLED.

**Root cause:** Full-precision interest accrual consumed slightly more than the schedule's 2dp interest, leaving a sub-cent gap on the principal. `allocate_payment_into_installments` and `Installment.is_fully_paid` used `_COVERAGE_TOLERANCE` (1 cent) for their checks, but `compute_state` only snapped `running_principal` to zero when negative — not when it was a sub-cent positive residual. `Loan.is_paid_off` checked `current_balance.is_zero()` (exact zero), which failed for the residual.

**Fix:** In `compute_state`, after subtracting `principal_paid` from `running_principal`, also snap to zero when the balance is positive but within `_COVERAGE_TOLERANCE`. This aligns the principal balance with the same tolerance used by the allocation and installment layers.

**Lesson:** All consistency checks across a system must use the same tolerance. When tolerance-based flags (`is_fully_covered`, `is_fully_paid`) coexist with exact checks (`is_paid_off` via `is_zero()`), the exact check must be relaxed to match, or the underlying data must be snapped so the exact check naturally passes.

### Settlement spill invariant (fixed 2026-03-23, root cause eliminated 2026-03-23)

**Original symptom:** `settlement.X_paid != sum(a.X_allocated for a in settlement.allocations)` for interest and principal.

**Original root cause:** The per-installment reservation held back principal from being allocated, creating "spill" that appeared in totals but not in allocations. Fixed with `_compute_spill` + `_reconcile_allocations`.

**Permanent fix:** The two-step allocation refactor eliminated the reservation and spill entirely. The invariant now holds by construction: `distribute_into_installments` fills from exact loan-level totals, and `_apply_residual` handles only the residual gap (loan-level accrual exceeding per-installment expectations). Per-installment owed amounts are still clamped to non-negative (`max(owed, 0)`) to prevent negative allocations.

### Interest double-counted on sequential early partial payments (fixed 2026-04-09)

**Symptom:** Two sequential `pay_installment` calls before the due date produced a different (worse) outcome than a single combined payment of the same total. The second payment charged spurious interest for the overlap period between `payment_date` and `interest_date`, starving the current installment of principal and preventing full coverage.

**Root cause:** `compute_state` set `last_payment_date = payment.datetime` after each payment. For early payments, `interest_date = max(payment_date, next_due_date) > payment_date`, so the accrual period `[last_payment_date, interest_date]` extended past the payment timestamp. The next payment then re-accrued interest from `payment_date` to its own `interest_date`, double-counting the overlap.

**Fix:** Introduced `last_accrual_end` in the forward pass, set to `max(payment.datetime, interest_date)` after each payment. All subsequent interest computation, regular/mora splitting, and installment snapshot building use `last_accrual_end` instead of `last_payment_date`. The user-facing `Loan.last_payment_date` property is unchanged — `LoanState` now carries both fields.

**Scope:** Both `Loan` and `BillingCycleLoan` were affected and fixed.

**Lesson:** In a forward pass that processes events chronologically, the start of the next accrual period must be the *end* of the previous one, not the timestamp of the event that triggered it. When `interest_date` and `payment_date` diverge, using the wrong one as the accrual boundary creates invisible overlap.
