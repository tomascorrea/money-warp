"""Invariant tests for settlement_balance.

settlement_balance returns the amount needed to fully cover the next
installment via pay_installment.  These invariants must hold:

1. pay_installment(settlement_balance) fully covers the next installment.
2. settlement_balance >= current_balance for single/last installment.
3. settlement_balance < current_balance for multi-installment (more than 1 remaining).
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from money_warp import Warp

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


# ------------------------------------------------------------------
# Invariant 1: pay_installment(settlement_balance) covers the next installment
# ------------------------------------------------------------------


def test_loan_single_early_settlement_pays_off(single_installment_loan):
    """Single-installment Loan: early payment with settlement_balance pays off."""
    with Warp(single_installment_loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(w.settlement_balance)
        assert w.is_paid_off, f"Expected is_paid_off but remaining={settlement.remaining_balance}"


def test_loan_single_ontime_settlement_pays_off(single_installment_loan):
    """Single-installment Loan: on-time payment with settlement_balance pays off."""
    with Warp(single_installment_loan, datetime(2025, 12, 20, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(w.settlement_balance)
        assert w.is_paid_off, f"Expected is_paid_off but remaining={settlement.remaining_balance}"


def test_loan_single_late_settlement_pays_off(single_installment_loan):
    """Single-installment Loan: late payment with settlement_balance pays off."""
    with Warp(single_installment_loan, datetime(2025, 12, 25, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(w.settlement_balance)
        assert w.is_paid_off, f"Expected is_paid_off but remaining={settlement.remaining_balance}"


def test_loan_multi_early_settlement_covers_next_installment(multi_installment_loan):
    """Multi-installment Loan: early payment covers next installment."""
    with Warp(multi_installment_loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        w.pay_installment(w.settlement_balance)
        inst = w.installments[0]
        assert any(a.is_fully_covered for a in inst.allocations), f"Installment 1 not covered: balance={inst.balance}"


def test_bcl_single_early_settlement_pays_off(single_bcl):
    """Single-installment BillingCycleLoan: early payment pays off."""
    with Warp(single_bcl, datetime(2025, 11, 10, tzinfo=SAO_PAULO)) as w:
        settlement = w.pay_installment(w.settlement_balance)
        assert w.is_paid_off, f"Expected is_paid_off but remaining={settlement.remaining_balance}"


def test_bcl_single_late_settlement_pays_off(single_bcl):
    """Single-installment BillingCycleLoan: late payment pays off."""
    with Warp(single_bcl, datetime(2025, 11, 24, tzinfo=SAO_PAULO)) as w:
        settlement = w.pay_installment(w.settlement_balance)
        assert w.is_paid_off, f"Expected is_paid_off but remaining={settlement.remaining_balance}"


def test_bcl_multi_early_settlement_covers_next_installment(multi_bcl):
    """Multi-installment BillingCycleLoan: early payment covers next installment."""
    with Warp(multi_bcl, datetime(2025, 12, 10, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(w.settlement_balance)
        inst = w.installments[0]
        assert any(a.is_fully_covered for a in inst.allocations), f"Installment 1 not covered: balance={inst.balance}"


# ------------------------------------------------------------------
# Invariant 2: relationship between settlement_balance and current_balance
# ------------------------------------------------------------------


def test_loan_multi_early_settlement_less_than_current(multi_installment_loan):
    """Multi-installment, early: settlement_balance < current_balance."""
    with Warp(multi_installment_loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        assert (
            w.settlement_balance < w.current_balance
        ), f"settlement={w.settlement_balance} should be < current={w.current_balance}"


def test_loan_single_early_settlement_gte_current(single_installment_loan):
    """Single-installment, early: settlement_balance >= current_balance."""
    with Warp(single_installment_loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        assert (
            w.settlement_balance >= w.current_balance
        ), f"settlement={w.settlement_balance} should be >= current={w.current_balance}"


def test_loan_single_late_settlement_equals_current(single_installment_loan):
    """Single-installment, late: settlement_balance == current_balance."""
    with Warp(single_installment_loan, datetime(2025, 12, 25, tzinfo=timezone.utc)) as w:
        assert (
            w.settlement_balance == w.current_balance
        ), f"settlement={w.settlement_balance} should == current={w.current_balance}"


def test_bcl_multi_early_settlement_less_than_current(multi_bcl):
    """Multi-installment BCL, early: settlement_balance < current_balance."""
    with Warp(multi_bcl, datetime(2025, 12, 10, tzinfo=SAO_PAULO)) as w:
        assert (
            w.settlement_balance < w.current_balance
        ), f"settlement={w.settlement_balance} should be < current={w.current_balance}"
