---
name: describe-loan
description: Interactively describe and simulate a loan using the money-warp library. Collects principal, interest rate, and installment count from the user, optionally simulates payments, and produces a well-formatted markdown summary. Use when the user wants to describe a loan, see an amortization schedule, simulate loan payments, or understand a loan's behavior.
---

# Describe Loan

Walk the user through creating a loan, viewing its amortization schedule, simulating payments, and generating a markdown summary.

## Step 1: Collect Loan Parameters

Ask the user for three values **one at a time** (conversationally, not all at once). Always state the default so the user can just confirm.

1. **Principal** -- default `10,000`
   > "What is the loan principal? (default: 10,000)"

2. **Annual/Monthly Interest Rate** -- default `1% monthly`
   > "What is the interest rate? You can use formats like `1% m`, `12% a`, `0.5% a.m.` (default: 1% monthly)"

3. **Number of Installments** -- default `12`
   > "How many installments? (default: 12)"

If the user accepts the default, use it. If they provide a value, use theirs.

## Step 2: Create the Loan and Show the Schedule

Run a Python script via the shell to build the loan and print the amortization schedule.

### Imports

```python
from datetime import datetime, timedelta
from money_warp import (
    Money, InterestRate, Loan, PriceScheduler,
    generate_monthly_dates,
)
```

### Loan creation pattern

```python
disbursement = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
first_due = disbursement + timedelta(days=30)
due_dates = generate_monthly_dates(first_due, NUM_INSTALLMENTS)

loan = Loan(
    principal=Money(PRINCIPAL),
    interest_rate=InterestRate(RATE),
    due_dates=due_dates,
    disbursement_date=disbursement,
)
schedule = loan.get_original_schedule()
```

### Print the schedule

Iterate `schedule.entries` and print a markdown table:

```python
print("| # | Due Date | Payment | Principal | Interest | Balance |")
print("|---|----------|---------|-----------|----------|---------|")
for e in schedule.entries:
    print(
        f"| {e.payment_number} "
        f"| {e.due_date.strftime('%Y-%m-%d')} "
        f"| {e.payment_amount.real_amount:,.2f} "
        f"| {e.principal_payment.real_amount:,.2f} "
        f"| {e.interest_payment.real_amount:,.2f} "
        f"| {e.ending_balance.real_amount:,.2f} |"
    )
print()
print(f"Total payments: {schedule.total_payments.real_amount:,.2f}")
print(f"Total interest: {schedule.total_interest.real_amount:,.2f}")
print(f"Total principal: {schedule.total_principal.real_amount:,.2f}")
```

Present the table to the user as markdown.

## Step 3: Ask About Payments

After showing the schedule, ask:

> "Would you like to simulate any payments on this loan? (yes/no)"

If **no**, skip to Step 4.

If **yes**, collect each payment one at a time:

1. **Amount** -- e.g. `"500"`
2. **Payment date** -- e.g. `"2026-04-10"` or a relative description like "on the first due date"
3. **Type** -- ask:
   > "Is this a regular payment or an anticipation (early payoff with interest discount)?"
   - **Regular**: use `loan.record_payment(Money(amount), payment_date)`
   - **Anticipation**: use `loan.anticipate_payment(Money(amount))` (inside a `Warp` context at the payment date if needed)

After each payment, print:

```python
settlement = loan.record_payment(Money(AMOUNT), PAYMENT_DATE)
print(f"Payment: {settlement.payment_amount.real_amount:,.2f}")
print(f"  Interest paid: {settlement.interest_paid.real_amount:,.2f}")
print(f"  Mora paid:     {settlement.mora_paid.real_amount:,.2f}")
print(f"  Fine paid:     {settlement.fine_paid.real_amount:,.2f}")
print(f"  Principal paid:{settlement.principal_paid.real_amount:,.2f}")
print(f"  Remaining:     {settlement.remaining_balance.real_amount:,.2f}")
```

Then ask:

> "Would you like to add another payment? (yes/no)"

Repeat until the user says no or the loan is paid off.

## Step 4: Generate the Loan Summary

Produce a single markdown block with the full loan summary. Use the template below, filling in actual values from the script output.

### Summary Template

````markdown
# Loan Summary

## Loan Terms

| Parameter       | Value              |
|-----------------|--------------------|
| Principal       | {principal}        |
| Interest Rate   | {rate}             |
| Installments    | {num_installments} |
| Disbursement    | {disbursement}     |
| First Due Date  | {first_due}        |
| Last Due Date   | {last_due}         |
| Total Payments  | {total_payments}   |
| Total Interest  | {total_interest}   |

## Amortization Schedule

| # | Due Date | Payment | Principal | Interest | Balance |
|---|----------|---------|-----------|----------|---------|
| ... rows ... |

## Payments Made

> Only include this section if the user simulated payments.

| # | Date | Amount | Interest | Mora | Fine | Principal | Remaining |
|---|------|--------|----------|------|------|-----------|-----------|
| ... one row per settlement ... |

## Current State

| Metric              | Value                    |
|---------------------|--------------------------|
| Current Balance     | {current_balance}        |
| Paid Off            | {is_paid_off}            |
| Installments Paid   | {paid_count}/{total}     |
| Remaining Balance   | {remaining}              |

## Installment Detail

> Only include this section if the user simulated payments.

| # | Due Date | Expected | Paid | Balance | Status |
|---|----------|----------|------|---------|--------|
| ... one row per installment ... |
````

### Producing the summary

Run a single Python script that:

1. Recreates the loan with the same parameters (or reuses if in the same session)
2. Applies all payments in order
3. Reads `loan.get_original_schedule()` for the amortization table
4. Reads `loan.settlements` for payment history
5. Reads `loan.installments` for per-installment status
6. Reads `loan.current_balance` and `loan.is_paid_off`
7. Prints the full markdown summary following the template above

Present the markdown output directly to the user.

## Notes

- Always use `Money` for monetary amounts -- never raw numbers.
- Interest rates accept human-friendly strings: `"1% m"`, `"12% a"`, `"0.5% a.m."`, `"0.0137% d"`.
- `generate_monthly_dates(start, n)` creates `n` monthly due dates from `start`.
- `PriceScheduler` (French amortization, fixed payment) is the default scheduler. Do not specify it unless the user asks for a different one (e.g. `InvertedPriceScheduler` for SAC/constant amortization).
- All datetimes should be timezone-aware. The library handles this automatically via `ensure_aware`.
- Run Python scripts with `poetry run python -c "..."` or write a temp script and run with `poetry run python script.py`.
