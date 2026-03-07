# ruff: noqa: A003
"""Shared models, fixtures, and factories for SQLAlchemy extension tests."""

from datetime import datetime, timezone

import factory
import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, relationship

from money_warp.ext.sa import (
    InterestRateType,
    MoneyType,
    RateType,
    loan_bridge,
    settlement_bridge,
)
from money_warp.interest_rate import InterestRate
from money_warp.money import Money

# ---------------------------------------------------------------------------
# Base & models
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class MoneyRawModel(Base):
    __tablename__ = "money_raw"
    id = Column(Integer, primary_key=True)
    amount = Column(MoneyType(representation="raw"))


class MoneyRealModel(Base):
    __tablename__ = "money_real"
    id = Column(Integer, primary_key=True)
    amount = Column(MoneyType(representation="real"))


class MoneyCentsModel(Base):
    __tablename__ = "money_cents"
    id = Column(Integer, primary_key=True)
    amount = Column(MoneyType(representation="cents"))


class RateStringModel(Base):
    __tablename__ = "rate_string"
    id = Column(Integer, primary_key=True)
    rate = Column(RateType(representation="string"))


class RateJsonModel(Base):
    __tablename__ = "rate_json"
    id = Column(Integer, primary_key=True)
    rate = Column(RateType(representation="json"))


class InterestRateStringModel(Base):
    __tablename__ = "interest_rate_string"
    id = Column(Integer, primary_key=True)
    rate = Column(InterestRateType(representation="string"))


class InterestRateJsonModel(Base):
    __tablename__ = "interest_rate_json"
    id = Column(Integer, primary_key=True)
    rate = Column(InterestRateType(representation="json"))


@settlement_bridge()
class SettlementRecord(Base):
    __tablename__ = "settlements"
    id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("loans.id"))
    amount = Column(MoneyType())
    payment_date = Column(DateTime)
    remaining_balance = Column(MoneyType())


@loan_bridge(principal="principal", settlements="settlements")
class LoanRecord(Base):
    __tablename__ = "loans"
    id = Column(Integer, primary_key=True)
    principal = Column(MoneyType())
    interest_rate = Column(InterestRateType(representation="json"))
    disbursement_date = Column(DateTime)
    due_dates = Column(JSON)
    settlements = relationship("SettlementRecord", order_by="SettlementRecord.payment_date")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


class LoanRecordFactory(factory.Factory):
    class Meta:
        model = LoanRecord
        exclude = ["_session"]

    _session = None
    principal = factory.LazyFunction(lambda: Money("10000"))
    interest_rate = factory.LazyFunction(lambda: InterestRate("10% a"))
    disbursement_date = factory.LazyFunction(lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))
    due_dates = factory.LazyFunction(lambda: ["2024-02-01", "2024-03-01"])


class SettlementRecordFactory(factory.Factory):
    class Meta:
        model = SettlementRecord

    amount = factory.LazyFunction(lambda: Money("3000"))
    payment_date = factory.LazyFunction(lambda: datetime(2024, 2, 1, tzinfo=timezone.utc))
    remaining_balance = factory.LazyFunction(lambda: Money("7000"))
