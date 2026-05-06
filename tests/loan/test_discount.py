"""Tests for flat-amount discount on loan payments."""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money, Warp
from money_warp.billing_cycle import MonthlyBillingCycle
from money_warp.billing_cycle_loan import BillingCycleLoan


@pytest.fixture
def on_time_loan():
    """Single-installment loan for on-time discount tests."""
    return Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def late_loan():
    """Single-installment loan with fine for late discount tests."""
    return Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )


@pytest.fixture
def multi_installment_loan():
    """3-installment loan for multi-payment discount tests."""
    return Loan(
        Money("890.22"),
        InterestRate("15% annual"),
        [
            date(2025, 2, 1),
            date(2025, 3, 1),
            date(2025, 4, 1),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
    )


# --- Discount on on-time payments ---


def test_discount_reduces_interest_on_time(on_time_loan):
    """On-time R$50 discount absorbs all R$49.61 interest, rest to principal."""
    with Warp(on_time_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        s = w.pay_installment(Money("10500.00"), discount=Money("50.00"))

    assert s.interest_paid == Money("0.00")
    assert s.principal_paid == Money("10500.00")
    assert s.discount_applied == Money("50.00")


def test_discount_applied_field_records_amount(on_time_loan):
    """Settlement.discount_applied equals the requested discount."""
    with Warp(on_time_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("10500.00"), discount=Money("100.00"))

    assert settlement.discount_applied == Money("100.00")


def test_no_discount_has_zero_discount_applied(on_time_loan):
    """Without discount, discount_applied is zero."""
    with Warp(on_time_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        settlement = w.pay_installment(Money("10500.00"))

    assert settlement.discount_applied == Money.zero()


# --- Discount on late payments (fines + mora) ---


def test_discount_absorbs_fines_first(late_loan):
    """Discount equal to fine amount zeroes fines, redirects to principal."""
    late_loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(late_loan_disc, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s = w.pay_installment(Money("11000.00"), discount=Money("502.48"))

    assert s.fine_paid == Money("0.00")
    assert s.mora_paid == Money("22.49")
    assert s.interest_paid == Money("49.61")
    assert s.principal_paid == Money("10927.90")


def test_discount_absorbs_fines_then_mora(late_loan):
    """Discount equal to fines + mora zeroes both components."""
    late_loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(late_loan_disc, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s = w.pay_installment(Money("11000.00"), discount=Money("524.97"))

    assert s.fine_paid == Money("0.00")
    assert s.mora_paid == Money("0.00")
    assert s.interest_paid == Money("49.61")
    assert s.principal_paid == Money("10950.39")


def test_discount_zeroes_fine_balance(late_loan):
    """After discount absorbs all fines, fine_balance is zero."""
    late_loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(late_loan_disc, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("11000.00"), discount=Money("502.48"))
        assert w.fine_balance == Money.zero()


# --- Discount combined with waivers ---


def test_discount_with_waive_fines(late_loan):
    """Fines waived, discount absorbs mora. All goes to interest + principal."""
    late_loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(late_loan_disc, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s = w.pay_installment(
            Money("11000.00"),
            waive_fines=True,
            discount=Money("22.49"),
        )

    assert s.fine_paid == Money("0.00")
    assert s.mora_paid == Money("0.00")
    assert s.interest_paid == Money("49.61")
    assert s.principal_paid == Money("10950.39")
    assert s.fines_waived == Money("502.48")


def test_discount_with_waive_both(late_loan):
    """Both waivers active, R$50 discount absorbs interest."""
    late_loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(late_loan_disc, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s = w.pay_installment(
            Money("11000.00"),
            waive_fines=True,
            waive_mora=True,
            discount=Money("50.00"),
        )

    assert s.fine_paid == Money("0.00")
    assert s.mora_paid == Money("0.00")
    assert s.interest_paid == Money("0.00")
    assert s.principal_paid == Money("11000.00")
    assert s.discount_applied == Money("50.00")


# --- Discount reduces principal ---


def test_discount_larger_than_non_principal_reduces_principal():
    """Discount exceeding interest spills into principal reduction."""
    loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan_disc, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        s = w.pay_installment(Money("5100.00"), discount=Money("149.61"))

    assert s.interest_paid == Money("0.00")
    assert s.principal_paid == Money("5100.00")
    assert s.remaining_balance == Money("4800.00")


def test_discount_pays_off_loan_with_smaller_payment():
    """R$200 discount + R$809.67 payment covers R$1009.67 scheduled amount."""
    loan = Loan(
        Money("1000.00"),
        InterestRate("12% annual"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("809.67"), discount=Money("200.00"))
        assert w.is_paid_off


# --- Zero discount ---


def test_zero_discount_is_noop(on_time_loan):
    """Explicit zero discount produces same result as no discount."""
    no_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    payment = Money("10500.00")
    payment_dt = datetime(2025, 2, 1, tzinfo=timezone.utc)

    with Warp(on_time_loan, payment_dt) as w:
        s_zero = w.pay_installment(payment, discount=Money.zero())

    with Warp(no_disc, payment_dt) as w:
        s_none = w.pay_installment(payment)

    assert s_zero.interest_paid == Money("49.61")
    assert s_none.interest_paid == Money("49.61")
    assert s_zero.principal_paid == Money("10450.39")
    assert s_none.principal_paid == Money("10450.39")
    assert s_zero.discount_applied == Money.zero()


# --- Payment methods forward discount ---


def test_record_payment_accepts_discount(on_time_loan):
    """record_payment passes discount to the settlement engine."""
    settlement = on_time_loan.record_payment(
        Money("10500.00"),
        datetime(2025, 2, 1, tzinfo=timezone.utc),
        discount=Money("50.00"),
    )

    assert settlement.discount_applied == Money("50.00")
    assert settlement.interest_paid == Money("0.00")
    assert settlement.principal_paid == Money("10500.00")


def test_anticipate_payment_accepts_discount():
    """anticipate_payment forwards discount to record_payment."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as w:
        settlement = w.anticipate_payment(
            Money("10500.00"),
            installments=[1, 2],
            discount=Money("75.00"),
        )

    assert settlement.discount_applied == Money("75.00")


# --- Multiple payments with discount ---


def test_multiple_payments_with_discount(multi_installment_loan):
    """Discounts on sequential payments produce correct allocations."""
    with Warp(multi_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        s1 = w.pay_installment(Money("303.62"), discount=Money("5.00"))

    assert s1.discount_applied == Money("5.00")
    assert s1.interest_paid == Money("5.63")
    assert s1.principal_paid == Money("297.99")

    with Warp(multi_installment_loan, datetime(2025, 3, 1, tzinfo=timezone.utc)) as w:
        s2 = w.pay_installment(Money("303.62"), discount=Money("3.00"))

    assert s2.discount_applied == Money("3.00")
    assert s2.interest_paid == Money("17.07")
    assert s2.principal_paid == Money("273.77")


# --- Discount redirects payment money to principal ---


def test_discount_redirects_to_principal_like_waive(late_loan):
    """Discount on fines produces identical allocation as waive_fines."""
    loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )
    loan_waive = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(loan_disc, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_disc = w.pay_installment(Money("11000.00"), discount=Money("502.48"))

    with Warp(loan_waive, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_waive = w.pay_installment(Money("11000.00"), waive_fines=True)

    assert s_disc.fine_paid == Money("0.00")
    assert s_waive.fine_paid == Money("0.00")
    assert s_disc.principal_paid == Money("10927.90")
    assert s_waive.principal_paid == Money("10927.90")


# --- Edge cases ---


def test_discount_exceeding_total_obligation():
    """Discount larger than all obligations zeroes the balance."""
    loan = Loan(
        Money("1000.00"),
        InterestRate("12% annual"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        s = w.pay_installment(Money("500.00"), discount=Money("5000.00"))

    assert s.remaining_balance == Money("0.00")
    assert s.interest_paid == Money("0.00")
    assert s.principal_paid == Money("500.00")
    assert s.discount_applied == Money("5000.00")


def test_negative_discount_raises_value_error():
    """Negative discount is rejected."""
    loan = Loan(
        Money("1000.00"),
        InterestRate("12% annual"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="Discount amount must not be negative"):
        loan.record_payment(
            Money("500.00"),
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            discount=Money("-10.00"),
        )


def test_negative_discount_rejected_on_bcl():
    """BillingCycleLoan also rejects negative discount."""
    loan = BillingCycleLoan(
        principal=Money("3000.00"),
        interest_rate=InterestRate("12% a"),
        billing_cycle=MonthlyBillingCycle(closing_day=28, payment_due_days=15),
        start_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        num_installments=3,
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(ValueError, match="Discount amount must not be negative"):
        loan.record_payment(
            Money("500.00"),
            datetime(2025, 2, 12, tzinfo=timezone.utc),
            discount=Money("-5.00"),
        )
