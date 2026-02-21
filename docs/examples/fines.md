# Fines, Mora Interest & Payment Methods

MoneyWarp models late payments realistically: overdue installments incur **fines** (a flat percentage of the missed amount) and **mora interest** (extra daily-compounded interest for the days beyond the due date). Payments are always allocated in strict priority: fines first, then interest, then principal.

## Payment Methods

MoneyWarp provides two sugar methods for recording payments, plus a low-level method for full control.

### `pay_installment()` — The Common Case

Records a payment at the current date (`self.now()`). Interest accrual depends on timing:

- **Early or on-time**: interest accrues up to the due date (no discount)
- **Late**: interest accrues up to `self.now()`, charging extra interest for the overdue days

```python
from datetime import datetime
from money_warp import Loan, Money, InterestRate, Warp, generate_monthly_dates

loan = Loan(
    Money("10000"),
    InterestRate("5% a"),
    generate_monthly_dates(datetime(2024, 2, 1), 12),
)

# Pay on time using the Time Machine
with Warp(loan, datetime(2024, 2, 1)) as warped:
    warped.pay_installment(Money("856.07"), "February payment")

# Pay late — mora interest is automatically charged
with Warp(loan, datetime(2024, 3, 15)) as warped:
    warped.pay_installment(Money("900.00"), "March payment (late)")
```

### `anticipate_payment()` — Early Payment with Discount

Records a payment at the current date, but calculates interest only up to `self.now()`. Fewer elapsed days means less interest charged — the borrower gets a discount.

```python
# Anticipate a payment before the due date — pay less interest
with Warp(loan, datetime(2024, 3, 20)) as warped:
    warped.anticipate_payment(Money("800.00"), "Early April payment")
```

### `record_payment()` — Explicit Date Control

Sets both `payment_date` and `interest_date` to the given date. Useful for batch processing and tests where you need explicit dates.

```python
loan.record_payment(Money("856.07"), datetime(2024, 2, 1), "February payment")
loan.record_payment(Money("856.07"), datetime(2024, 3, 1), "March payment")
```

## Fine Configuration

Configure fines and grace periods when creating a loan:

```python
from decimal import Decimal

# Default: 2% fine, no grace period
loan = Loan(
    Money("10000"),
    InterestRate("5% a"),
    generate_monthly_dates(datetime(2024, 2, 1), 12),
)

# Custom: 5% fine with a 7-day grace period
loan = Loan(
    Money("10000"),
    InterestRate("5% a"),
    generate_monthly_dates(datetime(2024, 2, 1), 12),
    fine_rate=Decimal("0.05"),
    grace_period_days=7,
)
```

| Parameter | Default | Meaning |
|---|---|---|
| `fine_rate` | `0.02` (2%) | Fine as a fraction of the expected installment amount |
| `grace_period_days` | `0` | Days after the due date before fines are applied |

## How Fines Work

### Checking for Late Payments

```python
from datetime import datetime
from money_warp import Loan, Money, InterestRate, generate_monthly_dates

loan = Loan(
    Money("10000"),
    InterestRate("5% a"),
    generate_monthly_dates(datetime(2024, 2, 1), 3),
)

# Is the February payment late as of February 15?
is_late = loan.is_payment_late(datetime(2024, 2, 1), as_of_date=datetime(2024, 2, 15))
print(f"Late? {is_late}")  # True — no payment was made
```

### Calculating and Applying Fines

`calculate_late_fines()` scans all due dates up to the given date and applies one fine per missed due date. Fines are never duplicated — each due date can only be fined once.

```python
# Apply fines as of March 15 (both Feb and March installments missed)
new_fines = loan.calculate_late_fines(as_of_date=datetime(2024, 3, 15))
print(f"New fines applied: {new_fines}")
print(f"Total fines: {loan.total_fines}")
print(f"Outstanding fines: {loan.outstanding_fines}")
```

### Fine Amounts Come from the Original Schedule

Fines are calculated as `fine_rate * expected_payment_amount`, where the expected payment comes from the **original** amortization schedule — not the rebuilt schedule. This ensures fine amounts are predictable and don't change as payments are recorded.

## Mora Interest

When a borrower pays late, they are charged extra interest for the days beyond the due date. The interest is automatically split into two separate cash flow items:

- **Regular interest** (`"actual_interest"`) — accrued from the last payment to the due date
- **Mora interest** (`"actual_mora_interest"`) — accrued from the due date to the payment date

On-time and early payments produce only a regular interest item (no mora).

```python
loan = Loan(
    Money("10000"),
    InterestRate("6% a"),
    [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)],
    disbursement_date=datetime(2024, 1, 1),
)

# Miss installment 1, pay 2 weeks late
# The borrower pays:
#   1. A fine (2% of the expected installment)
#   2. Regular interest for 31 days (disbursement to due date)
#   3. Mora interest for 14 days (due date to payment date)
#   4. The remaining amount reduces principal
with Warp(loan, datetime(2024, 2, 15)) as warped:
    warped.pay_installment(Money("3600.00"), "Late payment")
    print(f"Outstanding fines: {warped.outstanding_fines}")
    print(f"Remaining balance: {warped.current_balance}")
```

## Payment Allocation Priority

All payment methods allocate funds in the same strict order:

1. **Outstanding fines** — paid off first
2. **Accrued interest** — daily-compounded since last payment, up to the interest date
3. **Principal** — whatever remains reduces the loan balance

A large late payment naturally covers the missed installment **and** eats into future installments through this allocation pipeline. There is no special-casing — the allocation priority and principal balance tracking handle overpayments automatically.

## Grace Periods

A grace period delays when fines are applied. If `grace_period_days=7`, a payment due on February 1st is not considered late until February 8th.

```python
from decimal import Decimal

loan = Loan(
    Money("10000"),
    InterestRate("5% a"),
    [datetime(2024, 2, 1)],
    grace_period_days=7,
)

# Not late on February 5 (within grace period)
print(loan.is_payment_late(datetime(2024, 2, 1), datetime(2024, 2, 5)))  # False

# Late on February 9 (grace period expired)
print(loan.is_payment_late(datetime(2024, 2, 1), datetime(2024, 2, 9)))  # True
```

Note: the grace period only affects **fines**. Mora interest always accrues for every day past the due date, regardless of the grace period.

## Tracking Payments in Cash Flows

All cash flow items use explicit category prefixes. Expected schedule items use `expected_`, actual recorded payments use `actual_`:

```python
actual_cf = loan.get_actual_cash_flow()

# Query fine application events
fines = actual_cf.query.filter_by(category="fine_applied").all()
for fine in fines:
    print(f"{fine.datetime}: {fine.amount} — {fine.description}")

# Query mora interest payments
mora = actual_cf.query.filter_by(category="actual_mora_interest").all()
for item in mora:
    print(f"{item.datetime}: {item.amount} — {item.description}")
```

### Cash Flow Categories

| Category | Meaning |
|---|---|
| `"expected_disbursement"` | Loan disbursement (expected schedule) |
| `"expected_interest"` | Scheduled interest payment |
| `"expected_principal"` | Scheduled principal payment |
| `"actual_interest"` | Regular interest paid (up to due date) |
| `"actual_mora_interest"` | Mora interest paid (beyond due date) |
| `"actual_principal"` | Principal paid |
| `"actual_fine"` | Fine paid |
| `"fine_applied"` | Fine applied to loan |

## Key Properties

| Property | Type | Meaning |
|---|---|---|
| `total_fines` | `Money` | Sum of all fines ever applied |
| `outstanding_fines` | `Money` | Unpaid fines (total minus what's been paid off) |
| `fines_applied` | `Dict[datetime, Money]` | Fine amount applied per due date |
| `is_paid_off` | `bool` | True only when principal **and** fines are zero |
