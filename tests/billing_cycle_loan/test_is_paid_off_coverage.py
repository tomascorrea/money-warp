"""Tests for is_paid_off when all installments have is_fully_covered=True."""

from datetime import date, datetime

from dateutil.relativedelta import relativedelta
from zoneinfo import ZoneInfo

from money_warp import (
    BillingCycleLoan,
    BrazilianWorkingDayCalendar,
    InterestRate,
    Money,
    PriceScheduler,
    Warp,
)
from money_warp.billing_cycle import MonthlyBillingCycle

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def test_is_paid_off_when_all_installments_fully_covered():
    """is_paid_off must be True when every allocation reports is_fully_covered=True.

    Schedule divergence (forward-pass daily interest vs scheduler 2dp
    rounding) can leave a small residual that the exact-zero balance
    check rejects.  The per-installment tolerance that allows
    is_fully_covered should propagate to is_paid_off.

    Uses record_payment (not pay_installment) to bypass the tolerance
    adjustment mechanism, matching how consumer code records payments.
    """
    base = date(2025, 11, 11)
    due_dates = [(base + relativedelta(months=i)) for i in range(1, 5)]

    loan = BillingCycleLoan(
        principal=Money("5000.00"),
        interest_rate=InterestRate("3.99% a.m."),
        billing_cycle=MonthlyBillingCycle(due_dates=due_dates),
        start_date=datetime(2025, 10, 11, tzinfo=SAO_PAULO),
        num_installments=4,
        disbursement_date=datetime(2025, 10, 11, tzinfo=SAO_PAULO),
        scheduler=PriceScheduler,
        tz=SAO_PAULO,
        working_day_calendar=BrazilianWorkingDayCalendar(),
    )

    schedule = loan.get_original_schedule()
    for entry in schedule.entries:
        pay_date = datetime(
            entry.due_date.year,
            entry.due_date.month,
            entry.due_date.day,
            tzinfo=SAO_PAULO,
        )
        with Warp(loan, pay_date) as w:
            settlement = w.record_payment(
                entry.payment_amount,
                pay_date,
                interest_date=pay_date,
            )
            for alloc in settlement.allocations:
                assert (
                    alloc.is_fully_covered is True
                ), f"Installment #{alloc.installment_number} should be fully covered"
        loan = w

    assert loan.current_balance.is_positive(), "Residual should exist (schedule divergence)"
    assert loan.is_paid_off is True
