# Tax Module

The tax module provides a strategy pattern for computing taxes on loans, with IOF (Imposto sobre Operacoes Financeiras) as the first concrete implementation, and a standalone grossup function for financed taxes.

## Package Structure

```
money_warp/tax/
├── __init__.py    # Public exports
├── base.py        # BaseTax ABC, TaxResult, TaxInstallmentDetail
├── iof.py         # IOF implementation
└── grossup.py     # grossup() function, GrossupResult
```

## Design Decisions

### Strategy Pattern (like Schedulers)

Taxes follow the same pattern as schedulers: an abstract base class (`BaseTax`) with a single `calculate` method. Each tax receives a `PaymentSchedule` and `disbursement_date`, and returns a `TaxResult` with a total and per-installment breakdown. This makes taxes pluggable without modifying the Loan class.

### Taxes Are Schedule-Dependent

IOF (and similar taxes) depend on the amortization schedule -- the daily IOF rate applies to each installment's principal payment based on the number of days from disbursement to that payment's due date. This is why `calculate()` takes the full `PaymentSchedule` rather than just the principal amount.

### Grossup as a Standalone Function with `to_loan()` Convenience

The grossup function lives outside the Loan class. It takes a `requested_amount` (what the borrower wants to receive) and uses `scipy.optimize.fsolve` to find the grossed-up principal such that `principal - tax = requested_amount`.

The returned `GrossupResult` carries all the parameters needed to construct a Loan, exposed via a `to_loan(**loan_kwargs)` convenience method. This is the most common usage pattern:

```python
result = grossup(requested_amount=Money("10000"), ...)
loan = result.to_loan()                          # default loan settings
loan = result.to_loan(fine_rate=Decimal("0.05"))  # with custom settings
```

This keeps each piece focused on one job:

- `grossup()` -- numerical solver, computes the adjusted principal
- `GrossupResult.to_loan()` -- convenience factory for the common case
- `Loan` -- takes the actual principal, optionally stores taxes for reporting

### Loan Knows About Taxes for Reporting

The Loan class accepts an optional `taxes: List[BaseTax]` parameter. When present:

- `loan.tax_amounts` returns per-tax `TaxResult` objects (lazily computed, cached)
- `loan.total_tax` returns the sum of all taxes
- `loan.net_disbursement` returns `principal - total_tax`
- `generate_expected_cash_flow()` includes an `"expected_tax"` cash flow item at disbursement and shows the disbursement as the net amount

This is important for CET (Custo Efetivo Total) calculation, which requires tax in the cash flow.

## API Surface

### BaseTax

```python
class BaseTax(ABC):
    def calculate(self, schedule: PaymentSchedule, disbursement_date: datetime) -> TaxResult
```

### TaxResult / TaxInstallmentDetail

```python
@dataclass
class TaxResult:
    total: Money
    per_installment: List[TaxInstallmentDetail]

@dataclass
class TaxInstallmentDetail:
    payment_number: int
    due_date: datetime
    principal_payment: Money
    tax_amount: Money
```

### IOF

```python
class IOF(BaseTax):
    def __init__(self, daily_rate, additional_rate, max_daily_days=365)
```

- `daily_rate`: daily IOF rate (e.g. `"0.0082%"` or `Decimal("0.000082")`)
- `additional_rate`: flat additional IOF rate (e.g. `"0.38%"` or `Decimal("0.0038")`)
- `max_daily_days`: cap on days for daily rate calculation (default 365)

Accepts strings with optional `%` suffix, or `Decimal` values.

### grossup()

```python
def grossup(
    requested_amount: Money,
    interest_rate: InterestRate,
    due_dates: List[datetime],
    disbursement_date: datetime,
    scheduler: Type[BaseScheduler],
    taxes: List[BaseTax],
) -> GrossupResult
```

Returns a `GrossupResult` with `principal`, `requested_amount`, `total_tax`, and `to_loan()`.

### GrossupResult.to_loan()

```python
result.to_loan(**loan_kwargs) -> Loan
```

Creates a Loan with the grossed-up principal and all schedule parameters forwarded automatically. Pass additional Loan keyword arguments (fine_rate, grace_period_days, mora_interest_rate, mora_strategy) as needed.

### grossup_loan()

```python
def grossup_loan(
    requested_amount: Money,
    interest_rate: InterestRate,
    due_dates: List[datetime],
    disbursement_date: datetime,
    scheduler: Type[BaseScheduler],
    taxes: List[BaseTax],
    **loan_kwargs,
) -> Loan
```

Sugar for `grossup(...).to_loan(**loan_kwargs)` in a single call. This is the most common entry point -- compute the grossed-up principal and get a ready-to-use Loan:

```python
loan = grossup_loan(
    requested_amount=Money("10000"),
    interest_rate=InterestRate("2% monthly"),
    due_dates=dates,
    disbursement_date=disbursement,
    scheduler=PriceScheduler,
    taxes=[iof],
    fine_rate=Decimal("0.05"),
)
```

## Key Learnings / Gotchas

- IOF calculation uses `raw_amount` for high-precision arithmetic, wrapping results back into `Money` at each step to maintain the dual-precision semantics.
- The grossup uses `scipy.optimize.fsolve` to solve `f(p) = p - requested_amount - tax(p) = 0`. The objective function converts between float (scipy domain) and `Money`/`Decimal` (our domain) at the boundary. The numpy array from fsolve is accessed via `.flat[0]` to extract the scalar.
- The tax cache on `Loan` (`_tax_cache`) is set to `None` initially and computed on first access to `tax_amounts`. Since the original schedule is immutable (depends only on `principal`, `interest_rate`, `due_dates`, `disbursement_date`, and `scheduler`), the cache never needs invalidation.
- When taxes are present, `generate_expected_cash_flow()` records the disbursement as the net amount (not the full principal) and adds a separate negative `"expected_tax"` item. This means the CET IRR calculation automatically accounts for the tax.
- `GrossupResult.to_loan()` uses a lazy import of `Loan` to break the circular dependency `tax.grossup -> loan.loan -> tax.base`. This matches the existing pattern in `loan.py` for `present_value` and `irr`.
