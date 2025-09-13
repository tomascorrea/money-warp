# Cash Flow Analysis

MoneyWarp treats all financial activities as cash flows through time. The `CashFlow` and `CashFlowItem` classes provide powerful tools for modeling, analyzing, and querying financial transactions.

## Basic Cash Flow Concepts

A cash flow is a collection of monetary movements over time:

```python
from datetime import datetime
from money_warp import CashFlow, CashFlowItem, Money

# Create individual transactions
transactions = [
    CashFlowItem(Money("1000.00"), datetime(2024, 1, 1), "Initial deposit", "deposit"),
    CashFlowItem(Money("-50.00"), datetime(2024, 1, 15), "Monthly fee", "fee"),
    CashFlowItem(Money("25.00"), datetime(2024, 2, 1), "Interest earned", "interest"),
    CashFlowItem(Money("-200.00"), datetime(2024, 2, 15), "Withdrawal", "withdrawal"),
    CashFlowItem(Money("30.00"), datetime(2024, 3, 1), "Interest earned", "interest"),
]

# Create cash flow
cash_flow = CashFlow(transactions)

print(f"Total transactions: {len(cash_flow)}")
print(f"Net cash flow: {cash_flow.sum()}")
print(f"Date range: {cash_flow.start_date()} to {cash_flow.end_date()}")
```

**Output:**
```
Total transactions: 5
Net cash flow: 805.00
Date range: 2024-01-01 00:00:00 to 2024-03-01 00:00:00
```

## CashFlowItem Details

Each transaction captures essential information:

```python
# Create a detailed transaction
transaction = CashFlowItem(
    amount=Money("-1250.00"),
    datetime=datetime(2024, 6, 15, 14, 30),  # Specific time
    description="Rent payment for June",
    category="housing"
)

print(f"Amount: {transaction.amount}")
print(f"Date/Time: {transaction.datetime}")
print(f"Description: {transaction.description}")
print(f"Category: {transaction.category}")
print(f"Is outflow? {transaction.is_outflow()}")
print(f"Is inflow? {transaction.is_inflow()}")

# String representation
print(f"Transaction: {transaction}")
```

**Output:**
```
Amount: -1,250.00
Date/Time: 2024-06-15 14:30:00
Description: Rent payment for June
Category: housing
Is outflow? True
Is inflow? False
Transaction: -1,250.00 on 2024-06-15 14:30:00: Rent payment for June (housing)
```

## Powerful Querying with CashFlowQuery

MoneyWarp provides SQLAlchemy-style querying for cash flows:

```python
# Sample data: Personal finance for 3 months
personal_transactions = [
    # January
    CashFlowItem(Money("5000.00"), datetime(2024, 1, 1), "Salary", "income"),
    CashFlowItem(Money("-1200.00"), datetime(2024, 1, 1), "Rent", "housing"),
    CashFlowItem(Money("-300.00"), datetime(2024, 1, 5), "Groceries", "food"),
    CashFlowItem(Money("-150.00"), datetime(2024, 1, 10), "Utilities", "utilities"),
    CashFlowItem(Money("-80.00"), datetime(2024, 1, 15), "Gas", "transportation"),
    
    # February  
    CashFlowItem(Money("5000.00"), datetime(2024, 2, 1), "Salary", "income"),
    CashFlowItem(Money("-1200.00"), datetime(2024, 2, 1), "Rent", "housing"),
    CashFlowItem(Money("-280.00"), datetime(2024, 2, 8), "Groceries", "food"),
    CashFlowItem(Money("-120.00"), datetime(2024, 2, 12), "Utilities", "utilities"),
    CashFlowItem(Money("-90.00"), datetime(2024, 2, 18), "Gas", "transportation"),
    CashFlowItem(Money("-500.00"), datetime(2024, 2, 20), "Car repair", "transportation"),
    
    # March
    CashFlowItem(Money("5000.00"), datetime(2024, 3, 1), "Salary", "income"),
    CashFlowItem(Money("-1200.00"), datetime(2024, 3, 1), "Rent", "housing"),
    CashFlowItem(Money("-320.00"), datetime(2024, 3, 7), "Groceries", "food"),
    CashFlowItem(Money("-140.00"), datetime(2024, 3, 11), "Utilities", "utilities"),
    CashFlowItem(Money("-75.00"), datetime(2024, 3, 16), "Gas", "transportation"),
]

personal_cf = CashFlow(personal_transactions)

# Query by category
income = personal_cf.query.filter_by(category="income")
housing = personal_cf.query.filter_by(category="housing") 
food = personal_cf.query.filter_by(category="food")

print("Spending by Category:")
print(f"Income: {income.sum()}")
print(f"Housing: {housing.sum()}")
print(f"Food: {food.sum()}")
print(f"Transportation: {personal_cf.query.filter_by(category='transportation').sum()}")
print(f"Utilities: {personal_cf.query.filter_by(category='utilities').sum()}")
```

**Output:**
```
Spending by Category:
Income: 15,000.00
Housing: -3,600.00
Food: -900.00
Transportation: -745.00
Utilities: -410.00
```

## Date-Based Filtering

Query cash flows by date ranges:

```python
# Filter by specific month
february = personal_cf.query.filter_by(
    datetime__gte=datetime(2024, 2, 1),
    datetime__lt=datetime(2024, 3, 1)
)

print(f"February transactions: {len(february.all())}")
print(f"February net: {february.sum()}")

# Filter recent transactions (last 30 days from March 1)
recent_cutoff = datetime(2024, 2, 1)  # 30 days before March 1
recent = personal_cf.query.filter_by(datetime__gte=recent_cutoff)

print(f"Recent transactions: {len(recent.all())}")
print(f"Recent net: {recent.sum()}")

# Combine filters: Food expenses in February
feb_food = personal_cf.query.filter_by(
    category="food",
    datetime__gte=datetime(2024, 2, 1),
    datetime__lt=datetime(2024, 3, 1)
)

print(f"February food spending: {feb_food.sum()}")
```

## Advanced Query Operations

```python
# Multiple categories
essential_categories = ["housing", "food", "utilities"]
essentials = personal_cf.query.filter_by(category__in=essential_categories)
print(f"Essential expenses: {essentials.sum()}")

# Exclude categories  
non_income = personal_cf.query.exclude(category="income")
print(f"Total expenses: {non_income.sum()}")

# Amount-based filtering
large_expenses = personal_cf.query.filter_by(amount__lt=Money("-200.00"))
print(f"Large expenses (>$200): {large_expenses.sum()}")

# Get specific items
all_transactions = personal_cf.query.all()
first_transaction = personal_cf.query.first()
print(f"First transaction: {first_transaction}")
```

## Real-World Example: Investment Portfolio Analysis

```python
def analyze_investment_portfolio():
    """Analyze a diversified investment portfolio."""
    
    # Portfolio transactions over 1 year
    portfolio_transactions = [
        # Initial investments (January)
        CashFlowItem(Money("-10000.00"), datetime(2024, 1, 15), "S&P 500 ETF", "stocks"),
        CashFlowItem(Money("-5000.00"), datetime(2024, 1, 15), "Bond ETF", "bonds"),
        CashFlowItem(Money("-2000.00"), datetime(2024, 1, 15), "REIT ETF", "reits"),
        
        # Quarterly dividends
        CashFlowItem(Money("125.00"), datetime(2024, 3, 31), "S&P 500 dividend", "dividends"),
        CashFlowItem(Money("87.50"), datetime(2024, 3, 31), "Bond dividend", "dividends"),
        CashFlowItem(Money("45.00"), datetime(2024, 3, 31), "REIT dividend", "dividends"),
        
        CashFlowItem(Money("130.00"), datetime(2024, 6, 30), "S&P 500 dividend", "dividends"),
        CashFlowItem(Money("90.00"), datetime(2024, 6, 30), "Bond dividend", "dividends"),
        CashFlowItem(Money("48.00"), datetime(2024, 6, 30), "REIT dividend", "dividends"),
        
        CashFlowItem(Money("135.00"), datetime(2024, 9, 30), "S&P 500 dividend", "dividends"),
        CashFlowItem(Money("92.50"), datetime(2024, 9, 30), "Bond dividend", "dividends"),
        CashFlowItem(Money("50.00"), datetime(2024, 9, 30), "REIT dividend", "dividends"),
        
        CashFlowItem(Money("140.00"), datetime(2024, 12, 31), "S&P 500 dividend", "dividends"),
        CashFlowItem(Money("95.00"), datetime(2024, 12, 31), "Bond dividend", "dividends"),
        CashFlowItem(Money("52.00"), datetime(2024, 12, 31), "REIT dividend", "dividends"),
        
        # Rebalancing (mid-year)
        CashFlowItem(Money("-1000.00"), datetime(2024, 7, 15), "Additional S&P investment", "stocks"),
        
        # Year-end values (theoretical sales)
        CashFlowItem(Money("12100.00"), datetime(2024, 12, 31), "S&P 500 value", "stocks"),
        CashFlowItem(Money("5150.00"), datetime(2024, 12, 31), "Bond value", "bonds"),
        CashFlowItem(Money("2080.00"), datetime(2024, 12, 31), "REIT value", "reits"),
    ]
    
    portfolio = CashFlow(portfolio_transactions)
    
    # Analysis by asset class
    print("Portfolio Analysis:")
    print("=" * 50)
    
    stocks = portfolio.query.filter_by(category="stocks")
    bonds = portfolio.query.filter_by(category="bonds")
    reits = portfolio.query.filter_by(category="reits")
    dividends = portfolio.query.filter_by(category="dividends")
    
    print(f"Stocks net: {stocks.sum()}")
    print(f"Bonds net: {bonds.sum()}")
    print(f"REITs net: {reits.sum()}")
    print(f"Total dividends: {dividends.sum()}")
    print(f"Portfolio net: {portfolio.sum()}")
    
    # Calculate returns
    initial_investment = Money("17000.00")  # 10k + 5k + 2k
    additional_investment = Money("1000.00")
    total_invested = initial_investment + additional_investment
    final_value = Money("19330.00")  # 12.1k + 5.15k + 2.08k
    total_dividends = dividends.sum()
    
    capital_gains = final_value - total_invested
    total_return = capital_gains + total_dividends
    return_percentage = (total_return / total_invested) * 100
    
    print(f"\nReturn Analysis:")
    print(f"Total invested: {total_invested}")
    print(f"Final value: {final_value}")
    print(f"Capital gains: {capital_gains}")
    print(f"Dividend income: {total_dividends}")
    print(f"Total return: {total_return}")
    print(f"Return percentage: {return_percentage:.2f}%")
    
    # Monthly dividend analysis
    monthly_dividends = {}
    for item in dividends.all():
        month_key = item.datetime.strftime("%Y-%m")
        if month_key not in monthly_dividends:
            monthly_dividends[month_key] = Money.zero()
        monthly_dividends[month_key] += item.amount
    
    print(f"\nQuarterly Dividend Income:")
    for month, amount in monthly_dividends.items():
        print(f"{month}: {amount}")

analyze_investment_portfolio()
```

## Business Cash Flow Analysis

```python
def analyze_business_cash_flow():
    """Analyze business cash flow with seasonal patterns."""
    
    # Small business cash flow (quarterly data)
    business_transactions = [
        # Q1 - Slow season
        CashFlowItem(Money("15000.00"), datetime(2024, 1, 31), "Q1 Revenue", "revenue"),
        CashFlowItem(Money("-8000.00"), datetime(2024, 1, 31), "Salaries", "payroll"),
        CashFlowItem(Money("-2500.00"), datetime(2024, 1, 31), "Rent", "overhead"),
        CashFlowItem(Money("-1200.00"), datetime(2024, 1, 31), "Utilities", "overhead"),
        CashFlowItem(Money("-800.00"), datetime(2024, 1, 31), "Marketing", "marketing"),
        
        # Q2 - Growing season
        CashFlowItem(Money("22000.00"), datetime(2024, 4, 30), "Q2 Revenue", "revenue"),
        CashFlowItem(Money("-9000.00"), datetime(2024, 4, 30), "Salaries", "payroll"),
        CashFlowItem(Money("-2500.00"), datetime(2024, 4, 30), "Rent", "overhead"),
        CashFlowItem(Money("-1100.00"), datetime(2024, 4, 30), "Utilities", "overhead"),
        CashFlowItem(Money("-1500.00"), datetime(2024, 4, 30), "Marketing", "marketing"),
        
        # Q3 - Peak season
        CashFlowItem(Money("35000.00"), datetime(2024, 7, 31), "Q3 Revenue", "revenue"),
        CashFlowItem(Money("-12000.00"), datetime(2024, 7, 31), "Salaries + Bonus", "payroll"),
        CashFlowItem(Money("-2500.00"), datetime(2024, 7, 31), "Rent", "overhead"),
        CashFlowItem(Money("-1400.00"), datetime(2024, 7, 31), "Utilities", "overhead"),
        CashFlowItem(Money("-2000.00"), datetime(2024, 7, 31), "Marketing", "marketing"),
        
        # Q4 - Holiday season
        CashFlowItem(Money("28000.00"), datetime(2024, 10, 31), "Q4 Revenue", "revenue"),
        CashFlowItem(Money("-10000.00"), datetime(2024, 10, 31), "Salaries", "payroll"),
        CashFlowItem(Money("-2500.00"), datetime(2024, 10, 31), "Rent", "overhead"),
        CashFlowItem(Money("-1300.00"), datetime(2024, 10, 31), "Utilities", "overhead"),
        CashFlowItem(Money("-1800.00"), datetime(2024, 10, 31), "Marketing", "marketing"),
    ]
    
    business_cf = CashFlow(business_transactions)
    
    # Category analysis
    revenue = business_cf.query.filter_by(category="revenue")
    payroll = business_cf.query.filter_by(category="payroll")
    overhead = business_cf.query.filter_by(category="overhead")
    marketing = business_cf.query.filter_by(category="marketing")
    
    print("Annual Business Analysis:")
    print("=" * 40)
    print(f"Total Revenue: {revenue.sum()}")
    print(f"Payroll Costs: {payroll.sum()}")
    print(f"Overhead Costs: {overhead.sum()}")
    print(f"Marketing Costs: {marketing.sum()}")
    print(f"Net Profit: {business_cf.sum()}")
    
    # Quarterly breakdown
    quarters = [
        ("Q1", datetime(2024, 1, 1), datetime(2024, 4, 1)),
        ("Q2", datetime(2024, 4, 1), datetime(2024, 7, 1)),
        ("Q3", datetime(2024, 7, 1), datetime(2024, 10, 1)),
        ("Q4", datetime(2024, 10, 1), datetime(2025, 1, 1)),
    ]
    
    print(f"\nQuarterly Performance:")
    for quarter, start, end in quarters:
        q_cf = business_cf.query.filter_by(
            datetime__gte=start,
            datetime__lt=end
        )
        q_revenue = q_cf.filter_by(category="revenue").sum()
        q_expenses = q_cf.exclude(category="revenue").sum()
        q_profit = q_cf.sum()
        margin = (q_profit / q_revenue) * 100 if q_revenue > Money.zero() else 0
        
        print(f"{quarter}: Revenue {q_revenue}, Expenses {q_expenses}, Profit {q_profit} ({margin:.1f}% margin)")

analyze_business_cash_flow()
```

## Cash Flow Patterns and Utilities

```python
# Create repeating patterns
def create_monthly_salary(amount, start_date, months):
    """Create monthly salary payments."""
    from datetime import timedelta
    
    transactions = []
    current_date = start_date
    
    for i in range(months):
        transactions.append(
            CashFlowItem(
                Money(amount),
                current_date,
                f"Salary - Month {i+1}",
                "salary"
            )
        )
        # Approximate monthly increment (30 days)
        current_date += timedelta(days=30)
    
    return transactions

# Generate salary cash flow
salary_cf = CashFlow(create_monthly_salary("5000.00", datetime(2024, 1, 1), 12))
print(f"Annual salary: {salary_cf.sum()}")

# Cash flow statistics
def cash_flow_stats(cf):
    """Calculate cash flow statistics."""
    amounts = [item.amount for item in cf.items()]
    
    inflows = [amt for amt in amounts if amt.is_positive()]
    outflows = [amt for amt in amounts if amt.is_negative()]
    
    total_inflows = sum(inflows, Money.zero())
    total_outflows = sum(outflows, Money.zero())
    
    print(f"Cash Flow Statistics:")
    print(f"Total transactions: {len(amounts)}")
    print(f"Inflows: {len(inflows)} transactions, {total_inflows}")
    print(f"Outflows: {len(outflows)} transactions, {total_outflows}")
    print(f"Net flow: {cf.sum()}")
    print(f"Average transaction: {cf.sum() / len(amounts) if amounts else Money.zero()}")

cash_flow_stats(personal_cf)
```

## Best Practices

1. **Consistent categories**: Use standardized category names for better querying
2. **Detailed descriptions**: Include meaningful descriptions for transaction tracking
3. **Precise timestamps**: Use specific datetime objects for accurate analysis
4. **Logical grouping**: Group related transactions for easier analysis
5. **Regular analysis**: Periodically analyze cash flows to identify patterns

## Common Patterns

```python
# Monthly expense tracking
def monthly_expenses(cash_flow, year, month):
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)
    
    return cash_flow.query.filter_by(
        datetime__gte=start,
        datetime__lt=end
    ).exclude(category="income")

# Category budgeting
def budget_analysis(cash_flow, budget_dict):
    """Compare actual spending to budget."""
    for category, budget in budget_dict.items():
        actual = cash_flow.query.filter_by(category=category).sum()
        variance = actual - Money(budget)
        status = "OVER" if variance.is_positive() else "UNDER"
        print(f"{category}: Budget {Money(budget)}, Actual {actual}, {status} by {abs(variance)}")

# Cash flow forecasting
def forecast_cash_flow(historical_cf, months_ahead):
    """Simple cash flow forecasting based on historical averages."""
    # This is a simplified example - real forecasting would be more sophisticated
    monthly_avg = historical_cf.sum() / 12  # Assuming 12 months of data
    return monthly_avg * months_ahead
```

Cash flows are the foundation of all financial analysis in MoneyWarp! 💸
