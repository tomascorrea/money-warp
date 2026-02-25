"""Verify PriceScheduler and IOF output against an external Brazilian lending system.

The reference schedule comes from a PRICE amortization loan with BASE_365
daily compounding, 1% monthly interest, 12 periods, principal of 10,000.

Last-payment difference
-----------------------
Our PriceScheduler rounds PMT, interest, and balance to 2 decimal places at
every step, matching the external system for periods 1 through N-1.  The last
installment is computed by difference (remaining_balance + true_interest) so
the final balance is exactly zero.  The external system instead keeps the same
PMT for the last period and adjusts the interest/principal split.

As a result, periods 1-11 match the external system exactly, while period 12
has a slightly different payment amount (888.10 vs 888.08) and interest
(8.96 vs 8.94).  Both approaches zero out the balance.

IOF rounding
------------
The external system rounds each IOF component (daily and additional) to 2
decimal places before summing them per installment.  Our IOFRounding.PER_COMPONENT
mode replicates this and matches periods 1-11 exactly.  Period 12 has a 1-cent
difference (29.65 vs 29.64) that propagates to the total (201.89 vs 201.88).
This mirrors the last-payment-by-difference discrepancy in the schedule itself.

Our default IOFRounding.PRECISE mode keeps full precision during component
addition and rounds once per installment; it stays within 1 cent of every
external value.
"""

from datetime import datetime
from decimal import Decimal

import pytest

from money_warp import IOF, InterestRate, IOFRounding, Loan, Money, PriceScheduler

EXTERNAL_SCHEDULE = [
    {"period": 1, "days": 28, "payment": "888.08", "interest": "92.02", "principal": "796.06", "balance": "9203.94"},
    {"period": 2, "days": 31, "payment": "888.08", "interest": "93.81", "principal": "794.27", "balance": "8409.67"},
    {"period": 3, "days": 30, "payment": "888.08", "interest": "82.94", "principal": "805.14", "balance": "7604.53"},
    {"period": 4, "days": 31, "payment": "888.08", "interest": "77.51", "principal": "810.57", "balance": "6793.96"},
    {"period": 5, "days": 30, "payment": "888.08", "interest": "67.00", "principal": "821.08", "balance": "5972.88"},
    {"period": 6, "days": 31, "payment": "888.08", "interest": "60.88", "principal": "827.20", "balance": "5145.68"},
    {"period": 7, "days": 31, "payment": "888.08", "interest": "52.45", "principal": "835.63", "balance": "4310.05"},
    {"period": 8, "days": 30, "payment": "888.08", "interest": "42.51", "principal": "845.57", "balance": "3464.48"},
    {"period": 9, "days": 31, "payment": "888.08", "interest": "35.31", "principal": "852.77", "balance": "2611.71"},
    {"period": 10, "days": 30, "payment": "888.08", "interest": "25.76", "principal": "862.32", "balance": "1749.39"},
    {"period": 11, "days": 31, "payment": "888.08", "interest": "17.83", "principal": "870.25", "balance": "879.14"},
    {"period": 12, "days": 31, "payment": "888.08", "interest": "8.94", "principal": "879.14", "balance": "0.00"},
]

OUR_LAST_PERIOD = {"payment": "888.10", "interest": "8.96", "principal": "879.14", "balance": "0.00"}

EXPECTED_PMT = Decimal("888.08")

EXTERNAL_IOF = [
    {"period": 1, "iof": "4.86"},
    {"period": 2, "iof": "6.86"},
    {"period": 3, "iof": "8.94"},
    {"period": 4, "iof": "11.06"},
    {"period": 5, "iof": "13.22"},
    {"period": 6, "iof": "15.42"},
    {"period": 7, "iof": "17.71"},
    {"period": 8, "iof": "19.99"},
    {"period": 9, "iof": "22.33"},
    {"period": 10, "iof": "24.71"},
    {"period": 11, "iof": "27.14"},
    {"period": 12, "iof": "29.64"},
]

EXTERNAL_TOTAL_IOF = Decimal("201.88")

OUR_LAST_PERIOD_IOF = Decimal("29.65")

ONE_CENT = Decimal("0.01")
TWO_CENTS = Decimal("0.02")


@pytest.fixture(scope="module")
def external_loan_schedule():
    principal = Money("10000")
    interest_rate = InterestRate("1% m")
    loan = Loan(principal, interest_rate, DUE_DATES, DISBURSEMENT_DATE)
    return loan.get_original_schedule()


@pytest.mark.parametrize("period_idx", range(11))
def test_price_schedule_pmt_matches_external(external_loan_schedule, period_idx):
    assert external_loan_schedule[period_idx].payment_amount == EXPECTED_PMT


def test_price_schedule_last_pmt_by_difference(external_loan_schedule):
    assert external_loan_schedule[-1].payment_amount == Decimal(OUR_LAST_PERIOD["payment"])


def test_price_schedule_total_owed(external_loan_schedule):
    total = sum(
        (entry.payment_amount for entry in external_loan_schedule),
        Money.zero(),
    )
    assert total == EXPECTED_PMT * 11 + Decimal(OUR_LAST_PERIOD["payment"])


@pytest.mark.parametrize(
    "period_idx,expected",
    [(i, row) for i, row in enumerate(EXTERNAL_SCHEDULE[:11])],
    ids=[f"period-{row['period']}" for row in EXTERNAL_SCHEDULE[:11]],
)
def test_price_schedule_interest_matches_external(external_loan_schedule, period_idx, expected):
    assert external_loan_schedule[period_idx].interest_payment == Decimal(expected["interest"])


def test_price_schedule_last_interest_by_difference(external_loan_schedule):
    assert external_loan_schedule[-1].interest_payment == Decimal(OUR_LAST_PERIOD["interest"])


@pytest.mark.parametrize(
    "period_idx,expected",
    [(i, row) for i, row in enumerate(EXTERNAL_SCHEDULE[:11])],
    ids=[f"period-{row['period']}" for row in EXTERNAL_SCHEDULE[:11]],
)
def test_price_schedule_principal_matches_external(external_loan_schedule, period_idx, expected):
    assert external_loan_schedule[period_idx].principal_payment == Decimal(expected["principal"])


def test_price_schedule_last_principal_by_difference(external_loan_schedule):
    assert external_loan_schedule[-1].principal_payment == Decimal(OUR_LAST_PERIOD["principal"])


@pytest.mark.parametrize(
    "period_idx,expected",
    [(i, row) for i, row in enumerate(EXTERNAL_SCHEDULE)],
    ids=[f"period-{row['period']}" for row in EXTERNAL_SCHEDULE],
)
def test_price_schedule_balance_matches_external(external_loan_schedule, period_idx, expected):
    assert external_loan_schedule[period_idx].ending_balance == Decimal(expected["balance"])


@pytest.mark.parametrize(
    "period_idx,expected",
    [(i, row) for i, row in enumerate(EXTERNAL_SCHEDULE)],
    ids=[f"period-{row['period']}" for row in EXTERNAL_SCHEDULE],
)
def test_price_schedule_days_in_period_matches_external(external_loan_schedule, period_idx, expected):
    assert external_loan_schedule[period_idx].days_in_period == expected["days"]


def test_price_schedule_final_balance_is_zero(external_loan_schedule):
    assert external_loan_schedule[-1].ending_balance == Decimal("0.00")


def test_price_schedule_total_principal_equals_loan_amount(external_loan_schedule):
    assert external_loan_schedule.total_principal == Decimal("10000.00")


DISBURSEMENT_DATE = datetime(2026, 2, 22)

DUE_DATES = [
    datetime(2026, 3, 22),
    datetime(2026, 4, 22),
    datetime(2026, 5, 22),
    datetime(2026, 6, 22),
    datetime(2026, 7, 22),
    datetime(2026, 8, 22),
    datetime(2026, 9, 22),
    datetime(2026, 10, 22),
    datetime(2026, 11, 22),
    datetime(2026, 12, 22),
    datetime(2027, 1, 22),
    datetime(2027, 2, 22),
]

IOF_DAILY_RATE = Decimal("0.000082")
IOF_ADDITIONAL_RATE = Decimal("0.0038")


@pytest.fixture(scope="module")
def external_iof_per_component():
    principal = Money("10000")
    rate = InterestRate("1% m")
    schedule = PriceScheduler.generate_schedule(principal, rate, DUE_DATES, DISBURSEMENT_DATE)
    iof = IOF(
        daily_rate=IOF_DAILY_RATE,
        additional_rate=IOF_ADDITIONAL_RATE,
        rounding=IOFRounding.PER_COMPONENT,
    )
    return iof.calculate(schedule, DISBURSEMENT_DATE)


@pytest.fixture(scope="module")
def external_iof_precise():
    principal = Money("10000")
    rate = InterestRate("1% m")
    schedule = PriceScheduler.generate_schedule(principal, rate, DUE_DATES, DISBURSEMENT_DATE)
    iof = IOF(
        daily_rate=IOF_DAILY_RATE,
        additional_rate=IOF_ADDITIONAL_RATE,
        rounding=IOFRounding.PRECISE,
    )
    return iof.calculate(schedule, DISBURSEMENT_DATE)


# --- IOF: PER_COMPONENT rounding (matches external system) ---


@pytest.mark.parametrize(
    "period_idx,expected",
    [(i, row) for i, row in enumerate(EXTERNAL_IOF[:11])],
    ids=[f"period-{row['period']}" for row in EXTERNAL_IOF[:11]],
)
def test_iof_per_component_matches_external(external_iof_per_component, period_idx, expected):
    assert external_iof_per_component.per_installment[period_idx].tax_amount.real_amount == Decimal(expected["iof"])


def test_iof_per_component_last_period_by_difference(external_iof_per_component):
    assert external_iof_per_component.per_installment[-1].tax_amount.real_amount == OUR_LAST_PERIOD_IOF


def test_iof_per_component_total_within_one_cent(external_iof_per_component):
    assert abs(external_iof_per_component.total.real_amount - EXTERNAL_TOTAL_IOF) <= ONE_CENT


# --- IOF: PRECISE rounding (default, within 1 cent of external) ---


@pytest.mark.parametrize(
    "period_idx,expected",
    [(i, row) for i, row in enumerate(EXTERNAL_IOF)],
    ids=[f"period-{row['period']}" for row in EXTERNAL_IOF],
)
def test_iof_precise_within_one_cent_of_external(external_iof_precise, period_idx, expected):
    diff = abs(external_iof_precise.per_installment[period_idx].tax_amount.real_amount - Decimal(expected["iof"]))
    assert diff <= ONE_CENT


def test_iof_precise_total_within_two_cents(external_iof_precise):
    assert abs(external_iof_precise.total.real_amount - EXTERNAL_TOTAL_IOF) <= TWO_CENTS


# --- PMT verification across various principals and rates ---


@pytest.mark.parametrize(
    "principal,rate,expected",
    [
        ["1000", "1.0% m", "88.81"],
        ["1000", "2.0% m", "94.47"],
        ["1000", "3.0% m", "100.32"],
        ["1000", "4.0% m", "106.35"],
        ["1000", "5.0% m", "112.56"],
        ["3342", "1.0% m", "296.8"],
        ["3342", "2.0% m", "315.73"],
        ["3342", "3.0% m", "335.27"],
        ["3342", "4.0% m", "355.43"],
        ["3342", "5.0% m", "376.17"],
        ["7654", "1.0% m", "679.74"],
        ["7654", "2.0% m", "723.09"],
        ["7654", "3.0% m", "767.86"],
        ["7654", "4.0% m", "814.02"],
        ["7654", "5.0% m", "861.52"],
        ["5343", "1.0% m", "474.5"],
        ["5343", "2.0% m", "504.77"],
        ["5343", "3.0% m", "536.02"],
        ["5343", "4.0% m", "568.24"],
        ["5343", "5.0% m", "601.4"],
        ["54354353", "1.0% m", "4827111.92"],
        ["54354353", "2.0% m", "5134981.55"],
        ["54354353", "3.0% m", "5452916.69"],
        ["54354353", "4.0% m", "5780675.55"],
        ["54354353", "5.0% m", "6117997.65"],
        ["4534535", "1.0% m", "402703.86"],
        ["4534535", "2.0% m", "428388.02"],
        ["4534535", "3.0% m", "454911.89"],
        ["4534535", "4.0% m", "482255.31"],
        ["4534535", "5.0% m", "510396.55"],
        ["70000", "1.0% m", "6216.57"],
        ["70000", "2.0% m", "6613.06"],
        ["70000", "3.0% m", "7022.51"],
        ["70000", "4.0% m", "7444.62"],
        ["70000", "5.0% m", "7879.03"],
        ["453553", "1.0% m", "40279.22"],
        ["453553", "2.0% m", "42848.2"],
        ["453553", "3.0% m", "45501.17"],
        ["453553", "4.0% m", "48236.11"],
        ["453553", "5.0% m", "51050.85"],
    ],
)
def test_external_loan_schedule_by_principal(principal, rate, expected):
    principal = Money(principal)
    interest_rate = InterestRate(rate, precision=6)
    loan = Loan(principal, interest_rate, DUE_DATES, DISBURSEMENT_DATE)
    schedule = loan.get_original_schedule()
    assert schedule[0].payment_amount == Decimal(expected)
