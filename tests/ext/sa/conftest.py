# ruff: noqa: A003
"""Shared models, fixtures, and factories for SQLAlchemy extension tests."""

from datetime import date, datetime, timezone

import factory
import factory.alchemy
import pytest
from pytest_postgresql import factories as pg_factories
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.types import JSON
from sqlalchemy.orm import DeclarativeBase, Session, relationship

from money_warp import Loan, MoraStrategy
from money_warp.ext.sa import (
    DueDatesType,
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


class MoneyCustomPrecisionModel(Base):
    __tablename__ = "money_custom_precision"
    id = Column(Integer, primary_key=True)
    amount = Column(MoneyType(representation="raw", precision=10, scale=2))


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


class DueDatesModel(Base):
    __tablename__ = "due_dates"
    id = Column(Integer, primary_key=True)
    dates = Column(DueDatesType())


@settlement_bridge()
class SettlementRecord(Base):
    __tablename__ = "settlements"
    id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("loans.id"))
    amount = Column(MoneyType())
    payment_date = Column(DateTime)
    remaining_balance = Column(MoneyType())
    interest_date = Column(DateTime, nullable=True)
    processing_date = Column(DateTime, nullable=True)
    intention = Column(JSON, nullable=False, default={"method": "record_payment"})


@loan_bridge()
class LoanRecord(Base):
    __tablename__ = "loans"
    id = Column(Integer, primary_key=True)
    principal = Column(MoneyType())
    interest_rate = Column(InterestRateType(representation="json"), nullable=True)
    disbursement_date = Column(DateTime, nullable=True)
    due_dates = Column(DueDatesType(), nullable=True)
    fine_rate = Column(InterestRateType(representation="json"), nullable=True)
    grace_period_days = Column(Integer(), nullable=True)
    mora_interest_rate = Column(InterestRateType(representation="json"), nullable=True)
    mora_strategy = Column(String(), nullable=True)
    settlements = relationship("SettlementRecord", order_by="SettlementRecord.payment_date")


@settlement_bridge()
class StringSettlementRecord(Base):
    __tablename__ = "string_settlements"
    id = Column(Integer, primary_key=True)
    loan_id = Column(Integer, ForeignKey("string_loans.id"))
    amount = Column(MoneyType())
    payment_date = Column(DateTime)
    remaining_balance = Column(MoneyType())
    interest_date = Column(DateTime, nullable=True)
    processing_date = Column(DateTime, nullable=True)
    intention = Column(JSON, nullable=False, default={"method": "record_payment"})


@loan_bridge()
class StringLoanRecord(Base):
    __tablename__ = "string_loans"
    id = Column(Integer, primary_key=True)
    principal = Column(MoneyType())
    interest_rate = Column(InterestRateType(representation="string"), nullable=True)
    disbursement_date = Column(DateTime, nullable=True)
    due_dates = Column(DueDatesType(), nullable=True)
    fine_rate = Column(InterestRateType(representation="string"), nullable=True)
    grace_period_days = Column(Integer(), nullable=True)
    mora_interest_rate = Column(InterestRateType(representation="string"), nullable=True)
    mora_strategy = Column(String(), nullable=True)
    settlements = relationship(
        "StringSettlementRecord",
        order_by="StringSettlementRecord.payment_date",
    )


# ---------------------------------------------------------------------------
# PostgreSQL fixtures (pytest-postgresql starts its own PG process)
# ---------------------------------------------------------------------------

postgresql_proc = pg_factories.postgresql_proc()
postgresql_conn = pg_factories.postgresql("postgresql_proc")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(params=[pytest.param("sqlite", id="sqlite"), pytest.param("postgresql", id="postgresql")])
def engine(request):
    if request.param == "sqlite":
        eng = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(eng)
        yield eng
        return

    pg = request.getfixturevalue("postgresql_conn")
    info = pg.info
    dsn = f"postgresql+psycopg://{info.user}@{info.host}:{info.port}/{info.dbname}"
    eng = create_engine(dsn)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        LoanRecordFactory._meta.sqlalchemy_session = s
        SettlementRecordFactory._meta.sqlalchemy_session = s
        StringLoanRecordFactory._meta.sqlalchemy_session = s
        StringSettlementRecordFactory._meta.sqlalchemy_session = s
        yield s


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------


_LATE_PAYMENT_DUE_DATES = [
    date(2025, 2, 1),
    date(2025, 3, 1),
    date(2025, 4, 1),
]


def _build_late_payment_settlements(obj, create, extracted, **kwargs):
    """PostGeneration hook: build money_warp Loan, record payments, persist."""
    if not create:
        return

    due_dates_dt = [datetime(d.year, d.month, d.day, tzinfo=timezone.utc) for d in obj.due_dates]

    loan = Loan(
        obj.principal,
        obj.interest_rate,
        due_dates_dt,
        disbursement_date=obj.disbursement_date,
        fine_rate=obj.fine_rate,
        grace_period_days=obj.grace_period_days,
        mora_interest_rate=obj.mora_interest_rate,
        mora_strategy=MoraStrategy[obj.mora_strategy],
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

    settlements = [s1, s2, s3]
    interest_dates = [None, datetime(2025, 3, 15, tzinfo=timezone.utc), None]
    for s, idate in zip(settlements, interest_dates):
        SettlementRecordFactory(
            loan_id=obj.id,
            amount=s.payment_amount,
            payment_date=s.payment_date,
            remaining_balance=s.remaining_balance,
            interest_date=idate,
        )

    obj._mw_loan = loan
    obj._mw_settlements = settlements


class LoanRecordFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = LoanRecord
        sqlalchemy_session_persistence = "flush"

    principal = factory.LazyFunction(lambda: Money("10000"))
    interest_rate = factory.LazyFunction(lambda: InterestRate("10% a"))
    disbursement_date = factory.LazyFunction(lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))
    due_dates = factory.LazyFunction(lambda: [date(2024, 2, 1), date(2024, 3, 1)])
    fine_rate = None
    grace_period_days = None
    mora_interest_rate = None
    mora_strategy = None

    class Params:
        with_late_payment = factory.Trait(
            principal=factory.LazyFunction(lambda: Money("10000")),
            interest_rate=factory.LazyFunction(lambda: InterestRate("6% a")),
            disbursement_date=factory.LazyFunction(lambda: datetime(2025, 1, 1, tzinfo=timezone.utc)),
            due_dates=factory.LazyFunction(lambda: list(_LATE_PAYMENT_DUE_DATES)),
            fine_rate=factory.LazyFunction(lambda: InterestRate("2% annual")),
            grace_period_days=0,
            mora_interest_rate=factory.LazyFunction(lambda: InterestRate("12% a")),
            mora_strategy="COMPOUND",
            settle=factory.PostGeneration(_build_late_payment_settlements),
        )


class SettlementRecordFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = SettlementRecord
        sqlalchemy_session_persistence = "flush"

    amount = factory.LazyFunction(lambda: Money("3000"))
    payment_date = factory.LazyFunction(lambda: datetime(2024, 2, 1, tzinfo=timezone.utc))
    remaining_balance = factory.LazyFunction(lambda: Money("7000"))
    interest_date = None
    processing_date = None
    intention = factory.LazyFunction(lambda: {"method": "record_payment"})


class StringLoanRecordFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = StringLoanRecord
        sqlalchemy_session_persistence = "flush"

    principal = factory.LazyFunction(lambda: Money("10000"))
    interest_rate = factory.LazyFunction(lambda: InterestRate("10% a"))
    disbursement_date = factory.LazyFunction(lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))
    due_dates = factory.LazyFunction(lambda: [date(2024, 2, 1), date(2024, 3, 1)])
    fine_rate = None
    grace_period_days = None
    mora_interest_rate = None
    mora_strategy = None


class StringSettlementRecordFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = StringSettlementRecord
        sqlalchemy_session_persistence = "flush"

    amount = factory.LazyFunction(lambda: Money("3000"))
    payment_date = factory.LazyFunction(lambda: datetime(2024, 2, 1, tzinfo=timezone.utc))
    remaining_balance = factory.LazyFunction(lambda: Money("7000"))
    interest_date = None
    processing_date = None
    intention = factory.LazyFunction(lambda: {"method": "record_payment"})
