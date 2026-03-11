---
name: validate-loan
description: Validate loan conditions by cross-checking money-warp calculations against independent Python math and assessing whether the loan terms are fair. Use when the user wants to validate a loan, check loan conditions, verify amortization math, or assess whether a loan is a good deal.
---

# Validate Loan Conditions

Cross-check money-warp's loan calculations using independent Python formulas and assess the fairness of the loan terms for the borrower.

## Step 0: Read Knowledge Files

Before writing any code, read these knowledge files to understand how money-warp works internally:

1. `knowledge/loan.md` -- loan model, schedulers, payment allocation, day-count details
2. `knowledge/rate.md` -- rate types, conversion logic, compounding
3. `knowledge/architecture.md` -- overall design, component relationships
4. `knowledge/tvm.md` -- present value, IRR, MIRR

Use the Read tool on each file. This context is essential for writing correct independent formulas that match the same financial conventions money-warp uses (daily compounding, actual days between dates, 365-day commercial year).

## Step 1: Collect Loan Parameters

**Switch to Plan mode** before collecting parameters. Plan mode provides a structured question interface (via `AskQuestion`) that is cleaner for the user than free-form chat.

Use `AskQuestion` to collect the three loan parameters. Ask them **one at a time** so the user can focus on each value.

**Question 1 -- Principal:**

```
AskQuestion:
  prompt: "What is the loan principal?"
  options:
    - "10,000 (default)"
    - "5,000"
    - "20,000"
    - "50,000"
    - "Other (I'll type a custom value)"
```

If the user picks "Other", follow up conversationally to get the exact amount.

**Question 2 -- Interest Rate:**

```
AskQuestion:
  prompt: "What is the interest rate?"
  options:
    - "1% monthly (default)"
    - "0.5% monthly"
    - "1.5% monthly"
    - "2% monthly"
    - "12% annual"
    - "Other (I'll type a custom value)"
```

If the user picks "Other", follow up to get the rate in any format (`1% m`, `12% a`, `0.5% a.m.`, etc.).

**Question 3 -- Number of Installments:**

```
AskQuestion:
  prompt: "How many installments?"
  options:
    - "6"
    - "12 (default)"
    - "24"
    - "36"
    - "48"
    - "Other (I'll type a custom value)"
```

After collecting all three parameters, **switch back to Agent mode** to proceed with the computation steps.

## Step 2: Compute with money-warp

Run a Python script via the shell that uses money-warp to compute the loan schedule and effective rate. Output structured JSON to stdout.

### Script pattern

```python
import json
from datetime import datetime, timedelta
from money_warp import Money, InterestRate, Loan, generate_monthly_dates

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

effective_rate = loan.irr()

entries = []
for e in schedule.entries:
    entries.append({
        "number": e.payment_number,
        "due_date": e.due_date.strftime("%Y-%m-%d"),
        "days_in_period": e.days_in_period,
        "payment": str(e.payment_amount.real_amount),
        "principal": str(e.principal_payment.real_amount),
        "interest": str(e.interest_payment.real_amount),
        "balance": str(e.ending_balance.real_amount),
    })

result = {
    "pmt": str(schedule.entries[0].payment_amount.real_amount),
    "total_payments": str(schedule.total_payments.real_amount),
    "total_interest": str(schedule.total_interest.real_amount),
    "total_principal": str(schedule.total_principal.real_amount),
    "effective_annual_rate": str(effective_rate.to_annual()._decimal_rate),
    "entries": entries,
}
print(json.dumps(result, indent=2))
```

Run with `poetry run python -c "..."` or write a temp file and run with `poetry run python /tmp/mw_check.py`. Capture the JSON output.

## Step 3: Independent Cross-Check (no money-warp)

Run a **separate** Python script that uses **only** `decimal.Decimal` and `datetime` (no money-warp imports) to independently compute the same values.

The formulas below match money-warp's PriceScheduler conventions (daily compounding, actual days between dates, 365-day commercial year). Refer to `knowledge/loan.md` for details.

### Script pattern

```python
import json
from decimal import Decimal, getcontext, ROUND_HALF_UP
from datetime import datetime, timedelta

getcontext().prec = 50

principal = Decimal("PRINCIPAL")
monthly_rate = Decimal("MONTHLY_RATE")  # e.g. 0.01 for 1%
num_installments = NUM_INSTALLMENTS

annual_rate = (1 + monthly_rate) ** 12 - 1
daily_rate = (1 + annual_rate) ** (Decimal(1) / Decimal(365)) - 1

disbursement = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
first_due = disbursement + timedelta(days=30)
due_dates = []
current = first_due
for i in range(num_installments):
    due_dates.append(current)
    if i < num_installments - 1:
        next_month = current.month % 12 + 1
        next_year = current.year + (1 if current.month == 12 else 0)
        current = current.replace(year=next_year, month=next_month)

# PMT = principal / sum(1 / (1 + daily_rate)^days_i)
discount_sum = Decimal(0)
for d in due_dates:
    days = (d - disbursement).days
    discount_sum += Decimal(1) / (1 + daily_rate) ** days

pmt = principal / discount_sum
pmt_rounded = pmt.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

# Amortization table
balance = principal
entries = []
prev_date = disbursement
for i, d in enumerate(due_dates):
    days = (d - prev_date).days
    interest = balance * ((1 + daily_rate) ** days - 1)
    interest_rounded = interest.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if i == len(due_dates) - 1:
        principal_pay = balance
        payment = balance + interest_rounded
    else:
        principal_pay = pmt_rounded - interest_rounded
        payment = pmt_rounded

    balance -= principal_pay
    entries.append({
        "number": i + 1,
        "due_date": d.strftime("%Y-%m-%d"),
        "days_in_period": days,
        "payment": str(payment.quantize(Decimal("0.01"))),
        "principal": str(principal_pay.quantize(Decimal("0.01"))),
        "interest": str(interest_rounded),
        "balance": str(balance.quantize(Decimal("0.01"))),
    })
    prev_date = d

total_payments = sum(Decimal(e["payment"]) for e in entries)
total_interest = sum(Decimal(e["interest"]) for e in entries)
total_principal = sum(Decimal(e["principal"]) for e in entries)

result = {
    "pmt": str(pmt_rounded),
    "total_payments": str(total_payments.quantize(Decimal("0.01"))),
    "total_interest": str(total_interest.quantize(Decimal("0.01"))),
    "total_principal": str(total_principal.quantize(Decimal("0.01"))),
    "entries": entries,
}
print(json.dumps(result, indent=2))
```

**Important**: the date generation logic must produce the same due dates as money-warp's `generate_monthly_dates`. Read the knowledge files to verify. If the user provides a non-monthly rate, convert it to daily using the same convention described in `knowledge/rate.md`.

## Step 4: Compare Results

Compare the two JSON outputs field by field. Use these tolerances:

| Metric | Tolerance |
|---|---|
| PMT | 0.01 (one cent) |
| Per-period interest | 0.01 |
| Per-period principal | 0.01 |
| Per-period ending balance | 0.01 |
| Total interest | 0.02 (two cents, rounding accumulation) |
| Total payments | 0.02 |

For each field, compute `abs(money_warp_value - independent_value)`. If within tolerance, mark **PASS**. Otherwise, mark **WARNING**.

Present a comparison table to the user:

```markdown
## Validation Results

| Metric | money-warp | Independent | Diff | Status |
|---|---|---|---|---|
| PMT | 888.49 | 888.49 | 0.00 | PASS |
| Total Interest | 661.85 | 661.85 | 0.00 | PASS |
| Total Payments | 10,661.85 | 10,661.85 | 0.00 | PASS |
| Inst. 1 Interest | 104.71 | 104.71 | 0.00 | PASS |
| Inst. 1 Balance | 9,216.22 | 9,216.22 | 0.00 | PASS |
| ... | ... | ... | ... | ... |
```

If all rows pass, state clearly: **"All calculations match -- money-warp output is verified."**

If any row shows WARNING, flag it and explain the discrepancy. Small rounding differences (1-2 cents) on totals are normal and should be noted as acceptable.

## Step 5: Collect Payments

**Switch to Plan mode** to collect payment information using `AskQuestion`.

First, ask whether the user wants to simulate payments:

```
AskQuestion:
  prompt: "Would you like to simulate payments on this loan?"
  options:
    - "Yes"
    - "No -- skip to fairness assessment"
```

If **no**, skip to Step 7.

If **yes**, collect each payment one at a time. For each payment, ask three questions:

**Question A -- Payment timing:**

```
AskQuestion:
  prompt: "When is this payment made relative to the next due date?"
  options:
    - "On the due date (on-time)"
    - "Before the due date (early)"
    - "After the due date (late -- X days, I'll specify)"
    - "Custom date (I'll specify)"
```

If the user picks a late or custom option, follow up to get the exact number of late days or the specific date.

**Question B -- Payment type:**

```
AskQuestion:
  prompt: "What type of payment is this?"
  options:
    - "Regular payment (pay_installment)"
    - "Anticipation -- early payoff with interest discount (anticipate_payment)"
```

**Question C -- Payment amount:**

```
AskQuestion:
  prompt: "How much is the payment?"
  options:
    - "Full installment amount ({PMT from schedule})"
    - "Double installment ({2x PMT})"
    - "Full remaining balance ({current balance})"
    - "Other (I'll type a custom amount)"
```

After collecting a payment, ask:

```
AskQuestion:
  prompt: "Would you like to add another payment?"
  options:
    - "Yes"
    - "No -- proceed to validation"
```

Repeat until the user says no or the loan is fully paid off. Then **switch back to Agent mode**.

## Step 6: Validate Payments

For each payment collected in Step 5, run two scripts and compare the results.

### money-warp script

Build the loan (same parameters as Step 2) and record each payment in sequence. For each payment, capture the `Settlement` as JSON:

```python
import json
from datetime import datetime, timedelta
from money_warp import Money, InterestRate, Loan, generate_monthly_dates

disbursement = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
first_due = disbursement + timedelta(days=30)
due_dates = generate_monthly_dates(first_due, NUM_INSTALLMENTS)

loan = Loan(
    principal=Money(PRINCIPAL),
    interest_rate=InterestRate(RATE),
    due_dates=due_dates,
    disbursement_date=disbursement,
)

payments = [
    # (amount, payment_date, type)
    # type: "regular" uses record_payment, "anticipation" uses anticipate_payment
]

results = []
for amount, payment_date, ptype in payments:
    if ptype == "regular":
        settlement = loan.record_payment(Money(amount), payment_date)
    else:
        settlement = loan.record_payment(Money(amount), payment_date,
                                          interest_date=payment_date)

    results.append({
        "payment_amount": str(settlement.payment_amount.real_amount),
        "interest_paid": str(settlement.interest_paid.real_amount),
        "mora_paid": str(settlement.mora_paid.real_amount),
        "fine_paid": str(settlement.fine_paid.real_amount),
        "principal_paid": str(settlement.principal_paid.real_amount),
        "remaining_balance": str(settlement.remaining_balance.real_amount),
    })

print(json.dumps(results, indent=2))
```

### Independent script (no money-warp)

Compute the expected settlement for each payment using only `decimal.Decimal` and `datetime`. The script must track cumulative state (running balance, which due dates are covered, fines already applied) across payments.

```python
import json
from decimal import Decimal, getcontext, ROUND_HALF_UP
from datetime import datetime, timedelta

getcontext().prec = 50

principal = Decimal("PRINCIPAL")
monthly_rate = Decimal("MONTHLY_RATE")
fine_rate = Decimal("0.02")  # default 2% (InterestRate.as_decimal)
num_installments = NUM_INSTALLMENTS

annual_rate = (1 + monthly_rate) ** 12 - 1
daily_rate = (1 + annual_rate) ** (Decimal(1) / Decimal(365)) - 1

# Build due dates and original schedule (same as Step 3)
# ... (reuse the date generation and PMT/schedule logic from Step 3)

balance = principal
last_payment_date = disbursement
fines_applied = set()
covered_installments = 0

# original_schedule = list of (due_date, expected_payment) from Step 3

payments = [
    # (amount, payment_date, type)
]

results = []
for amount, payment_date, ptype in payments:
    amount = Decimal(amount)
    fine_total = Decimal(0)
    interest_total = Decimal(0)
    mora_total = Decimal(0)

    # 1. Calculate fines for any overdue installments
    for i, (due_date, expected_pmt) in enumerate(original_schedule):
        if i < covered_installments:
            continue
        if due_date < payment_date and i not in fines_applied:
            fine = (fine_rate * expected_pmt).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP)
            fine_total += fine
            fines_applied.add(i)

    # 2. Calculate interest
    next_due = original_schedule[covered_installments][0]

    if ptype == "anticipation":
        # Anticipation: interest accrues only to payment_date
        days = (payment_date - last_payment_date).days
        interest_total = (balance * ((1 + daily_rate) ** days - 1)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
    elif payment_date <= next_due:
        # On-time or early: interest accrues to the due date
        interest_date = next_due
        days = (interest_date - last_payment_date).days
        interest_total = (balance * ((1 + daily_rate) ** days - 1)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        # Late: regular interest (to due date) + mora interest (due date to payment)
        regular_days = (next_due - last_payment_date).days
        mora_days = (payment_date - next_due).days
        regular_interest = balance * ((1 + daily_rate) ** regular_days - 1)

        # COMPOUND mora (default): mora base = balance + regular_interest
        mora_base = balance + regular_interest
        mora_total = (mora_base * ((1 + daily_rate) ** mora_days - 1)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)
        interest_total = regular_interest.quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP)

    # 3. Allocate: fine -> interest -> mora -> principal
    remaining = amount
    fine_paid = min(fine_total, remaining)
    remaining -= fine_paid
    interest_paid = min(interest_total, remaining)
    remaining -= interest_paid
    mora_paid = min(mora_total, remaining)
    remaining -= mora_paid
    principal_paid = remaining

    balance -= principal_paid
    last_payment_date = payment_date

    # Update covered installment count based on balance vs original schedule
    while (covered_installments < num_installments
           and balance <= Decimal(
               original_schedule[covered_installments][2])):
        # original_schedule[i][2] = ending_balance of installment i
        covered_installments += 1

    results.append({
        "payment_amount": str(amount.quantize(Decimal("0.01"))),
        "interest_paid": str(interest_paid),
        "mora_paid": str(mora_paid),
        "fine_paid": str(fine_paid),
        "principal_paid": str(principal_paid.quantize(Decimal("0.01"))),
        "remaining_balance": str(balance.quantize(Decimal("0.01"))),
    })

print(json.dumps(results, indent=2))
```

**Key conventions** (from `knowledge/loan.md`):
- Allocation order: fines first, then interest, then mora, then principal.
- Fine = `fine_rate.as_decimal * expected_payment` from the **original** schedule. One fine per missed due date, never duplicated.
- Mora strategy defaults to COMPOUND: mora rate is applied to `balance + regular_interest`.
- If `mora_interest_rate` is not specified, it defaults to `interest_rate`.
- Anticipation: `interest_date = payment_date` (discount for fewer days).
- Covered installment count is determined by comparing remaining balance against the original schedule's ending balances.

### Comparison

Use the same tolerance-based comparison as Step 4. Present one table per payment:

```markdown
### Payment 1 -- On-time, 888.49 on 2026-04-10

| Field | money-warp | Independent | Diff | Status |
|---|---|---|---|---|
| Interest Paid | 104.71 | 104.71 | 0.00 | PASS |
| Mora Paid | 0.00 | 0.00 | 0.00 | PASS |
| Fine Paid | 0.00 | 0.00 | 0.00 | PASS |
| Principal Paid | 783.78 | 783.78 | 0.00 | PASS |
| Remaining Balance | 9,216.22 | 9,216.22 | 0.00 | PASS |
```

If all fields pass: **"Payment 1 validated."**

If any field shows WARNING, flag it and investigate before proceeding.

## Step 7: Assess Loan Fairness

Using the computed data, evaluate the loan from the borrower's perspective.

### Metrics to compute

1. **Effective Annual Cost (CET)**: from `loan.irr()` in Step 2, expressed as an annual percentage. This is the true cost of the loan including compounding. If payments were simulated, use the actual cash flow IRR instead.

2. **Total Cost Ratio**: `total_interest / principal`. How much extra the borrower pays on top of what they borrowed.

3. **Payment Multiplier**: `total_payments / principal`. E.g. "you pay back 1.07x what you borrowed."

4. **Interest Share (first installment)**: `first_interest / PMT * 100`. What percentage of the first payment goes to interest.

5. **Interest Share (last installment)**: `last_interest / last_payment * 100`. What percentage of the last payment goes to interest.

### Plain-language assessment

Use this scale:

| Total Cost Ratio | Assessment |
|---|---|
| < 10% | Low cost -- favorable terms for the borrower |
| 10% -- 30% | Moderate cost -- typical for short/medium-term loans |
| 30% -- 50% | High cost -- borrower should compare alternatives |
| > 50% | Very high cost -- borrower pays significantly more than borrowed |

Present the assessment as a clear, concise paragraph. Include the key numbers and what they mean in practical terms.

### Example output

```markdown
## Fairness Assessment

| Metric | Value |
|---|---|
| Effective Annual Cost (CET) | 12.68% |
| Total Cost Ratio | 6.62% |
| Payment Multiplier | 1.07x |
| Interest Share (1st payment) | 11.79% |
| Interest Share (last payment) | 0.93% |

**Assessment**: This is a **low-cost** loan. The borrower pays 6.62% extra in interest
over the life of the loan (1.07x the principal). The effective annual cost of 12.68%
reflects monthly compounding of the 1% rate. Interest decreases steadily from 11.79% of
the first payment down to 0.93% of the last, showing healthy amortization.
```

## Step 8: Final Report

Combine everything into a single markdown report. Include the payment validation section only if the user simulated payments.

````markdown
# Loan Validation Report

## 1. Loan Terms

| Parameter | Value |
|---|---|
| Principal | {principal} |
| Interest Rate | {rate} |
| Installments | {num_installments} |
| Disbursement | {disbursement} |
| First Due Date | {first_due} |
| Last Due Date | {last_due} |

## 2. Schedule Validation

| Metric | money-warp | Independent | Diff | Status |
|---|---|---|---|---|
| ... rows from Step 4 ... |

**Verdict**: {All calculations match / Discrepancies found -- see warnings above}

## 3. Payment Validation

> Only include this section if the user simulated payments in Step 5.

### Payment 1 -- {type}, {amount} on {date}

| Field | money-warp | Independent | Diff | Status |
|---|---|---|---|---|
| Interest Paid | ... | ... | ... | ... |
| Mora Paid | ... | ... | ... | ... |
| Fine Paid | ... | ... | ... | ... |
| Principal Paid | ... | ... | ... | ... |
| Remaining Balance | ... | ... | ... | ... |

**Verdict**: {Payment 1 validated / Discrepancies found}

> Repeat for each payment.

## 4. Fairness Assessment

| Metric | Value |
|---|---|
| ... rows from Step 7 ... |

{Plain-language assessment paragraph}

## 5. Amortization Schedule

| # | Due Date | Payment | Principal | Interest | Balance |
|---|----------|---------|-----------|----------|---------|
| ... rows from money-warp (verified) ... |

| Total Payments | Total Interest | Total Principal |
|---|---|---|
| {total_payments} | {total_interest} | {total_principal} |
````

Present the full report directly to the user as markdown.

## Notes

- Always use `Money` for monetary amounts inside money-warp scripts -- never raw numbers.
- Interest rates accept human-friendly strings: `"1% m"`, `"12% a"`, `"0.5% a.m."`, `"0.0137% d"`.
- `generate_monthly_dates(start, n)` creates `n` monthly due dates from `start`.
- `PriceScheduler` (French amortization, fixed payment) is the default scheduler. Do not specify it unless the user asks for a different one.
- All datetimes should be timezone-aware. The library handles this automatically via `ensure_aware`.
- Run Python scripts with `poetry run python -c "..."` or write a temp script and run with `poetry run python /tmp/script.py`.
- The independent script must NOT import anything from money-warp. The whole point is to verify money-warp's output with a separate implementation.
- If validation finds a genuine discrepancy (not just rounding), investigate before presenting the report. Re-read the relevant knowledge file and check if the independent formula matches the convention described there.
