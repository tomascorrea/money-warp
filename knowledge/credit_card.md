# Credit Card

The `CreditCard` class models a revolving credit instrument with periodic billing statements. It follows the same "emerges from the cash flow" philosophy as the Loan: transactions are recorded as `CashFlowItem` objects, and statements, interest charges, and fines are all derived from that cash flow.

## Constructor Parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `interest_rate` | `InterestRate` | required | Annual rate for unpaid balances |
| `billing_cycle` | `BaseBillingCycle` | `MonthlyBillingCycle()` | Pluggable cycle strategy |
| `minimum_payment_rate` | `Decimal` | `0.15` (15%) | Fraction of closing balance |
| `minimum_payment_floor` | `Money` | `$25.00` | Absolute floor |
| `fine_rate` | `Decimal` | `0.02` (2%) | Fine as fraction of minimum payment |
| `opening_date` | `Optional[datetime]` | `now()` | When the card was opened |
| `credit_limit` | `Optional[Money]` | `None` | Max balance; None = unlimited |

## Internal State

Minimal, like the Loan:

- `_time_ctx: TimeContext` — shared, Warp-compatible
- `_all_items: List[CashFlowItem]` — all transactions + materialised charges
- `_cycles_closed: int` — idempotency counter for billing-cycle processing

## Transaction Methods

- `purchase(amount, date?, description?)` — records a `CashFlowItem` with category `"purchase"`
- `pay(amount, date?, description?)` — records category `"payment"`
- `refund(amount, date?, description?)` — records category `"refund"`

All validate positive amounts. `purchase` also checks `credit_limit` if set. `date` defaults to `self.now()` (Warp-aware).

## CashFlowItem Categories

| Category | Effect on Balance | Origin |
|---|---|---|
| `purchase` | +amount | User transaction |
| `payment` | -amount | User transaction |
| `refund` | -amount | User transaction |
| `interest_charge` | +amount | Materialised at cycle close |
| `fine_charge` | +amount | Materialised at cycle close |

## Billing-Cycle Processing

`_close_billing_cycles(as_of_date)` processes all completed cycles up to `as_of_date`. For each unprocessed cycle:

1. Compute the **carried balance**: `max(0, previous_closing_balance - payments_in_period - refunds_in_period)`.
2. If carried balance is positive, compute interest via `interest_rate.accrue(carried, days)` and materialise as a `CashFlowItem` with category `"interest_charge"`.
3. For cycles after the first: check if the previous cycle's minimum payment was met (payments between previous close and previous due date). If not, materialise a fine = `fine_rate * minimum_payment`.

Tracked by `_cycles_closed` counter to guarantee idempotency.

Called automatically by:
- `purchase()`, `pay()`, `refund()` — before recording the transaction
- `current_balance` property
- `statements` property
- `_on_warp()` — called by Warp after overriding TimeContext

## Statement (Derived View)

`Statement` is a frozen dataclass built on demand from the cash flow. Analogous to `Installment` on the Loan.

Fields: `period_number`, `opening_date`, `closing_date`, `due_date`, `previous_balance`, `purchases_total`, `payments_total`, `refunds_total`, `interest_charged`, `fine_charged`, `closing_balance`, `minimum_payment`.

`closing_balance = previous_balance + purchases - payments - refunds + interest + fine`

`minimum_payment = min(closing_balance, max(floor, rate * closing_balance))`

`is_minimum_met` property: `payments_total >= minimum_payment`.

## Minimum Payment

`min(closing_balance, max(minimum_payment_floor, minimum_payment_rate * closing_balance))`

This means:
- If balance < floor: minimum = balance (pay it all)
- If rate * balance < floor: minimum = floor
- Otherwise: minimum = rate * balance

## Interest Calculation

At each statement close, interest accrues on the carried balance (previous balance minus payments/refunds during the period). Uses `InterestRate.accrue()` which daily-compounds, consistent with the Loan.

## Warp Integration

`CreditCard` exposes `_time_ctx` and `_on_warp(target_date)` so Warp works via duck typing. The `_on_warp` hook calls `_close_billing_cycles(target_date)`, materialising interest and fines up to the warped date. The clone is discarded on exit, so the original card is never modified.

## Key Decisions

- **Cash flow as source of truth**: transactions are `CashFlowItem`s; statements are computed views.
- **Lazy materialisation**: interest and fines are only materialised when a billing cycle is observed or a transaction is recorded. The `_cycles_closed` counter prevents duplication.
- **No grace period**: interest accrues on any carried balance regardless of payment timing within the cycle. This keeps the model simple; grace period logic can be added as a future enhancement.
- **Credit limit is optional**: `None` means unlimited. When set, `purchase()` validates against `credit_limit - current_balance`.
