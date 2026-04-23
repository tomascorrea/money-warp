"""Tests for BillingCycleLoan payment settlements."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from money_warp import (
    BillingCycleLoan,
    InterestRate,
    Money,
    PriceScheduler,
    Warp,
)
from money_warp.billing_cycle import MonthlyBillingCycle


def test_on_time_payment_first_installment(simple_loan):
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 2, 12, tzinfo=timezone.utc),
    )
    assert s.fine_paid == Money("0.00")
    assert s.mora_paid == Money("0.00")
    assert s.interest_paid == Money("39.38")
    assert s.principal_paid == Money("983.20")
    assert s.remaining_balance == Money("2016.80")


def test_on_time_payment_all_installments(simple_loan):
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 2, 12, tzinfo=timezone.utc))
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 3, 15, tzinfo=timezone.utc))
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 4, 12, tzinfo=timezone.utc))

    assert simple_loan.is_paid_off is True
    assert len(simple_loan.settlements) == 3


def test_on_time_second_settlement_values(simple_loan):
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 2, 12, tzinfo=timezone.utc))
    s2 = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 15, tzinfo=timezone.utc),
    )
    assert s2.fine_paid == Money("0.00")
    assert s2.mora_paid == Money("0.00")
    assert s2.interest_paid == Money("19.51")
    assert s2.principal_paid == Money("1003.07")


def test_on_time_third_settlement_values(simple_loan):
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 2, 12, tzinfo=timezone.utc))
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 3, 15, tzinfo=timezone.utc))
    s3 = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 4, 12, tzinfo=timezone.utc),
    )
    assert s3.fine_paid == Money("0.00")
    assert s3.mora_paid == Money("0.00")
    assert s3.interest_paid == Money("8.85")
    assert s3.principal_paid == Money("1013.73")


def test_allocation_installment_numbers(simple_loan):
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 2, 12, tzinfo=timezone.utc),
    )
    assert len(s.allocations) == 1
    assert s.allocations[0].installment_number == 1
    assert s.allocations[0].is_fully_covered is True


def test_allocation_is_fully_covered_with_one_cent_gap_multi_installment():
    """is_fully_covered=True when payment is R$0.01 short on a multi-installment BCL.

    The _apply_coverage_fixup only triggers when the entire loan is nearly
    paid off.  For a mid-loan installment the initial per-installment check
    must apply BALANCE_TOLERANCE directly.
    """
    sao_paulo = ZoneInfo("America/Sao_Paulo")
    loan = BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("26.675% a.a."),
        billing_cycle=MonthlyBillingCycle(
            due_dates=[
                datetime(2025, 12, 18).date(),
                datetime(2026, 1, 18).date(),
                datetime(2026, 2, 18).date(),
            ],
        ),
        start_date=datetime(2025, 11, 13, tzinfo=sao_paulo),
        num_installments=3,
        disbursement_date=datetime(2025, 11, 13, tzinfo=sao_paulo),
        scheduler=PriceScheduler,
        tz=sao_paulo,
    )
    schedule = loan.get_original_schedule()
    short = schedule.entries[0].payment_amount - Money("0.01")

    with Warp(loan, datetime(2025, 12, 18, tzinfo=sao_paulo)) as w:
        settlement = w.pay_installment(short)
        assert settlement.allocations[0].is_fully_covered is True


def test_allocation_not_fully_covered_with_two_cent_gap_multi_installment():
    """is_fully_covered=False when payment is R$0.02 short — beyond tolerance."""
    sao_paulo = ZoneInfo("America/Sao_Paulo")
    loan = BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("26.675% a.a."),
        billing_cycle=MonthlyBillingCycle(
            due_dates=[
                datetime(2025, 12, 18).date(),
                datetime(2026, 1, 18).date(),
                datetime(2026, 2, 18).date(),
            ],
        ),
        start_date=datetime(2025, 11, 13, tzinfo=sao_paulo),
        num_installments=3,
        disbursement_date=datetime(2025, 11, 13, tzinfo=sao_paulo),
        scheduler=PriceScheduler,
        tz=sao_paulo,
    )
    schedule = loan.get_original_schedule()
    short = schedule.entries[0].payment_amount - Money("0.02")

    with Warp(loan, datetime(2025, 12, 18, tzinfo=sao_paulo)) as w:
        settlement = w.pay_installment(short)
        assert settlement.allocations[0].is_fully_covered is False


def test_allocation_is_fully_covered_when_tolerance_absorbs_residual():
    """Regression: is_paid_off=True must imply allocation.is_fully_covered=True.

    Reproduces the reported scenario: a single-installment BillingCycleLoan
    where forward-pass interest vs. schedule-level rounding leaves a
    sub-cent principal residual, which is then absorbed by the tolerance
    adjustment.  The loan becomes paid off but the settlement's allocation
    used to still report is_fully_covered=False.
    """
    sao_paulo = ZoneInfo("America/Sao_Paulo")
    loan = BillingCycleLoan(
        principal=Money("19523.82"),
        interest_rate=InterestRate("26.675% a.a."),
        billing_cycle=MonthlyBillingCycle(
            due_dates=[datetime(2025, 12, 12).date()],
        ),
        start_date=datetime(2025, 11, 11, tzinfo=sao_paulo),
        num_installments=1,
        disbursement_date=datetime(2025, 11, 11, tzinfo=sao_paulo),
        scheduler=PriceScheduler,
        tz=sao_paulo,
    )

    with Warp(loan, datetime(2025, 12, 10, tzinfo=sao_paulo)) as w:
        settlement = w.pay_installment(Money("19919.86"))
        assert w.is_paid_off is True
        assert settlement.allocations[-1].is_fully_covered is True
