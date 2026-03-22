# Loan

The `Loan` class models a personal loan where **everything emerges from the CashFlow**. A single `CashFlow` instance is the source of truth — it contains both expected items (the amortization schedule) and actual payments. Settlements, installment views, balances, and fines are all derived on demand by a forward pass over the cashflow. Nothing is decomposed or stored at payment time.

## Architecture

The Loan delegates computation to two focused components in `engines.py`:

- **`InterestCalculator`** — stateless interest math (regular + mora split). Holds `interest_rate`, `mora_interest_rate`, `mora_strategy`.
- **Pure functions** — compute all derived state. Key exports:
  - `compute_state(...)` — the forward pass that produces a `LoanState` (settlements, principal balance, fines applied, fines paid total, last payment date).
  - `build_installments(...)` — builds `Installment` objects from settlements + schedule.
  - `compute_fines_at(...)` — determines which due dates should have fines applied.
  - `allocate_payment_per_installment(...)` — runs the per-installment allocation algorithm.
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

All payment methods allocate funds **per-installment** in strict sequential order. Within each installment, the priority is:

1. **Fine** for this installment
2. **Mora interest** for this installment
3. **Regular interest** for this installment
4. **Principal** for this installment

Installment 1 is fully addressed before installment 2 receives anything.

## Forward Pass: `compute_state`

The central algorithm in `engines.compute_state`. It processes a merged timeline of payment events and fine observation dates in chronological order:

1. For each event (payment or fine observation), compute fines using only previously processed payments.
2. For payment events:
   a. Compute interest (regular + mora) since last payment.
   b. Build installment snapshot reflecting all prior allocations.
   c. Add skipped contractual interest for periods beyond the current due-date boundary.
   d. Run per-installment allocation (`allocate_payment_per_installment`).
   e. Update running principal, fines paid total, and allocation history.
   f. Create a `Settlement` object.
3. Return `LoanState` with all settlements and running state.

### `is_fully_covered` Post-Payment Fixup

The `allocate_payment_per_installment` function determines `is_fully_covered` per allocation in two stages:

1. **During the loop:** `Installment.allocate_from_payment` computes `is_covered` by comparing the total allocated against the installment's remaining balance. This can be `False` when interest caps prevent full interest allocation (e.g., paying all installments at once on the first due date).
2. **After the loop:** If the post-payment balance (`ending_balance - principal_total`) is within tolerance of zero, the function does a second pass. Any allocation whose principal is fully covered gets `is_fully_covered` overridden to `True`. This handles the case where the loan is paid off but interest caps prevented exact coverage of each installment's interest obligation.

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

## Installments and Settlements

### Design Philosophy

A loan is **not** a group of installments. Installments are a **consequence** of the loan terms plus a repayment strategy (scheduler). Settlements are a **consequence** of making a payment. Both are derived views computed from the cashflow, not stored state.

### Installment (`loan.installments`)

A frozen dataclass built by `build_installments` from settlements + schedule. Warp-aware.

Fields: `number`, `due_date`, `days_in_period`, `expected_payment`, `expected_principal`, `expected_interest`, `expected_mora`, `expected_fine`, `principal_paid`, `interest_paid`, `mora_paid`, `fine_paid`, `allocations`.

- `balance` — amount still owed to fully settle this installment.
- `is_fully_paid` — `True` when `balance` is within tolerance of zero.
- `allocate_from_payment(remaining, fine_remaining, mora_remaining, interest_remaining)` — allocates in priority order (fine -> mora -> interest -> principal), each capped by both the installment's remaining obligation and running caps.

### Settlement (`loan.settlements`)

A frozen dataclass capturing how a single payment was allocated. Derived by the forward pass.

Fields: `payment_amount`, `payment_date`, `fine_paid`, `interest_paid`, `mora_paid`, `principal_paid`, `remaining_balance`, `allocations`.

### Allocation

Defined in `loan/allocation.py`. Fields: `installment_number`, `principal_allocated`, `interest_allocated`, `mora_allocated`, `fine_allocated`, `is_fully_covered`.

Shared between Settlement (forward view) and Installment (reverse view).

### LoanState

Internal dataclass returned by `compute_state`: `settlements`, `principal_balance`, `fines_applied`, `fines_paid_total`, `last_payment_date`.

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

### Payment allocation order was loan-level, not per-installment (fixed 2026-03-20)

**Fix:** Rewrote allocation to be strictly per-installment sequential. `allocate_payment_per_installment` walks installments in order. Within each, `Installment.allocate_from_payment` applies fine -> mora -> interest -> principal.

**Lesson:** The per-installment interpretation is correct for Brazilian lending: installment 1's mora interest is more urgent than installment 2's fine.

### Sub-cent precision loss in allocation loop (fixed 2026-03-20)

**Fix:** Use `raw_amount` comparisons in the allocation loop instead of `Money`'s 2dp-rounded methods. Sub-cent allocations are included in component totals but excluded from the `allocations` list.

**Lesson:** `Money`'s `real_amount`-based comparisons are correct for business display but dangerous in accounting loops where sub-cent values compound.

### Contractual interest lost for later installments (fixed 2026-03-22)

**Fix:** `_skipped_contractual_interest` sums unpaid contractual interest for installments past `next_due` and up to `cutoff`. The forward pass uses `interest_cap = regular + skipped` to ensure later periods' contractual interest is included.

### is_fully_covered used pre-payment balance (fixed 2026-03-22)

**Symptom:** When a single payment fully paid off the loan, some allocations had `is_fully_covered = False` even though the loan's remaining balance was zero. This happened because the interest cap prevented full interest allocation to later installments (their interest hadn't accrued yet), and the coverage check failed since `total_allocated < installment.balance`.

**Root cause:** `allocate_payment_per_installment` checked `ending_balance <= tolerance` at the **start** of the function (line 183), using the pre-payment principal. For a payment that fully pays off the loan, the pre-payment balance is the full remaining principal, so this check was always `False`. The override that corrects `is_fully_covered` when principal is fully covered never activated.

**Fix:** Moved the override to a post-loop fixup. After the allocation loop and spillover handling, compute `post_balance = ending_balance - principal_total`. If `post_balance <= tolerance`, iterate through allocations and fix `is_fully_covered` for any installment whose principal was fully allocated (within tolerance).

**Lesson:** When a boolean flag depends on the outcome of the allocation, it must be evaluated after the allocation completes, not before. Pre-payment state is only useful for pre-conditions; coverage determination requires post-payment state.

### Sub-cent principal residual left loan in impossible state (fixed 2026-03-22)

**Symptom:** After paying the exact scheduled amount, `is_fully_covered` and `is_fully_paid` returned `True` but `is_paid_off` returned `False` and `remaining_balance` showed a sub-cent residual (0.005--0.012). Consumer code marked all installments as PAID but never marked the loan as SETTLED.

**Root cause:** Full-precision interest accrual consumed slightly more than the schedule's 2dp interest, leaving a sub-cent gap on the principal. `allocate_payment_per_installment` and `Installment.is_fully_paid` used `_COVERAGE_TOLERANCE` (1 cent) for their checks, but `compute_state` only snapped `running_principal` to zero when negative — not when it was a sub-cent positive residual. `Loan.is_paid_off` checked `current_balance.is_zero()` (exact zero), which failed for the residual.

**Fix:** In `compute_state`, after subtracting `principal_paid` from `running_principal`, also snap to zero when the balance is positive but within `_COVERAGE_TOLERANCE`. This aligns the principal balance with the same tolerance used by the allocation and installment layers.

**Lesson:** All consistency checks across a system must use the same tolerance. When tolerance-based flags (`is_fully_covered`, `is_fully_paid`) coexist with exact checks (`is_paid_off` via `is_zero()`), the exact check must be relaxed to match, or the underlying data must be snapped so the exact check naturally passes.
