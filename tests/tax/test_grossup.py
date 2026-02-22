"""Tests for the grossup function (financed tax calculation)."""

from datetime import datetime
from decimal import Decimal

import pytest

from money_warp import (
    IOF,
    InterestRate,
    InvertedPriceScheduler,
    Loan,
    Money,
    PriceScheduler,
    grossup,
    grossup_loan,
)


@pytest.fixture
def standard_iof():
    return IOF(daily_rate=Decimal("0.000082"), additional_rate=Decimal("0.0038"))


@pytest.fixture
def disbursement_date():
    return datetime(2024, 1, 1)


@pytest.fixture
def three_due_dates():
    return [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)]


@pytest.fixture
def interest_rate():
    return InterestRate("2% monthly")


def test_grossup_principal_greater_than_requested(standard_iof, interest_rate, three_due_dates, disbursement_date):
    result = grossup(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=three_due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    assert result.principal > Money("10000")


def test_grossup_requested_amount_preserved(standard_iof, interest_rate, three_due_dates, disbursement_date):
    result = grossup(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=three_due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    assert result.requested_amount == Money("10000")


def test_grossup_principal_minus_tax_equals_requested(standard_iof, interest_rate, three_due_dates, disbursement_date):
    result = grossup(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=three_due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    net = result.principal - result.total_tax
    assert abs(net - result.requested_amount) <= Money("0.01")


def test_grossup_tax_is_positive(standard_iof, interest_rate, three_due_dates, disbursement_date):
    result = grossup(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=three_due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    assert result.total_tax.is_positive()


def test_grossup_with_inverted_price_scheduler(standard_iof, interest_rate, three_due_dates, disbursement_date):
    result = grossup(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=three_due_dates,
        disbursement_date=disbursement_date,
        scheduler=InvertedPriceScheduler,
        taxes=[standard_iof],
    )
    net = result.principal - result.total_tax
    assert abs(net - result.requested_amount) <= Money("0.01")


def test_grossup_single_installment(standard_iof, interest_rate, disbursement_date):
    result = grossup(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=[datetime(2024, 2, 1)],
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    net = result.principal - result.total_tax
    assert abs(net - result.requested_amount) <= Money("0.01")


def test_grossup_small_amount(standard_iof, interest_rate, disbursement_date):
    result = grossup(
        requested_amount=Money("100"),
        interest_rate=interest_rate,
        due_dates=[datetime(2024, 2, 1)],
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    net = result.principal - result.total_tax
    assert abs(net - result.requested_amount) <= Money("0.01")


def test_grossup_large_amount(standard_iof, interest_rate, disbursement_date):
    result = grossup(
        requested_amount=Money("1000000"),
        interest_rate=interest_rate,
        due_dates=[datetime(2024, 2, 1), datetime(2024, 3, 1)],
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    net = result.principal - result.total_tax
    assert abs(net - result.requested_amount) <= Money("0.01")


def test_grossup_raises_on_zero_requested_amount(standard_iof, interest_rate, disbursement_date):
    with pytest.raises(ValueError, match="requested_amount must be positive"):
        grossup(
            requested_amount=Money("0"),
            interest_rate=interest_rate,
            due_dates=[datetime(2024, 2, 1)],
            disbursement_date=disbursement_date,
            scheduler=PriceScheduler,
            taxes=[standard_iof],
        )


def test_grossup_raises_on_negative_requested_amount(standard_iof, interest_rate, disbursement_date):
    with pytest.raises(ValueError, match="requested_amount must be positive"):
        grossup(
            requested_amount=Money("-1000"),
            interest_rate=interest_rate,
            due_dates=[datetime(2024, 2, 1)],
            disbursement_date=disbursement_date,
            scheduler=PriceScheduler,
            taxes=[standard_iof],
        )


def test_grossup_raises_on_empty_taxes(interest_rate, disbursement_date):
    with pytest.raises(ValueError, match="At least one tax is required"):
        grossup(
            requested_amount=Money("10000"),
            interest_rate=interest_rate,
            due_dates=[datetime(2024, 2, 1)],
            disbursement_date=disbursement_date,
            scheduler=PriceScheduler,
            taxes=[],
        )


def test_grossup_with_multiple_taxes(interest_rate, three_due_dates, disbursement_date):
    iof1 = IOF(daily_rate=Decimal("0.000082"), additional_rate=Decimal("0"))
    iof2 = IOF(daily_rate=Decimal("0"), additional_rate=Decimal("0.0038"))
    result = grossup(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=three_due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[iof1, iof2],
    )
    net = result.principal - result.total_tax
    assert abs(net - result.requested_amount) <= Money("0.01")


# --- grossup_loan tests ---


def test_grossup_loan_returns_loan_instance(standard_iof, interest_rate, three_due_dates, disbursement_date):
    loan = grossup_loan(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=three_due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    assert isinstance(loan, Loan)


def test_grossup_loan_net_disbursement_matches_requested(
    standard_iof, interest_rate, three_due_dates, disbursement_date
):
    loan = grossup_loan(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=three_due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    assert abs(loan.net_disbursement - Money("10000")) <= Money("0.01")


def test_grossup_loan_principal_is_grossed_up(standard_iof, interest_rate, three_due_dates, disbursement_date):
    loan = grossup_loan(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=three_due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
    )
    assert loan.principal > Money("10000")


def test_grossup_loan_forwards_fine_rate(standard_iof, interest_rate, three_due_dates, disbursement_date):
    loan = grossup_loan(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=three_due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
        fine_rate=Decimal("0.05"),
    )
    assert loan.fine_rate == Decimal("0.05")


def test_grossup_loan_forwards_grace_period(standard_iof, interest_rate, three_due_dates, disbursement_date):
    loan = grossup_loan(
        requested_amount=Money("10000"),
        interest_rate=interest_rate,
        due_dates=three_due_dates,
        disbursement_date=disbursement_date,
        scheduler=PriceScheduler,
        taxes=[standard_iof],
        grace_period_days=7,
    )
    assert loan.grace_period_days == 7
