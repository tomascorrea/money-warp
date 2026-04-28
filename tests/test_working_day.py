"""Tests for the working_day module."""

from datetime import date

import pytest

from money_warp.working_day import (
    BrazilianWorkingDayCalendar,
    EveryDayCalendar,
    WeekendCalendar,
    WorkingDayCalendar,
    effective_penalty_due_date,
)


class TestEveryDayCalendar:
    """EveryDayCalendar treats all days as working days."""

    @pytest.fixture
    def calendar(self) -> EveryDayCalendar:
        return EveryDayCalendar()

    @pytest.mark.parametrize(
        "d",
        [
            date(2025, 1, 6),   # Monday
            date(2025, 1, 7),   # Tuesday
            date(2025, 1, 8),   # Wednesday
            date(2025, 1, 9),   # Thursday
            date(2025, 1, 10),  # Friday
            date(2025, 1, 11),  # Saturday
            date(2025, 1, 12),  # Sunday
            date(2025, 12, 25), # Christmas
        ],
        ids=["mon", "tue", "wed", "thu", "fri", "sat", "sun", "christmas"],
    )
    def test_every_day_is_working(self, calendar: EveryDayCalendar, d: date) -> None:
        """All days are working days."""
        assert calendar.is_working_day(d) is True

    def test_next_working_day_is_always_tomorrow(self, calendar: EveryDayCalendar) -> None:
        """Next working day is always the next calendar day."""
        assert calendar.next_working_day(date(2025, 1, 10)) == date(2025, 1, 11)
        assert calendar.next_working_day(date(2025, 1, 11)) == date(2025, 1, 12)

    def test_conforms_to_protocol(self, calendar: EveryDayCalendar) -> None:
        """EveryDayCalendar satisfies the WorkingDayCalendar protocol."""
        assert isinstance(calendar, WorkingDayCalendar)


class TestWeekendCalendar:
    """WeekendCalendar treats Saturday and Sunday as non-working."""

    @pytest.fixture
    def calendar(self) -> WeekendCalendar:
        return WeekendCalendar()

    @pytest.mark.parametrize(
        "d,expected",
        [
            (date(2025, 1, 6), True),   # Monday
            (date(2025, 1, 7), True),   # Tuesday
            (date(2025, 1, 8), True),   # Wednesday
            (date(2025, 1, 9), True),   # Thursday
            (date(2025, 1, 10), True),  # Friday
            (date(2025, 1, 11), False), # Saturday
            (date(2025, 1, 12), False), # Sunday
        ],
        ids=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    )
    def test_is_working_day(self, calendar: WeekendCalendar, d: date, expected: bool) -> None:
        """Weekdays are working; weekends are not."""
        assert calendar.is_working_day(d) is expected

    @pytest.mark.parametrize(
        "d,expected_next",
        [
            (date(2025, 1, 6), date(2025, 1, 7)),   # Mon -> Tue
            (date(2025, 1, 9), date(2025, 1, 10)),   # Thu -> Fri
            (date(2025, 1, 10), date(2025, 1, 13)),  # Fri -> Mon
            (date(2025, 1, 11), date(2025, 1, 13)),  # Sat -> Mon
            (date(2025, 1, 12), date(2025, 1, 13)),  # Sun -> Mon
        ],
        ids=["mon_to_tue", "thu_to_fri", "fri_to_mon", "sat_to_mon", "sun_to_mon"],
    )
    def test_next_working_day(self, calendar: WeekendCalendar, d: date, expected_next: date) -> None:
        """Next working day skips weekends."""
        assert calendar.next_working_day(d) == expected_next

    def test_conforms_to_protocol(self, calendar: WeekendCalendar) -> None:
        """WeekendCalendar satisfies the WorkingDayCalendar protocol."""
        assert isinstance(calendar, WorkingDayCalendar)


class TestBrazilianWorkingDayCalendar:
    """BrazilianWorkingDayCalendar with national holidays."""

    @pytest.fixture
    def calendar(self) -> BrazilianWorkingDayCalendar:
        return BrazilianWorkingDayCalendar()

    def test_weekday_is_working(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """A normal weekday is a working day."""
        assert calendar.is_working_day(date(2025, 1, 2)) is True

    def test_weekend_is_not_working(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """Weekends are non-working."""
        assert calendar.is_working_day(date(2025, 1, 4)) is False  # Saturday

    def test_new_year_is_not_working(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """Jan 1 is a national holiday."""
        assert calendar.is_working_day(date(2025, 1, 1)) is False

    def test_christmas_is_not_working(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """Dec 25 is a national holiday."""
        assert calendar.is_working_day(date(2025, 12, 25)) is False

    def test_tiradentes_is_not_working(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """Apr 21 is Tiradentes Day."""
        assert calendar.is_working_day(date(2025, 4, 21)) is False

    def test_carnival_tuesday_2025(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """Carnival Tuesday 2025 (Easter 2025 = Apr 20, Carnival = Feb 25-Mar 4).

        Easter 2025 is April 20.  Carnival Tuesday = Easter - 47 = March 4.
        """
        assert calendar.is_working_day(date(2025, 3, 4)) is False

    def test_carnival_monday_2025(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """Carnival Monday 2025: Easter - 48 = March 3."""
        assert calendar.is_working_day(date(2025, 3, 3)) is False

    def test_good_friday_2025(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """Good Friday 2025: Easter - 2 = April 18."""
        assert calendar.is_working_day(date(2025, 4, 18)) is False

    def test_corpus_christi_2025(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """Corpus Christi 2025: Easter + 60 = June 19."""
        assert calendar.is_working_day(date(2025, 6, 19)) is False

    def test_next_working_day_skips_holiday(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """Next working day after a holiday skips to the following working day."""
        # Dec 24, 2025 is Wednesday; Dec 25 is Thursday (holiday) -> next = Dec 26
        assert calendar.next_working_day(date(2025, 12, 24)) == date(2025, 12, 26)

    def test_next_working_day_skips_holiday_and_weekend(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """When a holiday is followed by a weekend, skip both."""
        # Nov 20, 2026 is Friday (Black Consciousness) -> next day Sat -> Sun -> Mon Nov 23
        assert calendar.next_working_day(date(2026, 11, 19)) == date(2026, 11, 23)

    def test_extra_holidays(self) -> None:
        """Extra holidays (state/municipal) are respected."""
        extra = {date(2025, 1, 25)}  # São Paulo anniversary
        calendar = BrazilianWorkingDayCalendar(extra_holidays=extra)
        # Jan 25, 2025 is Saturday (already non-working), use a weekday example
        extra2 = {date(2025, 7, 9)}  # Revolução Constitucionalista (SP)
        calendar2 = BrazilianWorkingDayCalendar(extra_holidays=extra2)
        assert calendar2.is_working_day(date(2025, 7, 9)) is False

    def test_normal_weekday_not_holiday(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """A regular weekday that is not a holiday is working."""
        assert calendar.is_working_day(date(2025, 3, 5)) is True

    def test_caches_holidays_per_year(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """Holiday computation is cached per year."""
        calendar.is_working_day(date(2025, 1, 1))
        calendar.is_working_day(date(2025, 12, 25))
        assert 2025 in calendar._cache

    def test_conforms_to_protocol(self, calendar: BrazilianWorkingDayCalendar) -> None:
        """BrazilianWorkingDayCalendar satisfies the WorkingDayCalendar protocol."""
        assert isinstance(calendar, WorkingDayCalendar)


class TestEffectivePenaltyDueDate:
    """Test the effective_penalty_due_date helper."""

    def test_working_day_returns_same_date(self) -> None:
        """A working day returns itself."""
        calendar = WeekendCalendar()
        assert effective_penalty_due_date(date(2025, 1, 6), calendar) == date(2025, 1, 6)  # Monday

    def test_saturday_returns_monday(self) -> None:
        """Saturday shifts to Monday."""
        calendar = WeekendCalendar()
        assert effective_penalty_due_date(date(2025, 1, 11), calendar) == date(2025, 1, 13)

    def test_sunday_returns_monday(self) -> None:
        """Sunday shifts to Monday."""
        calendar = WeekendCalendar()
        assert effective_penalty_due_date(date(2025, 1, 12), calendar) == date(2025, 1, 13)

    def test_holiday_shifts_to_next_working_day(self) -> None:
        """A holiday on a weekday shifts to the next working day."""
        calendar = BrazilianWorkingDayCalendar()
        # Apr 21, 2025 is Monday (Tiradentes) -> next working day is Apr 22 (Tue)
        assert effective_penalty_due_date(date(2025, 4, 21), calendar) == date(2025, 4, 22)

    def test_every_day_calendar_never_shifts(self) -> None:
        """EveryDayCalendar never shifts dates."""
        calendar = EveryDayCalendar()
        assert effective_penalty_due_date(date(2025, 1, 11), calendar) == date(2025, 1, 11)  # Saturday
        assert effective_penalty_due_date(date(2025, 12, 25), calendar) == date(2025, 12, 25)  # Christmas
