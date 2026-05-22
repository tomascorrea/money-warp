"""Payment allocation and per-installment distribution.

The allocator is driven by primitive expected/paid amounts derived from
the cashflow and schedule, never by a public :class:`Installment` view.
``_InstallmentExpectation`` is the internal bag of those primitives so
``compute_state`` can stay strictly downstream of the cashflow.
"""

from dataclasses import dataclass, field
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

    Prior discount portions (``*_discounted``) are tracked alongside
    prior payments so the next payment sees a previously-discounted
    installment as covered and does not re-target it.
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
    fine_discounted: Money = field(default_factory=Money.zero)
    mora_discounted: Money = field(default_factory=Money.zero)
    interest_discounted: Money = field(default_factory=Money.zero)
    principal_discounted: Money = field(default_factory=Money.zero)

    @property
    def total_discounted(self) -> Money:
        return self.fine_discounted + self.mora_discounted + self.interest_discounted + self.principal_discounted

    @property
    def balance(self) -> Money:
        total_expected = self.expected_principal + self.expected_interest + self.expected_mora + self.expected_fine
        total_paid = self.principal_paid + self.interest_paid + self.mora_paid + self.fine_paid
        remaining = total_expected - total_paid - self.total_discounted
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
    fine_discount_total: Money = None,
    mora_discount_total: Money = None,
    interest_discount_total: Money = None,
    principal_discount_total: Money = None,
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

    The ``*_discount_total`` parameters carry the discount portion that
    ``_apply_waivers_and_discounts`` already deducted from the loan-level
    caps. They are distributed across the same installments in
    fine→mora→interest→principal priority so the per-installment view
    can mark a discounted installment as fully paid. Discount portions
    do not consume the payment pool.

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
    fine_discount_remaining = fine_discount_total if fine_discount_total is not None else Money.zero()
    mora_discount_remaining = mora_discount_total if mora_discount_total is not None else Money.zero()
    interest_discount_remaining = interest_discount_total if interest_discount_total is not None else Money.zero()
    principal_discount_remaining = principal_discount_total if principal_discount_total is not None else Money.zero()
    allocations: List[Allocation] = []

    for exp in expectations:
        if exp.is_fully_paid or exp.balance <= balance_tolerance:
            continue

        fine_alloc, fine_remaining, fine_disc, fine_discount_remaining = _split_component(
            owed=exp.expected_fine - exp.fine_paid - exp.fine_discounted,
            pay_pool=fine_remaining,
            discount_pool=fine_discount_remaining,
        )
        mora_alloc, mora_remaining, mora_disc, mora_discount_remaining = _split_component(
            owed=exp.expected_mora - exp.mora_paid - exp.mora_discounted,
            pay_pool=mora_remaining,
            discount_pool=mora_discount_remaining,
        )
        interest_alloc, interest_remaining, interest_disc, interest_discount_remaining = _split_component(
            owed=exp.expected_interest - exp.interest_paid - exp.interest_discounted,
            pay_pool=interest_remaining,
            discount_pool=interest_discount_remaining,
        )
        principal_alloc, principal_remaining, principal_disc, principal_discount_remaining = _split_component(
            owed=exp.expected_principal - exp.principal_paid - exp.principal_discounted,
            pay_pool=principal_remaining,
            discount_pool=principal_discount_remaining,
        )

        total = fine_alloc + mora_alloc + interest_alloc + principal_alloc
        total_disc = fine_disc + mora_disc + interest_disc + principal_disc
        if total.is_positive():
            covered = total + total_disc + balance_tolerance >= exp.balance

            if not covered:
                shortfall = exp.balance - total - total_disc
                fine_extra, shortfall, fine_remaining = _absorb(shortfall, fine_remaining)
                mora_extra, shortfall, mora_remaining = _absorb(shortfall, mora_remaining)
                interest_extra, shortfall, interest_remaining = _absorb(shortfall, interest_remaining)
                principal_extra, shortfall, principal_remaining = _absorb(shortfall, principal_remaining)
                fine_alloc = fine_alloc + fine_extra
                mora_alloc = mora_alloc + mora_extra
                interest_alloc = interest_alloc + interest_extra
                principal_alloc = principal_alloc + principal_extra

        if total.is_positive() or total_disc.is_positive():
            allocations.append(
                Allocation(
                    installment_number=exp.number,
                    principal_allocated=principal_alloc,
                    interest_allocated=interest_alloc,
                    mora_allocated=mora_alloc,
                    fine_allocated=fine_alloc,
                    is_fully_covered=False,
                    fine_discounted=fine_disc,
                    mora_discounted=mora_disc,
                    interest_discounted=interest_disc,
                    principal_discounted=principal_disc,
                )
            )

    _apply_residual(allocations, expectations, fine_total, mora_total, interest_total, principal_total)
    return allocations


def _split_component(
    owed: Money,
    pay_pool: Money,
    discount_pool: Money,
) -> Tuple[Money, Money, Money, Money]:
    """Split a single component's obligation between payment and discount pools.

    Fills the payment allocation first (cash), then the discount
    allocation, capping both at the per-installment ``owed`` remaining
    after each step. Returns the four updated values:
    ``(pay_alloc, pay_pool_remaining, discount_alloc, discount_pool_remaining)``.
    """
    owed_raw = max(owed.raw_amount, 0)
    pay_raw = min(owed_raw, pay_pool.raw_amount)
    pay_alloc = Money(pay_raw)
    pay_pool = pay_pool - pay_alloc
    owed_after_pay = owed_raw - pay_raw
    disc_raw = min(owed_after_pay, discount_pool.raw_amount)
    discount_alloc = Money(disc_raw)
    discount_pool = discount_pool - discount_alloc
    return pay_alloc, pay_pool, discount_alloc, discount_pool


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
            fine_discounted=last.fine_discounted,
            mora_discounted=last.mora_discounted,
            interest_discounted=last.interest_discounted,
            principal_discounted=last.principal_discounted,
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
    fine_discount_total: Money = None,
    mora_discount_total: Money = None,
    interest_discount_total: Money = None,
    principal_discount_total: Money = None,
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

    The ``*_discount_total`` parameters carry the per-category discount
    amounts that ``_apply_waivers_and_discounts`` already absorbed at
    the loan level. They are forwarded to
    :func:`distribute_into_installments` so each allocation records the
    discount portion it covered, making
    :attr:`Installment.is_fully_paid` consistent with the loan-level
    ``remaining_balance``.

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
        fine_discount_total=fine_discount_total,
        mora_discount_total=mora_discount_total,
        interest_discount_total=interest_discount_total,
        principal_discount_total=principal_discount_total,
    )

    return fine_paid, mora_paid, interest_paid, principal_paid, allocations
