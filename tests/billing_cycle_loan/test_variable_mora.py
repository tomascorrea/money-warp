"""Tests for variable mora rate resolution via MoraRateResolver."""

from datetime import date, datetime, timezone

from money_warp import BillingCycleLoan, InterestRate, Money
from money_warp.billing_cycle import MonthlyBillingCycle


def test_variable_mora_same_as_constant_when_resolver_passes_through():
    """When the resolver returns the base rate unchanged, results match constant."""
    bc = MonthlyBillingCycle(closing_day=28, payment_due_days=15)
    passthrough = lambda ref, base: base

    loan_var = BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=bc,
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        mora_interest_rate=InterestRate("12% a"),
        mora_rate_resolver=passthrough,
    )
    loan_const = BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=bc,
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        mora_interest_rate=InterestRate("12% a"),
    )

    late_dt = datetime(2025, 3, 4, tzinfo=timezone.utc)
    sv = loan_var.record_payment(Money("1022.58"), late_dt)
    sc = loan_const.record_payment(Money("1022.58"), late_dt)

    assert sv.mora_paid == sc.mora_paid
    assert sv.interest_paid == sc.interest_paid
    assert sv.principal_paid == sc.principal_paid


def test_doubled_mora_charges_more_than_constant(variable_mora_loan):
    """When mora doubles after Feb 28, late inst 3 (cycle Mar 28) charges more."""
    variable_mora_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 2, 12, tzinfo=timezone.utc),
    )
    variable_mora_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 15, tzinfo=timezone.utc),
    )

    bc = MonthlyBillingCycle(closing_day=28, payment_due_days=15)
    constant_loan = BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=bc,
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        mora_interest_rate=InterestRate("12% a"),
    )
    constant_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 2, 12, tzinfo=timezone.utc),
    )
    constant_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 15, tzinfo=timezone.utc),
    )

    late_dt = datetime(2025, 5, 1, tzinfo=timezone.utc)
    sv = variable_mora_loan.record_payment(Money("1100.00"), late_dt)
    sc = constant_loan.record_payment(Money("1100.00"), late_dt)

    assert sv.mora_paid == Money("11.51")
    assert sc.mora_paid == Money("6.05")
    assert sv.mora_paid > sc.mora_paid


def test_variable_mora_late_first_installment_uses_base_rate(variable_mora_loan):
    """Cycle 1 closes Jan 28 (before Feb 28 threshold), so base rate applies."""
    s = variable_mora_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 4, tzinfo=timezone.utc),
    )
    assert s.fine_paid == Money("20.45")
    assert s.mora_paid == Money("18.93")
    assert s.interest_paid == Money("39.38")


def test_resolver_receives_closing_date_and_base_rate():
    """Verify the resolver is called with the correct arguments."""
    calls = []

    def tracking_resolver(ref_date: date, base: InterestRate) -> InterestRate:
        calls.append((ref_date, base))
        return base

    bc = MonthlyBillingCycle(closing_day=28, payment_due_days=15)
    loan = BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=bc,
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        mora_interest_rate=InterestRate("18% a"),
        mora_rate_resolver=tracking_resolver,
    )

    loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 4, tzinfo=timezone.utc),
    )

    assert len(calls) >= 1
    ref_date, base = calls[0]
    assert ref_date == date(2025, 1, 28)
    assert base == InterestRate("18% a")
