# Billing Cycle Loan

The `BillingCycleLoan` models a personal loan where principal is amortized on a fixed schedule (Price / SAC) but payment timing is driven by credit-card-like billing cycles. Unlike the standard `Loan`, the mora interest rate can change per billing cycle via a user-supplied callable.

## Architecture

`BillingCycleLoan` follows the same CashFlow-emergence philosophy as `Loan`: a single `CashFlow` is the source of truth, and all financial state (settlements, installments, balances, fines, statements) is derived on demand by a forward pass.

### Components

- **`BillingCycleLoan`** (facade) — wires billing cycle, scheduler, interest calculator, and mora rate resolver. Provides payment methods and property views.
- **`BaseBillingCycle`** — existing factory that generates closing dates and due dates. Enhanced with optional explicit `due_dates` and a `due_dates_between()` method.
- **`MoraRateResolver`** (protocol) — callable `(date, InterestRate) -> InterestRate` that adjusts the mora rate per cycle. The first argument is the cycle's closing date; the second is the base mora rate.
- **`engines.py`** (root) — shared building blocks (`InterestCalculator`, `MoraStrategy`, `MoraRateCallback`) used by both `Loan` and `BillingCycleLoan`. No dependency on domain objects.
- **`loan/engines.py`** — unified forward pass (`compute_state`) with an optional `mora_rate_for_event` callback, plus all allocation, fine, and installment logic. `Loan` omits the callback; `BillingCycleLoan` passes one.
- **`billing_cycle_loan/engines.py`** — thin product-specific layer: `resolve_mora_rate`, `make_mora_callback`, a wrapper `compute_state` that builds the callback and delegates, and `build_statements`.
- **`BillingCycleLoanStatement`** — per-period view combining schedule expectations with actual payments, mora rate used, and fine activity.

### Key Differences from Loan

| Aspect | Loan | BillingCycleLoan |
|---|---|---|
| Due dates | Explicit `List[date]` | Derived from `BillingCycle` (or explicit on the cycle) |
| Mora rate | Fixed `InterestRate` | Base rate + optional `MoraRateResolver` per cycle |
| Statements | None | `BillingCycleLoanStatement` per billing period |
| Closing dates | N/A | From `BillingCycle`, drives statement periods |

## Constructor Parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `principal` | `Money` | required | Must be positive |
| `interest_rate` | `InterestRate` | required | Annual contractual rate |
| `billing_cycle` | `BaseBillingCycle` | required | Generates closing and due dates |
| `start_date` | `datetime` | required | Start of first billing period |
| `num_installments` | `int` | required | Number of amortization periods |
| `disbursement_date` | `Optional[datetime]` | `now()` | Must be before first due date |
| `scheduler` | `Optional[Type[BaseScheduler]]` | `PriceScheduler` | Amortization strategy |
| `fine_rate` | `Optional[InterestRate]` | `InterestRate("2% annual")` | Fine rate on missed payments |
| `grace_period_days` | `int` | `0` | Days after due date before fines |
| `mora_interest_rate` | `Optional[InterestRate]` | `interest_rate` | Base mora rate |
| `mora_rate_resolver` | `Optional[MoraRateResolver]` | `None` | Per-cycle mora adjustment |
| `mora_strategy` | `MoraStrategy` | `COMPOUND` | How mora compounds |
| `working_day_calendar` | `Optional[WorkingDayCalendar]` | `EveryDayCalendar()` | Calendar for penalty due-date deferral; when a due date falls on a non-working day, fines and mora start from the next working day |

## Mora Rate Resolution

Two parameters work together:

1. **`mora_interest_rate`** — the base rate, used directly when no resolver is provided (constant, identical to `Loan`).
2. **`mora_rate_resolver`** — optional callable `(closing_date: date, base_mora_rate: InterestRate) -> InterestRate`. Called at each payment event to resolve the cycle-specific mora rate. The resolver receives the base rate and can adjust, replace, or pass it through.

Resolution happens in `resolve_mora_rate()`: the function maps the current installment's due date to its billing cycle's closing date, then calls the resolver with that closing date and the base rate.

## Due Date Derivation

Due dates are owned by the billing cycle, not the loan. `BaseBillingCycle` was enhanced with:

- Optional `due_dates: List[date]` constructor parameter — explicit override.
- `due_dates_between(start, end)` method — returns explicit dates (filtered by range) or derives from `closing_dates_between` + `due_date_for`.

The `BillingCycleLoan` constructor calls `billing_cycle.due_dates_between(...)` and truncates to `num_installments`.

## Forward Pass

There is a single unified `compute_state` in `loan/engines.py` with an optional `mora_rate_for_event: MoraRateCallback` parameter. `Loan` calls it without the callback (default mora rate). `BillingCycleLoan`'s `billing_cycle_loan/engines.py` builds a callback via `make_mora_callback` that resolves the per-cycle mora rate and delegates to the same unified function. No forward-pass logic is duplicated.

## Statements

`build_statements` produces one `BillingCycleLoanStatement` per billing period. Each statement shows:

- Schedule expectations (expected payment, principal, interest)
- The mora rate resolved for that cycle
- Mora and fines charged
- Payments received in the period (between closing dates)
- Opening and closing principal balance

Statements are a reporting view — they don't affect the financial computation.

## Payment Methods

- **`record_payment(amount, payment_date, interest_date=None)`** — full control, same as `Loan`.
- **`pay_installment(amount)`** — sugar method using `now()`. Interest accrual depends on timing (early/on-time/late), same semantics as `Loan.pay_installment`.

## Warp Integration

`BillingCycleLoan` has `_time_ctx` and `_on_warp`, so `Warp` works out of the box. Warping materialises fines at the target date.

## Key Design Decisions

- **No duplication of engine logic**: `loan/engines.py` has a single unified `compute_state` with a `MoraRateCallback` hook. BCL injects its per-cycle resolver via the callback; `Loan` omits it. All allocation, fine, and installment functions are shared.
- **Three-layer engine architecture**: `engines.py` (root) → `loan/engines.py` → `billing_cycle_loan/engines.py`. Root has standalone types (no `loan/` dependency, avoids circular imports). Loan engines have the full forward pass. BCL engines add product-specific wrappers.
- **Resolver is optional**: without it, behavior is identical to a `Loan` with billing-cycle-derived due dates. This invariant is property-tested under Hypothesis (`tests/test_schedule_equivalence.py`) across many randomly generated configurations.
- **Billing cycle owns all date logic**: the loan never receives explicit `due_dates` — it always derives them from the billing cycle. To customize due dates, pass them to the billing cycle constructor.
- **`InterestCalculator.compute_accrued_interest` gained `mora_rate_override`**: backward-compatible (optional param), allows per-call mora rate without duplicating the calculator.
- **Closing-date alignment with explicit due dates**: when the billing cycle has explicit due dates, `_derive_closing_dates()` selects the latest closing date on or before each due date rather than naively slicing the first N. This keeps `closing_dates[i]` aligned with `due_dates[i]` — a requirement for `resolve_mora_rate()` and `build_statements()` which map by index position.
