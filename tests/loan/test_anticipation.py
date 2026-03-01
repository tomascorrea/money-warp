"""Tests for installment anticipation (calculate_anticipation, anticipate_payment)."""

from datetime import datetime, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from money_warp import InterestRate, Loan, Money, Warp
from money_warp.loan.settlement import AnticipationResult
from money_warp.scheduler import InvertedPriceScheduler


@pytest.fixture
def three_installment_loan():
    return Loan(
        Money("10000"),
        InterestRate("12% annual"),
        [
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            datetime(2024, 3, 1, tzinfo=timezone.utc),
            datetime(2024, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def six_installment_loan():
    return Loan(
        Money("60000"),
        InterestRate("12% annual"),
        [
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            datetime(2024, 3, 1, tzinfo=timezone.utc),
            datetime(2024, 4, 1, tzinfo=timezone.utc),
            datetime(2024, 5, 1, tzinfo=timezone.utc),
            datetime(2024, 6, 1, tzinfo=timezone.utc),
            datetime(2024, 7, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


# -- calculate_anticipation: basic properties --


def test_anticipation_amount_is_positive(three_installment_loan):
    with Warp(three_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan:
        result = loan.calculate_anticipation([3])
    assert result.amount.is_positive()


def test_anticipation_returns_anticipation_result(three_installment_loan):
    with Warp(three_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan:
        result = loan.calculate_anticipation([3])
    assert isinstance(result, AnticipationResult)


def test_anticipation_returns_correct_installments(three_installment_loan):
    with Warp(three_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan:
        result = loan.calculate_anticipation([2, 3])
    assert len(result.installments) == 2
    assert result.installments[0].number == 2
    assert result.installments[1].number == 3


# -- calculate_anticipation: specific installment selections --


def test_anticipation_last_installment(three_installment_loan):
    with Warp(three_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan:
        result = loan.calculate_anticipation([3])
    assert result.amount.is_positive()
    assert len(result.installments) == 1
    assert result.installments[0].number == 3


def test_anticipation_middle_installment(six_installment_loan):
    with Warp(six_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan:
        result = loan.calculate_anticipation([3])
    assert result.amount.is_positive()
    assert len(result.installments) == 1
    assert result.installments[0].number == 3


def test_anticipation_multiple_installments(six_installment_loan):
    with Warp(six_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan:
        result = loan.calculate_anticipation([4, 5])
    assert result.amount.is_positive()
    assert len(result.installments) == 2


def test_anticipation_all_remaining_equals_current_balance(three_installment_loan):
    with Warp(three_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan:
        result = loan.calculate_anticipation([1, 2, 3])
        assert result.amount == loan.current_balance


# -- calculate_anticipation: validation --


def test_anticipation_paid_installment_raises_error(three_installment_loan):
    with Warp(three_installment_loan, datetime(2024, 2, 1, tzinfo=timezone.utc)) as loan:
        schedule = loan.get_original_schedule()
        pmt = schedule.entries[0].payment_amount
        loan.pay_installment(pmt)

        with pytest.raises(ValueError, match="already paid"):
            loan.calculate_anticipation([1])


def test_anticipation_invalid_number_raises_error(three_installment_loan):
    with Warp(three_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan, pytest.raises(
        ValueError, match="out of range"
    ):
        loan.calculate_anticipation([0])


def test_anticipation_number_too_large_raises_error(three_installment_loan):
    with Warp(three_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan, pytest.raises(
        ValueError, match="out of range"
    ):
        loan.calculate_anticipation([99])


# -- calculate_anticipation: Warp-aware --


def test_anticipation_warp_aware(three_installment_loan):
    with Warp(three_installment_loan, datetime(2024, 1, 10, tzinfo=timezone.utc)) as loan:
        result_early = loan.calculate_anticipation([3])

    with Warp(three_installment_loan, datetime(2024, 1, 25, tzinfo=timezone.utc)) as loan:
        result_late = loan.calculate_anticipation([3])

    assert result_early.amount != result_late.amount


# -- calculate_anticipation: works with SAC scheduler --


def test_anticipation_with_sac_scheduler():
    loan = Loan(
        Money("10000"),
        InterestRate("12% annual"),
        [
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            datetime(2024, 3, 1, tzinfo=timezone.utc),
            datetime(2024, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        scheduler=InvertedPriceScheduler,
    )
    with Warp(loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as warped:
        result = warped.calculate_anticipation([3])
    assert result.amount.is_positive()
    assert len(result.installments) == 1


# -- anticipate_payment: backward compatible --


def test_anticipate_payment_backward_compatible(three_installment_loan):
    with Warp(three_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan:
        settlement = loan.anticipate_payment(Money("500"))
    assert settlement.principal_paid.is_positive()


# -- anticipate_payment: full lifecycle zeroes balance --


def test_anticipation_full_lifecycle_zeroes_balance():
    loan = Loan(
        Money("10000"),
        InterestRate("12% annual"),
        [
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            datetime(2024, 3, 1, tzinfo=timezone.utc),
            datetime(2024, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as warped:
        result = warped.calculate_anticipation([3])

    loan.record_payment(
        result.amount,
        datetime(2024, 1, 15, tzinfo=timezone.utc),
        description="Anticipate installment 3",
    )

    loan.get_amortization_schedule()
    kept = [e for e in loan.get_original_schedule().entries if e.payment_number != 3]

    for entry in kept:
        loan.record_payment(entry.payment_amount, entry.due_date)

    tolerance = Money("0.10")
    assert loan.principal_balance < tolerance


# -- anticipate_payment: removes all remaining (full early payoff) --


def test_anticipation_all_remaining_full_payoff():
    loan = Loan(
        Money("10000"),
        InterestRate("12% annual"),
        [
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            datetime(2024, 3, 1, tzinfo=timezone.utc),
            datetime(2024, 4, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    with Warp(loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as warped:
        result = warped.calculate_anticipation([1, 2, 3])
        warped.anticipate_payment(result.amount, installments=[1, 2, 3])
        assert warped.is_paid_off


# -- anticipate_payment: removing more installments costs less up front --


def test_removing_more_installments_increases_anticipation_amount(six_installment_loan):
    with Warp(six_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan:
        result_one = loan.calculate_anticipation([6])

    with Warp(six_installment_loan, datetime(2024, 1, 15, tzinfo=timezone.utc)) as loan:
        result_two = loan.calculate_anticipation([5, 6])

    assert result_two.amount > result_one.amount


# -- Property: kept installments are unchanged regardless of anticipation --


@given(
    anticipated=st.lists(
        st.integers(min_value=1, max_value=6),
        min_size=1,
        max_size=6,
        unique=True,
    ),
    day_offset=st.integers(min_value=2, max_value=30),
)
@settings(max_examples=50)
def test_kept_installments_unchanged_regardless_of_anticipation(anticipated, day_offset):
    """No matter which subset of installments is anticipated, and no matter
    when the anticipation happens, the kept installments must have the same
    expected_principal and expected_interest as in the original schedule.
    """
    loan = Loan(
        Money("60000"),
        InterestRate("12% annual"),
        [
            datetime(2024, 2, 1, tzinfo=timezone.utc),
            datetime(2024, 3, 1, tzinfo=timezone.utc),
            datetime(2024, 4, 1, tzinfo=timezone.utc),
            datetime(2024, 5, 1, tzinfo=timezone.utc),
            datetime(2024, 6, 1, tzinfo=timezone.utc),
            datetime(2024, 7, 1, tzinfo=timezone.utc),
        ],
        disbursement_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )

    original_schedule = loan.get_original_schedule()
    original_by_number = {e.payment_number: e for e in original_schedule.entries}
    removed_set = set(anticipated)
    warp_date = datetime(2024, 1, day_offset, tzinfo=timezone.utc)

    with Warp(loan, warp_date) as warped:
        result = warped.calculate_anticipation(anticipated)
        warped.anticipate_payment(result.amount, installments=anticipated)

        for inst in warped.installments:
            if inst.number in removed_set:
                continue
            orig = original_by_number[inst.number]
            assert inst.expected_principal == orig.principal_payment
            assert inst.expected_interest == orig.interest_payment
