"""SQLAlchemy custom types and bridge decorators for money-warp.

Requires the ``sa`` extra::

    pip install money-warp[sa]
"""

from money_warp.ext.sa.bridge import loan_bridge, settlement_bridge
from money_warp.ext.sa.types import InterestRateType, MoneyType, RateType

__all__ = [
    "MoneyType",
    "RateType",
    "InterestRateType",
    "settlement_bridge",
    "loan_bridge",
]
