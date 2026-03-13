# ruff: noqa: A003
"""Tests for settlement_bridge, loan_bridge, balance, and balance_at."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, create_engine, select
from sqlalchemy.orm import Session, relationship

from money_warp import Warp
from money_warp.ext.sa import MoneyType, loan_bridge, settlement_bridge
from money_warp.money import Money

from .conftest import (
    Base,
    LoanRecord,
    LoanRecordFactory,
    SettlementRecord,
    SettlementRecordFactory,
)

# ===========================================================================
# settlement_bridge — metadata
# ===========================================================================


def test_settlement_bridge_defaults():
    assert SettlementRecord._money_warp_bridge_meta == {
        "balance": "remaining_balance",
        "date": "payment_date",
        "amount": "amount",
        "interest_date": "interest_date",
        "processing_date": "processing_date",
        "intention": "intention",
    }


def test_settlement_bridge_custom_names():
    @settlement_bridge(
        balance="bal",
        date="settled_at",
        amount="paid",
        interest_date="int_dt",
        processing_date="proc_dt",
        intention="intent",
    )
    class Custom(Base):
        __tablename__ = "custom_settlements"
        id = Column(Integer, primary_key=True)

    assert Custom._money_warp_bridge_meta == {
        "balance": "bal",
        "date": "settled_at",
        "amount": "paid",
        "interest_date": "int_dt",
        "processing_date": "proc_dt",
        "intention": "intent",
    }


# ===========================================================================
# loan_bridge — metadata
# ===========================================================================


def test_loan_bridge_stores_metadata():
    assert LoanRecord._money_warp_bridge_meta == {
        "principal": "principal",
        "settlements": "settlements",
        "interest_rate": "interest_rate",
        "due_dates": "due_dates",
        "disbursement_date": "disbursement_date",
        "fine_rate": "fine_rate",
        "grace_period_days": "grace_period_days",
        "mora_interest_rate": "mora_interest_rate",
        "mora_strategy": "mora_strategy",
    }


# ===========================================================================
# _load_money_warp_loan — raises on missing required fields
# ===========================================================================


def test_load_money_warp_loan_raises_when_interest_rate_none(session):
    loan = LoanRecordFactory(interest_rate=None)
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)

    with pytest.raises(ValueError, match="interest_rate"):
        loaded._load_money_warp_loan()


# ===========================================================================
# balance_at hybrid_method (Python side) — uses Loan reconstruction
# ===========================================================================


def test_balance_at_no_settlements_includes_accrued_interest(session):
    loan = LoanRecordFactory()
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)

    result = loaded.balance_at(datetime(2024, 2, 1, tzinfo=timezone.utc))
    assert result > Money("10000")


def test_balance_at_matches_loan_current_balance(session):
    loan = LoanRecordFactory()
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)
    as_of = datetime(2024, 2, 15, tzinfo=timezone.utc)

    mw_loan = loaded._load_money_warp_loan()
    with Warp(mw_loan, as_of) as warped:
        expected = warped.current_balance
    assert loaded.balance_at(as_of) == expected


def test_balance_at_with_settlement_reflects_post_payment_interest(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        amount=Money("3000"),
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("7500"),
    )
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)

    as_of = datetime(2024, 2, 15, tzinfo=timezone.utc)
    result = loaded.balance_at(as_of)
    mw_loan = loaded._load_money_warp_loan()
    with Warp(mw_loan, as_of) as warped:
        expected = warped.current_balance
    assert result == expected


def test_balance_delegates_to_balance_at(session):
    loan = LoanRecordFactory()
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)

    assert loaded.balance == loaded.balance_at(datetime.now(tz=timezone.utc))


# ===========================================================================
# balance_at hybrid_method (SQL side)
# ===========================================================================


def test_balance_at_sql_filter(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        amount=Money("3000"),
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("7500"),
    )
    SettlementRecordFactory(
        loan_id=loan.id,
        amount=Money("7000"),
        payment_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
        remaining_balance=Money("500"),
    )

    results = (
        session.execute(select(LoanRecord).where(LoanRecord.balance_at(datetime(2024, 2, 15)) > Decimal("5000")))
        .scalars()
        .all()
    )
    assert len(results) == 1


def test_balance_at_sql_before_settlements(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
    )

    results = (
        session.execute(select(LoanRecord).where(LoanRecord.balance_at(datetime(2024, 1, 15)) > Decimal("9000")))
        .scalars()
        .all()
    )
    assert len(results) == 1


def test_balance_at_sql_order_by(session):
    loan1 = LoanRecordFactory(principal=Money("10000"))
    loan2 = LoanRecordFactory(principal=Money("5000"))
    SettlementRecordFactory(
        loan_id=loan1.id,
        amount=Money("7500"),
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("3000"),
    )

    results = (
        session.execute(select(LoanRecord).order_by(LoanRecord.balance_at(datetime(2024, 2, 15)).desc()))
        .scalars()
        .all()
    )
    assert results[0].id == loan2.id
    assert results[1].id == loan1.id


# ===========================================================================
# balance hybrid_property (SQL side)
# ===========================================================================


def test_balance_filter_gt(session):
    loan1 = LoanRecordFactory(principal=Money("10000"))
    LoanRecordFactory(principal=Money("500"))

    results = session.execute(select(LoanRecord).where(LoanRecord.balance > Decimal("1000"))).scalars().all()
    assert len(results) == 1
    assert results[0].id == loan1.id


def test_balance_filter_with_settlements(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        amount=Money("9500"),
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("800"),
    )

    results = session.execute(select(LoanRecord).where(LoanRecord.balance < Decimal("1000"))).scalars().all()
    assert len(results) == 1


def test_balance_order_by(session):
    loan1 = LoanRecordFactory(principal=Money("5000"))
    loan2 = LoanRecordFactory(principal=Money("20000"))
    loan3 = LoanRecordFactory(principal=Money("1000"))

    results = session.execute(select(LoanRecord).order_by(LoanRecord.balance.desc())).scalars().all()
    assert [r.id for r in results] == [loan2.id, loan1.id, loan3.id]


def test_balance_filter_paid_off(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        amount=Money("10000"),
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("0"),
    )

    results = session.execute(select(LoanRecord).where(LoanRecord.balance <= Decimal("0"))).scalars().all()
    assert len(results) == 1


# ===========================================================================
# Component balance hybrid_methods (Python side)
# ===========================================================================


def test_principal_balance_at_matches_loan(session):
    loan = LoanRecordFactory()
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)
    as_of = datetime(2024, 2, 15, tzinfo=timezone.utc)

    mw_loan = loaded._load_money_warp_loan()
    with Warp(mw_loan, as_of) as warped:
        expected = warped.principal_balance
    assert loaded.principal_balance_at(as_of) == expected


def test_interest_balance_at_matches_loan(session):
    loan = LoanRecordFactory()
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)
    as_of = datetime(2024, 2, 15, tzinfo=timezone.utc)

    mw_loan = loaded._load_money_warp_loan()
    with Warp(mw_loan, as_of) as warped:
        expected = warped.interest_balance
    assert loaded.interest_balance_at(as_of) == expected


def test_mora_interest_balance_at_zero_before_due_date(session):
    loan = LoanRecordFactory()
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)
    as_of = datetime(2024, 1, 15, tzinfo=timezone.utc)

    assert loaded.mora_interest_balance_at(as_of) == Money.zero()


def test_fine_balance_at_zero_without_late_payments(session):
    loan = LoanRecordFactory()
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)
    as_of = datetime(2024, 1, 15, tzinfo=timezone.utc)

    assert loaded.fine_balance_at(as_of) == Money.zero()


def test_component_balances_sum_to_balance_at(session):
    loan = LoanRecordFactory()
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)
    as_of = datetime(2024, 2, 15, tzinfo=timezone.utc)

    total = loaded.balance_at(as_of)
    components = (
        loaded.principal_balance_at(as_of)
        + loaded.interest_balance_at(as_of)
        + loaded.mora_interest_balance_at(as_of)
        + loaded.fine_balance_at(as_of)
    )
    assert total == components


def test_component_properties_delegate_to_at_methods(session):
    loan = LoanRecordFactory()
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)
    now_dt = datetime.now(tz=timezone.utc)

    assert loaded.principal_balance == loaded.principal_balance_at(now_dt)
    assert loaded.interest_balance == loaded.interest_balance_at(now_dt)
    assert loaded.mora_interest_balance == loaded.mora_interest_balance_at(now_dt)
    assert loaded.fine_balance == loaded.fine_balance_at(now_dt)


# ===========================================================================
# Component balance hybrid_methods (SQL side)
# ===========================================================================


def test_principal_balance_at_sql_filter(session):
    LoanRecordFactory(principal=Money("10000"))
    LoanRecordFactory(principal=Money("500"))

    results = (
        session.execute(
            select(LoanRecord).where(LoanRecord.principal_balance_at(datetime(2024, 1, 15)) > Decimal("5000"))
        )
        .scalars()
        .all()
    )
    assert len(results) == 1


def test_principal_balance_at_sql_with_settlement(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        amount=Money("7500"),
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("3000"),
    )

    results = (
        session.execute(
            select(LoanRecord).where(LoanRecord.principal_balance_at(datetime(2024, 2, 15)) < Decimal("5000"))
        )
        .scalars()
        .all()
    )
    assert len(results) == 1


def test_interest_balance_at_sql_positive_before_due(session):
    LoanRecordFactory()

    results = (
        session.execute(select(LoanRecord).where(LoanRecord.interest_balance_at(datetime(2024, 1, 15)) > Decimal("0")))
        .scalars()
        .all()
    )
    assert len(results) == 1


def test_fine_balance_at_sql_zero_without_late(session):
    LoanRecordFactory()

    results = (
        session.execute(select(LoanRecord).where(LoanRecord.fine_balance_at(datetime(2024, 1, 15)) <= Decimal("0")))
        .scalars()
        .all()
    )
    assert len(results) == 1


def test_principal_balance_sql_order_by(session):
    loan1 = LoanRecordFactory(principal=Money("5000"))
    loan2 = LoanRecordFactory(principal=Money("20000"))

    results = session.execute(select(LoanRecord).order_by(LoanRecord.principal_balance.desc())).scalars().all()
    assert results[0].id == loan2.id
    assert results[1].id == loan1.id


# ===========================================================================
# Error when settlement_bridge missing
# ===========================================================================


def test_loan_bridge_raises_without_settlement_bridge():
    class UnmarkedSettlement(Base):
        __tablename__ = "unmarked_settlements"
        id = Column(Integer, primary_key=True)
        loan_id = Column(Integer, ForeignKey("loans_bad.id"))
        remaining_balance = Column(MoneyType())
        payment_date = Column(DateTime)

    @loan_bridge()
    class BadLoan(Base):
        __tablename__ = "loans_bad"
        id = Column(Integer, primary_key=True)
        principal = Column(MoneyType())
        settlements = relationship("UnmarkedSettlement")

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(BadLoan(id=1, principal=Money("1000")))
        s.flush()

        with pytest.raises(TypeError, match="@settlement_bridge"):
            s.execute(select(BadLoan).where(BadLoan.balance > Decimal("0"))).scalars().all()
