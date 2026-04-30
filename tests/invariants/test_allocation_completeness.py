"""Property-based tests: every cent of a payment must be fully allocated."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from money_warp import Money, Settlement, Warp

from strategies import (
    DISBURSEMENT,
    annual_rate_st,
    build_loan,
    payment_fraction_st,
    principal_st,
    scheduler_st,
)

num_installments_st = st.integers(min_value=1, max_value=12)


def _assert_fully_allocated(settlement: Settlement) -> None:
    """Assert the three allocation invariants on a settlement."""
    assert (
        settlement.total_paid == settlement.payment_amount
    ), f"Component sum {settlement.total_paid} != payment {settlement.payment_amount}"

    alloc_fine = Money(sum((a.fine_allocated.raw_amount for a in settlement.allocations), Decimal(0)))
    alloc_interest = Money(sum((a.interest_allocated.raw_amount for a in settlement.allocations), Decimal(0)))
    alloc_mora = Money(sum((a.mora_allocated.raw_amount for a in settlement.allocations), Decimal(0)))
    alloc_principal = Money(sum((a.principal_allocated.raw_amount for a in settlement.allocations), Decimal(0)))

    assert alloc_fine == settlement.fine_paid, f"Allocation fine sum {alloc_fine} != fine_paid {settlement.fine_paid}"
    assert (
        alloc_interest == settlement.interest_paid
    ), f"Allocation interest sum {alloc_interest} != interest_paid {settlement.interest_paid}"
    assert alloc_mora == settlement.mora_paid, f"Allocation mora sum {alloc_mora} != mora_paid {settlement.mora_paid}"
    assert (
        alloc_principal == settlement.principal_paid
    ), f"Allocation principal sum {alloc_principal} != principal_paid {settlement.principal_paid}"

    alloc_total = Money(sum((a.total_allocated.raw_amount for a in settlement.allocations), Decimal(0)))
    assert (
        alloc_total == settlement.payment_amount
    ), f"Allocation total {alloc_total} != payment {settlement.payment_amount}"


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
    payment_fraction=payment_fraction_st,
)
@settings(max_examples=50)
def test_on_time_payment_fully_allocated(principal, annual_rate, num_installments, scheduler, payment_fraction):
    """Paying on the due date: all money is accounted for."""
    loan = build_loan(principal, annual_rate, num_installments, scheduler)
    due_date_dt = datetime(
        loan.due_dates[0].year,
        loan.due_dates[0].month,
        loan.due_dates[0].day,
        tzinfo=timezone.utc,
    )

    with Warp(loan, due_date_dt) as warped:
        amount = Money(
            str((warped.current_balance.raw_amount * Decimal(str(payment_fraction))).quantize(Decimal("0.01")))
        )
        if amount.is_zero() or amount.is_negative():
            return
        settlement = warped.pay_installment(amount)

    _assert_fully_allocated(settlement)


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
    payment_fraction=payment_fraction_st,
    days_early=st.integers(min_value=1, max_value=25),
)
@settings(max_examples=50)
def test_early_payment_fully_allocated(
    principal, annual_rate, num_installments, scheduler, payment_fraction, days_early
):
    """Paying before the due date: all money is accounted for."""
    loan = build_loan(principal, annual_rate, num_installments, scheduler)
    due_date_dt = datetime(
        loan.due_dates[0].year,
        loan.due_dates[0].month,
        loan.due_dates[0].day,
        tzinfo=timezone.utc,
    )
    early_dt = due_date_dt - timedelta(days=days_early)
    if early_dt <= DISBURSEMENT:
        return

    with Warp(loan, early_dt) as warped:
        amount = Money(
            str((warped.current_balance.raw_amount * Decimal(str(payment_fraction))).quantize(Decimal("0.01")))
        )

        settlement = warped.pay_installment(amount)

    _assert_fully_allocated(settlement)


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
    payment_fraction=payment_fraction_st,
    days_late=st.integers(min_value=1, max_value=60),
)
@settings(max_examples=50)
def test_late_payment_with_fines_fully_allocated(
    principal, annual_rate, num_installments, scheduler, payment_fraction, days_late
):
    """Paying after the due date (fines + mora active): all money is accounted for."""
    loan = build_loan(principal, annual_rate, num_installments, scheduler)
    due_date_dt = datetime(
        loan.due_dates[0].year,
        loan.due_dates[0].month,
        loan.due_dates[0].day,
        tzinfo=timezone.utc,
    )
    late_dt = due_date_dt + timedelta(days=days_late)

    with Warp(loan, late_dt) as warped:
        amount = Money(
            str((warped.current_balance.raw_amount * Decimal(str(payment_fraction))).quantize(Decimal("0.01")))
        )

        settlement = warped.pay_installment(amount)

    _assert_fully_allocated(settlement)


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=st.integers(min_value=2, max_value=12),
    scheduler=scheduler_st,
    fractions=st.lists(
        st.floats(min_value=0.50, max_value=1.0),
        min_size=2,
        max_size=3,
    ),
)
@settings(max_examples=50)
def test_multiple_sequential_payments_all_fully_allocated(
    principal, annual_rate, num_installments, scheduler, fractions
):
    """Multiple payments across due dates: every settlement is fully allocated."""
    loan = build_loan(principal, annual_rate, num_installments, scheduler)
    payments_to_make = min(len(fractions), num_installments)

    for i in range(payments_to_make):
        due_date_dt = datetime(
            loan.due_dates[i].year,
            loan.due_dates[i].month,
            loan.due_dates[i].day,
            tzinfo=timezone.utc,
        )

        with Warp(loan, due_date_dt) as warped:
            amount = Money(
                str((warped.current_balance.raw_amount * Decimal(str(fractions[i]))).quantize(Decimal("0.01")))
            )

            warped.pay_installment(amount)

    for settlement in loan.settlements:
        _assert_fully_allocated(settlement)
