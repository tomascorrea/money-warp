"""Regression tests for the settlement spill invariant.

Settlement totals must equal the sum of their per-allocation counterparts:

    settlement.X_paid == sum(a.X_allocated for a in settlement.allocations)

for X in {principal, interest, mora, fine}. Before the fix, spill amounts
and sub-cent allocations were counted in the totals but absent from the
allocations list.
"""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money, Warp
from money_warp.scheduler import PriceScheduler


def _utc(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _assert_allocation_invariant(settlement):
    """Assert that settlement totals equal the sum of allocations."""
    sum_principal = sum(a.principal_allocated.raw_amount for a in settlement.allocations)
    sum_interest = sum(a.interest_allocated.raw_amount for a in settlement.allocations)
    sum_mora = sum(a.mora_allocated.raw_amount for a in settlement.allocations)
    sum_fine = sum(a.fine_allocated.raw_amount for a in settlement.allocations)

    assert settlement.principal_paid.raw_amount == sum_principal
    assert settlement.interest_paid.raw_amount == sum_interest
    assert settlement.mora_paid.raw_amount == sum_mora
    assert settlement.fine_paid.raw_amount == sum_fine


# -- Fixtures --


@pytest.fixture
def catchup_loan():
    """5-installment loan: first paid early, then 3 months skipped."""
    loan = Loan(
        principal=Money(5000),
        interest_rate=InterestRate("2.5% a.m."),
        due_dates=[
            date(2026, 2, 10),
            date(2026, 3, 10),
            date(2026, 4, 10),
            date(2026, 5, 10),
            date(2026, 6, 10),
        ],
        disbursement_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
        scheduler=PriceScheduler,
        mora_interest_rate=InterestRate("1% a.m."),
        fine_rate=InterestRate("2% a.m."),
    )
    with Warp(loan, datetime(2026, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(loan.installments[0].expected_payment)
    return w


@pytest.fixture
def late_two_installment_loan():
    """2-installment loan paid late in a single catch-up."""
    return Loan(
        principal=Money(2000),
        interest_rate=InterestRate("3% a.m."),
        due_dates=[date(2026, 2, 10), date(2026, 3, 10)],
        disbursement_date=datetime(2026, 1, 10, tzinfo=timezone.utc),
        scheduler=PriceScheduler,
        mora_interest_rate=InterestRate("1% a.m."),
        fine_rate=InterestRate("2% a.m."),
    )


@pytest.fixture
def on_time_loan():
    """3-installment loan paid exactly on schedule."""
    return Loan(
        principal=Money(10000),
        interest_rate=InterestRate("6% a"),
        due_dates=[date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


# -- Bug-report reproduction (catch-up payment, large spill) --


def test_catchup_settlement_invariant(catchup_loan):
    with Warp(catchup_loan, datetime(2026, 5, 25, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money(5000))

    _assert_allocation_invariant(settlement)


def test_catchup_settlement_exact_totals(catchup_loan):
    with Warp(catchup_loan, datetime(2026, 5, 25, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money(5000))

    assert settlement.principal_paid == Money("4512.07")
    assert settlement.interest_paid == Money("294.98")
    assert settlement.mora_paid == Money("106.58")
    assert settlement.fine_paid == Money("86.38")
    assert settlement.remaining_balance == Money("0.00")


def test_catchup_all_installments_covered(catchup_loan):
    with Warp(catchup_loan, datetime(2026, 5, 25, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money(5000))

    assert len(settlement.allocations) == 5
    assert all(a.is_fully_covered for a in settlement.allocations)


# -- Late payment on 2-installment loan --


def test_late_payment_settlement_invariant(late_two_installment_loan):
    with Warp(late_two_installment_loan, datetime(2026, 4, 10, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money(2500))

    _assert_allocation_invariant(settlement)


def test_late_payment_exact_totals(late_two_installment_loan):
    with Warp(late_two_installment_loan, datetime(2026, 4, 10, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money(2500))

    assert settlement.principal_paid == Money("2328.84")
    assert settlement.interest_paid == Money("89.21")
    assert settlement.mora_paid == Money("40.17")
    assert settlement.fine_paid == Money("41.78")
    assert settlement.remaining_balance == Money("0.00")


def test_late_payment_exact_allocations(late_two_installment_loan):
    with Warp(late_two_installment_loan, datetime(2026, 4, 10, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money(2500))

    assert len(settlement.allocations) == 2

    a1 = settlement.allocations[0]
    assert a1.installment_number == 1
    assert a1.principal_allocated == Money("983.43")
    assert a1.interest_allocated == Money("61.17")
    assert a1.mora_allocated == Money("40.17")
    assert a1.fine_allocated == Money("20.89")
    assert a1.is_fully_covered is True

    a2 = settlement.allocations[1]
    assert a2.installment_number == 2
    assert a2.principal_allocated == Money("1345.41")
    assert a2.interest_allocated == Money("28.04")
    assert a2.mora_allocated == Money("0.00")
    assert a2.fine_allocated == Money("20.89")
    assert a2.is_fully_covered is True


# -- On-time exact payment (sub-cent interest spill) --


def test_on_time_exact_payment_invariant(on_time_loan):
    schedule = on_time_loan.get_original_schedule()
    settlement = on_time_loan.record_payment(
        schedule[0].payment_amount,
        _utc(schedule[0].due_date),
    )

    _assert_allocation_invariant(settlement)


def test_on_time_sequential_payments_invariant(on_time_loan):
    schedule = on_time_loan.get_original_schedule()
    for entry in schedule:
        settlement = on_time_loan.record_payment(
            entry.payment_amount,
            _utc(entry.due_date),
        )
        _assert_allocation_invariant(settlement)


# -- Parametrized: invariant holds for various payment sizes --


@pytest.mark.parametrize(
    "payment_amount",
    [
        Money("500"),
        Money("1079.70"),
        Money("2000"),
        Money("5000"),
        Money("6000"),
    ],
)
def test_invariant_holds_for_various_payment_sizes(payment_amount):
    loan = Loan(
        principal=Money(5000),
        interest_rate=InterestRate("2.5% a.m."),
        due_dates=[
            date(2026, 2, 10),
            date(2026, 3, 10),
            date(2026, 4, 10),
            date(2026, 5, 10),
            date(2026, 6, 10),
        ],
        disbursement_date=datetime(2026, 1, 5, tzinfo=timezone.utc),
        scheduler=PriceScheduler,
        mora_interest_rate=InterestRate("1% a.m."),
        fine_rate=InterestRate("2% a.m."),
    )

    with Warp(loan, datetime(2026, 3, 15, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(payment_amount)

    _assert_allocation_invariant(settlement)
