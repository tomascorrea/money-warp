# Loan

The `Loan` class is a state machine that models a personal loan with daily-compounding interest, configurable schedulers, and late-payment fines. It tracks recorded payments and computes balances, cash flows, and amortization schedules on demand.

## Constructor Parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `principal` | `Money` | required | Must be positive |
| `interest_rate` | `InterestRate` | required | Annual rate |
| `due_dates` | `List[datetime]` | required | Sorted automatically |
| `disbursement_date` | `Optional[datetime]` | first due date - 30d | When funds are released |
| `scheduler` | `Optional[Type[BaseScheduler]]` | `PriceScheduler` | Amortization strategy |
| `late_fee_rate` | `Optional[Decimal]` | `0.02` (2%) | Fine as fraction of expected payment |
| `grace_period_days` | `int` | `0` | Days after due date before fines apply |

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

- **`anticipate_payment(amount, description=None)`** — early payment with discount. Records payment at `self.now()` and calculates interest only up to `self.now()` (fewer days = less interest charged).

### Explicit-Date Methods

- **`record_payment(amount, payment_date, description=None)`** — convenience wrapper that sets `interest_date = payment_date` (discount). Useful in tests and batch processing where you need explicit dates.

- **`_record_payment(amount, payment_date, interest_date=None, processing_date=None, description=None)`** — the low-level workhorse. Full control over all three dates.

### Payment Allocation

All payment methods allocate funds in strict priority order:

1. **Outstanding fines** first
2. **Accrued interest** (daily-compounded since last payment, up to `interest_date`)
3. **Principal** remainder

Interest days and principal balance are pre-computed at the top of `_record_payment` using `payment_date` as the filter for existing payments, before any internal state is mutated.

## Dynamic Amortization Schedule

### `get_amortization_schedule()`

Returns a clean, ordered list of `PaymentScheduleEntry` records. Past entries come first (reflecting actual payments: real interest paid, real principal paid), followed by projected entries (recalculated from remaining principal, same rate, remaining unpaid due dates, and last payment date as the disbursement reference — same count of remaining payments, new PMT).

If no payments have been made, returns the original static schedule.

### `get_original_schedule()`

Always returns the static schedule based on original loan terms, ignoring any payments. Used internally for late fee calculations (`get_expected_payment_amount`) and for comparison.

### PaymentScheduleEntry

Each entry contains: `payment_number`, `due_date`, `days_in_period`, `beginning_balance`, `payment_amount`, `principal_payment`, `interest_payment`, `ending_balance`. The schedule auto-calculates `total_payments`, `total_interest`, and `total_principal`.

## Schedulers

All schedulers implement `BaseScheduler.generate_schedule(principal, interest_rate, due_dates, disbursement_date) -> PaymentSchedule`.

### PriceScheduler (French Amortization)

Fixed total payment per period. Interest portion decreases and principal portion increases over time. The PMT is computed as `principal / sum(1 / (1 + daily_rate)^n)` where `n` is the number of days from disbursement to each due date.

### InvertedPriceScheduler (Constant Amortization System / SAC)

Fixed principal payment per period (`principal / number_of_payments`). Interest is computed on the outstanding balance, so total payment decreases over time. The last payment adjusts to ensure zero final balance.

## Late Payment Fines

- `calculate_late_fines(as_of_date)` scans all due dates up to `as_of_date`, applies one fine per missed due date (never duplicated), and stores them in `fines_applied: Dict[datetime, Money]`.
- `is_payment_late(due_date, as_of_date)` respects `grace_period_days`.
- `is_paid_off` requires zero principal **and** zero outstanding fines.
- Fine amounts are calculated from the **original** schedule (`get_original_schedule`), not the rebuilt schedule.

## Cash Flow Generation

- `generate_expected_cash_flow()` — disbursement (positive, category `"disbursement"`) plus original scheduled payments split into interest and principal items (negative). Uses `get_original_schedule()`.
- `get_actual_cash_flow()` — expected items plus recorded payments and fine-application events.

## TVM Sugar

- `loan.present_value(discount_rate=None, valuation_date=None)` — defaults to the loan's own rate and `loan.now()`.
- `loan.irr(guess=None)` — IRR of the expected cash flow.

Both methods are time-aware: inside a `Warp` context they reflect the warped date.

## Key Learnings

### Balance residual after full repayment (fixed 2026-02-20)

**Symptom:** After paying all scheduled installments, a residual balance of ~$103.36 persisted on a $10,000 loan.

**Root cause:** `record_payment` computed interest days via `self.days_since_last_payment(payment_date)`, which filtered `_all_payments` by `self.now()` (real wall-clock time). When installments were recorded sequentially for future dates, previously-recorded future payments were invisible, leading to inflated day counts, too much interest, too little principal, and a non-zero residual.

**Fix:** Pre-compute `days` and `principal_balance` at the top of `_record_payment` using `payment_date` as the filter, before step 1 modifies `_all_payments`.

**Lesson:** Any method that reads loan state and then mutates it must snapshot the relevant values first. Time-dependent queries inside mutation methods must use the payment's own date, not wall-clock time.

### Warp creates deep clones (important for sugar methods)

Sugar methods (`pay_installment`, `anticipate_payment`) use `self.now()` for the payment date. Inside a `Warp` context, `self.now()` returns the warped date — but payments on the warped loan do **not** persist back to the original. This is by design: Warp is for observation, not mutation. Use `record_payment(amount, date)` or `_record_payment(...)` with explicit dates to set up loan state outside of Warp.

### Due date coverage uses cumulative principal, not payment count (fixed 2026-02-20)

**Symptom:** `_next_unpaid_due_date()` and `get_amortization_schedule()` would miscount covered due dates when partial payments, overpayments, or multiple anticipations were made.

**Root cause:** The original implementation used `len(self._actual_schedule_entries)` to determine how many due dates were covered — assuming one `_record_payment` call = one installment. This broke with partial payments (inflated count) and large overpayments (undercounted).

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
