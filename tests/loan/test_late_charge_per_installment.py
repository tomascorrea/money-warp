"""Late fine and mora are charged on each unpaid installment.

Each installment carries its own clock. The charge uses that installment's
payment amount and its own days late. The loan total is the sum. An
installment that is not yet due contributes nothing. The charge is not
added to a later installment's principal.

The schedule below is three commitments of 100, disbursed on 1 Jan 2025:

- due 1 Feb, 45 days late on 18 Mar, 55 days late on 28 Mar
- due 3 Mar, 15 days late on 18 Mar, 25 days late on 28 Mar
- due 18 Apr, not yet due on either date

Contractual interest is zero, so each payment amount is 100. The fine
rate is 2%, so each overdue installment is fined 2 once. The mora rate
is 1% a day, so mora is 1 per day on that 100.
"""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money, Warp

_DISBURSEMENT = datetime(2025, 1, 1, tzinfo=timezone.utc)
_ON_18_MAR = datetime(2025, 3, 18, tzinfo=timezone.utc)
_ON_28_MAR = datetime(2025, 3, 28, tzinfo=timezone.utc)
_DUE_DATES = [date(2025, 2, 1), date(2025, 3, 3), date(2025, 4, 18)]


def _loan(mora_rate: str = "1% daily", grace_period_days: int = 0, principal: str = "300.00") -> Loan:
    return Loan(
        Money(principal),
        InterestRate("0% annual"),
        _DUE_DATES,
        disbursement_date=_DISBURSEMENT,
        fine_rate=InterestRate("2% annual"),
        mora_interest_rate=InterestRate(mora_rate),
        grace_period_days=grace_period_days,
    )


@pytest.fixture
def loan():
    """Three installments of 100. Two are overdue on 18 Mar 2025."""
    return _loan()


def test_each_overdue_installment_is_charged_on_its_own_amount_and_days(loan):
    """
    Given two overdue installments of 100, one 45 days late and one 15
    When the loan is observed on 18 Mar 2025
    Then each is fined once on its own amount and accrues mora for its own days
    """
    with Warp(loan, _ON_18_MAR) as warped:
        first, second, _future = warped.installments

        assert first.expected_fine == Money("2.00")
        assert first.expected_mora == Money("45.00")
        assert second.expected_fine == Money("2.00")
        assert second.expected_mora == Money("15.00")


def test_installment_not_yet_due_adds_no_late_charge(loan):
    """
    Given an installment due on 18 Apr
    When the loan is observed on 18 Mar 2025
    Then that installment has no fine and no mora, and its payment stays 100
    """
    with Warp(loan, _ON_18_MAR) as warped:
        future = warped.installments[2]

        assert future.expected_fine == Money.zero()
        assert future.expected_mora == Money.zero()
        assert future.expected_payment == Money("100.00")
        assert future.expected_principal == Money("100.00")


def test_loan_late_charge_is_the_sum_of_the_installments(loan):
    """
    Given overdue charges of 2 + 45 and 2 + 15, and nothing on the third
    When the loan is observed on 18 Mar 2025
    Then the loan fine is 4 and the loan mora is 60
    """
    with Warp(loan, _ON_18_MAR) as warped:
        assert warped.fine_balance == Money("4.00")
        assert warped.mora_interest_balance == Money("60.00")
        assert warped.principal_balance == Money("300.00")


def test_late_charge_does_not_join_the_installment_principal(loan):
    """
    Given an installment that already carries fine and mora
    When the loan is observed
    Then its principal and its contractual payment stay 100
    """
    with Warp(loan, _ON_18_MAR) as warped:
        first = warped.installments[0]

        assert first.expected_principal == Money("100.00")
        assert first.expected_interest == Money.zero()
        assert first.expected_payment == Money("100.00")


def test_mora_uses_the_installment_amount(loan):
    """
    Given 300 still outstanding and a first installment of 100 that is 45 days late
    When mora is read
    Then it is 45, the charge on that installment, not 135 on the outstanding principal
    """
    with Warp(loan, _ON_18_MAR) as warped:
        assert warped.principal_balance == Money("300.00")
        assert warped.installments[0].expected_mora == Money("45.00")


def test_fine_is_charged_once_when_more_days_pass(loan):
    """
    Given an installment already fined 2 on 18 Mar
    When the loan is observed again on 28 Mar
    Then the fine is still 2
    """
    with Warp(loan, _ON_28_MAR) as warped:
        assert warped.installments[0].expected_fine == Money("2.00")
        assert warped.installments[1].expected_fine == Money("2.00")
        assert warped.fine_balance == Money("4.00")


def test_extra_days_accrue_on_each_open_installment(loan):
    """
    Given the same two overdue installments
    When ten more days pass and the loan is observed on 28 Mar
    Then the first mora is 55, the second is 25, and the third is still zero
    """
    with Warp(loan, _ON_28_MAR) as warped:
        first, second, future = warped.installments

        assert first.expected_mora == Money("55.00")
        assert second.expected_mora == Money("25.00")
        assert future.expected_mora == Money.zero()
        assert warped.mora_interest_balance == Money("80.00")


def test_grace_period_suppresses_the_charge_and_then_counts_those_days():
    """
    Given one installment of 100 due on 1 Mar with 5 days of grace
    When observed on 6 Mar, the due date plus the grace
    Then fine and mora are zero
    When observed on 7 Mar, the first day past grace
    Then the fine is 2 and the mora is 6, counting back to the due date
    """
    loan = Loan(
        Money("100.00"),
        InterestRate("0% annual"),
        [date(2025, 3, 1)],
        disbursement_date=datetime(2025, 2, 1, tzinfo=timezone.utc),
        fine_rate=InterestRate("2% annual"),
        mora_interest_rate=InterestRate("1% daily"),
        grace_period_days=5,
    )

    with Warp(loan, datetime(2025, 3, 6, tzinfo=timezone.utc)) as warped:
        installment = warped.installments[0]
        assert installment.expected_fine == Money.zero()
        assert installment.expected_mora == Money.zero()

    with Warp(loan, datetime(2025, 3, 7, tzinfo=timezone.utc)) as warped:
        installment = warped.installments[0]
        assert installment.expected_fine == Money("2.00")
        assert installment.expected_mora == Money("6.00")


def test_mora_rate_changes_the_mora_and_not_the_fine(loan):
    """
    Given the same installments and a mora rate of 2% a day instead of 1%
    When the loan is observed on 18 Mar
    Then the moras are 90 and 30, and each fine is still 2
    """
    faster = _loan(mora_rate="2% daily")

    with Warp(faster, _ON_18_MAR) as warped:
        first, second, future = warped.installments

        assert first.expected_mora == Money("90.00")
        assert second.expected_mora == Money("30.00")
        assert future.expected_mora == Money.zero()
        assert warped.mora_interest_balance == Money("120.00")
        assert first.expected_fine == Money("2.00")
        assert second.expected_fine == Money("2.00")
        assert warped.fine_balance == Money("4.00")


def test_paying_the_outstanding_late_charge_clears_the_loan_balances(loan):
    """
    Given 4 of fine and 60 of mora outstanding on 18 Mar
    When a payment of 64 is recorded on that date
    Then the loan fine and the loan mora are both zero, and the principal is unchanged
    """
    loan.record_payment(Money("64.00"), _ON_18_MAR)

    with Warp(loan, _ON_18_MAR) as warped:
        assert warped.fine_balance == Money.zero()
        assert warped.mora_interest_balance == Money.zero()
        assert warped.principal_balance == Money("300.00")


def test_open_installments_keep_their_own_clock_after_the_late_charge_is_paid(loan):
    """
    Given the late charge of 64 was paid on 18 Mar and every installment is still open
    When the loan is observed on 28 Mar
    Then each open installment has accrued 10 more days on its own 100
    And the loan mora is 20, the fine stays paid, and no payment amount changed
    """
    loan.record_payment(Money("64.00"), _ON_18_MAR)

    with Warp(loan, _ON_28_MAR) as warped:
        first, second, future = warped.installments

        assert first.expected_mora == Money("55.00")
        assert second.expected_mora == Money("25.00")
        assert future.expected_mora == Money.zero()
        assert warped.mora_interest_balance == Money("20.00")
        assert warped.fine_balance == Money.zero()
        assert first.expected_payment == Money("100.00")
        assert second.expected_payment == Money("100.00")
        assert future.expected_payment == Money("100.00")
