"""Tests for BillingCycleLoan.settlement_balance with explicit expected values."""

from datetime import datetime
from zoneinfo import ZoneInfo

from money_warp import Money, Warp

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


# ------------------------------------------------------------------
# Single installment
# ------------------------------------------------------------------


def test_bcl_single_early_equals_scheduled_pmt(single_bcl):
    """Early: settlement_balance equals scheduled PMT."""
    sched = single_bcl.get_original_schedule()
    with Warp(single_bcl, datetime(2025, 11, 10, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == sched.entries[0].payment_amount
        assert w.settlement_balance == Money("993.19")


def test_bcl_single_early_greater_than_current(single_bcl):
    """Early: settlement_balance > current_balance."""
    with Warp(single_bcl, datetime(2025, 11, 10, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == Money("993.19")
        assert w.current_balance == Money("977.42")
        assert w.settlement_balance > w.current_balance


def test_bcl_single_ontime_equals_current(single_bcl):
    """On-time: settlement_balance == current_balance (single installment at due date)."""
    with Warp(single_bcl, datetime(2025, 11, 20, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == w.current_balance


def test_bcl_single_late_equals_current(single_bcl):
    """Late: settlement_balance == current_balance."""
    with Warp(single_bcl, datetime(2025, 11, 24, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == Money("1019.44")
        assert w.settlement_balance == w.current_balance


def test_bcl_single_at_disbursement_equals_pmt(single_bcl):
    """At disbursement: settlement_balance equals scheduled PMT."""
    sched = single_bcl.get_original_schedule()
    with Warp(single_bcl, datetime(2025, 10, 21, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == sched.entries[0].payment_amount
        assert w.settlement_balance == Money("993.19")


def test_bcl_single_components_sum(single_bcl):
    """settlement_balance = interest_to_due + scheduled_principal (early, no fines)."""
    sched = single_bcl.get_original_schedule()
    with Warp(single_bcl, datetime(2025, 11, 10, tzinfo=SAO_PAULO)) as w:
        expected_principal = sched.entries[0].principal_payment
        interest_component = Money(
            w.settlement_balance.raw_amount - expected_principal.raw_amount
        )
        assert interest_component == sched.entries[0].interest_payment


# ------------------------------------------------------------------
# Multi installment
# ------------------------------------------------------------------


def test_bcl_multi_early_equals_first_pmt(multi_bcl):
    """Early: settlement_balance equals installment 1 PMT."""
    sched = multi_bcl.get_original_schedule()
    with Warp(multi_bcl, datetime(2025, 12, 10, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == sched.entries[0].payment_amount
        assert w.settlement_balance == Money("3672.95")


def test_bcl_multi_early_less_than_current(multi_bcl):
    """Early: settlement_balance < current_balance."""
    with Warp(multi_bcl, datetime(2025, 12, 10, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance < w.current_balance


def test_bcl_multi_ontime_less_than_current(multi_bcl):
    """On-time for inst 1: settlement_balance < current_balance (3 installments remain)."""
    with Warp(multi_bcl, datetime(2025, 12, 20, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == Money("3672.95")
        assert w.settlement_balance < w.current_balance


def test_bcl_multi_after_first_payment_covers_second(multi_bcl):
    """After paying inst 1, settlement_balance covers inst 2."""
    sched = multi_bcl.get_original_schedule()
    with Warp(multi_bcl, datetime(2025, 12, 20, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(w.settlement_balance)
        warped = w

    with Warp(warped, datetime(2026, 1, 10, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == sched.entries[1].payment_amount


def test_bcl_multi_fully_paid_is_zero(multi_bcl):
    """After all installments paid, settlement_balance is zero."""
    sched = multi_bcl.get_original_schedule()

    with Warp(multi_bcl, datetime(2025, 12, 20, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(sched.entries[0].payment_amount)
        w1 = w

    with Warp(w1, datetime(2026, 1, 20, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(sched.entries[1].payment_amount)
        w2 = w

    with Warp(w2, datetime(2026, 2, 20, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(sched.entries[2].payment_amount)
        w3 = w

    with Warp(w3, datetime(2026, 3, 1, tzinfo=SAO_PAULO)) as w:
        assert w.settlement_balance == Money("0.00")
