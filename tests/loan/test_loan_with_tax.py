"""Tests for Loan integration with taxes."""

from datetime import datetime
from decimal import Decimal

import pytest

from money_warp import IOF, CompoundingFrequency, InterestRate, Loan, Money, PriceScheduler, grossup, grossup_loan


@pytest.fixture
def standard_iof():
    return IOF(daily_rate=Decimal("0.000082"), additional_rate=Decimal("0.0038"))


@pytest.fixture
def disbursement_date():
    return datetime(2024, 1, 1)


@pytest.fixture
def due_dates():
    return [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]


@pytest.fixture
def interest_rate():
    return InterestRate("2% monthly")


@pytest.fixture
def loan_with_tax(standard_iof, interest_rate, due_dates, disbursement_date):
    return Loan(
        principal=Money("10000"),
        interest_rate=interest_rate,
        due_dates=due_dates,
        disbursement_date=disbursement_date,
        taxes=[standard_iof],
    )


@pytest.fixture
def loan_without_tax(interest_rate, due_dates, disbursement_date):
    return Loan(
        principal=Money("10000"),
        interest_rate=interest_rate,
        due_dates=due_dates,
        disbursement_date=disbursement_date,
    )


def test_loan_with_tax_total_tax_is_positive(loan_with_tax):
    assert loan_with_tax.total_tax.is_positive()


def test_loan_without_tax_total_tax_is_zero(loan_without_tax):
    assert loan_without_tax.total_tax.is_zero()


def test_loan_with_tax_net_disbursement_less_than_principal(loan_with_tax):
    assert loan_with_tax.net_disbursement < loan_with_tax.principal


def test_loan_without_tax_net_disbursement_equals_principal(loan_without_tax):
    assert loan_without_tax.net_disbursement == loan_without_tax.principal


def test_loan_with_tax_net_plus_tax_equals_principal(loan_with_tax):
    assert loan_with_tax.net_disbursement + loan_with_tax.total_tax == loan_with_tax.principal


def test_loan_tax_amounts_keyed_by_class_name(loan_with_tax):
    assert "IOF" in loan_with_tax.tax_amounts


def test_loan_tax_amounts_has_per_installment_details(loan_with_tax):
    iof_result = loan_with_tax.tax_amounts["IOF"]
    assert len(iof_result.per_installment) == 3


def test_loan_cash_flow_includes_tax_item(loan_with_tax):
    cf = loan_with_tax.generate_expected_cash_flow()
    tax_items = [item for item in cf if item.category == "expected_tax"]
    assert len(tax_items) == 1


def test_loan_cash_flow_tax_item_amount(loan_with_tax):
    cf = loan_with_tax.generate_expected_cash_flow()
    tax_items = [item for item in cf if item.category == "expected_tax"]
    assert tax_items[0].amount == -loan_with_tax.total_tax


def test_loan_cash_flow_disbursement_is_principal_when_not_grossed_up(loan_with_tax):
    cf = loan_with_tax.generate_expected_cash_flow()
    disbursement_items = [item for item in cf if item.category == "expected_disbursement"]
    assert disbursement_items[0].amount == loan_with_tax.principal


def test_loan_without_tax_cash_flow_has_no_tax_item(loan_without_tax):
    cf = loan_without_tax.generate_expected_cash_flow()
    tax_items = [item for item in cf if item.category == "expected_tax"]
    assert len(tax_items) == 0


def test_loan_without_tax_cash_flow_disbursement_is_principal(loan_without_tax):
    cf = loan_without_tax.generate_expected_cash_flow()
    disbursement_items = [item for item in cf if item.category == "expected_disbursement"]
    assert disbursement_items[0].amount == loan_without_tax.principal


def test_loan_with_grossup_to_loan_net_disbursement(standard_iof, interest_rate, due_dates, disbursement_date):
    """to_loan() produces a loan where net_disbursement matches the requested amount."""
    result = grossup(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    loan = result.to_loan()
    assert abs(loan.net_disbursement - Money("10000")) <= Money("0.01")


def test_loan_with_grossup_to_loan_principal_is_grossed_up(standard_iof, interest_rate, due_dates, disbursement_date):
    result = grossup(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    loan = result.to_loan()
    assert loan.principal > Money("10000")


def test_loan_with_grossup_to_loan_forwards_extra_kwargs(standard_iof, interest_rate, due_dates, disbursement_date):
    result = grossup(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    loan = result.to_loan(fine_rate=Decimal("0.05"), grace_period_days=7)
    assert loan.fine_rate == Decimal("0.05")


def test_loan_with_grossup_to_loan_grace_period(standard_iof, interest_rate, due_dates, disbursement_date):
    result = grossup(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    loan = result.to_loan(grace_period_days=5)
    assert loan.grace_period_days == 5


def test_loan_tax_cache_returns_same_result(loan_with_tax):
    first_call = loan_with_tax.tax_amounts
    second_call = loan_with_tax.tax_amounts
    assert first_call is second_call


def test_loan_backward_compatible_existing_behavior(loan_without_tax):
    """Verify that loans without taxes behave exactly as before."""
    assert loan_without_tax.principal == Money("10000")
    assert loan_without_tax.taxes == []
    assert loan_without_tax.principal_balance == Money("10000")


def test_loan_not_grossed_up_cash_flow_day0_net_equals_net_disbursement(loan_with_tax):
    cf = loan_with_tax.generate_expected_cash_flow()
    day0 = loan_with_tax.disbursement_date
    day0_net = Money(sum(item.amount.raw_amount for item in cf if item.datetime == day0))
    assert day0_net == loan_with_tax.net_disbursement


def test_grossup_loan_is_grossed_up_flag():
    loan = grossup_loan(
        requested_amount=Money("1000"),
        interest_rate=InterestRate(0.0399, CompoundingFrequency.MONTHLY),
        due_dates=[datetime(2024, 9, 20), datetime(2024, 10, 20)],
        disbursement_date=datetime(2024, 8, 28),
        scheduler=PriceScheduler,
        taxes=[IOF(daily_rate="0.0082%", additional_rate="0.38%")],
    )
    assert loan.is_grossed_up is True


def test_grossup_loan_cash_flow_has_no_tax_item():
    loan = grossup_loan(
        requested_amount=Money("1000"),
        interest_rate=InterestRate(0.0399, CompoundingFrequency.MONTHLY),
        due_dates=[datetime(2024, 9, 20), datetime(2024, 10, 20)],
        disbursement_date=datetime(2024, 8, 28),
        scheduler=PriceScheduler,
        taxes=[IOF(daily_rate="0.0082%", additional_rate="0.38%")],
    )
    cf = loan.generate_expected_cash_flow()
    tax_items = [item for item in cf if item.category == "expected_tax"]
    assert len(tax_items) == 0


def test_grossup_loan_cash_flow_disbursement_equals_net_disbursement():
    loan = grossup_loan(
        requested_amount=Money("1000"),
        interest_rate=InterestRate(0.0399, CompoundingFrequency.MONTHLY),
        due_dates=[datetime(2024, 9, 20), datetime(2024, 10, 20)],
        disbursement_date=datetime(2024, 8, 28),
        scheduler=PriceScheduler,
        taxes=[IOF(daily_rate="0.0082%", additional_rate="0.38%")],
    )
    cf = loan.generate_expected_cash_flow()
    disbursement_items = [item for item in cf if item.category == "expected_disbursement"]
    assert disbursement_items[0].amount == loan.net_disbursement


def test_grossup_loan_irr_not_inflated_by_double_counted_tax():
    loan = grossup_loan(
        requested_amount=Money("1000"),
        interest_rate=InterestRate(0.0399, CompoundingFrequency.MONTHLY),
        due_dates=[datetime(2024, 9, 20), datetime(2024, 10, 20)],
        disbursement_date=datetime(2024, 8, 28),
        scheduler=PriceScheduler,
        taxes=[IOF(daily_rate="0.0082%", additional_rate="0.38%")],
    )
    irr = loan.irr()
    assert abs(irr.as_decimal - Decimal("0.710526")) < Decimal("0.01")
