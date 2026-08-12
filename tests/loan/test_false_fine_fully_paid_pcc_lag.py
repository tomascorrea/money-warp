"""Regression tests for issue #104: false fine when fully_paid but pcc lags.

#103 exempts dues via ``principal_covered_count``. Early skewed payments can
leave an installment ``is_fully_paid`` while running principal stays above that
installment's schedule ending-balance milestone (``pcc`` lags). After the due
date, proximity misses the early cash and a fine is invented.

These tests lock the bag-settled exemption and keep the existing fine guardrails.
"""

from datetime import date, datetime, timezone

import pytest

from money_warp import InterestRate, Loan, Money, PriceScheduler, Warp
from money_warp.engines.forward_pass import principal_covered_count


def _aware(d: date, hour: int = 12) -> datetime:
    return datetime(d.year, d.month, d.day, hour, tzinfo=timezone.utc)


@pytest.fixture
def issue_104_loan() -> Loan:
    return Loan(
        principal=Money("10000.00"),
        interest_rate=InterestRate("2.499% a.m."),
        due_dates=[date(2026, m, 1) for m in range(1, 11)],
        disbursement_date=_aware(date(2025, 12, 1), 0),
        scheduler=PriceScheduler,
    )


@pytest.fixture
def issue_104_after_pay4(issue_104_loan: Loan) -> Loan:
    """Minimal #104 chain: inst 1-3 bag-settled, pcc still 2."""
    payments = [
        (date(2025, 12, 25), "100.00"),
        (date(2025, 12, 31), "1042.27"),
        (date(2026, 1, 22), "1142.27"),
        (date(2026, 2, 3), "1142.27"),
    ]
    cur = issue_104_loan
    for pay_day, amount in payments:
        with Warp(cur, _aware(pay_day)) as warped:
            warped.pay_installment(Money(amount), waive_overdue_interest=True)
            cur = warped
    return cur


def test_issue_104_after_pay4_fully_paid_with_pcc_lag(issue_104_after_pay4: Loan) -> None:
    """Sanity: installment 3 is bag-settled while principal_covered_count lags at 2."""
    with Warp(issue_104_after_pay4, _aware(date(2026, 2, 3))) as warped:
        assert warped.installments[0].is_fully_paid is True
        assert warped.installments[1].is_fully_paid is True
        assert warped.installments[2].is_fully_paid is True
        pcc = principal_covered_count(
            warped.principal_balance,
            warped.get_original_schedule(),
        )
        assert pcc == 2
        assert warped.fine_balance == Money.zero()


def test_issue_104_no_fine_after_due_when_bag_settled(issue_104_after_pay4: Loan) -> None:
    """Canonical #104: day after installment 3 due must not invent a fine."""
    with Warp(issue_104_after_pay4, _aware(date(2026, 3, 2))) as warped:
        assert warped.fine_balance == Money.zero()
        inst3 = warped.installments[2]
        assert inst3.expected_fine == Money.zero()
        assert inst3.is_fully_paid is True
        assert inst3.balance == Money.zero()


def test_issue_104_unpaid_installment_still_fined(issue_104_loan: Loan) -> None:
    """Guardrail: with no payments, the first late observation still creates a fine."""
    with Warp(issue_104_loan, _aware(date(2026, 1, 2))) as warped:
        assert warped.fine_balance > Money.zero()
        assert warped.installments[0].expected_fine > Money.zero()


def test_issue_104_late_payment_still_creates_fine(issue_104_loan: Loan) -> None:
    """Guardrail: a late payment on the first late day still materialises the fine."""
    face = issue_104_loan.get_original_schedule().entries[0].payment_amount
    with Warp(issue_104_loan, _aware(date(2026, 1, 2))) as warped:
        settlement = warped.pay_installment(face + Money("300"))
    assert settlement.fine_paid > Money.zero()


def test_issue_104_underpaid_still_fined(issue_104_loan: Loan) -> None:
    """Guardrail: a material underpayment before the due does not block the fine."""
    with Warp(issue_104_loan, _aware(date(2025, 12, 20))) as warped:
        warped.pay_installment(Money("100.00"), waive_overdue_interest=True)
    loan = warped

    with Warp(loan, _aware(date(2026, 1, 2))) as warped:
        assert warped.fine_balance > Money.zero()
        assert warped.installments[0].expected_fine > Money.zero()
