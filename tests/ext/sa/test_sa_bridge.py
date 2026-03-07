# ruff: noqa: A003
"""Tests for settlement_bridge, loan_bridge, balance, and balance_at."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, create_engine, select
from sqlalchemy.orm import Session, relationship

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
    }


def test_settlement_bridge_custom_names():
    @settlement_bridge(balance="bal", date="settled_at", amount="paid")
    class Custom(Base):
        __tablename__ = "custom_settlements"
        id = Column(Integer, primary_key=True)

    assert Custom._money_warp_bridge_meta == {
        "balance": "bal",
        "date": "settled_at",
        "amount": "paid",
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
# balance hybrid_property (Python side)
# ===========================================================================


def test_balance_no_settlements_returns_principal(session):
    loan = LoanRecordFactory()
    session.expire_all()
    loaded = session.get(LoanRecord, loan.id)
    assert loaded.balance == Money("10000")


def test_balance_with_settlements_returns_last_remaining(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("7500"),
    )
    SettlementRecordFactory(
        loan_id=loan.id,
        payment_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
        remaining_balance=Money("3800"),
    )
    session.expire_all()

    loaded = session.get(LoanRecord, loan.id)
    assert loaded.balance == Money("3800")


# ===========================================================================
# balance_at hybrid_method (Python side)
# ===========================================================================


def test_balance_at_before_any_settlement_returns_principal(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
    )
    session.expire_all()

    loaded = session.get(LoanRecord, loan.id)
    assert loaded.balance_at(datetime(2024, 1, 15, tzinfo=timezone.utc)) == Money("10000")


def test_balance_at_after_first_settlement(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("7500"),
    )
    SettlementRecordFactory(
        loan_id=loan.id,
        payment_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
        remaining_balance=Money("3800"),
    )
    session.expire_all()

    loaded = session.get(LoanRecord, loan.id)
    assert loaded.balance_at(datetime(2024, 2, 15, tzinfo=timezone.utc)) == Money("7500")


def test_balance_at_after_all_settlements(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("7500"),
    )
    SettlementRecordFactory(
        loan_id=loan.id,
        payment_date=datetime(2024, 3, 1, tzinfo=timezone.utc),
        remaining_balance=Money("3800"),
    )
    session.expire_all()

    loaded = session.get(LoanRecord, loan.id)
    assert loaded.balance_at(datetime(2025, 1, 1, tzinfo=timezone.utc)) == Money("3800")


def test_balance_at_exact_settlement_date(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("7500"),
    )
    session.expire_all()

    loaded = session.get(LoanRecord, loan.id)
    assert loaded.balance_at(datetime(2024, 2, 1, tzinfo=timezone.utc)) == Money("7500")


def test_balance_at_no_settlements_returns_principal(session):
    loan = LoanRecordFactory()
    session.expire_all()

    loaded = session.get(LoanRecord, loan.id)
    assert loaded.balance_at(datetime(2025, 1, 1, tzinfo=timezone.utc)) == Money("10000")


# ===========================================================================
# balance_at hybrid_method (SQL side)
# ===========================================================================


def test_balance_at_sql_filter(session):
    loan = LoanRecordFactory()
    SettlementRecordFactory(
        loan_id=loan.id,
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("7500"),
    )
    SettlementRecordFactory(
        loan_id=loan.id,
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
        payment_date=datetime(2024, 2, 1, tzinfo=timezone.utc),
        remaining_balance=Money("0"),
    )

    results = session.execute(select(LoanRecord).where(LoanRecord.balance <= Decimal("0"))).scalars().all()
    assert len(results) == 1


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

    @loan_bridge(principal="principal", settlements="settlements")
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
