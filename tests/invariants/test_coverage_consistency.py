"""Property-based tests for the coverage-consistency invariant.

Invariant: for every allocation produced by a *late* payment that incurs
mora, ``Allocation.is_fully_covered`` must equal
``Installment.is_fully_paid`` for the targeted installment.

This file pins down the issue-#93 bug class — late payments where mora
or fine consume part of the payment budget — across arbitrary
principals, interest rates, mora rates, and installment counts.
Anticipation, on-time-exact, and partial-payment scenarios involve
separate semantic considerations (scheduled-vs-actual interest gaps
that ``Installment.is_fully_paid`` deliberately surfaces) and are
covered by their own test files.

See: https://github.com/tomascorrea/money-warp/issues/93
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import List

from hypothesis import given, settings
from hypothesis import strategies as st
from zoneinfo import ZoneInfo

from money_warp import (
    BillingCycleLoan,
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
    num_installments_st,
    principal_st,
    scheduler_st,
)

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


# ── Helpers ─────────────────────────────────────────────────────────


def _assert_coverage_matches_fully_paid(settlement: Settlement, installments: List[Installment]) -> None:
    """For every allocation, ``is_fully_covered`` must equal ``is_fully_paid``.

    Both flags read the same underlying fact — "is the targeted
    installment settled by this payment?" — through different code
    paths, so divergence is a bug.
    """
    by_number = {inst.number: inst for inst in installments}
    for alloc in settlement.allocations:
        inst = by_number[alloc.installment_number]
        assert alloc.is_fully_covered == inst.is_fully_paid, (
            f"Installment #{alloc.installment_number}: "
            f"is_fully_covered={alloc.is_fully_covered} "
            f"vs is_fully_paid={inst.is_fully_paid}. "
            f"balance={inst.balance}, "
            f"expected={inst.expected_principal}+{inst.expected_interest}"
            f"+{inst.expected_mora}+{inst.expected_fine}, "
            f"paid={inst.principal_paid}+{inst.interest_paid}"
            f"+{inst.mora_paid}+{inst.fine_paid}"
        )


def _mora_resolver_12pm(reference_date: date, base_rate: InterestRate) -> InterestRate:
    return InterestRate("12% a.m.")


def _build_bcl_with_variable_mora(
    principal: Decimal,
    annual_rate: Decimal,
    num_installments: int,
) -> BillingCycleLoan:
    """Build a ``BillingCycleLoan`` whose mora rate differs from the contract rate.

    The bug at issue #93 only manifests when the per-cycle mora rate
    diverges from the calculator's default. The resolver returns
    12% a.m., which is materially higher than any reasonable contract
    interest rate, guaranteeing the divergence.
    """
    return BillingCycleLoan(
        principal=Money(str(principal)),
        interest_rate=InterestRate(f"{annual_rate}% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        start_date=DISBURSEMENT,
        num_installments=num_installments,
        disbursement_date=DISBURSEMENT,
        scheduler=PriceScheduler,
        fine_rate=InterestRate("2% a.m."),
        mora_rate_resolver=_mora_resolver_12pm,
    )


# ── Deterministic reproduction (issue #93) ──────────────────────────


def test_coverage_matches_fully_paid_for_late_payment_with_variable_mora() -> None:
    """Late payment with a per-cycle mora resolver keeps the flags consistent.

    Reproduces the bug where the installment snapshot built during
    ``compute_state`` used the calculator's default mora rate instead
    of the resolved per-cycle rate, making ``inst.balance``
    underestimate the true obligation. The loan-level allocation then
    flagged the installment as ``is_fully_covered=True`` while the
    post-payment installment view showed ``is_fully_paid=False``.
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
        mora_rate_resolver=_mora_resolver_12pm,
    )

    with Warp(loan, datetime(2026, 1, 7, tzinfo=SAO_PAULO)) as w:
        w.pay_installment(Money("113.40"), waive_overdue_interest=True)
    loan = w

    with Warp(loan, datetime(2026, 2, 11, tzinfo=SAO_PAULO)) as w:
        settlement = w.pay_installment(Money("116.12"), waive_overdue_interest=True)
        _assert_coverage_matches_fully_paid(settlement, w.installments)


# ── Property-based: late payment on a BCL with variable mora ────────


# Payment "shape" relative to the installment's full obligation. We
# stay at or above 1.0 so the customer fully covers the scheduled
# obligation (and possibly more, to cover accrued mora/fine).
# Under-payments are exercised by the deterministic bug reproduction
# above; broader under-payment exploration belongs to its own file.
payment_multiplier_st = st.floats(min_value=1.0, max_value=1.50)

# Days late, well past any grace period and past the first due date.
late_days_st = st.integers(min_value=1, max_value=45)


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    late_days=late_days_st,
    payment_multiplier=payment_multiplier_st,
)
@settings(max_examples=200)
def test_late_payment_coverage_matches_fully_paid_bcl_variable_mora(
    principal: Decimal,
    annual_rate: Decimal,
    num_installments: int,
    late_days: int,
    payment_multiplier: float,
) -> None:
    """Late payment with per-cycle mora must keep flags consistent.

    Exercises the issue-#93 bug class across the parameters the user
    cares about: principal, interest rate, number of installments,
    days late, and how much the customer paid relative to the
    installment's full obligation.
    """
    loan = _build_bcl_with_variable_mora(principal, annual_rate, num_installments)
    first_due_dt = datetime(
        loan.due_dates[0].year,
        loan.due_dates[0].month,
        loan.due_dates[0].day,
        tzinfo=timezone.utc,
    )
    pay_dt = first_due_dt + timedelta(days=late_days)

    schedule = loan.get_original_schedule()
    base = schedule.entries[0].payment_amount.raw_amount
    amount_raw = (base * Decimal(str(payment_multiplier))).quantize(Decimal("0.01"))
    amount = Money(str(amount_raw))
    if amount.is_zero() or amount.is_negative():
        return

    with Warp(loan, pay_dt) as w:
        settlement = w.pay_installment(amount)
        _assert_coverage_matches_fully_paid(settlement, w.installments)


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    late_days=late_days_st,
    payment_multiplier=payment_multiplier_st,
)
@settings(max_examples=200)
def test_late_payment_with_waiver_coverage_matches_fully_paid(
    principal: Decimal,
    annual_rate: Decimal,
    num_installments: int,
    late_days: int,
    payment_multiplier: float,
) -> None:
    """Late payment with ``waive_overdue_interest`` keeps flags consistent.

    The original bug surfaced specifically with
    ``waive_overdue_interest=True`` (Settlement 2 in the issue
    reproduction). This property test broadens that across loan
    parameters.
    """
    loan = _build_bcl_with_variable_mora(principal, annual_rate, num_installments)
    first_due_dt = datetime(
        loan.due_dates[0].year,
        loan.due_dates[0].month,
        loan.due_dates[0].day,
        tzinfo=timezone.utc,
    )
    pay_dt = first_due_dt + timedelta(days=late_days)

    schedule = loan.get_original_schedule()
    base = schedule.entries[0].payment_amount.raw_amount
    amount_raw = (base * Decimal(str(payment_multiplier))).quantize(Decimal("0.01"))
    amount = Money(str(amount_raw))
    if amount.is_zero() or amount.is_negative():
        return

    with Warp(loan, pay_dt) as w:
        settlement = w.pay_installment(amount, waive_overdue_interest=True)
        _assert_coverage_matches_fully_paid(settlement, w.installments)


# ── Property-based: late payment on a plain Loan (constant mora) ────


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=num_installments_st,
    scheduler=scheduler_st,
    late_days=late_days_st,
    payment_multiplier=payment_multiplier_st,
)
@settings(max_examples=200)
def test_late_payment_coverage_matches_fully_paid_loan(
    principal: Decimal,
    annual_rate: Decimal,
    num_installments: int,
    scheduler: type,
    late_days: int,
    payment_multiplier: float,
) -> None:
    """Late payment on a plain ``Loan`` (constant mora rate) keeps the
    flags consistent across principal, rate, term, and scheduler.

    Parallels :func:`test_late_payment_coverage_matches_fully_paid_bcl_variable_mora`
    but without the per-cycle mora resolver — ensures the invariant
    is not BCL-specific.
    """
    loan = build_loan(principal, annual_rate, num_installments, scheduler)
    first_due_dt = datetime(
        loan.due_dates[0].year,
        loan.due_dates[0].month,
        loan.due_dates[0].day,
        tzinfo=timezone.utc,
    )
    pay_dt = first_due_dt + timedelta(days=late_days)

    schedule = loan.get_original_schedule()
    base = schedule.entries[0].payment_amount.raw_amount
    amount_raw = (base * Decimal(str(payment_multiplier))).quantize(Decimal("0.01"))
    amount = Money(str(amount_raw))
    if amount.is_zero() or amount.is_negative():
        return

    with Warp(loan, pay_dt) as w:
        settlement = w.pay_installment(amount)
        _assert_coverage_matches_fully_paid(settlement, w.installments)


# ── Property-based: sequential late payments on a BCL with variable mora


@given(
    principal=principal_st,
    annual_rate=annual_rate_st,
    num_installments=st.integers(min_value=2, max_value=6),
    late_days_list=st.lists(
        st.integers(min_value=1, max_value=30),
        min_size=2,
        max_size=4,
    ),
    payment_multipliers=st.lists(
        payment_multiplier_st,
        min_size=4,
        max_size=4,
    ),
)
@settings(max_examples=100)
def test_sequential_late_payments_coverage_matches_fully_paid(
    principal: Decimal,
    annual_rate: Decimal,
    num_installments: int,
    late_days_list: List[int],
    payment_multipliers: List[float],
) -> None:
    """Sequential late payments must keep flags consistent across every settlement.

    Pay each scheduled installment *late* (after its due date) by an
    amount that fully covers (or slightly overpays) the installment.
    Mora accrues for each one. Every settlement's allocations must
    agree with the installment view at that point.
    """
    loan = _build_bcl_with_variable_mora(principal, annual_rate, num_installments)
    schedule = loan.get_original_schedule()
    captured: List[tuple] = []

    for i, late_days in enumerate(late_days_list):
        if i >= len(loan.due_dates):
            break
        due = loan.due_dates[i]
        pay_dt = datetime(due.year, due.month, due.day, tzinfo=timezone.utc) + timedelta(days=late_days)

        base = schedule.entries[i].payment_amount.raw_amount
        amount_raw = (base * Decimal(str(payment_multipliers[i]))).quantize(Decimal("0.01"))
        amount = Money(str(amount_raw))
        if amount.is_zero() or amount.is_negative():
            continue

        with Warp(loan, pay_dt) as w:
            settlement = w.pay_installment(amount, waive_overdue_interest=True)
            captured.append((settlement, list(w.installments)))
        loan = w

    for settlement, installments in captured:
        _assert_coverage_matches_fully_paid(settlement, installments)
