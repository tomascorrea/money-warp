# MoneyWarp 💰⏰

**Bend time. Model cash.**

[![Release](https://img.shields.io/github/v/release/tomas_correa/money-warp)](https://img.shields.io/github/v/release/tomas_correa/money-warp)
[![Build status](https://img.shields.io/github/actions/workflow/status/tomas_correa/money-warp/main.yml?branch=main)](https://github.com/tomas_correa/money-warp/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/tomas_correa/money-warp/branch/main/graph/badge.svg)](https://codecov.io/gh/tomas_correa/money-warp)
[![License](https://img.shields.io/github/license/tomas_correa/money-warp)](https://img.shields.io/github/license/tomas_correa/money-warp)

> **⚠️ Development Stage Notice**
> 
> MoneyWarp is currently in active development and should be considered **alpha/pre-release software**. While the core functionality is implemented and tested, the API may change between versions. Use in production environments at your own risk.
>
> - ✅ Core classes (`Money`, `InterestRate`, `CashFlow`, `Loan`) are stable
> - ✅ Comprehensive test suite with 240+ tests
> - ⚠️ API may evolve based on user feedback
> - ⚠️ Not yet published to PyPI
> - 🚧 Additional features and schedulers in development

MoneyWarp is a Python library for working with the time value of money. It treats loans, annuities, and investments as simple cash flows through time — and gives you the tools to warp them back and forth between present, future, and everything in between.

## 🚀 Features

- 🔢 **Calculate PMT, NPV, IRR** and other core finance functions
- ⏳ **Track loans and repayments** as evolving cash-flow streams  
- 🌀 **Explore "what if" timelines** by bending payments across time
- 💰 **High-precision calculations** using Decimal arithmetic
- 📊 **Progressive Price Schedules** (French amortization system)
- 🎯 **Flexible payment scheduling** with irregular due dates
- 🔒 **Type-safe interest rates** with explicit percentage handling

## 📦 Installation

```bash
pip install money-warp
```

Or with Poetry:

```bash
poetry add money-warp
```

## 🎯 Quick Start

### Basic Loan Analysis

```python
from datetime import datetime, timedelta
from money_warp import Money, InterestRate, Loan

# Create a $10,000 loan at 5% annual interest
principal = Money("10000.00")
rate = InterestRate("5% a")  # 5% annually

# Monthly payments for 12 months
start_date = datetime(2024, 1, 1)
due_dates = [start_date + timedelta(days=30*i) for i in range(1, 13)]

# Generate the loan
loan = Loan(principal, rate, due_dates)

# Get the payment schedule
schedule = loan.get_amortization_schedule()
print(f"Monthly payment: {schedule[0].payment_amount}")
print(f"Total interest: {schedule.total_interest}")

# Track actual payments
loan.record_payment(Money("856.07"), datetime(2024, 2, 1))
print(f"Remaining balance: {loan.current_balance}")
```

### Cash Flow Analysis

```python
from money_warp import CashFlow, CashFlowItem, Money
from datetime import datetime

# Create cash flow items
items = [
    CashFlowItem(Money("1000.00"), datetime(2024, 1, 1), "Initial deposit", "deposit"),
    CashFlowItem(Money("-50.00"), datetime(2024, 2, 1), "Monthly fee", "fee"),
    CashFlowItem(Money("200.00"), datetime(2024, 3, 1), "Interest payment", "interest"),
]

# Analyze the cash flow
cash_flow = CashFlow(items)
print(f"Net cash flow: {cash_flow.sum()}")
print(f"Total deposits: {cash_flow.query.filter_by(category='deposit').sum()}")

# Filter by date range
recent = cash_flow.query.filter_by(datetime__gte=datetime(2024, 2, 1))
print(f"Recent activity: {recent.sum()}")
```

### High-Precision Money Handling

```python
from money_warp import Money
from decimal import Decimal

# Create money with high internal precision
money = Money("100.123456789")
print(f"Internal precision: {money.raw_amount}")      # 100.123456789
print(f"Real money (2 decimals): {money.real_amount}") # 100.12
print(f"Display: {money}")                            # 100.12

# Arithmetic maintains precision internally
result = money * 3 / 7
print(f"Calculation result: {result}")  # Precise to 2 decimals for display
```

### Interest Rate Conversions

```python
from money_warp import InterestRate

# Create rates with explicit formats
annual_rate = InterestRate("5.25% a")     # 5.25% annually  
monthly_rate = InterestRate("0.4167% m")  # 0.4167% monthly
daily_rate = InterestRate("3% d")         # 3% daily (extreme example)

# Convert between frequencies
print(f"Annual: {annual_rate}")
print(f"As monthly: {annual_rate.to_monthly()}")
print(f"As daily: {annual_rate.to_daily()}")

# Safe decimal/percentage handling
print(f"As decimal: {annual_rate.as_decimal}")      # 0.0525
print(f"As percentage: {annual_rate.as_percentage}") # 5.25
```

## 🏗️ Architecture

MoneyWarp is built around four core concepts:

### 💰 Money
High-precision monetary amounts using Python's `Decimal` for accuracy:
- **Internal precision**: Stores full decimal precision
- **Display precision**: Shows 2 decimal places for "real money"
- **Arithmetic safety**: No floating-point errors

### 📈 InterestRate  
Type-safe interest rate handling with explicit conversions:
- **Clear representation**: Eliminates 0.05 vs 5% confusion
- **Frequency conversion**: Annual ↔ Monthly ↔ Daily ↔ Quarterly
- **String parsing**: `"5.25% annual"` or `"0.004167 monthly"`

### 💸 CashFlow
Container for cash flow analysis with SQLAlchemy-style querying:
- **CashFlowItem**: Individual transactions with amount, date, description, category
- **CashFlow**: Collection with filtering, summing, and analysis methods
- **Query interface**: `cashflow.query.filter_by(category='interest').sum()`

### 🏦 Loan
State machine for loan analysis with configurable schedulers:
- **Expected vs Actual**: Compare planned payments with reality
- **Payment allocation**: Automatic interest/principal calculation  
- **Flexible scheduling**: Any list of due dates, not just monthly
- **Multiple schedulers**: PMT-based, fixed payment, custom algorithms

## 📊 Supported Calculations

### Loan Schedules
- **Progressive Price Schedule** (French amortization system)
- **Fixed payment amounts** with interest/principal allocation
- **Irregular payment dates** with daily compounding
- **Bullet loans** (single payment at maturity)

### Financial Functions
- **PMT**: Payment calculation for loans and annuities
- **Daily compounding**: Precise interest calculations
- **Amortization schedules**: Complete payment breakdowns
- **Balance tracking**: Outstanding principal over time

## 🧪 Testing & Validation

MoneyWarp includes comprehensive test coverage with validation against established financial libraries:

- **254 total tests** with 100% core functionality coverage
- **Reference validation** against [cartaorobbin/loan-calculator](https://github.com/cartaorobbin/loan-calculator)
- **Edge case handling**: Zero interest, irregular schedules, high precision
- **Property-based testing**: Parametrized tests across various scenarios

## 🎯 Use Cases

### Personal Finance
- **Mortgage analysis**: Compare different loan terms and rates
- **Payment tracking**: Monitor actual vs expected payments
- **Refinancing decisions**: Calculate savings from rate changes

### Investment Analysis  
- **Cash flow modeling**: Track investment returns over time
- **Scenario analysis**: "What if" calculations with different assumptions
- **Performance measurement**: Calculate actual returns vs projections

### Financial Planning
- **Loan comparison**: Evaluate different lending options
- **Payment scheduling**: Optimize payment timing for cash flow
- **Interest calculation**: Precise daily compounding for any scenario

## 🔮 Roadmap

- **Additional Schedulers**: SAC (Price), Constant amortization, Custom schedules
- **TVM Functions**: NPV, IRR, PV, FV with irregular cash flows  
- **TimeMachine**: "What if" scenario modeling and comparison
- **Multi-currency**: Support for currency conversion and international rates
- **Performance optimization**: Vectorized calculations for large datasets

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.rst) for details.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Inspired by the time value of money concepts and validated against [cartaorobbin/loan-calculator](https://github.com/cartaorobbin/loan-calculator)
- Built with modern Python practices using Poetry, pytest, and pre-commit hooks
- Follows the Zen of Python: "Beautiful is better than ugly. Explicit is better than implicit."

---

**MoneyWarp** - Because time is money, and money should bend to your will. 💰⏰