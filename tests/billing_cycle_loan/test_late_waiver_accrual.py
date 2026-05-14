"""Tests for the interest-accrual fix when an installment is paid late
with ``waive_overdue_interest=True``.

Without the fix, a late payment that fully covers an installment shortens
the next installment's interest period (it starts from the actual payment
date instead of the contractual due date), so the principal/interest
split drifts and small residuals leak past ``is_paid_off``.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from money_warp import Money, Warp

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def test_late_paid_installment_does_not_shorten_next_period(make_late_waiver_loan):
    """Paying #1 one day late with all waivers must not change #2's split."""
    on_time = make_late_waiver_loan()
    with Warp(on_time, datetime(2025, 12, 25, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(Money("188.40"))
    on_time = w
    with Warp(on_time, datetime(2026, 1, 25, tzinfo=SAO_PAULO)) as w:
        on_time_second = w.pay_installment(Money("188.40"))

    late = make_late_waiver_loan()
    with Warp(late, datetime(2025, 12, 26, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(
            Money("188.40"),
            waive_fines=True,
            waive_mora=True,
            waive_overdue_interest=True,
        )
    late = w
    with Warp(late, datetime(2026, 1, 25, tzinfo=SAO_PAULO)) as w:
        late_second = w.pay_installment(Money("188.40"))

    assert late_second.allocations[0].principal_allocated == on_time_second.allocations[0].principal_allocated
    assert late_second.allocations[0].interest_allocated == on_time_second.allocations[0].interest_allocated


def test_every_installment_late_with_waivers_matches_on_time_split(make_late_waiver_loan):
    """Paying each installment one day late with all waivers must produce the
    same principal/interest split per installment as paying every installment
    on time."""
    on_time_due_dates = [
        datetime(2025, 12, 25, tzinfo=SAO_PAULO),
        datetime(2026, 1, 25, tzinfo=SAO_PAULO),
        datetime(2026, 2, 25, tzinfo=SAO_PAULO),
        datetime(2026, 3, 25, tzinfo=SAO_PAULO),
    ]
    on_time_loan = make_late_waiver_loan()
    on_time_splits = []
    for pay_dt in on_time_due_dates:
        with Warp(on_time_loan, pay_dt) as w:
            r = w.pay_installment(Money("188.40"))
            on_time_splits.append((r.allocations[0].principal_allocated, r.allocations[0].interest_allocated))
        on_time_loan = w

    late_dates = [
        datetime(2025, 12, 26, tzinfo=SAO_PAULO),
        datetime(2026, 1, 26, tzinfo=SAO_PAULO),
        datetime(2026, 2, 26, tzinfo=SAO_PAULO),
        datetime(2026, 3, 26, tzinfo=SAO_PAULO),
    ]
    late_loan = make_late_waiver_loan()
    late_splits = []
    for pay_dt in late_dates:
        with Warp(late_loan, pay_dt) as w:
            r = w.pay_installment(
                Money("188.40"),
                waive_fines=True,
                waive_mora=True,
                waive_overdue_interest=True,
            )
            late_splits.append((r.allocations[0].principal_allocated, r.allocations[0].interest_allocated))
        late_loan = w

    assert late_splits == on_time_splits
