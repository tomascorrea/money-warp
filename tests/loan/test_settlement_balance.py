"""Tests for Loan.settlement_balance with explicit expected values."""

from datetime import date, datetime, timezone

from money_warp import InterestRate, Loan, Money, PriceScheduler, Warp


def _single_installment_loan() -> Loan:
    return Loan(
        principal=Money("10000"),
        interest_rate=InterestRate("10% a.m."),
        due_dates=[date(2025, 12, 20)],
        disbursement_date=datetime(2025, 11, 20, tzinfo=timezone.utc),
        scheduler=PriceScheduler,
    )


def _multi_installment_loan() -> Loan:
    return Loan(
        principal=Money("10000"),
        interest_rate=InterestRate("5% a.m."),
        due_dates=[date(2025, 12, 20), date(2026, 1, 20), date(2026, 2, 20)],
        disbursement_date=datetime(2025, 11, 20, tzinfo=timezone.utc),
        scheduler=PriceScheduler,
    )


# ------------------------------------------------------------------
# Single installment
# ------------------------------------------------------------------


def test_single_early_equals_scheduled_pmt():
    """Early: settlement_balance equals the scheduled PMT."""
    loan = _single_installment_loan()
    sched = loan.get_original_schedule()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        assert w.settlement_balance == sched.entries[0].payment_amount


def test_single_early_greater_than_current_balance():
    """Early: settlement_balance > current_balance (extra 10 days interest)."""
    loan = _single_installment_loan()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        assert w.settlement_balance == Money("10985.65")
        assert w.current_balance == Money("10646.75")
        assert w.settlement_balance > w.current_balance


def test_single_ontime_equals_current_balance():
    """On-time: settlement_balance == current_balance."""
    loan = _single_installment_loan()
    with Warp(loan, datetime(2025, 12, 20, tzinfo=timezone.utc)) as w:
        assert w.settlement_balance == Money("10985.65")
        assert w.settlement_balance == w.current_balance


def test_single_late_equals_current_balance():
    """Late: settlement_balance == current_balance (both accrue to now)."""
    loan = _single_installment_loan()
    with Warp(loan, datetime(2025, 12, 25, tzinfo=timezone.utc)) as w:
        assert w.settlement_balance == Money("11378.83")
        assert w.settlement_balance == w.current_balance


def test_single_late_includes_mora_and_fines():
    """Late: settlement_balance includes mora interest and fines."""
    loan = _single_installment_loan()
    with Warp(loan, datetime(2025, 12, 25, tzinfo=timezone.utc)) as w:
        assert w.fine_balance == Money("219.71")
        assert w.mora_interest_balance == Money("173.47")
        assert w.settlement_balance == Money("11378.83")


def test_single_at_disbursement_equals_scheduled_pmt():
    """At disbursement: settlement_balance equals PMT (full period ahead)."""
    loan = _single_installment_loan()
    with Warp(loan, datetime(2025, 11, 20, tzinfo=timezone.utc)) as w:
        sched = loan.get_original_schedule()
        assert w.settlement_balance == sched.entries[0].payment_amount


# ------------------------------------------------------------------
# Multi installment
# ------------------------------------------------------------------


def test_multi_early_equals_first_installment_pmt():
    """Early: settlement_balance equals installment 1 PMT."""
    loan = _multi_installment_loan()
    sched = loan.get_original_schedule()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        assert w.settlement_balance == sched.entries[0].payment_amount
        assert w.settlement_balance == Money("3672.95")


def test_multi_early_less_than_current_balance():
    """Early: settlement_balance < current_balance (1 installment vs all principal)."""
    loan = _multi_installment_loan()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        assert w.settlement_balance == Money("3672.95")
        assert w.current_balance == Money("10326.01")
        assert w.settlement_balance < w.current_balance


def test_multi_after_first_payment_settlement_is_second_pmt():
    """After paying inst 1, settlement_balance covers inst 2."""
    loan = _multi_installment_loan()
    sched = loan.get_original_schedule()

    with Warp(loan, datetime(2025, 12, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(w.settlement_balance)
        warped = w

    with Warp(warped, datetime(2026, 1, 10, tzinfo=timezone.utc)) as w:
        assert w.settlement_balance == sched.entries[1].payment_amount


def test_multi_fully_paid_settlement_is_zero():
    """After all installments paid, settlement_balance is zero."""
    loan = _multi_installment_loan()
    sched = loan.get_original_schedule()

    with Warp(loan, datetime(2025, 12, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(sched.entries[0].payment_amount)
        warped1 = w

    with Warp(warped1, datetime(2026, 1, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(sched.entries[1].payment_amount)
        warped2 = w

    with Warp(warped2, datetime(2026, 2, 20, tzinfo=timezone.utc)) as w:
        w.pay_installment(sched.entries[2].payment_amount)
        warped3 = w

    with Warp(warped3, datetime(2026, 3, 1, tzinfo=timezone.utc)) as w:
        assert w.settlement_balance == Money("0.00")


def test_multi_components_sum():
    """settlement_balance = interest_to_due + scheduled_principal (no fines/mora)."""
    loan = _multi_installment_loan()
    sched = loan.get_original_schedule()
    with Warp(loan, datetime(2025, 12, 10, tzinfo=timezone.utc)) as w:
        expected_principal = sched.entries[0].principal_payment
        interest_component = Money(
            w.settlement_balance.raw_amount - expected_principal.raw_amount
        )
        assert interest_component == sched.entries[0].interest_payment
