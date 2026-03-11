"""Tests for Marshmallow extension fields."""

from decimal import Decimal

import pytest
from marshmallow import Schema, ValidationError

from money_warp.ext.marshmallow import InterestRateField, MoneyField, RateField
from money_warp.interest_rate import InterestRate
from money_warp.money import Money
from money_warp.rate import CompoundingFrequency, Rate, YearSize

# ---------------------------------------------------------------------------
# Helper schemas
# ---------------------------------------------------------------------------


class RawMoneySchema(Schema):
    amount = MoneyField(representation="raw")


class RealMoneySchema(Schema):
    amount = MoneyField(representation="real")


class CentsMoneySchema(Schema):
    amount = MoneyField(representation="cents")


class StringRateSchema(Schema):
    rate = RateField(representation="string")


class DictRateSchema(Schema):
    rate = RateField(representation="dict")


class StringInterestRateSchema(Schema):
    rate = InterestRateField(representation="string")


class DictInterestRateSchema(Schema):
    rate = InterestRateField(representation="dict")


# ===========================================================================
# MoneyField — construction
# ===========================================================================


def test_money_field_invalid_representation_raises():
    with pytest.raises(ValueError, match="Invalid representation"):
        MoneyField(representation="unknown")


@pytest.mark.parametrize("representation", ["raw", "real", "cents"])
def test_money_field_valid_representation_accepted(representation):
    field = MoneyField(representation=representation)
    assert field.representation == representation


# ===========================================================================
# MoneyField — serialization
# ===========================================================================


@pytest.mark.parametrize(
    "amount_str,expected",
    [
        ("100.50", "100.50"),
        ("0", "0"),
        ("999999999.123456789", "999999999.123456789"),
        ("-50.25", "-50.25"),
    ],
)
def test_money_field_serialize_raw(amount_str, expected):
    result = RawMoneySchema().dump({"amount": Money(amount_str)})
    assert result["amount"] == expected


@pytest.mark.parametrize(
    "amount_str,expected",
    [
        ("100.50", "100.50"),
        ("100.125", "100.13"),
        ("0.001", "0.00"),
        ("-50.255", "-50.26"),
    ],
)
def test_money_field_serialize_real(amount_str, expected):
    result = RealMoneySchema().dump({"amount": Money(amount_str)})
    assert result["amount"] == expected


@pytest.mark.parametrize(
    "amount_str,expected_cents",
    [
        ("100.50", 10050),
        ("0", 0),
        ("0.01", 1),
        ("-25.99", -2599),
    ],
)
def test_money_field_serialize_cents(amount_str, expected_cents):
    result = CentsMoneySchema().dump({"amount": Money(amount_str)})
    assert result["amount"] == expected_cents


def test_money_field_serialize_none_returns_none():
    result = RawMoneySchema().dump({"amount": None})
    assert result["amount"] is None


# ===========================================================================
# MoneyField — deserialization
# ===========================================================================


@pytest.mark.parametrize(
    "input_val,expected_raw",
    [
        ("100.50", Decimal("100.50")),
        ("0", Decimal("0")),
        ("999999999.123456789", Decimal("999999999.123456789")),
    ],
)
def test_money_field_deserialize_raw(input_val, expected_raw):
    result = RawMoneySchema().load({"amount": input_val})
    assert result["amount"].raw_amount == expected_raw


def test_money_field_deserialize_real():
    result = RealMoneySchema().load({"amount": "100.50"})
    assert result["amount"].raw_amount == Decimal("100.50")


@pytest.mark.parametrize(
    "cents_input,expected_real",
    [
        (10050, Decimal("100.50")),
        (0, Decimal("0.00")),
        (1, Decimal("0.01")),
    ],
)
def test_money_field_deserialize_cents(cents_input, expected_real):
    result = CentsMoneySchema().load({"amount": cents_input})
    assert result["amount"].real_amount == expected_real


def test_money_field_deserialize_invalid_raises():
    with pytest.raises(ValidationError):
        RawMoneySchema().load({"amount": "not-a-number"})


# ===========================================================================
# MoneyField — round-trips
# ===========================================================================


@pytest.mark.parametrize(
    "amount_str",
    ["100.50", "0", "999999999.123456789", "-50.25"],
)
def test_money_field_roundtrip_raw(amount_str):
    original = Money(amount_str)
    serialized = RawMoneySchema().dump({"amount": original})
    loaded = RawMoneySchema().load(serialized)
    assert loaded["amount"].raw_amount == original.raw_amount


@pytest.mark.parametrize(
    "amount_str",
    ["100.50", "100.125", "0.001"],
)
def test_money_field_roundtrip_real(amount_str):
    original = Money(amount_str)
    serialized = RealMoneySchema().dump({"amount": original})
    loaded = RealMoneySchema().load(serialized)
    assert loaded["amount"].real_amount == original.real_amount


@pytest.mark.parametrize(
    "amount_str",
    ["100.50", "0.01", "0"],
)
def test_money_field_roundtrip_cents(amount_str):
    original = Money(amount_str)
    serialized = CentsMoneySchema().dump({"amount": original})
    loaded = CentsMoneySchema().load(serialized)
    assert loaded["amount"].real_amount == original.real_amount


# ===========================================================================
# MoneyField — edge cases
# ===========================================================================


def test_money_field_zero_money():
    result = RawMoneySchema().dump({"amount": Money.zero()})
    assert result["amount"] == "0"


def test_money_field_very_large_amount():
    big = Money("99999999999.99")
    loaded = RawMoneySchema().load(RawMoneySchema().dump({"amount": big}))
    assert loaded["amount"].raw_amount == big.raw_amount


# ===========================================================================
# RateField — construction
# ===========================================================================


def test_rate_field_invalid_representation_raises():
    with pytest.raises(ValueError, match="Invalid representation"):
        RateField(representation="unknown")


@pytest.mark.parametrize("representation", ["string", "dict"])
def test_rate_field_valid_representation_accepted(representation):
    field = RateField(representation=representation)
    assert field.representation == representation


# ===========================================================================
# RateField — serialization (string)
# ===========================================================================


def test_rate_field_serialize_string():
    rate = Rate("5.25% a")
    result = StringRateSchema().dump({"rate": rate})
    assert result["rate"] == "5.250% annual"


def test_rate_field_serialize_string_monthly():
    rate = Rate("1.5% m")
    result = StringRateSchema().dump({"rate": rate})
    assert result["rate"] == "1.500% monthly"


def test_rate_field_serialize_string_negative():
    rate = Rate("-2.5% a")
    result = StringRateSchema().dump({"rate": rate})
    assert result["rate"] == "-2.500% annual"


def test_rate_field_serialize_none_returns_none():
    result = StringRateSchema().dump({"rate": None})
    assert result["rate"] is None


# ===========================================================================
# RateField — serialization (dict)
# ===========================================================================


def test_rate_field_serialize_dict_rate_value():
    rate = Rate(Decimal("0.0525"), CompoundingFrequency.ANNUALLY)
    result = DictRateSchema().dump({"rate": rate})
    assert result["rate"]["rate"] == "0.0525"


def test_rate_field_serialize_dict_period():
    rate = Rate(Decimal("0.015"), CompoundingFrequency.MONTHLY)
    result = DictRateSchema().dump({"rate": rate})
    assert result["rate"]["period"] == "monthly"


def test_rate_field_serialize_dict_year_size():
    rate = Rate(Decimal("0.05"), CompoundingFrequency.ANNUALLY, year_size=YearSize.banker)
    result = DictRateSchema().dump({"rate": rate})
    assert result["rate"]["year_size"] == 360


def test_rate_field_serialize_dict_precision():
    rate = Rate(Decimal("0.05"), CompoundingFrequency.ANNUALLY, precision=4)
    result = DictRateSchema().dump({"rate": rate})
    assert result["rate"]["precision"] == 4


def test_rate_field_serialize_dict_str_style():
    rate = Rate("5.25% a.a.")
    result = DictRateSchema().dump({"rate": rate})
    assert result["rate"]["str_style"] == "abbrev"


# ===========================================================================
# RateField — deserialization (string)
# ===========================================================================


def test_rate_field_deserialize_string_annually():
    result = StringRateSchema().load({"rate": "5.25% a"})
    assert result["rate"].as_decimal() == Decimal("0.0525")


def test_rate_field_deserialize_string_monthly():
    result = StringRateSchema().load({"rate": "1.5% monthly"})
    assert result["rate"].period == CompoundingFrequency.MONTHLY


def test_rate_field_deserialize_string_negative():
    result = StringRateSchema().load({"rate": "-2.5% a"})
    assert result["rate"].as_decimal() == Decimal("-0.025")


def test_rate_field_deserialize_string_invalid_raises():
    with pytest.raises(ValidationError):
        StringRateSchema().load({"rate": "not-a-rate"})


def test_rate_field_deserialize_string_uses_field_year_size():
    schema_class = type(
        "S",
        (Schema,),
        {"rate": RateField(representation="string", year_size=YearSize.banker)},
    )
    result = schema_class().load({"rate": "5% a"})
    assert result["rate"].year_size == YearSize.banker


# ===========================================================================
# RateField — deserialization (dict)
# ===========================================================================


def test_rate_field_deserialize_dict_basic():
    data = {"rate": {"rate": "0.0525", "period": "annually"}}
    result = DictRateSchema().load(data)
    assert result["rate"].as_decimal() == Decimal("0.0525")


def test_rate_field_deserialize_dict_with_year_size():
    data = {"rate": {"rate": "0.05", "period": "annually", "year_size": 360}}
    result = DictRateSchema().load(data)
    assert result["rate"].year_size == YearSize.banker


def test_rate_field_deserialize_dict_with_precision():
    data = {"rate": {"rate": "0.05", "period": "annually", "precision": 4}}
    result = DictRateSchema().load(data)
    assert result["rate"]._precision == 4


def test_rate_field_deserialize_dict_with_str_style():
    data = {"rate": {"rate": "0.05", "period": "annually", "str_style": "abbrev"}}
    result = DictRateSchema().load(data)
    assert str(result["rate"]) == "5.000% a.a."


def test_rate_field_deserialize_dict_missing_rate_raises():
    with pytest.raises(ValidationError, match="'rate' and 'period'"):
        DictRateSchema().load({"rate": {"period": "annually"}})


def test_rate_field_deserialize_dict_missing_period_raises():
    with pytest.raises(ValidationError, match="'rate' and 'period'"):
        DictRateSchema().load({"rate": {"rate": "0.05"}})


def test_rate_field_deserialize_dict_not_dict_raises():
    with pytest.raises(ValidationError, match="'rate' and 'period'"):
        DictRateSchema().load({"rate": "not-a-dict"})


def test_rate_field_deserialize_dict_invalid_period_raises():
    with pytest.raises(ValidationError, match="'rate' and 'period'"):
        DictRateSchema().load({"rate": {"rate": "0.05", "period": "biweekly"}})


# ===========================================================================
# RateField — round-trips
# ===========================================================================


def test_rate_field_roundtrip_string():
    original = Rate("5.25% a")
    serialized = StringRateSchema().dump({"rate": original})
    loaded = StringRateSchema().load(serialized)
    assert loaded["rate"] == original


def test_rate_field_roundtrip_dict():
    original = Rate(Decimal("0.0525"), CompoundingFrequency.ANNUALLY)
    serialized = DictRateSchema().dump({"rate": original})
    loaded = DictRateSchema().load(serialized)
    assert loaded["rate"] == original


def test_rate_field_roundtrip_dict_with_all_params():
    original = Rate(
        Decimal("0.015"),
        CompoundingFrequency.MONTHLY,
        precision=6,
        year_size=YearSize.banker,
        str_style="abbrev",
    )
    serialized = DictRateSchema().dump({"rate": original})
    loaded = DictRateSchema().load(serialized)
    assert loaded["rate"] == original


def test_rate_field_roundtrip_dict_negative():
    original = Rate(Decimal("-0.025"), CompoundingFrequency.ANNUALLY)
    serialized = DictRateSchema().dump({"rate": original})
    loaded = DictRateSchema().load(serialized)
    assert loaded["rate"] == original


# ===========================================================================
# InterestRateField — serialization
# ===========================================================================


def test_interest_rate_field_serialize_string():
    rate = InterestRate("5.25% a")
    result = StringInterestRateSchema().dump({"rate": rate})
    assert result["rate"] == "5.250% annual"


def test_interest_rate_field_serialize_dict_rate_value():
    rate = InterestRate(Decimal("0.0525"), CompoundingFrequency.ANNUALLY)
    result = DictInterestRateSchema().dump({"rate": rate})
    assert result["rate"]["rate"] == "0.0525"


# ===========================================================================
# InterestRateField — deserialization
# ===========================================================================


def test_interest_rate_field_deserialize_string():
    result = StringInterestRateSchema().load({"rate": "5.25% a"})
    assert isinstance(result["rate"], InterestRate)


def test_interest_rate_field_deserialize_dict():
    data = {"rate": {"rate": "0.0525", "period": "annually"}}
    result = DictInterestRateSchema().load(data)
    assert isinstance(result["rate"], InterestRate)


def test_interest_rate_field_deserialize_string_negative_raises():
    with pytest.raises(ValidationError):
        StringInterestRateSchema().load({"rate": "-2.5% a"})


def test_interest_rate_field_deserialize_dict_negative_raises():
    with pytest.raises(ValidationError):
        DictInterestRateSchema().load({"rate": {"rate": "-0.025", "period": "annually"}})


# ===========================================================================
# InterestRateField — round-trips
# ===========================================================================


def test_interest_rate_field_roundtrip_string():
    original = InterestRate("5.25% a")
    serialized = StringInterestRateSchema().dump({"rate": original})
    loaded = StringInterestRateSchema().load(serialized)
    assert loaded["rate"] == original


def test_interest_rate_field_roundtrip_dict():
    original = InterestRate(Decimal("0.0525"), CompoundingFrequency.ANNUALLY)
    serialized = DictInterestRateSchema().dump({"rate": original})
    loaded = DictInterestRateSchema().load(serialized)
    assert loaded["rate"] == original
