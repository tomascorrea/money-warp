"""Tests for Loan class with scheduler architecture - following project patterns."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money, PriceScheduler


# Loan Creation Tests
def test_loan_creation_basic():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]

    loan = Loan(principal, rate, due_dates)
    assert loan.principal == principal
    assert loan.interest_rate == rate
    assert loan.due_dates == due_dates
    assert loan.scheduler == PriceScheduler  # Default scheduler


def test_loan_creation_with_disbursement_date():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    assert loan.disbursement_date == disbursement_date


def test_loan_creation_with_custom_scheduler():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, scheduler=PriceScheduler)
    assert loan.scheduler == PriceScheduler


def test_loan_creation_default_disbursement_date():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    expected_disbursement = datetime(2024, 2, 1) - timedelta(days=30)
    assert loan.disbursement_date == expected_disbursement


def test_loan_creation_sorts_due_dates():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 3, 1), datetime(2024, 1, 1), datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    expected_sorted = [datetime(2024, 1, 1), datetime(2024, 2, 1), datetime(2024, 3, 1)]
    assert loan.due_dates == expected_sorted


def test_loan_creation_empty_due_dates_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")

    with pytest.raises(ValueError, match="At least one due date is required"):
        Loan(principal, rate, [])


def test_loan_creation_zero_principal_raises_error():
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    with pytest.raises(ValueError, match="Principal must be positive"):
        Loan(Money.zero(), rate, due_dates)


def test_loan_creation_negative_principal_raises_error():
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    with pytest.raises(ValueError, match="Principal must be positive"):
        Loan(Money("-1000.00"), rate, due_dates)


# Loan Properties Tests
def test_loan_initial_current_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    assert loan.current_balance == principal


def test_loan_initial_not_paid_off():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    assert not loan.is_paid_off


def test_loan_last_payment_date_initial():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    assert loan.last_payment_date == disbursement_date


def test_loan_days_since_last_payment_initial():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    check_date = datetime(2024, 1, 15)
    assert loan.days_since_last_payment(check_date) == 14


def test_loan_days_since_last_payment_defaults_to_now():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    # Should not raise error and return some number
    days = loan.days_since_last_payment()
    assert isinstance(days, int)


# Amortization Schedule Tests
def test_loan_get_amortization_schedule_structure():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates)
    schedule = loan.get_amortization_schedule()

    assert len(schedule) == 2
    assert schedule.total_payments > Money.zero()
    assert schedule.total_interest > Money.zero()
    assert schedule.total_principal == principal


def test_loan_get_amortization_schedule_entries():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    schedule = loan.get_amortization_schedule()

    entry = schedule[0]
    assert entry.payment_number == 1
    assert entry.due_date == datetime(2024, 2, 1)
    assert entry.beginning_balance == principal
    assert entry.payment_amount > Money.zero()
    assert entry.principal_payment > Money.zero()
    assert entry.interest_payment >= Money.zero()
    assert entry.ending_balance == Money.zero()


# Cash Flow Tests
def test_loan_generate_expected_cash_flow_includes_disbursement():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    disbursement_items = cash_flow.query.filter_by(category="disbursement").all()
    assert len(disbursement_items) == 1
    assert disbursement_items[0].amount == principal


def test_loan_generate_expected_cash_flow_has_payment_breakdown():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    interest_items = cash_flow.query.filter_by(category="interest").all()
    principal_items = cash_flow.query.filter_by(category="principal").all()

    assert len(interest_items) == 1
    assert len(principal_items) == 1


def test_loan_generate_expected_cash_flow_multiple_payments():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    # Should have 1 disbursement + 3 interest + 3 principal = 7 items
    assert len(cash_flow) == 7

    interest_items = cash_flow.query.filter_by(category="interest").all()
    principal_items = cash_flow.query.filter_by(category="principal").all()
    assert len(interest_items) == 3
    assert len(principal_items) == 3


def test_loan_generate_expected_cash_flow_net_zero():
    principal = Money("10000.00")
    rate = InterestRate("0% a")  # Zero interest for simplicity
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    # Net should be close to zero (disbursement + payments)
    net = cash_flow.net_present_value()
    assert abs(net.real_amount) < Decimal("0.01")


# Payment Recording Tests
def test_loan_record_payment_updates_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15))

    # Balance should be reduced by principal portion
    assert loan.current_balance < principal


def test_loan_record_payment_creates_interest_and_principal_items():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15))

    # Should have created interest and principal payment items
    assert len(loan._actual_payments) == 2

    # Check categories
    categories = [payment.category for payment in loan._actual_payments]
    assert "actual_interest" in categories
    assert "actual_principal" in categories


def test_loan_record_payment_updates_last_payment_date():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    payment_date = datetime(2024, 1, 15)

    assert loan.last_payment_date == disbursement_date

    loan.record_payment(Money("5000.00"), payment_date)
    assert loan.last_payment_date == payment_date


def test_loan_record_payment_multiple_payments():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan.record_payment(Money("3000.00"), datetime(2024, 1, 15))
    loan.record_payment(Money("2000.00"), datetime(2024, 1, 20))

    assert loan.current_balance < principal


def test_loan_record_payment_overpayment_zeros_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan.record_payment(Money("15000.00"), datetime(2024, 1, 15))

    assert loan.current_balance == Money.zero()
    assert loan.is_paid_off


def test_loan_record_payment_negative_amount_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)

    with pytest.raises(ValueError, match="Payment amount must be positive"):
        loan.record_payment(Money("-1000.00"), datetime(2024, 1, 15))


def test_loan_record_payment_zero_amount_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)

    with pytest.raises(ValueError, match="Payment amount must be positive"):
        loan.record_payment(Money.zero(), datetime(2024, 1, 15))


# Actual Cash Flow Tests
def test_loan_get_actual_cash_flow_empty_initially():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    actual_cf = loan.get_actual_cash_flow()

    # Should have disbursement + expected payments, but no actual payments yet
    disbursement_items = actual_cf.query.filter_by(category="disbursement").all()
    actual_payment_items = actual_cf.query.filter_by(category="actual_interest").all()

    assert len(disbursement_items) == 1
    assert len(actual_payment_items) == 0


def test_loan_get_actual_cash_flow_includes_payments():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan.record_payment(Money("5000.00"), datetime(2024, 1, 15), "First payment")

    actual_cf = loan.get_actual_cash_flow()

    # Should have expected payments + actual payments
    actual_interest_items = actual_cf.query.filter_by(category="actual_interest").all()
    actual_principal_items = actual_cf.query.filter_by(category="actual_principal").all()

    assert len(actual_interest_items) >= 1
    assert len(actual_principal_items) >= 1


# String Representation Tests
def test_loan_string_representation():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    loan_str = str(loan)

    assert "10,000.00" in loan_str
    assert "5.000%" in loan_str
    assert "payments=1" in loan_str


def test_loan_repr_representation():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    loan_repr = repr(loan)

    assert "Loan(" in loan_repr
    assert "principal=Money(10000.00)" in loan_repr
    assert "2024, 2, 1" in loan_repr


# Edge Case Tests
def test_loan_single_payment_zero_interest():
    principal = Money("10000.00")
    rate = InterestRate("0% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    schedule = loan.get_amortization_schedule()

    # Should equal principal exactly
    assert schedule[0].payment_amount == principal
    assert schedule[0].interest_payment == Money.zero()


def test_loan_very_small_principal():
    principal = Money("0.01")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    # Should still generate valid cash flow
    assert len(cash_flow) > 0


def test_loan_high_interest_rate():
    principal = Money("10000.00")
    rate = InterestRate("50% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates)
    schedule = loan.get_amortization_schedule()

    # Should be significantly higher than principal (50% annual for ~30 days)
    payment = schedule[0].payment_amount
    assert payment > Money("10300.00")


def test_loan_many_payments():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    # Create monthly payments for 2 years
    due_dates = [datetime(2024, 1, 1) + timedelta(days=30 * i) for i in range(1, 25)]

    loan = Loan(principal, rate, due_dates)
    cash_flow = loan.generate_expected_cash_flow()

    # Should have 1 disbursement + 24 * 2 (interest, principal) = 49 items
    assert len(cash_flow) == 49

    interest_items = cash_flow.query.filter_by(category="interest").all()
    principal_items = cash_flow.query.filter_by(category="principal").all()
    assert len(interest_items) == 24
    assert len(principal_items) == 24


# Present Value method tests
def test_loan_present_value_with_own_rate():
    loan = Loan(
        Money("10000"),
        InterestRate("5% annual"),
        [datetime(2024, 1, 15), datetime(2024, 2, 15)],
        datetime(2023, 12, 16),
    )

    # Calculate PV using loan's own interest rate (default)
    pv = loan.present_value()

    # Should return a Money object
    assert isinstance(pv, Money)
    # PV using loan's own rate from current time - shows time value effect
    # Let's test PV from disbursement date should be close to zero
    pv_from_disbursement = loan.present_value(valuation_date=loan.disbursement_date)
    assert abs(pv_from_disbursement.raw_amount) < Money("1").raw_amount


def test_loan_present_value_with_different_rate():
    loan = Loan(
        Money("10000"),
        InterestRate("5% annual"),
        [datetime(2024, 1, 15), datetime(2024, 2, 15)],
        datetime(2023, 12, 16),
    )

    # Calculate PV with 8% discount rate
    pv = loan.present_value(InterestRate("8% annual"))

    # Should return a Money object
    assert isinstance(pv, Money)
    # From borrower's perspective, loan PV is typically negative
    # (receive money now, pay back more later)
    assert pv.is_negative()


def test_loan_present_value_with_custom_valuation_date():
    loan = Loan(
        Money("5000"), InterestRate("4% annual"), [datetime(2024, 6, 1), datetime(2024, 12, 1)], datetime(2024, 1, 1)
    )

    valuation_date = datetime(2024, 2, 1)
    # Test with loan's own rate and custom valuation date
    pv = loan.present_value(valuation_date=valuation_date)

    assert isinstance(pv, Money)
    # Should be close to zero when using loan's own rate
    assert abs(pv.raw_amount) < Money("50").raw_amount  # Within $50


def test_loan_present_value_uses_current_time_by_default():
    loan = Loan(Money("1000"), InterestRate("3% annual"), [datetime(2024, 12, 31)], datetime(2024, 1, 1))

    # Should use loan's current time and loan's own rate by default
    pv = loan.present_value()

    assert isinstance(pv, Money)
    # Test that PV from disbursement date is close to zero
    pv_from_disbursement = loan.present_value(valuation_date=loan.disbursement_date)
    assert abs(pv_from_disbursement.raw_amount) < Money("1").raw_amount


def test_loan_present_value_with_time_machine():
    from money_warp import Warp

    loan = Loan(
        Money("2000"), InterestRate("4% annual"), [datetime(2024, 6, 1), datetime(2024, 12, 1)], datetime(2024, 1, 1)
    )

    # Calculate PV using loan's own rate from different time perspectives
    normal_pv = loan.present_value()

    with Warp(loan, datetime(2024, 3, 1)) as warped_loan:
        warped_pv = warped_loan.present_value()

    # Both should be valid Money objects
    assert isinstance(normal_pv, Money)
    assert isinstance(warped_pv, Money)
    # Test that PV from disbursement date is close to zero
    pv_from_disbursement = loan.present_value(valuation_date=loan.disbursement_date)
    assert abs(pv_from_disbursement.raw_amount) < Money("1").raw_amount


def test_loan_present_value_different_discount_rates():
    # Create a loan with longer duration to see bigger differences
    loan = Loan(
        Money("10000"),
        InterestRate("6% annual"),
        [datetime(2024, 6, 1), datetime(2025, 6, 1), datetime(2026, 6, 1)],
        datetime(2024, 1, 1),
    )

    low_rate_pv = loan.present_value(InterestRate("2% annual"))  # Very low discount
    high_rate_pv = loan.present_value(InterestRate("20% annual"))  # Very high discount

    # Higher discount rate should result in lower present value
    # The difference should be significant with these rates and timeframes
    assert high_rate_pv != low_rate_pv  # At minimum, they should be different
    assert abs(high_rate_pv.raw_amount) != abs(low_rate_pv.raw_amount)


# IRR method tests
def test_loan_irr_basic():
    loan = Loan(
        Money("10000"),
        InterestRate("5% annual"),
        [datetime(2024, 1, 15), datetime(2024, 2, 15)],
        datetime(2023, 12, 16),
    )

    # Calculate IRR
    loan_irr = loan.irr()

    # Should return an InterestRate
    assert isinstance(loan_irr, InterestRate)
    # IRR should be very close to the loan's interest rate (5%)
    # because that's the rate where NPV ≈ 0
    actual_rate = float(loan_irr.as_decimal * 100)
    assert abs(actual_rate - 5.0) < 0.1  # Should be very close to 5%


def test_loan_irr_with_time_machine_for_valuation():
    # Use Time Machine instead of valuation_date parameter
    loan = Loan(
        Money("5000"), InterestRate("4% annual"), [datetime(2024, 6, 1), datetime(2024, 12, 1)], datetime(2024, 1, 1)
    )

    # Calculate IRR from a specific date using Time Machine
    from money_warp import Warp

    with Warp(loan, datetime(2024, 2, 1)) as warped_loan:
        loan_irr = warped_loan.irr()

    assert isinstance(loan_irr, InterestRate)
    # Should be close to the loan's interest rate (4%)
    actual_rate = float(loan_irr.as_decimal * 100)
    assert abs(actual_rate - 4.0) < 0.1  # Should be very close to 4%


def test_loan_irr_with_custom_guess():
    loan = Loan(
        Money("2000"), InterestRate("6% annual"), [datetime(2024, 6, 1), datetime(2024, 12, 1)], datetime(2024, 1, 1)
    )

    guess = InterestRate("10% annual")
    loan_irr = loan.irr(guess=guess)

    assert isinstance(loan_irr, InterestRate)
    # Should converge to loan's rate (6%) regardless of initial guess
    actual_rate = float(loan_irr.as_decimal * 100)
    assert abs(actual_rate - 6.0) < 0.1  # Should be very close to 6%


def test_loan_irr_with_time_machine():
    from money_warp import Warp

    loan = Loan(
        Money("3000"), InterestRate("7% annual"), [datetime(2024, 6, 1), datetime(2024, 12, 1)], datetime(2024, 1, 1)
    )

    # Calculate IRR from different time perspectives
    normal_irr = loan.irr()

    with Warp(loan, datetime(2024, 3, 1)) as warped_loan:
        warped_irr = warped_loan.irr()

    # Both should be valid InterestRates
    assert isinstance(normal_irr, InterestRate)
    assert isinstance(warped_irr, InterestRate)
    # Both should be close to the loan's rate (7%)
    for test_irr in [normal_irr, warped_irr]:
        actual_rate = float(test_irr.as_decimal * 100)
        assert abs(actual_rate - 7.0) < 0.1  # Should be very close to 7%


def test_loan_irr_multiple_payments():
    # Test with more payments for better IRR accuracy
    loan = Loan(
        Money("12000"),
        InterestRate("5.5% annual"),
        [datetime(2024, i, 1) for i in range(1, 7)],  # 6 monthly payments
        datetime(2023, 12, 1),
    )

    loan_irr = loan.irr()

    assert isinstance(loan_irr, InterestRate)
    # Should be very close to the loan's rate (5.5%)
    actual_rate = float(loan_irr.as_decimal * 100)
    assert abs(actual_rate - 5.5) < 0.1  # Should be very close to 5.5%
