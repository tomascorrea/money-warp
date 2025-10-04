# Quick Start Guide

Welcome to MoneyWarp! This guide will get you up and running with the core concepts in just a few minutes.

> **⚠️ Development Notice:** MoneyWarp is in active development (alpha stage). The core functionality is stable and well-tested, but the API may evolve. Not recommended for production use yet.

## Installation

> **Note:** MoneyWarp is not yet published to PyPI. For now, install from source:

```bash
git clone https://github.com/tomas_correa/money-warp.git
cd money-warp
pip install -e .
```

Or using Poetry (recommended for development):

```bash
git clone https://github.com/tomas_correa/money-warp.git
cd money-warp
poetry install
```

## Basic Loan Analysis

Let's start with a simple loan analysis - the most common use case:

```python
from datetime import datetime, timedelta
from money_warp import Money, InterestRate, Loan

# Create a $10,000 personal loan at 8% annual interest
principal = Money("10000.00")
rate = InterestRate("8% a")  # 8% annually

# Set up monthly payments for 2 years (24 payments)
start_date = datetime(2024, 1, 1)
due_dates = [start_date + timedelta(days=30*i) for i in range(1, 25)]

# Create the loan
loan = Loan(principal, rate, due_dates)

# Get the payment schedule
schedule = loan.get_amortization_schedule()

print(f"Monthly payment: {schedule[0].payment_amount}")
print(f"Total interest over life of loan: {schedule.total_interest}")
print(f"Total amount to be paid: {schedule.total_payments}")
```

**Output:**
```
Monthly payment: 452.27
Total interest over life of loan: 854.48
Total amount to be paid: 10,854.48
```

## Payment Breakdown

Let's examine how each payment is split between interest and principal:

```python
# Look at the first few payments
for i in range(3):
    payment = schedule[i]
    print(f"Payment {payment.payment_number}:")
    print(f"  Total: {payment.payment_amount}")
    print(f"  Interest: {payment.interest_payment}")
    print(f"  Principal: {payment.principal_payment}")
    print(f"  Remaining balance: {payment.ending_balance}")
    print()
```

**Output:**
```
Payment 1:
  Total: 452.27
  Interest: 66.85
  Principal: 385.42
  Remaining balance: 9,614.58

Payment 2:
  Total: 452.27
  Interest: 64.28
  Principal: 387.99
  Remaining balance: 9,226.59

Payment 3:
  Total: 452.27
  Interest: 61.69
  Principal: 390.58
  Remaining balance: 8,836.01
```

Notice how the interest portion decreases and principal portion increases over time!

## Tracking Actual Payments

Now let's track what actually happens when you make payments:

```python
# Record some actual payments
loan.record_payment(Money("452.27"), datetime(2024, 2, 1), "First payment")
loan.record_payment(Money("500.00"), datetime(2024, 3, 1), "Extra payment")  # Paid extra!

print(f"Current balance: {loan.current_balance}")
print(f"Days since last payment: {loan.days_since_last_payment()}")

# Compare expected vs actual cash flow
actual_cf = loan.get_actual_cash_flow()
actual_payments = actual_cf.query.filter_by(category__in=["actual_interest", "actual_principal"])
print(f"Total actual payments so far: {actual_payments.sum()}")
```

## Cash Flow Analysis

MoneyWarp treats everything as cash flows, making it easy to analyze complex scenarios:

```python
from money_warp import CashFlow, CashFlowItem

# Create a cash flow for investment analysis
cash_flows = [
    CashFlowItem(Money("-10000.00"), datetime(2024, 1, 1), "Initial investment", "investment"),
    CashFlowItem(Money("500.00"), datetime(2024, 4, 1), "Q1 dividend", "dividend"),
    CashFlowItem(Money("500.00"), datetime(2024, 7, 1), "Q2 dividend", "dividend"),
    CashFlowItem(Money("500.00"), datetime(2024, 10, 1), "Q3 dividend", "dividend"),
    CashFlowItem(Money("11000.00"), datetime(2024, 12, 31), "Sale proceeds", "sale"),
]

portfolio = CashFlow(cash_flows)

print(f"Net cash flow: {portfolio.sum()}")
print(f"Total dividends: {portfolio.query.filter_by(category='dividend').sum()}")
print(f"Return on investment: {(portfolio.sum() / Money('10000.00')) * 100:.2f}%")
```

**Output:**
```
Net cash flow: 2,500.00
Total dividends: 1,500.00
Return on investment: 25.00%
```

## High-Precision Calculations

MoneyWarp uses Python's Decimal for precision, avoiding floating-point errors:

```python
# This would cause precision issues with floats
money1 = Money("0.1")
money2 = Money("0.2") 
result = money1 + money2

print(f"0.1 + 0.2 = {result}")  # Exactly 0.30, not 0.30000000000000004!

# Complex calculations maintain precision
complex_calc = Money("100.00") * 1.08 / 12 * 365.25
print(f"Complex calculation: {complex_calc}")
print(f"Internal precision: {complex_calc.raw_amount}")
print(f"Display precision: {complex_calc.real_amount}")
```

## Interest Rate Conversions

Work with interest rates safely and explicitly:

```python
# Create rates with clear formats
annual = InterestRate("6.5% a")      # 6.5% annually
monthly = InterestRate("0.5417% m")  # 0.5417% monthly

# Convert between frequencies
print(f"Annual rate: {annual}")
print(f"As monthly: {annual.to_monthly()}")
print(f"As daily: {annual.to_daily()}")

# Safe decimal access
print(f"As decimal: {annual.as_decimal}")      # 0.065
print(f"As percentage: {annual.as_percentage}") # 6.5
```

## Next Steps

Now that you've seen the basics, explore the detailed examples:

- **[Money & Precision](money.md)** - Deep dive into high-precision calculations
- **[Interest Rates](interest_rates.md)** - Master interest rate conversions
- **[Cash Flow Analysis](cash_flow.md)** - Advanced cash flow modeling
- **[Time Machine (Warp)](time_machine.md)** - Time travel for financial modeling
- **[Present Value & IRR](present_value_irr.md)** - Investment analysis tools

## Key Concepts Recap

1. **Money**: High-precision monetary amounts with 2-decimal display
2. **InterestRate**: Type-safe rates with explicit frequency conversion
3. **CashFlow**: Collections of transactions with powerful querying
4. **Loan**: State machine for loan analysis with actual vs expected tracking
5. **Schedulers**: Pluggable algorithms for different amortization methods

Ready to dive deeper? Choose your next topic from the examples above! 🚀
