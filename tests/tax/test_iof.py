"""Tests for IOF (Imposto sobre Operações Financeiras) tax calculation."""

from datetime import datetime
from decimal import Decimal

import pytest

from money_warp import (
    IOF,
    CorporateIOF,
    IndividualIOF,
    InterestRate,
    InvertedPriceScheduler,
    Money,
    PriceScheduler,
)


@pytest.fixture
def standard_iof():
    return IOF(daily_rate="0.0082%", additional_rate="0.38%")


@pytest.fixture
def disbursement_date():
    return datetime(2024, 1, 1)


@pytest.fixture
def single_installment_schedule(disbursement_date):
    return PriceScheduler.generate_schedule(
        Money("10000"),
        InterestRate("2% monthly"),
        [datetime(2024, 2, 1)],
        disbursement_date,
    )


@pytest.fixture
def three_installment_schedule(disbursement_date):
    return PriceScheduler.generate_schedule(
        Money("10000"),
        InterestRate("2% monthly"),
        [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)],
        disbursement_date,
    )


def test_iof_parse_rate_from_percentage_string():
    iof = IOF(daily_rate="0.0082%", additional_rate="0.38%")
    assert iof.daily_rate == Decimal("0.000082")


def test_iof_parse_rate_from_decimal_string():
    iof = IOF(daily_rate="0.000082", additional_rate="0.0038")
    assert iof.daily_rate == Decimal("0.000082")


def test_iof_parse_rate_from_decimal_type():
    iof = IOF(daily_rate=Decimal("0.000082"), additional_rate=Decimal("0.0038"))
    assert iof.additional_rate == Decimal("0.0038")


def test_iof_max_daily_days_default():
    iof = IOF(daily_rate="0.0082%", additional_rate="0.38%")
    assert iof.max_daily_days == 365


def test_iof_max_daily_days_custom():
    iof = IOF(daily_rate="0.0082%", additional_rate="0.38%", max_daily_days=180)
    assert iof.max_daily_days == 180


def test_iof_single_installment_total_is_positive(standard_iof, single_installment_schedule, disbursement_date):
    result = standard_iof.calculate(single_installment_schedule, disbursement_date)
    assert result.total.is_positive()


def test_iof_single_installment_has_one_detail(standard_iof, single_installment_schedule, disbursement_date):
    result = standard_iof.calculate(single_installment_schedule, disbursement_date)
    assert len(result.per_installment) == 1


def test_iof_single_installment_detail_payment_number(standard_iof, single_installment_schedule, disbursement_date):
    result = standard_iof.calculate(single_installment_schedule, disbursement_date)
    assert result.per_installment[0].payment_number == 1


def test_iof_single_installment_manual_calculation(disbursement_date):
    """Verify IOF with a known manual calculation.

    Single installment of 10,000 at 2% monthly, due 2024-02-01 (31 days).
    The entire principal (10,000) is repaid in one installment.
    Daily IOF: 10000 * 0.000082 * 31 = 25.42
    Additional IOF: 10000 * 0.0038 = 38.00
    Total: 63.42
    """
    iof = IOF(daily_rate=Decimal("0.000082"), additional_rate=Decimal("0.0038"))
    schedule = PriceScheduler.generate_schedule(
        Money("10000"),
        InterestRate("2% monthly"),
        [datetime(2024, 2, 1)],
        disbursement_date,
    )
    result = iof.calculate(schedule, disbursement_date)
    assert result.total == Money("63.42")


def test_iof_three_installments_has_three_details(standard_iof, three_installment_schedule, disbursement_date):
    result = standard_iof.calculate(three_installment_schedule, disbursement_date)
    assert len(result.per_installment) == 3


def test_iof_three_installments_total_equals_sum_of_details(
    standard_iof, three_installment_schedule, disbursement_date
):
    result = standard_iof.calculate(three_installment_schedule, disbursement_date)
    sum_details = Money(sum(d.tax_amount.raw_amount for d in result.per_installment))
    assert result.total == sum_details


def test_iof_later_installments_have_higher_daily_component(disbursement_date):
    """Later installments accrue more daily IOF because they're further from disbursement."""
    iof = IOF(daily_rate=Decimal("0.000082"), additional_rate=Decimal("0"))
    schedule = PriceScheduler.generate_schedule(
        Money("10000"),
        InterestRate("2% monthly"),
        [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)],
        disbursement_date,
    )
    result = iof.calculate(schedule, disbursement_date)
    assert result.per_installment[2].tax_amount > result.per_installment[0].tax_amount


def test_iof_max_daily_days_caps_days(disbursement_date):
    """When days exceed max_daily_days, the cap is applied."""
    iof_capped = IOF(daily_rate=Decimal("0.000082"), additional_rate=Decimal("0"), max_daily_days=10)
    iof_uncapped = IOF(daily_rate=Decimal("0.000082"), additional_rate=Decimal("0"), max_daily_days=365)
    schedule = PriceScheduler.generate_schedule(
        Money("10000"),
        InterestRate("2% monthly"),
        [datetime(2024, 2, 1)],
        disbursement_date,
    )
    result_capped = iof_capped.calculate(schedule, disbursement_date)
    result_uncapped = iof_uncapped.calculate(schedule, disbursement_date)
    assert result_capped.total < result_uncapped.total


def test_iof_with_inverted_price_scheduler(standard_iof, disbursement_date):
    schedule = InvertedPriceScheduler.generate_schedule(
        Money("10000"),
        InterestRate("2% monthly"),
        [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)],
        disbursement_date,
    )
    result = standard_iof.calculate(schedule, disbursement_date)
    assert result.total.is_positive()


def test_iof_with_inverted_price_has_equal_principal_payments(disbursement_date):
    """SAC scheduler has equal principal payments, so additional IOF per installment should be equal."""
    iof = IOF(daily_rate=Decimal("0"), additional_rate=Decimal("0.0038"))
    schedule = InvertedPriceScheduler.generate_schedule(
        Money("9000"),
        InterestRate("2% monthly"),
        [datetime(2024, 2, 1), datetime(2024, 3, 1), datetime(2024, 4, 1)],
        disbursement_date,
    )
    result = iof.calculate(schedule, disbursement_date)
    assert result.per_installment[0].tax_amount == result.per_installment[1].tax_amount


def test_iof_detail_preserves_principal_payment(standard_iof, three_installment_schedule, disbursement_date):
    result = standard_iof.calculate(three_installment_schedule, disbursement_date)
    for detail, entry in zip(result.per_installment, three_installment_schedule):
        assert detail.principal_payment == entry.principal_payment


def test_iof_detail_preserves_due_date(standard_iof, three_installment_schedule, disbursement_date):
    result = standard_iof.calculate(three_installment_schedule, disbursement_date)
    for detail, entry in zip(result.per_installment, three_installment_schedule):
        assert detail.due_date == entry.due_date


def test_iof_repr(standard_iof):
    r = repr(standard_iof)
    assert "IOF" in r
    assert "daily_rate" in r


@pytest.mark.parametrize(
    "daily_rate,additional_rate",
    [
        ("0%", "0%"),
        (Decimal("0"), Decimal("0")),
    ],
)
def test_iof_zero_rates_produce_zero_tax(daily_rate, additional_rate, disbursement_date):
    iof = IOF(daily_rate=daily_rate, additional_rate=additional_rate)
    schedule = PriceScheduler.generate_schedule(
        Money("10000"),
        InterestRate("2% monthly"),
        [datetime(2024, 2, 1)],
        disbursement_date,
    )
    result = iof.calculate(schedule, disbursement_date)
    assert result.total.is_zero()


# --- IndividualIOF preset ---


def test_individual_iof_default_daily_rate():
    iof = IndividualIOF()
    assert iof.daily_rate == Decimal("0.000082")


def test_individual_iof_default_additional_rate():
    iof = IndividualIOF()
    assert iof.additional_rate == Decimal("0.0038")


def test_individual_iof_is_instance_of_iof():
    assert isinstance(IndividualIOF(), IOF)


def test_individual_iof_override_daily_rate():
    iof = IndividualIOF(daily_rate=Decimal("0.0001"))
    assert iof.daily_rate == Decimal("0.0001")


def test_individual_iof_override_additional_rate():
    iof = IndividualIOF(additional_rate="0.5%")
    assert iof.additional_rate == Decimal("0.005")


def test_individual_iof_calculate_produces_positive_result(disbursement_date):
    iof = IndividualIOF()
    schedule = PriceScheduler.generate_schedule(
        Money("10000"),
        InterestRate("2% monthly"),
        [datetime(2024, 2, 1)],
        disbursement_date,
    )
    result = iof.calculate(schedule, disbursement_date)
    assert result.total.is_positive()


# --- CorporateIOF preset ---


def test_corporate_iof_default_daily_rate():
    iof = CorporateIOF()
    assert iof.daily_rate == Decimal("0.000041")


def test_corporate_iof_default_additional_rate():
    iof = CorporateIOF()
    assert iof.additional_rate == Decimal("0.0038")


def test_corporate_iof_is_instance_of_iof():
    assert isinstance(CorporateIOF(), IOF)


def test_corporate_iof_override_daily_rate():
    iof = CorporateIOF(daily_rate="0.01%")
    assert iof.daily_rate == Decimal("0.0001")


def test_corporate_iof_override_additional_rate():
    iof = CorporateIOF(additional_rate=Decimal("0.005"))
    assert iof.additional_rate == Decimal("0.005")


def test_corporate_iof_calculate_produces_positive_result(disbursement_date):
    iof = CorporateIOF()
    schedule = PriceScheduler.generate_schedule(
        Money("10000"),
        InterestRate("2% monthly"),
        [datetime(2024, 2, 1)],
        disbursement_date,
    )
    result = iof.calculate(schedule, disbursement_date)
    assert result.total.is_positive()


def test_corporate_iof_lower_daily_than_individual(disbursement_date):
    schedule = PriceScheduler.generate_schedule(
        Money("10000"),
        InterestRate("2% monthly"),
        [datetime(2024, 2, 1)],
        disbursement_date,
    )
    individual_result = IndividualIOF().calculate(schedule, disbursement_date)
    corporate_result = CorporateIOF().calculate(schedule, disbursement_date)
    assert corporate_result.total < individual_result.total
