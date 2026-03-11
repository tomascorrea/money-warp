# MoneyWarp

**Bend time. Model cash.**

[![Release](https://img.shields.io/github/v/release/tomascorrea/money-warp)](https://img.shields.io/github/v/release/tomascorrea/money-warp)
[![Build status](https://img.shields.io/github/actions/workflow/status/tomascorrea/money-warp/on-release-main.yml?branch=main)](https://github.com/tomascorrea/money-warp/actions/workflows/on-release-main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/tomascorrea/money-warp/branch/main/graph/badge.svg)](https://codecov.io/gh/tomascorrea/money-warp)
[![License](https://img.shields.io/github/license/tomascorrea/money-warp)](https://img.shields.io/github/license/tomascorrea/money-warp)

> **Development Stage Notice** -- MoneyWarp is in active development (alpha). Core classes are stable and covered by 1200+ tests, but the API may evolve.

MoneyWarp is a Python library for working with the time value of money. It treats loans, annuities, and investments as cash flows through time -- and gives you the tools to warp them back and forth between present, future, and everything in between.

## Key Features

- **Time Machine (Warp)** -- travel to any date and see loan state as of that moment
- **PMT, NPV, IRR, MIRR** -- core finance functions powered by scipy
- **Loan tracking** -- payments, fines, mora interest, grace periods
- **High-precision Money** -- Decimal arithmetic, never floats
- **Amortization schedules** -- French (Price) and SAC (Inverted Price)
- **Flexible dates** -- irregular due dates, smart month-end handling
- **Type-safe interest rates** -- explicit percentage handling, frequency conversions
- **Installments and Settlements** -- first-class repayment plan and payment allocation
- **Tax module** -- Brazilian IOF, grossup, pluggable tax strategy
- **Timezone-aware** -- UTC by default, configurable globally
- **Marshmallow extension** -- custom fields for serialization
- **SQLAlchemy extension** -- column types + loan/settlement bridge with SQL-queryable balance

## Time Value of Money Functions

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
- **Day-count conventions**: `YearSize.commercial` (365) or `YearSize.banker` (360) for IRR and MIRR
- **Automatic bracketing**: Robust root finding across complex cash flows
- **Sugar syntax**: `loan.irr()` convenience methods (automatically uses the loan's `year_size`)

### Integration Features
- **Time Machine compatibility**: All functions work with `Warp`
- **High precision**: Maintains decimal precision throughout
- **Type safety**: Full type annotations and mypy compatibility
- **Error handling**: Clear messages and edge case handling

## Documentation

Explore the comprehensive examples and API reference:

- **[Quick Start](examples/quickstart.md)** -- get up and running quickly
- **[Money](examples/money.md)** -- high-precision monetary amounts
- **[Interest Rates](examples/interest_rates.md)** -- type-safe rate handling and conversions
- **[Date Generation](examples/date_generation.md)** -- smart payment date utilities
- **[Present Value & IRR](examples/present_value_irr.md)** -- TVM functions and analysis
- **[Time Machine](examples/time_machine.md)** -- travel through time with loans
- **[Cash Flow Analysis](examples/cash_flow.md)** -- work with cash flow streams
- **[Fines & Payments](examples/fines.md)** -- fines, mora interest, installments, settlements, and payment methods
- **[Tax & IOF](examples/tax.md)** -- Brazilian IOF, grossup, and pluggable taxes
- **[Timezone Handling](examples/timezone.md)** -- UTC default, global configuration, silent coercion
- **[Marshmallow Extension](examples/marshmallow.md)** -- custom Marshmallow fields for Money, Rate, InterestRate
- **[SQLAlchemy Extension](examples/sqlalchemy.md)** -- column types, bridge decorators, SQL-queryable balance
- **[API Reference](modules.md)** -- complete function documentation

## Architecture

MoneyWarp is built around core financial concepts:

- **Money**: High-precision monetary amounts using Decimal
- **InterestRate**: Type-safe rates with frequency conversions, abbreviated notation, and day-count conventions
- **CashFlow**: Collections with SQLAlchemy-style querying
- **Loan**: State machines for loan analysis and tracking
- **Installment & Settlement**: Derived views of repayment plans and payment allocations
- **Tax**: Pluggable tax strategy with IOF, grossup, and presets
- **tz**: Timezone configuration -- UTC default, global `set_tz()`, silent coercion
- **Warp**: Time Machine for temporal financial analysis

## Quality & Testing

- **1200+ comprehensive tests** with 100% core functionality coverage
- **Type safety**: Full mypy compatibility with zero type errors
- **Code quality**: Passes ruff linting and black formatting
- **Robust numerics**: Scipy-powered calculations for reliability
- **Reference validation**: Tested against established financial libraries

MoneyWarp combines the power of modern Python with solid financial theory to provide a reliable foundation for time value of money calculations.
