# Tax & IOF (Brazilian Financial Operations Tax)

MoneyWarp includes a pluggable tax system built around the `BaseTax` interface. The first concrete implementation is **IOF** (Imposto sobre Operações Financeiras), the Brazilian tax levied on loan operations. The module also provides a **grossup** solver for financed taxes — where the tax is incorporated into the principal so the borrower receives an exact "requested amount."

## IOF Basics

IOF has two components applied to each installment's principal payment:

- **Daily rate**: applied per day from disbursement to payment date (capped at 365 days)
- **Additional rate**: a flat percentage applied once per installment

```python
from datetime import datetime
from decimal import Decimal
from money_warp import IOF, Money, InterestRate, PriceScheduler

# Create an IOF with explicit rates
iof = IOF(daily_rate=Decimal("0.000082"), additional_rate=Decimal("0.0038"))

# Rates can also be passed as percentage strings
iof = IOF(daily_rate="0.0082%", additional_rate="0.38%")

# Generate a schedule and calculate IOF
disbursement = datetime(2024, 1, 1)
due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]
schedule = PriceScheduler.generate_schedule(
    Money("10000"), InterestRate("2% m"), due_dates, disbursement
)

result = iof.calculate(schedule, disbursement)
print(f"Total IOF: {result.total}")
print(f"Installments: {len(result.per_installment)}")

# Inspect per-installment breakdown
for detail in result.per_installment:
    print(f"  Period {detail.payment_number}: "
          f"principal={detail.principal_payment}, "
          f"IOF={detail.tax_amount}")
```

## Preset Classes: IndividualIOF and CorporateIOF

Brazilian IOF rates differ by borrower type. MoneyWarp provides two preset subclasses with standard rates:

| Preset | Borrower Type | Daily Rate | Additional Rate |
|---|---|---|---|
| `IndividualIOF` | Pessoa Fisica (PF) | 0.0082% | 0.38% |
| `CorporateIOF` | Pessoa Juridica (PJ) | 0.0041% | 0.38% |

```python
from money_warp import IndividualIOF, CorporateIOF

# Zero-config — just use the standard rates
iof_pf = IndividualIOF()
iof_pj = CorporateIOF()

# Override any parameter if rates change
iof_custom = IndividualIOF(daily_rate=Decimal("0.0001"))
```

Both are subclasses of `IOF` and inherit all behavior. They work anywhere `IOF` or `BaseTax` is expected.

## Rounding Modes

Different systems round IOF components differently. MoneyWarp supports two strategies via `IOFRounding`:

- **`PRECISE`** (default): sums daily and additional components, then rounds the installment to 2 decimal places
- **`PER_COMPONENT`**: rounds each component to 2 decimal places individually before summing — matches common Brazilian lending platforms

Both modes produce proper 2-decimal money values for every installment.

```python
from money_warp import IOF, IOFRounding

# Default: precise rounding
iof_precise = IOF(daily_rate="0.0082%", additional_rate="0.38%")

# Match external system rounding
iof_external = IOF(
    daily_rate="0.0082%",
    additional_rate="0.38%",
    rounding=IOFRounding.PER_COMPONENT,
)

# Also works with presets
iof_pf = IndividualIOF(rounding=IOFRounding.PER_COMPONENT)
```

The difference between modes is at most 1 cent per installment. Use `PER_COMPONENT` when you need exact reconciliation with an external system.

## Loan with Tax

Attach taxes to a `Loan` for reporting. The loan lazily computes and caches tax amounts from the original schedule:

```python
from money_warp import Loan, Money, InterestRate, IndividualIOF, generate_monthly_dates

iof = IndividualIOF()
due_dates = generate_monthly_dates(datetime(2024, 2, 1), 12)

loan = Loan(
    Money("10000"),
    InterestRate("1% m"),
    due_dates,
    disbursement_date=datetime(2024, 1, 1),
    taxes=[iof],
)

# Tax reporting properties
print(f"Total IOF: {loan.total_tax}")
print(f"Net disbursement: {loan.net_disbursement}")  # principal - total_tax

# Per-tax breakdown (keyed by class name)
for name, result in loan.tax_amounts.items():
    print(f"{name}: {result.total}")
```

When taxes are present, `generate_expected_cash_flow()` includes an `"expected_tax"` item at the disbursement date, so IRR and present value calculations automatically account for the tax.

## Grossup: Financed Tax

When the tax is financed (incorporated into the principal), the borrower receives at least the "requested amount" after tax deduction. The `grossup()` function uses `scipy.optimize.brentq` (bracketed bisection) to find the principal where `principal - tax(principal) >= requested_amount`, then snaps the result to a clean cent-aligned principal. In most cases the net equals the requested amount exactly; in rare rounding-boundary cases the borrower receives up to 1 cent more (never less).

```python
from money_warp import grossup, Money, InterestRate, PriceScheduler, IndividualIOF

iof = IndividualIOF()
due_dates = generate_monthly_dates(datetime(2024, 2, 1), 12)

result = grossup(
    requested_amount=Money("10000"),
    interest_rate=InterestRate("1% m"),
    due_dates=due_dates,
    disbursement_date=datetime(2024, 1, 1),
    scheduler=PriceScheduler,
    taxes=[iof],
)

print(f"Grossed-up principal: {result.principal}")     # > 10,000
print(f"Requested amount: {result.requested_amount}")  # 10,000
print(f"Total tax: {result.total_tax}")

# Create a Loan from the result
loan = result.to_loan()
print(f"Net disbursement: {loan.net_disbursement}")  # ~= 10,000
```

### `grossup_loan()` — The Common Case

Most of the time you want the grossed-up `Loan` directly. The `grossup_loan()` function does `grossup(...).to_loan(...)` in a single call:

```python
from money_warp import grossup_loan, Money, InterestRate, PriceScheduler, IndividualIOF
from decimal import Decimal

iof = IndividualIOF()
due_dates = generate_monthly_dates(datetime(2024, 2, 1), 12)

loan = grossup_loan(
    requested_amount=Money("10000"),
    interest_rate=InterestRate("1% m"),
    due_dates=due_dates,
    disbursement_date=datetime(2024, 1, 1),
    scheduler=PriceScheduler,
    taxes=[iof],
    fine_rate=Decimal("0.05"),   # forwarded to Loan
    grace_period_days=3,         # forwarded to Loan
)

print(f"Principal: {loan.principal}")              # > 10,000
print(f"Net to borrower: {loan.net_disbursement}") # ~= 10,000
print(f"Total IOF: {loan.total_tax}")
```

## Custom Taxes

To add support for a different tax, subclass `BaseTax` and implement `calculate()`:

```python
from money_warp.tax.base import BaseTax, TaxResult, TaxInstallmentDetail

class MyTax(BaseTax):
    def calculate(self, schedule, disbursement_date):
        details = []
        total = Money.zero()
        for entry in schedule:
            tax_amount = entry.principal_payment * Decimal("0.01")  # 1% flat
            details.append(TaxInstallmentDetail(
                payment_number=entry.payment_number,
                due_date=entry.due_date,
                principal_payment=entry.principal_payment,
                tax_amount=tax_amount,
            ))
            total = total + tax_amount
        return TaxResult(total=total, per_installment=details)
```

Custom taxes work with `Loan(taxes=[...])`, `grossup()`, and `grossup_loan()` — the entire system is polymorphic over `BaseTax`.

## Key Properties

| Property / Function | Type | Description |
|---|---|---|
| `loan.total_tax` | `Money` | Sum of all taxes on the loan |
| `loan.net_disbursement` | `Money` | `principal - total_tax` |
| `loan.tax_amounts` | `Dict[str, TaxResult]` | Per-tax results keyed by class name |
| `grossup()` | `GrossupResult` | Finds the grossed-up principal |
| `grossup_loan()` | `Loan` | Sugar: grossup + create loan in one call |
| `IOFRounding.PRECISE` | enum | Sum-then-round (default) |
| `IOFRounding.PER_COMPONENT` | enum | Round-then-sum (matches external systems) |

## Cash Flow Categories

When taxes are attached to a loan, the expected cash flow includes:

| Category | Meaning |
|---|---|
| `"expected_tax"` | Tax deducted at disbursement (negative from borrower's perspective) |
