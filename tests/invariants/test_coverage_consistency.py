"""Test that is_fully_covered and is_fully_paid stay consistent.

Invariant: for every allocation, ``allocation.is_fully_covered`` must
agree with ``installment.is_fully_paid`` for the targeted installment.
If a payment is marked as fully covering an installment, that
installment must also be marked as fully paid.

See: https://github.com/tomascorrea/money-warp/issues/93
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from money_warp import (
    BillingCycleLoan,
    InterestRate,
    Money,
    MonthlyBillingCycle,
    PriceScheduler,
    Warp,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _mora_resolver(reference_date: date, base_rate: InterestRate) -> InterestRate:
    return InterestRate("12% a.m.")


def test_coverage_matches_fully_paid_for_late_payment_with_variable_mora() -> None:
    """Late payment with a per-cycle mora resolver must keep the flags consistent.

    Reproduces the bug where the installment snapshot built during
    ``compute_state`` uses the calculator's default mora rate instead of
    the resolved per-cycle rate, making ``inst.balance`` underestimate
    the true obligation. The loan-level allocation then flags the
    installment as ``is_fully_covered=True`` while the post-payment
    installment view shows ``is_fully_paid=False``.
    """
    loan = BillingCycleLoan(
        principal=Money("223.09"),
        interest_rate=InterestRate("26.675% a.a."),
        billing_cycle=MonthlyBillingCycle(due_dates=[date(2026, 1, 9), date(2026, 2, 9)]),
        start_date=datetime(2025, 12, 30, tzinfo=SAO_PAULO),
        num_installments=2,
        disbursement_date=datetime(2025, 12, 30, tzinfo=SAO_PAULO),
        scheduler=PriceScheduler,
        fine_rate=InterestRate("2% a.m."),
        mora_rate_resolver=_mora_resolver,
    )

    with Warp(loan, datetime(2026, 1, 7, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(Money("113.40"), waive_overdue_interest=True)
    loan = w

    with Warp(loan, datetime(2026, 2, 11, tzinfo=SAO_PAULO)) as w:
        settlement = w.pay_installment(Money("116.12"), waive_overdue_interest=True)
        installments_by_number = {inst.number: inst for inst in w.installments}

        for allocation in settlement.allocations:
            installment = installments_by_number[allocation.installment_number]
            assert allocation.is_fully_covered == installment.is_fully_paid, (
                f"Installment #{allocation.installment_number}: "
                f"is_fully_covered={allocation.is_fully_covered} "
                f"but is_fully_paid={installment.is_fully_paid}. "
                f"balance={installment.balance}, "
                f"expected={installment.expected_principal}+{installment.expected_interest}"
                f"+{installment.expected_mora}+{installment.expected_fine}, "
                f"paid={installment.principal_paid}+{installment.interest_paid}"
                f"+{installment.mora_paid}+{installment.fine_paid}"
            )
