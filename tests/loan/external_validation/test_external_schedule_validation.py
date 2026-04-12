"""Verify PriceScheduler PMT against an external Brazilian lending system.

Cross-validates parameter combinations across PRICE amortization with
BASE_365 daily compounding and 12 monthly periods.

The external system finances IOF into the principal (``financed_iof=True``),
so each test case uses ``financed_amount`` -- not the raw requested amount --
as the loan principal.

Grossup rounding
----------------
The external system's grossup can land on a ``financed_amount`` that is 1 cent
different from our solver's result.  That 1-cent principal difference
propagates to a 1-cent PMT difference.  We therefore assert within 1-cent
tolerance rather than exact equality.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from money_warp import InterestRate, Loan, Money

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixtures():
    cases = []
    for fixture in sorted(FIXTURES_DIR.glob("2026-*.json")):
        with open(fixture) as f:
            data = json.load(f)
        cases.extend(list(d.values()) for d in data)
    return cases


@pytest.mark.parametrize(
    "principal,rate,expected_pmt,disbursement_date,due_dates,annual_interest_rate,external_schedule",
    _load_fixtures(),
)
def test_external_loan_pmt_within_one_cent(
    principal,
    rate,
    expected_pmt,
    disbursement_date,
    due_dates,
    annual_interest_rate,
    external_schedule,
):
    loan = Loan(
        Money(principal),
        InterestRate(rate, precision=6),
        disbursement_date=datetime.strptime(disbursement_date, "%Y-%m-%d"),
        due_dates=[datetime.strptime(d, "%Y-%m-%d").date() for d in due_dates],
    )

    our_schedule = loan.get_original_schedule()
    assert float(our_schedule[0].payment_amount.real_amount) == pytest.approx(expected_pmt, abs=0.011)
