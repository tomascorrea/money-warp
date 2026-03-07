# Billing Cycle

The `billing_cycle` module provides a pluggable strategy for generating statement closing dates, payment due dates, and building statements from a cash flow. It follows the same factory pattern as `BaseScheduler` on the Loan.

## Design

### BaseBillingCycle (ABC)

Two abstract methods define the date logic:

- `closing_dates_between(start, end) -> List[datetime]` — all closing dates for complete cycles strictly after `start` up to `end`.
- `due_date_for(closing_date) -> datetime` — payment due date for a given closing date.

Two concrete methods use those dates:

- `build_statements(cash_flow, opening_date, end_date, minimum_payment_rate, minimum_payment_floor) -> List[Statement]` — slices the cash flow by period and produces a `Statement` for each closed cycle. Balance is carried forward iteratively. Works for any billing cycle implementation because it relies on the abstract date methods.
- `compute_minimum_payment(closing_balance, rate, floor) -> Money` — static method. `min(closing_balance, max(floor, rate * closing_balance))`.

### Statement

Frozen dataclass living in `billing_cycle/statement.py`. Re-exported by `credit_card` for backward compatibility.

Fields: `period_number`, `opening_date`, `closing_date`, `due_date`, `previous_balance`, `purchases_total`, `payments_total`, `refunds_total`, `interest_charged`, `fine_charged`, `closing_balance`, `minimum_payment`.

`is_minimum_met` property: `payments_total >= minimum_payment`.

### MonthlyBillingCycle

First (and default) implementation. Generates one closing date per month on a fixed calendar day.

Constructor parameters:

| Parameter | Type | Default | Notes |
|---|---|---|---|
| `closing_day` | `int` | `1` | Day of month (1-28). Restricted to 28 to avoid month-length edge cases. |
| `payment_due_days` | `int` | `15` | Days after closing for the payment due date. |

Closing dates have time `23:59:59` to ensure that transactions recorded on the closing day itself are included in the period.

Uses `dateutil.relativedelta` for month arithmetic (already a project dependency).

## Extending

To create a new billing cycle (e.g. weekly, bi-weekly):

```python
class WeeklyBillingCycle(BaseBillingCycle):
    def closing_dates_between(self, start, end):
        # return weekly closing dates
        ...

    def due_date_for(self, closing_date):
        return closing_date + timedelta(days=7)
```

Inject into `CreditCard(billing_cycle=WeeklyBillingCycle(...))`. `build_statements` and `compute_minimum_payment` are inherited — no need to re-implement them.

## Key Decisions

- Closing day capped at 28 to avoid ambiguity for short months (Feb).
- `closing_dates_between` returns dates strictly after `start`. This means the opening date is never itself a closing date, which prevents zero-length first periods.
- Statement building is a concrete method on the base class, not abstract. Every billing cycle implementation gets it for free — only the date generation needs to be customized.
- `compute_minimum_payment` is a static method so both the billing cycle (in `build_statements`) and the credit card (in `_maybe_apply_fine`) can call it without duplication.
