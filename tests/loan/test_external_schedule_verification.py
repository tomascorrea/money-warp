"""Verify PriceScheduler output against an external Brazilian lending system.

The reference schedule comes from a PRICE amortization loan with BASE_365
daily compounding, 1% monthly interest, 12 periods, principal of 10,000.
IOF fields are ignored -- only interest, principal, and balance are checked.

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
"""

from datetime import datetime
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money

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


@pytest.fixture(scope="module")
def external_loan_schedule():
    principal = Money("10000")
    interest_rate = InterestRate("1% m")
    disbursement_date = datetime(2026, 2, 22)
    due_dates = [
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
    loan = Loan(principal, interest_rate, due_dates, disbursement_date)
    return loan.get_original_schedule()


@pytest.mark.parametrize("period_idx", range(11))
def test_price_schedule_pmt_matches_external(external_loan_schedule, period_idx):
    assert external_loan_schedule[period_idx].payment_amount.real_amount == EXPECTED_PMT


def test_price_schedule_last_pmt_by_difference(external_loan_schedule):
    assert external_loan_schedule[-1].payment_amount.real_amount == Decimal(OUR_LAST_PERIOD["payment"])


def test_price_schedule_total_owed(external_loan_schedule):
    total = sum(
        (entry.payment_amount.real_amount for entry in external_loan_schedule),
        Decimal("0"),
    )
    assert total == EXPECTED_PMT * 11 + Decimal(OUR_LAST_PERIOD["payment"])


@pytest.mark.parametrize(
    "period_idx,expected",
    [(i, row) for i, row in enumerate(EXTERNAL_SCHEDULE[:11])],
    ids=[f"period-{row['period']}" for row in EXTERNAL_SCHEDULE[:11]],
)
def test_price_schedule_interest_matches_external(external_loan_schedule, period_idx, expected):
    assert external_loan_schedule[period_idx].interest_payment.real_amount == Decimal(expected["interest"])


def test_price_schedule_last_interest_by_difference(external_loan_schedule):
    assert external_loan_schedule[-1].interest_payment.real_amount == Decimal(OUR_LAST_PERIOD["interest"])


@pytest.mark.parametrize(
    "period_idx,expected",
    [(i, row) for i, row in enumerate(EXTERNAL_SCHEDULE[:11])],
    ids=[f"period-{row['period']}" for row in EXTERNAL_SCHEDULE[:11]],
)
def test_price_schedule_principal_matches_external(external_loan_schedule, period_idx, expected):
    assert external_loan_schedule[period_idx].principal_payment.real_amount == Decimal(expected["principal"])


def test_price_schedule_last_principal_by_difference(external_loan_schedule):
    assert external_loan_schedule[-1].principal_payment.real_amount == Decimal(OUR_LAST_PERIOD["principal"])


@pytest.mark.parametrize(
    "period_idx,expected",
    [(i, row) for i, row in enumerate(EXTERNAL_SCHEDULE)],
    ids=[f"period-{row['period']}" for row in EXTERNAL_SCHEDULE],
)
def test_price_schedule_balance_matches_external(external_loan_schedule, period_idx, expected):
    assert external_loan_schedule[period_idx].ending_balance.real_amount == Decimal(expected["balance"])


@pytest.mark.parametrize(
    "period_idx,expected",
    [(i, row) for i, row in enumerate(EXTERNAL_SCHEDULE)],
    ids=[f"period-{row['period']}" for row in EXTERNAL_SCHEDULE],
)
def test_price_schedule_days_in_period_matches_external(external_loan_schedule, period_idx, expected):
    assert external_loan_schedule[period_idx].days_in_period == expected["days"]


def test_price_schedule_final_balance_is_zero(external_loan_schedule):
    assert external_loan_schedule[-1].ending_balance.real_amount == Decimal("0.00")


def test_price_schedule_total_principal_equals_loan_amount(external_loan_schedule):
    assert external_loan_schedule.total_principal.real_amount == Decimal("10000.00")


@pytest.mark.parametrize(
    "principal,expected",
    [
        ["1000", "88.81"],
        ["3342", "296.8"],
        ["7654", "679.74"],
        ["5343", "474.5"],
        ["54354353", "4827111.92"],
        ["4534535", "402703.86"],
        ["70000", "6216.57"],
        ["453553", "40279.22"],
    ],
)
def test_external_loan_schedule_by_principal(principal, expected):
    principal = Money(principal)
    interest_rate = InterestRate("1% m", precision=6)
    disbursement_date = datetime(2026, 2, 22)
    due_dates = [
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
    loan = Loan(principal, interest_rate, due_dates, disbursement_date)
    schedule = loan.get_original_schedule()
    assert schedule[0].payment_amount.real_amount == Decimal(expected)
