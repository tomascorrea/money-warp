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
> - ✅ Comprehensive test suite with 465 tests
> - ✅ Time Machine, Present Value, and IRR functions complete
> - ⚠️ API may evolve based on user feedback
> - ⚠️ Not yet published to PyPI
> - 🚧 Additional features and schedulers in development

MoneyWarp is a Python library for working with the time value of money. It treats loans, annuities, and investments as simple cash flows through time — and gives you the tools to warp them back and forth between present, future, and everything in between.

## 🚀 Key Features

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
- 🍭 **Sugar payment methods** — `pay_installment()` and `anticipate_payment()`

## 🧮 Time Value of Money Functions

MoneyWarp provides comprehensive TVM functions powered by scipy:

### Present Value Functions
- **Present Value (PV)**: Discount future cash flows to present value
- **Net Present Value (NPV)**: Sum of discounted cash flows
- **Present Value of Annuities**: Regular payment streams
- **Present Value of Perpetuities**: Infinite payment streams
- **Discount Factors**: Time value calculations

### Internal Rate of Return
- **IRR**: Rate where NPV equals zero (scipy-powered for reliability)
- **Modified IRR (MIRR)**: IRR with different financing/reinvestment rates
- **Automatic bracketing**: Robust root finding across complex cash flows
- **Sugar syntax**: `loan.irr()` convenience methods

### Integration Features
- **Time Machine compatibility**: All functions work with `Warp`
- **High precision**: Maintains decimal precision throughout
- **Type safety**: Full type annotations and mypy compatibility
- **Error handling**: Clear messages and edge case handling

## 📖 Documentation

Explore the comprehensive examples and API reference:

- **[Quick Start](examples/quickstart.md)** - Get up and running quickly
- **[Money](examples/money.md)** - High-precision monetary amounts
- **[Interest Rates](examples/interest_rates.md)** - Type-safe rate handling and conversions
- **[Date Generation](examples/date_generation.md)** - Smart payment date utilities
- **[Present Value & IRR](examples/present_value_irr.md)** - TVM functions and analysis
- **[Time Machine](examples/time_machine.md)** - Travel through time with loans
- **[Cash Flow Analysis](examples/cash_flow.md)** - Work with cash flow streams
- **[Fines & Payments](examples/fines.md)** - Fines, mora interest, and payment methods
- **[API Reference](modules.md)** - Complete function documentation

## 🏗️ Architecture

MoneyWarp is built around core financial concepts:

- **💰 Money**: High-precision monetary amounts using Decimal
- **📈 InterestRate**: Type-safe rates with frequency conversions  
- **💸 CashFlow**: Collections with SQLAlchemy-style querying
- **🏦 Loan**: State machines for loan analysis and tracking
- **🕰️ Warp**: Time Machine for temporal financial analysis

## 🧪 Quality & Testing

- **469 comprehensive tests** with 100% core functionality coverage
- **Type safety**: Full mypy compatibility with zero type errors
- **Code quality**: Passes ruff linting and black formatting
- **Robust numerics**: Scipy-powered calculations for reliability
- **Reference validation**: Tested against established financial libraries

MoneyWarp combines the power of modern Python with solid financial theory to provide a reliable foundation for time value of money calculations.