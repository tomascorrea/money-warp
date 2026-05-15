"""Tests for sequential installment coverage ordering.

Money flows oldest-first through the allocation engine: principal
allocated to installment N+1 requires installment N's principal to be
fully covered. This file asserts that *principal* never leaks past a
principal-uncovered installment.

Flag monotonicity (``is_fully_covered`` never going True after False)
is *not* asserted here — non-principal pools (mora, fine, interest)
running out on an earlier installment can legitimately leave it
uncovered while later installments are fully paid. The per-allocation
``is_fully_covered == is_fully_paid`` invariant lives in
``test_coverage_consistency``.

Includes both a deterministic reproduction of the original bug and
property-based tests (Hypothesis) that assert the invariant holds
for arbitrary loan parameters, payment amounts, and timing.
"""

from datetime import date, datetime, timedelta, timezone
from typing import List
from zoneinfo import ZoneInfo

from hypothesis import given, settings
from hypothesis import strategies as st

from money_warp import (
    BillingCycleLoan,
    BrazilianWorkingDayCalendar,
    Installment,
    InterestRate,
    Money,
    MonthlyBillingCycle,
    PriceScheduler,
    Settlement,
    Warp,
)

from .strategies import (
    DISBURSEMENT,
    annual_rate_st,
    build_loan,
    days_offset_st,
    make_payment_amount,
    num_installments_st,
    payment_fraction_st,
    principal_st,
    scheduler_st,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def _resolve_high_mora_rate(reference_date: date, base_mora_rate: InterestRate) -> InterestRate:
    return InterestRate("17% a.m.")


def _assert_sequential_coverage(settlement: Settlement, installments: List[Installment]) -> None:
    """Assert that no principal leaks past a principal-uncovered installment.

    Principal flows oldest-first: once an installment still owes
    principal, no later installment may receive any principal in the
    same settlement. Non-principal gaps (mora/fine/interest pools
    running out, or sub-cent residuals absorbed by tolerance) do not
    block principal flow — the earlier installment kept everything it
    could absorb and the remaining principal pool legitimately moved
    onward.

    Flag monotonicity (``is_fully_covered`` never going True after
    False) is *not* enforced. The per-allocation
    ``is_fully_covered == is_fully_paid`` invariant lives in
    ``test_coverage_consistency``.
    """
    inst_by_number = {inst.number: inst for inst in installments}
    principal_short_seen = False
    short_number = None
    for alloc in settlement.allocations:
        if principal_short_seen:
            assert alloc.principal_allocated.is_zero(), (
                f"Installment #{alloc.installment_number} received "
                f"{alloc.principal_allocated} in principal but installment "
                f"#{short_number} still owes principal — principal must not "
                "leak to newer installments"
            )
        inst = inst_by_number.get(alloc.installment_number)
        if inst is None:
            continue
        principal_remaining = inst.expected_principal - inst.principal_paid
        if principal_remaining.is_positive():
            principal_short_seen = True
            short_number = alloc.installment_number


# ── Deterministic reproduction ──────────────────────────────────────


def test_high_mora_does_not_cover_later_installment_before_earlier():
    """When mora consumes most of a payment, earlier installments must be
    covered before later ones.  Reproduces the bug where installment #3
    was marked is_fully_covered=True while #2 remained False.
    """
    loan = BillingCycleLoan(
        principal=Money("6554.31"),
        interest_rate=InterestRate("1.99% a.m."),
        billing_cycle=MonthlyBillingCycle(
            due_dates=[
                date(2025, 2, 3),
                date(2025, 3, 3),
                date(2025, 4, 3),
                date(2025, 5, 3),
                date(2025, 6, 3),
                date(2025, 7, 3),
            ]
        ),
        start_date=datetime(2025, 1, 21, tzinfo=SAO_PAULO),
        num_installments=6,
        disbursement_date=datetime(2025, 1, 21, tzinfo=SAO_PAULO),
        scheduler=PriceScheduler,
        mora_interest_rate=InterestRate("1.99% a.m."),
        mora_rate_resolver=_resolve_high_mora_rate,
        fine_rate=InterestRate("2% a.m."),
        tz=SAO_PAULO,
        working_day_calendar=BrazilianWorkingDayCalendar(),
    )

    payments = [
        (datetime(2025, 2, 3, tzinfo=SAO_PAULO), Money("1156.22")),
        (datetime(2025, 5, 2, tzinfo=SAO_PAULO), Money("1156.22")),
        (datetime(2025, 6, 2, tzinfo=SAO_PAULO), Money("1156.22")),
        (datetime(2025, 7, 2, tzinfo=SAO_PAULO), Money("1156.22")),
    ]

    all_settlements: List[tuple] = []
    for pay_date, amount in payments:
        with Warp(loan, pay_date) as w:
            settlement = w.pay_installment(amount)
            all_settlements.append((settlement, list(w.installments)))
        loan = w

    for settlement, installments in all_settlements:
        _assert_sequential_coverage(settlement, installments)


# ── Property-based: single payment at any time ──────────────────────


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
    payment_fraction=payment_fraction_st,
    days_offset=days_offset_st,
)
@settings(max_examples=200)
def test_single_payment_coverage_always_sequential(
    principal, annual_rate, num_installments, scheduler, payment_fraction, days_offset
):
    """A single payment — early, on-time, or late — must never leak
    principal past a principal-uncovered installment.
    """
    loan = build_loan(principal, annual_rate, num_installments, scheduler)
    due_date_dt = datetime(
        loan.due_dates[0].year,
        loan.due_dates[0].month,
        loan.due_dates[0].day,
        tzinfo=timezone.utc,
    )
    pay_dt = due_date_dt + timedelta(days=days_offset)
    if pay_dt <= DISBURSEMENT:
        return

    with Warp(loan, pay_dt) as warped:
        amount = make_payment_amount(warped.current_balance, payment_fraction)
        if amount.is_zero() or amount.is_negative():
            return
        settlement = warped.pay_installment(amount)
        installments = list(warped.installments)

    _assert_sequential_coverage(settlement, installments)


# ── Property-based: multiple payments, varying timing ───────────────


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=st.integers(min_value=2, max_value=8),
    scheduler=scheduler_st,
    payment_days=st.lists(
        st.integers(min_value=20, max_value=400),
        min_size=2,
        max_size=5,
        unique=True,
    ).map(sorted),
    fractions=st.lists(
        st.floats(min_value=0.10, max_value=1.0),
        min_size=5,
        max_size=5,
    ),
)
@settings(max_examples=200)
def test_multiple_payments_coverage_always_sequential(
    principal, annual_rate, num_installments, scheduler, payment_days, fractions
):
    """Multiple payments spread across the loan lifetime — principal
    must never leak past a principal-uncovered installment in any
    settlement, regardless of how many payments are made or when they
    land.
    """
    loan = build_loan(principal, annual_rate, num_installments, scheduler)

    all_settlements: List[tuple] = []
    for i, day_offset in enumerate(payment_days):
        pay_dt = DISBURSEMENT + timedelta(days=day_offset)

        with Warp(loan, pay_dt) as warped:
            balance = warped.current_balance
            if balance.is_zero() or balance.is_negative():
                break
            amount = make_payment_amount(balance, fractions[i])
            if amount.is_zero() or amount.is_negative():
                continue
            settlement = warped.pay_installment(amount)
            all_settlements.append((settlement, list(warped.installments)))
        loan = warped

    for settlement, installments in all_settlements:
        _assert_sequential_coverage(settlement, installments)
