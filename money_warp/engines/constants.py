"""Shared constants for engine submodules."""

from ..money import Money

# Sub-cent tolerance for internal balance comparisons (rounding artifacts
# from our own calculations).
BALANCE_TOLERANCE = Money("0.01")
