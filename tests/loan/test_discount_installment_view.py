"""Per-installment consistency tests for ``pay_installment(discount=...)``.

When the cash payment plus the discount exactly covers an installment's
total obligation, the per-installment view must agree with the
loan-level ``remaining_balance``:

* ``Installment.is_fully_paid`` is ``True``
* ``Installment.balance`` is zero
* ``Allocation.is_fully_covered`` is ``True``

These tests pin that invariant across every discount-target category:
interest, fines, mora, a mix of all three, and a principal-heavy
discount on a tiny installment. The companion test in
``tests/billing_cycle_loan/test_discount_installment_view.py`` covers
the exact reproducer from the bug report on ``BillingCycleLoan``.
"""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money, Warp


def _late_loan() -> Loan:
    """Single-installment loan paid 14 days late.

    Obligations on 2025-02-15 are pinned by
    ``tests/loan/test_discount.py`` and probed independently:
    principal 10_000.00, interest 49.61, mora 22.49, fine 502.48.
    """
    return Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )


def _on_time_loan() -> Loan:
    return Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def test_discount_on_interest_only_makes_installment_fully_paid():
    """Plain ``Loan`` mirror of the BCL regression: discount fills the
    interest gap and the installment becomes fully paid.
    """
    loan = _on_time_loan()
    expected_payment = loan.get_original_schedule().entries[0].payment_amount

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(expected_payment - Money("0.10"), discount=Money("0.10"))
        inst = w.installments[0]

    assert inst.is_fully_paid is True
    assert inst.balance == Money.zero()
    assert inst.interest_discounted == Money("0.10")
    assert settlement.allocations[0].is_fully_covered is True


def test_discount_on_fines_only_makes_installment_fully_paid():
    """Discount equal to the accrued fine, payment covers the rest in cash."""
    loan = _late_loan()
    pay_dt = datetime(2025, 2, 15, tzinfo=timezone.utc)

    with Warp(loan, pay_dt) as w:
        settlement = w.pay_installment(
            Money("10072.10"),
            discount=Money("502.48"),
        )
        inst = w.installments[0]

    assert inst.is_fully_paid is True
    assert inst.balance == Money.zero()
    assert inst.fine_discounted == Money("502.48")
    assert inst.fine_paid == Money.zero()
    assert inst.mora_paid == Money("22.49")
    assert inst.interest_paid == Money("49.61")
    assert inst.principal_paid == Money("10000.00")
    assert settlement.allocations[0].is_fully_covered is True
    assert settlement.remaining_balance == Money.zero()


def test_discount_on_mora_only_makes_installment_fully_paid():
    """``waive_fines`` clears the fine, the discount absorbs the accrued mora."""
    loan = _late_loan()
    pay_dt = datetime(2025, 2, 15, tzinfo=timezone.utc)

    with Warp(loan, pay_dt) as w:
        settlement = w.pay_installment(
            Money("10049.61"),
            waive_fines=True,
            discount=Money("22.49"),
        )
        inst = w.installments[0]

    assert inst.is_fully_paid is True
    assert inst.balance == Money.zero()
    assert inst.mora_discounted == Money("22.49")
    assert inst.mora_paid == Money.zero()
    assert inst.interest_paid == Money("49.61")
    assert inst.principal_paid == Money("10000.00")
    assert settlement.allocations[0].is_fully_covered is True
    assert settlement.remaining_balance == Money.zero()


def test_discount_mix_spills_from_fines_through_mora_into_interest():
    """Discount larger than fine + mora consumes the difference from interest."""
    loan = _late_loan()
    pay_dt = datetime(2025, 2, 15, tzinfo=timezone.utc)

    discount = Money("502.48") + Money("22.49") + Money("30.00")
    amount = Money("10000.00") + (Money("49.61") - Money("30.00"))

    with Warp(loan, pay_dt) as w:
        settlement = w.pay_installment(amount, discount=discount)
        inst = w.installments[0]

    assert inst.is_fully_paid is True
    assert inst.balance == Money.zero()
    assert inst.fine_discounted == Money("502.48")
    assert inst.mora_discounted == Money("22.49")
    assert inst.interest_discounted == Money("30.00")
    assert inst.principal_discounted == Money.zero()
    assert inst.interest_paid == Money("19.61")
    assert inst.principal_paid == Money("10000.00")
    assert settlement.allocations[0].is_fully_covered is True
    assert settlement.remaining_balance == Money.zero()


def test_discount_covers_principal_of_tiny_final_installment():
    """A tiny final installment whose principal is mostly covered by discount
    is still marked fully paid.

    The discount is large enough that, after the (effectively zero)
    interest cap is consumed, the leftover spills into
    ``principal_discounted``. With ``amount=$0.01`` and
    ``discount=$0.99``, the entire R$1.00 principal is settled — R$0.01
    in cash, R$0.99 by discount.
    """
    loan = Loan(
        Money("1.00"),
        InterestRate("0.001% annual"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    expected_payment = loan.get_original_schedule().entries[0].payment_amount

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("0.01"), discount=expected_payment - Money("0.01"))
        inst = w.installments[0]

    assert inst.is_fully_paid is True
    assert inst.balance == Money.zero()
    assert inst.principal_discounted.is_positive()
    assert inst.principal_paid + inst.principal_discounted == inst.expected_principal
    assert settlement.allocations[0].is_fully_covered is True
    assert settlement.remaining_balance == Money.zero()


@pytest.mark.parametrize(
    "scenario,amount,discount,waive_fines",
    [
        ("fines", "10072.10", "502.48", False),
        ("mora", "10049.61", "22.49", True),
        ("mix", "10019.61", "554.97", False),
    ],
    ids=["fines_only", "mora_only", "mix_fine_mora_interest"],
)
def test_late_payment_discount_keeps_loan_level_balance_at_zero(
    scenario: str,
    amount: str,
    discount: str,
    waive_fines: bool,
) -> None:
    """The loan-level invariant must hold across every late-payment discount target.

    Independent of how the discount is split per category, ``amount +
    discount`` covers the full obligation, so the loan must be paid off
    and the installment view must agree.
    """
    loan = _late_loan()
    pay_dt = datetime(2025, 2, 15, tzinfo=timezone.utc)

    with Warp(loan, pay_dt) as w:
        settlement = w.pay_installment(
            Money(amount),
            discount=Money(discount),
            waive_fines=waive_fines,
        )
        inst = w.installments[0]

    assert settlement.remaining_balance == Money.zero()
    assert inst.is_fully_paid is True
    assert inst.balance == Money.zero()
    assert settlement.allocations[0].is_fully_covered is True
    assert settlement.discount_applied == Money(discount)
