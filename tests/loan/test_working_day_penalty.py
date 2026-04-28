"""Integration tests for Loan with working_day_calendar penalty deferral."""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money
from money_warp.working_day import (
    BrazilianWorkingDayCalendar,
    EveryDayCalendar,
    WeekendCalendar,
)


@pytest.fixture
def weekend_calendar() -> WeekendCalendar:
    return WeekendCalendar()


@pytest.fixture
def brazilian_calendar() -> BrazilianWorkingDayCalendar:
    return BrazilianWorkingDayCalendar()


def _make_loan(
    due_dates: list[date],
    calendar=None,
    grace_period_days: int = 0,
) -> Loan:
    """Helper to create a simple loan for testing."""
    return Loan(
        principal=Money("3000"),
        interest_rate=InterestRate("12% annual"),
        due_dates=due_dates,
        disbursement_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
        grace_period_days=grace_period_days,
        working_day_calendar=calendar,
    )


def test_due_date_saturday_payment_monday_no_fine(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Saturday, payment on Monday: no fine incurred."""
    # Feb 1, 2025 is Saturday
    loan = _make_loan([date(2025, 2, 1)], calendar=weekend_calendar)
    # Pay on Monday Feb 3
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert s.fine_paid == Money.zero()


def test_due_date_saturday_payment_monday_no_mora(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Saturday, payment on Monday: no mora interest."""
    # Feb 1, 2025 is Saturday, effective due = Monday Feb 3
    loan = _make_loan([date(2025, 2, 1)], calendar=weekend_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert s.mora_paid == Money.zero()


def test_due_date_saturday_payment_tuesday_has_fine(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Saturday, payment on Tuesday: 1 day late after effective Monday."""
    loan = _make_loan([date(2025, 2, 1)], calendar=weekend_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 4, tzinfo=timezone.utc))
    assert s.fine_paid > Money.zero()


def test_due_date_saturday_payment_tuesday_has_mora(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Saturday, payment on Tuesday: mora accrues from effective Monday."""
    loan = _make_loan([date(2025, 2, 1)], calendar=weekend_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 4, tzinfo=timezone.utc))
    assert s.mora_paid > Money.zero()


def test_due_date_sunday_payment_monday_no_fine(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Sunday, payment on Monday: no fine."""
    # Feb 2, 2025 is Sunday
    loan = _make_loan([date(2025, 2, 2)], calendar=weekend_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert s.fine_paid == Money.zero()


def test_due_date_friday_payment_monday_has_fine(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Friday (working day), payment on Monday: genuinely late."""
    # Jan 31, 2025 is Friday
    loan = _make_loan([date(2025, 1, 31)], calendar=weekend_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert s.fine_paid > Money.zero()


def test_due_date_friday_payment_monday_has_mora(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Friday (working day), payment on Monday: mora accrues."""
    loan = _make_loan([date(2025, 1, 31)], calendar=weekend_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert s.mora_paid > Money.zero()


def test_default_calendar_no_deferral() -> None:
    """Without explicit calendar, EveryDayCalendar is used — no deferral."""
    # Feb 1, 2025 is Saturday but EveryDayCalendar does not defer
    loan = _make_loan([date(2025, 2, 1)], calendar=None)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 3, tzinfo=timezone.utc))
    # With EveryDayCalendar, Saturday is a working day -> Monday is 2 days late
    assert s.fine_paid > Money.zero()
    assert s.mora_paid > Money.zero()


def test_holiday_due_date_no_penalty(brazilian_calendar: BrazilianWorkingDayCalendar) -> None:
    """Due date on a national holiday, payment on next working day: no penalty."""
    # Apr 21, 2025 is Monday (Tiradentes Day) -> effective = Apr 22 (Tue)
    loan = _make_loan([date(2025, 4, 21)], calendar=brazilian_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 4, 22, tzinfo=timezone.utc))
    assert s.fine_paid == Money.zero()
    assert s.mora_paid == Money.zero()


def test_is_payment_late_with_calendar(weekend_calendar: WeekendCalendar) -> None:
    """Loan.is_payment_late respects the working day calendar."""
    loan = _make_loan([date(2025, 2, 1)], calendar=weekend_calendar)
    # Saturday Feb 1 -> effective Monday Feb 3
    # Checking on Monday: not late
    assert loan.is_payment_late(date(2025, 2, 1), datetime(2025, 2, 3, tzinfo=timezone.utc)) is False
    # Checking on Tuesday: late
    assert loan.is_payment_late(date(2025, 2, 1), datetime(2025, 2, 4, tzinfo=timezone.utc)) is True


def test_grace_period_with_calendar(weekend_calendar: WeekendCalendar) -> None:
    """Grace period is applied after the effective due date for fines.

    Mora still accrues from the effective due date (Mon Feb 3) because
    grace period only defers the fine, not the interest boundary.
    """
    # Feb 1, 2025 is Saturday -> effective Monday Feb 3
    # With 1 day grace: fine deadline is Feb 4 (Tuesday)
    loan = _make_loan([date(2025, 2, 1)], calendar=weekend_calendar, grace_period_days=1)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 4, tzinfo=timezone.utc))
    assert s.fine_paid == Money.zero()
    assert s.mora_paid > Money.zero()


def test_grace_period_exceeded_with_calendar(weekend_calendar: WeekendCalendar) -> None:
    """Payment after grace period on the effective due date incurs penalty."""
    # Feb 1, 2025 is Saturday -> effective Monday Feb 3
    # With 1 day grace: deadline is Feb 4 (Tuesday)
    # Pay on Wednesday Feb 5 -> late
    loan = _make_loan([date(2025, 2, 1)], calendar=weekend_calendar, grace_period_days=1)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 5, tzinfo=timezone.utc))
    assert s.fine_paid > Money.zero()


def test_fine_observation_respects_calendar(weekend_calendar: WeekendCalendar) -> None:
    """calculate_late_fines respects the working day calendar."""
    loan = _make_loan([date(2025, 2, 1)], calendar=weekend_calendar)
    # Observe on Monday (effective due date): no fine
    fines = loan.calculate_late_fines(datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert fines == Money.zero()
    # Observe on Tuesday (1 day after effective): fine
    fines = loan.calculate_late_fines(datetime(2025, 2, 4, tzinfo=timezone.utc))
    assert fines > Money.zero()


def test_multiple_installments_weekend_deferral(weekend_calendar: WeekendCalendar) -> None:
    """Multiple due dates on weekends: fines are not applied when paying on effective dates."""
    # Feb 1 (Sat) and Mar 1 (Sat) 2025
    loan = _make_loan(
        [date(2025, 2, 1), date(2025, 3, 1)],
        calendar=weekend_calendar,
    )
    # Pay first on Monday Feb 3 (effective due): no fine
    schedule = loan.get_original_schedule()
    s1 = loan.record_payment(schedule[0].payment_amount, datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert s1.fine_paid == Money.zero()
    assert s1.mora_paid == Money.zero()
    # Pay second on Monday Mar 3 (effective due): no fine
    s2 = loan.record_payment(schedule[1].payment_amount + Money("20"), datetime(2025, 3, 3, tzinfo=timezone.utc))
    assert s2.fine_paid == Money.zero()
