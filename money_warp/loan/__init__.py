"""Loan module for personal loan modeling with flexible payment schedules."""

from .allocation import Allocation
from .installment import Installment
from .settlement import AnticipationResult, Settlement

__all__ = [
    "Allocation",
    "AnticipationResult",
    "Installment",
    "Loan",
    "Settlement",
]


def __getattr__(name: str):  # type: ignore[misc]
    if name == "Loan":
        from .loan import Loan

        return Loan
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
