from datetime import datetime, timedelta, timezone

import pytest

from money_warp import InterestRate, Loan, Money


@pytest.mark.parametrize(
    "principal",
    [
        Money("10000.00"),
        Money("30000.00"),
        Money("40000.00"),
        Money("90000.00"),
    ],
)
@pytest.mark.parametrize(
    "payment",
    [
        Money("1000.00"),
        Money("3000.00"),
        Money("4000.00"),
        Money("9000.00"),
    ],
)
def test_loan_pay_instalment_all_money_is_alocated(principal, payment):
    rate = InterestRate("5% a")
    disbursement_date = datetime.now(timezone.utc)
    due_dates = [(disbursement_date + timedelta(days=20)).date()]

    loan = Loan(principal, rate, due_dates, disbursement_date=disbursement_date)
    loan.pay_installment(payment)

    # Balance should be reduced by principal portion

    allocated = Money(0)
    for intallment in loan.installments:
        for allocation in intallment.allocations:
            allocated += allocation.principal_allocated + allocation.interest_allocated
    assert allocated == payment
