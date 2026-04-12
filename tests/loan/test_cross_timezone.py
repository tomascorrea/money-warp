"""Tests for cross-timezone loan behaviour.

Verifies that a loan disbursed late at night in BRT (which is the next
calendar day in UTC) stores the datetime as UTC internally but resolves
all calendar dates — disbursement, schedule day counts, payment dates —
in the configured business timezone (BRT).

Also verifies the per-loan timezone: two loans in different timezones
can coexist and each resolves dates in its own timezone.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from money_warp import InterestRate, Loan, Money
from money_warp.tz import get_tz, set_tz, to_date
from money_warp.warp import Warp

SP = ZoneInfo("America/Sao_Paulo")
TOKYO = ZoneInfo("Asia/Tokyo")


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
    assert to_date(loan.disbursement_date, SP) == date(2024, 1, 15)


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
    assert to_date(settlement.payment_date, SP) == date(2024, 2, 15)
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


# --- Fixture: loan with two cross-midnight BRT payments ---


@pytest.fixture
def loan_with_two_brt_payments(brt_timezone):
    """Loan with two payments at 11pm BRT (next day in UTC).

    Disbursement: 10pm BRT Jan 15 = 1am UTC Jan 16
    Payment 1:    11pm BRT Feb 15 = 2am UTC Feb 16  (pays installment 1)
    Payment 2:    11pm BRT Mar 15 = 2am UTC Mar 16  (pays installment 2)
    """
    disbursement = datetime(2024, 1, 15, 22, 0, 0, tzinfo=SP)

    loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15), date(2024, 3, 15)],
        disbursement_date=disbursement,
    )

    schedule = loan.get_original_schedule()
    loan.record_payment(schedule[0].payment_amount, datetime(2024, 2, 15, 23, 0, 0, tzinfo=SP))
    loan.record_payment(schedule[1].payment_amount, datetime(2024, 3, 15, 23, 0, 0, tzinfo=SP))

    return loan


# --- Warp with cross-midnight BRT payments ---


def test_warp_next_brt_day_sees_cross_midnight_payment(loan_with_two_brt_payments):
    """Warp to Feb 16 includes a payment made at 11pm BRT Feb 15.

    The payment is stored as 2am UTC Feb 16.  Warp to date(2024, 2, 16)
    creates midnight BRT Feb 16 = 3am UTC Feb 16, which is AFTER the
    payment (2am UTC).  So the payment is visible.

    If the Warp target were midnight UTC instead of midnight BRT,
    the payment at 2am UTC would be AFTER midnight UTC and would be
    excluded — wrong.
    """
    loan = loan_with_two_brt_payments

    with Warp(loan, date(2024, 2, 16)) as warped:
        assert len(warped.settlements) == 1
        assert to_date(warped.settlements[0].payment_date, SP) == date(2024, 2, 15)
        assert warped.principal_balance == Money("502.56")
        assert warped.days_since_last_payment() == 1
        assert warped.interest_balance == Money("0.16")


def test_warp_between_payments_sees_only_first(loan_with_two_brt_payments):
    """Warp to Mar 1 sees only payment 1, with 15 BRT days of accrual."""
    loan = loan_with_two_brt_payments

    with Warp(loan, date(2024, 3, 1)) as warped:
        assert len(warped.settlements) == 1
        assert warped.principal_balance == Money("502.56")
        assert warped.days_since_last_payment() == 15
        assert warped.interest_balance == Money("2.35")


def test_warp_five_brt_days_after_payment_correct_day_count(loan_with_two_brt_payments):
    """Warp to Feb 20: 5 BRT days since payment at 11pm BRT Feb 15.

    If UTC dates were used for day counting, the last payment date
    would be Feb 16 (UTC) giving 4 days instead of 5.
    """
    loan = loan_with_two_brt_payments

    with Warp(loan, date(2024, 2, 20)) as warped:
        assert warped.days_since_last_payment() == 5
        assert warped.interest_balance == Money("0.78")


def test_warp_after_both_payments_loan_paid_off(loan_with_two_brt_payments):
    """Warp to Mar 16 sees both cross-midnight BRT payments; loan is paid off."""
    loan = loan_with_two_brt_payments

    with Warp(loan, date(2024, 3, 16)) as warped:
        assert len(warped.settlements) == 2
        assert warped.is_paid_off is True


# ===================================================================
# Per-loan timezone: two loans in different timezones coexisting
# ===================================================================


def test_per_loan_tz_stored_on_time_context():
    """Loan.tz parameter flows into TimeContext."""
    loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15)],
        disbursement_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        tz=SP,
    )
    assert loan._time_ctx.tz == SP


def test_per_loan_tz_accepts_string():
    """tz='America/Sao_Paulo' is resolved to ZoneInfo."""
    loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15)],
        disbursement_date=datetime(2024, 1, 15, tzinfo=timezone.utc),
        tz="America/Sao_Paulo",
    )
    assert loan._time_ctx.tz == SP


def test_two_loans_different_tz_coexist():
    """Two loans with different timezones resolve the same UTC instant
    to different calendar dates without interfering.

    10:30pm BRT Jan 15 = 1:30am UTC Jan 16 = 10:30am JST Jan 16.
    BRT loan: disbursement date = Jan 15 (still Jan 15 in BRT).
    Tokyo loan: disbursement date = Jan 16 (already Jan 16 in JST).
    """
    utc_instant = datetime(2024, 1, 16, 1, 30, 0, tzinfo=timezone.utc)

    brt_loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15)],
        disbursement_date=utc_instant,
        tz=SP,
    )

    tokyo_loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15)],
        disbursement_date=utc_instant,
        tz=TOKYO,
    )

    brt_schedule = brt_loan.get_original_schedule()
    tokyo_schedule = tokyo_loan.get_original_schedule()

    assert brt_schedule[0].days_in_period == 31
    assert tokyo_schedule[0].days_in_period == 30


def test_two_loans_different_tz_independent_schedules():
    """Changing global set_tz does not affect per-loan timezone."""
    original_tz = get_tz()
    try:
        set_tz(timezone.utc)
        brt_loan = Loan(
            Money("1000"),
            InterestRate("12% annual"),
            [date(2024, 2, 15)],
            disbursement_date=datetime(2024, 1, 16, 1, 30, 0, tzinfo=timezone.utc),
            tz=SP,
        )

        set_tz("Asia/Tokyo")
        brt_schedule = brt_loan.get_original_schedule()
        assert brt_schedule[0].days_in_period == 31
    finally:
        set_tz(original_tz)


def test_warp_uses_per_loan_tz_for_date_resolution():
    """Warp(date) interprets the target date in the loan's timezone."""
    utc_instant = datetime(2024, 1, 16, 1, 30, 0, tzinfo=timezone.utc)

    loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15), date(2024, 3, 15)],
        disbursement_date=utc_instant,
        tz=SP,
    )

    payment_dt = datetime(2024, 2, 15, 23, 0, 0, tzinfo=SP)
    loan.record_payment(loan.get_original_schedule()[0].payment_amount, payment_dt)

    with Warp(loan, date(2024, 2, 16)) as warped:
        assert len(warped.settlements) == 1
        assert warped.days_since_last_payment() == 1


def test_warp_with_different_per_loan_tz_gives_different_views():
    """Two loans in different timezones see different states at the same
    warp target date.

    Payment at 2am UTC Feb 16 = 11pm BRT Feb 15 = 11am JST Feb 16.
    Warp to date(2024, 2, 16):
      BRT: midnight BRT Feb 16 = 3am UTC Feb 16 -> after payment -> 1 settlement
      JST: midnight JST Feb 16 = 3pm UTC Feb 15 -> before payment -> 0 settlements
    """
    utc_instant = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    payment_utc = datetime(2024, 2, 16, 2, 0, 0, tzinfo=timezone.utc)

    brt_loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15), date(2024, 3, 15)],
        disbursement_date=utc_instant,
        tz=SP,
    )
    brt_loan.record_payment(Money("500"), payment_utc)

    tokyo_loan = Loan(
        Money("1000"),
        InterestRate("12% annual"),
        [date(2024, 2, 15), date(2024, 3, 15)],
        disbursement_date=utc_instant,
        tz=TOKYO,
    )
    tokyo_loan.record_payment(Money("500"), payment_utc)

    with Warp(brt_loan, date(2024, 2, 16)) as brt_warped:
        brt_settlements = len(brt_warped.settlements)

    with Warp(tokyo_loan, date(2024, 2, 16)) as tokyo_warped:
        tokyo_settlements = len(tokyo_warped.settlements)

    assert brt_settlements == 1
    assert tokyo_settlements == 0
