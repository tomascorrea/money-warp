"""Integration: money_warp Loan engine -> SQLAlchemy round-trip with balance_at.

Creates a real Loan with fines and mora interest, makes payments (one late),
persists to SA models, and verifies balance_at against settlement data.
"""

import copy
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from money_warp import Loan, MoraStrategy, Warp
from money_warp.interest_rate import InterestRate
from money_warp.money import Money

from .conftest import (
    _LATE_PAYMENT_DUE_DATES,
    LoanRecord,
    LoanRecordFactory,
    StringLoanRecord,
    StringLoanRecordFactory,
)

_LOAN_PRINCIPAL = Money("10000")
_LOAN_RATE = InterestRate("6% a")
_LOAN_DISBURSEMENT = datetime(2025, 1, 1, tzinfo=timezone.utc)


@pytest.fixture()
def loan_with_payments():
    """Loan with three payments (second is late), exposing fine and mora."""
    loan = Loan(
        _LOAN_PRINCIPAL,
        _LOAN_RATE,
        _LATE_PAYMENT_DUE_DATES,
        disbursement_date=_LOAN_DISBURSEMENT,
        fine_rate=Decimal("0.02"),
        grace_period_days=0,
        mora_interest_rate=InterestRate("12% a"),
        mora_strategy=MoraStrategy.COMPOUND,
    )

    schedule = loan.get_original_schedule()

    s1 = loan.record_payment(
        schedule[0].payment_amount,
        datetime(2025, 2, 1, tzinfo=timezone.utc),
    )
    s2 = loan.record_payment(
        schedule[1].payment_amount + Money("200"),
        datetime(2025, 3, 15, tzinfo=timezone.utc),
        interest_date=datetime(2025, 3, 15, tzinfo=timezone.utc),
    )
    s3 = loan.record_payment(
        loan.principal_balance,
        datetime(2025, 4, 1, tzinfo=timezone.utc),
    )

    return loan, [s1, s2, s3]


# ===========================================================================
# Sanity checks on the money_warp Loan itself
# ===========================================================================


def test_late_payment_has_fine_and_mora(loan_with_payments):
    _, settlements = loan_with_payments
    assert settlements[1].fine_paid.is_positive()
    assert settlements[1].mora_paid.is_positive()


def test_on_time_payment_has_no_fine(loan_with_payments):
    _, settlements = loan_with_payments
    assert settlements[0].fine_paid.is_zero()
    assert settlements[0].mora_paid.is_zero()


def test_late_payment_remaining_balance_higher_than_on_time(loan_with_payments):
    """Fines and mora eat into the payment so less principal is retired."""
    _, late_settlements = loan_with_payments

    on_time_loan = Loan(
        _LOAN_PRINCIPAL,
        _LOAN_RATE,
        _LATE_PAYMENT_DUE_DATES,
        disbursement_date=_LOAN_DISBURSEMENT,
        fine_rate=Decimal("0.02"),
        mora_interest_rate=InterestRate("12% a"),
    )
    schedule = on_time_loan.get_original_schedule()
    on_time_loan.record_payment(
        schedule[0].payment_amount,
        datetime(2025, 2, 1, tzinfo=timezone.utc),
    )
    on_time_s2 = on_time_loan.record_payment(
        schedule[1].payment_amount + Money("200"),
        datetime(2025, 3, 1, tzinfo=timezone.utc),
    )

    assert late_settlements[1].remaining_balance > on_time_s2.remaining_balance


# ===========================================================================
# balance_at proves fine and mora are captured (Python side)
# ===========================================================================


@pytest.mark.parametrize(
    "warp_to",
    [
        datetime(2025, 1, 15, tzinfo=timezone.utc),
        datetime(2025, 2, 1, tzinfo=timezone.utc),
        datetime(2025, 2, 15, tzinfo=timezone.utc),
        datetime(2025, 3, 15, tzinfo=timezone.utc),
        datetime(2025, 3, 20, tzinfo=timezone.utc),
        datetime(2025, 4, 1, tzinfo=timezone.utc),
    ],
)
def test_balance_reflects_fine_and_mora(session, warp_to):
    """Warp time, then assert balance equals the exact money_warp value.

    We deep-copy the loan and clear ``fines_applied`` so that
    ``calculate_late_fines`` inside Warp recomputes fines purely for
    ``warp_to``, matching what ``balance_at`` does (point-in-time view
    without phantom fines from future settlements).
    """
    sa_loan = LoanRecordFactory(with_late_payment=True)

    loan = copy.deepcopy(sa_loan._mw_loan)
    loan.fines_applied = {}
    with Warp(loan, warp_to) as warped_loan:
        assert warped_loan.current_balance == sa_loan.balance_at(warp_to)


# ===========================================================================
# balance_at(date) — SQL side approximation
# ===========================================================================


@pytest.mark.parametrize(
    "warp_to",
    [
        datetime(2025, 1, 15, tzinfo=timezone.utc),
        datetime(2025, 2, 1, tzinfo=timezone.utc),
        datetime(2025, 2, 15, tzinfo=timezone.utc),
        datetime(2025, 3, 15, tzinfo=timezone.utc),
        datetime(2025, 3, 20, tzinfo=timezone.utc),
        datetime(2025, 4, 1, tzinfo=timezone.utc),
    ],
)
def test_balance_at_sql_matches_python(session, warp_to):
    """SQL CTE expression matches the Python-side balance_at."""
    sa_loan = LoanRecordFactory(with_late_payment=True)
    session.expire_all()
    loaded = session.get(LoanRecord, sa_loan.id)

    expected = float(loaded.balance_at(warp_to).raw_amount)

    sql_result = session.execute(select(LoanRecord.balance_at(warp_to)).where(LoanRecord.id == sa_loan.id)).scalar()

    assert float(sql_result.raw_amount) == pytest.approx(expected, abs=1e-4)


# ===========================================================================
# balance_at(date) — SQL side with various rate periods
# ===========================================================================


@pytest.mark.parametrize(
    "rate_str",
    [
        "10% a",
        "1% m",
        "3% q",
        "5% s",
        "0.03% d",
    ],
    ids=["annual", "monthly", "quarterly", "semi_annual", "daily"],
)
def test_balance_at_sql_matches_python_various_interest_rate_periods(session, rate_str):
    """SQL CTE correctly converts non-annual interest rates to daily."""
    sa_loan = LoanRecordFactory(interest_rate=InterestRate(rate_str))
    session.expire_all()
    loaded = session.get(LoanRecord, sa_loan.id)

    as_of = datetime(2024, 1, 20, tzinfo=timezone.utc)
    expected = float(loaded.balance_at(as_of).raw_amount)

    sql_result = session.execute(select(LoanRecord.balance_at(as_of)).where(LoanRecord.id == sa_loan.id)).scalar()

    assert float(sql_result.raw_amount) == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize(
    "mora_rate_str",
    [
        "12% a",
        "1% m",
        "3% q",
    ],
    ids=["annual", "monthly", "quarterly"],
)
def test_balance_at_sql_matches_python_various_mora_rate_periods(session, mora_rate_str):
    """SQL CTE correctly converts non-annual mora interest rates to daily."""
    sa_loan = LoanRecordFactory(
        interest_rate=InterestRate("6% a"),
        mora_interest_rate=InterestRate(mora_rate_str),
        mora_strategy="COMPOUND",
        fine_rate=Decimal("0.02"),
        grace_period_days=0,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        due_dates=[d.isoformat() for d in _LATE_PAYMENT_DUE_DATES],
    )
    session.expire_all()
    loaded = session.get(LoanRecord, sa_loan.id)

    as_of = datetime(2025, 3, 20, tzinfo=timezone.utc)
    expected = float(loaded.balance_at(as_of).raw_amount)

    sql_result = session.execute(select(LoanRecord.balance_at(as_of)).where(LoanRecord.id == sa_loan.id)).scalar()

    assert float(sql_result.raw_amount) == pytest.approx(expected, abs=1e-4)


# ===========================================================================
# balance_at(date) — string representation SQL side
# ===========================================================================


@pytest.mark.parametrize(
    "rate_str",
    [
        "10% a",
        "1% m",
        "3% q",
        "5% s",
        "0.03% d",
    ],
    ids=["annual", "monthly", "quarterly", "semi_annual", "daily"],
)
def test_string_repr_balance_at_sql_matches_python(session, rate_str):
    """SQL CTE with string-representation rates matches Python balance."""
    sa_loan = StringLoanRecordFactory(interest_rate=InterestRate(rate_str))
    session.expire_all()
    loaded = session.get(StringLoanRecord, sa_loan.id)

    as_of = datetime(2024, 1, 20, tzinfo=timezone.utc)
    expected = float(loaded.balance_at(as_of).raw_amount)

    sql_result = session.execute(
        select(StringLoanRecord.balance_at(as_of)).where(StringLoanRecord.id == sa_loan.id)
    ).scalar()

    assert float(sql_result.raw_amount) == pytest.approx(expected, abs=1e-4)


@pytest.mark.parametrize(
    "mora_rate_str",
    [
        "12% a",
        "1% m",
        "3% q",
    ],
    ids=["annual", "monthly", "quarterly"],
)
def test_string_repr_balance_at_sql_matches_python_mora(session, mora_rate_str):
    """SQL CTE with string-representation mora rates matches Python balance."""
    sa_loan = StringLoanRecordFactory(
        interest_rate=InterestRate("6% a"),
        mora_interest_rate=InterestRate(mora_rate_str),
        mora_strategy="COMPOUND",
        fine_rate=Decimal("0.02"),
        grace_period_days=0,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        due_dates=[d.isoformat() for d in _LATE_PAYMENT_DUE_DATES],
    )
    session.expire_all()
    loaded = session.get(StringLoanRecord, sa_loan.id)

    as_of = datetime(2025, 3, 20, tzinfo=timezone.utc)
    expected = float(loaded.balance_at(as_of).raw_amount)

    sql_result = session.execute(
        select(StringLoanRecord.balance_at(as_of)).where(StringLoanRecord.id == sa_loan.id)
    ).scalar()

    assert float(sql_result.raw_amount) == pytest.approx(expected, abs=1e-4)
