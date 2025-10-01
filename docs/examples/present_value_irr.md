# Present Value and IRR Analysis

MoneyWarp provides comprehensive Time Value of Money (TVM) functions powered by scipy for robust numerical calculations.

> **💡 Design Philosophy**: MoneyWarp focuses on Present Value calculations because with our Time Machine, you can simply "voyage dans le temps" to any future date and observe values directly. Future Value functions are unnecessary when you can warp to the future! 🕰️

## Present Value Functions

### Basic Present Value

Calculate the present value of any cash flow stream:

```python
from money_warp import CashFlow, CashFlowItem, Money, InterestRate, present_value
from datetime import datetime

# Create a cash flow
items = [
    CashFlowItem(Money("-1000"), datetime(2024, 1, 1), "Investment", "investment"),
    CashFlowItem(Money("300"), datetime(2024, 6, 1), "Return 1", "return"),
    CashFlowItem(Money("400"), datetime(2024, 12, 1), "Return 2", "return"),
    CashFlowItem(Money("500"), datetime(2025, 6, 1), "Return 3", "return"),
]
cash_flow = CashFlow(items)

# Calculate present value at 8% annual discount rate
discount_rate = InterestRate("8% annual")
pv = present_value(cash_flow, discount_rate)
print(f"Present Value: {pv}")
```


### Present Value of Annuities

Calculate PV of regular payment streams:

```python
from money_warp import present_value_of_annuity

# PV of $1000 monthly payments for 12 months at 5% annual
monthly_rate = InterestRate("5% annual").to_monthly()
pv_annuity = present_value_of_annuity(
    payment_amount=Money("1000"),
    interest_rate=monthly_rate,
    periods=12
)
print(f"PV of Annuity: {pv_annuity}")

# Annuity due (payments at beginning of period)
pv_due = present_value_of_annuity(
    payment_amount=Money("1000"),
    interest_rate=monthly_rate,
    periods=12,
    payment_timing="begin"
)
print(f"PV of Annuity Due: {pv_due}")
```

### Present Value of Perpetuities

Calculate PV of infinite payment streams:

```python
from money_warp import present_value_of_perpetuity

# PV of $100 annual payments forever at 5%
pv_perpetuity = present_value_of_perpetuity(
    payment_amount=Money("100"),
    interest_rate=InterestRate("5% annual")
)
print(f"PV of Perpetuity: {pv_perpetuity}")  # Should be $2000
```

## Internal Rate of Return (IRR)

### Basic IRR Calculation

Find the rate where NPV equals zero:

```python
from money_warp import irr

# Simple investment example
items = [
    CashFlowItem(Money("-1000"), datetime(2024, 1, 1), "Investment", "investment"),
    CashFlowItem(Money("1100"), datetime(2024, 12, 31), "Return", "return"),
]
cash_flow = CashFlow(items)

# Calculate IRR
investment_irr = irr(cash_flow)
print(f"IRR: {investment_irr}")  # Should be ~10%
```

### IRR with Custom Initial Guess

Provide a starting point for the numerical solver:

```python
# Use custom initial guess
guess = InterestRate("15% annual")
irr_with_guess = irr(cash_flow, guess=guess)
print(f"IRR with guess: {irr_with_guess}")  # Same result, different path
```

### Complex Cash Flow IRR

IRR works with irregular cash flows:

```python
# Complex investment with multiple cash flows
complex_items = [
    CashFlowItem(Money("-10000"), datetime(2024, 1, 1), "Initial investment", "investment"),
    CashFlowItem(Money("2000"), datetime(2024, 3, 1), "Q1 return", "return"),
    CashFlowItem(Money("-1000"), datetime(2024, 6, 1), "Additional investment", "investment"),
    CashFlowItem(Money("3000"), datetime(2024, 9, 1), "Q3 return", "return"),
    CashFlowItem(Money("8000"), datetime(2024, 12, 31), "Final return", "return"),
]
complex_cf = CashFlow(complex_items)

complex_irr = irr(complex_cf)
print(f"Complex IRR: {complex_irr}")
```

### Modified Internal Rate of Return (MIRR)

MIRR addresses IRR limitations by using different rates for financing and reinvestment:

```python
from money_warp import modified_internal_rate_of_return

# MIRR with different financing and reinvestment rates
finance_rate = InterestRate("10% annual")      # Cost of borrowing
reinvestment_rate = InterestRate("6% annual")  # Reinvestment return

mirr = modified_internal_rate_of_return(
    cash_flow=complex_cf,
    finance_rate=finance_rate,
    reinvestment_rate=reinvestment_rate
)
print(f"MIRR: {mirr}")
```

## Loan Analysis Sugar Syntax

### Loan Present Value

Calculate loan PV from borrower's perspective:

```python
from money_warp import Loan

# Create a loan
loan = Loan(
    principal=Money("10000"),
    interest_rate=InterestRate("5% annual"),
    due_dates=[datetime(2024, 6, 1), datetime(2024, 12, 1)],
    disbursement_date=datetime(2024, 1, 1)
)

# Present value using loan's own rate (should be close to zero)
pv_own_rate = loan.present_value()
print(f"PV at loan's rate: {pv_own_rate}")

# Present value using different discount rate
pv_market_rate = loan.present_value(InterestRate("8% annual"))
print(f"PV at 8%: {pv_market_rate}")  # Negative from borrower's perspective
```

### Loan IRR

Calculate loan's effective rate:

```python
# Loan IRR (should equal the loan's interest rate)
loan_irr = loan.irr()
print(f"Loan IRR: {loan_irr}")  # Should be ~5%

# IRR with custom guess
loan_irr_guess = loan.irr(guess=InterestRate("3% annual"))
print(f"Loan IRR with guess: {loan_irr_guess}")  # Same result
```

## Time Machine Integration

### IRR from Specific Dates

Use the Time Machine to calculate IRR from any point in time:

```python
from money_warp import Warp

# Calculate IRR from different time perspectives
current_irr = loan.irr()

# IRR as of a specific past date
with Warp(loan, datetime(2024, 3, 1)) as past_loan:
    past_irr = past_loan.irr()
    
print(f"Current IRR: {current_irr}")
print(f"IRR as of March 1: {past_irr}")
```

### Present Value with Time Machine

```python
# Present value from different time perspectives
current_pv = loan.present_value(InterestRate("8% annual"))

with Warp(loan, datetime(2024, 2, 1)) as past_loan:
    past_pv = past_loan.present_value(InterestRate("8% annual"))

print(f"Current PV: {current_pv}")
print(f"PV as of Feb 1: {past_pv}")
```

## Key Features

### Robust Numerics
- **Scipy-powered**: Uses `scipy.optimize.brentq` for reliable root finding
- **Automatic bracketing**: Finds sign changes in NPV function automatically
- **Fallback methods**: Uses `fsolve` if bracketing fails
- **High precision**: Maintains decimal precision throughout

### Error Handling
- **Clear messages**: Descriptive error messages for common issues
- **Convergence checking**: Validates solutions within reasonable tolerance
- **Edge case handling**: Handles empty cash flows, single-sign flows, etc.

### Integration
- **Time Machine**: All functions work seamlessly with `Warp`
- **Sugar syntax**: Convenient methods on `Loan` objects
- **Type safety**: Full type annotations and mypy compatibility
- **Consistent API**: Similar patterns across all TVM functions

## Common Patterns

### Investment Analysis
```python
# Compare investment alternatives
investments = [
    ("Project A", project_a_cashflow),
    ("Project B", project_b_cashflow),
    ("Project C", project_c_cashflow),
]

hurdle_rate = InterestRate("12% annual")

for name, cf in investments:
    pv = present_value(cf, hurdle_rate)
    irr_rate = irr(cf)
    print(f"{name}: PV={pv}, IRR={irr_rate}")
```

### Loan Comparison
```python
# Compare loan offers
loans = [loan_a, loan_b, loan_c]
market_rate = InterestRate("7% annual")

for i, loan in enumerate(loans, 1):
    pv = loan.present_value(market_rate)
    effective_rate = loan.irr()
    print(f"Loan {i}: PV={pv}, Effective Rate={effective_rate}")
```

### Sensitivity Analysis
```python
# Test different discount rates
rates = ["5% annual", "8% annual", "10% annual", "12% annual"]

for rate_str in rates:
    rate = InterestRate(rate_str)
    pv = present_value(cash_flow, rate)
    print(f"PV at {rate}: {pv}")
```

MoneyWarp's TVM functions provide the foundation for sophisticated financial analysis while maintaining simplicity and reliability through scipy-powered numerics.
