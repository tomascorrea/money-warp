"""Tests for flat-amount discount on billing-cycle loan payments."""

from datetime import datetime, timezone

from money_warp import BillingCycleLoan, InterestRate, Money, Warp
from money_warp.billing_cycle import MonthlyBillingCycle


def _make_simple_bcl() -> BillingCycleLoan:
    return BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


def test_discount_applied_on_record_payment(simple_loan):
    """record_payment with discount records the amount on the settlement."""
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 2, 12, tzinfo=timezone.utc),
        discount=Money("30.00"),
    )
    assert s.discount_applied == Money("30.00")
    assert s.interest_paid == Money("9.38")
    assert s.principal_paid == Money("1013.20")


def test_discount_reduces_interest_on_time(simple_loan):
    """On-time R$10 discount reduces interest from R$39.38 to R$29.38."""
    loan_disc = _make_simple_bcl()
    s = loan_disc.record_payment(
        Money("1022.58"),
        datetime(2025, 2, 12, tzinfo=timezone.utc),
        discount=Money("10.00"),
    )

    assert s.interest_paid == Money("29.38")
    assert s.principal_paid == Money("993.20")


def test_discount_absorbs_fines_late_payment(simple_loan):
    """Late payment discount of R$20.45 absorbs all fines."""
    loan_disc = _make_simple_bcl()
    s = loan_disc.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 4, tzinfo=timezone.utc),
        discount=Money("20.45"),
    )

    assert s.fine_paid == Money("0.00")
    assert s.mora_paid == Money("18.93")
    assert s.interest_paid == Money("39.38")
    assert s.principal_paid == Money("964.27")


def test_pay_installment_forwards_discount(simple_loan):
    """pay_installment passes discount through to record_payment."""
    with Warp(simple_loan, datetime(2025, 2, 12, tzinfo=timezone.utc)) as w:
        s = w.pay_installment(Money("1022.58"), discount=Money("20.00"))

    assert s.discount_applied == Money("20.00")
    assert s.interest_paid == Money("19.38")
    assert s.principal_paid == Money("1003.20")


def test_no_discount_has_zero_field(simple_loan):
    """Without discount, discount_applied is zero and normal allocation applies."""
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 2, 12, tzinfo=timezone.utc),
    )
    assert s.discount_applied == Money.zero()
    assert s.interest_paid == Money("39.38")
    assert s.principal_paid == Money("983.20")
