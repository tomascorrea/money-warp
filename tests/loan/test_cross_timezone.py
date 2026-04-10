"""Tests for cross-timezone loan behaviour.

Verifies that a loan disbursed late at night in BRT (which is the next
calendar day in UTC) stores the datetime as UTC internally but resolves
all calendar dates — disbursement, schedule day counts, payment dates —
in the configured business timezone (BRT).
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from money_warp import InterestRate, Loan, Money
from money_warp.tz import get_tz, set_tz, to_date

SP = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def brt_timezone():
    """Configure the business timezone to America/Sao_Paulo for the test."""
    original = get_tz()
    set_tz("America/Sao_Paulo")
    yield
    set_tz(original)


# --- Disbursement date resolution ---


def test_loan_disbursement_stored_as_utc_resolved_as_brt(brt_timezone):
    """10pm BRT Jan 15 is stored as 1am UTC Jan 16, but to_date gives Jan 15."""
    disbursement = datetime(2024, 1, 15, 22, 0, 0, tzinfo=SP)

    loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15), date(2024, 3, 15)],
        disbursement_date=disbursement,
    )

    assert loan.disbursement_date.tzinfo == timezone.utc
    assert loan.disbursement_date == datetime(2024, 1, 16, 1, 0, 0, tzinfo=timezone.utc)
    assert to_date(loan.disbursement_date) == date(2024, 1, 15)


def test_loan_due_date_on_utc_next_day_accepted(brt_timezone):
    """Due date on Jan 16 is valid because BRT disbursement is Jan 15.

    Without the two-timezone architecture the UTC date (Jan 16) would
    equal the first due date and raise ValueError.
    """
    disbursement = datetime(2024, 1, 15, 22, 0, 0, tzinfo=SP)

    loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 1, 16)],
        disbursement_date=disbursement,
    )

    schedule = loan.get_original_schedule()
    assert schedule[0].days_in_period == 1
    assert schedule[0].due_date == date(2024, 1, 16)


# --- Schedule day counts ---


def test_loan_schedule_counts_days_from_brt_date(brt_timezone):
    """Day counts use BRT dates: Jan 15 → Feb 15 = 31 days.

    If UTC dates were used, Jan 16 → Feb 15 would give 30 days.
    """
    disbursement = datetime(2024, 1, 15, 22, 0, 0, tzinfo=SP)

    loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15), date(2024, 3, 15)],
        disbursement_date=disbursement,
    )

    schedule = loan.get_original_schedule()
    assert schedule[0].days_in_period == 31
    assert schedule[1].days_in_period == 29


# --- Payment date resolution ---


def test_loan_payment_cross_midnight_brt_resolves_correctly(brt_timezone):
    """Payment at 11pm BRT Feb 15 resolves to Feb 15, not UTC's Feb 16."""
    disbursement = datetime(2024, 1, 15, 22, 0, 0, tzinfo=SP)

    loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15), date(2024, 3, 15)],
        disbursement_date=disbursement,
    )

    payment_dt = datetime(2024, 2, 15, 23, 0, 0, tzinfo=SP)
    settlement = loan.record_payment(Money("500"), payment_dt)

    assert settlement.payment_amount == Money("500")
    assert to_date(settlement.payment_date) == date(2024, 2, 15)
    assert settlement.payment_date.tzinfo == timezone.utc


# --- Amortization schedule after payment ---


def test_loan_amortization_schedule_uses_brt_dates_after_payment(brt_timezone):
    """Post-payment amortization schedule entries use BRT dates."""
    disbursement = datetime(2024, 1, 15, 22, 0, 0, tzinfo=SP)

    loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15), date(2024, 3, 15)],
        disbursement_date=disbursement,
    )

    payment_dt = datetime(2024, 2, 15, 23, 0, 0, tzinfo=SP)
    loan.record_payment(loan.get_original_schedule()[0].payment_amount, payment_dt)

    amort = loan.get_amortization_schedule()
    assert amort[0].due_date == date(2024, 2, 15)
    assert amort[0].days_in_period == 31
