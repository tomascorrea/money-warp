# Credit Card

The `CreditCard` class models a revolving credit instrument with periodic billing statements. It follows the same "emerges from the cash flow" philosophy as the Loan: transactions are recorded as `CashFlowItem` objects, and statements, interest charges, and fines are all derived from that cash flow.

## Constructor Parameters

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `interest_rate` | `InterestRate` | required | Annual rate for unpaid balances |
| `billing_cycle` | `BaseBillingCycle` | `MonthlyBillingCycle()` | Pluggable cycle strategy |
| `minimum_payment_rate` | `Decimal` | `0.15` (15%) | Fraction of closing balance |
| `minimum_payment_floor` | `Money` | `$25.00` | Absolute floor |
| `fine_rate` | `InterestRate` | `InterestRate("2% annual")` | Fine rate applied to minimum payment |
| `opening_date` | `Optional[datetime]` | `now()` | When the card was opened |
| `credit_limit` | `Optional[Money]` | `None` | Max balance; None = unlimited |

## Internal State

Minimal:

- `_time_ctx: TimeContext` — shared, Warp-compatible
- `cash_flow: CashFlow` — public; all transactions + materialised charges
- `_cycles_closed: int` — idempotency counter for billing-cycle processing
- `_last_closing_balance: Money` — iteratively tracked closing balance of the last processed cycle

## No `as_of` Parameters

No method on CreditCard accepts an `as_of` date parameter. Time filtering is handled by the CashFlow's `resolve()` mechanism:

- `CashFlowItem` objects are created with `effective_date=date`, so they only resolve (become visible) when `now() >= date`.
- When Warp overrides `TimeContext`, items from the "future" don't resolve and are invisible to queries.
- `_raw_balance()` simply sums resolved debits minus credits — no date filter needed.

Date-range queries in `_sum_category_between` are data slicing (category sums within billing periods), not time travel.

## Transaction Methods

- `purchase(amount, date?, description?)` — records a `CashFlowItem` with category `"purchase"`
- `pay(amount, date?, description?)` — records category `"payment"`
- `refund(amount, date?, description?)` — records category `"refund"`

All validate positive amounts. `purchase` also checks `credit_limit` if set. `date` defaults to `self.now()` (Warp-aware). Transaction methods do NOT close billing cycles — cycle closing is lazy, triggered only by derived properties.

## get_cash_flow()

`get_cash_flow() -> List[CashFlowEntry]` returns a signed cash-flow view of all resolved transactions. Triggers `_close_billing_cycles()` first to materialise interest and fines, then iterates resolved entries:

- Debits (purchase, interest_charge, fine_charge) — returned with original positive amount
- Credits (payment, refund) — returned with negated (negative) amount

Items are sorted by datetime. Uses `dataclasses.replace()` to create copies of frozen `CashFlowEntry` objects with flipped signs — does not mutate the underlying cash flow.

## CashFlowItem Categories

| Category | Effect on Balance | Origin |
|---|---|---|
| `purchase` | +amount | User transaction |
| `payment` | -amount | User transaction |
| `refund` | -amount | User transaction |
| `interest_charge` | +amount | Materialised at cycle close |
| `fine_charge` | +amount | Materialised at cycle close |

## Billing-Cycle Processing

`_close_billing_cycles()` (no parameters — uses `self.now()`) processes all completed cycles. Balance is tracked iteratively via `_last_closing_balance`. For each unprocessed cycle:

1. Compute the **carried balance**: `max(0, previous_closing_balance - payments_in_period - refunds_in_period)`.
2. If carried balance is positive, compute interest via `interest_rate.accrue(carried, days)` and materialise as a `CashFlowItem` with category `"interest_charge"`.
3. For cycles after the first: check if the previous cycle's minimum payment was met (payments between previous close and previous due date). If not, materialise a fine = `fine_rate.as_decimal() * minimum_payment.raw_amount` (wrapped in `Money`).
4. Update `_last_closing_balance` with the new closing balance.

Tracked by `_cycles_closed` counter to guarantee idempotency.

Called automatically by:
- `current_balance` property
- `statements` property
- `_on_warp()` — called by Warp after overriding TimeContext

## Statement (Derived View)

`Statement` lives in the `billing_cycle` package (re-exported by `credit_card` for convenience). The billing cycle builds statements via `build_statements()`, which the credit card delegates to.

Fields: `period_number`, `opening_date`, `closing_date`, `due_date`, `previous_balance`, `purchases_total`, `payments_total`, `refunds_total`, `interest_charged`, `fine_charged`, `closing_balance`, `minimum_payment`.

`closing_balance = previous_balance + purchases - payments - refunds + interest + fine`

`minimum_payment = min(closing_balance, max(floor, rate * closing_balance))`

`is_minimum_met` property: `payments_total >= minimum_payment`.

## Interest Calculation

At each statement close, interest accrues on the carried balance (previous balance minus payments/refunds during the period). Uses `InterestRate.accrue()` which daily-compounds, consistent with the Loan.

## Warp Integration

`CreditCard` exposes `_time_ctx` and `_on_warp(target_date)` so Warp works via duck typing. The `_on_warp` hook calls `_close_billing_cycles()`, materialising interest and fines up to the warped date. The clone is discarded on exit, so the original card is never modified.

## Key Decisions

- **Cash flow as source of truth**: transactions are `CashFlowItem`s with `effective_date`; statements are computed views.
- **`effective_date` on CashFlowItem**: items use `effective_date=transaction_date` so `resolve()` returns `None` when `now() < effective_date`. This is how the CashFlow "does the time filter" — no explicit `datetime__lte` filtering needed.
- **Lazy materialisation**: interest and fines are only materialised when a derived property is accessed or Warp triggers `_on_warp`. The `_cycles_closed` counter prevents duplication.
- **Iterative balance tracking**: `_last_closing_balance` carries forward across cycles, eliminating the need for "balance at date X" queries.
- **Statement building delegated to billing cycle**: `CreditCard.statements` calls `self.billing_cycle.build_statements(...)`. The billing cycle owns the logic of slicing a cash flow into period summaries.
- **No grace period**: interest accrues on any carried balance regardless of payment timing within the cycle. This keeps the model simple; grace period logic can be added as a future enhancement.
- **Credit limit is optional**: `None` means unlimited. When set, `purchase()` validates against `credit_limit - raw_balance`.
