"""Payment allocation and per-installment distribution.

The allocator is driven by primitive expected/paid amounts derived from
the cashflow and schedule, never by a public :class:`Installment` view.
``_InstallmentExpectation`` is the internal bag of those primitives so
``compute_state`` can stay strictly downstream of the cashflow.
"""

from dataclasses import dataclass
from datetime import date
from typing import List, Tuple

from ..models import Allocation
from ..types.money import Money
from .constants import BALANCE_TOLERANCE


@dataclass(frozen=True)
class _InstallmentExpectation:
    """Per-installment caps used by the allocator.

    Same ``balance`` / ``is_fully_paid`` semantics as
    :class:`money_warp.models.Installment`, but with no allocations list
    and no public exposure. Built directly from the schedule, prior
    allocations, accrued mora, and fines applied — i.e. from primitives
    the forward pass already has on hand.
    """

    number: int
    due_date: date
    expected_principal: Money
    expected_interest: Money
    expected_mora: Money
    expected_fine: Money
    principal_paid: Money
    interest_paid: Money
    mora_paid: Money
    fine_paid: Money
    balance_tolerance: Money

    @property
    def balance(self) -> Money:
        total_expected = self.expected_principal + self.expected_interest + self.expected_mora + self.expected_fine
        total_paid = self.principal_paid + self.interest_paid + self.mora_paid + self.fine_paid
        remaining = total_expected - total_paid
        if not remaining.is_positive() or remaining <= self.balance_tolerance:
            return Money.zero()
        return remaining

    @property
    def is_fully_paid(self) -> bool:
        return self.balance.is_zero()


def allocate_payment(
    amount: Money,
    fines_owed: Money,
    mora_accrued: Money,
    interest_accrued: Money,
) -> Tuple[Money, Money, Money, Money]:
    """Loan-level allocation: fine -> mora -> interest -> principal.

    Determines how a payment splits across the four obligation
    components.  Everything left after fines, mora, and interest
    goes to principal reduction (which may exceed the current
    balance, producing overpayment handled by the caller).

    Returns:
        (fine_paid, mora_paid, interest_paid, principal_paid)
    """
    remaining = amount

    fine_paid = Money(min(fines_owed.raw_amount, remaining.raw_amount))
    remaining = remaining - fine_paid

    mora_paid = Money(min(mora_accrued.raw_amount, remaining.raw_amount))
    remaining = remaining - mora_paid

    interest_paid = Money(min(interest_accrued.raw_amount, remaining.raw_amount))
    remaining = remaining - interest_paid

    principal_paid = remaining
    return fine_paid, mora_paid, interest_paid, principal_paid


def distribute_into_installments(
    expectations: List[_InstallmentExpectation],
    fine_total: Money,
    mora_total: Money,
    interest_total: Money,
    principal_total: Money,
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> List[Allocation]:
    """Distribute loan-level totals into per-installment allocations.

    Walks installments sequentially, filling each installment's
    obligations from the pre-computed loan-level totals. This is a
    reporting view -- the financial math is done by
    :func:`allocate_payment`.

    Each emitted :class:`Allocation` receives a provisional
    ``is_fully_covered=False``; ``compute_state`` runs a single final
    pass against the post-payment :class:`Installment` view to assign
    the real value. Keeping the per-event step out of the loop is what
    lets us guarantee one and only one writer for that flag.

    A residual sweep at the end ensures ``sum(allocations.X) ==
    X_total`` for every component (loan-level accrual can exceed what
    installments absorb due to rounding, partial periods, or
    overpayment).

    Returns:
        List of Allocation objects (one per touched installment).
    """
    fine_remaining = fine_total
    mora_remaining = mora_total
    interest_remaining = interest_total
    principal_remaining = principal_total
    allocations: List[Allocation] = []

    for exp in expectations:
        if exp.is_fully_paid or exp.balance <= balance_tolerance:
            continue

        fine_owed = exp.expected_fine - exp.fine_paid
        fine_alloc = Money(min(max(fine_owed.raw_amount, 0), fine_remaining.raw_amount))
        fine_remaining = fine_remaining - fine_alloc

        mora_owed = exp.expected_mora - exp.mora_paid
        mora_alloc = Money(min(max(mora_owed.raw_amount, 0), mora_remaining.raw_amount))
        mora_remaining = mora_remaining - mora_alloc

        interest_owed = exp.expected_interest - exp.interest_paid
        interest_alloc = Money(min(max(interest_owed.raw_amount, 0), interest_remaining.raw_amount))
        interest_remaining = interest_remaining - interest_alloc

        principal_owed = exp.expected_principal - exp.principal_paid
        principal_alloc = Money(min(max(principal_owed.raw_amount, 0), principal_remaining.raw_amount))
        principal_remaining = principal_remaining - principal_alloc

        total = fine_alloc + mora_alloc + interest_alloc + principal_alloc
        if total.is_positive():
            is_covered = total + balance_tolerance >= exp.balance

            if not is_covered:
                shortfall = exp.balance - total
                fine_extra, shortfall, fine_remaining = _absorb(shortfall, fine_remaining)
                mora_extra, shortfall, mora_remaining = _absorb(shortfall, mora_remaining)
                interest_extra, shortfall, interest_remaining = _absorb(shortfall, interest_remaining)
                principal_extra, shortfall, principal_remaining = _absorb(shortfall, principal_remaining)
                fine_alloc = fine_alloc + fine_extra
                mora_alloc = mora_alloc + mora_extra
                interest_alloc = interest_alloc + interest_extra
                principal_alloc = principal_alloc + principal_extra

            allocations.append(
                Allocation(
                    installment_number=exp.number,
                    principal_allocated=principal_alloc,
                    interest_allocated=interest_alloc,
                    mora_allocated=mora_alloc,
                    fine_allocated=fine_alloc,
                    is_fully_covered=False,
                )
            )

    _apply_residual(allocations, expectations, fine_total, mora_total, interest_total, principal_total)
    return allocations


def _absorb(shortfall: Money, pool: Money) -> Tuple[Money, Money, Money]:
    """Pull up to *shortfall* from *pool*.

    Returns ``(absorbed, remaining_shortfall, remaining_pool)``.
    """
    grab = Money(min(shortfall.raw_amount, pool.raw_amount))
    return grab, shortfall - grab, pool - grab


def _apply_residual(
    allocations: List[Allocation],
    expectations: List[_InstallmentExpectation],
    fine_total: Money,
    mora_total: Money,
    interest_total: Money,
    principal_total: Money,
) -> None:
    """Adjust the last allocation so ``sum(allocations)`` matches the totals.

    Loan-level accrual can exceed what installments absorb (rounding,
    partial periods, overpayment).  This single sweep patches any gap.
    """
    sum_f = sum((a.fine_allocated.raw_amount for a in allocations), Money.zero().raw_amount)
    sum_m = sum((a.mora_allocated.raw_amount for a in allocations), Money.zero().raw_amount)
    sum_i = sum((a.interest_allocated.raw_amount for a in allocations), Money.zero().raw_amount)
    sum_p = sum((a.principal_allocated.raw_amount for a in allocations), Money.zero().raw_amount)

    f_diff = fine_total.raw_amount - sum_f
    m_diff = mora_total.raw_amount - sum_m
    i_diff = interest_total.raw_amount - sum_i
    p_diff = principal_total.raw_amount - sum_p

    if not (f_diff or m_diff or i_diff or p_diff):
        return

    if allocations:
        last = allocations[-1]
        allocations[-1] = Allocation(
            installment_number=last.installment_number,
            principal_allocated=Money(last.principal_allocated.raw_amount + p_diff),
            interest_allocated=Money(last.interest_allocated.raw_amount + i_diff),
            mora_allocated=Money(last.mora_allocated.raw_amount + m_diff),
            fine_allocated=Money(last.fine_allocated.raw_amount + f_diff),
            is_fully_covered=last.is_fully_covered,
        )
    elif expectations:
        allocations.append(
            Allocation(
                installment_number=expectations[-1].number,
                principal_allocated=Money(p_diff),
                interest_allocated=Money(i_diff),
                mora_allocated=Money(m_diff),
                fine_allocated=Money(f_diff),
                is_fully_covered=False,
            )
        )


def allocate_payment_into_installments(
    amount: Money,
    expectations: List[_InstallmentExpectation],
    fine_cap: Money,
    interest_cap: Money,
    mora_cap: Money,
    balance_tolerance: Money = BALANCE_TOLERANCE,
) -> Tuple[Money, Money, Money, Money, List[Allocation]]:
    """Allocate a payment across installments in priority order.

    Two-step process:

    1. **Loan-level allocation** (:func:`allocate_payment`) determines
       the totals: fine -> mora -> interest -> principal.
    2. **Per-installment distribution** (:func:`distribute_into_installments`)
       maps those totals to individual installments for reporting.

    *balance_tolerance* controls the sub-cent threshold used by the
    per-installment distribution.  Defaults to the engine-wide
    ``BALANCE_TOLERANCE``.

    Returns:
        (fine_total, mora_total, interest_total, principal_total, allocations)
    """
    fine_paid, mora_paid, interest_paid, principal_paid = allocate_payment(
        amount,
        fine_cap,
        mora_cap,
        interest_cap,
    )

    allocations = distribute_into_installments(
        expectations,
        fine_paid,
        mora_paid,
        interest_paid,
        principal_paid,
        balance_tolerance=balance_tolerance,
    )

    return fine_paid, mora_paid, interest_paid, principal_paid, allocations
