"""Tests for BillingCycleLoanStatement generation."""

from datetime import date, datetime, timezone

from money_warp import InterestRate, Money


def test_statements_count_matches_installments(simple_loan):
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 2, 12, tzinfo=timezone.utc))
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 3, 15, tzinfo=timezone.utc))
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 4, 12, tzinfo=timezone.utc))

    stmts = simple_loan.statements
    assert len(stmts) == 3


def test_statement_period_numbers(simple_loan):
    stmts = simple_loan.statements
    assert [s.period_number for s in stmts] == [1, 2, 3]


def test_statement_closing_dates(simple_loan):
    stmts = simple_loan.statements
    assert stmts[0].closing_date.date() == date(2025, 1, 28)
    assert stmts[1].closing_date.date() == date(2025, 2, 28)
    assert stmts[2].closing_date.date() == date(2025, 3, 28)


def test_statement_due_dates(simple_loan):
    stmts = simple_loan.statements
    assert stmts[0].due_date.date() == date(2025, 2, 12)
    assert stmts[1].due_date.date() == date(2025, 3, 15)
    assert stmts[2].due_date.date() == date(2025, 4, 12)


def test_statement_expected_amounts(simple_loan):
    stmts = simple_loan.statements
    assert stmts[0].expected_payment == Money("1022.58")
    assert stmts[0].expected_principal == Money("983.20")
    assert stmts[0].expected_interest == Money("39.38")


def test_statement_opening_and_closing_balances(simple_loan):
    stmts = simple_loan.statements
    assert stmts[0].opening_balance == Money("3000.00")
    assert stmts[0].closing_balance == Money("2016.80")
    assert stmts[1].opening_balance == Money("2016.80")
    assert stmts[1].closing_balance == Money("1013.73")
    assert stmts[2].opening_balance == Money("1013.73")
    assert stmts[2].closing_balance == Money("0.00")


def test_statement_mora_rate_constant(simple_loan):
    stmts = simple_loan.statements
    for s in stmts:
        assert s.mora_rate == InterestRate("12% a")


def test_statement_mora_rate_variable(variable_mora_loan):
    stmts = variable_mora_loan.statements
    assert stmts[0].mora_rate == InterestRate("12% a")
    assert stmts[1].mora_rate == InterestRate("12% a")
    assert stmts[2].mora_rate == InterestRate("24% a")


def test_statement_payments_received_on_time(simple_loan):
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 2, 12, tzinfo=timezone.utc))
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 3, 15, tzinfo=timezone.utc))
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 4, 12, tzinfo=timezone.utc))

    stmts = simple_loan.statements
    assert stmts[0].payments_received == Money("0.00")
    assert stmts[1].payments_received == Money("1022.58")
    assert stmts[2].payments_received == Money("1022.58")


def test_statement_no_mora_on_time(simple_loan):
    simple_loan.record_payment(Money("1022.58"), datetime(2025, 2, 12, tzinfo=timezone.utc))
    stmts = simple_loan.statements
    for s in stmts:
        assert s.mora_charged == Money("0.00")
