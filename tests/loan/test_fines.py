"""Tests for fines and late overpayment allocation."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from money_warp import InterestRate, Loan, Money, Warp


def test_loan_creation_with_fine_parameters():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.03"),
        grace_period_days=5,
    )
    assert loan.fine_rate == Decimal("0.03")
    assert loan.grace_period_days == 5


def test_loan_creation_with_default_fine_parameters():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert loan.fine_rate == Decimal("0.02")  # Default 2%
    assert loan.grace_period_days == 0  # Default no grace period


def test_loan_creation_negative_fine_rate_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    with pytest.raises(ValueError, match="Fine rate must be non-negative"):
        Loan(
            principal,
            rate,
            due_dates,
            disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            fine_rate=Decimal("-0.01"),
        )


def test_loan_creation_negative_grace_period_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    with pytest.raises(ValueError, match="Grace period days must be non-negative"):
        Loan(
            principal,
            rate,
            due_dates,
            disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            grace_period_days=-1,
        )


def test_loan_initial_fine_properties():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    assert loan.total_fines == Money.zero()
    assert loan.outstanding_fines == Money.zero()
    assert len(loan.fines_applied) == 0


def test_loan_get_expected_payment_amount_valid_date():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc), datetime(2024, 3, 1, tzinfo=timezone.utc)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    expected_payment = loan.get_expected_payment_amount(datetime(2024, 2, 1, tzinfo=timezone.utc))
    assert expected_payment > Money.zero()


def test_loan_get_expected_payment_amount_invalid_date_raises_error():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="Due date .* is not in loan's due dates"):
        loan.get_expected_payment_amount(datetime(2024, 3, 1, tzinfo=timezone.utc))


def test_loan_is_payment_late_within_grace_period():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc), grace_period_days=5
    )
    check_date = datetime(2024, 2, 3, tzinfo=timezone.utc)  # 2 days after due date, within grace period
    assert not loan.is_payment_late(datetime(2024, 2, 1, tzinfo=timezone.utc), check_date)


def test_loan_is_payment_late_after_grace_period():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc), grace_period_days=5
    )
    check_date = datetime(2024, 2, 7, tzinfo=timezone.utc)  # 6 days after due date, past grace period
    assert loan.is_payment_late(datetime(2024, 2, 1, tzinfo=timezone.utc), check_date)


def test_loan_is_payment_late_no_grace_period():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc), grace_period_days=0
    )
    check_date = datetime(2024, 2, 2, tzinfo=timezone.utc)  # 1 day after due date
    assert loan.is_payment_late(datetime(2024, 2, 1, tzinfo=timezone.utc), check_date)


def test_loan_calculate_late_fines_applies_fine():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
        grace_period_days=0,
    )
    late_date = datetime(2024, 2, 5, tzinfo=timezone.utc)  # 4 days late

    new_fines = loan.calculate_late_fines(late_date)
    assert new_fines > Money.zero()
    assert loan.total_fines == new_fines


def test_loan_calculate_late_fines_correct_amount():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.05"),
    )  # 5% fine
    expected_payment = loan.get_expected_payment_amount(datetime(2024, 2, 1, tzinfo=timezone.utc))
    expected_fine = Money(expected_payment.raw_amount * Decimal("0.05"))

    loan.calculate_late_fines(datetime(2024, 2, 5, tzinfo=timezone.utc))
    assert loan.total_fines == expected_fine


def test_loan_calculate_late_fines_only_once_per_due_date():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
    )

    # Apply fines twice for same due date
    first_fines = loan.calculate_late_fines(datetime(2024, 2, 5, tzinfo=timezone.utc))
    second_fines = loan.calculate_late_fines(datetime(2024, 2, 10, tzinfo=timezone.utc))

    assert first_fines > Money.zero()
    assert second_fines == Money.zero()  # No new fines applied


def test_loan_calculate_late_fines_multiple_due_dates():
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc), datetime(2024, 3, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
    )

    # Both payments are late
    late_date = datetime(2024, 3, 5, tzinfo=timezone.utc)
    new_fines = loan.calculate_late_fines(late_date)

    assert new_fines > Money.zero()
    assert len(loan.fines_applied) == 2  # Fines for both due dates


def test_loan_record_payment_allocates_to_fines_first():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
    )

    # Apply fines first
    loan.calculate_late_fines(datetime(2024, 2, 5, tzinfo=timezone.utc))
    initial_fines = loan.outstanding_fines

    # Make payment smaller than fines
    payment_amount = Money(initial_fines.raw_amount / 2)
    loan.record_payment(payment_amount, datetime(2024, 2, 6, tzinfo=timezone.utc))

    # Check that payment went to fines
    fine_payments = [p for p in loan._actual_payments if p.category == "actual_fine"]
    assert len(fine_payments) == 1
    assert fine_payments[0].amount == payment_amount


def test_loan_record_payment_allocates_fines_then_principal():
    principal = Money("1000.00")  # Smaller loan for easier testing
    rate = InterestRate("0% a")  # No interest for simplicity
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.10"),
    )  # 10% fine

    # Apply fines
    loan.calculate_late_fines(datetime(2024, 2, 5, tzinfo=timezone.utc))
    total_fines = loan.outstanding_fines

    # Make payment that covers fines + some principal
    payment_amount = total_fines + Money("200")
    loan.record_payment(payment_amount, datetime(2024, 2, 6, tzinfo=timezone.utc))

    # Check allocations
    fine_payments = [p for p in loan._actual_payments if p.category == "actual_fine"]
    principal_payments = [p for p in loan._actual_payments if p.category == "actual_principal"]

    assert len(fine_payments) == 1
    assert fine_payments[0].amount == total_fines
    assert len(principal_payments) == 1
    assert principal_payments[0].amount == Money("200")


def test_loan_current_balance_includes_outstanding_fines():
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
    )
    initial_balance = loan.current_balance

    # Apply fines
    loan.calculate_late_fines(datetime(2024, 2, 5, tzinfo=timezone.utc))
    balance_with_fines = loan.current_balance

    assert balance_with_fines > initial_balance
    assert balance_with_fines == initial_balance + loan.outstanding_fines


def test_loan_is_paid_off_considers_fines():
    principal = Money("1000.00")
    rate = InterestRate("0% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.05"),
    )

    # Make partial payment that doesn't cover full installment
    loan.record_payment(Money("500.00"), datetime(2024, 1, 31, tzinfo=timezone.utc))
    assert not loan.is_paid_off  # Should not be paid off yet

    # Now apply fines for insufficient payment
    loan.calculate_late_fines(datetime(2024, 2, 5, tzinfo=timezone.utc))

    # Should have fines and still not be paid off
    assert loan.outstanding_fines > Money.zero()
    assert not loan.is_paid_off  # Should not be paid off due to outstanding balance and fines


@pytest.mark.parametrize(
    "fine_rate,expected_multiplier",
    [
        (Decimal("0.01"), Decimal("0.01")),  # 1%
        (Decimal("0.05"), Decimal("0.05")),  # 5%
        (Decimal("0.10"), Decimal("0.10")),  # 10%
    ],
)
def test_loan_fine_calculation_with_different_rates(fine_rate, expected_multiplier):
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_dates = [datetime(2024, 2, 1, tzinfo=timezone.utc)]

    loan = Loan(
        principal, rate, due_dates, disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc), fine_rate=fine_rate
    )
    expected_payment = loan.get_expected_payment_amount(datetime(2024, 2, 1, tzinfo=timezone.utc))
    expected_fine = Money(expected_payment.raw_amount * expected_multiplier)

    loan.calculate_late_fines(datetime(2024, 2, 5, tzinfo=timezone.utc))
    assert loan.total_fines == expected_fine


@pytest.mark.parametrize(
    "grace_days,check_day,should_be_late",
    [
        (0, 1, True),  # No grace, 1 day late
        (3, 2, False),  # 3-day grace, 2 days after due date
        (3, 4, True),  # 3-day grace, 4 days after due date
        (5, 5, False),  # 5-day grace, exactly at grace boundary
        (5, 6, True),  # 5-day grace, 1 day past grace
    ],
)
def test_loan_grace_period_scenarios(grace_days, check_day, should_be_late):
    principal = Money("10000.00")
    rate = InterestRate("5% a")
    due_date = datetime(2024, 2, 1, tzinfo=timezone.utc)
    due_dates = [due_date]

    loan = Loan(
        principal,
        rate,
        due_dates,
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        grace_period_days=grace_days,
    )
    check_date = due_date + timedelta(days=check_day)

    assert loan.is_payment_late(due_date, check_date) == should_be_late


def test_pay_installment_late_triggers_fines_and_extra_interest():
    """Late payment should apply both fines and charge interest beyond the due date."""
    principal = Money("10000.00")
    rate = InterestRate("6% a")
    due_date = datetime(2025, 2, 1, tzinfo=timezone.utc)
    disbursement = datetime(2025, 1, 1, tzinfo=timezone.utc)

    loan = Loan(
        principal,
        rate,
        [due_date],
        disbursement_date=disbursement,
        fine_rate=Decimal("0.05"),
    )

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("11000.00"))
        fine_items = [p for p in warped._all_payments if p.category == "actual_fine"]
        interest_items = [p for p in warped._all_payments if p.category == "actual_interest"]
        mora_items = [p for p in warped._all_payments if p.category == "actual_mora_interest"]

    assert len(fine_items) == 1
    assert fine_items[0].amount > Money.zero()
    assert len(interest_items) == 1
    assert interest_items[0].amount > Money.zero()
    assert len(mora_items) == 1
    assert mora_items[0].amount > Money.zero()


# --- Late overpayment covering multiple installments ---
#
# Scenario: $10k loan at 6% annual, disbursed Jan 1, dues Feb 1 / Mar 1 / Apr 1.
# Borrower misses Feb 1, pays $7,000 on Feb 15 (late, 2% fine).
#
# Allocation of the $7,000 payment:
#   1. Fine:      2% of scheduled Feb 1 payment
#   2. Interest:  45 days daily-compounded on full $10k (mora)
#   3. Principal: remainder -> covers installments 1 and 2
#
# After payment, only Apr 1 installment remains.


def test_late_overpayment_fine_equals_two_percent_of_scheduled_payment():
    """Fine = 2% of the original Feb 1 scheduled payment amount."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            datetime(2025, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
    )

    scheduled_payment = loan.get_expected_payment_amount(datetime(2025, 2, 1, tzinfo=timezone.utc))
    expected_fine = Money(scheduled_payment.raw_amount * Decimal("0.02"))

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("7000.00"))
        fine_items = [p for p in warped._all_payments if p.category == "actual_fine"]

    assert fine_items[0].amount == expected_fine


def test_late_overpayment_total_interest_for_45_days():
    """Total interest (regular + mora) = 45-day daily-compounded accrual on full $10k principal."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            datetime(2025, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
    )

    daily_rate = InterestRate("6% a").to_daily().as_decimal
    expected_total = Decimal("10000") * ((1 + daily_rate) ** 45 - 1)

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("7000.00"))
        interest_items = [p for p in warped._all_payments if p.category in ("actual_interest", "actual_mora_interest")]
        total_interest = sum((p.amount for p in interest_items), Money.zero())

    assert total_interest == Money(expected_total)


def test_late_overpayment_principal_is_remainder_after_fine_and_interest():
    """Principal paid = $7,000 - fine - interest."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            datetime(2025, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
    )

    scheduled_payment = loan.get_expected_payment_amount(datetime(2025, 2, 1, tzinfo=timezone.utc))
    fine = scheduled_payment.raw_amount * Decimal("0.02")
    daily_rate = InterestRate("6% a").to_daily().as_decimal
    interest = Decimal("10000") * ((1 + daily_rate) ** 45 - 1)
    expected_principal = Decimal("7000") - fine - interest

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("7000.00"))
        principal_items = [p for p in warped._all_payments if p.category == "actual_principal"]

    assert principal_items[0].amount == Money(expected_principal)


def test_late_overpayment_ending_balance_in_actual_entry():
    """Actual schedule entry: beginning=$10k, ending = $10k - principal paid."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            datetime(2025, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
    )

    scheduled_payment = loan.get_expected_payment_amount(datetime(2025, 2, 1, tzinfo=timezone.utc))
    fine = scheduled_payment.raw_amount * Decimal("0.02")
    daily_rate = InterestRate("6% a").to_daily().as_decimal
    interest = Decimal("10000") * ((1 + daily_rate) ** 45 - 1)
    principal_paid = Decimal("7000") - fine - interest
    expected_ending = Decimal("10000") - principal_paid

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("7000.00"))
        entry = warped._actual_schedule_entries[-1]

    assert entry.ending_balance == Money(expected_ending)


def test_late_overpayment_covers_two_installments():
    """The large principal reduction covers installments 1 and 2; only Apr 1 remains."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            datetime(2025, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
    )

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("7000.00"))
        next_unpaid = warped._next_unpaid_due_date()

    assert next_unpaid == datetime(2025, 4, 1, tzinfo=timezone.utc)


def test_late_overpayment_projected_entry_closes_loan():
    """Projected Apr 1 entry should pay off the remaining balance to zero."""
    loan = Loan(
        Money("10000.00"),
        InterestRate("6% a"),
        [
            datetime(2025, 2, 1, tzinfo=timezone.utc),
            datetime(2025, 3, 1, tzinfo=timezone.utc),
            datetime(2025, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        fine_rate=Decimal("0.02"),
    )

    with Warp(loan, datetime(2025, 2, 15, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(Money("7000.00"))
        schedule = warped.get_amortization_schedule()
        projected = schedule[-1]

    assert projected.ending_balance == Money.zero()
