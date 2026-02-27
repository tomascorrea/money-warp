"""Tests for the timezone configuration module."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

import pytest

from money_warp.tz import _DefaultTimeSource, ensure_aware, get_tz, now, set_tz, tz_aware

# --- get_tz / set_tz ---


def test_default_timezone_is_utc():
    assert get_tz() == timezone.utc


def test_set_tz_with_string():
    original = get_tz()
    try:
        set_tz("America/Sao_Paulo")
        assert get_tz() == ZoneInfo("America/Sao_Paulo")
    finally:
        set_tz(original)


def test_set_tz_with_tzinfo_instance():
    original = get_tz()
    try:
        tz = ZoneInfo("Europe/London")
        set_tz(tz)
        assert get_tz() is tz
    finally:
        set_tz(original)


def test_set_tz_with_fixed_offset():
    original = get_tz()
    try:
        tz = timezone(timedelta(hours=-3))
        set_tz(tz)
        assert get_tz() is tz
    finally:
        set_tz(original)


# --- now ---


def test_now_returns_aware_datetime():
    result = now()
    assert result.tzinfo is not None


def test_now_uses_configured_timezone():
    original = get_tz()
    try:
        set_tz("America/Sao_Paulo")
        result = now()
        assert result.tzinfo == ZoneInfo("America/Sao_Paulo")
    finally:
        set_tz(original)


def test_now_uses_utc_by_default():
    result = now()
    assert result.tzinfo == timezone.utc


# --- ensure_aware ---


def test_ensure_aware_attaches_default_tz_to_naive():
    naive = datetime(2024, 6, 15, 12, 0, 0)
    result = ensure_aware(naive)
    assert result.tzinfo == timezone.utc


def test_ensure_aware_preserves_already_aware():
    tz = ZoneInfo("Asia/Tokyo")
    aware = datetime(2024, 6, 15, 12, 0, 0, tzinfo=tz)
    result = ensure_aware(aware)
    assert result.tzinfo is tz


def test_ensure_aware_uses_configured_tz_for_naive():
    original = get_tz()
    try:
        set_tz("America/Sao_Paulo")
        naive = datetime(2024, 6, 15, 12, 0, 0)
        result = ensure_aware(naive)
        assert result.tzinfo == ZoneInfo("America/Sao_Paulo")
    finally:
        set_tz(original)


def test_ensure_aware_keeps_datetime_values_unchanged():
    naive = datetime(2024, 6, 15, 14, 30, 45)
    result = ensure_aware(naive)
    assert result.year == 2024
    assert result.month == 6
    assert result.day == 15
    assert result.hour == 14
    assert result.minute == 30
    assert result.second == 45


# --- _DefaultTimeSource ---


def test_default_time_source_returns_aware():
    source = _DefaultTimeSource()
    result = source.now()
    assert result.tzinfo is not None


def test_default_time_source_uses_configured_tz():
    original = get_tz()
    try:
        set_tz("Europe/Berlin")
        source = _DefaultTimeSource()
        result = source.now()
        assert result.tzinfo == ZoneInfo("Europe/Berlin")
    finally:
        set_tz(original)


# --- invalid inputs ---


def test_set_tz_with_invalid_string_raises():
    with pytest.raises(Exception):
        set_tz("Not/A/Real/Timezone")


# --- tz_aware decorator ---


def test_tz_aware_coerces_naive_positional_arg():
    @tz_aware
    def func(dt: datetime) -> datetime:
        return dt

    result = func(datetime(2024, 1, 1))
    assert result.tzinfo == timezone.utc


def test_tz_aware_coerces_naive_keyword_arg():
    @tz_aware
    def func(dt: datetime) -> datetime:
        return dt

    result = func(dt=datetime(2024, 1, 1))
    assert result.tzinfo == timezone.utc


def test_tz_aware_preserves_already_aware_arg():
    tz = ZoneInfo("Asia/Tokyo")

    @tz_aware
    def func(dt: datetime) -> datetime:
        return dt

    aware = datetime(2024, 1, 1, tzinfo=tz)
    result = func(aware)
    assert result.tzinfo is tz


def test_tz_aware_coerces_list_of_datetimes():
    @tz_aware
    def func(dates: List[datetime]) -> List[datetime]:
        return dates

    result = func([datetime(2024, 1, 1), datetime(2024, 2, 1)])
    assert all(d.tzinfo == timezone.utc for d in result)


def test_tz_aware_leaves_none_untouched():
    @tz_aware
    def func(dt: Optional[datetime] = None) -> Optional[datetime]:
        return dt

    assert func() is None
    assert func(None) is None


def test_tz_aware_leaves_non_datetime_args_untouched():
    @tz_aware
    def func(name: str, count: int) -> str:
        return f"{name}-{count}"

    assert func("hello", 42) == "hello-42"


def test_tz_aware_works_on_method_with_self():
    class Dummy:
        @tz_aware
        def get_date(self, dt: datetime) -> datetime:
            return dt

    result = Dummy().get_date(datetime(2024, 6, 15))
    assert result.tzinfo == timezone.utc


def test_tz_aware_uses_configured_timezone():
    original = get_tz()
    try:
        set_tz("America/Sao_Paulo")

        @tz_aware
        def func(dt: datetime) -> datetime:
            return dt

        result = func(datetime(2024, 1, 1))
        assert result.tzinfo == ZoneInfo("America/Sao_Paulo")
    finally:
        set_tz(original)
