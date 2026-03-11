"""Tests for MoneyType TypeDecorator."""

from decimal import Decimal

import pytest
from sqlalchemy import Integer

from money_warp.ext.sa import MoneyType
from money_warp.money import Money

from .conftest import MoneyCentsModel, MoneyCustomPrecisionModel, MoneyRawModel, MoneyRealModel

# ===========================================================================
# Construction
# ===========================================================================


def test_money_type_invalid_representation_raises():
    with pytest.raises(ValueError, match="Invalid representation"):
        MoneyType(representation="unknown")


@pytest.mark.parametrize("representation", ["raw", "real", "cents"])
def test_money_type_valid_representation_accepted(representation):
    col_type = MoneyType(representation=representation)
    assert col_type.representation == representation


def test_money_type_default_precision_and_scale():
    col_type = MoneyType()
    assert col_type.precision == 20
    assert col_type.scale == 10


def test_money_type_custom_precision_and_scale():
    col_type = MoneyType(precision=12, scale=4)
    assert col_type.precision == 12
    assert col_type.scale == 4


def test_money_type_cents_ignores_precision_and_scale(session):
    col_type = MoneyType(representation="cents", precision=8, scale=3)
    assert col_type.precision == 8
    assert col_type.scale == 3
    dialect_impl = col_type.load_dialect_impl(session.bind.dialect)
    assert isinstance(dialect_impl, Integer)


# ===========================================================================
# Round-trip with custom precision/scale
# ===========================================================================


def test_money_type_roundtrip_custom_precision(session):
    original = Money("12345.67")
    session.add(MoneyCustomPrecisionModel(id=1, amount=original))
    session.flush()
    session.expire_all()
    loaded = session.get(MoneyCustomPrecisionModel, 1)
    assert loaded.amount.real_amount == Decimal("12345.67")


# ===========================================================================
# Round-trip raw
# ===========================================================================


@pytest.mark.parametrize(
    "amount_str,expected_raw",
    [
        ("100.50", Decimal("100.50")),
        ("0", Decimal("0")),
        ("12345.6789", Decimal("12345.6789")),
        ("-50.25", Decimal("-50.25")),
    ],
)
def test_money_type_roundtrip_raw(session, amount_str, expected_raw):
    original = Money(amount_str)
    session.add(MoneyRawModel(id=1, amount=original))
    session.flush()
    session.expire_all()
    loaded = session.get(MoneyRawModel, 1)
    assert loaded.amount.raw_amount == expected_raw


# ===========================================================================
# Round-trip real
# ===========================================================================


@pytest.mark.parametrize(
    "amount_str,expected_real",
    [
        ("100.50", Decimal("100.50")),
        ("100.125", Decimal("100.13")),
        ("0.001", Decimal("0.00")),
    ],
)
def test_money_type_roundtrip_real(session, amount_str, expected_real):
    original = Money(amount_str)
    session.add(MoneyRealModel(id=1, amount=original))
    session.flush()
    session.expire_all()
    loaded = session.get(MoneyRealModel, 1)
    assert loaded.amount.real_amount == expected_real


# ===========================================================================
# Round-trip cents
# ===========================================================================


@pytest.mark.parametrize(
    "amount_str,expected_real",
    [
        ("100.50", Decimal("100.50")),
        ("0.01", Decimal("0.01")),
        ("0", Decimal("0.00")),
    ],
)
def test_money_type_roundtrip_cents(session, amount_str, expected_real):
    original = Money(amount_str)
    session.add(MoneyCentsModel(id=1, amount=original))
    session.flush()
    session.expire_all()
    loaded = session.get(MoneyCentsModel, 1)
    assert loaded.amount.real_amount == expected_real


# ===========================================================================
# None handling
# ===========================================================================


def test_money_type_none_raw(session):
    session.add(MoneyRawModel(id=1, amount=None))
    session.flush()
    session.expire_all()
    loaded = session.get(MoneyRawModel, 1)
    assert loaded.amount is None


def test_money_type_none_cents(session):
    session.add(MoneyCentsModel(id=1, amount=None))
    session.flush()
    session.expire_all()
    loaded = session.get(MoneyCentsModel, 1)
    assert loaded.amount is None
