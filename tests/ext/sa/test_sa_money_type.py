"""Tests for MoneyType TypeDecorator."""

from decimal import Decimal

import pytest

from money_warp.ext.sa import MoneyType
from money_warp.money import Money

from .conftest import MoneyCentsModel, MoneyRawModel, MoneyRealModel

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
