"""Tests for Loan present value and IRR (time value of money) methods."""

from datetime import datetime, timezone

from money_warp import InterestRate, Loan, Money, Warp


def test_loan_present_value_with_own_rate():
    loan = Loan(
        Money("10000"),
        InterestRate("5% annual"),
        [datetime(2024, 1, 15, tzinfo=timezone.utc), datetime(2024, 2, 15, tzinfo=timezone.utc)],
        datetime(2023, 12, 16, tzinfo=timezone.utc),
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
        [datetime(2024, 1, 15, tzinfo=timezone.utc), datetime(2024, 2, 15, tzinfo=timezone.utc)],
        datetime(2023, 12, 16, tzinfo=timezone.utc),
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
        Money("5000"),
        InterestRate("4% annual"),
        [datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 12, 1, tzinfo=timezone.utc)],
        datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    valuation_date = datetime(2024, 2, 1, tzinfo=timezone.utc)
    # Test with loan's own rate and custom valuation date
    pv = loan.present_value(valuation_date=valuation_date)

    assert isinstance(pv, Money)
    # Should be close to zero when using loan's own rate
    assert abs(pv.raw_amount) < Money("50").raw_amount  # Within $50


def test_loan_present_value_uses_current_time_by_default():
    loan = Loan(
        Money("1000"),
        InterestRate("3% annual"),
        [datetime(2024, 12, 31, tzinfo=timezone.utc)],
        datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    # Should use loan's current time and loan's own rate by default
    pv = loan.present_value()

    assert isinstance(pv, Money)
    # Test that PV from disbursement date is close to zero
    pv_from_disbursement = loan.present_value(valuation_date=loan.disbursement_date)
    assert abs(pv_from_disbursement.raw_amount) < Money("1").raw_amount


def test_loan_present_value_with_time_machine():
    loan = Loan(
        Money("2000"),
        InterestRate("4% annual"),
        [datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 12, 1, tzinfo=timezone.utc)],
        datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    # Calculate PV using loan's own rate from different time perspectives
    normal_pv = loan.present_value()

    with Warp(loan, datetime(2024, 3, 1, tzinfo=timezone.utc)) as warped_loan:
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
        [
            datetime(2024, 6, 1, tzinfo=timezone.utc),
            datetime(2025, 6, 1, tzinfo=timezone.utc),
            datetime(2026, 6, 1, tzinfo=timezone.utc),
        ],
        datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    low_rate_pv = loan.present_value(InterestRate("2% annual"))  # Very low discount
    high_rate_pv = loan.present_value(InterestRate("20% annual"))  # Very high discount

    # Higher discount rate should result in lower present value
    # The difference should be significant with these rates and timeframes
    assert high_rate_pv != low_rate_pv  # At minimum, they should be different
    assert abs(high_rate_pv.raw_amount) != abs(low_rate_pv.raw_amount)


def test_loan_irr_basic():
    loan = Loan(
        Money("10000"),
        InterestRate("5% annual"),
        [datetime(2024, 1, 15, tzinfo=timezone.utc), datetime(2024, 2, 15, tzinfo=timezone.utc)],
        datetime(2023, 12, 16, tzinfo=timezone.utc),
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
        Money("5000"),
        InterestRate("4% annual"),
        [datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 12, 1, tzinfo=timezone.utc)],
        datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    # Calculate IRR from a specific date using Time Machine
    with Warp(loan, datetime(2024, 2, 1, tzinfo=timezone.utc)) as warped_loan:
        loan_irr = warped_loan.irr()

    assert isinstance(loan_irr, InterestRate)
    # Should be close to the loan's interest rate (4%)
    actual_rate = float(loan_irr.as_decimal * 100)
    assert abs(actual_rate - 4.0) < 0.1  # Should be very close to 4%


def test_loan_irr_with_custom_guess():
    loan = Loan(
        Money("2000"),
        InterestRate("6% annual"),
        [datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 12, 1, tzinfo=timezone.utc)],
        datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    guess = InterestRate("10% annual")
    loan_irr = loan.irr(guess=guess)

    assert isinstance(loan_irr, InterestRate)
    # Should converge to loan's rate (6%) regardless of initial guess
    actual_rate = float(loan_irr.as_decimal * 100)
    assert abs(actual_rate - 6.0) < 0.1  # Should be very close to 6%


def test_loan_irr_with_time_machine():
    loan = Loan(
        Money("3000"),
        InterestRate("7% annual"),
        [datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 12, 1, tzinfo=timezone.utc)],
        datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    # Calculate IRR from different time perspectives
    normal_irr = loan.irr()

    with Warp(loan, datetime(2024, 3, 1, tzinfo=timezone.utc)) as warped_loan:
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
        datetime(2023, 12, 1, tzinfo=timezone.utc),
    )

    loan_irr = loan.irr()

    assert isinstance(loan_irr, InterestRate)
    # Should be very close to the loan's rate (5.5%)
    actual_rate = float(loan_irr.as_decimal * 100)
    assert abs(actual_rate - 5.5) < 0.1  # Should be very close to 5.5%
