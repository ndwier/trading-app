"""
Brokerage API integration module.
Supports Schwab and E-Trade for order execution and portfolio management.
"""

from .base import BaseBroker
from .schwab import SchwabBroker
from .etrade import ETradeBroker

__all__ = ['BaseBroker', 'SchwabBroker', 'ETradeBroker']

