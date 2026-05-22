"""Regression test for the bug where Installment.is_fully_paid ignored
the discount applied to a payment.

When ``pay_installment(amount, discount=...)`` is called and
``amount + discount`` exactly covers ``expected_payment``, the per-
installment view used to report ``balance > 0`` and ``is_fully_paid is
False`` even though the loan-level ``remaining_balance`` was correct
and ``Settlement.discount_applied`` recorded the discount.

The root cause was that ``_apply_waivers_and_discounts`` shrank the
loan-level fine / mora / interest caps by the discount portion they
consumed without recording that portion on the per-installment
``Allocation``. The installment therefore saw only the cash payment in
``*_paid`` and considered the discounted residual still owed.
"""

from datetime import date, datetime

from money_warp import (
    BillingCycleLoan,
    InterestRate,
    Money,
    MonthlyBillingCycle,
    PriceScheduler,
    Warp,
)


def test_installment_is_fully_paid_when_amount_plus_discount_equals_expected():
    """Amount + discount == expected_payment must mark the installment fully paid.

    The reproducer is a 2-installment BCL whose first installment is
    paid with R$2.58 plus a R$0.02 discount, equal to its R$2.60
    scheduled payment. Before the fix, ``inst.balance`` was R$0.02 and
    ``inst.is_fully_paid`` was ``False``; the allocation flag was kept
    in sync and therefore also wrong.
    """
    loan = BillingCycleLoan(
        principal=Money("5.04"),
        interest_rate=InterestRate("1.99% a.m."),
        billing_cycle=MonthlyBillingCycle(due_dates=[date(2025, 11, 10), date(2025, 12, 10)]),
        start_date=datetime(2025, 10, 9),
        num_installments=2,
        disbursement_date=datetime(2025, 10, 9),
        scheduler=PriceScheduler,
    )

    expected_payment = loan.get_original_schedule().entries[0].payment_amount
    assert expected_payment == Money("2.60")

    with Warp(loan, datetime(2025, 11, 5)) as warped:
        settlement = warped.pay_installment(
            Money("2.58"),
            discount=Money("0.02"),
            waive_overdue_interest=True,
        )
        inst = warped.installments[0]

        assert settlement.discount_applied == Money("0.02")
        assert Money("2.58") + Money("0.02") == inst.expected_payment

        assert inst.balance == Money.zero(), f"balance={inst.balance}"
        assert inst.is_fully_paid is True
        assert settlement.allocations[0].is_fully_covered is True


def test_loan_level_remaining_balance_unchanged_by_fix():
    """The loan-level ``remaining_balance`` was correct before the fix.

    Pinning the exact value protects against any regression where the
    per-installment fix accidentally double-counts the discount at the
    loan level.
    """
    loan = BillingCycleLoan(
        principal=Money("5.04"),
        interest_rate=InterestRate("1.99% a.m."),
        billing_cycle=MonthlyBillingCycle(due_dates=[date(2025, 11, 10), date(2025, 12, 10)]),
        start_date=datetime(2025, 10, 9),
        num_installments=2,
        disbursement_date=datetime(2025, 10, 9),
        scheduler=PriceScheduler,
    )

    with Warp(loan, datetime(2025, 11, 5)) as warped:
        settlement = warped.pay_installment(
            Money("2.58"),
            discount=Money("0.02"),
            waive_overdue_interest=True,
        )

        assert settlement.principal_paid == Money("2.49")
        assert settlement.interest_paid == Money("0.09")
        assert settlement.remaining_balance == Money("2.55")
