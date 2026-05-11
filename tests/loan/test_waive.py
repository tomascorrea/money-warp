"""Tests for waiving fines and mora interest on loan payments."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

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


# --- Late payment with waive covers the installment ---


@pytest.fixture
def late_loan():
    """3-installment loan with fine and mora, for coverage tests."""
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


def test_late_without_waive_installment_not_fully_paid(late_loan):
    """Paying the scheduled amount late leaves the installment short due to fines and mora."""
    scheduled = late_loan.get_expected_payment_amount(date(2025, 2, 1))

    with Warp(late_loan, datetime(2025, 2, 16, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(scheduled)
        inst = warped.installments[0]

    assert inst.fine_paid > Money.zero()
    assert not inst.is_fully_paid


def test_late_with_waive_both_installment_fully_paid(late_loan):
    """Same scheduled amount late with both waivers covers the installment fully."""
    scheduled = late_loan.get_expected_payment_amount(date(2025, 2, 1))

    with Warp(late_loan, datetime(2025, 2, 16, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(scheduled, waive_fines=True, waive_mora=True)
        inst = warped.installments[0]
        settlement = warped.settlements[-1]

    assert settlement.fine_paid == Money.zero()
    assert settlement.mora_paid == Money.zero()
    assert inst.is_fully_paid


def test_late_with_waive_fines_more_principal_than_without(late_loan):
    """Waiving fines redirects fine amount to principal."""
    scheduled = late_loan.get_expected_payment_amount(date(2025, 2, 1))

    loan_no_waive = Loan(
        Money("890.22"),
        InterestRate("15% annual"),
        [date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
    )

    with Warp(late_loan, datetime(2025, 2, 16, tzinfo=timezone.utc)) as warped:
        s_waived = warped.pay_installment(scheduled, waive_fines=True)

    with Warp(loan_no_waive, datetime(2025, 2, 16, tzinfo=timezone.utc)) as warped:
        s_normal = warped.pay_installment(scheduled)

    assert s_waived.fine_paid == Money.zero()
    assert s_waived.principal_paid > s_normal.principal_paid


def test_late_with_waive_both_loan_paid_off():
    """Full loan amount late with both waivers pays off a single-installment loan."""
    loan = Loan(
        Money("1000.00"),
        InterestRate("12% annual"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    scheduled = loan.get_expected_payment_amount(date(2025, 2, 1))

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(scheduled, waive_fines=True, waive_mora=True)
        assert warped.is_paid_off


def test_late_without_waive_loan_not_paid_off():
    """Same payment without waivers does not pay off the loan."""
    loan = Loan(
        Money("1000.00"),
        InterestRate("12% annual"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
    )

    scheduled = loan.get_expected_payment_amount(date(2025, 2, 1))

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(scheduled)
        assert not warped.is_paid_off


def test_late_with_waive_covers_more_installments(late_loan):
    """Large late payment with waivers covers more installments than without."""
    with Warp(late_loan, datetime(2025, 2, 16, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("800.00"), waive_fines=True, waive_mora=True)
        covered_waived = [a for a in warped.settlements[-1].allocations if a.is_fully_covered]

    loan_no_waive = Loan(
        Money("890.22"),
        InterestRate("15% annual"),
        [date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
    )

    with Warp(loan_no_waive, datetime(2025, 2, 16, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("800.00"))
        covered_normal = [a for a in warped.settlements[-1].allocations if a.is_fully_covered]

    assert len(covered_waived) >= len(covered_normal)


# --- Overdue interest waiver ---


def _make_single_loan(grace_period_days: int = 30):
    """Single-installment loan for overdue interest tests.

    Uses a grace period so that post-due interest is reclassified from
    mora to regular — the scenario where waive_overdue_interest matters.
    """
    return Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        grace_period_days=grace_period_days,
    )


def test_waive_overdue_interest_late_payment_pays_off():
    """Scheduled amount late with waive_overdue_interest=True pays off the loan."""
    loan = _make_single_loan()
    scheduled = loan.get_expected_payment_amount(date(2025, 2, 1))

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(scheduled, waive_overdue_interest=True)
        assert warped.is_paid_off


def test_waive_overdue_interest_settlement_records_waived_amount():
    """Settlement.overdue_interest_waived should reflect the forgiven interest."""
    loan = _make_single_loan()
    scheduled = loan.get_expected_payment_amount(date(2025, 2, 1))

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        settlement = warped.pay_installment(scheduled, waive_overdue_interest=True)

    assert settlement.overdue_interest_waived > Money.zero()


def test_waive_overdue_interest_interest_matches_scheduled():
    """With overdue interest waived, interest paid should match the on-time amount."""
    loan_waived = _make_single_loan()
    loan_on_time = _make_single_loan()

    scheduled = loan_waived.get_expected_payment_amount(date(2025, 2, 1))

    with Warp(loan_on_time, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        s_on_time = warped.pay_installment(scheduled)

    with Warp(loan_waived, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        s_waived = warped.pay_installment(scheduled, waive_overdue_interest=True)

    assert s_waived.interest_paid == s_on_time.interest_paid


def test_waive_overdue_interest_early_payment_no_effect():
    """Early payment with waive_overdue_interest=True has no effect."""
    loan = _make_single_loan()

    with Warp(loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as warped:
        settlement = warped.pay_installment(Money("11000.00"), waive_overdue_interest=True)

    assert settlement.overdue_interest_waived == Money.zero()


def test_waive_overdue_interest_on_time_payment_no_effect():
    """On-time payment with waive_overdue_interest=True has no effect."""
    loan = _make_single_loan()

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        settlement = warped.pay_installment(Money("11000.00"), waive_overdue_interest=True)

    assert settlement.overdue_interest_waived == Money.zero()


def test_waive_overdue_interest_default_false_preserves_behavior():
    """Default False should not change the settlement."""
    loan_default = _make_single_loan()
    loan_explicit = _make_single_loan()
    scheduled = loan_default.get_expected_payment_amount(date(2025, 2, 1))

    with Warp(loan_default, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        s_default = warped.pay_installment(scheduled)

    with Warp(loan_explicit, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        s_explicit = warped.pay_installment(scheduled, waive_overdue_interest=False)

    assert s_default.interest_paid == s_explicit.interest_paid
    assert s_default.principal_paid == s_explicit.principal_paid
    assert s_default.overdue_interest_waived == Money.zero()


def test_waive_all_three_flags_combined():
    """Combining waive_fines + waive_mora + waive_overdue_interest should pay off the loan."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("5% annual"),
        grace_period_days=30,
    )
    scheduled = loan.get_expected_payment_amount(date(2025, 2, 1))

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        settlement = warped.pay_installment(
            scheduled,
            waive_fines=True,
            waive_mora=True,
            waive_overdue_interest=True,
        )
        assert warped.is_paid_off

    assert settlement.fine_paid == Money.zero()
    assert settlement.mora_paid == Money.zero()
    assert settlement.overdue_interest_waived > Money.zero()


def test_waive_overdue_interest_multi_installment():
    """Overdue interest waiver affects only the current installment."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        grace_period_days=30,
    )
    scheduled_1 = loan.get_expected_payment_amount(date(2025, 2, 1))

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        s1 = warped.pay_installment(scheduled_1, waive_overdue_interest=True)
        assert s1.overdue_interest_waived > Money.zero()
        inst_1 = warped.installments[0]
        assert inst_1.allocations[0].is_fully_covered


def test_waive_overdue_interest_via_record_payment():
    """record_payment should accept and honor waive_overdue_interest."""
    loan = _make_single_loan()
    scheduled = loan.get_expected_payment_amount(date(2025, 2, 1))

    settlement = loan.record_payment(
        scheduled,
        datetime(2025, 2, 15, tzinfo=timezone.utc),
        interest_date=datetime(2025, 2, 15, tzinfo=timezone.utc),
        waive_overdue_interest=True,
    )

    assert settlement.overdue_interest_waived > Money.zero()


# --- Overdue interest balance ---


def test_overdue_interest_balance_positive_when_late():
    """overdue_interest_balance should be positive when past the due date."""
    loan = _make_single_loan()

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        assert warped.overdue_interest_balance > Money.zero()


def test_overdue_interest_balance_zero_when_early():
    """overdue_interest_balance should be zero when before the due date."""
    loan = _make_single_loan()

    with Warp(loan, datetime(2025, 1, 20, tzinfo=timezone.utc)) as warped:
        assert warped.overdue_interest_balance == Money.zero()


def test_overdue_interest_balance_zero_when_on_time():
    """overdue_interest_balance should be zero on the due date."""
    loan = _make_single_loan()

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        assert warped.overdue_interest_balance == Money.zero()


def test_overdue_interest_balance_is_subset_of_interest_balance():
    """overdue_interest_balance should always be <= interest_balance."""
    loan = _make_single_loan()

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        assert warped.overdue_interest_balance <= warped.interest_balance


def test_current_balance_does_not_double_count_overdue():
    """current_balance should not include overdue interest as a separate component."""
    loan = _make_single_loan()

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        expected = (
            warped.principal_balance + warped.interest_balance + warped.mora_interest_balance + warped.fine_balance
        )
        assert warped.current_balance == expected
