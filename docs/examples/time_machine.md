# Time Machine (Warp) Examples

**Core Philosophy:** *The loan is always time sensitive... it always filters based on present date regardless if it is warped or not... the warp just changes the present date.*

## Basic Time Travel

```python
from money_warp import Warp, Loan, Money, InterestRate
from datetime import datetime

# Create a loan
loan = Loan(
    Money("10000"), 
    InterestRate("5% annual"), 
    [datetime(2024, 1, 15), datetime(2024, 2, 15), datetime(2024, 3, 15)]
)

# Make some payments
loan.record_payment(Money("500"), datetime(2024, 1, 10), "Payment 1")
loan.record_payment(Money("600"), datetime(2024, 2, 10), "Payment 2") 
loan.record_payment(Money("700"), datetime(2024, 3, 10), "Payment 3")

print(f"Current balance: {loan.current_balance}")
# Current balance: 8,200.00 (approximately, after all payments)
```

## Warp to the Past

```python
# Travel back to January 20th - only first payment has been made
with Warp(loan, datetime(2024, 1, 20)) as past_loan:
    print(f"Balance on Jan 20: {past_loan.current_balance}")
    # Balance on Jan 20: 9,500.00 (approximately, only first payment applied)
    
    print(f"Payments made by Jan 20: {len(past_loan._actual_payments)}")
    # Payments made by Jan 20: 2 (interest + principal portions of first payment)
    
    # Time-dependent calculations use the warped date
    days_since = past_loan.days_since_last_payment()
    print(f"Days since last payment (from Jan 20): {days_since}")
    # Days since last payment (from Jan 20): 10 (Jan 20 - Jan 10)

# Original loan is unchanged
print(f"Back to present: {loan.current_balance}")
# Back to present: 8,200.00 (all payments still applied)
```

## Warp to the Future

```python
# Travel to the future - all payments are still visible
with Warp(loan, datetime(2025, 6, 15)) as future_loan:
    print(f"Balance in June 2025: {future_loan.current_balance}")
    # Balance in June 2025: 8,200.00 (same as present, no new payments)
    
    print(f"All payments made: {len(future_loan._actual_payments)}")
    # All payments made: 6 (all 3 payments × 2 components each)
    
    # Time calculations from the future perspective
    days_since = future_loan.days_since_last_payment()
    print(f"Days since last payment (from June 2025): {days_since}")
    # Days since last payment (from June 2025): ~460 days
```

## Flexible Date Formats

```python
# String dates (ISO format)
with Warp(loan, "2024-01-20") as warped:
    print(f"String date: {warped.current_balance}")

# datetime objects
with Warp(loan, datetime(2024, 1, 20, 14, 30)) as warped:
    print(f"Datetime object: {warped.current_balance}")

# date objects
from datetime import date
with Warp(loan, date(2024, 1, 20)) as warped:
    print(f"Date object: {warped.current_balance}")
```

## Safety Features

```python
# Nested warps are prevented
with Warp(loan, "2024-01-20") as outer_warp:
    try:
        with Warp(loan, "2024-02-20") as inner_warp:  # This will fail
            pass
    except NestedWarpError as e:
        print(f"Nested warp prevented: {e}")
        # Nested warp prevented: Nested Warp contexts are not allowed. 
        # Playing with time is dangerous enough with one level.

# Invalid dates are caught
try:
    with Warp(loan, "not-a-date") as warped:
        pass
except InvalidDateError as e:
    print(f"Invalid date caught: {e}")
    # Invalid date caught: Could not parse date 'not-a-date': ...
```

## Real-World Scenario: Payment Analysis

```python
# Analyze loan performance at different points in time
loan = Loan(Money("50000"), InterestRate("4.5% annual"), 
           [datetime(2024, i, 1) for i in range(1, 13)])  # Monthly payments

# Record some irregular payments
loan.record_payment(Money("4500"), datetime(2024, 1, 1), "On time")
loan.record_payment(Money("4500"), datetime(2024, 2, 5), "5 days late") 
loan.record_payment(Money("2000"), datetime(2024, 3, 1), "Partial payment")
loan.record_payment(Money("2500"), datetime(2024, 3, 15), "Catch up payment")

# Analyze at different points
analysis_dates = [
    datetime(2024, 1, 31),  # After first payment
    datetime(2024, 2, 28),  # After second payment  
    datetime(2024, 3, 31),  # After all March payments
]

for analysis_date in analysis_dates:
    with Warp(loan, analysis_date) as snapshot:
        print(f"\n=== Analysis as of {analysis_date.strftime('%B %Y')} ===")
        print(f"Outstanding balance: {snapshot.current_balance}")
        print(f"Payments made: {len(snapshot._actual_payments) // 2}")  # Divide by 2 for payment count
        print(f"Days since last payment: {snapshot.days_since_last_payment()}")
```

## Key Benefits

1. **Natural Time Filtering**: Loans automatically show the correct state for any date
2. **Safe Analysis**: Original loan data is never modified during time travel
3. **Instant Calculations**: All loan properties update automatically based on the warped time
4. **Flexible Integration**: Works seamlessly with existing loan methods and properties
5. **Error Prevention**: Built-in safeguards against nested warps and invalid dates

The Time Machine makes it trivial to analyze loan performance at any point in history or project future states based on current payment patterns.
