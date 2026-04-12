"""Loan module for personal loan modeling with flexible payment schedules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .allocation import Allocation
from .installment import Installment
from .settlement import AnticipationResult, Settlement

if TYPE_CHECKING:
    from .loan import Loan

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

        globals()["Loan"] = Loan
        return Loan
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
