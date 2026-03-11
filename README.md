# MoneyWarp

**Bend time. Model cash.**

[![Release](https://img.shields.io/github/v/release/tomascorrea/money-warp)](https://img.shields.io/github/v/release/tomascorrea/money-warp)
[![Build status](https://img.shields.io/github/actions/workflow/status/tomascorrea/money-warp/on-release-main.yml?branch=main)](https://github.com/tomascorrea/money-warp/actions/workflows/on-release-main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/tomascorrea/money-warp/branch/main/graph/badge.svg)](https://codecov.io/gh/tomascorrea/money-warp)
[![License](https://img.shields.io/github/license/tomascorrea/money-warp)](https://img.shields.io/github/license/tomascorrea/money-warp)

> **Development Stage Notice** -- MoneyWarp is in active development (alpha). Core classes are stable and covered by 1200+ tests, but the API may evolve.

MoneyWarp is a Python library for working with the time value of money. It treats loans, annuities, and investments as cash flows through time -- and gives you the tools to warp them back and forth between present, future, and everything in between.

## Features

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

## Installation

```bash
pip install money-warp
```

With optional extensions:

```bash
pip install money-warp[marshmallow]   # Marshmallow fields
pip install money-warp[sa]            # SQLAlchemy types + bridge
```

## Quick Start

```python
from datetime import datetime, timezone
from money_warp import Money, InterestRate, Loan, generate_monthly_dates

principal = Money("10000.00")
rate = InterestRate("5% a")  # 5% annually

start_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
due_dates = generate_monthly_dates(start_date, 12)

loan = Loan(principal, rate, due_dates)

schedule = loan.get_amortization_schedule()
print(f"Monthly payment: {schedule[0].payment_amount}")
print(f"Total interest: {schedule.total_interest}")

loan.record_payment(Money("856.07"), datetime(2024, 2, 1, tzinfo=timezone.utc))
print(f"Remaining balance: {loan.current_balance}")
```

## Time Machine

Travel to any date and see the loan exactly as it was -- payments, interest, fines, everything filtered to that moment:

```python
from money_warp import Warp, Loan, Money, InterestRate
from datetime import datetime

loan = Loan(Money("10000"), InterestRate("5% a"), [datetime(2024, 1, 15)])
loan.record_payment(Money("500"), datetime(2024, 1, 10))
loan.record_payment(Money("600"), datetime(2024, 2, 10))
loan.record_payment(Money("700"), datetime(2024, 3, 10))

# Warp to the past -- only payments made by that date are visible
with Warp(loan, datetime(2024, 1, 20)) as past_loan:
    print(f"Balance on Jan 20: {past_loan.current_balance}")

# Warp to the future
with Warp(loan, datetime(2025, 1, 1)) as future_loan:
    print(f"Balance in 2025: {future_loan.current_balance}")

# Original loan is unchanged
print(f"Present balance: {loan.current_balance}")
```

## Documentation

Full guides, examples, and API reference at **[tomascorrea.github.io/money-warp](https://tomascorrea.github.io/money-warp)**.

- [Quick Start](https://tomascorrea.github.io/money-warp/examples/quickstart/)
- [Money and Precision](https://tomascorrea.github.io/money-warp/examples/money/)
- [Interest Rates](https://tomascorrea.github.io/money-warp/examples/interest_rates/)
- [Cash Flow Analysis](https://tomascorrea.github.io/money-warp/examples/cash_flow/)
- [Date Generation](https://tomascorrea.github.io/money-warp/examples/date_generation/)
- [Time Machine](https://tomascorrea.github.io/money-warp/examples/time_machine/)
- [Present Value and IRR](https://tomascorrea.github.io/money-warp/examples/present_value_irr/)
- [Fines and Mora Interest](https://tomascorrea.github.io/money-warp/examples/fines/)
- [Tax and IOF](https://tomascorrea.github.io/money-warp/examples/tax/)
- [Timezone Handling](https://tomascorrea.github.io/money-warp/examples/timezone/)
- [Marshmallow Extension](https://tomascorrea.github.io/money-warp/examples/marshmallow/)
- [SQLAlchemy Extension](https://tomascorrea.github.io/money-warp/examples/sqlalchemy/)
- [API Reference](https://tomascorrea.github.io/money-warp/modules/)

## Contributing

Contributions are welcome! See the [Contributing Guide](CONTRIBUTING.rst) for details.

## License

MIT -- see [LICENSE](LICENSE).
