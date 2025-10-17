"""
Base broker class for brokerage API integration.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from decimal import Decimal
from datetime import datetime


class BaseBroker(ABC):
    """Abstract base class for brokerage integrations."""
    
    def __init__(self, api_key: str, api_secret: str, **kwargs):
        self.api_key = api_key
        self.api_secret = api_secret
        self.authenticated = False
    
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with the brokerage API."""
        pass
    
    @abstractmethod
    def get_account_info(self) -> Dict:
        """Get account information and balances."""
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Dict]:
        """Get current portfolio positions."""
        pass
    
    @abstractmethod
    def place_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str,  # 'market', 'limit', 'stop'
        side: str,  # 'buy', 'sell'
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None
    ) -> Dict:
        """Place a trade order."""
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        pass
    
    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict:
        """Get status of a specific order."""
        pass
    
    @abstractmethod
    def get_quote(self, symbol: str) -> Dict:
        """Get current quote for a symbol."""
        pass


class Order:
    """Order representation."""
    
    def __init__(
        self,
        symbol: str,
        quantity: int,
        order_type: str,
        side: str,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None
    ):
        self.symbol = symbol
        self.quantity = quantity
        self.order_type = order_type
        self.side = side
        self.limit_price = limit_price
        self.stop_price = stop_price
        self.status = 'pending'
        self.order_id = None
        self.filled_quantity = 0
        self.average_fill_price = None
        self.created_at = datetime.now()
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'quantity': self.quantity,
            'order_type': self.order_type,
            'side': self.side,
            'limit_price': float(self.limit_price) if self.limit_price else None,
            'stop_price': float(self.stop_price) if self.stop_price else None,
            'status': self.status,
            'order_id': self.order_id,
            'filled_quantity': self.filled_quantity,
            'average_fill_price': float(self.average_fill_price) if self.average_fill_price else None,
            'created_at': self.created_at.isoformat()
        }

