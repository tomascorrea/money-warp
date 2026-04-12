"""Allocation data structure for per-installment payment breakdown."""

from dataclasses import dataclass

from ..money import Money


@dataclass(frozen=True)
class Allocation:
    """Breakdown of a payment's allocation to a single installment.

    Each allocation shows how much principal, interest, mora, and fine
    from a payment were attributed to a specific installment.
    """

    installment_number: int
    principal_allocated: Money
    interest_allocated: Money
    mora_allocated: Money
    fine_allocated: Money
    is_fully_covered: bool

    @property
    def total_allocated(self) -> Money:
        """Sum of all components allocated to this installment."""
        return self.principal_allocated + self.interest_allocated + self.mora_allocated + self.fine_allocated
