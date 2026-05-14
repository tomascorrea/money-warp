"""Shared constants for engine submodules.

Re-exports the canonical balance-tolerance default defined alongside
``Installment``, so the engine and the model can never drift apart.
The literal lives in :mod:`money_warp.models.installment` because the
"balance" concept belongs to the installment view; the engine consumes
it.
"""

from ..models.installment import DEFAULT_BALANCE_TOLERANCE as BALANCE_TOLERANCE

__all__ = ["BALANCE_TOLERANCE"]
