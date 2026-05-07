# Percentages

The `Percentage` class represents a non-negative percentage applied flat over a value, with **no temporal dimension** and **no compounding**. It is the right type for fees, fines, MDR, IOF flat components, and any percentage where the operation is `valor × taxa` and ends there.

## Why a separate type?

`Rate` and `InterestRate` model rates with a temporal dimension — they have a `period` and support conversions between periodicities (`to_daily`, `to_monthly`, `to_annual`). A flat percentage does **not** belong in those types:

| Concept | Has time dimension? | Compounds? | Example |
|---|---|---|---|
| `Rate` / `InterestRate` | Yes | Yes | `"5% a.a."` (annual interest) |
| `Percentage` | **No** | **No** | `"5%"` (MDR, multa, fee) |

If you store a flat percentage as `InterestRate("5% a.m.")` (a common workaround), any later call to `.to_annual()` or `.accrue()` produces a silently wrong number — the type checker won't catch it. `Percentage` exists to remove that footgun: it physically does not expose those methods.

## Construction is string-only

`Percentage` only accepts strings of the form `"<number>%"`. Numeric inputs and bare strings without `%` are rejected on purpose:

```python
from money_warp import Percentage

# OK
Percentage("5%")          # 5%
Percentage("5.5%")        # 5.5%
Percentage("0.5%")        # 0.5%
Percentage("0%")          # 0% (no fee)
Percentage("100%")        # 100%

# Rejected
Percentage(5)             # TypeError
Percentage(0.05)          # TypeError
Percentage("5")           # ValueError — missing '%'
Percentage("0.05")        # ValueError — missing '%'
Percentage("-5%")         # ValueError — negative not allowed
Percentage("5% a.a.")     # ValueError — temporal suffix → use Rate/InterestRate
Percentage("5% monthly")  # ValueError — same reason
```

The reason for rejecting numeric inputs is the classic ambiguity: when someone writes `Percentage(5)`, you cannot tell if they mean `5%` or `500%`. The literal `%` in the string is the only unambiguous contract.

## API: as_decimal and as_percentage

`Percentage` exposes only two accessors. There is no `apply(money)`, no `as_float`, no `to_*`, no `accrue` — those would all imply semantics the type does not have.

```python
from money_warp import Percentage
from decimal import Decimal

mdr = Percentage("5%")

mdr.as_decimal()     # Decimal('0.05')
mdr.as_percentage()  # Decimal('5')

# Optional precision argument
high_precision = Percentage("6.123%")
high_precision.as_decimal()    # Decimal('0.06123')
high_precision.as_decimal(2)   # Decimal('0.06')  (rounded)
high_precision.as_percentage(2)  # Decimal('6.12')

# Constructor-level precision applies as default
fixed = Percentage("6.123%", precision=2)
fixed.as_decimal()    # Decimal('0.06')

# String form (canonical: 2 decimals by default)
str(Percentage("5%"))                    # '5.00%'
str(Percentage("5%", str_decimals=4))    # '5.0000%'
str(Percentage("5%", str_decimals=0))    # '5%'

# Round-trip (stable within the configured str_decimals)
p = Percentage("5%")
Percentage(str(p)) == p                  # True

# High-precision values: increase str_decimals to keep the round-trip lossless
hp = Percentage("6.123%", str_decimals=4)
Percentage(str(hp), str_decimals=4) == hp  # True ('6.1230%')

# Default str_decimals=2 truncates beyond 2 places (rounded via ROUND_HALF_UP)
str(Percentage("6.129%"))                # '6.13%'
```

## Applying a percentage to Money

`Percentage` does not include an `apply(money)` method. The consumer does the multiplication explicitly so the boundary between "I have a percentage" and "I'm computing a fee in money" stays visible:

```python
from money_warp import Money, Percentage

mdr = Percentage("5%")
amount = Money("1000")

fee = Money(amount.raw_amount * mdr.as_decimal())
print(fee)  # 50.00
```

This pattern works for any value-based fee:

```python
# Late-payment fine over an overdue installment
fine_rate = Percentage("2%")
overdue = Money("450")
fine = Money(overdue.raw_amount * fine_rate.as_decimal())  # 9.00

# IOF flat component
iof_flat_rate = Percentage("0.38%")
principal = Money("10000")
iof_flat = Money(principal.raw_amount * iof_flat_rate.as_decimal())  # 38.00
```

## Comparisons

`Percentage` supports `==`, `<`, `<=`, `>`, `>=` and is hashable. Equality has a small tolerance to make equal-by-value percentages compare equal regardless of construction precision:

```python
from money_warp import Percentage

Percentage("5%") == Percentage("5.00%")         # True
Percentage("5%") < Percentage("6%")             # True
Percentage("5%") <= Percentage("5%")            # True

{Percentage("5%"), Percentage("5.00%")}         # set with 1 element

# Cross-type comparisons return NotImplemented (==) or fail (ordering),
# because Percentage and Rate live in different semantic dimensions.
from money_warp import Rate
Percentage("5%") == Rate("5% a.a.")             # False
# Percentage("5%") < Rate("5% a.a.")            # raises (cannot compare)
```

## Decision table: which type?

| Case | Type | Justification |
|---|---|---|
| MDR (partner rate) | `Percentage` | Applied once over the operation amount. No capitalization, no period. |
| Fine (`fine_rate`, multa) | `Percentage` | Applied once over the overdue amount. No capitalization. |
| IOF flat component | `Percentage` | Percentage applied once over the value. |
| Contractual interest rate | `InterestRate` | Has a temporal dimension, capitalizes, ≥ 0. |
| Late-payment interest rate | `InterestRate` | Capitalizes over days of delay. |
| IRR / MIRR (computed) | `Rate` | Computed metric, may be negative, has a temporal dimension. |

Practical rule: **if the operation you want to do with the "rate" is `valor × taxa` and ends there, it is `Percentage`**. If it involves time (accrual, conversion between periodicities, capitalization), it is `Rate` / `InterestRate`.

## Serialization

`Percentage` integrates with the same extensions as `Rate` and `InterestRate`:

```python
# Marshmallow
from money_warp.ext.marshmallow import PercentageField
from marshmallow import Schema

class FeeSchema(Schema):
    mdr = PercentageField()

FeeSchema().dump({"mdr": Percentage("5%")})    # {"mdr": "5.00%"}
FeeSchema().load({"mdr": "5.00%"})             # {"mdr": Percentage('5.00%')}

# SQLAlchemy
from money_warp.ext.sa import PercentageType
from sqlalchemy import Column, Integer
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase): ...

class PartnerFee(Base):
    __tablename__ = "partner_fees"
    id = Column(Integer, primary_key=True)
    mdr = Column(PercentageType())  # stored as String("5.00%")
```

Both extensions delegate validation to the `Percentage` constructor, so invalid inputs (numeric, missing `%`, temporal suffix, negative) raise on load and never poison the in-memory model.
