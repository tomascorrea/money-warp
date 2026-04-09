"""Regression tests: sequential partial payments must match a single combined payment.

Scenario: borrower pays inst#1 in two chunks (both before the due date).
The two sequential payments must produce the same financial outcome as one
combined payment of the same total amount.

Bug (fixed): the forward pass used ``payment.datetime`` as the start of the
next interest accrual period.  When ``interest_date > payment_date`` (early
payments where interest accrues to the due date), the gap between
``payment_date`` and ``interest_date`` was double-counted as interest on the
second payment, starving inst#1 of principal and preventing full coverage.
"""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money, PriceScheduler, Warp


@pytest.fixture
def six_installment_loan():
    """Loan matching the production scenario that exposed the bug."""
    return Loan(
        principal=Money("21169.56"),
        interest_rate=InterestRate("3.19% a.m."),
        due_dates=[
            date(2025, 11, 12),
            date(2025, 12, 12),
            date(2026, 1, 12),
            date(2026, 2, 12),
            date(2026, 3, 12),
            date(2026, 4, 12),
        ],
        disbursement_date=datetime(2025, 10, 9, 18, 0, tzinfo=timezone.utc),
        scheduler=PriceScheduler,
        mora_interest_rate=InterestRate("1% a.m."),
        fine_rate=InterestRate("2% a.m."),
    )


@pytest.fixture
def warp_dt():
    return datetime(2025, 11, 10, 18, 0, tzinfo=timezone.utc)


# --- Single combined payment baseline ---


@pytest.fixture
def single_payment_result(six_installment_loan, warp_dt):
    """Pay the full amount (3,976.40) in one shot."""
    with Warp(six_installment_loan, warp_dt) as w:
        settlement = w.pay_installment(Money("3976.40"))
        return w, settlement


def test_single_payment_interest(single_payment_result):
    _, settlement = single_payment_result
    assert settlement.interest_paid == Money("756.27")


def test_single_payment_principal(single_payment_result):
    _, settlement = single_payment_result
    assert settlement.principal_paid == Money("3220.13")


def test_single_payment_inst1_fully_covered(single_payment_result):
    _, settlement = single_payment_result
    a = settlement.allocations[0]
    assert a.installment_number == 1
    assert a.interest_allocated == Money("756.27")
    assert a.principal_allocated == Money("3189.36")
    assert a.is_fully_covered is True


def test_single_payment_inst1_fully_paid(single_payment_result):
    loan, _ = single_payment_result
    assert loan.installments[0].is_fully_paid is True
    assert loan.installments[0].balance == Money("0.00")


def test_single_payment_spill_to_inst2(single_payment_result):
    _, settlement = single_payment_result
    a = settlement.allocations[1]
    assert a.installment_number == 2
    assert a.principal_allocated == Money("30.77")
    assert a.interest_allocated == Money("0.00")


# --- Two sequential partial payments ---


@pytest.fixture
def two_payment_result(six_installment_loan, warp_dt):
    """Pay in two chunks at the same warp time: 3,932.03 then 44.37."""
    with Warp(six_installment_loan, warp_dt) as w1:
        s1 = w1.pay_installment(Money("3932.03"))
        with Warp(w1, warp_dt) as w2:
            s2 = w2.pay_installment(Money("44.37"))
            return w2, s1, s2


def test_first_partial_interest(two_payment_result):
    _, s1, _ = two_payment_result
    assert s1.interest_paid == Money("756.27")


def test_first_partial_principal(two_payment_result):
    _, s1, _ = two_payment_result
    assert s1.principal_paid == Money("3175.76")


def test_first_partial_inst1_not_yet_covered(two_payment_result):
    _, s1, _ = two_payment_result
    a = s1.allocations[0]
    assert a.installment_number == 1
    assert a.is_fully_covered is False


def test_second_partial_no_double_counted_interest(two_payment_result):
    """The top-up payment must not charge extra interest for the overlap period."""
    _, _, s2 = two_payment_result
    assert s2.interest_paid == Money("0.00")


def test_second_partial_full_principal(two_payment_result):
    """All of the top-up goes to principal reduction."""
    _, _, s2 = two_payment_result
    assert s2.principal_paid == Money("44.37")


def test_second_partial_inst1_fully_covered(two_payment_result):
    _, _, s2 = two_payment_result
    a = s2.allocations[0]
    assert a.installment_number == 1
    assert a.principal_allocated == Money("13.60")
    assert a.interest_allocated == Money("0.00")
    assert a.is_fully_covered is True


def test_second_partial_spill_to_inst2(two_payment_result):
    """Remaining principal spills to inst#2, matching the single-payment case."""
    _, _, s2 = two_payment_result
    a = s2.allocations[1]
    assert a.installment_number == 2
    assert a.principal_allocated == Money("30.77")
    assert a.interest_allocated == Money("0.00")


def test_sequential_inst1_fully_paid(two_payment_result):
    loan, _, _ = two_payment_result
    assert loan.installments[0].is_fully_paid is True
    assert loan.installments[0].balance == Money("0.00")


# --- Equivalence: sequential vs single ---


def test_combined_principal_matches_single(single_payment_result, two_payment_result):
    """Total principal paid across both partials equals the single payment."""
    _, single_s = single_payment_result
    _, s1, s2 = two_payment_result
    assert s1.principal_paid + s2.principal_paid == single_s.principal_paid


def test_combined_interest_matches_single(single_payment_result, two_payment_result):
    """Total interest paid across both partials equals the single payment."""
    _, single_s = single_payment_result
    _, s1, s2 = two_payment_result
    assert s1.interest_paid + s2.interest_paid == single_s.interest_paid


def test_remaining_balance_matches_single(single_payment_result, two_payment_result):
    """Final principal balance is identical regardless of payment splitting."""
    single_loan, _ = single_payment_result
    seq_loan, _, _ = two_payment_result
    assert seq_loan.principal_balance == single_loan.principal_balance
