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

## Payment Recording and Allocation

`record_payment(amount, payment_date, description)` applies funds in strict priority order:

1. **Outstanding fines** first
2. **Accrued interest** (daily-compounded since last payment)
3. **Principal** remainder

Interest days and principal balance are pre-computed at the top of `record_payment` using `payment_date` as the cutoff, before any internal state is mutated. This is critical for correctness when recording multiple future-dated payments in sequence (see Key Learnings below).

## Schedulers

All schedulers implement `BaseScheduler.generate_schedule(principal, interest_rate, due_dates, disbursement_date) -> PaymentSchedule`.

### PriceScheduler (French Amortization)

Fixed total payment per period. Interest portion decreases and principal portion increases over time. The PMT is computed as `principal / sum(1 / (1 + daily_rate)^n)` where `n` is the number of days from disbursement to each due date.

### InvertedPriceScheduler (Constant Amortization System / SAC)

Fixed principal payment per period (`principal / number_of_payments`). Interest is computed on the outstanding balance, so total payment decreases over time. The last payment adjusts to ensure zero final balance.

### PaymentSchedule

A list of `PaymentScheduleEntry` dataclass instances, each containing: `payment_number`, `due_date`, `days_in_period`, `beginning_balance`, `payment_amount`, `principal_payment`, `interest_payment`, `ending_balance`. The schedule auto-calculates `total_payments`, `total_interest`, and `total_principal`.

## Late Payment Fines

- `calculate_late_fines(as_of_date)` scans all due dates up to `as_of_date`, applies one fine per missed due date (never duplicated), and stores them in `fines_applied: Dict[datetime, Money]`.
- `is_payment_late(due_date, as_of_date)` respects `grace_period_days`.
- `is_paid_off` requires zero principal **and** zero outstanding fines.

## Cash Flow Generation

- `generate_expected_cash_flow()` — disbursement (positive, category `"disbursement"`) plus scheduled payments split into interest and principal items (negative).
- `get_actual_cash_flow()` — expected items plus recorded payments and fine-application events.
- `get_amortization_schedule()` — delegates to the configured scheduler.

## Sugar Syntax

- `loan.present_value(discount_rate=None, valuation_date=None)` — defaults to the loan's own rate and `loan.now()`.
- `loan.irr(guess=None)` — IRR of the expected cash flow.

Both methods are time-aware: inside a `Warp` context they reflect the warped date.

## Key Learnings

### Balance residual after full repayment (fixed 2026-02-20)

**Symptom:** After paying all scheduled installments, a residual balance of ~$103.36 persisted on a $10,000 loan.

**Root cause:** `record_payment` computed interest days via `self.days_since_last_payment(payment_date)`, which filtered `_all_payments` by `self.now()` (real wall-clock time). When installments were recorded sequentially for future dates, previously-recorded future payments were invisible, leading to inflated day counts, too much interest, too little principal, and a non-zero residual.

**Fix:** Pre-compute `days` and `principal_balance` at the top of `record_payment` using `payment_date` as the filter, before step 1 modifies `_all_payments`.

**Lesson:** Any method that reads loan state and then mutates it must snapshot the relevant values first. Time-dependent queries inside mutation methods must use the payment's own date, not wall-clock time.
