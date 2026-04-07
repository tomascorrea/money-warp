"""Forward pass and statement builder for billing-cycle loans.

Reuses allocation, distribution, fine, and coverage logic from
:mod:`money_warp.loan.engines`.  The main difference is that the
mora interest rate is resolved per billing cycle via an optional
:class:`MoraRateResolver`.
"""

from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from ..billing_cycle import BaseBillingCycle
from ..interest_rate import InterestRate
from ..loan.engines import (
    InterestCalculator,
    LoanState,
    _build_event_timeline,
    _build_installments_snapshot,
    _skipped_contractual_interest,
    allocate_payment_into_installments,
    compute_fines_at,
    covered_due_date_count,
)
from ..loan.settlement import Settlement
from ..money import Money
from ..scheduler import PaymentSchedule
from .mora_rate_resolver import MoraRateResolver
from .statement import BillingCycleLoanStatement

_COVERAGE_TOLERANCE = Money("0.01")


# ------------------------------------------------------------------
# Mora rate resolution
# ------------------------------------------------------------------


def resolve_mora_rate(
    due_dates: List[date],
    closing_dates: List[datetime],
    current_due: Optional[date],
    base_mora_rate: InterestRate,
    resolver: Optional[MoraRateResolver],
) -> InterestRate:
    """Return the mora rate for the cycle that owns *current_due*.

    Finds the closing date whose due date matches *current_due*,
    then passes it to the resolver.  Falls back to *base_mora_rate*
    when no resolver is provided or the due date cannot be mapped.
    """
    if resolver is None or current_due is None:
        return base_mora_rate

    for i, dd in enumerate(due_dates):
        if dd == current_due and i < len(closing_dates):
            return resolver(closing_dates[i].date(), base_mora_rate)

    return base_mora_rate


# ------------------------------------------------------------------
# Forward pass
# ------------------------------------------------------------------


def compute_state(
    principal: Money,
    interest_calc: InterestCalculator,
    schedule: PaymentSchedule,
    due_dates: List[date],
    closing_dates: List[datetime],
    fine_rate: InterestRate,
    grace_period_days: int,
    disbursement_date: datetime,
    payment_entries: list,
    as_of: datetime,
    base_mora_rate: InterestRate,
    mora_rate_resolver: Optional[MoraRateResolver] = None,
    fine_observation_dates: Optional[List[datetime]] = None,
) -> LoanState:
    """Forward pass adapted for billing-cycle loans.

    Identical to :func:`money_warp.loan.engines.compute_state` except
    that the mora rate is resolved per billing cycle via
    *mora_rate_resolver* instead of using a fixed rate.
    """
    running_principal = principal
    last_payment_date = disbursement_date
    fines_applied: Dict[date, Money] = {}
    fines_paid_total = Money.zero()
    overpaid = Money.zero()
    settlements = []
    allocs_by_number: Dict[int, list] = {}
    processed_payments: list = []

    events = _build_event_timeline(payment_entries, fine_observation_dates)

    for event_dt, is_payment, payment in events:
        if event_dt > as_of:
            break

        fines_applied = compute_fines_at(
            event_dt,
            due_dates,
            schedule,
            fine_rate,
            grace_period_days,
            fines_applied,
            processed_payments,
        )

        if not is_payment:
            continue

        interest_date = (
            payment.interest_date
            if payment.interest_date is not None
            else payment.datetime
        )
        days = max(0, (interest_date.date() - last_payment_date.date()).days)

        covered = covered_due_date_count(running_principal, schedule)
        next_due = due_dates[covered] if covered < len(due_dates) else None

        mora_rate = resolve_mora_rate(
            due_dates, closing_dates, next_due, base_mora_rate, mora_rate_resolver,
        )

        regular, mora = interest_calc.compute_accrued_interest(
            days,
            running_principal,
            next_due,
            last_payment_date,
            mora_rate_override=mora_rate,
        )

        installments = _build_installments_snapshot(
            allocs_by_number,
            running_principal,
            payment.datetime,
            schedule,
            fines_applied,
            interest_calc,
            last_payment_date=last_payment_date,
        )

        skipped = _skipped_contractual_interest(installments, next_due, interest_date.date())
        interest_cap = Money(regular.raw_amount + skipped.raw_amount)

        total_fines = (
            Money(sum(f.raw_amount for f in fines_applied.values()))
            if fines_applied
            else Money.zero()
        )
        fine_balance = total_fines - fines_paid_total
        if fine_balance.is_negative():
            fine_balance = Money.zero()

        fine_paid, mora_paid, interest_paid, principal_paid, allocations = (
            allocate_payment_into_installments(
                payment.amount,
                installments,
                running_principal,
                fine_cap=fine_balance,
                interest_cap=interest_cap,
                mora_cap=mora,
            )
        )

        fines_paid_total = fines_paid_total + fine_paid
        running_principal = running_principal - principal_paid
        if running_principal.is_negative():
            overpaid = overpaid + Money(-running_principal.raw_amount)
            running_principal = Money.zero()
        elif running_principal.is_positive() and running_principal <= _COVERAGE_TOLERANCE:
            running_principal = Money.zero()

        for a in allocations:
            allocs_by_number.setdefault(a.installment_number, []).append(a)

        settlements.append(
            Settlement(
                payment_amount=payment.amount,
                payment_date=payment.datetime,
                fine_paid=fine_paid,
                interest_paid=interest_paid,
                mora_paid=mora_paid,
                principal_paid=principal_paid,
                remaining_balance=running_principal,
                allocations=allocations,
            )
        )

        last_payment_date = payment.datetime
        processed_payments.append(payment)

    return LoanState(
        settlements=settlements,
        principal_balance=running_principal,
        fines_applied=fines_applied,
        fines_paid_total=fines_paid_total,
        last_payment_date=last_payment_date,
        overpaid=overpaid,
    )


# ------------------------------------------------------------------
# Statement builder
# ------------------------------------------------------------------


def build_statements(
    schedule: PaymentSchedule,
    due_dates: List[date],
    closing_dates: List[datetime],
    billing_cycle: BaseBillingCycle,
    settlements: List,
    fines_applied: Dict[date, Money],
    principal: Money,
    base_mora_rate: InterestRate,
    mora_rate_resolver: Optional[MoraRateResolver] = None,
) -> List[BillingCycleLoanStatement]:
    """Build one :class:`BillingCycleLoanStatement` per billing period.

    Walks closing dates, maps each to its schedule entry and
    settlements, and produces a statement showing expected vs actual
    activity for the period.
    """
    result: List[BillingCycleLoanStatement] = []
    running_balance = principal

    schedule_by_due: Dict[date, object] = {}
    for entry in schedule:
        schedule_by_due[entry.due_date] = entry

    settlement_by_date: Dict[date, List] = {}
    for s in settlements:
        key = s.payment_date.date()
        settlement_by_date.setdefault(key, []).append(s)

    for idx, closing_date in enumerate(closing_dates):
        if idx >= len(due_dates):
            break

        dd = due_dates[idx]
        due_dt = billing_cycle.due_date_for(closing_date)
        entry = schedule_by_due.get(dd)

        expected_payment = entry.payment_amount if entry else Money.zero()
        expected_principal = entry.principal_payment if entry else Money.zero()
        expected_interest = entry.interest_payment if entry else Money.zero()

        mora_rate = resolve_mora_rate(
            due_dates, closing_dates, dd, base_mora_rate, mora_rate_resolver,
        )

        fine_charged = fines_applied.get(dd, Money.zero())

        prev_closing = closing_dates[idx - 1] if idx > 0 else None
        payments_received = Money.zero()
        mora_charged = Money.zero()
        for s_list in settlement_by_date.values():
            for s in s_list:
                in_period = (
                    (prev_closing is None or s.payment_date > prev_closing)
                    and s.payment_date <= closing_date
                )
                if in_period:
                    payments_received = payments_received + s.payment_amount
                    mora_charged = mora_charged + s.mora_paid

        opening_balance = running_balance
        running_balance = running_balance - expected_principal
        if running_balance.is_negative():
            running_balance = Money.zero()

        result.append(
            BillingCycleLoanStatement(
                period_number=idx + 1,
                closing_date=closing_date,
                due_date=due_dt,
                opening_balance=opening_balance,
                expected_payment=expected_payment,
                expected_principal=expected_principal,
                expected_interest=expected_interest,
                mora_rate=mora_rate,
                mora_charged=mora_charged,
                fine_charged=fine_charged,
                payments_received=payments_received,
                closing_balance=running_balance,
            )
        )

    return result
