"""Tests for waiving fines and mora interest on billing-cycle loan payments."""

from datetime import datetime, timezone

from money_warp import BillingCycleLoan, InterestRate, Money, Warp
from money_warp.billing_cycle import MonthlyBillingCycle


def test_waive_fines_zeroes_fine_balance(simple_loan):
    """Late payment with waive_fines=True should result in zero fine paid."""
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 4, tzinfo=timezone.utc),
        waive_fines=True,
    )
    assert s.fine_paid == Money.zero()
    assert s.fines_waived == Money("20.45")
    assert simple_loan.fine_balance == Money.zero()


def test_waive_mora_zeroes_mora_allocation(simple_loan):
    """Late payment with waive_mora=True should result in zero mora paid."""
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 4, tzinfo=timezone.utc),
        waive_mora=True,
    )
    assert s.mora_paid == Money.zero()
    assert s.mora_waived == Money("18.93")


def test_waive_both_fines_and_mora(simple_loan):
    """Waiving both should allocate all payment to interest and principal."""
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 4, tzinfo=timezone.utc),
        waive_fines=True,
        waive_mora=True,
    )
    assert s.fine_paid == Money.zero()
    assert s.mora_paid == Money.zero()
    assert s.interest_paid > Money.zero()
    assert s.principal_paid > Money.zero()


def test_waive_fines_more_goes_to_principal(simple_loan):
    """When fines are waived, more of the payment goes to principal."""
    s_waived = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 4, tzinfo=timezone.utc),
        waive_fines=True,
    )
    assert s_waived.principal_paid > Money("943.82")


def test_settlement_no_waiver_has_zero_waived_fields(simple_loan):
    """Without waivers, waived fields should be zero."""
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 3, 4, tzinfo=timezone.utc),
    )
    assert s.fines_waived == Money.zero()
    assert s.mora_waived == Money.zero()


def test_waive_fines_no_fines_is_noop(simple_loan):
    """Waiving fines on an on-time payment should be harmless."""
    s = simple_loan.record_payment(
        Money("1022.58"),
        datetime(2025, 2, 12, tzinfo=timezone.utc),
        waive_fines=True,
    )
    assert s.fine_paid == Money.zero()
    assert s.fines_waived == Money.zero()


def test_pay_installment_waive_flags(simple_loan):
    """pay_installment should forward waiver flags to record_payment."""
    with Warp(simple_loan, datetime(2025, 3, 4, tzinfo=timezone.utc)) as warped:
        s = warped.pay_installment(Money("1022.58"), waive_fines=True, waive_mora=True)

    assert s.fine_paid == Money.zero()
    assert s.mora_paid == Money.zero()
    assert s.fines_waived > Money.zero()
    assert s.mora_waived > Money.zero()


def test_pay_installment_waive_overdue_interest():
    """pay_installment with waive_overdue_interest=True should waive post-due regular interest."""
    bcl = BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        grace_period_days=30,
    )
    scheduled = bcl.get_original_schedule().entries[0].payment_amount

    with Warp(bcl, datetime(2025, 3, 4, tzinfo=timezone.utc)) as warped:
        s = warped.pay_installment(scheduled, waive_overdue_interest=True)

    assert s.overdue_interest_waived > Money.zero()


def test_overdue_interest_balance_on_bcl():
    """overdue_interest_balance should work on BillingCycleLoan."""
    bcl = BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        grace_period_days=30,
    )

    with Warp(bcl, datetime(2025, 3, 4, tzinfo=timezone.utc)) as warped:
        assert warped.overdue_interest_balance > Money.zero()
        assert warped.overdue_interest_balance <= warped.interest_balance
