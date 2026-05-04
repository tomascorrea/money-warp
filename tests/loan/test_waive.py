"""Tests for waiving fines and mora interest on loan payments."""

from datetime import date, datetime, timezone
from decimal import Decimal

from money_warp import InterestRate, Loan, Money, Warp


def test_waive_fines_zeroes_fine_balance():
    """Paying late with waive_fines=True should result in zero fine balance."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("11000.00"), waive_fines=True)
        settlement = warped.settlements[-1]

    assert settlement.fine_paid == Money.zero()
    assert warped.fine_balance == Money.zero()


def test_waive_fines_redirects_money_to_other_components():
    """When fines are waived, the full payment goes to mora, interest, and principal."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("11000.00"), waive_fines=True)
        settlement = warped.settlements[-1]

    total_allocated = settlement.fine_paid + settlement.interest_paid + settlement.mora_paid + settlement.principal_paid
    assert settlement.fine_paid == Money.zero()
    assert settlement.principal_paid > Money.zero()
    assert total_allocated == settlement.payment_amount


def test_waive_mora_zeroes_mora_allocation():
    """Paying late with waive_mora=True should result in zero mora paid."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("11000.00"), waive_mora=True)
        settlement = warped.settlements[-1]

    assert settlement.mora_paid == Money.zero()
    assert settlement.interest_paid > Money.zero()


def test_waive_mora_redirects_money_to_principal():
    """When mora is waived, money that would go to mora goes to principal instead."""
    loan_with_mora = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    loan_waived = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    payment = Money("11000.00")
    payment_dt = datetime(2025, 2, 15, tzinfo=timezone.utc)

    with Warp(loan_with_mora, payment_dt) as warped:
        warped.pay_installment(payment)
        s_with = warped.settlements[-1]

    with Warp(loan_waived, payment_dt) as warped:
        warped.pay_installment(payment, waive_mora=True)
        s_waived = warped.settlements[-1]

    assert s_waived.principal_paid > s_with.principal_paid
    assert s_waived.mora_paid == Money.zero()


def test_waive_both_fines_and_mora():
    """Waiving both fines and mora should allocate entire payment to interest + principal."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("11000.00"), waive_fines=True, waive_mora=True)
        settlement = warped.settlements[-1]

    assert settlement.fine_paid == Money.zero()
    assert settlement.mora_paid == Money.zero()
    assert settlement.interest_paid > Money.zero()
    assert settlement.principal_paid > Money.zero()


def test_waive_fines_snapshot_future_fines_still_accrue():
    """After waiving fines on one payment, a later late payment still triggers new fines."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    first = loan.record_payment(
        Money("5500.00"),
        datetime(2025, 2, 15, tzinfo=timezone.utc),
        waive_fines=True,
    )
    assert first.fines_waived > Money.zero()
    assert first.fine_paid == Money.zero()

    second = loan.record_payment(
        Money("5500.00"),
        datetime(2025, 3, 15, tzinfo=timezone.utc),
    )
    assert second.fine_paid > Money.zero()


def test_settlement_records_waived_fine_amounts():
    """Settlement.fines_waived should contain the amount of forgiven fines."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    scheduled_payment = loan.get_expected_payment_amount(date(2025, 2, 1))
    expected_fine = Money(scheduled_payment.raw_amount * Decimal("0.05"))

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("11000.00"), waive_fines=True)
        settlement = warped.settlements[-1]

    assert settlement.fines_waived == expected_fine
    assert settlement.fine_paid == Money.zero()


def test_settlement_records_waived_mora_amounts():
    """Settlement.mora_waived should contain the accrued mora that was forgiven."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    daily_rate = InterestRate("6% a").to_daily().as_decimal()
    regular_interest = Decimal("10000") * ((1 + daily_rate) ** 31 - 1)
    total_interest = Decimal("10000") * ((1 + daily_rate) ** 45 - 1)
    expected_mora = total_interest - regular_interest

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("11000.00"), waive_mora=True)
        settlement = warped.settlements[-1]

    assert settlement.mora_waived == Money(expected_mora)
    assert settlement.mora_paid == Money.zero()


def test_settlement_no_waiver_has_zero_waived_fields():
    """Without waivers, fines_waived and mora_waived should be zero."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("11000.00"))
        settlement = warped.settlements[-1]

    assert settlement.fines_waived == Money.zero()
    assert settlement.mora_waived == Money.zero()


def test_waive_fines_no_fines_is_noop():
    """Waiving fines when none exist should be harmless."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    loan.record_payment(
        Money("10500.00"),
        datetime(2025, 2, 1, tzinfo=timezone.utc),
        waive_fines=True,
    )
    settlement = loan.settlements[-1]

    assert settlement.fine_paid == Money.zero()
    assert settlement.fines_waived == Money.zero()


def test_waive_mora_no_mora_is_noop():
    """Waiving mora when payment is on time should be harmless."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )

    loan.record_payment(
        Money("10500.00"),
        datetime(2025, 2, 1, tzinfo=timezone.utc),
        waive_mora=True,
    )
    settlement = loan.settlements[-1]

    assert settlement.mora_paid == Money.zero()
    assert settlement.mora_waived == Money.zero()


def test_pay_installment_waive_fines():
    """pay_installment with waive_fines=True should forward the flag."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        settlement = warped.pay_installment(Money("11000.00"), waive_fines=True)

    assert settlement.fine_paid == Money.zero()
    assert settlement.fines_waived > Money.zero()


def test_record_payment_waive_flags():
    """record_payment should accept and honor waive flags."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    loan.calculate_late_fines(datetime(2025, 2, 10, tzinfo=timezone.utc))

    settlement = loan.record_payment(
        Money("11000.00"),
        datetime(2025, 2, 15, tzinfo=timezone.utc),
        waive_fines=True,
        waive_mora=True,
    )

    assert settlement.fine_paid == Money.zero()
    assert settlement.mora_paid == Money.zero()
    assert settlement.fines_waived > Money.zero()
    assert settlement.mora_waived > Money.zero()


def test_anticipate_payment_waive_flags():
    """anticipate_payment should forward waiver flags to record_payment."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    loan.calculate_late_fines(datetime(2025, 2, 10, tzinfo=timezone.utc))

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        settlement = warped.anticipate_payment(
            Money("11000.00"),
            installments=[1, 2],
            waive_fines=True,
            waive_mora=True,
        )

    assert settlement.fine_paid == Money.zero()
    assert settlement.mora_paid == Money.zero()
    assert settlement.fines_waived > Money.zero()
