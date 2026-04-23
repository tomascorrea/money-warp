"""Tests for the tolerance adjustment CashFlowItem approach.

When an external origination system introduces a small per-installment
rounding error, ``pay_installment`` detects the balance drift and adds
a tolerance adjustment entry to the cashflow.  This prevents rounding
drift from compounding across installments.
"""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money, Warp

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def twelve_installment_loan():
    """12-installment loan with default 1-cent tolerance."""
    due_dates = [
        date(2026, 3, 22),
        date(2026, 4, 22),
        date(2026, 5, 22),
        date(2026, 6, 22),
        date(2026, 7, 22),
        date(2026, 8, 22),
        date(2026, 9, 22),
        date(2026, 10, 22),
        date(2026, 11, 22),
        date(2026, 12, 22),
        date(2027, 1, 22),
        date(2027, 2, 22),
    ]
    return Loan(
        Money("10000"),
        InterestRate("1% m"),
        due_dates,
        disbursement_date=datetime(2026, 2, 22, tzinfo=timezone.utc),
    )


@pytest.fixture
def three_installment_loan():
    """3-installment loan for testing tolerance adjustment."""
    return Loan(
        Money("10000"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# Loan.payment_tolerance defaults
# ---------------------------------------------------------------------------


def test_default_payment_tolerance_is_one_cent(twelve_installment_loan):
    assert twelve_installment_loan.payment_tolerance == Money("0.01")


def test_custom_payment_tolerance():
    loan = Loan(
        Money("10000"),
        InterestRate("1% m"),
        [date(2026, 3, 22), date(2026, 4, 22)],
        disbursement_date=datetime(2026, 2, 22, tzinfo=timezone.utc),
        payment_tolerance=Money("0.05"),
    )
    assert loan.payment_tolerance == Money("0.05")


def test_zero_tolerance_gives_exact_matching():
    loan = Loan(
        Money("10000"),
        InterestRate("1% m"),
        [date(2026, 3, 22), date(2026, 4, 22)],
        disbursement_date=datetime(2026, 2, 22, tzinfo=timezone.utc),
        payment_tolerance=Money("0"),
    )
    assert loan.payment_tolerance == Money("0")


# ---------------------------------------------------------------------------
# Tolerance adjustment CashFlowItem
# ---------------------------------------------------------------------------


def test_tolerance_adjustment_added_when_balance_drifts(three_installment_loan):
    """When pay_installment underpays by <= tolerance, an adjustment entry appears."""
    schedule = three_installment_loan.get_original_schedule()
    pmt = schedule[0].payment_amount

    with Warp(three_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(pmt - Money("0.01"))
    loan = warped

    cf_items = [e for e in loan.cashflow.items() if "Tolerance adjustment" in (e.description or "")]
    assert len(cf_items) == 1
    assert cf_items[0].amount == Money("0.01")
    assert "installment 1" in cf_items[0].description


def test_no_tolerance_adjustment_when_exact_payment(three_installment_loan):
    """No adjustment when the payment exactly matches the schedule."""
    schedule = three_installment_loan.get_original_schedule()
    pmt = schedule[0].payment_amount

    with Warp(three_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(pmt)
    loan = warped

    cf_items = [e for e in loan.cashflow.items() if "Tolerance adjustment" in (e.description or "")]
    assert len(cf_items) == 0


def test_no_tolerance_adjustment_when_gap_exceeds_tolerance(three_installment_loan):
    """No adjustment when the gap is larger than payment_tolerance."""
    schedule = three_installment_loan.get_original_schedule()
    pmt = schedule[0].payment_amount

    with Warp(three_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(pmt - Money("0.02"))
    loan = warped

    cf_items = [e for e in loan.cashflow.items() if "Tolerance adjustment" in (e.description or "")]
    assert len(cf_items) == 0


def test_tolerance_adjustment_prevents_balance_drift(twelve_installment_loan):
    """After paying each installment with a 1-cent shortfall, balance stays aligned."""
    schedule = twelve_installment_loan.get_original_schedule()

    loan = twelve_installment_loan
    for _i, entry in enumerate(schedule):
        due_dt = datetime(entry.due_date.year, entry.due_date.month, entry.due_date.day, tzinfo=timezone.utc)
        with Warp(loan, due_dt) as warped:
            warped.pay_installment(entry.payment_amount - Money("0.01"))
        loan = warped

    cf_items = [e for e in loan.cashflow.items() if "Tolerance adjustment" in (e.description or "")]
    assert len(cf_items) == 12

    last_due = schedule[-1].due_date
    with Warp(loan, datetime(last_due.year, last_due.month, last_due.day, tzinfo=timezone.utc)) as warped:
        assert warped.is_paid_off is True


# ---------------------------------------------------------------------------
# is_paid_off -- exact matching
# ---------------------------------------------------------------------------


def test_is_paid_off_after_full_repayment(three_installment_loan):
    schedule = three_installment_loan.get_original_schedule()
    loan = three_installment_loan
    for entry in schedule:
        due_dt = datetime(entry.due_date.year, entry.due_date.month, entry.due_date.day, tzinfo=timezone.utc)
        with Warp(loan, due_dt) as warped:
            warped.pay_installment(entry.payment_amount)
        loan = warped
    assert loan.is_paid_off is True


def test_is_paid_off_after_full_repayment_with_warp(twelve_installment_loan):
    schedule = twelve_installment_loan.get_original_schedule()
    with Warp(twelve_installment_loan, datetime(2027, 3, 1, tzinfo=timezone.utc)) as warped:
        for entry in schedule:
            warped.record_payment(
                entry.payment_amount,
                datetime(entry.due_date.year, entry.due_date.month, entry.due_date.day, tzinfo=timezone.utc),
            )
        assert warped.is_paid_off is True


# ---------------------------------------------------------------------------
# is_fully_paid -- exact matching
# ---------------------------------------------------------------------------


def test_installment_is_fully_paid_after_exact_payment(three_installment_loan):
    schedule = three_installment_loan.get_original_schedule()
    pmt = schedule[0].payment_amount

    with Warp(three_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(pmt)
    loan = warped

    assert loan.installments[0].is_fully_paid is True


def test_installment_is_fully_paid_after_tolerance_adjustment(three_installment_loan):
    """Installment is fully paid when a tolerance adjustment closes the gap."""
    schedule = three_installment_loan.get_original_schedule()
    pmt = schedule[0].payment_amount

    with Warp(three_installment_loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(pmt - Money("0.01"))
    loan = warped

    cf_items = [e for e in loan.cashflow.items() if "Tolerance adjustment" in (e.description or "")]
    assert len(cf_items) == 1


# ---------------------------------------------------------------------------
# Coverage flag consistency with is_paid_off when tolerance absorbs residual
# ---------------------------------------------------------------------------


def test_allocation_is_fully_covered_when_tolerance_absorbs_residual():
    """If is_paid_off is True, the allocation must report is_fully_covered=True.

    Regression for the reported contradiction: a single-installment loan paid
    by an amount that leaves a sub-cent principal residual.  The tolerance
    adjustment absorbs the residual so the loan is paid off, but the
    returned Settlement used to still say is_fully_covered=False.
    """
    loan = Loan(
        Money("10000"),
        InterestRate("6% a"),
        [date(2025, 2, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    schedule = loan.get_original_schedule()
    short = schedule[0].payment_amount - Money("0.01")

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        settlement = warped.pay_installment(short)
        assert warped.is_paid_off is True
        assert settlement.allocations[-1].is_fully_covered is True


# ---------------------------------------------------------------------------
# Zero tolerance -- no adjustments
# ---------------------------------------------------------------------------


def test_allocation_is_fully_covered_with_one_cent_gap_multi_installment():
    """is_fully_covered=True when payment is R$0.01 short on a multi-installment loan.

    The _apply_coverage_fixup only helps when the entire loan is nearly paid
    off.  For a mid-loan installment the per-installment check must apply the
    BALANCE_TOLERANCE itself.
    """
    loan = Loan(
        Money("10000"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1), date(2025, 4, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    schedule = loan.get_original_schedule()
    short = schedule[0].payment_amount - Money("0.01")

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        settlement = warped.pay_installment(short)
        assert settlement.allocations[0].is_fully_covered is True


def test_zero_tolerance_never_adds_adjustment():
    loan = Loan(
        Money("10000"),
        InterestRate("6% a"),
        [date(2025, 2, 1), date(2025, 3, 1)],
        disbursement_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
        payment_tolerance=Money("0"),
    )
    schedule = loan.get_original_schedule()

    with Warp(loan, datetime(2025, 2, 1, tzinfo=timezone.utc)) as warped:
        warped.pay_installment(schedule[0].payment_amount - Money("0.01"))
    loan = warped

    cf_items = [e for e in loan.cashflow.items() if "Tolerance adjustment" in (e.description or "")]
    assert len(cf_items) == 0
