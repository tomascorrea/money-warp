"""Integration tests for BillingCycleLoan with working_day_calendar penalty deferral."""

from datetime import date, datetime, timezone

import pytest

from money_warp import BillingCycleLoan, InterestRate, Money
from money_warp.billing_cycle import MonthlyBillingCycle
from money_warp.working_day import (
    BrazilianWorkingDayCalendar,
    WeekendCalendar,
)


@pytest.fixture
def weekend_calendar() -> WeekendCalendar:
    return WeekendCalendar()


@pytest.fixture
def brazilian_calendar() -> BrazilianWorkingDayCalendar:
    return BrazilianWorkingDayCalendar()


def _make_bcl(
    due_dates: list[date],
    calendar=None,
    grace_period_days: int = 0,
) -> BillingCycleLoan:
    """Helper: BCL with explicit due dates via billing cycle."""
    cycle = MonthlyBillingCycle(closing_day=1, payment_due_days=10, due_dates=due_dates)
    return BillingCycleLoan(
        principal=Money("3000"),
        interest_rate=InterestRate("12% annual"),
        billing_cycle=cycle,
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=len(due_dates),
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
        grace_period_days=grace_period_days,
        working_day_calendar=calendar,
    )


def test_due_date_saturday_payment_monday_no_fine(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Saturday, payment on Monday: no fine."""
    # Feb 1, 2025 is Saturday
    loan = _make_bcl([date(2025, 2, 1)], calendar=weekend_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert s.fine_paid == Money.zero()


def test_due_date_saturday_payment_monday_no_mora(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Saturday, payment on Monday: no mora interest."""
    loan = _make_bcl([date(2025, 2, 1)], calendar=weekend_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert s.mora_paid == Money.zero()


def test_due_date_saturday_payment_tuesday_has_fine(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Saturday, payment on Tuesday: late after effective Monday."""
    loan = _make_bcl([date(2025, 2, 1)], calendar=weekend_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 4, tzinfo=timezone.utc))
    assert s.fine_paid > Money.zero()


def test_due_date_saturday_payment_tuesday_has_mora(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Saturday, payment on Tuesday: mora accrues from effective Monday."""
    loan = _make_bcl([date(2025, 2, 1)], calendar=weekend_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 4, tzinfo=timezone.utc))
    assert s.mora_paid > Money.zero()


def test_due_date_friday_payment_monday_has_fine(weekend_calendar: WeekendCalendar) -> None:
    """Due date on Friday (working day), payment on Monday: genuinely late."""
    # Jan 31, 2025 is Friday
    loan = _make_bcl([date(2025, 1, 31)], calendar=weekend_calendar)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert s.fine_paid > Money.zero()


def test_default_calendar_no_deferral() -> None:
    """Without calendar, default EveryDayCalendar does not defer."""
    loan = _make_bcl([date(2025, 2, 1)], calendar=None)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert s.fine_paid > Money.zero()


def test_holiday_due_date_no_penalty(brazilian_calendar: BrazilianWorkingDayCalendar) -> None:
    """Due date on a national holiday, payment on next working day: no penalty."""
    # Apr 21, 2025 is Monday (Tiradentes) -> effective = Apr 22 (Tue)
    # Use closing_day=10, payment_due_days=11 so due dates land on the 21st
    cycle = MonthlyBillingCycle(
        closing_day=10,
        payment_due_days=11,
        due_dates=[
            date(2025, 2, 21),
            date(2025, 3, 21),
            date(2025, 4, 21),
        ],
    )
    loan = BillingCycleLoan(
        principal=Money("3000"),
        interest_rate=InterestRate("12% annual"),
        billing_cycle=cycle,
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
        working_day_calendar=brazilian_calendar,
    )
    assert loan.due_dates[-1] == date(2025, 4, 21)
    # Pay first 2 on time
    schedule = loan.get_original_schedule()
    for i in range(2):
        loan.record_payment(
            schedule[i].payment_amount,
            datetime(
                schedule[i].due_date.year, schedule[i].due_date.month, schedule[i].due_date.day, tzinfo=timezone.utc
            ),
        )
    # 3rd installment: due Apr 21 (Tiradentes), pay Apr 22 (next working day)
    s = loan.record_payment(schedule[2].payment_amount + Money("5"), datetime(2025, 4, 22, tzinfo=timezone.utc))
    assert s.fine_paid == Money.zero()
    assert s.mora_paid == Money.zero()


def test_is_late_with_calendar(weekend_calendar: WeekendCalendar) -> None:
    """BillingCycleLoan.is_late respects the working day calendar."""
    loan = _make_bcl([date(2025, 2, 1)], calendar=weekend_calendar)
    # Saturday Feb 1 -> effective Monday Feb 3
    assert loan.is_late(date(2025, 2, 1), datetime(2025, 2, 3, tzinfo=timezone.utc)) is False
    assert loan.is_late(date(2025, 2, 1), datetime(2025, 2, 4, tzinfo=timezone.utc)) is True


def test_fine_observation_respects_calendar(weekend_calendar: WeekendCalendar) -> None:
    """calculate_late_fines respects the working day calendar."""
    loan = _make_bcl([date(2025, 2, 1)], calendar=weekend_calendar)
    fines = loan.calculate_late_fines(datetime(2025, 2, 3, tzinfo=timezone.utc))
    assert fines == Money.zero()
    fines = loan.calculate_late_fines(datetime(2025, 2, 4, tzinfo=timezone.utc))
    assert fines > Money.zero()


def test_grace_period_defers_fine_not_mora(weekend_calendar: WeekendCalendar) -> None:
    """Grace period defers fine but mora still accrues from effective due date."""
    # Feb 1, 2025 is Saturday -> effective Monday Feb 3
    # With 1 day grace: fine deadline is Feb 4
    loan = _make_bcl([date(2025, 2, 1)], calendar=weekend_calendar, grace_period_days=1)
    s = loan.record_payment(Money("3000"), datetime(2025, 2, 4, tzinfo=timezone.utc))
    assert s.fine_paid == Money.zero()
    assert s.mora_paid > Money.zero()
