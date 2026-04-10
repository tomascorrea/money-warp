"""Tests for the timezone configuration module."""

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

import pytest

from money_warp.tz import _DefaultTimeSource, ensure_aware, get_tz, now, set_tz, to_date, tz_aware

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


def test_ensure_aware_normalizes_already_aware_to_default_tz():
    tz = ZoneInfo("Asia/Tokyo")
    aware = datetime(2024, 6, 15, 12, 0, 0, tzinfo=tz)
    result = ensure_aware(aware)
    assert result.tzinfo == timezone.utc
    assert result == aware


def test_ensure_aware_interprets_naive_in_configured_tz_then_converts_to_utc():
    original = get_tz()
    try:
        set_tz("America/Sao_Paulo")
        naive = datetime(2024, 6, 15, 12, 0, 0)
        result = ensure_aware(naive)
        assert result.tzinfo == timezone.utc
        assert result.hour == 15
        assert result == naive.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
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


def test_tz_aware_normalizes_already_aware_arg_to_default_tz():
    tz = ZoneInfo("Asia/Tokyo")

    @tz_aware
    def func(dt: datetime) -> datetime:
        return dt

    aware = datetime(2024, 1, 1, tzinfo=tz)
    result = func(aware)
    assert result.tzinfo == timezone.utc
    assert result == aware


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


def test_tz_aware_interprets_naive_in_configured_tz_returns_utc():
    original = get_tz()
    try:
        set_tz("America/Sao_Paulo")

        @tz_aware
        def func(dt: datetime) -> datetime:
            return dt

        result = func(datetime(2024, 1, 1))
        assert result.tzinfo == timezone.utc
        assert result == datetime(2024, 1, 1, tzinfo=ZoneInfo("America/Sao_Paulo"))
    finally:
        set_tz(original)


# --- ensure_aware: cross-timezone normalization ---


def test_ensure_aware_converts_sao_paulo_to_utc():
    sp = ZoneInfo("America/Sao_Paulo")
    aware = datetime(2024, 1, 15, 20, 0, 0, tzinfo=sp)
    result = ensure_aware(aware)
    assert result.tzinfo == timezone.utc
    assert result.hour == 23
    assert result.day == 15


def test_ensure_aware_always_returns_utc_regardless_of_configured_tz():
    original = get_tz()
    try:
        set_tz("America/Sao_Paulo")
        utc_dt = datetime(2024, 1, 16, 2, 0, 0, tzinfo=timezone.utc)
        result = ensure_aware(utc_dt)
        assert result.tzinfo == timezone.utc
        assert result.hour == 2
        assert result.day == 16
    finally:
        set_tz(original)


def test_ensure_aware_cross_midnight_date_change():
    sp = ZoneInfo("America/Sao_Paulo")
    sp_dt = datetime(2024, 1, 15, 23, 0, 0, tzinfo=sp)
    assert sp_dt.date().day == 15

    result = ensure_aware(sp_dt)
    assert result.tzinfo == timezone.utc
    assert result.date().day == 16


def test_ensure_aware_preserves_instant():
    sp = ZoneInfo("America/Sao_Paulo")
    tokyo = ZoneInfo("Asia/Tokyo")
    sp_dt = datetime(2024, 6, 15, 10, 0, 0, tzinfo=sp)
    tokyo_dt = datetime(2024, 6, 15, 22, 0, 0, tzinfo=tokyo)
    assert ensure_aware(sp_dt) == ensure_aware(tokyo_dt)


# --- to_date: timezone-aware date extraction ---


def test_to_date_extracts_date_in_configured_tz():
    original = get_tz()
    try:
        set_tz("America/Sao_Paulo")
        utc_dt = datetime(2024, 1, 16, 2, 0, 0, tzinfo=timezone.utc)
        assert to_date(utc_dt, ZoneInfo("America/Sao_Paulo")) == date(2024, 1, 15)
    finally:
        set_tz(original)


def test_to_date_passes_plain_date_through():
    d = date(2024, 6, 15)
    assert to_date(d, timezone.utc) is d


def test_to_date_utc_datetime_gives_utc_date():
    utc_dt = datetime(2024, 1, 16, 2, 0, 0, tzinfo=timezone.utc)
    assert to_date(utc_dt, timezone.utc) == date(2024, 1, 16)


# --- Full round-trip: BRT input → UTC storage → BRT date extraction ---


def test_brt_input_stored_as_utc_extracted_as_brt_date():
    """The core scenario: a BRT datetime is normalised to UTC for storage,
    but to_date extracts the calendar date in the business timezone (BRT).
    """
    original = get_tz()
    try:
        set_tz("America/Sao_Paulo")
        sp = ZoneInfo("America/Sao_Paulo")

        brt_dt = datetime(2024, 1, 15, 23, 0, 0, tzinfo=sp)

        stored = ensure_aware(brt_dt)
        assert stored.tzinfo == timezone.utc
        assert stored == datetime(2024, 1, 16, 2, 0, 0, tzinfo=timezone.utc)

        extracted_date = to_date(stored, ZoneInfo("America/Sao_Paulo"))
        assert extracted_date == date(2024, 1, 15)
    finally:
        set_tz(original)


def test_naive_input_stored_as_utc_extracted_as_brt_date():
    """Naive datetimes are interpreted as business-tz, stored as UTC,
    and to_date recovers the original calendar date.
    """
    original = get_tz()
    try:
        set_tz("America/Sao_Paulo")

        naive = datetime(2024, 1, 15, 22, 0, 0)

        stored = ensure_aware(naive)
        assert stored.tzinfo == timezone.utc
        assert stored.hour == 1
        assert stored.day == 16

        assert to_date(stored, ZoneInfo("America/Sao_Paulo")) == date(2024, 1, 15)
    finally:
        set_tz(original)
