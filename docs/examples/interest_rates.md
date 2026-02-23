# Interest Rates

The `InterestRate` class eliminates confusion between decimal and percentage representations while providing safe conversions between different compounding frequencies.

## The Problem with Raw Numbers

Interest rates are confusing when represented as raw numbers:

```python
# Is this 5% or 500%? 🤔
rate = 0.05

# Is this 5% or 0.05%? 🤔  
rate = 5

# MoneyWarp makes it explicit
from money_warp import InterestRate

rate = InterestRate("5% a")  # Clearly 5% annually ✅
```

## Creating Interest Rates

Multiple clear formats supported:

```python
from money_warp import InterestRate, CompoundingFrequency

# String format (recommended)
annual = InterestRate("5.25% a")        # 5.25% annually
monthly = InterestRate("0.4375% m")     # 0.4375% monthly  
daily = InterestRate("0.0144% d")       # 0.0144% daily
quarterly = InterestRate("1.3125% q")   # 1.3125% quarterly

# Long form strings
annual_long = InterestRate("5.25% annual")
monthly_long = InterestRate("0.4375% monthly")

# Abbreviated notation (Brazilian/LatAm convention)
annual_abbrev = InterestRate("5.25% a.a.")    # ao ano
monthly_abbrev = InterestRate("0.4375% a.m.") # ao mês
daily_abbrev = InterestRate("0.0144% a.d.")   # ao dia
quarterly_abbrev = InterestRate("2.75% a.t.")  # ao trimestre
semi_annual_abbrev = InterestRate("3% a.s.")   # ao semestre

# Decimal format (explicit)
decimal_annual = InterestRate("0.0525 a")     # 5.25% as decimal
decimal_monthly = InterestRate("0.004375 m")  # 0.4375% as decimal

# Numeric with explicit frequency
numeric_rate = InterestRate(5.25, CompoundingFrequency.ANNUALLY, as_percentage=True)

print(f"Annual: {annual}")
print(f"Monthly: {monthly}")
print(f"Daily: {daily}")
print(f"Quarterly: {quarterly}")
```

**Output:**
```
Annual: 5.250% annually
Monthly: 0.438% monthly
Daily: 0.014% daily
Quarterly: 1.313% quarterly
```

## Accessing Rate Values

Safe access to decimal and percentage representations:

```python
rate = InterestRate("6.5% a")

print(f"As percentage: {rate.as_percentage}")  # 6.5
print(f"As decimal: {rate.as_decimal}")        # 0.065
print(f"Frequency: {rate.period}")             # CompoundingFrequency.ANNUALLY
print(f"Display: {rate}")                      # 6.500% annually
```

## Frequency Conversions

Convert between different compounding frequencies:

```python
# Start with annual rate
annual = InterestRate("6% a")

# Convert to other frequencies
monthly = annual.to_monthly()
daily = annual.to_daily()
quarterly = annual.to_quarterly()

print(f"Annual: {annual}")
print(f"Monthly equivalent: {monthly}")
print(f"Daily equivalent: {daily}")
print(f"Quarterly equivalent: {quarterly}")
```

**Output:**
```
Annual: 6.000% annually
Monthly equivalent: 0.487% monthly
Daily equivalent: 0.016% daily
Quarterly equivalent: 1.467% quarterly
```

## Understanding Effective vs Nominal Rates

MoneyWarp handles the conversion between nominal and effective rates:

```python
# Nominal 12% annual rate
nominal = InterestRate("12% a")

# What's the effective monthly rate?
monthly_effective = nominal.to_monthly()
print(f"Nominal annual: {nominal}")
print(f"Effective monthly: {monthly_effective}")

# Verify: 12 months of monthly rate should equal annual
annual_check = (1 + monthly_effective.as_decimal) ** 12 - 1
print(f"Verification: {annual_check:.6f} ≈ {nominal.as_decimal:.6f}")
```

**Output:**
```
Nominal annual: 12.000% annually
Effective monthly: 0.949% monthly
Verification: 0.120000 ≈ 0.120000
```

## Real-World Example: Credit Card APR

```python
def analyze_credit_card(balance, apr_string, monthly_payment):
    """Analyze credit card payoff with daily compounding."""
    
    from money_warp import Money
    
    balance = Money(balance)
    monthly_payment = Money(monthly_payment)
    
    # Credit cards typically compound daily
    apr = InterestRate(apr_string)
    daily_rate = apr.to_daily()
    
    print(f"Credit Card Analysis:")
    print(f"Balance: {balance}")
    print(f"APR: {apr}")
    print(f"Daily rate: {daily_rate}")
    print(f"Monthly payment: {monthly_payment}")
    print()
    
    # Calculate monthly interest (30 days)
    monthly_interest = balance * (daily_rate.as_decimal * 30)
    principal_payment = monthly_payment - monthly_interest
    
    print(f"Monthly breakdown:")
    print(f"  Interest (30 days): {monthly_interest}")
    print(f"  Principal: {principal_payment}")
    
    if principal_payment <= Money.zero():
        print("⚠️  Payment doesn't cover interest!")
        return
    
    # Estimate payoff time (simplified)
    months = 0
    current_balance = balance
    
    while current_balance > Money.zero() and months < 600:  # Max 50 years
        interest = current_balance * (daily_rate.as_decimal * 30)
        principal = monthly_payment - interest
        
        if principal <= Money.zero():
            break
            
        current_balance -= principal
        months += 1
        
        if current_balance < Money.zero():
            current_balance = Money.zero()
    
    print(f"Estimated payoff: {months} months ({months/12:.1f} years)")
    total_paid = monthly_payment * months
    total_interest = total_paid - balance
    print(f"Total paid: {total_paid}")
    print(f"Total interest: {total_interest}")

# Analyze a typical credit card scenario
analyze_credit_card("5000.00", "18.99% a", "150.00")
```

**Output:**
```
Credit Card Analysis:
Balance: 5,000.00
APR: 18.990% annually
Daily rate: 0.047% daily
Monthly payment: 150.00

Monthly breakdown:
  Interest (30 days): 78.95
  Principal: 71.05

Estimated payoff: 48 months (4.0 years)
Total paid: 7,200.00
Total interest: 2,200.00
```

## Mortgage Rate Comparisons

```python
def compare_mortgage_rates(principal, loan_term_years, rates):
    """Compare different mortgage rates."""
    
    from money_warp import Money, Loan
    from datetime import datetime, timedelta
    
    principal = Money(principal)
    
    print(f"Mortgage Comparison - {principal} over {loan_term_years} years")
    print("=" * 60)
    
    # Generate monthly payment schedule
    start_date = datetime(2024, 1, 1)
    num_payments = loan_term_years * 12
    due_dates = [start_date + timedelta(days=30*i) for i in range(1, num_payments + 1)]
    
    results = []
    
    for rate_str in rates:
        rate = InterestRate(rate_str)
        loan = Loan(principal, rate, due_dates)
        schedule = loan.get_amortization_schedule()
        
        monthly_payment = schedule[0].payment_amount
        total_interest = schedule.total_interest
        total_paid = schedule.total_payments
        
        results.append({
            'rate': rate,
            'monthly_payment': monthly_payment,
            'total_interest': total_interest,
            'total_paid': total_paid
        })
        
        print(f"{rate_str:>8} | {monthly_payment:>10} | {total_interest:>12} | {total_paid:>12}")
    
    # Find best rate
    best = min(results, key=lambda x: x['total_interest'])
    worst = max(results, key=lambda x: x['total_interest'])
    savings = worst['total_interest'] - best['total_interest']
    
    print("=" * 60)
    print(f"Best rate: {best['rate']} saves {savings} vs worst rate")

# Compare common mortgage rates
rates = ["3.5% a", "4.0% a", "4.5% a", "5.0% a", "5.5% a"]
compare_mortgage_rates("300000.00", 30, rates)
```

## High-Frequency Trading Example

```python
def calculate_compound_returns(principal, daily_rate_pct, days):
    """Calculate returns with daily compounding."""
    
    from money_warp import Money
    
    principal = Money(principal)
    daily_rate = InterestRate(f"{daily_rate_pct}% d")
    
    print(f"Compound Growth Analysis:")
    print(f"Principal: {principal}")
    print(f"Daily rate: {daily_rate}")
    print(f"Period: {days} days")
    print()
    
    # Calculate compound growth
    growth_factor = (1 + daily_rate.as_decimal) ** days
    final_amount = principal * growth_factor
    total_return = final_amount - principal
    
    # Convert to annual equivalent
    annual_equivalent = InterestRate(
        float((growth_factor ** (365/days)) - 1), 
        CompoundingFrequency.ANNUALLY, 
        as_percentage=False
    )
    
    print(f"Final amount: {final_amount}")
    print(f"Total return: {total_return}")
    print(f"Return percentage: {(total_return / principal) * 100:.2f}%")
    print(f"Annualized rate: {annual_equivalent}")

# Example: 0.1% daily return over 100 days
calculate_compound_returns("10000.00", "0.1", 100)
```

## Custom Periodic Rates

```python
# For non-standard periods
rate = InterestRate("8% a")

# Convert to any period (e.g., weekly = 52 periods per year)
weekly_rate = rate.to_periodic_rate(52)
print(f"Weekly rate: {weekly_rate:.6f}")

# Bi-weekly (26 periods per year)
biweekly_rate = rate.to_periodic_rate(26)
print(f"Bi-weekly rate: {biweekly_rate:.6f}")

# Custom: every 45 days (365/45 ≈ 8.11 periods per year)
custom_periods = 365 / 45
custom_rate = rate.to_periodic_rate(custom_periods)
print(f"45-day rate: {custom_rate:.6f}")
```

## Rate Validation and Error Handling

```python
try:
    # Invalid format
    bad_rate = InterestRate("5% x")  # 'x' is not a valid frequency
except ValueError as e:
    print(f"Error: {e}")

try:
    # Missing frequency for numeric input
    bad_rate = InterestRate(0.05)  # No frequency specified
except ValueError as e:
    print(f"Error: {e}")

# Valid alternatives
good_rate1 = InterestRate(0.05, CompoundingFrequency.ANNUALLY, as_percentage=False)
good_rate2 = InterestRate(5, CompoundingFrequency.ANNUALLY, as_percentage=True)
good_rate3 = InterestRate("5% a")  # Recommended

print(f"All equivalent: {good_rate1} = {good_rate2} = {good_rate3}")
```

## Abbreviated Notation (str_style)

MoneyWarp supports abbreviated period labels commonly used in Brazilian and Latin American finance. The `str_style` parameter controls how `__str__` renders the period:

| Frequency | Long (`"long"`) | Abbreviated (`"abbrev"`) |
|---|---|---|
| Annually | `5.250% annually` | `5.250% a.a.` |
| Monthly | `0.500% monthly` | `0.500% a.m.` |
| Daily | `0.014% daily` | `0.014% a.d.` |
| Quarterly | `2.750% quarterly` | `2.750% a.t.` |
| Semi-annually | `3.000% semi_annually` | `3.000% a.s.` |

### Auto-detection from string input

When you parse a string that uses abbreviated tokens, the style is set automatically:

```python
rate = InterestRate("5.25% a.a.")
print(rate)  # "5.250% a.a." — round-trips without extra config
```

### Explicit style on numeric rates

For rates created from numbers, pass `str_style="abbrev"`:

```python
rate = InterestRate(
    1.5, CompoundingFrequency.MONTHLY,
    as_percentage=True, str_style="abbrev",
)
print(rate)  # "1.500% a.m."
```

### Style propagates through conversions

Converting a rate preserves its display style:

```python
annual = InterestRate("6% a.a.")
monthly = annual.to_monthly()
daily = annual.to_daily()

print(annual)   # "6.000% a.a."
print(monthly)  # "0.487% a.m."
print(daily)    # "0.016% a.d."
```

## Best Practices

1. **Use string format**: `InterestRate("5.25% a")` is clearest
2. **Be explicit**: Always specify frequency (a/m/d/q/s or a.a./a.m./a.d./a.t./a.s.)
3. **Convert appropriately**: Match compounding to your calculation needs
4. **Validate inputs**: Handle user input with try/catch
5. **Document assumptions**: Make compounding frequency clear in your code
6. **Use abbreviated notation** when integrating with Brazilian/LatAm financial systems

## Common Patterns

```python
# Reading rates from configuration
config_rates = {
    'savings': "0.5% a",
    'checking': "0.01% a", 
    'mortgage': "4.25% a",
    'credit_card': "18.99% a"
}

rates = {name: InterestRate(rate_str) for name, rate_str in config_rates.items()}

# Comparing rates (convert to same frequency)
annual_rates = {name: rate.to_annual() for name, rate in rates.items()}
for name, rate in annual_rates.items():
    print(f"{name}: {rate}")

# Finding the best rate
best_savings = max(rates['savings'], rates['checking'], key=lambda r: r.as_decimal)
print(f"Best savings rate: {best_savings}")
```

Interest rates are now type-safe and crystal clear! 📈
