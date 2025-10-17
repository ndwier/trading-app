"""
Brokerage API integration module.
Supports Schwab and E-Trade for order execution and portfolio management.
"""

from .base import BaseBroker, Order
from .schwab import SchwabBroker
from .etrade import ETradeBroker
from .broker_manager import BrokerManager, get_broker_manager

__all__ = ['BaseBroker', 'Order', 'SchwabBroker', 'ETradeBroker', 'BrokerManager', 'get_broker_manager']

