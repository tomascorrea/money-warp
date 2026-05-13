"""Test that fully-paid installments are skipped during allocation.

Reproduces the bug where pay_installment allocates interest to an
installment that is already is_fully_paid=True, leaking money from
the payment and shorting the next installment.

See: https://github.com/tomascorrea/money-warp/issues/88
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from money_warp import (
    BillingCycleLoan,
    InterestRate,
    Money,
    MonthlyBillingCycle,
    Warp,
)
from money_warp.engines.constants import BALANCE_TOLERANCE

SAO_PAULO = ZoneInfo("America/Sao_Paulo")

_DUE_DATES = [
    datetime(2025, 5, 15).date(),
    datetime(2025, 6, 15).date(),
    datetime(2025, 7, 15).date(),
    datetime(2025, 8, 15).date(),
    datetime(2025, 9, 15).date(),
    datetime(2025, 10, 15).date(),
]

_PAY_DATES = [
    datetime(2025, 5, 15, tzinfo=SAO_PAULO),
    datetime(2025, 6, 16, tzinfo=SAO_PAULO),
    datetime(2025, 7, 15, tzinfo=SAO_PAULO),
]


def _make_loan() -> BillingCycleLoan:
    """Build a loan whose schedule payment amount causes rounding mismatch.

    With principal=20.24 and 1.99% monthly over 6 installments, each
    payment is R$3.58.  After 3 payments, installment #3 has
    principal overpaid by R$0.01 and interest underpaid by R$0.01,
    making is_fully_paid=True at the aggregate level while the
    per-component view still shows interest owed.
    """
    return BillingCycleLoan(
        principal=Money("20.24"),
        interest_rate=InterestRate("1.990% a.m."),
        billing_cycle=MonthlyBillingCycle(due_dates=_DUE_DATES),
        start_date=datetime(2025, 4, 28, tzinfo=SAO_PAULO),
        num_installments=6,
        disbursement_date=datetime(2025, 4, 28, tzinfo=SAO_PAULO),
        tz=SAO_PAULO,
    )


def _pay_first_three(loan: BillingCycleLoan) -> BillingCycleLoan:
    """Pay installments 1, 2, 3 with the scheduled payment amount."""
    pmt = loan.get_original_schedule().entries[0].payment_amount
    for pay_date in _PAY_DATES:
        with Warp(loan, pay_date) as w:
            w.pay_installment(
                pmt,
                waive_fines=True,
                waive_mora=True,
                waive_overdue_interest=True,
            )
        loan = w
    return loan


def test_fully_paid_installment_receives_no_allocation() -> None:
    """A fully-paid installment must not receive any allocation.

    When installment #3 has is_fully_paid=True (component-level rounding
    offsets cancel out), paying installment #4 must skip #3 entirely.
    The full payment must flow to #4.
    """
    loan = _make_loan()
    pmt = loan.get_original_schedule().entries[0].payment_amount
    loan = _pay_first_three(loan)

    with Warp(loan, datetime(2025, 9, 15, tzinfo=SAO_PAULO)) as w:
        inst3 = w.installments[2]
        assert (
            inst3.is_fully_paid or inst3.balance <= BALANCE_TOLERANCE
        ), f"Precondition: installment #3 should be settled (balance within tolerance), balance={inst3.balance}"

        settlement = w.pay_installment(
            pmt,
            waive_fines=True,
            waive_mora=True,
            waive_overdue_interest=True,
        )

    alloc_for_3 = [a for a in settlement.allocations if a.installment_number == 3]
    assert (
        not alloc_for_3
    ), f"Installment #3 is fully paid but received allocation: interest={alloc_for_3[0].interest_allocated}"

    alloc_for_4 = [a for a in settlement.allocations if a.installment_number == 4]
    assert alloc_for_4, "Installment #4 should have received an allocation"
    assert alloc_for_4[
        0
    ].is_fully_covered, (
        f"Installment #4 should be fully covered but is not. Allocated: {alloc_for_4[0].total_allocated}"
    )
