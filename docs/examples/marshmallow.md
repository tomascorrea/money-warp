# Marshmallow Extension

Custom Marshmallow fields for serializing and deserializing `Money`, `Rate`, and `InterestRate` objects.

## Installation

```bash
pip install money-warp[marshmallow]
```

## Fields

### MoneyField

Serializes `Money` instances. The `representation` parameter controls the format:

| Representation | Serialized type | Serialize logic | Deserialize logic |
|---|---|---|---|
| `"raw"` (default) | `str` | `str(money.raw_amount)` | `Money(value)` |
| `"real"` | `str` | `str(money.real_amount)` | `Money(value)` |
| `"cents"` | `int` | `money.cents` | `Money.from_cents(value)` |
| `"float"` | `float` | `float(money.real_amount)` | `Money(str(value))` |

### RateField

Serializes `Rate` instances. The `representation` parameter controls the format:

| Representation | Serialized type | Example output |
|---|---|---|
| `"string"` (default) | `str` | `"5.250% annual"` |
| `"dict"` | `dict` | `{"rate": "0.0525", "period": "annually", ...}` |

**String mode** outputs a parseable format that feeds directly back into `Rate(...)`. Field-level defaults (`year_size`, `precision`, `rounding`, `str_style`) are applied on deserialization.

**Dict mode** captures all constructor params (`rate`, `period`, `year_size`, `precision`, `rounding`, `str_style`) for lossless reconstruction.

### InterestRateField

Inherits from `RateField` with `RATE_CLASS = InterestRate`. Same representations, but constructs `InterestRate` on deserialization (rejects negative values).

## Usage

```python
from marshmallow import Schema
from money_warp import Money, InterestRate
from money_warp.ext.marshmallow import MoneyField, InterestRateField

class LoanSchema(Schema):
    principal = MoneyField(representation="raw")
    rate = InterestRateField(representation="string")

schema = LoanSchema()

# Serialize
data = schema.dump({"principal": Money("10000"), "rate": InterestRate("5.25% a")})
# {"principal": "10000", "rate": "5.250% annual"}

# Deserialize
result = schema.load(data)
# {"principal": Money(10000), "rate": InterestRate(5.25% annually)}
```

### Dict representation for lossless round-trips

```python
from money_warp.ext.marshmallow import RateField
from money_warp import Rate, CompoundingFrequency, YearSize

class DetailedSchema(Schema):
    rate = RateField(representation="dict")

schema = DetailedSchema()
rate = Rate(0.0525, CompoundingFrequency.ANNUALLY, year_size=YearSize.banker)

data = schema.dump({"rate": rate})
# {
#     "rate": {
#         "rate": "0.0525",
#         "period": "annually",
#         "year_size": 360,
#         "precision": None,
#         "rounding": "ROUND_HALF_UP",
#         "str_style": "long"
#     }
# }

restored = schema.load(data)
# Rate is fully reconstructed with all original parameters
```

### Cents representation for integer storage

```python
class PaymentSchema(Schema):
    amount = MoneyField(representation="cents")

schema = PaymentSchema()
data = schema.dump({"amount": Money("123.45")})
# {"amount": 12345}

result = schema.load(data)
# {"amount": Money("123.45")}
```

### Float representation for JSON-friendly APIs

```python
class ApiSchema(Schema):
    amount = MoneyField(representation="float")

schema = ApiSchema()
data = schema.dump({"amount": Money("123.45")})
# {"amount": 123.45}

result = schema.load(data)
# {"amount": Money("123.45")}
```

## Notes

- All fields pass `None` through in both directions.
- String round-trips lose some precision: the percentage rate is formatted with 3 decimal places. Use dict representation for rates with more than 3 decimal digits in percentage form.
- `InterestRateField` raises a validation error for negative rates.
