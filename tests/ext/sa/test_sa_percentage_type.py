"""Tests for PercentageType TypeDecorator."""

from decimal import Decimal

import pytest
from sqlalchemy import text

from money_warp.ext.sa import PercentageType
from money_warp.percentage import Percentage

from .conftest import PercentageModel

# ===========================================================================
# PercentageType — construction
# ===========================================================================


def test_percentage_type_default_construction():
    col_type = PercentageType()
    assert col_type.percentage_str_decimals == 2
    assert col_type.percentage_precision is None


def test_percentage_type_accepts_str_decimals():
    col_type = PercentageType(str_decimals=4)
    assert col_type.percentage_str_decimals == 4


# ===========================================================================
# PercentageType — round-trip
# ===========================================================================


def test_percentage_type_roundtrip_basic(session):
    original = Percentage("5%")
    session.add(PercentageModel(id=1, pct=original))
    session.flush()
    session.expire_all()
    loaded = session.get(PercentageModel, 1)
    assert isinstance(loaded.pct, Percentage)
    assert loaded.pct == original


def test_percentage_type_roundtrip_within_str_decimals(session):
    """Default `str_decimals=2` round-trips values with up to 2 decimals."""
    original = Percentage("6.12%")
    session.add(PercentageModel(id=1, pct=original))
    session.flush()
    session.expire_all()
    loaded = session.get(PercentageModel, 1)
    assert loaded.pct == original


def test_percentage_type_roundtrip_zero(session):
    """Zero percentages (no fee) should round-trip cleanly."""
    original = Percentage("0%")
    session.add(PercentageModel(id=1, pct=original))
    session.flush()
    session.expire_all()
    loaded = session.get(PercentageModel, 1)
    assert loaded.pct == original
    assert loaded.pct.as_decimal() == Decimal("0")


def test_percentage_type_stored_as_canonical_string(session):
    """The DB value should be the canonical '5.00%' form."""
    session.add(PercentageModel(id=1, pct=Percentage("5%")))
    session.flush()
    raw = session.execute(text("SELECT pct FROM percentages WHERE id = 1")).scalar()
    assert raw == "5.00%"


def test_percentage_type_respects_str_decimals_on_value(session):
    session.add(PercentageModel(id=1, pct=Percentage("5%", str_decimals=4)))
    session.flush()
    raw = session.execute(text("SELECT pct FROM percentages WHERE id = 1")).scalar()
    assert raw == "5.0000%"


# ===========================================================================
# PercentageType — None handling
# ===========================================================================


def test_percentage_type_none(session):
    session.add(PercentageModel(id=1, pct=None))
    session.flush()
    session.expire_all()
    loaded = session.get(PercentageModel, 1)
    assert loaded.pct is None


# ===========================================================================
# PercentageType — validation propagates from Percentage constructor
# ===========================================================================


def test_percentage_type_load_rejects_invalid_string(session):
    """Direct DB poisoning (bypassing the type) is caught on load by Percentage."""
    session.execute(text("INSERT INTO percentages (id, pct) VALUES (1, '5')"))
    session.commit()
    session.expire_all()
    with pytest.raises(ValueError, match="Invalid Percentage format"):
        session.get(PercentageModel, 1)


def test_percentage_type_load_rejects_temporal_string(session):
    """Direct DB poisoning with a temporal token is caught with helpful error."""
    session.execute(text("INSERT INTO percentages (id, pct) VALUES (1, '5% a.a.')"))
    session.commit()
    session.expire_all()
    with pytest.raises(ValueError, match="cannot parse temporal rate"):
        session.get(PercentageModel, 1)
