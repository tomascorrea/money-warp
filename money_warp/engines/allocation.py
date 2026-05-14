"""Payment allocation and per-installment distribution."""

from typing import List, Tuple

from ..models import Allocation, Installment
from ..types.money import Money
from .constants import BALANCE_TOLERANCE


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
    installments: List[Installment],
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

    Two post-processing passes run on the resulting allocations:

    * :func:`_apply_residual` ensures ``sum(allocations.X) == X_total``
      for every component (loan-level accrual can exceed what
      installments absorb due to rounding, partial periods, or
      overpayment).
    * :func:`_finalize_coverage` recomputes every allocation's
      ``is_fully_covered`` flag from the post-payment per-installment
      view, so it agrees with :attr:`Installment.is_fully_paid` by
      construction.

    Returns:
        List of Allocation objects (one per touched installment).
    """
    fine_remaining = fine_total
    mora_remaining = mora_total
    interest_remaining = interest_total
    principal_remaining = principal_total
    allocations: List[Allocation] = []

    for inst in installments:
        if inst.is_fully_paid or inst.balance <= balance_tolerance:
            continue

        fine_owed = inst.expected_fine - inst.fine_paid
        fine_alloc = Money(min(max(fine_owed.raw_amount, 0), fine_remaining.raw_amount))
        fine_remaining = fine_remaining - fine_alloc

        mora_owed = inst.expected_mora - inst.mora_paid
        mora_alloc = Money(min(max(mora_owed.raw_amount, 0), mora_remaining.raw_amount))
        mora_remaining = mora_remaining - mora_alloc

        interest_owed = inst.expected_interest - inst.interest_paid
        interest_alloc = Money(min(max(interest_owed.raw_amount, 0), interest_remaining.raw_amount))
        interest_remaining = interest_remaining - interest_alloc

        principal_owed = inst.expected_principal - inst.principal_paid
        principal_alloc = Money(min(max(principal_owed.raw_amount, 0), principal_remaining.raw_amount))
        principal_remaining = principal_remaining - principal_alloc

        total = fine_alloc + mora_alloc + interest_alloc + principal_alloc
        if total.is_positive():
            is_covered = total + balance_tolerance >= inst.balance

            if not is_covered:
                shortfall = inst.balance - total
                fine_extra, shortfall, fine_remaining = _absorb(shortfall, fine_remaining)
                mora_extra, shortfall, mora_remaining = _absorb(shortfall, mora_remaining)
                interest_extra, shortfall, interest_remaining = _absorb(shortfall, interest_remaining)
                principal_extra, shortfall, principal_remaining = _absorb(shortfall, principal_remaining)
                fine_alloc = fine_alloc + fine_extra
                mora_alloc = mora_alloc + mora_extra
                interest_alloc = interest_alloc + interest_extra
                principal_alloc = principal_alloc + principal_extra
                total = fine_alloc + mora_alloc + interest_alloc + principal_alloc
                is_covered = total + balance_tolerance >= inst.balance

            allocations.append(
                Allocation(
                    installment_number=inst.number,
                    principal_allocated=principal_alloc,
                    interest_allocated=interest_alloc,
                    mora_allocated=mora_alloc,
                    fine_allocated=fine_alloc,
                    is_fully_covered=is_covered,
                )
            )

    _apply_residual(allocations, installments, fine_total, mora_total, interest_total, principal_total)
    _finalize_coverage(allocations, installments)
    return allocations


def _absorb(shortfall: Money, pool: Money) -> Tuple[Money, Money, Money]:
    """Pull up to *shortfall* from *pool*.

    Returns ``(absorbed, remaining_shortfall, remaining_pool)``.
    """
    grab = Money(min(shortfall.raw_amount, pool.raw_amount))
    return grab, shortfall - grab, pool - grab


def _apply_residual(
    allocations: List[Allocation],
    installments: List[Installment],
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
    elif installments:
        allocations.append(
            Allocation(
                installment_number=installments[-1].number,
                principal_allocated=Money(p_diff),
                interest_allocated=Money(i_diff),
                mora_allocated=Money(m_diff),
                fine_allocated=Money(f_diff),
                is_fully_covered=False,
            )
        )


def _finalize_coverage(
    allocations: List[Allocation],
    installments: List[Installment],
) -> None:
    """Recompute ``is_fully_covered`` using the post-payment installment view.

    An allocation is fully covered iff its targeted installment is
    fully paid after the allocation is applied. We project a
    hypothetical post-payment :class:`Installment` and read
    :attr:`Installment.is_fully_paid` directly, so the flag follows
    whatever balance semantics the model defines (including the
    configurable ``balance_tolerance``).
    """
    inst_by_number = {inst.number: inst for inst in installments}
    for i, alloc in enumerate(allocations):
        inst = inst_by_number.get(alloc.installment_number)
        if inst is None:
            continue

        projected = Installment(
            number=inst.number,
            due_date=inst.due_date,
            days_in_period=inst.days_in_period,
            expected_payment=inst.expected_payment,
            expected_principal=inst.expected_principal,
            expected_interest=inst.expected_interest,
            expected_mora=inst.expected_mora,
            expected_fine=inst.expected_fine,
            principal_paid=inst.principal_paid + alloc.principal_allocated,
            interest_paid=inst.interest_paid + alloc.interest_allocated,
            mora_paid=inst.mora_paid + alloc.mora_allocated,
            fine_paid=inst.fine_paid + alloc.fine_allocated,
            allocations=inst.allocations,
            balance_tolerance=inst.balance_tolerance,
        )
        is_settled = projected.is_fully_paid

        if alloc.is_fully_covered != is_settled:
            allocations[i] = Allocation(
                installment_number=alloc.installment_number,
                principal_allocated=alloc.principal_allocated,
                interest_allocated=alloc.interest_allocated,
                mora_allocated=alloc.mora_allocated,
                fine_allocated=alloc.fine_allocated,
                is_fully_covered=is_settled,
            )


def allocate_payment_into_installments(
    amount: Money,
    installments: List[Installment],
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
    per-installment distribution and by :func:`_finalize_coverage`.
    Defaults to the engine-wide ``BALANCE_TOLERANCE``.

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
        installments,
        fine_paid,
        mora_paid,
        interest_paid,
        principal_paid,
        balance_tolerance=balance_tolerance,
    )

    return fine_paid, mora_paid, interest_paid, principal_paid, allocations
