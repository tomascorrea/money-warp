"""Protocol for resolving mora interest rates per billing cycle."""

from datetime import date
from typing import Protocol, runtime_checkable

from ..interest_rate import InterestRate


@runtime_checkable
class MoraRateResolver(Protocol):
    """Callable that returns the mora rate for a given billing cycle.

    Receives the cycle's reference date (typically the closing date)
    and the base mora rate configured on the loan.  Returns the
    ``InterestRate`` to use for mora computation in that cycle.

    Implementations are free to ignore the base rate and return an
    entirely independent value, or to adjust it (e.g. add a spread
    on top of an external index).
    """

    def __call__(self, reference_date: date, base_mora_rate: InterestRate) -> InterestRate: ...
