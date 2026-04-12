"""Backward-compatible re-exports from :mod:`money_warp.engines`.

All shared engine logic now lives in the ``money_warp.engines``
package.  This module re-exports every public name so that existing
code importing from ``money_warp.loan.engines`` continues to work.
"""

from ..engines import (
    InterestCalculator,
    LoanState,
    MoraRateCallback,
    MoraStrategy,
    allocate_payment,
    allocate_payment_into_installments,
    apply_tolerance_adjustment,
    build_installments,
    compute_fines_at,
    compute_state,
    covered_due_date_count,
    distribute_into_installments,
    is_payment_late,
)

__all__ = [
    "InterestCalculator",
    "LoanState",
    "MoraRateCallback",
    "MoraStrategy",
    "allocate_payment",
    "allocate_payment_into_installments",
    "apply_tolerance_adjustment",
    "build_installments",
    "compute_fines_at",
    "compute_state",
    "covered_due_date_count",
    "distribute_into_installments",
    "is_payment_late",
]
