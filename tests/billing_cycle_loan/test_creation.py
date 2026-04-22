"""Tests for BillingCycleLoan construction and date derivation."""

from datetime import date, datetime, timezone

import pytest

from money_warp import BillingCycleLoan, InterestRate, Money
from money_warp.billing_cycle import MonthlyBillingCycle


def test_due_dates_derived_from_billing_cycle(simple_loan):
    assert simple_loan.due_dates == [
        date(2025, 2, 12),
        date(2025, 3, 15),
        date(2025, 4, 12),
    ]


def test_closing_dates_derived_from_billing_cycle(simple_loan):
    closing = [cd.date() for cd in simple_loan.closing_dates]
    assert closing == [
        date(2025, 1, 28),
        date(2025, 2, 28),
        date(2025, 3, 28),
    ]


def test_explicit_due_dates_on_billing_cycle():
    explicit = [date(2025, 2, 10), date(2025, 3, 10), date(2025, 4, 10)]
    bc = MonthlyBillingCycle(closing_day=28, payment_due_days=15, due_dates=explicit)
    loan = BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=bc,
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    assert loan.due_dates == [date(2025, 2, 10), date(2025, 3, 10), date(2025, 4, 10)]


def test_explicit_due_dates_with_start_date_far_before_first_due():
    """All explicit due dates are preserved when start_date is more than one cycle before the first due date."""
    explicit = [date(2025, 11, 15), date(2025, 12, 15)]
    bc = MonthlyBillingCycle(closing_day=1, payment_due_days=15, due_dates=explicit)
    loan = BillingCycleLoan(
        principal=Money("1000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=bc,
        start_date=datetime(2025, 9, 15, tzinfo=timezone.utc),
        num_installments=2,
        disbursement_date=datetime(2025, 9, 15, tzinfo=timezone.utc),
    )
    assert loan.due_dates == [date(2025, 11, 15), date(2025, 12, 15)]
    assert len(loan.installments) == 2
    closing = [cd.date() for cd in loan.closing_dates]
    assert closing == [date(2025, 11, 1), date(2025, 12, 1)]


def test_principal_must_be_positive(billing_cycle):
    with pytest.raises(ValueError, match="Principal must be positive"):
        BillingCycleLoan(
            principal=Money("0.00"),
            interest_rate=InterestRate("12% a"),
            billing_cycle=billing_cycle,
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            num_installments=3,
        )


def test_num_installments_must_be_positive(billing_cycle):
    with pytest.raises(ValueError, match="num_installments must be at least 1"):
        BillingCycleLoan(
            principal=Money("3000.00"),
            interest_rate=InterestRate("12% a"),
            billing_cycle=billing_cycle,
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            num_installments=0,
        )


def test_disbursement_must_be_before_first_due(billing_cycle):
    with pytest.raises(ValueError, match="disbursement_date must be before"):
        BillingCycleLoan(
            principal=Money("3000.00"),
            interest_rate=InterestRate("12% a"),
            billing_cycle=billing_cycle,
            start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            num_installments=3,
            disbursement_date=datetime(2025, 3, 1, tzinfo=timezone.utc),
        )


def test_mora_defaults_to_interest_rate(simple_loan):
    assert simple_loan.mora_interest_rate == simple_loan.interest_rate


def test_original_schedule_has_correct_num_entries(simple_loan):
    schedule = simple_loan.get_original_schedule()
    assert len(schedule) == 3


def test_first_due_date_before_first_closing_date():
    """Loan with start_date between closing_day and first due date must not crash."""
    from zoneinfo import ZoneInfo

    SAO_PAULO = ZoneInfo("America/Sao_Paulo")
    bc = MonthlyBillingCycle(
        due_dates=[
            date(2025, 11, 20),
            date(2025, 12, 20),
            date(2026, 1, 20),
            date(2026, 2, 20),
        ],
    )
    loan = BillingCycleLoan(
        principal=Money(1000),
        interest_rate=InterestRate("3% a.m."),
        billing_cycle=bc,
        start_date=datetime(2025, 11, 12, tzinfo=SAO_PAULO),
        num_installments=4,
        disbursement_date=datetime(2025, 11, 12, tzinfo=SAO_PAULO),
        tz=SAO_PAULO,
    )
    assert loan.due_dates == [
        date(2025, 11, 20),
        date(2025, 12, 20),
        date(2026, 1, 20),
        date(2026, 2, 20),
    ]
    closing = [cd.date() for cd in loan.closing_dates]
    assert closing == [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]
    assert len(loan.get_original_schedule()) == 4
