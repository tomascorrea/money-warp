# ruff: noqa: A003
"""Tests for SQLAlchemy extension types and bridge decorators."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Session, relationship

from money_warp import Loan, MoraStrategy
from money_warp.ext.sa import (
    InterestRateType,
    MoneyType,
    RateType,
    loan_bridge,
    settlement_bridge,
)
from money_warp.interest_rate import InterestRate
from money_warp.money import Money
from money_warp.rate import CompoundingFrequency, Rate, YearSize

# ---------------------------------------------------------------------------
# Test models
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


# ===========================================================================
# MoneyType — construction
# ===========================================================================


def test_money_type_invalid_representation_raises():
    with pytest.raises(ValueError, match="Invalid representation"):
        MoneyType(representation="unknown")


@pytest.mark.parametrize("representation", ["raw", "real", "cents"])
def test_money_type_valid_representation_accepted(representation):
    col_type = MoneyType(representation=representation)
    assert col_type.representation == representation


# ===========================================================================
# MoneyType — round-trip raw
# ===========================================================================


@pytest.mark.parametrize(
    "amount_str,expected_raw",
    [
        ("100.50", Decimal("100.50")),
        ("0", Decimal("0")),
        ("12345.6789", Decimal("12345.6789")),
        ("-50.25", Decimal("-50.25")),
    ],
)
def test_money_type_roundtrip_raw(session, amount_str, expected_raw):
    original = Money(amount_str)
    session.add(MoneyRawModel(id=1, amount=original))
    session.flush()
    session.expire_all()
    loaded = session.get(MoneyRawModel, 1)
    assert loaded.amount.raw_amount == expected_raw


# ===========================================================================
# MoneyType — round-trip real
# ===========================================================================


@pytest.mark.parametrize(
    "amount_str,expected_real",
    [
        ("100.50", Decimal("100.50")),
        ("100.125", Decimal("100.13")),
        ("0.001", Decimal("0.00")),
    ],
)
def test_money_type_roundtrip_real(session, amount_str, expected_real):
    original = Money(amount_str)
    session.add(MoneyRealModel(id=1, amount=original))
    session.flush()
    session.expire_all()
    loaded = session.get(MoneyRealModel, 1)
    assert loaded.amount.real_amount == expected_real


# ===========================================================================
# MoneyType — round-trip cents
# ===========================================================================


@pytest.mark.parametrize(
    "amount_str,expected_real",
    [
        ("100.50", Decimal("100.50")),
        ("0.01", Decimal("0.01")),
        ("0", Decimal("0.00")),
    ],
)
def test_money_type_roundtrip_cents(session, amount_str, expected_real):
    original = Money(amount_str)
    session.add(MoneyCentsModel(id=1, amount=original))
    session.flush()
    session.expire_all()
    loaded = session.get(MoneyCentsModel, 1)
    assert loaded.amount.real_amount == expected_real


# ===========================================================================
# MoneyType — None handling
# ===========================================================================


def test_money_type_none_raw(session):
    session.add(MoneyRawModel(id=1, amount=None))
    session.flush()
    session.expire_all()
    loaded = session.get(MoneyRawModel, 1)
    assert loaded.amount is None


def test_money_type_none_cents(session):
    session.add(MoneyCentsModel(id=1, amount=None))
    session.flush()
    session.expire_all()
    loaded = session.get(MoneyCentsModel, 1)
    assert loaded.amount is None


# ===========================================================================
# RateType — construction
# ===========================================================================


def test_rate_type_invalid_representation_raises():
    with pytest.raises(ValueError, match="Invalid representation"):
        RateType(representation="unknown")


@pytest.mark.parametrize("representation", ["string", "json"])
def test_rate_type_valid_representation_accepted(representation):
    col_type = RateType(representation=representation)
    assert col_type.representation == representation


# ===========================================================================
# RateType — round-trip string
# ===========================================================================


def test_rate_type_roundtrip_string_annually(session):
    original = Rate("5.25% a")
    session.add(RateStringModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateStringModel, 1)
    assert loaded.rate == original


def test_rate_type_roundtrip_string_monthly(session):
    original = Rate("1.5% m")
    session.add(RateStringModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateStringModel, 1)
    assert loaded.rate.period == CompoundingFrequency.MONTHLY


def test_rate_type_roundtrip_string_negative(session):
    original = Rate("-2.5% a")
    session.add(RateStringModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateStringModel, 1)
    assert loaded.rate == original


# ===========================================================================
# RateType — round-trip json
# ===========================================================================


def test_rate_type_roundtrip_json_basic(session):
    original = Rate(Decimal("0.0525"), CompoundingFrequency.ANNUALLY)
    session.add(RateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateJsonModel, 1)
    assert loaded.rate == original


def test_rate_type_roundtrip_json_with_all_params(session):
    original = Rate(
        Decimal("0.015"),
        CompoundingFrequency.MONTHLY,
        precision=6,
        year_size=YearSize.banker,
        str_style="abbrev",
    )
    session.add(RateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateJsonModel, 1)
    assert loaded.rate == original


def test_rate_type_roundtrip_json_negative(session):
    original = Rate(Decimal("-0.025"), CompoundingFrequency.ANNUALLY)
    session.add(RateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(RateJsonModel, 1)
    assert loaded.rate == original


# ===========================================================================
# RateType — None handling
# ===========================================================================


def test_rate_type_none_string(session):
    session.add(RateStringModel(id=1, rate=None))
    session.flush()
    session.expire_all()
    loaded = session.get(RateStringModel, 1)
    assert loaded.rate is None


def test_rate_type_none_json(session):
    session.add(RateJsonModel(id=1, rate=None))
    session.flush()
    session.expire_all()
    loaded = session.get(RateJsonModel, 1)
    assert loaded.rate is None


# ===========================================================================
# InterestRateType — round-trips
# ===========================================================================


def test_interest_rate_type_roundtrip_string(session):
    original = InterestRate("5.25% a")
    session.add(InterestRateStringModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(InterestRateStringModel, 1)
    assert isinstance(loaded.rate, InterestRate)
    assert loaded.rate == original


def test_interest_rate_type_roundtrip_json(session):
    original = InterestRate(Decimal("0.0525"), CompoundingFrequency.ANNUALLY)
    session.add(InterestRateJsonModel(id=1, rate=original))
    session.flush()
    session.expire_all()
    loaded = session.get(InterestRateJsonModel, 1)
    assert isinstance(loaded.rate, InterestRate)
    assert loaded.rate == original


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
    }


# ===========================================================================
# loan_bridge — balance hybrid_property (Python side)
# ===========================================================================


def test_loan_balance_no_settlements_returns_principal(session):
    loan = LoanRecord(
        id=1,
        principal=Money("10000"),
        interest_rate=InterestRate("10% a"),
        disbursement_date=datetime(2024, 1, 1),
        due_dates=["2024-02-01", "2024-03-01"],
    )
    session.add(loan)
    session.flush()
    session.expire_all()
    loaded = session.get(LoanRecord, 1)
    assert loaded.balance == Money("10000")


def test_loan_balance_with_settlements_returns_last_remaining(session):
    loan = LoanRecord(
        id=1,
        principal=Money("10000"),
        interest_rate=InterestRate("10% a"),
        disbursement_date=datetime(2024, 1, 1),
        due_dates=["2024-02-01", "2024-03-01"],
    )
    session.add(loan)
    session.flush()

    s1 = SettlementRecord(
        loan_id=1,
        amount=Money("3000"),
        payment_date=datetime(2024, 2, 1),
        remaining_balance=Money("7500"),
    )
    s2 = SettlementRecord(
        loan_id=1,
        amount=Money("4000"),
        payment_date=datetime(2024, 3, 1),
        remaining_balance=Money("3800"),
    )
    session.add_all([s1, s2])
    session.flush()
    session.expire_all()

    loaded = session.get(LoanRecord, 1)
    assert loaded.balance == Money("3800")


# ===========================================================================
# loan_bridge — balance_at hybrid_method (Python side)
# ===========================================================================


def test_loan_balance_at_before_any_settlement_returns_principal(session):
    loan = LoanRecord(
        id=1,
        principal=Money("10000"),
        interest_rate=InterestRate("10% a"),
        disbursement_date=datetime(2024, 1, 1),
        due_dates=["2024-02-01", "2024-03-01"],
    )
    session.add(loan)
    session.add(
        SettlementRecord(
            loan_id=1,
            amount=Money("3000"),
            payment_date=datetime(2024, 2, 1),
            remaining_balance=Money("7500"),
        )
    )
    session.flush()
    session.expire_all()

    loaded = session.get(LoanRecord, 1)
    assert loaded.balance_at(datetime(2024, 1, 15)) == Money("10000")


def test_loan_balance_at_after_first_settlement(session):
    loan = LoanRecord(
        id=1,
        principal=Money("10000"),
        interest_rate=InterestRate("10% a"),
        disbursement_date=datetime(2024, 1, 1),
        due_dates=["2024-02-01", "2024-03-01"],
    )
    session.add(loan)
    session.add_all(
        [
            SettlementRecord(
                loan_id=1,
                amount=Money("3000"),
                payment_date=datetime(2024, 2, 1),
                remaining_balance=Money("7500"),
            ),
            SettlementRecord(
                loan_id=1,
                amount=Money("4000"),
                payment_date=datetime(2024, 3, 1),
                remaining_balance=Money("3800"),
            ),
        ]
    )
    session.flush()
    session.expire_all()

    loaded = session.get(LoanRecord, 1)
    assert loaded.balance_at(datetime(2024, 2, 15)) == Money("7500")


def test_loan_balance_at_after_all_settlements(session):
    loan = LoanRecord(
        id=1,
        principal=Money("10000"),
        interest_rate=InterestRate("10% a"),
        disbursement_date=datetime(2024, 1, 1),
        due_dates=["2024-02-01", "2024-03-01"],
    )
    session.add(loan)
    session.add_all(
        [
            SettlementRecord(
                loan_id=1,
                amount=Money("3000"),
                payment_date=datetime(2024, 2, 1),
                remaining_balance=Money("7500"),
            ),
            SettlementRecord(
                loan_id=1,
                amount=Money("4000"),
                payment_date=datetime(2024, 3, 1),
                remaining_balance=Money("3800"),
            ),
        ]
    )
    session.flush()
    session.expire_all()

    loaded = session.get(LoanRecord, 1)
    assert loaded.balance_at(datetime(2025, 1, 1)) == Money("3800")


def test_loan_balance_at_exact_settlement_date(session):
    loan = LoanRecord(
        id=1,
        principal=Money("10000"),
        interest_rate=InterestRate("10% a"),
        disbursement_date=datetime(2024, 1, 1),
        due_dates=["2024-02-01"],
    )
    session.add(loan)
    session.add(
        SettlementRecord(
            loan_id=1,
            amount=Money("3000"),
            payment_date=datetime(2024, 2, 1),
            remaining_balance=Money("7500"),
        )
    )
    session.flush()
    session.expire_all()

    loaded = session.get(LoanRecord, 1)
    assert loaded.balance_at(datetime(2024, 2, 1)) == Money("7500")


def test_loan_balance_at_no_settlements_returns_principal(session):
    loan = LoanRecord(
        id=1,
        principal=Money("10000"),
        interest_rate=InterestRate("10% a"),
        disbursement_date=datetime(2024, 1, 1),
        due_dates=["2024-02-01"],
    )
    session.add(loan)
    session.flush()
    session.expire_all()

    loaded = session.get(LoanRecord, 1)
    assert loaded.balance_at(datetime(2025, 1, 1)) == Money("10000")


# ===========================================================================
# loan_bridge — balance_at hybrid_method (SQL side)
# ===========================================================================


def test_loan_balance_at_sql_filter(session):
    session.add(
        LoanRecord(
            id=1,
            principal=Money("10000"),
            interest_rate=InterestRate("10% a"),
            disbursement_date=datetime(2024, 1, 1),
            due_dates=["2024-02-01"],
        )
    )
    session.add_all(
        [
            SettlementRecord(
                loan_id=1,
                amount=Money("3000"),
                payment_date=datetime(2024, 2, 1),
                remaining_balance=Money("7500"),
            ),
            SettlementRecord(
                loan_id=1,
                amount=Money("9000"),
                payment_date=datetime(2024, 3, 1),
                remaining_balance=Money("500"),
            ),
        ]
    )
    session.flush()

    results = (
        session.execute(select(LoanRecord).where(LoanRecord.balance_at(datetime(2024, 2, 15)) > Decimal("5000")))
        .scalars()
        .all()
    )
    assert len(results) == 1
    assert results[0].id == 1


def test_loan_balance_at_sql_before_settlements(session):
    session.add(
        LoanRecord(
            id=1,
            principal=Money("10000"),
            interest_rate=InterestRate("10% a"),
            disbursement_date=datetime(2024, 1, 1),
            due_dates=["2024-02-01"],
        )
    )
    session.add(
        SettlementRecord(
            loan_id=1,
            amount=Money("3000"),
            payment_date=datetime(2024, 2, 1),
            remaining_balance=Money("7500"),
        )
    )
    session.flush()

    results = (
        session.execute(select(LoanRecord).where(LoanRecord.balance_at(datetime(2024, 1, 15)) > Decimal("9000")))
        .scalars()
        .all()
    )
    assert len(results) == 1
    assert results[0].id == 1


def test_loan_balance_at_sql_order_by(session):
    session.add(
        LoanRecord(
            id=1,
            principal=Money("10000"),
            interest_rate=InterestRate("10% a"),
            disbursement_date=datetime(2024, 1, 1),
            due_dates=["2024-02-01"],
        )
    )
    session.add(
        LoanRecord(
            id=2,
            principal=Money("5000"),
            interest_rate=InterestRate("10% a"),
            disbursement_date=datetime(2024, 1, 1),
            due_dates=["2024-02-01"],
        )
    )
    session.add(
        SettlementRecord(
            loan_id=1,
            amount=Money("8000"),
            payment_date=datetime(2024, 2, 1),
            remaining_balance=Money("3000"),
        )
    )
    session.flush()

    results = (
        session.execute(select(LoanRecord).order_by(LoanRecord.balance_at(datetime(2024, 2, 15)).desc()))
        .scalars()
        .all()
    )
    assert results[0].id == 2
    assert results[1].id == 1


# ===========================================================================
# loan_bridge — balance hybrid_property (SQL side)
# ===========================================================================


def test_loan_balance_filter_gt(session):
    session.add(
        LoanRecord(
            id=1,
            principal=Money("10000"),
            interest_rate=InterestRate("10% a"),
            disbursement_date=datetime(2024, 1, 1),
            due_dates=["2024-02-01"],
        )
    )
    session.add(
        LoanRecord(
            id=2,
            principal=Money("500"),
            interest_rate=InterestRate("10% a"),
            disbursement_date=datetime(2024, 1, 1),
            due_dates=["2024-02-01"],
        )
    )
    session.flush()

    results = session.execute(select(LoanRecord).where(LoanRecord.balance > Decimal("1000"))).scalars().all()
    assert len(results) == 1
    assert results[0].id == 1


def test_loan_balance_filter_with_settlements(session):
    session.add(
        LoanRecord(
            id=1,
            principal=Money("10000"),
            interest_rate=InterestRate("10% a"),
            disbursement_date=datetime(2024, 1, 1),
            due_dates=["2024-02-01"],
        )
    )
    session.add(
        SettlementRecord(
            loan_id=1,
            amount=Money("9500"),
            payment_date=datetime(2024, 2, 1),
            remaining_balance=Money("800"),
        )
    )
    session.flush()

    results = session.execute(select(LoanRecord).where(LoanRecord.balance < Decimal("1000"))).scalars().all()
    assert len(results) == 1
    assert results[0].id == 1


def test_loan_balance_order_by(session):
    session.add(
        LoanRecord(
            id=1,
            principal=Money("5000"),
            interest_rate=InterestRate("10% a"),
            disbursement_date=datetime(2024, 1, 1),
            due_dates=["2024-02-01"],
        )
    )
    session.add(
        LoanRecord(
            id=2,
            principal=Money("20000"),
            interest_rate=InterestRate("10% a"),
            disbursement_date=datetime(2024, 1, 1),
            due_dates=["2024-02-01"],
        )
    )
    session.add(
        LoanRecord(
            id=3,
            principal=Money("1000"),
            interest_rate=InterestRate("10% a"),
            disbursement_date=datetime(2024, 1, 1),
            due_dates=["2024-02-01"],
        )
    )
    session.flush()

    results = session.execute(select(LoanRecord).order_by(LoanRecord.balance.desc())).scalars().all()
    assert [r.id for r in results] == [2, 1, 3]


def test_loan_balance_filter_paid_off(session):
    session.add(
        LoanRecord(
            id=1,
            principal=Money("10000"),
            interest_rate=InterestRate("10% a"),
            disbursement_date=datetime(2024, 1, 1),
            due_dates=["2024-02-01"],
        )
    )
    session.add(
        SettlementRecord(
            loan_id=1,
            amount=Money("10500"),
            payment_date=datetime(2024, 2, 1),
            remaining_balance=Money("0"),
        )
    )
    session.flush()

    results = session.execute(select(LoanRecord).where(LoanRecord.balance <= Decimal("0"))).scalars().all()
    assert len(results) == 1
    assert results[0].id == 1


# ===========================================================================
# loan_bridge — error when settlement_bridge missing
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


# ===========================================================================
# Integration: money_warp Loan → SQLAlchemy round-trip with balance_at
# ===========================================================================

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
    sa_loan = LoanRecord(
        id=1,
        principal=loan.principal,
        interest_rate=loan.interest_rate,
        disbursement_date=loan.disbursement_date,
        due_dates=[d.isoformat() for d in loan.due_dates],
    )
    session.add(sa_loan)
    session.flush()

    for i, s in enumerate(settlements, start=1):
        session.add(
            SettlementRecord(
                id=i,
                loan_id=1,
                amount=s.payment_amount,
                payment_date=s.payment_date,
                remaining_balance=s.remaining_balance,
            )
        )
    session.flush()
    session.expire_all()


@pytest.fixture()
def loan_with_payments():
    return _build_loan_with_payments()


@pytest.fixture()
def integration_session(engine, loan_with_payments):
    loan, settlements = loan_with_payments
    with Session(engine) as s:
        _persist_loan(s, loan, settlements)
        yield s, loan, settlements


def test_integration_late_payment_has_fine_and_mora(loan_with_payments):
    _, settlements = loan_with_payments
    assert settlements[1].fine_paid.is_positive()
    assert settlements[1].mora_paid.is_positive()


def test_integration_on_time_payment_has_no_fine(loan_with_payments):
    _, settlements = loan_with_payments
    assert settlements[0].fine_paid.is_zero()
    assert settlements[0].mora_paid.is_zero()


def test_integration_late_payment_remaining_balance_higher_than_on_time():
    """When paying late, fines and mora eat into the payment so less
    principal is retired. Compare against an identical loan paid on time."""
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
def test_integration_balance_at_matches_settlement(integration_session, as_of, expected_idx):
    session, loan, settlements = integration_session
    loaded = session.get(LoanRecord, 1)

    expected = loan.principal if expected_idx is None else settlements[expected_idx].remaining_balance
    assert loaded.balance_at(as_of) == expected


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
def test_integration_balance_at_sql_matches_settlement(integration_session, as_of, expected_idx):
    session, loan, settlements = integration_session

    expected = loan.principal if expected_idx is None else settlements[expected_idx].remaining_balance

    results = (
        session.execute(select(LoanRecord).where(LoanRecord.balance_at(as_of) == expected.raw_amount)).scalars().all()
    )
    assert len(results) == 1
    assert results[0].id == 1
