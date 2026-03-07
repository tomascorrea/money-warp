# Billing Cycle

The `billing_cycle` module provides a pluggable strategy for generating statement closing dates and payment due dates. It follows the same factory pattern as `BaseScheduler` on the Loan.

## Design

### BaseBillingCycle (ABC)

Two abstract methods:

- `closing_dates_between(start, end) -> List[datetime]` — all closing dates for complete cycles strictly after `start` up to `end`.
- `due_date_for(closing_date) -> datetime` — payment due date for a given closing date.

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

Inject into `CreditCard(billing_cycle=WeeklyBillingCycle(...))`.

## Key Decisions

- Closing day capped at 28 to avoid ambiguity for short months (Feb).
- `closing_dates_between` returns dates strictly after `start`. This means the opening date is never itself a closing date, which prevents zero-length first periods.
