"""Invariant tests for settlement_balance.

settlement_balance returns the amount needed to fully cover the next
installment via pay_installment.  These invariants must hold:

1. pay_installment(settlement_balance) fully covers the next installment.
2. settlement_balance >= current_balance for single/last installment.
3. settlement_balance < current_balance for multi-installment (more than 1 remaining).
4. settlement_balance == current_balance when now >= next_unpaid_due_date.
"""

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from money_warp import (
    BillingCycleLoan,
    BrazilianWorkingDayCalendar,
    InterestRate,
    Loan,
    Money,
    MonthlyBillingCycle,
    PriceScheduler,
    Warp,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _make_loan_single() -> Loan:
    """Single-installment Loan."""
    return Loan(
        principal=Money("10000"),
        interest_rate=InterestRate("10% a.m."),
        due_dates=[date(2025, 12, 20)],
        disbursement_date=datetime(2025, 11, 20, tzinfo=timezone.utc),
        scheduler=PriceScheduler,
    )


def _make_loan_multi() -> Loan:
    """Multi-installment Loan (3 installments)."""
    return Loan(
        principal=Money("10000"),
        interest_rate=InterestRate("5% a.m."),
        due_dates=[date(2025, 12, 20), date(2026, 1, 20), date(2026, 2, 20)],
        disbursement_date=datetime(2025, 11, 20, tzinfo=timezone.utc),
        scheduler=PriceScheduler,
    )


def _make_bcl_single() -> BillingCycleLoan:
    """Single-installment BillingCycleLoan."""
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


def _make_bcl_multi() -> BillingCycleLoan:
    """Multi-installment BillingCycleLoan (3 installments)."""
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
# Invariant 1: pay_installment(settlement_balance) covers the next installment
# ------------------------------------------------------------------


def test_loan_single_early_settlement_pays_off():
    """Single-installment Loan: early payment with settlement_balance pays off."""
    loan = _make_loan_single()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(w.settlement_balance)
        assert w.is_paid_off, f"Expected is_paid_off but remaining={settlement.remaining_balance}"


def test_loan_single_ontime_settlement_pays_off():
    """Single-installment Loan: on-time payment with settlement_balance pays off."""
    loan = _make_loan_single()
    with Warp(loan, datetime(2025, 12, 20, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(w.settlement_balance)
        assert w.is_paid_off, f"Expected is_paid_off but remaining={settlement.remaining_balance}"


def test_loan_single_late_settlement_pays_off():
    """Single-installment Loan: late payment with settlement_balance pays off."""
    loan = _make_loan_single()
    with Warp(loan, datetime(2025, 12, 25, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(w.settlement_balance)
        assert w.is_paid_off, f"Expected is_paid_off but remaining={settlement.remaining_balance}"


def test_loan_multi_early_settlement_covers_next_installment():
    """Multi-installment Loan: early payment covers next installment."""
    loan = _make_loan_multi()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        w.pay_installment(w.settlement_balance)
        inst = w.installments[0]
        assert any(
            a.is_fully_covered for a in inst.allocations
        ), f"Installment 1 not covered: balance={inst.balance}"


def test_bcl_single_early_settlement_pays_off():
    """Single-installment BillingCycleLoan: early payment pays off."""
    loan = _make_bcl_single()
    with Warp(loan, datetime(2025, 11, 10, tzinfo=SAO_PAULO)) as w:
        settlement = w.pay_installment(w.settlement_balance)
        assert w.is_paid_off, f"Expected is_paid_off but remaining={settlement.remaining_balance}"


def test_bcl_single_late_settlement_pays_off():
    """Single-installment BillingCycleLoan: late payment pays off."""
    loan = _make_bcl_single()
    with Warp(loan, datetime(2025, 11, 24, tzinfo=SAO_PAULO)) as w:
        settlement = w.pay_installment(w.settlement_balance)
        assert w.is_paid_off, f"Expected is_paid_off but remaining={settlement.remaining_balance}"


def test_bcl_multi_early_settlement_covers_next_installment():
    """Multi-installment BillingCycleLoan: early payment covers next installment."""
    loan = _make_bcl_multi()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(w.settlement_balance)
        inst = w.installments[0]
        assert any(
            a.is_fully_covered for a in inst.allocations
        ), f"Installment 1 not covered: balance={inst.balance}"


# ------------------------------------------------------------------
# Invariant 2: relationship between settlement_balance and current_balance
# ------------------------------------------------------------------


def test_loan_multi_early_settlement_less_than_current():
    """Multi-installment, early: settlement_balance < current_balance."""
    loan = _make_loan_multi()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        assert w.settlement_balance < w.current_balance, (
            f"settlement={w.settlement_balance} should be < current={w.current_balance}"
        )


def test_loan_single_early_settlement_gte_current():
    """Single-installment, early: settlement_balance >= current_balance."""
    loan = _make_loan_single()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        assert w.settlement_balance >= w.current_balance, (
            f"settlement={w.settlement_balance} should be >= current={w.current_balance}"
        )


def test_loan_single_late_settlement_equals_current():
    """Single-installment, late: settlement_balance == current_balance."""
    loan = _make_loan_single()
    with Warp(loan, datetime(2025, 12, 25, tzinfo=timezone.utc)) as w:
        assert w.settlement_balance == w.current_balance, (
            f"settlement={w.settlement_balance} should == current={w.current_balance}"
        )


def test_bcl_multi_early_settlement_less_than_current():
    """Multi-installment BCL, early: settlement_balance < current_balance."""
    loan = _make_bcl_multi()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance < w.current_balance, (
            f"settlement={w.settlement_balance} should be < current={w.current_balance}"
        )
