"""Tests for Loan balance properties, accrued interest, and balance composition."""

from datetime import datetime
from decimal import Decimal

from money_warp import InterestRate, Loan, Money, Warp


def test_loan_initial_current_balance():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date=disbursement_date)

    # At disbursement time, current balance should equal principal (no accrued interest yet)
    with Warp(loan, disbursement_date) as warped_loan:
        assert warped_loan.current_balance == principal


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

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    # Should not raise error and return some number
    days = loan.days_since_last_payment()
    assert isinstance(days, int)


def test_loan_principal_balance_initial():
    """Test principal_balance property returns original principal initially."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))

    assert loan.principal_balance == principal


def test_loan_principal_balance_after_payment():
    """Test principal_balance decreases after principal payments."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))
    initial_principal = loan.principal_balance

    # Make a payment
    loan.record_payment(Money("1000.00"), datetime(2024, 1, 15))

    # Principal balance should be reduced
    assert loan.principal_balance < initial_principal
    assert loan.principal_balance > Money.zero()


def test_loan_principal_balance_zero_after_full_payment():
    """Test principal_balance becomes zero after full principal is paid."""
    principal = Money("1000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))

    # Make overpayment to cover all principal
    loan.record_payment(Money("2000.00"), datetime(2024, 1, 15))

    assert loan.principal_balance == Money.zero()


def test_loan_accrued_interest_initial_zero():
    """Test accrued_interest is zero at disbursement time."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]
    disbursement_date = datetime(2024, 1, 1)

    loan = Loan(principal, rate, due_dates, disbursement_date=disbursement_date)

    # At disbursement time, accrued interest should be zero
    with Warp(loan, disbursement_date) as warped_loan:
        assert warped_loan.accrued_interest == Money.zero()


def test_loan_accrued_interest_grows_over_time():
    """Test accrued_interest increases over time."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))

    # Use Warp to simulate time passing
    with Warp(loan, datetime(2024, 1, 15)) as warped_loan:
        interest_after_14_days = warped_loan.accrued_interest

    with Warp(loan, datetime(2024, 1, 30)) as warped_loan:
        interest_after_29_days = warped_loan.accrued_interest

    assert interest_after_14_days > Money.zero()
    assert interest_after_29_days > interest_after_14_days


def test_loan_accrued_interest_resets_after_payment():
    """Test accrued_interest resets after interest payment."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))

    # Let interest accrue
    with Warp(loan, datetime(2024, 1, 15)) as warped_loan:
        interest_before_payment = warped_loan.accrued_interest

    assert interest_before_payment > Money.zero()

    # Make payment to cover accrued interest
    loan.record_payment(Money("100.00"), datetime(2024, 1, 15))

    # Interest should be reset (or much lower)
    with Warp(loan, datetime(2024, 1, 16)) as warped_loan:
        interest_after_payment = warped_loan.accrued_interest

    assert interest_after_payment < interest_before_payment


def test_loan_current_balance_composition():
    """Test current_balance equals principal_balance + accrued_interest + outstanding_fines."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1), fine_rate=Decimal("0.02"))

    # Let interest accrue and apply fines
    with Warp(loan, datetime(2024, 2, 5)) as warped_loan:
        warped_loan.calculate_late_fines(datetime(2024, 2, 5))

        principal_bal = warped_loan.principal_balance
        accrued_int = warped_loan.accrued_interest
        fines = warped_loan.outstanding_fines
        current_bal = warped_loan.current_balance

        # Current balance should equal sum of components
        expected_balance = principal_bal + accrued_int + fines
        assert current_bal == expected_balance


def test_loan_balance_components_with_payments():
    """Test balance components work correctly with multiple payments."""
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1), datetime(2024, 3, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1))

    # Make partial payment
    loan.record_payment(Money("500.00"), datetime(2024, 1, 15))

    with Warp(loan, datetime(2024, 1, 20)) as warped_loan:
        principal_bal = warped_loan.principal_balance
        accrued_int = warped_loan.accrued_interest
        current_bal = warped_loan.current_balance

        # Principal should be reduced
        assert principal_bal < principal

        # Interest should be accruing on remaining principal
        assert accrued_int > Money.zero()

        # Current balance should be sum of components
        assert current_bal == principal_bal + accrued_int + warped_loan.outstanding_fines


def test_loan_balance_components_with_fines_and_payments():
    """Test balance components with fines and payments interaction."""
    principal = Money("5000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1), fine_rate=Decimal("0.03"))

    # Let payment become late and apply fine
    with Warp(loan, datetime(2024, 2, 10)) as warped_loan:
        warped_loan.calculate_late_fines(datetime(2024, 2, 10))
        fines_before_payment = warped_loan.outstanding_fines

    assert fines_before_payment > Money.zero()

    # Make payment that covers fines and some principal/interest
    loan.record_payment(Money("1000.00"), datetime(2024, 2, 10))

    with Warp(loan, datetime(2024, 2, 15)) as warped_loan:
        principal_bal = warped_loan.principal_balance
        accrued_int = warped_loan.accrued_interest
        fines = warped_loan.outstanding_fines
        current_bal = warped_loan.current_balance

        # Fines should be paid first (reduced or zero)
        assert fines < fines_before_payment

        # Principal should be reduced from payment
        assert principal_bal < principal

        # Components should sum to current balance
        assert current_bal == principal_bal + accrued_int + fines
