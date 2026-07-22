"""Regression tests for issue #102: retroactive fine on installment settled under waiver.

A settlement accepted as full coverage under ``waive_overdue_interest=True``
(cash below the original schedule face, difference discounted) must not be
fined by a later Warp observation just because the cash near the due date
does not reach the face amount.
"""

from datetime import date, datetime, timezone

from money_warp import Money, Warp
from money_warp.engines.fines import compute_fines_at
from money_warp.working_day import WeekendCalendar


def test_waived_settlement_on_penalty_due_is_fully_paid(weekend_due_loan):
    """Sanity: waiver + discount settlement on the penalty due date fully pays installment 1."""
    face = weekend_due_loan.get_original_schedule().entries[0].payment_amount
    shift_interest = weekend_due_loan.interest_rate.accrue(weekend_due_loan.principal, 2)

    with Warp(weekend_due_loan, datetime(2025, 10, 13, tzinfo=timezone.utc)) as warped:
        settlement = warped.pay_installment(
            face - shift_interest,
            discount=shift_interest,
            waive_overdue_interest=True,
        )
        inst1 = warped.installments[0]

    assert settlement.fine_paid == Money.zero()
    assert inst1.is_fully_paid
    assert inst1.expected_fine == Money.zero()


def test_no_retroactive_fine_after_next_cycle_warp(weekend_due_loan):
    """Canonical #102: next-cycle warp must not invent a fine on the settled installment."""
    face = weekend_due_loan.get_original_schedule().entries[0].payment_amount
    shift_interest = weekend_due_loan.interest_rate.accrue(weekend_due_loan.principal, 2)

    with Warp(weekend_due_loan, datetime(2025, 10, 13, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(
            face - shift_interest,
            discount=shift_interest,
            waive_overdue_interest=True,
        )
    loan = warped

    with Warp(loan, datetime(2025, 11, 12, tzinfo=timezone.utc)) as warped:
        inst1 = warped.installments[0]

    assert inst1.expected_fine == Money.zero()


def test_installment_stays_fully_paid_after_next_cycle_warp(weekend_due_loan):
    """Canonical #102: the settled installment must not be reopened by a later warp."""
    face = weekend_due_loan.get_original_schedule().entries[0].payment_amount
    shift_interest = weekend_due_loan.interest_rate.accrue(weekend_due_loan.principal, 2)

    with Warp(weekend_due_loan, datetime(2025, 10, 13, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(
            face - shift_interest,
            discount=shift_interest,
            waive_overdue_interest=True,
        )
    loan = warped

    with Warp(loan, datetime(2025, 11, 12, tzinfo=timezone.utc)) as warped:
        inst1 = warped.installments[0]

    assert inst1.is_fully_paid
    assert inst1.balance == Money.zero()


def test_truly_unpaid_installment_still_fined(weekend_due_loan):
    """Guardrail: with no payment at all, the first late observation creates the fine."""
    with Warp(weekend_due_loan, datetime(2025, 11, 12, tzinfo=timezone.utc)) as warped:
        inst1 = warped.installments[0]

    assert inst1.expected_fine > Money.zero()


def test_payment_on_first_late_day_still_creates_fine(weekend_due_loan):
    """Guardrail: a late payment event first materialises the fine, then allocates into it."""
    face = weekend_due_loan.get_original_schedule().entries[0].payment_amount

    with Warp(weekend_due_loan, datetime(2025, 10, 14, tzinfo=timezone.utc)) as warped:
        settlement = warped.pay_installment(face + Money("300"))

    assert settlement.fine_paid > Money.zero()


def test_underpaid_near_due_still_fined(weekend_due_loan):
    """Guardrail: a materially insufficient payment near the due date does not block the fine."""
    with Warp(weekend_due_loan, datetime(2025, 10, 13, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("4000"), waive_overdue_interest=True)
    loan = warped

    with Warp(loan, datetime(2025, 11, 12, tzinfo=timezone.utc)) as warped:
        inst1 = warped.installments[0]

    assert inst1.expected_fine > Money.zero()


def test_prepaid_installment_not_fined(weekend_due_loan):
    """An installment fully prepaid before the proximity window must not be fined later."""
    face = weekend_due_loan.get_original_schedule().entries[0].payment_amount

    with Warp(weekend_due_loan, datetime(2025, 10, 1, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(face)
    loan = warped

    with Warp(loan, datetime(2025, 11, 12, tzinfo=timezone.utc)) as warped:
        inst1 = warped.installments[0]

    assert inst1.expected_fine == Money.zero()


def test_settled_due_dates_after_as_of_are_ignored(weekend_due_loan_3):
    """Future dues in settled_due_dates do not exempt an earlier unpaid installment.

    Prepayment can put not-yet-due dates into principal_covered_count; the
    time-machine date (as_of) must drop those before applying the exemption,
    otherwise the set lies about what has settled under the warped clock.
    An unpaid past due must still be fined when only future dues are marked settled.
    """
    schedule = weekend_due_loan_3.get_original_schedule()
    as_of = datetime(2025, 10, 14, tzinfo=timezone.utc)
    future_only = {date(2025, 11, 11), date(2025, 12, 11)}

    fines = compute_fines_at(
        as_of,
        weekend_due_loan_3.due_dates,
        schedule,
        weekend_due_loan_3.fine_rate,
        weekend_due_loan_3.grace_period_days,
        {},
        [],
        timezone.utc,
        WeekendCalendar(),
        settled_due_dates=future_only,
    )

    assert date(2025, 10, 11) in fines
    assert date(2025, 11, 11) not in fines
    assert date(2025, 12, 11) not in fines


def test_no_cascade_into_later_installments(weekend_due_loan_3):
    """Guardrail: installments 2 and 3 settle with no shortfall/mora from a retroactive fine on #1."""
    schedule = weekend_due_loan_3.get_original_schedule()
    face1 = schedule.entries[0].payment_amount
    face2 = schedule.entries[1].payment_amount
    face3 = schedule.entries[2].payment_amount
    shift_interest = weekend_due_loan_3.interest_rate.accrue(weekend_due_loan_3.principal, 2)

    with Warp(weekend_due_loan_3, datetime(2025, 10, 13, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(
            face1 - shift_interest,
            discount=shift_interest,
            waive_overdue_interest=True,
        )
    loan = warped

    with Warp(loan, datetime(2025, 11, 11, tzinfo=timezone.utc)) as warped:
        settlement2 = warped.pay_installment(face2)
        inst1 = warped.installments[0]
        inst2 = warped.installments[1]

    assert settlement2.fine_paid == Money.zero()
    assert inst1.is_fully_paid
    assert inst2.is_fully_paid
    assert inst2.expected_fine == Money.zero()
    assert inst2.expected_mora == Money.zero()
    loan = warped

    with Warp(loan, datetime(2025, 12, 11, tzinfo=timezone.utc)) as warped:
        settlement3 = warped.pay_installment(face3)
        inst3 = warped.installments[2]

    assert settlement3.fine_paid == Money.zero()
    assert settlement3.mora_paid == Money.zero()
    assert inst3.is_fully_paid
    assert inst3.expected_fine == Money.zero()
    assert inst3.expected_mora == Money.zero()
