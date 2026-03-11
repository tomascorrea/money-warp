"""Tests for RateType and InterestRateType TypeDecorators."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from money_warp.ext.sa import RateType
from money_warp.interest_rate import InterestRate
from money_warp.rate import CompoundingFrequency, Rate, YearSize

from .conftest import (
    InterestRateJsonModel,
    InterestRateStringModel,
    RateJsonModel,
    RateStringModel,
)

# ===========================================================================
# RateType — construction
# ===========================================================================


def test_rate_type_invalid_representation_raises():
    with pytest.raises(ValueError, match="Invalid representation"):
        RateType(representation="unknown")


@pytest.mark.parametrize("representation", ["string", "json"])
def test_rate_type_valid_representation_accepted(representation):
    col_type = RateType(representation=representation)
    assert col_type.representation == representation


# ===========================================================================
# RateType — round-trip string
# ===========================================================================


def test_rate_type_roundtrip_string_annually(session):
    original = Rate("5.25% a")
    session.add(RateStringModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateStringModel, 1)
    assert loaded.rate == original


def test_rate_type_roundtrip_string_monthly(session):
    original = Rate("1.5% m")
    session.add(RateStringModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateStringModel, 1)
    assert loaded.rate.period == CompoundingFrequency.MONTHLY


def test_rate_type_roundtrip_string_negative(session):
    original = Rate("-2.5% a")
    session.add(RateStringModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateStringModel, 1)
    assert loaded.rate == original


# ===========================================================================
# RateType — round-trip json
# ===========================================================================


def test_rate_type_roundtrip_json_basic(session):
    original = Rate(Decimal("0.0525"), CompoundingFrequency.ANNUALLY)
    session.add(RateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateJsonModel, 1)
    assert loaded.rate == original


def test_rate_type_roundtrip_json_with_all_params(session):
    original = Rate(
        Decimal("0.015"),
        CompoundingFrequency.MONTHLY,
        precision=6,
        year_size=YearSize.banker,
        str_style="abbrev",
    )
    session.add(RateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateJsonModel, 1)
    assert loaded.rate == original


def test_rate_type_roundtrip_json_negative(session):
    original = Rate(Decimal("-0.025"), CompoundingFrequency.ANNUALLY)
    session.add(RateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateJsonModel, 1)
    assert loaded.rate == original


# ===========================================================================
# RateType — None handling
# ===========================================================================


def test_rate_type_none_string(session):
    session.add(RateStringModel(id=1, rate=None))
    session.flush()
    session.expire_all()
    loaded = session.get(RateStringModel, 1)
    assert loaded.rate is None


def test_rate_type_none_json(session):
    session.add(RateJsonModel(id=1, rate=None))
    session.flush()
    session.expire_all()
    loaded = session.get(RateJsonModel, 1)
    assert loaded.rate is None


# ===========================================================================
# InterestRateType — round-trips
# ===========================================================================


def test_interest_rate_type_roundtrip_string(session):
    original = InterestRate("5.25% a")
    session.add(InterestRateStringModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(InterestRateStringModel, 1)
    assert isinstance(loaded.rate, InterestRate)
    assert loaded.rate == original


def test_interest_rate_type_roundtrip_json(session):
    original = InterestRate(Decimal("0.0525"), CompoundingFrequency.ANNUALLY)
    session.add(InterestRateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(InterestRateJsonModel, 1)
    assert isinstance(loaded.rate, InterestRate)
    assert loaded.rate == original


# ===========================================================================
# RateType — str_decimals and abbrev_labels
# ===========================================================================


def test_rate_type_string_respects_str_decimals(session):
    original = Rate("5.25% a", str_decimals=2)
    session.add(RateStringModel(id=1, rate=original))
    session.flush()
    raw = session.execute(text("SELECT rate FROM rate_string WHERE id = 1")).scalar()
    assert raw == "5.25% annual"


def test_rate_type_string_respects_abbrev_labels(session):
    labels = {CompoundingFrequency.MONTHLY: "a.m"}
    original = Rate("1.5% a.m.", abbrev_labels=labels)
    session.add(RateStringModel(id=1, rate=original))
    session.flush()
    raw = session.execute(text("SELECT rate FROM rate_string WHERE id = 1")).scalar()
    assert raw == "1.500% a.m"


def test_rate_type_json_roundtrip_with_str_decimals(session):
    original = Rate(
        Decimal("0.0525"),
        CompoundingFrequency.ANNUALLY,
        str_decimals=2,
    )
    session.add(RateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateJsonModel, 1)
    assert loaded.rate._str_decimals == 2
    assert str(loaded.rate) == "5.25% annually"


def test_rate_type_json_roundtrip_with_abbrev_labels(session):
    labels = {CompoundingFrequency.MONTHLY: "a.m"}
    original = Rate(
        Decimal("0.01"),
        CompoundingFrequency.MONTHLY,
        str_style="abbrev",
        abbrev_labels=labels,
    )
    session.add(RateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateJsonModel, 1)
    assert str(loaded.rate) == "1.000% a.m"


def test_rate_type_json_roundtrip_with_both_formatting_params(session):
    labels = {CompoundingFrequency.ANNUALLY: "a.a"}
    original = Rate(
        Decimal("0.0525"),
        CompoundingFrequency.ANNUALLY,
        str_style="abbrev",
        str_decimals=2,
        abbrev_labels=labels,
    )
    session.add(RateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateJsonModel, 1)
    assert str(loaded.rate) == "5.25% a.a"


def test_interest_rate_type_json_roundtrip_with_formatting(session):
    labels = {CompoundingFrequency.ANNUALLY: "a.a"}
    original = InterestRate(
        Decimal("0.0525"),
        CompoundingFrequency.ANNUALLY,
        str_style="abbrev",
        str_decimals=2,
        abbrev_labels=labels,
    )
    session.add(InterestRateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(InterestRateJsonModel, 1)
    assert isinstance(loaded.rate, InterestRate)
    assert str(loaded.rate) == "5.25% a.a"


# ===========================================================================
# RateType — abbreviated string round-trips
# ===========================================================================


@pytest.mark.parametrize(
    "rate_string,expected_stored_token",
    [
        ("5.25% a.a.", "a.a."),
        ("1.5% a.m.", "a.m."),
        ("0.03% a.d.", "a.d."),
        ("2.5% a.t.", "a.t."),
        ("3.0% a.s.", "a.s."),
    ],
    ids=["annually", "monthly", "daily", "quarterly", "semi_annually"],
)
def test_rate_type_roundtrip_string_abbreviated(session, rate_string, expected_stored_token):
    original = Rate(rate_string)
    session.add(RateStringModel(id=1, rate=original))
    session.flush()

    raw = session.execute(text("SELECT rate FROM rate_string WHERE id = 1")).scalar()
    assert raw.endswith(expected_stored_token)

    session.expire_all()
    loaded = session.get(RateStringModel, 1)
    assert loaded.rate == original


def test_rate_type_abbreviated_preserves_str_style(session):
    original = Rate("5.25% a.a.")
    session.add(RateStringModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateStringModel, 1)
    assert loaded.rate._str_style == "abbrev"


def test_interest_rate_type_roundtrip_string_abbreviated(session):
    original = InterestRate("5.25% a.a.")
    session.add(InterestRateStringModel(id=1, rate=original))
    session.flush()

    raw = session.execute(text("SELECT rate FROM interest_rate_string WHERE id = 1")).scalar()
    assert raw == "5.250% a.a."

    session.expire_all()
    loaded = session.get(InterestRateStringModel, 1)
    assert isinstance(loaded.rate, InterestRate)
    assert loaded.rate == original
