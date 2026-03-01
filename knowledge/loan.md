# Loan

The `Loan` class is a state machine that models a personal loan with daily-compounding interest, configurable schedulers, late-payment fines, and mora interest. It tracks recorded payments and computes balances, cash flows, and amortization schedules on demand.

## Constructor Parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `principal` | `Money` | required | Must be positive |
| `interest_rate` | `InterestRate` | required | Annual rate |
| `due_dates` | `List[datetime]` | required | Sorted automatically |
| `disbursement_date` | `Optional[datetime]` | now | When funds are released; must be strictly before first due date |
| `scheduler` | `Optional[Type[BaseScheduler]]` | `PriceScheduler` | Amortization strategy |
| `fine_rate` | `Optional[Decimal]` | `0.02` (2%) | Fine as fraction of expected payment |
| `grace_period_days` | `int` | `0` | Days after due date before fines apply |
| `mora_interest_rate` | `Optional[InterestRate]` | `interest_rate` | Rate used for mora (late) interest; defaults to the base rate |
| `mora_strategy` | `MoraStrategy` | `COMPOUND` | How mora interest is computed (see Mora Strategy below) |

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

- **`pay_installment(amount, description=None)`** — the common case. Records payment at `self.now()` and calculates interest up to `max(self.now(), next_due_date)`. Early or on-time payments accrue interest up to the due date (no discount). Late payments accrue interest up to `self.now()`, so the borrower pays extra interest for the additional days beyond the due date. Late fines are also applied automatically. A large late payment naturally covers the missed installment **and** eats into future installments — the allocation (fines → interest → principal) and `_covered_due_date_count()` handle this without special-casing.

- **`anticipate_payment(amount, installments=None, description=None)`** — early payment with discount. Records payment at `self.now()` and calculates interest only up to `self.now()` (fewer days = less interest charged). When `installments` is provided (1-based numbers), the corresponding expected cash-flow items are temporally deleted via `CashFlowItem.delete()`.

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

Each entry contains: `payment_number`, `due_date`, `days_in_period`, `beginning_balance`, `payment_amount`, `principal_payment`, `interest_payment`, `ending_balance`. The schedule auto-calculates `total_payments`, `total_interest`, and `total_principal`.

## Schedulers

All schedulers implement `BaseScheduler.generate_schedule(principal, interest_rate, due_dates, disbursement_date) -> PaymentSchedule`.

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

- `calculate_late_fines(as_of_date)` scans all due dates up to `as_of_date`, applies one fine per missed due date (never duplicated), and stores them in `fines_applied: Dict[datetime, Money]`.
- `is_payment_late(due_date, as_of_date)` respects `grace_period_days`.
- `is_paid_off` requires zero principal **and** zero outstanding fines.
- Fine amounts are calculated from the **original** schedule (`get_original_schedule`), not the rebuilt schedule.

### Mora Interest

When `pay_installment` is called after the due date, `interest_date = max(self.now(), next_due_date)` causes interest to accrue beyond the due date up to the actual payment date. The interest is split into two separate `CashFlowItem` entries:

- **Regular interest** (`"actual_interest"`) — accrued from last payment to the due date using `interest_rate`.
- **Mora interest** (`"actual_mora_interest"`) — accrued from the due date to the payment date using `mora_interest_rate`.

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

The `accrued_interest` property also respects `mora_interest_rate` and `mora_strategy`. When the borrower is past the next unpaid due date, accrued interest is split internally into regular and mora components using `_compute_accrued_interest`, so `current_balance` reflects the true outstanding amount under the configured mora terms.

### Late Overpayment

A large late payment flows through the standard allocation pipeline (fines -> interest -> principal) with no special-casing. The excess principal naturally covers multiple installments because `_covered_due_date_count()` compares the remaining balance against original schedule milestones.

Example: $10k loan, 3 monthly installments at 6%, borrower misses installment 1 and pays $7,000 two weeks late. Allocation: ~$67 fine, ~$72 mora interest (45 days), ~$6,861 principal. The principal reduction covers installments 1 and 2, leaving only installment 3 projected.

## Cash Flow Generation

- `generate_expected_cash_flow()` — disbursement (positive, category `"expected_disbursement"`) plus original scheduled payments split into interest (`"expected_interest"`) and principal (`"expected_principal"`) items (negative). Uses `get_original_schedule()`.
- `get_actual_cash_flow()` — expected items plus recorded payments (`"actual_interest"`, `"actual_mora_interest"`, `"actual_principal"`, `"actual_fine"`) and fine-application events (`"fine_applied"`).

### CashFlowItem Categories

All categories are explicitly prefixed to distinguish expected schedule items from actual recorded payments:

| Category | Origin | Meaning |
|---|---|---|
| `"expected_disbursement"` | Expected | Loan disbursement |
| `"expected_interest"` | Expected | Scheduled interest payment |
| `"expected_principal"` | Expected | Scheduled principal payment |
| `"actual_interest"` | Actual | Regular interest paid (up to due date) |
| `"actual_mora_interest"` | Actual | Mora interest paid (beyond due date) |
| `"actual_principal"` | Actual | Principal paid |
| `"actual_fine"` | Actual | Fine paid |
| `"fine_applied"` | Event | Fine applied to loan (increases amount owed) |

## Installments and Settlements

### Design Philosophy

A loan is **not** a group of installments. Installments are a **consequence** of the loan terms plus a repayment strategy (scheduler). Settlements are a **consequence** of making a payment. Both are derived views computed from the cash flow, not stored state.

### Installment (`loan.installments`)

A frozen dataclass representing one period of the repayment plan. Built from the original schedule on demand. Warp-aware: all fields reflect the state at `self.now()`.

Fields: `number`, `due_date`, `days_in_period`, `expected_payment`, `expected_principal`, `expected_interest`, `expected_mora`, `expected_fine`, `principal_paid`, `interest_paid`, `mora_paid`, `fine_paid`, `allocations: List[SettlementAllocation]`.

Computed properties:
- `balance: Money` — the amount still owed to fully settle this installment: `(expected_principal + expected_interest + expected_mora + expected_fine) - (principal_paid + interest_paid + mora_paid + fine_paid)`. Clamped to zero.
- `is_fully_paid: bool` — `True` when `balance` is zero. Single source of truth for payment status.

Field semantics:
- `expected_payment`, `expected_principal`, `expected_interest` come from the original schedule.
- `expected_fine` comes from `Loan.fines_applied` for the installment's due date.
- `expected_mora` is computed by the Loan: for covered installments it equals `mora_paid`; for the first uncovered overdue installment it is the accrued mora from the due date to `self.now()` using `_compute_accrued_interest`; for all other installments it is zero.
- `*_paid` fields are aggregated totals from all settlement allocations attributed to this installment.
- `allocations` is the reverse view of Settlement: all `SettlementAllocation`s that touched this installment.
- Created via `Installment.from_schedule_entry(entry, allocations, expected_mora, expected_fine)`.
- `PaymentScheduleEntry` remains the internal scheduler data structure. `Installment` is the public-facing API.

### Settlement (`loan.settlements`, returned by payment methods)

A frozen dataclass capturing how a single payment was allocated. Reconstructed from the cash flow (`_all_payments` and `_actual_schedule_entries`) rather than stored as separate state.

Fields: `payment_amount`, `payment_date`, `fine_paid`, `interest_paid`, `mora_paid`, `principal_paid`, `remaining_balance`, `allocations: List[SettlementAllocation]`.

- `allocations` shows per-installment detail: which installments the payment covered and how much principal/interest/mora/fine went to each.
- Interest, mora, and fines are attributed to the first installment touched. Principal is distributed across installments using milestone comparison against the original schedule.
- All three payment methods (`record_payment`, `pay_installment`, `anticipate_payment`) return a `Settlement`.
- The `settlements` property reconstructs all settlements by querying the cash flow. Warp-aware: only includes settlements with `payment_date <= self.now()`.

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
