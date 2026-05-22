"""Allocation data structure for per-installment payment breakdown."""

from dataclasses import dataclass, field

from ..types.money import Money


@dataclass(frozen=True)
class Allocation:
    """Breakdown of a payment's allocation to a single installment.

    Each allocation shows how much principal, interest, mora, and fine
    from a payment were attributed to a specific installment, plus how
    much of the payment's ``discount`` covered each component. The
    discount fields default to zero so payments without a discount keep
    their original shape.
    """

    installment_number: int
    principal_allocated: Money
    interest_allocated: Money
    mora_allocated: Money
    fine_allocated: Money
    is_fully_covered: bool
    # ``dataclass`` rejects any non-(list/dict/set) instance as a plain
    # default — even immutable ones — so ``Money`` must be supplied via
    # ``default_factory`` despite being effectively immutable.
    fine_discounted: Money = field(default_factory=Money.zero)
    mora_discounted: Money = field(default_factory=Money.zero)
    interest_discounted: Money = field(default_factory=Money.zero)
    principal_discounted: Money = field(default_factory=Money.zero)

    @property
    def total_allocated(self) -> Money:
        """Sum of all components allocated to this installment."""
        return self.principal_allocated + self.interest_allocated + self.mora_allocated + self.fine_allocated

    @property
    def total_discounted(self) -> Money:
        """Sum of discount portions absorbed by this installment.

        Mirrors :attr:`total_allocated` for the payment's ``discount``
        contribution. A payment without a discount has every component
        at zero.
        """
        return self.fine_discounted + self.mora_discounted + self.interest_discounted + self.principal_discounted
