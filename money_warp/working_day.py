"""Working-day calendar abstractions for penalty due-date deferral.

Brazilian banking regulation requires that when a due date falls on a
non-working day, the payment can be made on the next working day
without incurring penalties (fine and mora).

This module provides a pluggable calendar protocol and concrete
implementations for determining working days.
"""

from datetime import date, timedelta
from typing import Optional, Protocol, Set, runtime_checkable

from dateutil.easter import easter


@runtime_checkable
class WorkingDayCalendar(Protocol):
    """Protocol for working-day determination.

    Implementations define which days are working days and how to
    find the next working day from a given date.
    """

    def is_working_day(self, d: date) -> bool:
        """Return True if *d* is a working day."""
        ...

    def next_working_day(self, d: date) -> date:
        """Return the next working day strictly after *d*."""
        ...


class EveryDayCalendar:
    """Calendar where every day is a working day.

    This is the default calendar for loans — no penalty deferral
    ever occurs.  Equivalent to the behavior before working-day
    support was introduced.
    """

    def is_working_day(self, d: date) -> bool:
        return True

    def next_working_day(self, d: date) -> date:
        return d + timedelta(days=1)


class WeekendCalendar:
    """Calendar where Saturdays and Sundays are non-working days."""

    def is_working_day(self, d: date) -> bool:
        return d.weekday() < 5

    def next_working_day(self, d: date) -> date:
        candidate = d + timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate += timedelta(days=1)
        return candidate


class BrazilianWorkingDayCalendar:
    """Brazilian working-day calendar with national holidays.

    Weekends and all Brazilian national holidays are non-working days.
    Optionally accepts extra holiday dates for state/municipal holidays.

    National holidays (fixed):
        - Jan 1:  Confraternização Universal (New Year)
        - Apr 21: Tiradentes
        - May 1:  Dia do Trabalhador (Labour Day)
        - Sep 7:  Independência do Brasil
        - Oct 12: Nossa Senhora Aparecida
        - Nov 2:  Finados (All Souls' Day)
        - Nov 15: Proclamação da República
        - Nov 20: Dia da Consciência Negra (Black Consciousness Day)
        - Dec 25: Natal (Christmas)

    National holidays (movable, computed from Easter):
        - Carnival Monday:  Easter - 48 days
        - Carnival Tuesday: Easter - 47 days
        - Good Friday:      Easter - 2 days
        - Corpus Christi:   Easter + 60 days
    """

    _FIXED_HOLIDAYS = (
        (1, 1),
        (4, 21),
        (5, 1),
        (9, 7),
        (10, 12),
        (11, 2),
        (11, 15),
        (11, 20),
        (12, 25),
    )

    def __init__(self, extra_holidays: Optional[Set[date]] = None) -> None:
        self._extra_holidays: Set[date] = extra_holidays or set()
        self._cache: dict[int, Set[date]] = {}

    def _holidays_for_year(self, year: int) -> Set[date]:
        if year in self._cache:
            return self._cache[year]

        holidays: Set[date] = set()

        for month, day in self._FIXED_HOLIDAYS:
            holidays.add(date(year, month, day))

        easter_date = easter(year)
        holidays.add(easter_date - timedelta(days=48))  # Carnival Monday
        holidays.add(easter_date - timedelta(days=47))  # Carnival Tuesday
        holidays.add(easter_date - timedelta(days=2))  # Good Friday
        holidays.add(easter_date + timedelta(days=60))  # Corpus Christi

        self._cache[year] = holidays
        return holidays

    def is_working_day(self, d: date) -> bool:
        if d.weekday() >= 5:
            return False
        holidays = self._holidays_for_year(d.year)
        if d in holidays:
            return False
        return d not in self._extra_holidays

    def next_working_day(self, d: date) -> date:
        candidate = d + timedelta(days=1)
        while not self.is_working_day(candidate):
            candidate += timedelta(days=1)
        return candidate


def effective_penalty_due_date(due_date: date, calendar: WorkingDayCalendar) -> date:
    """Return the effective due date for penalty evaluation.

    If *due_date* is a working day, returns it unchanged.
    Otherwise returns the next working day per *calendar*.
    """
    if calendar.is_working_day(due_date):
        return due_date
    return calendar.next_working_day(due_date)
