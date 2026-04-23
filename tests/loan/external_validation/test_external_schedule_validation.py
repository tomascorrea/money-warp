"""Verify PriceScheduler PMT against an external Brazilian lending system.

Cross-validates parameter combinations across PRICE amortization with
BASE_365 daily compounding and 12 monthly periods.

The external system finances IOF into the principal (``financed_iof=True``),
so each test case uses ``financed_amount`` -- not the raw requested amount --
as the loan principal.

Why a 1-cent tolerance
----------------------
Our analytic PMT matches the external's PMT to within 1 cent across the full
fixture set: ~90% of cases are exact and the remaining ~10% drift by exactly
1 cent in either direction (never more).

This residual is **not** a numeric precision issue. An empirical sweep in
``_investigate_csharp_precision.py`` found:

- Every decimal/double/``Math.Pow`` variant (full ``Decimal``, Python ``float``
  end-to-end, ``Decimal`` at 15-digit context) produces the *same*
  cent-rounded PMT as the baseline. Python's arbitrary precision is **not**
  the culprit.
- The external uses the same day count we do: ``running_day`` matches in
  100% of 3450 cases.
- Among the ~10% of PMT-mismatched cases, ~97% have period-1 **interest**
  matching the external exactly -- only the PMT itself differs by 1 cent.
  That means accrual is correct; the 1-cent drift comes from the external
  computing PMT via a grossup/IOF fixed-point iteration that rounds PMT along
  the way, rather than from the closed-form analytic PMT formula we use.
- The tiny remaining population (~0.3% of all cases, 10/3450) has period-1
  interest that differs by 1 cent from ours, consistent with the external
  applying a slightly different per-period rounding on the unrounded accrual
  (e.g. ``ROUND_DOWN`` in some edge cases) that we can't reproduce without
  access to its source.

Python is not less accurate than C# here; the two engines simply quantize
intermediates in different places.
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
