"""Tests for RateType and InterestRateType TypeDecorators."""

from decimal import Decimal

import pytest

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
