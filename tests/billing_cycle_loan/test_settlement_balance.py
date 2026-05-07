"""Tests for BillingCycleLoan.settlement_balance with explicit expected values."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from money_warp import (
    BillingCycleLoan,
    BrazilianWorkingDayCalendar,
    InterestRate,
    Money,
    MonthlyBillingCycle,
    PriceScheduler,
    Warp,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _single_bcl() -> BillingCycleLoan:
    return BillingCycleLoan(
        principal=Money("946.62"),
        interest_rate=InterestRate("4.99% a.m."),
        billing_cycle=MonthlyBillingCycle(due_dates=[date(2025, 11, 20)]),
        start_date=datetime(2025, 10, 21, tzinfo=SAO_PAULO),
        num_installments=1,
        disbursement_date=datetime(2025, 10, 21, tzinfo=SAO_PAULO),
        scheduler=PriceScheduler,
        mora_interest_rate=InterestRate("4.99% a.m."),
        fine_rate=InterestRate("2% a.m."),
        tz=SAO_PAULO,
        working_day_calendar=BrazilianWorkingDayCalendar(),
    )


def _multi_bcl() -> BillingCycleLoan:
    return BillingCycleLoan(
        principal=Money("10000"),
        interest_rate=InterestRate("5% a.m."),
        billing_cycle=MonthlyBillingCycle(
            due_dates=[date(2025, 12, 20), date(2026, 1, 20), date(2026, 2, 20)]
        ),
        start_date=datetime(2025, 11, 20, tzinfo=SAO_PAULO),
        num_installments=3,
        disbursement_date=datetime(2025, 11, 20, tzinfo=SAO_PAULO),
        scheduler=PriceScheduler,
        tz=SAO_PAULO,
    )


# ------------------------------------------------------------------
# Single installment
# ------------------------------------------------------------------


def test_bcl_single_early_equals_scheduled_pmt():
    """Early: settlement_balance equals scheduled PMT."""
    loan = _single_bcl()
    sched = loan.get_original_schedule()
    with Warp(loan, datetime(2025, 11, 10, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == sched.entries[0].payment_amount
        assert w.settlement_balance == Money("993.19")


def test_bcl_single_early_greater_than_current():
    """Early: settlement_balance > current_balance."""
    loan = _single_bcl()
    with Warp(loan, datetime(2025, 11, 10, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == Money("993.19")
        assert w.current_balance == Money("977.42")
        assert w.settlement_balance > w.current_balance


def test_bcl_single_late_equals_current():
    """Late: settlement_balance == current_balance."""
    loan = _single_bcl()
    with Warp(loan, datetime(2025, 11, 24, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == Money("1019.44")
        assert w.settlement_balance == w.current_balance


def test_bcl_single_components_sum():
    """settlement_balance = interest_to_due + scheduled_principal (early, no fines)."""
    loan = _single_bcl()
    sched = loan.get_original_schedule()
    with Warp(loan, datetime(2025, 11, 10, tzinfo=SAO_PAULO)) as w:
        expected_principal = sched.entries[0].principal_payment
        interest_component = Money(
            w.settlement_balance.raw_amount - expected_principal.raw_amount
        )
        assert interest_component == sched.entries[0].interest_payment


# ------------------------------------------------------------------
# Multi installment
# ------------------------------------------------------------------


def test_bcl_multi_early_equals_first_pmt():
    """Early: settlement_balance equals installment 1 PMT."""
    loan = _multi_bcl()
    sched = loan.get_original_schedule()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == sched.entries[0].payment_amount


def test_bcl_multi_early_less_than_current():
    """Early: settlement_balance < current_balance."""
    loan = _multi_bcl()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance < w.current_balance
