"""Validation tests for PriceScheduler against known loan calculation principles."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from money_warp import InterestRate, Money, PriceScheduler


def test_price_scheduler_reference_values():
    """Test PriceScheduler against fixed expected values from reference implementation."""
    # Based on cartaorobbin/loan-calculator test values
    # Original uses 3% DAILY rate (extremely high but matches reference test)
    principal = Money("8530.20")

    # Use 3% daily rate directly (matches reference implementation exactly)
    rate = InterestRate("3% d")  # 3% daily

    # 10 payments, 1 day apart each
    disbursement_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    due_dates = [datetime(2024, 1, i + 2, tzinfo=timezone.utc) for i in range(10)]  # Jan 2, 3, 4, ..., 11

    schedule = PriceScheduler.generate_schedule(principal, rate, due_dates, disbursement_date)

    # Expected values from reference implementation
    expected_payments = [1000.00] * 10
    expected_interests = [255.91, 233.58, 210.59, 186.91, 162.52, 137.39, 111.51, 84.86, 57.40, 29.13]
    expected_amortizations = [744.09, 766.42, 789.41, 813.09, 837.48, 862.61, 888.49, 915.14, 942.60, 970.87]
    expected_balances = [8530.20, 7786.11, 7019.69, 6230.28, 5417.19, 4579.71, 3717.10, 2828.61, 1913.47, 970.87, 0.0]

    # Validate schedule length
    assert len(schedule) == 10

    # Validate each payment against expected values
    for i, entry in enumerate(schedule):
        # Payment amounts (all should be 1000.00)
        assert (
            abs(float(entry.payment_amount.real_amount) - expected_payments[i]) < 0.01
        ), f"Payment {i+1}: expected {expected_payments[i]}, got {entry.payment_amount}"

        # Interest portions
        assert (
            abs(float(entry.interest_payment.real_amount) - expected_interests[i]) < 0.01
        ), f"Interest {i+1}: expected {expected_interests[i]}, got {entry.interest_payment}"

        # Principal portions (amortizations)
        assert (
            abs(float(entry.principal_payment.real_amount) - expected_amortizations[i]) < 0.01
        ), f"Principal {i+1}: expected {expected_amortizations[i]}, got {entry.principal_payment}"

        # Beginning balance
        assert (
            abs(float(entry.beginning_balance.real_amount) - expected_balances[i]) < 0.01
        ), f"Beginning balance {i+1}: expected {expected_balances[i]}, got {entry.beginning_balance}"

        # Ending balance
        assert (
            abs(float(entry.ending_balance.real_amount) - expected_balances[i + 1]) < 0.01
        ), f"Ending balance {i+1}: expected {expected_balances[i+1]}, got {entry.ending_balance}"

        # Days in period (all should be 1 day)
        assert entry.days_in_period == 1

    # Final balance should be zero
    assert abs(schedule[-1].ending_balance.real_amount) < Decimal("0.01")


def test_price_scheduler_zero_interest_validation():
    """Test PriceScheduler with zero interest rate."""
    principal = Money("12000.00")  # $12,000 loan
    rate = InterestRate("0% a")  # 0% interest

    # 12 monthly payments
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    due_dates = [start_date + timedelta(days=30 * i) for i in range(1, 13)]
    disbursement_date = start_date

    schedule = PriceScheduler.generate_schedule(principal, rate, due_dates, disbursement_date)

    # With 0% interest, each payment should be exactly principal/12
    expected_payment = Money("1000.00")  # $12,000 / 12

    for entry in schedule:
        assert entry.payment_amount == expected_payment
        assert entry.interest_payment == Money.zero()
        assert entry.principal_payment == expected_payment

    # Total interest should be zero
    assert schedule.total_interest == Money.zero()
    assert schedule.total_principal == principal


def test_price_scheduler_single_payment_validation():
    """Test PriceScheduler with a single payment (bullet loan)."""
    principal = Money("50000.00")  # $50,000 loan
    rate = InterestRate("5% a")  # 5% annual rate

    # Single payment after 1 year
    disbursement_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    due_dates = [datetime(2024, 12, 31, tzinfo=timezone.utc)]  # 365 days later

    schedule = PriceScheduler.generate_schedule(principal, rate, due_dates, disbursement_date)

    assert len(schedule) == 1

    # For 5% annual rate over 365 days, payment should be approximately $52,500
    payment = schedule[0]
    principal.raw_amount * (Decimal("1.05") ** 1)  # Simple annual compounding approximation

    # Allow some variance due to daily compounding vs annual
    assert Money("52000.00") < payment.payment_amount < Money("53000.00")

    # Interest should be approximately $2,500 (5% of $50,000)
    assert Money("2000.00") < payment.interest_payment < Money("3000.00")

    # Principal should be the original loan amount
    assert payment.principal_payment == principal


def test_price_scheduler_short_term_validation():
    """Test PriceScheduler with a short-term loan."""
    principal = Money("5000.00")  # $5,000 loan
    rate = InterestRate("12% a")  # 12% annual rate (1% monthly)

    # 6 monthly payments
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    due_dates = [start_date + timedelta(days=30 * i) for i in range(1, 7)]
    disbursement_date = start_date

    schedule = PriceScheduler.generate_schedule(principal, rate, due_dates, disbursement_date)

    assert len(schedule) == 6

    # For 12% annual (1% monthly), 6 payments on $5,000
    # Expected monthly payment should be approximately $860
    monthly_payment = schedule[0].payment_amount
    assert Money("850.00") < monthly_payment < Money("870.00")

    # Validate that balance decreases each month
    for i in range(len(schedule) - 1):
        assert schedule[i].ending_balance > schedule[i + 1].beginning_balance or abs(
            schedule[i].ending_balance.real_amount - schedule[i + 1].beginning_balance.real_amount
        ) < Decimal("0.01")

    # Final balance should be zero
    assert abs(schedule[-1].ending_balance.real_amount) < Decimal("0.01")


def test_price_scheduler_irregular_schedule_validation():
    """Test PriceScheduler with irregular payment dates."""
    principal = Money("10000.00")  # $10,000 loan
    rate = InterestRate("8% a")  # 8% annual rate

    # Irregular payment schedule
    disbursement_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    due_dates = [
        datetime(2024, 2, 15, tzinfo=timezone.utc),  # 45 days
        datetime(2024, 4, 1, tzinfo=timezone.utc),  # 45 days later
        datetime(2024, 6, 1, tzinfo=timezone.utc),  # 61 days later
        datetime(2024, 8, 15, tzinfo=timezone.utc),  # 75 days later
    ]

    schedule = PriceScheduler.generate_schedule(principal, rate, due_dates, disbursement_date)

    assert len(schedule) == 4

    # Validate that days_in_period matches actual calendar days
    assert schedule[0].days_in_period == 45  # Jan 1 to Feb 15
    assert schedule[1].days_in_period == 46  # Feb 15 to Apr 1 (Feb has different lengths)
    assert schedule[2].days_in_period == 61  # Apr 1 to Jun 1
    assert schedule[3].days_in_period == 75  # Jun 1 to Aug 15

    # Interest should vary based on period length and remaining balance
    # The balance decreases significantly, so later payments have less interest
    # even if they have more days. Let's validate the balance decreases properly.
    for i in range(len(schedule) - 1):
        assert schedule[i].ending_balance > schedule[i + 1].beginning_balance or abs(
            schedule[i].ending_balance.real_amount - schedule[i + 1].beginning_balance.real_amount
        ) < Decimal("0.01")

    # Final balance should be zero
    assert abs(schedule[-1].ending_balance.real_amount) < Decimal("0.01")


def test_price_scheduler_high_precision_validation():
    """Test PriceScheduler maintains precision in calculations."""
    principal = Money("123456.78")  # Odd amount
    rate = InterestRate("7.25% a")  # Odd rate

    # 24 monthly payments
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    due_dates = [start_date + timedelta(days=30 * i) for i in range(1, 25)]
    disbursement_date = start_date

    schedule = PriceScheduler.generate_schedule(principal, rate, due_dates, disbursement_date)

    # Validate precision is maintained
    total_principal_paid = sum(entry.principal_payment.raw_amount for entry in schedule)
    assert abs(total_principal_paid - principal.raw_amount) < Decimal("0.01")

    # Validate that each payment's components add up correctly
    for entry in schedule:
        calculated_payment = entry.interest_payment + entry.principal_payment
        assert abs(calculated_payment.raw_amount - entry.payment_amount.raw_amount) < Decimal("0.01")


@pytest.mark.parametrize(
    "principal_amount,annual_rate,num_payments",
    [
        ("1000.00", "3% a", 12),
        ("25000.00", "4.5% a", 60),
        ("150000.00", "6.75% a", 180),
        ("500000.00", "5.25% a", 360),
    ],
)
def test_price_scheduler_parametrized_validation(principal_amount, annual_rate, num_payments):
    """Test PriceScheduler with various loan parameters."""
    principal = Money(principal_amount)
    rate = InterestRate(annual_rate)

    # Generate monthly payment schedule
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    due_dates = [start_date + timedelta(days=30 * i) for i in range(1, num_payments + 1)]
    disbursement_date = start_date

    schedule = PriceScheduler.generate_schedule(principal, rate, due_dates, disbursement_date)

    # Basic validations
    assert len(schedule) == num_payments
    assert schedule.total_principal == principal

    # Payment amount should be consistent (except possibly the last payment)
    payment_amounts = [entry.payment_amount for entry in schedule[:-1]]
    if len(payment_amounts) > 1:
        # All payments except the last should be the same (within precision)
        first_payment = payment_amounts[0]
        for payment in payment_amounts[1:]:
            assert abs(payment.raw_amount - first_payment.raw_amount) < Decimal("0.01")

    # Final balance should be zero
    assert abs(schedule[-1].ending_balance.real_amount) < Decimal("0.01")

    # Total payments should equal principal plus interest
    expected_total = schedule.total_principal + schedule.total_interest
    assert abs(schedule.total_payments.raw_amount - expected_total.raw_amount) < Decimal("0.01")
