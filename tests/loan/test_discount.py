"""Tests for flat-amount discount on loan payments."""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money, Warp
from money_warp.billing_cycle_loan import BillingCycleLoan
from money_warp.billing_cycle import MonthlyBillingCycle


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
    """On-time payment with discount absorbs interest, more goes to principal."""
    no_discount = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    payment = Money("10500.00")
    payment_dt = datetime(2025, 2, 1, tzinfo=timezone.utc)

    with Warp(on_time_loan, payment_dt) as w:
        s_disc = w.pay_installment(payment, discount=Money("50.00"))

    with Warp(no_discount, payment_dt) as w:
        s_plain = w.pay_installment(payment)

    assert s_disc.principal_paid > s_plain.principal_paid
    assert s_disc.interest_paid < s_plain.interest_paid


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
    """Discount reduces fines before touching mora or interest."""
    with Warp(late_loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_plain = w.pay_installment(Money("11000.00"))

    late_loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(late_loan_disc, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_disc = w.pay_installment(Money("11000.00"), discount=s_plain.fine_paid)

    assert s_disc.fine_paid == Money.zero()
    assert s_disc.principal_paid > s_plain.principal_paid


def test_discount_absorbs_fines_then_mora(late_loan):
    """Discount larger than fines spills into mora."""
    with Warp(late_loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_plain = w.pay_installment(Money("11000.00"))

    fine_plus_mora = s_plain.fine_paid + s_plain.mora_paid

    late_loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(late_loan_disc, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_disc = w.pay_installment(Money("11000.00"), discount=fine_plus_mora)

    assert s_disc.fine_paid == Money.zero()
    assert s_disc.mora_paid == Money.zero()
    assert s_disc.interest_paid > Money.zero()


def test_discount_zeroes_fine_balance(late_loan):
    """After discount absorbs all fines, fine_balance is zero."""
    with Warp(late_loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_plain = w.pay_installment(Money("11000.00"))

    late_loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(late_loan_disc, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        w.pay_installment(Money("11000.00"), discount=s_plain.fine_paid)
        assert w.fine_balance == Money.zero()


# --- Discount combined with waivers ---


def test_discount_with_waive_fines(late_loan):
    """When fines are waived, discount starts from mora."""
    with Warp(late_loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_plain = w.pay_installment(Money("11000.00"))

    late_loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(late_loan_disc, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_disc = w.pay_installment(
            Money("11000.00"),
            waive_fines=True,
            discount=s_plain.mora_paid,
        )

    assert s_disc.fine_paid == Money.zero()
    assert s_disc.mora_paid == Money.zero()
    assert s_disc.fines_waived > Money.zero()


def test_discount_with_waive_both(late_loan):
    """With both waivers, discount starts from interest."""
    late_loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(late_loan_disc, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_disc = w.pay_installment(
            Money("11000.00"),
            waive_fines=True,
            waive_mora=True,
            discount=Money("50.00"),
        )

    assert s_disc.fine_paid == Money.zero()
    assert s_disc.mora_paid == Money.zero()
    assert s_disc.discount_applied == Money("50.00")


# --- Discount reduces principal ---


def test_discount_larger_than_non_principal_reduces_principal():
    """Discount exceeding interest spills into principal reduction."""
    loan_plain = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    loan_disc = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    payment = Money("5100.00")
    payment_dt = datetime(2025, 2, 1, tzinfo=timezone.utc)

    with Warp(loan_plain, payment_dt) as w:
        s_plain = w.pay_installment(payment)

    large_discount = s_plain.interest_paid + Money("100.00")

    with Warp(loan_disc, payment_dt) as w:
        s_disc = w.pay_installment(payment, discount=large_discount)

    assert s_disc.interest_paid == Money.zero()
    assert s_disc.remaining_balance < s_plain.remaining_balance


def test_discount_pays_off_loan_with_smaller_payment():
    """Discount + payment together can pay off the loan with less cash."""
    loan = Loan(
        Money("1000.00"),
        InterestRate("12% annual"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    scheduled = loan.get_expected_payment_amount(date(2025, 2, 1))
    discount = Money("200.00")
    reduced_payment = scheduled - discount

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        w.pay_installment(reduced_payment, discount=discount)
        assert w.is_paid_off


# --- Zero discount ---


def test_zero_discount_is_noop(on_time_loan):
    """Explicit zero discount behaves identically to no discount."""
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

    assert s_zero.interest_paid == s_none.interest_paid
    assert s_zero.principal_paid == s_none.principal_paid
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
    """Discounts on sequential payments accumulate correctly."""
    scheduled = multi_installment_loan.get_original_schedule()
    pmt_1 = scheduled[0].payment_amount
    pmt_2 = scheduled[1].payment_amount

    with Warp(multi_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        s1 = w.pay_installment(pmt_1, discount=Money("5.00"))

    with Warp(multi_installment_loan, datetime(2025, 3, 1, tzinfo=timezone.utc)) as w:
        s2 = w.pay_installment(pmt_2, discount=Money("3.00"))

    assert s1.discount_applied == Money("5.00")
    assert s2.discount_applied == Money("3.00")


# --- Discount redirects payment money to principal ---


def test_discount_redirects_to_principal_like_waive(late_loan):
    """Discount on fines has the same principal-boosting effect as waive_fines."""
    with Warp(late_loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_plain = w.pay_installment(Money("11000.00"))

    fine_amount = s_plain.fine_paid

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
        s_disc = w.pay_installment(Money("11000.00"), discount=fine_amount)

    with Warp(loan_waive, datetime(2025, 2, 15, tzinfo=timezone.utc)) as w:
        s_waive = w.pay_installment(Money("11000.00"), waive_fines=True)

    assert s_disc.fine_paid == Money.zero()
    assert s_waive.fine_paid == Money.zero()
    assert s_disc.principal_paid == s_waive.principal_paid


# --- Edge cases ---


def test_discount_exceeding_total_obligation():
    """Discount larger than all obligations doesn't crash and zeroes the balance."""
    loan = Loan(
        Money("1000.00"),
        InterestRate("12% annual"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as w:
        s = w.pay_installment(Money("500.00"), discount=Money("5000.00"))

    assert s.remaining_balance == Money.zero()
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
