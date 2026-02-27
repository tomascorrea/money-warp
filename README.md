# MoneyWarp 💰⏰

**Bend time. Model cash.**

[![Release](https://img.shields.io/github/v/release/tomascorrea/money-warp)](https://img.shields.io/github/v/release/tomascorrea/money-warp)
[![Build status](https://img.shields.io/github/actions/workflow/status/tomascorrea/money-warp/on-release-main.yml?branch=main)](https://github.com/tomascorrea/money-warp/actions/workflows/on-release-main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/tomascorrea/money-warp/branch/main/graph/badge.svg)](https://codecov.io/gh/tomascorrea/money-warp)
[![License](https://img.shields.io/github/license/tomascorrea/money-warp)](https://img.shields.io/github/license/tomascorrea/money-warp)

> **⚠️ Development Stage Notice**
> 
> MoneyWarp is currently in active development and should be considered **alpha/pre-release software**. While the core functionality is implemented and tested, the API may change between versions. Use in production environments at your own risk.
>
> - ✅ Core classes (`Money`, `InterestRate`, `CashFlow`, `Loan`) are stable
> - ✅ Comprehensive test suite with 830+ tests
> - ⚠️ API may evolve based on user feedback
> - ✅ Published to PyPI
> - 🚧 Additional features and schedulers in development

MoneyWarp is a Python library for working with the time value of money. It treats loans, annuities, and investments as simple cash flows through time — and gives you the tools to warp them back and forth between present, future, and everything in between.

## 🚀 Features

- 🕰️ **Time Machine (Warp)** - Travel to any date and see loan state as of that moment
- 🔢 **Calculate PMT, NPV, IRR, MIRR** and other core finance functions with scipy
- ⏳ **Track loans and repayments** as evolving cash-flow streams  
- 🌀 **Explore "what if" timelines** by bending payments across time
- 💰 **High-precision calculations** using Decimal arithmetic
- 📊 **Progressive Price Schedules** (French amortization system)
- 📈 **Inverted Price Schedules** (Constant Amortization System - SAC)
- 🎯 **Flexible payment scheduling** with irregular due dates
- 📅 **Easy date generation** with smart month-end handling via python-dateutil
- 🔒 **Type-safe interest rates** with explicit percentage handling
- 🧮 **Robust numerics** powered by scipy for IRR and financial calculations
- ⚖️ **Fine engine** with fines, mora interest, and configurable grace periods
- 🍭 **Sugar payment methods** — `pay_installment()` and `anticipate_payment()` for natural workflows
- 📋 **Installments & Settlements** — first-class views of the repayment plan and payment allocation
- 🇧🇷 **Tax module** — Brazilian IOF with pluggable tax strategy, grossup, and preset rates
- 🌐 **Timezone-aware** — all datetimes are UTC by default, configurable globally

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
from datetime import datetime, timezone
from money_warp import Money, InterestRate, Loan, generate_monthly_dates

# Create a $10,000 loan at 5% annual interest
principal = Money("10000.00")
rate = InterestRate("5% a")  # 5% annually

# Generate monthly payment dates easily
# Naive datetimes work too — they're silently coerced to the configured timezone (UTC)
start_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
due_dates = generate_monthly_dates(start_date, 12)

# Generate the loan
loan = Loan(principal, rate, due_dates)

# Get the payment schedule
schedule = loan.get_amortization_schedule()
print(f"Monthly payment: {schedule[0].payment_amount}")
print(f"Total interest: {schedule.total_interest}")

# Track actual payments
loan.record_payment(Money("856.07"), datetime(2024, 2, 1, tzinfo=timezone.utc))
print(f"Remaining balance: {loan.current_balance}")
```

### Installments & Settlements

```python
from money_warp import Loan, Money, InterestRate, generate_monthly_dates
from datetime import datetime

loan = Loan(
    Money("10000"),
    InterestRate("6% a"),
    generate_monthly_dates(datetime(2025, 2, 1), 3),
    disbursement_date=datetime(2025, 1, 1),
)

# Installments are the repayment plan — a consequence of the loan
for inst in loan.installments:
    print(f"#{inst.number} due {inst.due_date.date()}: "
          f"{inst.expected_payment} (principal: {inst.expected_principal}, "
          f"interest: {inst.expected_interest}) — paid: {inst.is_paid}")

# Payments return a Settlement showing how money was allocated
schedule = loan.get_original_schedule()
settlement = loan.record_payment(schedule[0].payment_amount, schedule[0].due_date)
print(f"Principal paid: {settlement.principal_paid}")
print(f"Interest paid: {settlement.interest_paid}")
print(f"Remaining balance: {settlement.remaining_balance}")

# Settlements show per-installment detail
for alloc in settlement.allocations:
    print(f"  Installment #{alloc.installment_number}: "
          f"principal={alloc.principal_allocated}, covered={alloc.is_fully_covered}")

# After payment, installments reflect what happened
inst = loan.installments[0]
print(f"Installment #1 paid: {inst.is_paid}, principal_paid: {inst.principal_paid}")
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
print(f"Net cash flow: {cash_flow.net_present_value()}")
print(f"Total deposits: {cash_flow.query.filter_by(category='deposit').sum_amounts()}")

# Filter by date range
recent = cash_flow.query.filter_by(datetime__gte=datetime(2024, 2, 1))
print(f"Recent activity: {recent.sum_amounts()}")
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

### Time Machine - Warp to Any Date 🕰️

**Core Philosophy:** *The loan is always time sensitive... it always filters based on present date regardless if it is warped or not... the warp just changes the present date.*

```python
from money_warp import Warp, Loan, Money, InterestRate
from datetime import datetime

# Create a loan and make some payments
loan = Loan(Money("10000"), InterestRate("5% a"), [datetime(2024, 1, 15)])
loan.record_payment(Money("500"), datetime(2024, 1, 10), "Payment 1")
loan.record_payment(Money("600"), datetime(2024, 2, 10), "Payment 2") 
loan.record_payment(Money("700"), datetime(2024, 3, 10), "Payment 3")

print(f"Current balance: {loan.current_balance}")  # All payments applied

# Warp to the past - only see payments made by that date
with Warp(loan, datetime(2024, 1, 20)) as past_loan:
    print(f"Balance on Jan 20: {past_loan.current_balance}")  # Only first payment
    print(f"Payments made: {len(past_loan._actual_payments)}")  # 2 items (interest + principal)

# Warp to the future - see all payments up to that date  
with Warp(loan, datetime(2025, 1, 1)) as future_loan:
    print(f"Balance in future: {future_loan.current_balance}")  # All payments applied
    print(f"Days since last payment: {future_loan.days_since_last_payment()}")  # From warped date

# Original loan unchanged
print(f"Back to present: {loan.current_balance}")
```

**Key Features:**
- 🕰️ **Natural time filtering**: Loans automatically show state as of any date
- 🔄 **Safe cloning**: Original loan never modified during time travel
- 📅 **Flexible date formats**: Accepts strings, datetime objects, or date objects
- 🚫 **No nested warps**: Prevents dangerous time paradoxes
- ⚡ **Instant calculations**: Balance and payment history update automatically

### Interest Rate Conversions

```python
from money_warp import InterestRate, CompoundingFrequency, YearSize

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

# Abbreviated notation (Brazilian/LatAm convention)
rate = InterestRate("5.25% a.a.")   # parsed as 5.25% annually
print(rate)                         # "5.250% a.a." — round-trips automatically

# Or set the style explicitly on numeric rates
rate = InterestRate(1.5, CompoundingFrequency.MONTHLY, as_percentage=True, str_style="abbrev")
print(rate)                         # "1.500% a.m."

# Day-count convention: commercial (365 days, default) or banker (360 days)
commercial = InterestRate("10% a", year_size=YearSize.commercial)
banker = InterestRate("10% a", year_size=YearSize.banker)
print(f"Commercial daily: {commercial.to_daily()}")  # 365-day year
print(f"Banker daily: {banker.to_daily()}")          # 360-day year — slightly higher
```

### Easy Date Generation 📅

**Simplified with python-dateutil for robust date handling:**

```python
from datetime import datetime
from money_warp import (
    generate_monthly_dates,
    generate_biweekly_dates,
    generate_weekly_dates,
    generate_quarterly_dates,
    generate_annual_dates,
    generate_custom_interval_dates,
)

# Monthly payments (handles end-of-month intelligently)
monthly_dates = generate_monthly_dates(datetime(2024, 1, 31), 12)
print(f"Jan 31 → Feb 29 → Mar 31...")  # Anchors to original day (31st)

# Bi-weekly payments (every 14 days)
biweekly_dates = generate_biweekly_dates(datetime(2024, 1, 1), 26)
print(f"26 payments over ~1 year")

# Weekly payments
weekly_dates = generate_weekly_dates(datetime(2024, 1, 1), 52)

# Quarterly payments
quarterly_dates = generate_quarterly_dates(datetime(2024, 1, 15), 4)

# Annual payments
annual_dates = generate_annual_dates(datetime(2024, 1, 1), 30)  # 30-year loan

# Custom intervals (every N days)
custom_dates = generate_custom_interval_dates(datetime(2024, 1, 1), 10, 45)  # Every 45 days

# Use with loans immediately
loan = Loan(
    principal=Money("50000"),
    interest_rate=InterestRate("3.5% annual"),
    due_dates=monthly_dates  # Just plug in the generated dates!
)
```

**Key Features:**
- 🗓️ **Smart date handling**: Uses `python-dateutil` for robust month arithmetic
- 📅 **End-of-month intelligence**: Jan 31 → Feb 29 → Mar 31 (anchors to original day)
- 🎯 **Simple API**: Just `datetime` and `int` parameters, no complex options
- ⚡ **Instant integration**: Generated dates work directly with `Loan` objects
- 🔒 **Type-safe**: Full type annotations and validation
```

### Timezone-Aware Datetimes 🌐

All datetimes inside MoneyWarp are timezone-aware. By default, UTC is used. Naive datetimes passed to any API are silently treated as UTC (or whatever timezone you configure).

```python
from money_warp import get_tz, set_tz, now

# Check the default
print(get_tz())  # datetime.timezone.utc

# Get the current time (always aware)
print(now())  # e.g. 2024-06-15 14:30:00+00:00

# Change the default timezone
set_tz("America/Sao_Paulo")
print(now())  # e.g. 2024-06-15 11:30:00-03:00

# You can also use a tzinfo object
from datetime import timezone, timedelta
set_tz(timezone(timedelta(hours=-3)))

# Reset back to UTC
set_tz("UTC")
```

Naive datetimes are accepted everywhere for convenience — the library converts them automatically:

```python
from datetime import datetime
from money_warp import Loan, Money, InterestRate

# These naive datetimes are silently coerced to UTC
loan = Loan(
    Money("10000"),
    InterestRate("5% a"),
    [datetime(2024, 2, 1), datetime(2024, 3, 1)],
    disbursement_date=datetime(2024, 1, 1),
)
print(loan.disbursement_date)  # 2024-01-01 00:00:00+00:00
```

### Present Value and IRR Analysis 🧮

**Powered by scipy for robust numerical calculations:**

```python
from money_warp import CashFlow, CashFlowItem, Money, InterestRate
from money_warp import present_value, irr, modified_internal_rate_of_return
from datetime import datetime

# Create an investment cash flow
items = [
    CashFlowItem(Money("-10000"), datetime(2024, 1, 1), "Initial investment", "investment"),
    CashFlowItem(Money("3000"), datetime(2024, 12, 31), "Year 1 return", "return"),
    CashFlowItem(Money("4000"), datetime(2025, 12, 31), "Year 2 return", "return"),
    CashFlowItem(Money("5000"), datetime(2026, 12, 31), "Year 3 return", "return"),
]
cash_flow = CashFlow(items)

# Calculate Present Value at 8% discount rate
discount_rate = InterestRate("8% annual")
pv = present_value(cash_flow, discount_rate)
print(f"Present Value at 8%: {pv}")

# Calculate Internal Rate of Return
investment_irr = irr(cash_flow)
print(f"IRR: {investment_irr}")  # Should be ~9.7%

# IRR with banker's year (360 days) for day-count convention
from money_warp import YearSize
banker_irr = irr(cash_flow, year_size=YearSize.banker)
print(f"IRR (360-day year): {banker_irr}")

# Calculate Modified IRR with different reinvestment assumptions
finance_rate = InterestRate("10% annual")      # Cost of capital
reinvestment_rate = InterestRate("6% annual")  # Reinvestment rate
mirr = modified_internal_rate_of_return(cash_flow, finance_rate, reinvestment_rate)
print(f"MIRR: {mirr}")

# Loan IRR (borrower's perspective)
loan = Loan(Money("10000"), InterestRate("5% annual"), [datetime(2024, 12, 31)])
loan_irr = loan.irr()  # Sugar syntax — uses the loan's own year_size
print(f"Loan IRR: {loan_irr}")  # Should be ~5% (loan's own rate)

# Present Value of loan using different discount rate
loan_pv = loan.present_value(InterestRate("8% annual"))
print(f"Loan PV at 8%: {loan_pv}")  # Negative from borrower's perspective
```

**Key Features:**
- 🔬 **Scipy-powered**: Uses `scipy.optimize.brentq` for robust root finding
- 📊 **Automatic bracketing**: Finds IRR solutions reliably across complex cash flows
- 🕰️ **Time Machine integration**: Use `Warp` to calculate IRR from any date
- 🍭 **Sugar syntax**: `loan.irr()` and `loan.present_value()` convenience methods
- 💰 **High precision**: Maintains decimal precision throughout calculations
- 📅 **Day-count conventions**: `YearSize.commercial` (365) or `YearSize.banker` (360) for IRR and MIRR
```

### Tax & Grossup (Brazilian IOF) 🇧🇷

**Pluggable tax system with built-in IOF support and grossup for financed taxes:**

```python
from datetime import datetime
from money_warp import (
    Money, InterestRate, Loan, IndividualIOF, CorporateIOF,
    grossup_loan, PriceScheduler, generate_monthly_dates,
)

# Use preset rates for individual borrowers (PF)
iof = IndividualIOF()  # daily=0.0082%, additional=0.38%

# Or for corporate borrowers (PJ)
iof_pj = CorporateIOF()  # daily=0.0041%, additional=0.38%

# Attach tax to a loan for reporting
due_dates = generate_monthly_dates(datetime(2024, 2, 1), 12)
loan = Loan(
    Money("10000"), InterestRate("1% m"), due_dates,
    disbursement_date=datetime(2024, 1, 1),
    taxes=[iof],
)
print(f"Total IOF: {loan.total_tax}")
print(f"Net disbursement: {loan.net_disbursement}")  # principal - tax

# Grossup: borrower wants to receive exactly 10,000 after tax
grossed_loan = grossup_loan(
    requested_amount=Money("10000"),
    interest_rate=InterestRate("1% m"),
    due_dates=due_dates,
    disbursement_date=datetime(2024, 1, 1),
    scheduler=PriceScheduler,
    taxes=[iof],
)
print(f"Grossed-up principal: {grossed_loan.principal}")    # > 10,000
print(f"Net to borrower: {grossed_loan.net_disbursement}")  # ~= 10,000
```

**Key Features:**
- 🔌 **Pluggable taxes**: Implement `BaseTax` for any tax type
- 🇧🇷 **IOF built-in**: Brazilian IOF with daily + additional rate components
- 👤 **Presets**: `IndividualIOF()` and `CorporateIOF()` with standard rates (overridable)
- 🔄 **Grossup**: Scipy-powered solver finds the principal so `principal - tax = requested_amount`
- 📊 **Rounding modes**: `PRECISE` (default) or `PER_COMPONENT` to match external systems

## 🏗️ Architecture

MoneyWarp is built around six core concepts:

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
- **Abbreviated notation**: `"5.25% a.a."`, `"1.5% a.m."` (Brazilian/LatAm convention)
- **Day-count convention**: `YearSize.commercial` (365) or `YearSize.banker` (360)

### 💸 CashFlow
Container for cash flow analysis with SQLAlchemy-style querying:
- **CashFlowItem**: Individual transactions with amount, date, description, category
- **CashFlow**: Collection with filtering, summing, and analysis methods
- **Query interface**: `cashflow.query.filter_by(category='interest').sum_amounts()`

### 🏦 Loan
State machine for loan analysis with configurable schedulers:
- **Expected vs Actual**: Compare planned payments with reality
- **Payment allocation**: Fines → Interest → Principal priority
- **Fine engine**: Automatic fines and mora interest for overdue payments
- **Sugar methods**: `pay_installment()` and `anticipate_payment()` for natural workflows
- **Installments**: Repayment plan as first-class objects derived from loan terms
- **Settlements**: Payment allocation results with per-installment detail
- **Flexible scheduling**: Any list of due dates, not just monthly
- **Multiple schedulers**: PMT-based, fixed payment, custom algorithms

### 🌐 Timezone (tz)
Global timezone configuration with automatic coercion:
- **UTC by default**: All datetimes are timezone-aware out of the box
- **Configurable**: `set_tz("America/Sao_Paulo")` changes the default globally
- **Silent coercion**: Naive datetimes passed to any API are automatically coerced
- **`@tz_aware` decorator**: Applied to API boundaries — no manual conversion needed

### 🇧🇷 Tax
Pluggable tax strategy with Brazilian IOF and grossup:
- **BaseTax interface**: Implement `calculate()` for any tax type
- **IOF**: Daily rate + additional rate components with configurable rounding
- **Presets**: `IndividualIOF` (PF) and `CorporateIOF` (PJ) with standard rates
- **Grossup**: Scipy-powered solver for financed tax calculations

## 📊 Supported Calculations

### Loan Schedules
- **Progressive Price Schedule** (French amortization system)
- **Inverted Price Schedule** (Constant Amortization System - SAC)
- **Fixed payment amounts** with interest/principal allocation
- **Irregular payment dates** with daily compounding
- **Bullet loans** (single payment at maturity)

### Time Value of Money Functions
- **Present Value (PV)**: Discount future cash flows to present value
- **Net Present Value (NPV)**: Sum of discounted cash flows
- **Internal Rate of Return (IRR)**: Rate where NPV equals zero, with configurable day-count convention
- **Modified IRR (MIRR)**: IRR with different financing/reinvestment rates, with configurable day-count convention
- **Present Value of Annuities**: Regular payment streams
- **Present Value of Perpetuities**: Infinite payment streams
- **Discount Factors**: Time value calculations

### Financial Functions
- **PMT**: Payment calculation for loans and annuities
- **Daily compounding**: Precise interest calculations
- **Amortization schedules**: Complete payment breakdowns
- **Balance tracking**: Outstanding principal over time
- **Robust numerics**: Scipy-powered calculations for complex scenarios

### Tax Calculations
- **IOF (Brazilian)**: Daily + additional rate on each installment's principal
- **Grossup**: Find the principal so borrower receives the exact requested amount
- **Per-installment breakdown**: Tax detail for every installment in the schedule
- **Rounding modes**: Precise (sum-then-round) or per-component (round-then-sum)
- **Custom taxes**: Extend `BaseTax` for any jurisdiction or tax type

## 🧪 Testing & Validation

MoneyWarp includes comprehensive test coverage with validation against established financial libraries:

- **830+ total tests** with 100% core functionality coverage
- **Reference validation** against [cartaorobbin/loan-calculator](https://github.com/cartaorobbin/loan-calculator)
- **External IOF validation** against a production Brazilian lending platform
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

- ✅ **Time Machine (Warp)**: Travel to any date and analyze loan state - *COMPLETED*
- ✅ **Inverted Price Scheduler**: Constant Amortization System (SAC) - *COMPLETED*
- ✅ **Present Value Functions**: PV, NPV, annuities, perpetuities - *COMPLETED*
- ✅ **IRR Functions**: IRR, MIRR with scipy-powered numerics - *COMPLETED*
- ✅ **Date Generation Utilities**: Smart payment scheduling - *COMPLETED*
- ✅ **Fine Engine**: Fines, mora interest, grace periods - *COMPLETED*
- ✅ **Payment Sugar Methods**: `pay_installment()`, `anticipate_payment()` - *COMPLETED*
- ✅ **Tax Module**: Brazilian IOF, grossup, pluggable tax strategy - *COMPLETED*
- ✅ **Installments & Settlements**: First-class repayment plan and payment allocation views - *COMPLETED*
- ✅ **Timezone-Aware Datetimes**: UTC by default with configurable global timezone - *COMPLETED*
- **Additional Schedulers**: Custom schedules, balloon payments
- **Performance optimization**: Vectorized calculations for large datasets
- **Advanced TVM**: Bond pricing, option valuation

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