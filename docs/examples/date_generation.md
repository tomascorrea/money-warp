# Date Generation Utilities

MoneyWarp provides convenient date generation functions powered by `python-dateutil` for robust and intelligent date arithmetic.

## Why Date Generation Matters

Creating payment schedules manually is error-prone and tedious:

```python
# ❌ Manual date creation (error-prone)
from datetime import datetime, timedelta

start_date = datetime(2024, 1, 31)
due_dates = []
for i in range(12):
    # This breaks for months with different lengths!
    due_dates.append(start_date + timedelta(days=30*i))
```

MoneyWarp's date utilities handle edge cases automatically:

```python
# ✅ Smart date generation (robust)
from money_warp import generate_monthly_dates
from datetime import datetime

due_dates = generate_monthly_dates(datetime(2024, 1, 31), 12)
# Handles Feb 29, month lengths, leap years automatically!
```

## Available Functions

### Monthly Dates

Generate monthly payment schedules with intelligent end-of-month handling:

```python
from money_warp import generate_monthly_dates
from datetime import datetime

# Basic monthly dates
dates = generate_monthly_dates(datetime(2024, 1, 15), 12)
print(f"12 monthly payments starting Jan 15")

# End-of-month intelligence
eom_dates = generate_monthly_dates(datetime(2024, 1, 31), 4)
# Results: [Jan 31, Feb 29, Mar 29, Apr 29]
# Notice how it maintains consistency after February adjustment
```

### Bi-weekly Dates

Perfect for payroll-aligned payment schedules:

```python
from money_warp import generate_biweekly_dates

# 26 bi-weekly payments (roughly 1 year)
dates = generate_biweekly_dates(datetime(2024, 1, 1), 26)
print(f"Payment every 14 days")

# Great for matching payroll schedules
payroll_dates = generate_biweekly_dates(datetime(2024, 1, 5), 26)  # Fridays
```

### Weekly Dates

For high-frequency payment schedules:

```python
from money_warp import generate_weekly_dates

# Weekly payments for a year
dates = generate_weekly_dates(datetime(2024, 1, 1), 52)
print(f"52 weekly payments")
```

### Quarterly Dates

Business-friendly quarterly schedules:

```python
from money_warp import generate_quarterly_dates

# Quarterly payments
dates = generate_quarterly_dates(datetime(2024, 1, 15), 8)  # 2 years
print(f"Quarterly payments: Q1, Q2, Q3, Q4...")

# End-of-quarter example
quarter_end = generate_quarterly_dates(datetime(2024, 3, 31), 4)
# Results: [Mar 31, Jun 30, Sep 30, Dec 30]
# Smart handling of different quarter-end dates
```

### Annual Dates

For long-term loans and investments:

```python
from money_warp import generate_annual_dates

# 30-year mortgage payments
dates = generate_annual_dates(datetime(2024, 1, 1), 30)

# Leap year handling
leap_dates = generate_annual_dates(datetime(2024, 2, 29), 4)
# Results: [2024-02-29, 2025-02-28, 2026-02-28, 2027-02-28]
# Automatically adjusts for non-leap years
```

### Custom Intervals

For any custom payment frequency:

```python
from money_warp import generate_custom_interval_dates

# Every 45 days
dates = generate_custom_interval_dates(datetime(2024, 1, 1), 8, 45)

# Every 10 days (short-term financing)
short_term = generate_custom_interval_dates(datetime(2024, 1, 1), 12, 10)
```

## Integration with Loans

All date generation functions work seamlessly with MoneyWarp loans:

```python
from money_warp import Loan, Money, InterestRate, generate_monthly_dates
from datetime import datetime

# Generate payment dates
due_dates = generate_monthly_dates(datetime(2024, 1, 15), 24)

# Create loan with generated dates
loan = Loan(
    principal=Money("25000"),
    interest_rate=InterestRate("4.5% annual"),
    due_dates=due_dates
)

# Get payment schedule
schedule = loan.get_amortization_schedule()
print(f"Monthly payment: {schedule[0].payment_amount}")
```

## Edge Cases Handled

### End-of-Month Intelligence

```python
# Starting on January 31st
dates = generate_monthly_dates(datetime(2024, 1, 31), 6)

# Results:
# Jan 31 → Feb 29 (leap year, Feb has 29 days)
# Feb 29 → Mar 29 (maintains the adjusted day)
# Mar 29 → Apr 29 (consistent)
# Apr 29 → May 29 (consistent)
# May 29 → Jun 29 (consistent)

for i, date in enumerate(dates, 1):
    print(f"Payment {i}: {date} (day {date.day})")
```

### Leap Year Handling

```python
# Annual payments starting on leap day
leap_dates = generate_annual_dates(datetime(2024, 2, 29), 3)

# Results:
# 2024-02-29 (leap year)
# 2025-02-28 (not leap year, adjusted)
# 2026-02-28 (not leap year, maintains adjustment)
```

### Quarter-End Variations

```python
# Starting at end of March (31 days)
quarter_dates = generate_quarterly_dates(datetime(2024, 3, 31), 4)

# Results:
# Mar 31 → Jun 30 (June has 30 days, adjusted)
# Jun 30 → Sep 30 (maintains adjusted day)
# Sep 30 → Dec 30 (maintains adjusted day)
```

## Real-World Examples

### Mortgage with Monthly Payments

```python
from money_warp import Loan, Money, InterestRate, generate_monthly_dates
from datetime import datetime

# 30-year mortgage starting mid-month
start_date = datetime(2024, 1, 15)
payment_dates = generate_monthly_dates(start_date, 360)  # 30 years * 12 months

mortgage = Loan(
    principal=Money("400000"),  # $400k house
    interest_rate=InterestRate("6.5% annual"),
    due_dates=payment_dates
)

print(f"30-year mortgage with {len(payment_dates)} payments")
print(f"First payment: {payment_dates[0]}")
print(f"Final payment: {payment_dates[-1]}")
```

### Bi-weekly Auto Loan

```python
# Bi-weekly auto loan (pays off faster)
biweekly_dates = generate_biweekly_dates(datetime(2024, 1, 5), 130)  # ~5 years

auto_loan = Loan(
    principal=Money("35000"),
    interest_rate=InterestRate("7.2% annual"),
    due_dates=biweekly_dates
)

print(f"Bi-weekly auto loan: {len(biweekly_dates)} payments")
```

### Business Quarterly Loan

```python
# Business loan with quarterly payments
quarterly_dates = generate_quarterly_dates(datetime(2024, 3, 31), 20)  # 5 years

business_loan = Loan(
    principal=Money("100000"),
    interest_rate=InterestRate("8.5% annual"),
    due_dates=quarterly_dates
)

print(f"Business loan: {len(quarterly_dates)} quarterly payments")
```

## API Reference

### Function Signatures

```python
def generate_monthly_dates(start_date: datetime, num_payments: int) -> List[datetime]:
    """Generate monthly payment dates with smart end-of-month handling."""

def generate_biweekly_dates(start_date: datetime, num_payments: int) -> List[datetime]:
    """Generate bi-weekly payment dates (every 14 days)."""

def generate_weekly_dates(start_date: datetime, num_payments: int) -> List[datetime]:
    """Generate weekly payment dates (every 7 days)."""

def generate_quarterly_dates(start_date: datetime, num_payments: int) -> List[datetime]:
    """Generate quarterly payment dates (every 3 months)."""

def generate_annual_dates(start_date: datetime, num_payments: int) -> List[datetime]:
    """Generate annual payment dates (every 12 months)."""

def generate_custom_interval_dates(
    start_date: datetime, num_payments: int, interval_days: int
) -> List[datetime]:
    """Generate payment dates with custom day intervals."""
```

### Error Handling

All functions validate inputs and raise clear errors:

```python
# Invalid payment count
try:
    generate_monthly_dates(datetime(2024, 1, 1), 0)
except ValueError as e:
    print(e)  # "Number of payments must be positive"

# Invalid interval
try:
    generate_custom_interval_dates(datetime(2024, 1, 1), 5, -1)
except ValueError as e:
    print(e)  # "Interval days must be positive"
```

## Key Benefits

### Robust Date Arithmetic
- **Powered by python-dateutil**: Industry-standard date manipulation
- **Smart month handling**: Handles varying month lengths automatically
- **Leap year aware**: Correctly handles February 29th edge cases

### Simple API
- **Type-safe**: Full type annotations and validation
- **Minimal parameters**: Just `datetime` and `int`, no complex options
- **Consistent behavior**: All functions follow the same patterns

### Immediate Integration
- **Loan compatibility**: Generated dates work directly with `Loan` objects
- **Time Machine support**: All dates work with `Warp` for temporal analysis
- **Schedule generation**: Seamless integration with payment schedulers

MoneyWarp's date utilities eliminate the complexity and bugs of manual date arithmetic, letting you focus on financial modeling instead of calendar math!
