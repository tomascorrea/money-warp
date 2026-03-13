"""Tests for Loan balance properties and balance composition."""

from datetime import datetime, timezone

from money_warp import InterestRate, Loan, Money, Warp


def test_loan_initial_current_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]
    disbursement_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

    loan = Loan(principal, rate, due_dates, disbursement_date=disbursement_date)

    # At disbursement time, current balance should equal principal (no accrued interest yet)
    with Warp(loan, disbursement_date) as warped_loan:
        assert warped_loan.current_balance == principal


def test_loan_last_payment_date_initial():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]
    disbursement_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    assert loan.last_payment_date == disbursement_date


def test_loan_days_since_last_payment_initial():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]
    disbursement_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

    loan = Loan(principal, rate, due_dates, disbursement_date)
    check_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    assert loan.days_since_last_payment(check_date) == 14


def test_loan_days_since_last_payment_defaults_to_now():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    # Should not raise error and return some number
    days = loan.days_since_last_payment()
    assert isinstance(days, int)


def test_loan_principal_balance_initial():
    """Test principal_balance property returns original principal initially."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))

    assert loan.principal_balance == principal


def test_loan_principal_balance_after_payment():
    """Test principal_balance decreases after principal payments."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    initial_principal = loan.principal_balance

    # Make a payment
    loan.record_payment(Money("1000.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))

    # Principal balance should be reduced
    assert loan.principal_balance < initial_principal
    assert loan.principal_balance > Money.zero()


def test_loan_principal_balance_zero_after_full_payment():
    """Test principal_balance becomes zero after full principal is paid."""
    principal = Money("1000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))

    # Make overpayment to cover all principal
    loan.record_payment(Money("2000.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))

    assert loan.principal_balance == Money.zero()


def test_loan_interest_balance_initial_zero():
    """Test interest_balance is zero at disbursement time."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]
    disbursement_date = datetime(2024, 1, 1, tzinfo=timezone.utc)

    loan = Loan(principal, rate, due_dates, disbursement_date=disbursement_date)

    with Warp(loan, disbursement_date) as warped_loan:
        assert warped_loan.interest_balance == Money.zero()


def test_loan_interest_balance_grows_over_time():
    """Test interest_balance increases over time."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))

    with Warp(loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as warped_loan:
        interest_after_14_days = warped_loan.interest_balance

    with Warp(loan, datetime(2024, 1, 30, tzinfo=timezone.utc)) as warped_loan:
        interest_after_29_days = warped_loan.interest_balance

    assert interest_after_14_days > Money.zero()
    assert interest_after_29_days > interest_after_14_days


def test_loan_interest_balance_resets_after_payment():
    """Test interest_balance resets after interest payment."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))

    with Warp(loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as warped_loan:
        interest_before_payment = warped_loan.interest_balance

    assert interest_before_payment > Money.zero()

    loan.record_payment(Money("100.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))

    with Warp(loan, datetime(2024, 1, 16, tzinfo=timezone.utc)) as warped_loan:
        interest_after_payment = warped_loan.interest_balance

    assert interest_after_payment < interest_before_payment


def test_loan_current_balance_composition():
    """Test current_balance equals sum of four component balances."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
    )

    with Warp(loan, datetime(2024, 2, 5, tzinfo=timezone.utc)) as warped_loan:
        warped_loan.calculate_late_fines(datetime(2024, 2, 5, tzinfo=timezone.utc))

        principal_bal = warped_loan.principal_balance
        interest = warped_loan.interest_balance
        mora = warped_loan.mora_interest_balance
        fines = warped_loan.fine_balance
        current_bal = warped_loan.current_balance

        expected_balance = principal_bal + interest + mora + fines
        assert current_bal == expected_balance


def test_loan_balance_components_with_payments():
    """Test balance components work correctly with multiple payments."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc), datetime(2024, 3, 1, tzinfo=timezone.utc)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))

    loan.record_payment(Money("500.00"), datetime(2024, 1, 15, tzinfo=timezone.utc))

    with Warp(loan, datetime(2024, 1, 20, tzinfo=timezone.utc)) as warped_loan:
        principal_bal = warped_loan.principal_balance
        interest = warped_loan.interest_balance
        mora = warped_loan.mora_interest_balance
        fines = warped_loan.fine_balance
        current_bal = warped_loan.current_balance

        assert principal_bal < principal
        assert interest > Money.zero()
        assert current_bal == principal_bal + interest + mora + fines


def test_loan_balance_components_with_fines_and_payments():
    """Test balance components with fines and payments interaction."""
    principal = Money("5000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("3% annual"),
    )

    with Warp(loan, datetime(2024, 2, 10, tzinfo=timezone.utc)) as warped_loan:
        warped_loan.calculate_late_fines(datetime(2024, 2, 10, tzinfo=timezone.utc))
        fines_before_payment = warped_loan.fine_balance

    assert fines_before_payment > Money.zero()

    loan.record_payment(Money("1000.00"), datetime(2024, 2, 10, tzinfo=timezone.utc))

    with Warp(loan, datetime(2024, 2, 15, tzinfo=timezone.utc)) as warped_loan:
        principal_bal = warped_loan.principal_balance
        interest = warped_loan.interest_balance
        mora = warped_loan.mora_interest_balance
        fines = warped_loan.fine_balance
        current_bal = warped_loan.current_balance

        assert fines < fines_before_payment
        assert principal_bal < principal
        assert current_bal == principal_bal + interest + mora + fines
