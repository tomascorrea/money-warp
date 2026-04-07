# Billing Cycle Loan

The `BillingCycleLoan` models a personal loan where principal is amortized on a fixed schedule (Price / SAC) but payment timing is driven by credit-card-like billing cycles. Unlike the standard `Loan`, the mora interest rate can change per billing cycle via a user-supplied callable.

## Architecture

`BillingCycleLoan` follows the same CashFlow-emergence philosophy as `Loan`: a single `CashFlow` is the source of truth, and all financial state (settlements, installments, balances, fines, statements) is derived on demand by a forward pass.

### Components

- **`BillingCycleLoan`** (facade) — wires billing cycle, scheduler, interest calculator, and mora rate resolver. Provides payment methods and property views.
- **`BaseBillingCycle`** — existing factory that generates closing dates and due dates. Enhanced with optional explicit `due_dates` and a `due_dates_between()` method.
- **`MoraRateResolver`** (protocol) — callable `(date, InterestRate) -> InterestRate` that adjusts the mora rate per cycle. The first argument is the cycle's closing date; the second is the base mora rate.
- **`InterestCalculator`** — reused from `loan/engines.py`, enhanced with `mora_rate_override` parameter.
- **`billing_cycle_loan/engines.py`** — adapted forward pass that resolves mora rate per cycle and delegates allocation/distribution/fines to `loan/engines.py`.
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

`billing_cycle_loan.engines.compute_state` is an adapted version of `loan.engines.compute_state`. The only structural difference: at each payment event, it resolves the mora rate for the current billing cycle and passes it as `mora_rate_override` to `InterestCalculator.compute_accrued_interest`.

All other engine functions are reused directly from `loan/engines.py`: `allocate_payment`, `distribute_into_installments`, `compute_fines_at`, `covered_due_date_count`, `_build_event_timeline`, `_build_installments_snapshot`, `_skipped_contractual_interest`.

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

- **No duplication of engine logic**: the adapted forward pass reuses 90%+ of `loan/engines.py` functions. Only mora rate resolution is new.
- **Resolver is optional**: without it, behavior is identical to a `Loan` with billing-cycle-derived due dates.
- **Billing cycle owns all date logic**: the loan never receives explicit `due_dates` — it always derives them from the billing cycle. To customize due dates, pass them to the billing cycle constructor.
- **`InterestCalculator.compute_accrued_interest` gained `mora_rate_override`**: backward-compatible (optional param), allows per-call mora rate without duplicating the calculator.
