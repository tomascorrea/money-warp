# SQLAlchemy Extension

Custom SQLAlchemy column types for `Money`, `Rate`, and `InterestRate`, plus bridge decorators that add SQL-queryable `balance_at(date)` to loan models.

## Installation

```bash
pip install money-warp[sa]
```

## Column Types

### MoneyType

Stores `Money` instances:

```python
MoneyType(precision=20, scale=10, representation="raw")
```

- `representation` controls the storage format (see table below).
- `precision` and `scale` set the `Numeric` column dimensions. Ignored when `representation="cents"` (uses `Integer`).

| Representation | Column type | Bind (Money -> DB) | Result (DB -> Money) |
|---|---|---|---|
| `"raw"` (default) | `Numeric(precision, scale)` | `money.raw_amount` | `Money(value)` |
| `"real"` | `Numeric(precision, scale)` | `money.real_amount` | `Money(value)` |
| `"cents"` | `Integer` | `money.cents` | `Money.from_cents(value)` |

`process_bind_param` also accepts raw `Decimal`/`int`/`float` values (passthrough) so that SQL comparisons like `LoanRecord.balance > Decimal("1000")` work without wrapping in `Money`.

### RateType

Stores `Rate` instances. The `representation` parameter controls the column type and conversion:

| Representation | Column type | Example stored value |
|---|---|---|
| `"string"` (default) | `String` | `"5.250% annual"` |
| `"json"` | `JSON` | `{"rate": "0.0525", "period": "annually", ...}` |

Additional constructor parameters (`year_size`, `precision`, `rounding`, `str_style`) control defaults for string deserialization.

### InterestRateType

Subclass of `RateType` with `RATE_CLASS = InterestRate`. Same representations, but constructs `InterestRate` on load (rejects negative values).

## Bridge Decorators

The bridge system connects SQLAlchemy models to money-warp's Loan engine, providing both Python-side and SQL-side balance calculations.

### @settlement_bridge

Marks a settlement model with column metadata so that `@loan_bridge` can discover which columns hold the remaining balance, payment date, and amount:

```python
from money_warp.ext.sa import settlement_bridge, MoneyType

@settlement_bridge()
class SettlementRecord(Base):
    __tablename__ = "settlements"
    id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("loans.id"))
    amount = Column(MoneyType())
    payment_date = Column(DateTime)
    remaining_balance = Column(MoneyType())
    interest_date = Column(DateTime, nullable=True)
    processing_date = Column(DateTime, nullable=True)
```

All parameters have sensible defaults. `@settlement_bridge()` with no arguments works if your columns follow the naming convention.

### @loan_bridge

Adds `balance_at(date)` hybrid method and `balance` hybrid property to a loan model:

```python
from money_warp.ext.sa import loan_bridge, MoneyType, InterestRateType

@loan_bridge()
class LoanRecord(Base):
    __tablename__ = "loans"
    id = Column(Integer, primary_key=True)
    principal = Column(MoneyType())
    interest_rate = Column(InterestRateType(representation="json"))
    disbursement_date = Column(DateTime)
    due_dates = Column(JSON)  # JSON array of ISO dates; bridge loads as list[date] for Loan
    fine_rate = Column(InterestRateType(representation="json"), nullable=True)
    grace_period_days = Column(Integer(), nullable=True)
    mora_interest_rate = Column(InterestRateType(representation="json"), nullable=True)
    mora_strategy = Column(String(), nullable=True)
    settlements = relationship("SettlementRecord", order_by="SettlementRecord.payment_date")
```

All parameter names default to conventional column names. `@loan_bridge()` with no arguments works if you follow the naming convention.

## balance_at(date)

The hybrid method works differently on instances vs queries:

**Python side** -- reconstructs a full `Loan` from the model's stored fields, replays settlements, and uses `Warp(loan, as_of)` to return the exact balance including accrued interest, fines, and mora:

```python
loan = session.get(LoanRecord, 1)
balance = loan.balance_at(some_date)  # Returns Money
```

**SQL side** -- generates a CTE-based expression that computes `principal_balance + regular_interest + mora_interest + fines` entirely in SQL:

```python
from sqlalchemy import select
from decimal import Decimal

high_balance_loans = session.execute(
    select(LoanRecord).where(LoanRecord.balance_at(some_date) > Decimal("5000"))
).scalars().all()
```

The `balance` property is a shortcut for `balance_at(now())`.

## Rate Representation Support

Both `"json"` and `"string"` representations are fully supported in the SQL balance expression. The bridge introspects the column's `InterestRateType` at expression-build time to determine the storage format and generates the correct SQL accordingly.

### JSON representation

Stores the full rate object with `rate`, `period`, `year_size`, and metadata. The SQL expression extracts these fields with `json_extract` and performs the conversion:

```python
interest_rate = Column(InterestRateType(representation="json"))
# Stored as: {"rate": "0.05", "period": "annually", "year_size": 365, ...}
```

### String representation

Stores a parseable string like `"5.000% annual"`. The SQL expression parses this with `SUBSTR`/`INSTR` and uses the column type's `rate_year_size` default:

```python
interest_rate = Column(InterestRateType(representation="string"))
# Stored as: "5.000% annual"
```

!!! note "String format limitations"
    The string format does not embed `year_size`. The SQL helpers use the `rate_year_size` from the column's `InterestRateType` definition. If different rates on the same column need different year sizes, use JSON representation instead. `CompoundingFrequency.CONTINUOUS` cannot be serialized as a string.

## Full Example

```python
from datetime import datetime
from decimal import Decimal
from sqlalchemy import Column, Integer, DateTime, JSON, Numeric, String, ForeignKey
from sqlalchemy import create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, relationship
from money_warp import Money, InterestRate
from money_warp.ext.sa import MoneyType, InterestRateType, settlement_bridge, loan_bridge

class Base(DeclarativeBase):
    pass

@settlement_bridge()
class Settlement(Base):
    __tablename__ = "settlements"
    id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("loans.id"))
    amount = Column(MoneyType())
    payment_date = Column(DateTime)
    remaining_balance = Column(MoneyType())

@loan_bridge()
class Loan(Base):
    __tablename__ = "loans"
    id = Column(Integer, primary_key=True)
    principal = Column(MoneyType())
    interest_rate = Column(InterestRateType(representation="json"))
    disbursement_date = Column(DateTime)
    due_dates = Column(JSON)  # ISO date strings -> list[date] when building Loan
    settlements = relationship("Settlement", order_by="Settlement.payment_date")

engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)

with Session(engine) as session:
    # Instance access returns Money
    loan = session.get(Loan, 1)
    print(loan.balance)  # Money("8500.00")

    # SQL queries work too
    overdue = session.execute(
        select(Loan).where(Loan.balance > Decimal("5000"))
    ).scalars().all()
```

## Notes

- All type fields pass `None` through in both directions.
- SQLite stores `Numeric` as floating-point internally. Very high-precision amounts may lose precision; use PostgreSQL or MySQL for production.
- The SQL expression returns raw `Numeric`, not `Money`. Filter comparisons use `Decimal`: `LoanRecord.balance > Decimal("1000")`.
- SQL arithmetic uses float64 while Python uses `Decimal`. Use approximate matching (`pytest.approx`) when comparing SQL results against Python in tests.
