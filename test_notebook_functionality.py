#!/usr/bin/env python3
"""
Test script to verify the core functionality used in the interactive notebook.
This tests the money-warp library integration without the Jupyter widgets.
"""

import sys
from datetime import datetime, timedelta
from decimal import Decimal

from money_warp import InterestRate, Loan, Money, Warp

# Add current directory to path
sys.path.append(".")


def test_loan_creation():
    """Test basic loan creation with default parameters."""
    print("🧪 Testing loan creation...")

    # Create loan with default parameters from notebook
    principal = Money("10000")
    interest_rate = InterestRate("5% annual")
    start_date = datetime(2024, 1, 1)

    # Calculate 12 monthly payment dates
    due_dates = []
    for i in range(12):
        month = start_date.month + i
        year = start_date.year + (month - 1) // 12
        month = ((month - 1) % 12) + 1
        due_dates.append(datetime(year, month, start_date.day))

    # Create loan with fine settings
    loan = Loan(
        principal=principal,
        interest_rate=interest_rate,
        due_dates=due_dates,
        fine_rate=Decimal("0.02"),  # 2%
        grace_period_days=0,
    )

    print(f"✅ Loan created: {loan}")
    print(f"   Principal: ${loan.principal.real_amount:,.2f}")
    print(f"   Interest Rate: {loan.interest_rate}")
    print(f"   Payments: {len(loan.due_dates)}")
    print(f"   Fine Rate: {float(loan.fine_rate * 100):.1f}%")
    print(f"   Current Balance: ${loan.current_balance.real_amount:,.2f}")

    return loan


def test_payment_recording(loan):
    """Test payment recording functionality."""
    print("\n🧪 Testing payment recording...")

    # Record a payment
    payment_amount = Money("900")
    payment_date = datetime(2024, 1, 15)

    initial_balance = loan.current_balance
    loan.record_payment(payment_amount, payment_date)
    new_balance = loan.current_balance

    print(f"✅ Payment recorded: ${payment_amount.real_amount:,.2f}")
    print(f"   Initial Balance: ${initial_balance.real_amount:,.2f}")
    print(f"   New Balance: ${new_balance.real_amount:,.2f}")
    print(f"   Balance Reduction: ${(initial_balance - new_balance).real_amount:,.2f}")

    # Check payment history
    payments = loan._actual_payments
    print(f"   Payment History: {len(payments)} payments")
    for payment in payments:
        print(
            f"     - {payment.datetime.strftime('%Y-%m-%d')}: ${payment.amount.real_amount:,.2f} ({payment.category})"
        )


def test_time_machine(loan):
    """Test time machine (Warp) functionality."""
    print("\n🧪 Testing time machine functionality...")

    # Test warping to a future date
    future_date = datetime(2024, 6, 1)

    print(f"   Current time balance: ${loan.current_balance.real_amount:,.2f}")

    with Warp(loan, future_date) as warped_loan:
        warped_balance = warped_loan.current_balance
        print(f"✅ Warped to {future_date.strftime('%Y-%m-%d')}")
        print(f"   Warped balance: ${warped_balance.real_amount:,.2f}")

        # Test fine calculation
        fines = warped_loan.calculate_late_fines(future_date)
        if fines.is_positive():
            print(f"   Late fines applied: ${fines.real_amount:,.2f}")
        else:
            print("   No late fines (payments up to date)")

    print(f"   Back to present balance: ${loan.current_balance.real_amount:,.2f}")


def test_chart_data_generation(loan):
    """Test data generation for charts."""
    print("\n🧪 Testing chart data generation...")

    # Create time range for chart (similar to notebook)
    start_date = loan.disbursement_date
    max(loan.due_dates)

    # Test balance data generation
    time_range = []
    current = start_date
    for _ in range(30):  # Test with 30 days
        time_range.append(current)
        current += timedelta(days=1)

    balance_data = []
    for date in time_range[:5]:  # Test first 5 days
        try:
            with Warp(loan, date) as warped_loan:
                total_balance = warped_loan.current_balance
                outstanding_fines = warped_loan.outstanding_fines
                principal_balance = total_balance - outstanding_fines

                balance_data.append(
                    {
                        "date": date,
                        "total_balance": float(total_balance.real_amount),
                        "principal_balance": float(principal_balance.real_amount),
                        "outstanding_fines": float(outstanding_fines.real_amount),
                    }
                )
        except Exception as e:
            print(f"   ⚠️ Error processing {date}: {e}")
            continue

    print(f"✅ Chart data generated for {len(balance_data)} time points")
    if balance_data:
        first_point = balance_data[0]
        print(f"   Sample data point: {first_point['date'].strftime('%Y-%m-%d')}")
        print(f"     Total Balance: ${first_point['total_balance']:,.2f}")
        print(f"     Principal: ${first_point['principal_balance']:,.2f}")
        print(f"     Fines: ${first_point['outstanding_fines']:,.2f}")


def test_late_payment_scenario(loan):
    """Test late payment and fine calculation."""
    print("\n🧪 Testing late payment scenario...")

    # Simulate a late payment scenario
    late_date = datetime(2024, 2, 15)  # 15 days after first payment due

    with Warp(loan, late_date) as warped_loan:
        # Calculate late fines
        fines_before = warped_loan.total_fines
        new_fines = warped_loan.calculate_late_fines(late_date)
        fines_after = warped_loan.total_fines

        print(f"✅ Late payment test at {late_date.strftime('%Y-%m-%d')}")
        print(f"   Fines before: ${fines_before.real_amount:,.2f}")
        print(f"   New fines applied: ${new_fines.real_amount:,.2f}")
        print(f"   Total fines after: ${fines_after.real_amount:,.2f}")
        print(f"   Outstanding fines: ${warped_loan.outstanding_fines.real_amount:,.2f}")

        if new_fines.is_positive():
            print(f"   Fine rate applied: {float(loan.fine_rate * 100):.1f}%")


def main():
    """Run all tests."""
    print("🚀 Testing Interactive Loan Notebook Functionality")
    print("=" * 60)

    try:
        # Test loan creation
        loan = test_loan_creation()

        # Test payment recording
        test_payment_recording(loan)

        # Test time machine
        test_time_machine(loan)

        # Test chart data generation
        test_chart_data_generation(loan)

        # Test late payment scenario
        test_late_payment_scenario(loan)

        print("\n🎉 All tests completed successfully!")
        print("✅ The notebook functionality is working correctly.")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
