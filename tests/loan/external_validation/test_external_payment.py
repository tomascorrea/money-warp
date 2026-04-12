"""Verify that paying every installment with the external system's amounts
results in a fully paid-off loan.

Each test case pays the external schedule's per-installment interest +
principal via ``pay_installment``.  The tolerance adjustment CashFlowItem
absorbs the small per-period rounding difference, preventing error
accumulation and ensuring ``is_paid_off`` is True at the end.

The full suite (1200 cases) is marked ``slow`` and skipped by default.
Run ``pytest -m slow`` to include it.  The fast sampled test below runs
50 random cases on every invocation.
"""

import json
import random
from datetime import datetime
from pathlib import Path

import pytest

from money_warp import InterestRate, Loan, Money, Warp

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixtures():
    cases = []
    for fixture in sorted(FIXTURES_DIR.glob("2026-*.json")):
        with open(fixture) as f:
            data = json.load(f)
        cases.extend(list(d.values()) for d in data)
    return cases


def _pay_external_schedule(case):
    """Pay every installment with the external system's amounts and assert paid off."""
    principal, rate, _, disbursement_date, due_dates, _, external_schedule = case
    loan = Loan(
        Money(principal),
        InterestRate(rate, precision=6),
        disbursement_date=datetime.strptime(disbursement_date, "%Y-%m-%d"),
        due_dates=[datetime.strptime(d, "%Y-%m-%d").date() for d in due_dates],
    )

    for index, instalment in enumerate(external_schedule):
        due_date = datetime.strptime(due_dates[index], "%Y-%m-%d")
        with Warp(loan, due_date) as warped:
            warped.pay_installment(Money(instalment["interest"] + instalment["principal"]))
        loan = warped

    due_date = datetime.strptime(due_dates[-1], "%Y-%m-%d")
    with Warp(loan, due_date) as warped:
        assert (
            warped.is_paid_off is True
        ), f"principal={principal}, rate={rate}, balance={warped.current_balance}, n={len(due_dates)}"


# ---------------------------------------------------------------------------
# Fast: 50 random cases (runs by default)
# ---------------------------------------------------------------------------

_ALL_FIXTURES = _load_fixtures()
_SAMPLE = random.Random(42).sample(_ALL_FIXTURES, min(50, len(_ALL_FIXTURES)))


@pytest.mark.parametrize(
    "principal,rate,expected_pmt,disbursement_date,due_dates,annual_interest_rate,external_schedule",
    _SAMPLE,
)
def test_external_loan_paid_off_sampled(
    principal,
    rate,
    expected_pmt,
    disbursement_date,
    due_dates,
    annual_interest_rate,
    external_schedule,
):
    _pay_external_schedule(
        (principal, rate, expected_pmt, disbursement_date, due_dates, annual_interest_rate, external_schedule)
    )


# ---------------------------------------------------------------------------
# Slow: all 1200 cases (opt-in with pytest -m slow)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.parametrize(
    "principal,rate,expected_pmt,disbursement_date,due_dates,annual_interest_rate,external_schedule",
    _ALL_FIXTURES,
)
def test_external_loan_paid_off_with_external_amounts(
    principal,
    rate,
    expected_pmt,
    disbursement_date,
    due_dates,
    annual_interest_rate,
    external_schedule,
):
    _pay_external_schedule(
        (principal, rate, expected_pmt, disbursement_date, due_dates, annual_interest_rate, external_schedule)
    )
