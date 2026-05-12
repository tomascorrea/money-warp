"""Tests for installments with overpaid principal but underpaid interest."""

from datetime import datetime
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


def test_pay_installment_covers_interest_on_principal_overcovered_installment():
    """Settlement must allocate interest to an installment whose principal was
    overcovered by a prior spillover before moving on to the next installment.

    Scenario: 6-installment loan where settlements 1-3 leave installment #3
    with principal_paid > expected_principal but interest still owed.
    Settlement 4 must first satisfy #3's remaining contractual interest,
    then allocate the remainder to #4.
    """
    loan = BillingCycleLoan(
        principal=Money("2257.92"),
        interest_rate=InterestRate("1.990% a.m."),
        billing_cycle=MonthlyBillingCycle(
            due_dates=[datetime(2025, i, 6).date() for i in range(1, 7)],
        ),
        start_date=datetime(2024, 12, 3, tzinfo=SAO_PAULO),
        num_installments=6,
        disbursement_date=datetime(2024, 12, 3, tzinfo=SAO_PAULO),
        scheduler=PriceScheduler,
        mora_interest_rate=InterestRate("1.990% a.m."),
        fine_rate=InterestRate("2% a.m."),
        tz=SAO_PAULO,
        working_day_calendar=BrazilianWorkingDayCalendar(),
    )

    with Warp(loan, datetime(2024, 12, 30, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(Money("403.67"), waive_overdue_interest=True)
    loan = w

    with Warp(loan, datetime(2025, 3, 5, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(
            Money("403.67"),
            waive_fines=True,
            waive_mora=True,
            waive_overdue_interest=True,
        )
    loan = w

    with Warp(loan, datetime(2025, 4, 7, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(
            Money("403.67"),
            waive_fines=True,
            waive_mora=True,
            waive_overdue_interest=True,
        )
    loan = w

    inst3 = loan.installments[2]
    assert inst3.principal_paid > inst3.expected_principal
    interest_owed = inst3.expected_interest - inst3.interest_paid
    assert interest_owed == Money("27.18")

    with Warp(loan, datetime(2025, 5, 5, tzinfo=SAO_PAULO)) as w:
        settlement = w.pay_installment(
            Money("403.67"),
            waive_fines=True,
            waive_mora=True,
            waive_overdue_interest=True,
        )

    alloc_by_num = {a.installment_number: a for a in settlement.allocations}

    assert 3 in alloc_by_num, "Settlement 4 must allocate to installment #3"
    assert alloc_by_num[3].interest_allocated == Money("27.18")
    assert alloc_by_num[3].is_fully_covered is True

    assert 4 in alloc_by_num, "Settlement 4 must also allocate to installment #4"
