"""Integration: money_warp Loan engine → SQLAlchemy round-trip with balance_at.

Creates a real Loan with fines and mora interest, makes payments (one late),
persists to SA models, and verifies balance_at against settlement data.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from money_warp import Loan, MoraStrategy
from money_warp.interest_rate import InterestRate
from money_warp.money import Money

from .conftest import (
    LoanRecord,
    LoanRecordFactory,
    SettlementRecordFactory,
)

_LOAN_PRINCIPAL = Money("10000")
_LOAN_RATE = InterestRate("6% a")
_LOAN_DISBURSEMENT = datetime(2025, 1, 1, tzinfo=timezone.utc)
_LOAN_DUE_DATES = [
    datetime(2025, 2, 1, tzinfo=timezone.utc),
    datetime(2025, 3, 1, tzinfo=timezone.utc),
    datetime(2025, 4, 1, tzinfo=timezone.utc),
]


def _build_loan_with_payments():
    """Create a loan, make three payments (one late), return (loan, settlements)."""
    loan = Loan(
        _LOAN_PRINCIPAL,
        _LOAN_RATE,
        _LOAN_DUE_DATES,
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


def _persist_loan(session, loan, settlements):
    """Persist a money_warp Loan + Settlements into SA models."""
    sa_loan = LoanRecordFactory(
        principal=loan.principal,
        interest_rate=loan.interest_rate,
        disbursement_date=loan.disbursement_date,
        due_dates=[d.isoformat() for d in loan.due_dates],
    )
    session.add(sa_loan)
    session.flush()

    for s in settlements:
        session.add(
            SettlementRecordFactory(
                loan_id=sa_loan.id,
                amount=s.payment_amount,
                payment_date=s.payment_date,
                remaining_balance=s.remaining_balance,
            )
        )
    session.flush()
    session.expire_all()
    return sa_loan.id


@pytest.fixture()
def loan_with_payments():
    return _build_loan_with_payments()


@pytest.fixture()
def integration_session(engine, loan_with_payments):
    loan, settlements = loan_with_payments
    with Session(engine) as s:
        loan_id = _persist_loan(s, loan, settlements)
        yield s, loan, settlements, loan_id


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


def test_late_payment_remaining_balance_higher_than_on_time():
    """Fines and mora eat into the payment so less principal is retired."""
    _, late_settlements = _build_loan_with_payments()

    on_time_loan = Loan(
        _LOAN_PRINCIPAL,
        _LOAN_RATE,
        _LOAN_DUE_DATES,
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
# balance_at(date) — Python side matches settlement remaining_balance
# ===========================================================================


@pytest.mark.parametrize(
    "as_of,expected_idx",
    [
        (datetime(2025, 1, 15, tzinfo=timezone.utc), None),
        (datetime(2025, 2, 1, tzinfo=timezone.utc), 0),
        (datetime(2025, 2, 15, tzinfo=timezone.utc), 0),
        (datetime(2025, 3, 15, tzinfo=timezone.utc), 1),
        (datetime(2025, 3, 20, tzinfo=timezone.utc), 1),
        (datetime(2025, 4, 1, tzinfo=timezone.utc), 2),
        (datetime(2025, 6, 1, tzinfo=timezone.utc), 2),
    ],
    ids=[
        "before_any_payment",
        "on_first_payment_date",
        "between_first_and_second",
        "on_second_payment_date",
        "between_second_and_third",
        "on_third_payment_date",
        "well_after_all_payments",
    ],
)
def test_balance_at_matches_settlement(integration_session, as_of, expected_idx):
    session, loan, settlements, loan_id = integration_session
    loaded = session.get(LoanRecord, loan_id)

    expected = loan.principal if expected_idx is None else settlements[expected_idx].remaining_balance
    assert loaded.balance_at(as_of) == expected


# ===========================================================================
# balance_at(date) — SQL side matches settlement remaining_balance
# ===========================================================================


@pytest.mark.parametrize(
    "as_of,expected_idx",
    [
        (datetime(2025, 1, 15, tzinfo=timezone.utc), None),
        (datetime(2025, 2, 1, tzinfo=timezone.utc), 0),
        (datetime(2025, 3, 15, tzinfo=timezone.utc), 1),
        (datetime(2025, 4, 1, tzinfo=timezone.utc), 2),
    ],
    ids=[
        "sql_before_any_payment",
        "sql_on_first_payment_date",
        "sql_on_second_payment_date",
        "sql_on_third_payment_date",
    ],
)
def test_balance_at_sql_matches_settlement(integration_session, as_of, expected_idx):
    session, loan, settlements, loan_id = integration_session

    expected = loan.principal if expected_idx is None else settlements[expected_idx].remaining_balance

    results = (
        session.execute(select(LoanRecord).where(LoanRecord.balance_at(as_of) == expected.raw_amount)).scalars().all()
    )
    assert len(results) == 1
    assert results[0].id == loan_id
