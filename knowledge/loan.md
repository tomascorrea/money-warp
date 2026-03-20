# Loan

The `Loan` class is a state machine that models a personal loan with daily-compounding interest, configurable schedulers, late-payment fines, and mora interest. It tracks recorded payments and computes balances, cash flows, and amortization schedules on demand.

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

`Loan` also keeps `_actual_payment_datetimes: List[datetime]`, one entry per `record_payment` call, so settlements and cash-flow grouping use full timestamps while schedule rows use calendar `due_date: date` values.

## Three-Date Payment Model

Every payment internally carries three dates:

| Date | Meaning | Default |
|---|---|---|
| `payment_date` | When the money moved | Required |
| `interest_date` | Cutoff for interest accrual calculation | `payment_date` |
| `processing_date` | When the system recorded the event (audit trail) | `self.now()` |

The **interest_date** controls how many days of interest are charged. Fewer days = less interest = discount for the borrower. This decouples "when money arrived" from "how much interest to charge."

## Payment Methods

### Sugar Methods (Public API)

Neither method takes a date parameter — they use `self.now()` (which respects `Warp` context for time travel).

- **`pay_installment(amount, description=None)`** — the common case. Records payment at `self.now()` and calculates interest up to `max(self.now(), next_due_date)`. Works correctly for all three timing scenarios:
  - **Early payment** (before due date): interest accrues up to the due date. The borrower pays the full scheduled interest — no discount. The installment is fully covered if the amount is sufficient.
  - **On-time payment**: interest matches the scheduled amount exactly.
  - **Late payment**: interest accrues up to `self.now()`, so the borrower pays extra interest (mora) for the days beyond the due date. Late fines are also applied automatically.

  A large payment naturally covers the current installment **and** eats into future installments — the per-installment allocation and `_covered_due_date_count()` handle this without special-casing.

- **`anticipate_payment(amount, installments=None, description=None)`** — early payment **with interest discount**. Records payment at `self.now()` and calculates interest only up to `self.now()` (fewer days = less interest charged). When `installments` is provided (1-based numbers), the corresponding expected cash-flow items are temporally deleted via `CashFlowItem.delete()`.

### Early Payment vs Anticipation

These are distinct concepts:

| | `pay_installment` (early payment) | `anticipate_payment` (anticipation) |
|---|---|---|
| **Interest accrual** | Up to the **due date** | Up to the **payment date** |
| **Discount** | None — borrower pays scheduled interest | Yes — fewer days = less interest |
| **Installment status** | Fully covered (if amount sufficient) | NOT fully covered (interest < scheduled) |
| **Use case** | Borrower wants to pay ahead of time, no discount expected | Borrower negotiates early payoff with reduced interest |
| **Test folder** | `up_to_date_payments/` | `antecipation/` |

- **`calculate_anticipation(installments)`** — pure calculation (no side effects). Returns an `AnticipationResult(amount, installments)` with the PV-based amount the borrower must pay today to eliminate specific installments. The formula: `amount = current_balance - PV(kept payments at kept dates)`. When all remaining installments are anticipated, `amount = current_balance` (full early payoff). Validates that all requested installment numbers are unpaid and in range.

### Explicit-Date Method

- **`record_payment(amount, payment_date, interest_date=None, processing_date=None, description=None)`** — full control over all dates. When `interest_date` is omitted it defaults to `payment_date` (borrower gets discount for early payment). Useful in tests and batch processing where you need explicit dates.

### Payment Allocation

All payment methods allocate funds in strict priority order:

1. **Outstanding fines** first
2. **Accrued interest** (daily-compounded since last payment, up to `interest_date`; split into regular + mora when late)
3. **Principal** remainder

Interest days and principal balance are pre-computed at the top of `record_payment` using `payment_date` as the filter for existing payments, before any internal state is mutated.

## Dynamic Amortization Schedule

### `get_amortization_schedule()`

Returns a clean, ordered list of `PaymentScheduleEntry` records. Past entries come first (reflecting actual payments: real interest paid, real principal paid), followed by projected entries (recalculated from remaining principal, same rate, remaining unpaid due dates, and last payment date as the disbursement reference — same count of remaining payments, new PMT).

If no payments have been made, returns the original static schedule.

### `get_original_schedule()`

Always returns the static schedule based on original loan terms, ignoring any payments. Used internally for fine calculations (`get_expected_payment_amount`) and for comparison.

### PaymentScheduleEntry

Each entry contains: `payment_number`, `due_date` (`date`), `days_in_period`, `beginning_balance`, `payment_amount`, `principal_payment`, `interest_payment`, `ending_balance`. The schedule auto-calculates `total_payments`, `total_interest`, and `total_principal`.

## Schedulers

All schedulers implement `BaseScheduler.generate_schedule(principal, interest_rate, due_dates: List[date], disbursement_date: datetime) -> PaymentSchedule`.

### PriceScheduler (French Amortization)

Fixed total payment per period. Interest portion decreases and principal portion increases over time. The PMT is computed as `principal / sum(1 / (1 + daily_rate)^n)` where `n` is the number of days from disbursement to each due date.

#### Matching external systems with `InterestRate` precision

Some lending systems (e.g. Brazilian banks) truncate the effective annual rate to a fixed number of decimal places before deriving the daily rate. This introduces a tiny difference in the daily rate which can shift the PMT by several cents on large principals.

`InterestRate` supports two optional parameters to reproduce this behaviour:

- `precision: int` — number of decimal places to keep on the effective annual rate during conversions. `None` (default) preserves full precision.
- `rounding: str` — Python `decimal` rounding mode (default `ROUND_HALF_UP`).

Precision is applied in `_to_effective_annual()`, the hub through which `to_daily()`, `to_monthly()`, and `to_annual()` all pass. The stored `_decimal_rate` and the converted output rate are **not** separately quantized — they naturally inherit limited precision from the quantized annual.

Example: a Brazilian system stores the annual rate as `0.126825` (6 decimal places) for a 1% monthly rate whose full annual is `0.126825030...`. To match:

```python
rate = InterestRate("1% m", precision=6)
loan = Loan(Money("10000"), rate, due_dates, disbursement_date)
```

### InvertedPriceScheduler (Constant Amortization System / SAC)

Fixed principal payment per period (`principal / number_of_payments`). Interest is computed on the outstanding balance, so total payment decreases over time. The last payment adjusts to ensure zero final balance.

## Late Payments

A late payment incurs two costs, both handled automatically by `pay_installment` and `record_payment`:

1. **Fines** — a flat percentage of the missed installment amount.
2. **Mora interest** — extra daily-compounded interest for the days beyond the due date.

### Fines

- `calculate_late_fines(as_of_date)` scans all due dates up to `as_of_date`, applies one fine per missed due date (never duplicated), and stores them in `fines_applied: Dict[date, Money]`.
- `is_payment_late(due_date, as_of_date)` respects `grace_period_days`.
- `is_paid_off` requires zero `current_balance` (principal, interest, mora, and fines all zero).
- Fine amounts are calculated from the **original** schedule (`get_original_schedule`), not the rebuilt schedule.

### Mora Interest

When `pay_installment` is called after the due date, `interest_date = max(self.now(), next_due_date)` causes interest to accrue beyond the due date up to the actual payment date. The interest is split into two separate `CashFlowItem` entries:

- **Regular interest** (`"interest"`, kind=HAPPENED) — accrued from last payment to the due date using `interest_rate`.
- **Mora interest** (`"mora_interest"`, kind=HAPPENED) — accrued from the due date to the payment date using `mora_interest_rate`.

On-time and early payments produce only a regular interest item (no mora). Regular interest is always computed with the base `interest_rate`; mora interest uses `mora_interest_rate` (which defaults to `interest_rate` when not provided).

### Mora Strategy (`MoraStrategy` enum)

The `mora_strategy` parameter controls how mora interest is computed when a payment is late. Both strategies share the same regular interest calculation; they differ only in the base amount used for the mora portion.

**`MoraStrategy.COMPOUND`** (default):
- `regular = interest_rate.accrue(principal, regular_days)`
- `mora = mora_interest_rate.accrue(principal + regular, mora_days)`

The mora rate is applied to the accumulated balance (principal plus accrued regular interest). This means mora compounds on top of regular interest.

**`MoraStrategy.SIMPLE`**:
- `regular = interest_rate.accrue(principal, regular_days)`
- `mora = mora_interest_rate.accrue(principal, mora_days)`

The mora rate is applied independently to the outstanding principal. Regular interest does not affect the mora base.

With the same rates, COMPOUND always produces more mora than SIMPLE because it applies the mora rate to a larger base. When `mora_interest_rate` equals `interest_rate` and strategy is `COMPOUND`, the result is identical to a single continuous compounding period — preserving the original behaviour before the mora strategy feature was introduced.

The `interest_balance` and `mora_interest_balance` properties respect `mora_interest_rate` and `mora_strategy`. When the borrower is past the next unpaid due date, `_accrued_interest_components()` splits interest into regular and mora via `_compute_accrued_interest`. `current_balance = principal_balance + interest_balance + mora_interest_balance + fine_balance`.

## Balance Properties

The loan's outstanding amount is decomposed into four canonical components:

| Property | Type | Meaning |
|---|---|---|
| `principal_balance` | `Money` | Outstanding principal (original minus principal payments) |
| `interest_balance` | `Money` | Regular accrued interest since last payment |
| `mora_interest_balance` | `Money` | Mora accrued interest (days beyond due date) |
| `fine_balance` | `Money` | Unpaid fines (total applied minus fines paid) |
| `current_balance` | `Money` | Sum of all four components |

`_accrued_interest_components()` is the shared private helper that returns `(regular, mora)` — both `interest_balance` and `mora_interest_balance` delegate to it.

### Late Overpayment

A large late payment flows through the standard allocation pipeline (fines -> interest -> principal) with no special-casing. The excess principal naturally covers multiple installments because `_covered_due_date_count()` compares the remaining balance against original schedule milestones.

Example: $10k loan, 3 monthly installments at 6%, borrower misses installment 1 and pays $7,000 two weeks late. Allocation: ~$67 fine, ~$72 mora interest (45 days), ~$6,861 principal. The principal reduction covers installments 1 and 2, leaving only installment 3 projected.

## Cash Flow Generation

- `generate_expected_cash_flow()` — disbursement (positive, category `"disbursement"`, kind=EXPECTED) plus original scheduled payments split into interest (`"interest"`) and principal (`"principal"`) items (negative, kind=EXPECTED). Uses `get_original_schedule()`.
- `get_actual_cash_flow()` — expected items plus recorded payments (kind=HAPPENED) and fine-application events.

### CashFlowEntry Hierarchy

`CashFlowEntry` is an abstract base class with two concrete subclasses:

- **`ExpectedCashFlowEntry`** — projected items (e.g. loan schedule). `kind` property returns `CashFlowType.EXPECTED`.
- **`HappenedCashFlowEntry`** — recorded facts (e.g. actual payments). `kind` property returns `CashFlowType.HAPPENED`.

The `CashFlowItem` constructor accepts `kind=CashFlowType.EXPECTED` or `kind=CashFlowType.HAPPENED` (default) and instantiates the correct subclass. Filtering works via `entry.kind == CashFlowType.EXPECTED`, `isinstance(entry, ExpectedCashFlowEntry)`, or the query shortcuts `cf.query.expected` / `cf.query.happened`.

### CashFlowItem Categories

Categories are clean domain names. The expected-vs-happened distinction is structural (subclass type), not encoded in the category string:

| Category | Kind | Meaning |
|---|---|---|
| `"disbursement"` | EXPECTED | Loan disbursement |
| `"tax"` | EXPECTED | Tax deducted at disbursement |
| `"interest"` | EXPECTED | Scheduled interest payment |
| `"principal"` | EXPECTED | Scheduled principal payment |
| `"interest"` | HAPPENED | Regular interest paid (up to due date) |
| `"mora_interest"` | HAPPENED | Mora interest paid (beyond due date) |
| `"principal"` | HAPPENED | Principal paid |
| `"fine"` | HAPPENED | Fine paid or fine applied (distinguished by sign) |

## Installments and Settlements

### Design Philosophy

A loan is **not** a group of installments. Installments are a **consequence** of the loan terms plus a repayment strategy (scheduler). Settlements are a **consequence** of making a payment. Both are derived views computed from the cash flow, not stored state.

### Installment (`loan.installments`)

A frozen dataclass representing one period of the repayment plan. Built from the original schedule on demand. Warp-aware: all fields reflect the state at `self.now()`.

Fields: `number`, `due_date` (`date`), `days_in_period`, `expected_payment`, `expected_principal`, `expected_interest`, `expected_mora`, `expected_fine`, `principal_paid`, `interest_paid`, `mora_paid`, `fine_paid`, `allocations: List[SettlementAllocation]`.

Computed properties:
- `balance: Money` — the amount still owed to fully settle this installment: `(expected_principal + expected_interest + expected_mora + expected_fine) - (principal_paid + interest_paid + mora_paid + fine_paid)`. Clamped to zero.
- `is_fully_paid: bool` — `True` when `balance` is zero. Single source of truth for payment status.

Field semantics:
- `expected_payment`, `expected_principal`, `expected_interest` come from the original schedule.
- `expected_fine` comes from `Loan.fines_applied` for the installment's due date.
- `expected_mora` is computed by the Loan: for covered installments it equals the sum of prior `mora_allocated` values; for the first uncovered overdue installment it is prior `mora_allocated` **plus** newly accrued mora (from last payment to `self.now()`) via `_compute_accrued_interest`; for all other installments it is zero. The cumulative form ensures `Installment.allocate` correctly computes `mora_owed = expected_mora - mora_paid` even when the same installment receives mora across multiple settlements.
- `*_paid` fields are aggregated totals from all settlement allocations attributed to this installment.
- `allocations` is the reverse view of Settlement: all `SettlementAllocation`s that touched this installment.
- Created via `Installment.from_schedule_entry(entry, allocations, expected_mora, expected_fine)`.
- `allocate(fine, mora, interest, principal)` — distributes four component pools against remaining obligations, returns `(SettlementAllocation, remaining_fine, remaining_mora, remaining_interest, remaining_principal)`. Used by `_build_settlement_allocations` to walk through installments in order.
- `PaymentScheduleEntry` remains the internal scheduler data structure. `Installment` is the public-facing API.

### Settlement (`loan.settlements`, returned by payment methods)

A frozen dataclass capturing how a single payment was allocated. Reconstructed from the cash flow (`_all_payments` and `_actual_schedule_entries`) rather than stored as separate state.

Fields: `payment_amount`, `payment_date`, `fine_paid`, `interest_paid`, `mora_paid`, `principal_paid`, `remaining_balance`, `allocations: List[SettlementAllocation]`.

- `allocations` shows per-installment detail: which installments the payment covered and how much principal/interest/mora/fine went to each.
- All three payment methods (`record_payment`, `pay_installment`, `anticipate_payment`) return a `Settlement`.
- The `settlements` property reconstructs all settlements by querying the cash flow. Warp-aware: only includes settlements with `payment_date <= self.now()`.
- **Reconciliation invariant:** For every settlement, each component total must equal the sum of its per-installment allocations: `settlement.X_paid == sum(a.X_allocated for a in settlement.allocations)` for X in {principal, interest, mora, fine}.

#### Per-Installment Allocation

Each component (fine, mora, interest, principal) is distributed as a **separate pool** across installments in order. The four pools come from `_allocate_payment` (loan-level totals). Each installment's `allocate()` method caps each component at the installment's remaining obligation for that component:

1. Build an installment snapshot (`_build_installments_snapshot`) reflecting all prior settlement allocations — avoids circular dependency with `self.settlements`.
2. For each installment in order, `Installment.allocate(fine_pool, mora_pool, interest_pool, principal_pool)` takes what's owed per component, returns the allocation and remaining pools.
3. Fully-paid installments consume nothing and are skipped.
4. When the loan is fully paid off (ending_balance ≈ 0), installments whose principal is fully covered are marked `is_fully_covered` even if their scheduled interest wasn't allocated from this specific payment.

The `settlements` property maintains a running `allocations_by_number` dict so each settlement sees the cumulative allocation state from prior settlements.

### AnticipationResult

Returned by `calculate_anticipation()`. Frozen dataclass with:
- `amount: Money` — the total amount to pay today to eliminate the specified installments.
- `installments: List[Installment]` — the installments being anticipated (removed).

### SettlementAllocation

Fields: `installment_number`, `principal_allocated`, `interest_allocated`, `mora_allocated`, `fine_allocated`, `is_fully_covered`.

Shared between Settlement (forward view: "this payment covered these installments") and Installment (reverse view: "these allocations covered me").

## TVM Sugar

- `loan.present_value(discount_rate=None, valuation_date=None)` — defaults to the loan's own rate and `loan.now()`.
- `loan.irr(guess=None)` — IRR of the expected cash flow.

Both methods are time-aware: inside a `Warp` context they reflect the warped date.

## Key Learnings

### Balance residual after full repayment (fixed 2026-02-20)

**Symptom:** After paying all scheduled installments, a residual balance of ~$103.36 persisted on a $10,000 loan.

**Root cause:** `record_payment` computed interest days via `self.days_since_last_payment(payment_date)`, which filtered `_all_payments` by `self.now()` (real wall-clock time). When installments were recorded sequentially for future dates, previously-recorded future payments were invisible, leading to inflated day counts, too much interest, too little principal, and a non-zero residual.

**Fix:** Pre-compute `days` and `principal_balance` at the top of `record_payment` using `payment_date` as the filter, before step 1 modifies `_all_payments`.

**Lesson:** Any method that reads loan state and then mutates it must snapshot the relevant values first. Time-dependent queries inside mutation methods must use the payment's own date, not wall-clock time.

### Warp creates deep clones (important for sugar methods)

Sugar methods (`pay_installment`, `anticipate_payment`) use `self.now()` for the payment date. Inside a `Warp` context, `self.now()` returns the warped date — but payments on the warped loan do **not** persist back to the original. This is by design: Warp is for observation, not mutation. Use `record_payment(amount, date)` or `record_payment(...)` with explicit dates to set up loan state outside of Warp.

### Due date coverage uses cumulative principal, not payment count (fixed 2026-02-20)

**Symptom:** `_next_unpaid_due_date()` and `get_amortization_schedule()` would miscount covered due dates when partial payments, overpayments, or multiple anticipations were made.

**Root cause:** The original implementation used `len(self._actual_schedule_entries)` to determine how many due dates were covered — assuming one `record_payment` call = one installment. This broke with partial payments (inflated count) and large overpayments (undercounted).

**Fix:** `_covered_due_date_count()` compares the remaining principal (from the last actual entry) against the original schedule's `ending_balance` milestones. A due date is covered when remaining principal is at or below that entry's ending balance.

**Lesson:** Avoid coupling "number of events" to "progress through a schedule." Use the financial state (principal balance) as the source of truth.

### Merged schedule is a clean list, not tagged entries (fixed 2026-02-20)

**Symptom:** Tests and consumers of `get_amortization_schedule()` had to filter entries by an `is_actual` flag to separate past payments from projected ones, leading to boilerplate like `[e for e in schedule if not e.is_actual]`.

**Root cause:** `PaymentScheduleEntry` carried an `is_actual: bool` field that leaked an internal implementation detail into the data model. No business logic depended on the flag — it only served test filtering.

**Fix:** Removed `is_actual` from `PaymentScheduleEntry` entirely. The merged schedule is a clean, ordered list: past entries (from `_actual_schedule_entries`) come first by construction, followed by projected entries. Tests use positional indexing (`schedule[0]` for the recorded payment, `schedule[1:]` for projected) instead of filtering.

**Lesson:** Don't tag data with internal metadata that consumers must filter. If ordering already encodes the distinction, a flag is redundant. Keep data structures minimal — the fewer fields, the simpler the API.

### Late payments undercharged interest (fixed 2026-02-20)

**Symptom:** `pay_installment()` called after the due date charged interest only up to the due date, not up to the actual payment date. The borrower was undercharged for the extra late days.

**Root cause:** `pay_installment` set `interest_date = self._next_unpaid_due_date()`. When the borrower paid late (now > due_date), interest was capped at the due date instead of extending to the actual payment date.

**Fix:** Changed to `interest_date = max(self.now(), self._next_unpaid_due_date())`. Early/on-time payments still accrue interest up to the due date (unchanged). Late payments now accrue interest up to `self.now()` (extra days charged).

**Lesson:** A late payment incurs two costs: fines (flat percentage of missed payment) and mora interest (extra daily-compounded interest beyond the due date). Both must be accounted for. The `max()` pattern ensures one method handles all three timing scenarios correctly.

### Same-time payments misattributed (fixed 2026-02-27)

**Symptom:** When two payments were recorded at the exact same datetime, the second settlement had all-zero amounts (`principal_paid = 0`, `interest_paid = 0`, etc.).

**Root cause:** `_extract_payment_items` grouped `CashFlowItem`s from `_all_payments` by matching `item.datetime == entry.due_date`. When two entries shared the same `due_date`, the break condition (`item.datetime != entry.due_date and idx > group_start`) was never true, so the first entry consumed all items, leaving nothing for the second.

**Fix:** Replaced datetime-based grouping with positional offset tracking. `record_payment` now records `len(self._all_payments)` into `_payment_item_offsets` before calling `_allocate_payment`. `_extract_payment_items` slices `_all_payments` by `[offsets[i]:offsets[i+1]]` instead of walking by datetime. This is simpler, faster (O(items-in-this-payment) vs O(all-items-up-to-this-payment)), and correct regardless of datetime values.

**Lesson:** Don't use a value that can be non-unique (datetime) as a grouping boundary when a positional invariant (sequential append order) already provides an unambiguous one.

### Day-count mismatch with non-midnight disbursement (fixed 2026-03-20)

**Symptom:** When `disbursement_date` had a non-midnight time component (e.g. 19:53), the first installment was never marked `is_fully_covered` even when the payment was large enough to cover it. The settlement interest was consistently lower than the scheduled interest by about one day's worth.

**Root cause:** The scheduler computes `days_in_period` using date subtraction (`(due_date - prev_date).days`), but `_compute_interest_snapshot` used datetime subtraction (`(interest_date - last_pay_date).days`). Python's `timedelta.days` truncates: `(April 12 00:00 - March 6 19:53).days == 36`, while `(April 12 - March 6).days == 37`. The 1-day shortfall meant settlement interest was less than the schedule expected, so `Installment.allocate` could not fully cover the first installment's interest obligation.

**Fix:** Use `.date()` on both operands in all three day-count calculations: `_compute_interest_snapshot`, `_build_installments_snapshot` (mora days), and `days_since_last_payment`. This aligns with the scheduler's calendar-day convention. Financial day counting operates on dates, not timestamps.

**Lesson:** When one subsystem counts days using dates and another uses datetimes, the results will diverge whenever a timestamp has a non-midnight time. Normalize to the same type (`.date()`) at every day-count boundary.

### Mora under-distributed across allocations (fixed 2026-03-19)

**Symptom:** `settlement.mora_paid` was consistently higher than `sum(a.mora_allocated for a in settlement.allocations)`. The difference was always positive and exactly equalled the mora allocated to the same installment in prior settlements.

**Root cause:** `_build_installments_snapshot` computed `expected_mora` for the first uncovered installment (`i == covered`) using only the newly accrued mora for the current period. It did not include mora already attributed from prior settlements. When `Installment.allocate` ran `mora_owed = expected_mora - mora_paid`, the `mora_paid` (cumulative from prior allocations) was subtracted from a non-cumulative `expected_mora`, producing an artificially low `mora_owed` and leaving mora unallocated.

**Trigger condition:** Two or more consecutive late payments where the same installment remains uncovered (partial late payments).

**Fix:** `expected_mora = prior_mora + accrued_mora` — sum the mora already allocated from prior settlements before adding the newly accrued amount. This makes the `i == covered` branch cumulative, matching the pattern already used for fully-covered installments (`i < covered`).

**Lesson:** When a derived quantity (expected_mora) participates in a subtraction against a cumulative counter (mora_paid), the derived quantity must also be cumulative. Mixing period-level and cumulative values in the same expression produces silent under-distribution.
