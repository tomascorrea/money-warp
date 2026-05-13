"""Tests for correct interest allocation across installments.

Validates that pay_installment never skips an installment with unpaid
obligations.  The original bug: waivers caused principal spillover that
made principal_covered_count report an installment as "covered" while its
interest was still owed, causing subsequent payments to skip it entirely.
"""

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


def _make_loan() -> BillingCycleLoan:
    return BillingCycleLoan(
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


def test_waiver_payments_never_skip_installments():
    """Late payments with waivers must cover each installment's full
    obligations (principal + interest) before moving to the next one.

    Scenario: 6-installment loan with 4 late payments using waivers.
    After all 4 payments, installments #1-#3 must be fully paid with
    no gaps.
    """
    loan = _make_loan()

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

    with Warp(loan, datetime(2025, 5, 5, tzinfo=SAO_PAULO)) as w:
        settlement = w.pay_installment(
            Money("403.67"),
            waive_fines=True,
            waive_mora=True,
            waive_overdue_interest=True,
        )
    loan = w

    for inst in loan.installments[:3]:
        assert inst.is_fully_paid, f"Installment #{inst.number} should be fully paid but has balance={inst.balance}"

    alloc_by_num = {a.installment_number: a for a in settlement.allocations}
    assert 4 in alloc_by_num, "Settlement 4 must also allocate to installment #4"
