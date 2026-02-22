# Money & Precision

The `Money` class is the foundation of MoneyWarp, providing high-precision financial calculations while maintaining intuitive 2-decimal display for "real money" amounts.

## Why Precision Matters

Financial calculations require precision. Floating-point arithmetic can introduce errors:

```python
# The classic floating-point problem
print(0.1 + 0.2)  # 0.30000000000000004 😱

# With MoneyWarp
from money_warp import Money

money1 = Money("0.1")
money2 = Money("0.2")
result = money1 + money2
print(result)  # 0.30 ✅
```

## Creating Money Objects

Multiple ways to create `Money` objects:

```python
from money_warp import Money
from decimal import Decimal

# From strings (recommended for precision)
price = Money("99.99")
salary = Money("75000.00")

# From integers
count = Money(100)  # $100.00

# From Decimal (maintains precision)
precise = Money(Decimal("123.456789"))

# From floats (converted to string internally)
approx = Money(99.99)  # Converted to avoid float precision issues

print(f"Price: {price}")
print(f"Salary: {salary}")
print(f"Count: {count}")
print(f"Precise: {precise}")
print(f"Approx: {approx}")
```

**Output:**
```
Price: 99.99
Salary: 75,000.00
Count: 100.00
Precise: 123.46
Approx: 99.99
```

## Precision vs Display

MoneyWarp maintains full precision internally but displays 2 decimals:

```python
# High precision calculation
money = Money("100.123456789")

print(f"Internal (raw): {money.raw_amount}")    # Full precision
print(f"Display (real): {money.real_amount}")   # 2 decimals
print(f"String: {money}")                       # 2 decimals
```

**Output:**
```
Internal (raw): 100.123456789
Display (real): 100.12
String: 100.12
```

## Arithmetic Operations

All arithmetic maintains precision internally:

```python
base = Money("100.00")

# Basic operations
addition = base + Money("25.50")
subtraction = base - Money("15.75")
multiplication = base * 1.08  # 8% increase
division = base / 4

print(f"Addition: {addition}")
print(f"Subtraction: {subtraction}")
print(f"Multiplication: {multiplication}")
print(f"Division: {division}")

# Complex calculations
compound = Money("1000.00") * (1.05 ** 10)  # 5% for 10 years
print(f"Compound growth: {compound}")

# Chain operations
result = Money("500.00") * 1.08 / 12 * 365.25 / 100
print(f"Complex chain: {result}")
print(f"Internal precision: {result.raw_amount}")
```

**Output:**
```
Addition: 125.50
Subtraction: 84.25
Multiplication: 108.00
Division: 25.00
Compound growth: 1,628.89
Complex chain: 164.25
Internal precision: 164.2500000000000000000000000
```

## Comparison Operations

Comparisons use the 2-decimal "real money" representation. You can compare `Money` against another `Money` or directly against a `Decimal`:

```python
from decimal import Decimal

money1 = Money("100.001")  # Rounds to 100.00
money2 = Money("100.009")  # Rounds to 100.01

print(f"Money1: {money1}")  # 100.00
print(f"Money2: {money2}")  # 100.01

# Money vs Money
print(f"Equal? {money1 == money2}")           # False
print(f"Money1 < Money2? {money1 < money2}") # True
print(f"Money1 <= 100.00? {money1 <= Money('100.00')}")  # True

# Money vs Decimal -- no need to extract .real_amount
print(f"Equals Decimal? {money1 == Decimal('100.00')}")  # True
print(f"Greater than? {money2 > Decimal('100.00')}")     # True
```

## Working with Cents

Avoid decimal issues by working with cents:

```python
# Create from cents
price_in_cents = Money.from_cents(9999)  # $99.99
print(f"From cents: {price_in_cents}")

# Get cents value
money = Money("123.45")
cents = money.cents
print(f"As cents: {cents}")  # 12345

# Useful for APIs that work in cents
api_amount = Money.from_cents(2500)  # $25.00 from API
print(f"API amount: {api_amount}")
```

## Zero and Utility Methods

Convenient methods for common operations:

```python
# Zero money
zero = Money.zero()
print(f"Zero: {zero}")

# Check if zero
balance = Money("0.00")
print(f"Is zero? {balance.is_zero()}")

# Check sign
positive = Money("100.00")
negative = Money("-50.00")
print(f"Positive? {positive.is_positive()}")
print(f"Negative? {negative.is_negative()}")

# Absolute value
debt = Money("-1500.00")
print(f"Debt: {debt}")
print(f"Absolute: {abs(debt)}")
```

**Output:**
```
Zero: 0.00
Is zero? True
Positive? True
Negative? True
Debt: -1,500.00
Absolute: 1,500.00
```

## Real-World Example: Tax Calculations

```python
def calculate_tax_breakdown(gross_salary, tax_rate, deductions):
    """Calculate detailed tax breakdown with high precision."""
    
    gross = Money(gross_salary)
    rate = tax_rate
    deduct = Money(deductions)
    
    # Calculate taxable income
    taxable = gross - deduct
    
    # Calculate taxes (maintains precision)
    federal_tax = taxable * rate
    state_tax = taxable * 0.05  # 5% state tax
    total_tax = federal_tax + state_tax
    
    # Net income
    net_income = gross - total_tax
    
    return {
        'gross': gross,
        'deductions': deduct,
        'taxable': taxable,
        'federal_tax': federal_tax,
        'state_tax': state_tax,
        'total_tax': total_tax,
        'net_income': net_income,
        'effective_rate': (total_tax / gross) * 100
    }

# Calculate for $75,000 salary
breakdown = calculate_tax_breakdown("75000.00", 0.22, "12550.00")

print("Tax Breakdown:")
print(f"Gross Salary: {breakdown['gross']}")
print(f"Standard Deduction: {breakdown['deductions']}")
print(f"Taxable Income: {breakdown['taxable']}")
print(f"Federal Tax (22%): {breakdown['federal_tax']}")
print(f"State Tax (5%): {breakdown['state_tax']}")
print(f"Total Tax: {breakdown['total_tax']}")
print(f"Net Income: {breakdown['net_income']}")
print(f"Effective Rate: {breakdown['effective_rate']:.2f}%")
```

**Output:**
```
Tax Breakdown:
Gross Salary: 75,000.00
Standard Deduction: 12,550.00
Taxable Income: 62,450.00
Federal Tax (22%): 13,739.00
State Tax (5%): 3,122.50
Total Tax: 16,861.50
Net Income: 58,138.50
Effective Rate: 22.48%
```

## Performance Considerations

While `Money` uses `Decimal` for precision, it's optimized for financial calculations:

```python
import time
from money_warp import Money

# Benchmark Money operations
start = time.time()
total = Money.zero()
for i in range(10000):
    total += Money("1.23")
end = time.time()

print(f"10,000 additions: {end - start:.4f} seconds")
print(f"Final total: {total}")

# Memory efficiency
money = Money("123456789.123456789")
print(f"Memory efficient: {money}")  # Only stores one Decimal
```

## Best Practices

1. **Use strings for input**: `Money("99.99")` not `Money(99.99)`
2. **Leverage precision**: Internal calculations maintain full precision
3. **Display consistency**: All output shows 2 decimals automatically
4. **Comparison safety**: Comparisons use "real money" (2 decimal) values -- works with both `Money` and `Decimal`
5. **Zero handling**: Use `Money.zero()` and `.is_zero()` for clarity

## Common Patterns

```python
# Running totals
total = Money.zero()
transactions = [Money("100.00"), Money("-25.50"), Money("75.25")]
for transaction in transactions:
    total += transaction
print(f"Final balance: {total}")

# Percentage calculations
principal = Money("10000.00")
interest_rate = 0.05
interest = principal * interest_rate
print(f"Interest: {interest}")

# Splitting amounts
bill = Money("127.50")
people = 3
per_person = bill / people
print(f"Per person: {per_person}")

# Rounding behavior (automatic)
precise_calc = Money("100.00") / 3 * 3
print(f"Rounded result: {precise_calc}")  # Shows 100.00
print(f"Internal: {precise_calc.raw_amount}")  # Shows full precision
```

The `Money` class ensures your financial calculations are both precise and intuitive! 💰
