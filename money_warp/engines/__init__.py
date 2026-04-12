"""Shared engine building blocks for loan products.

This package contains stateless computation logic used by multiple
product modules (``loan``, ``billing_cycle_loan``).  Product-specific
wiring lives in each product's own ``engines`` module.

Submodules
----------
interest
    Interest calculation primitives (InterestCalculator, MoraStrategy).
allocation
    Payment allocation and per-installment distribution.
fines
    Fine computation and late-payment detection.
forward_pass
    Unified forward pass, installment snapshots, tolerance adjustments.
"""

from .allocation import (
    allocate_payment,
    allocate_payment_into_installments,
    distribute_into_installments,
)
from .fines import compute_fines_at, is_payment_late
from .forward_pass import (
    LoanState,
    apply_tolerance_adjustment,
    build_installments,
    compute_state,
    covered_due_date_count,
)
from .interest import InterestCalculator, MoraRateCallback, MoraStrategy

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
