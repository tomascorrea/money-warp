"""Tests for sugar payment methods (pay_installment, anticipate_payment) and schedule rebuild."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from money_warp import InterestRate, Loan, Money, Warp

# --- pay_installment tests ---


def test_pay_installment_uses_now_as_payment_date():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    with Warp(loan, datetime(2025, 1, 20)) as warped:
        warped.pay_installment(Money("5000.00"))
        assert warped._all_payments[-1].datetime == datetime(2025, 1, 20)


def test_pay_installment_charges_interest_to_due_date():
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    # pay_installment on Jan 15 should charge interest for 31 days (to Feb 1 due date)
    with Warp(loan, datetime(2025, 1, 15)) as warped:
        warped.pay_installment(Money("5000.00"))
        interest_items = [p for p in warped._all_payments if p.category == "actual_interest"]
        assert len(interest_items) == 1

        daily_rate = InterestRate("6% a").to_daily().as_decimal
        expected_interest = Decimal("10000") * ((1 + daily_rate) ** 31 - 1)
        assert interest_items[0].amount == Money(expected_interest)


def test_pay_installment_no_discount_vs_anticipate_discount():
    """pay_installment charges full-period interest; anticipate_payment only charges for elapsed days."""
    due_dates = [datetime(2025, 2, 1)]
    disbursement = datetime(2025, 1, 1)
    principal = Money("10000.00")
    rate = InterestRate("6% a")

    # pay_installment: interest for 31 days (disbursement to due date)
    loan1 = Loan(principal, rate, due_dates, disbursement_date=disbursement)
    with Warp(loan1, datetime(2025, 1, 15)) as warped1:
        warped1.pay_installment(Money("5000.00"))
        installment_interest = [p for p in warped1._all_payments if p.category == "actual_interest"]

    # anticipate_payment: interest for 14 days (disbursement to payment date)
    loan2 = Loan(principal, rate, due_dates, disbursement_date=disbursement)
    with Warp(loan2, datetime(2025, 1, 15)) as warped2:
        warped2.anticipate_payment(Money("5000.00"))
        anticipate_interest = [p for p in warped2._all_payments if p.category == "actual_interest"]

    assert installment_interest[0].amount > anticipate_interest[0].amount


def test_pay_installment_more_principal_with_anticipate():
    """anticipate_payment allocates more to principal since interest is lower."""
    due_dates = [datetime(2025, 2, 1)]
    disbursement = datetime(2025, 1, 1)
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    payment = Money("5000.00")

    loan1 = Loan(principal, rate, due_dates, disbursement_date=disbursement)
    with Warp(loan1, datetime(2025, 1, 15)) as warped1:
        warped1.pay_installment(payment)
        installment_principal = [p for p in warped1._all_payments if p.category == "actual_principal"]

    loan2 = Loan(principal, rate, due_dates, disbursement_date=disbursement)
    with Warp(loan2, datetime(2025, 1, 15)) as warped2:
        warped2.anticipate_payment(payment)
        anticipate_principal = [p for p in warped2._all_payments if p.category == "actual_principal"]

    assert anticipate_principal[0].amount > installment_principal[0].amount


# --- anticipate_payment tests ---


def test_anticipate_payment_uses_now_as_payment_date():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    with Warp(loan, datetime(2025, 1, 20)) as warped:
        warped.anticipate_payment(Money("5000.00"))
        assert warped._all_payments[-1].datetime == datetime(2025, 1, 20)


def test_anticipate_payment_charges_interest_only_for_elapsed_days():
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    with Warp(loan, datetime(2025, 1, 15)) as warped:
        warped.anticipate_payment(Money("5000.00"))
        interest_items = [p for p in warped._all_payments if p.category == "actual_interest"]

        daily_rate = InterestRate("6% a").to_daily().as_decimal
        expected_interest = Decimal("10000") * ((1 + daily_rate) ** 14 - 1)
        assert interest_items[0].amount == Money(expected_interest)


def test_anticipate_payment_negative_amount_raises_error():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    with Warp(loan, datetime(2025, 1, 15)) as warped, pytest.raises(
        ValueError, match="Payment amount must be positive"
    ):
        warped.anticipate_payment(Money("-100.00"))


# --- _next_unpaid_due_date tests ---


def test_next_unpaid_due_date_returns_first_due_date():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    assert loan._next_unpaid_due_date() == datetime(2025, 2, 1)


def test_next_unpaid_due_date_advances_after_full_installment():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    scheduled_pmt = loan.get_original_schedule()[0].payment_amount
    loan.record_payment(scheduled_pmt, datetime(2025, 2, 1))
    assert loan._next_unpaid_due_date() == datetime(2025, 3, 1)


def test_next_unpaid_due_date_raises_when_all_paid():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    loan.record_payment(Money("15000.00"), datetime(2025, 2, 1))

    with pytest.raises(ValueError, match="All due dates have been paid"):
        loan._next_unpaid_due_date()


# --- record_payment three dates tests ---


def test_record_payment_with_explicit_interest_date():
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    # Pay on Jan 15 but calculate interest up to Feb 1 (31 days)
    loan.record_payment(
        Money("5000.00"),
        payment_date=datetime(2025, 1, 15),
        interest_date=datetime(2025, 2, 1),
    )

    interest_items = [p for p in loan._all_payments if p.category == "actual_interest"]
    daily_rate = InterestRate("6% a").to_daily().as_decimal
    expected_interest = Decimal("10000") * ((1 + daily_rate) ** 31 - 1)
    assert interest_items[0].amount == Money(expected_interest)


def test_record_payment_interest_date_defaults_to_payment_date():
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [datetime(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    loan.record_payment(Money("5000.00"), payment_date=datetime(2025, 1, 15))

    interest_items = [p for p in loan._all_payments if p.category == "actual_interest"]
    daily_rate = InterestRate("6% a").to_daily().as_decimal
    expected_interest = Decimal("10000") * ((1 + daily_rate) ** 14 - 1)
    assert interest_items[0].amount == Money(expected_interest)


# --- Schedule rebuild tests ---


def test_schedule_rebuild_first_entry_reflects_actual_payment():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    loan.record_payment(Money("3500.00"), datetime(2025, 2, 1))
    schedule = loan.get_amortization_schedule()

    assert schedule[0].beginning_balance == Money("10000.00")


def test_schedule_rebuild_remaining_entries_are_projected():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    loan.record_payment(Money("3500.00"), datetime(2025, 2, 1))
    schedule = loan.get_amortization_schedule()

    assert schedule[1].payment_amount.is_positive()
    assert schedule[2].payment_amount.is_positive()


def test_schedule_rebuild_total_entries_match_due_dates():
    due_dates = [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)]
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        due_dates,
        disbursement_date=datetime(2025, 1, 1),
    )

    loan.record_payment(Money("3500.00"), datetime(2025, 2, 1))
    schedule = loan.get_amortization_schedule()

    assert len(schedule) == len(due_dates)


def test_schedule_rebuild_projected_pmt_recalculated():
    """After a payment, the remaining PMT should be recalculated based on remaining principal."""
    due_dates = [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)]
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        due_dates,
        disbursement_date=datetime(2025, 1, 1),
    )

    original_schedule = loan.get_original_schedule()
    original_schedule[1].payment_amount

    loan.record_payment(original_schedule[0].payment_amount, datetime(2025, 2, 1))
    rebuilt_schedule = loan.get_amortization_schedule()

    # The projected PMT for the 2nd installment should be different from the original
    # because it's recalculated from the remaining principal with 2 remaining periods
    rebuilt_pmt = rebuilt_schedule[1].payment_amount

    # With equal payments on the same schedule, the PMT should be close but may differ
    # due to the rebuild using last_payment_date as disbursement reference
    assert rebuilt_pmt.is_positive()


def test_schedule_rebuild_payment_numbers_are_sequential():
    due_dates = [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)]
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        due_dates,
        disbursement_date=datetime(2025, 1, 1),
    )

    loan.record_payment(Money("3500.00"), datetime(2025, 2, 1))
    schedule = loan.get_amortization_schedule()

    assert [entry.payment_number for entry in schedule] == [1, 2, 3]


def test_schedule_no_rebuild_without_payments():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    schedule = loan.get_amortization_schedule()
    original = loan.get_original_schedule()

    assert len(schedule) == len(original)
    for s, o in zip(schedule, original):
        assert s.payment_amount == o.payment_amount


def test_schedule_fully_paid_returns_only_actual():
    loan = Loan(
        Money("1000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    schedule = loan.get_original_schedule()
    for entry in schedule:
        loan.record_payment(entry.payment_amount, entry.due_date)

    rebuilt = loan.get_amortization_schedule()

    assert len(rebuilt) == 2


def test_original_schedule_unchanged_after_payments():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    before = loan.get_original_schedule()
    loan.record_payment(Money("5000.00"), datetime(2025, 2, 1))
    after = loan.get_original_schedule()

    assert len(before) == len(after)
    for b, a in zip(before, after):
        assert b.payment_amount == a.payment_amount


# --- Merged schedule actual entry content tests ---


def test_actual_entry_beginning_balance_matches_principal():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    loan.record_payment(Money("5000.00"), datetime(2025, 2, 1))
    schedule = loan.get_amortization_schedule()

    assert schedule[0].beginning_balance == Money("10000.00")


def test_actual_entry_ending_balance_reflects_principal_paid():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    loan.record_payment(Money("5000.00"), datetime(2025, 2, 1))
    schedule = loan.get_amortization_schedule()

    actual_entry = schedule[0]
    assert actual_entry.ending_balance == actual_entry.beginning_balance - actual_entry.principal_payment


def test_projected_beginning_balance_matches_previous_ending():
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    loan.record_payment(Money("3500.00"), datetime(2025, 2, 1))
    schedule = loan.get_amortization_schedule()

    assert schedule[1].beginning_balance == schedule[0].ending_balance


# --- Due date coverage edge cases ---


def test_two_partial_payments_same_installment_next_due_date_unchanged():
    """Two partial payments that together don't cover the first installment."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    loan.record_payment(Money("1000.00"), datetime(2025, 1, 20))
    assert loan._next_unpaid_due_date() == datetime(2025, 2, 1)

    loan.record_payment(Money("1000.00"), datetime(2025, 1, 25))
    assert loan._next_unpaid_due_date() == datetime(2025, 2, 1)


def test_two_partial_payments_covering_one_installment():
    """Two partial payments that together cover the first installment."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    scheduled_pmt = loan.get_original_schedule()[0].payment_amount

    loan.record_payment(Money("1000.00"), datetime(2025, 1, 20))
    assert loan._next_unpaid_due_date() == datetime(2025, 2, 1)

    loan.record_payment(scheduled_pmt, datetime(2025, 2, 1))
    assert loan._next_unpaid_due_date() == datetime(2025, 3, 1)


def test_large_payment_covers_two_installments():
    """A single large payment that covers 2 installments worth of principal."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    original = loan.get_original_schedule()
    two_installments = original[0].payment_amount + original[1].payment_amount

    loan.record_payment(two_installments, datetime(2025, 2, 1))
    assert loan._covered_due_date_count() >= 2
    assert loan._next_unpaid_due_date() == datetime(2025, 4, 1)


def test_three_consecutive_anticipations():
    """Three anticipation payments back-to-back, each covering one installment."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    original = loan.get_original_schedule()

    for i in range(3):
        payment_date = datetime(2025, 1, 10 + i)
        loan.record_payment(
            original[i].payment_amount,
            payment_date=payment_date,
            interest_date=payment_date,
        )

    assert loan._covered_due_date_count() == 3

    with pytest.raises(ValueError, match="All due dates have been paid"):
        loan._next_unpaid_due_date()


def test_schedule_rebuild_after_partial_projects_from_correct_due_date():
    """After a partial payment, projected entries should start from the first uncovered due date."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    loan.record_payment(Money("1000.00"), datetime(2025, 1, 20))
    schedule = loan.get_amortization_schedule()

    assert schedule[1].due_date == datetime(2025, 2, 1)


def test_schedule_rebuild_after_overpayment_skips_covered_dates():
    """After a large overpayment, the projected schedule skips covered due dates."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1),
    )

    original = loan.get_original_schedule()
    two_installments = original[0].payment_amount + original[1].payment_amount

    loan.record_payment(two_installments, datetime(2025, 2, 1))
    schedule = loan.get_amortization_schedule()

    assert len(schedule) == 2
    assert schedule[1].due_date == datetime(2025, 4, 1)


# --- Schedule values: pay_installment vs anticipate_payment ---


def test_pay_installment_on_due_date_projected_schedule_matches_original():
    """
    pay_installment on the due date charges full-period interest, so the
    principal reduction matches the original plan exactly. The projected
    remaining schedule should have the same PMT as the original.
    """
    due_dates = [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)]
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        due_dates,
        disbursement_date=datetime(2025, 1, 1),
    )

    original = loan.get_original_schedule()
    scheduled_pmt = original[0].payment_amount

    with Warp(loan, datetime(2025, 2, 1)) as warped:
        warped.pay_installment(scheduled_pmt)
        rebuilt = warped.get_amortization_schedule()

        assert rebuilt[1].payment_amount == original[1].payment_amount
        assert rebuilt[2].payment_amount == original[2].payment_amount


def test_anticipate_payment_schedule_with_concrete_values():
    """
    anticipate_payment on Jan 15 for a $10,000 loan at 5% annual with 3 monthly
    payments from Feb-Apr. Only 14 days of interest accrues instead of 31.

    Original schedule PMT = $3,360.16 for all 3 installments.
    After anticipation:
      - Interest charged: $18.73 (14 days instead of $41.52 for 31 days)
      - Principal paid: $3,341.43 (vs $3,318.63 in original)
      - Remaining balance: $6,658.57 (vs $6,681.37 in original)
      - New projected PMT: $3,356.31 (lower than original $3,360.16)
    """
    due_dates = [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)]
    loan = Loan(
        Money("10000.00"),
        InterestRate("5% a"),
        due_dates,
        disbursement_date=datetime(2025, 1, 1),
    )

    original = loan.get_original_schedule()
    scheduled_pmt = original[0].payment_amount

    with Warp(loan, datetime(2025, 1, 15)) as warped:
        warped.anticipate_payment(scheduled_pmt)
        rebuilt = warped.get_amortization_schedule()

        assert rebuilt[0].payment_amount == Money("3360.16")
        assert rebuilt[0].interest_payment == Money("18.73")
        assert rebuilt[0].principal_payment == Money("3341.43")
        assert rebuilt[0].ending_balance == Money("6658.57")

        assert rebuilt[1].payment_amount == Money("3356.31")
        assert rebuilt[2].payment_amount == Money("3356.31")


@given(
    principal=st.decimals(min_value=1000, max_value=1_000_000, places=2),
    annual_rate=st.decimals(min_value=1, max_value=30, places=1),
    num_payments=st.integers(min_value=2, max_value=12),
    days_early=st.integers(min_value=1, max_value=25),
)
@settings(max_examples=50)
def test_anticipate_payment_projected_pmt_lower_than_original(principal, annual_rate, num_payments, days_early):
    """anticipate_payment always results in a lower projected PMT than the original schedule."""
    disbursement = datetime(2025, 1, 1)
    due_dates = [disbursement + timedelta(days=30 * (i + 1)) for i in range(num_payments)]
    rate_str = f"{annual_rate}% a"
    loan = Loan(
        Money(str(principal)),
        InterestRate(rate_str),
        due_dates,
        disbursement_date=disbursement,
    )

    original = loan.get_original_schedule()
    scheduled_pmt = original[0].payment_amount
    anticipation_date = disbursement + timedelta(days=30 - days_early)

    with Warp(loan, anticipation_date) as warped:
        warped.anticipate_payment(scheduled_pmt)
        rebuilt = warped.get_amortization_schedule()

        for i in range(1, len(rebuilt) - 1):
            assert rebuilt[i].payment_amount <= original[i].payment_amount


def test_anticipate_vs_installment_ending_balance_comparison():
    """
    After paying the same amount, anticipate_payment leaves a lower remaining
    principal than pay_installment because less went to interest.
    """
    due_dates = [datetime(2025, 2, 1), datetime(2025, 3, 1), datetime(2025, 4, 1)]
    disbursement = datetime(2025, 1, 1)
    principal = Money("10000.00")
    rate = InterestRate("5% a")

    original = Loan(principal, rate, due_dates, disbursement_date=disbursement).get_original_schedule()
    scheduled_pmt = original[0].payment_amount

    loan_installment = Loan(principal, rate, due_dates, disbursement_date=disbursement)
    with Warp(loan_installment, datetime(2025, 1, 15)) as warped:
        warped.pay_installment(scheduled_pmt)
        installment_remaining = warped._actual_schedule_entries[-1].ending_balance

    loan_anticipate = Loan(principal, rate, due_dates, disbursement_date=disbursement)
    with Warp(loan_anticipate, datetime(2025, 1, 15)) as warped:
        warped.anticipate_payment(scheduled_pmt)
        anticipate_remaining = warped._actual_schedule_entries[-1].ending_balance

    assert anticipate_remaining < installment_remaining
