"""
Schwab API integration using the official Schwab Trader API.

Setup instructions:
1. Register at https://developer.schwab.com/
2. Create an app and get your App Key and Secret
3. Set up OAuth2 authentication
4. Add credentials to .env:
   SCHWAB_APP_KEY=your_app_key
   SCHWAB_APP_SECRET=your_app_secret
   SCHWAB_REDIRECT_URI=https://localhost:8080/callback
"""

import requests
import logging
from typing import Dict, List, Optional
from decimal import Decimal
from .base import BaseBroker, Order


logger = logging.getLogger(__name__)


class SchwabBroker(BaseBroker):
    """Schwab brokerage integration."""
    
    BASE_URL = "https://api.schwabapi.com/trader/v1"
    AUTH_URL = "https://api.schwabapi.com/v1/oauth"
    
    def __init__(self, app_key: str, app_secret: str, redirect_uri: str = "https://localhost:8080/callback"):
        super().__init__(app_key, app_secret)
        self.redirect_uri = redirect_uri
        self.access_token = None
        self.refresh_token = None
        self.account_hash = None
    
    def authenticate(self) -> bool:
        """
        Authenticate with Schwab API using OAuth2.
        
        This is a placeholder - actual implementation requires:
        1. Browser-based OAuth flow
        2. Code exchange for tokens
        3. Token refresh logic
        """
        logger.warning("Schwab authentication requires OAuth2 flow - implement in production")
        return False
    
    def _get_headers(self) -> Dict:
        """Get request headers with authentication."""
        if not self.access_token:
            raise ValueError("Not authenticated. Call authenticate() first.")
        
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    
    def get_account_info(self) -> Dict:
        """Get Schwab account information."""
        if not self.authenticated:
            raise ValueError("Not authenticated")
        
        url = f"{self.BASE_URL}/accounts"
        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()
        
        accounts = response.json()
        if accounts:
            self.account_hash = accounts[0]['hashValue']
            return accounts[0]
        return {}
    
    def get_positions(self) -> List[Dict]:
        """Get current positions."""
        if not self.authenticated or not self.account_hash:
            raise ValueError("Not authenticated or no account selected")
        
        url = f"{self.BASE_URL}/accounts/{self.account_hash}"
        response = requests.get(url, headers=self._get_headers(), params={'fields': 'positions'})
        response.raise_for_status()
        
        data = response.json()
        positions = data.get('securitiesAccount', {}).get('positions', [])
        
        return [
            {
                'symbol': pos['instrument']['symbol'],
                'quantity': pos['longQuantity'],
                'market_value': pos['marketValue'],
                'average_price': pos['averagePrice'],
                'current_price': pos['instrument'].get('close', 0),
                'unrealized_pl': pos.get('currentDayProfitLoss', 0)
            }
            for pos in positions
        ]
    
    def place_order(
        self,
        symbol: str,
        quantity: int,
        order_type: str,
        side: str,
        limit_price: Optional[Decimal] = None,
        stop_price: Optional[Decimal] = None
    ) -> Dict:
        """Place an order with Schwab."""
        if not self.authenticated or not self.account_hash:
            raise ValueError("Not authenticated or no account selected")
        
        order_data = {
            "orderType": order_type.upper(),
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": "BUY" if side.lower() == 'buy' else "SELL",
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }
        
        if order_type.lower() == 'limit' and limit_price:
            order_data["price"] = float(limit_price)
        elif order_type.lower() == 'stop' and stop_price:
            order_data["stopPrice"] = float(stop_price)
        
        url = f"{self.BASE_URL}/accounts/{self.account_hash}/orders"
        response = requests.post(url, headers=self._get_headers(), json=order_data)
        response.raise_for_status()
        
        # Extract order ID from Location header
        location = response.headers.get('Location', '')
        order_id = location.split('/')[-1] if location else None
        
        return {
            'order_id': order_id,
            'status': 'submitted',
            'symbol': symbol,
            'quantity': quantity,
            'side': side,
            'type': order_type
        }
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        if not self.authenticated or not self.account_hash:
            raise ValueError("Not authenticated or no account selected")
        
        url = f"{self.BASE_URL}/accounts/{self.account_hash}/orders/{order_id}"
        response = requests.delete(url, headers=self._get_headers())
        return response.status_code == 200
    
    def get_order_status(self, order_id: str) -> Dict:
        """Get order status."""
        if not self.authenticated or not self.account_hash:
            raise ValueError("Not authenticated or no account selected")
        
        url = f"{self.BASE_URL}/accounts/{self.account_hash}/orders/{order_id}"
        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()
        
        order = response.json()
        return {
            'order_id': order_id,
            'status': order.get('status'),
            'filled_quantity': order.get('filledQuantity', 0),
            'remaining_quantity': order.get('remainingQuantity', 0)
        }
    
    def get_quote(self, symbol: str) -> Dict:
        """Get quote for a symbol."""
        if not self.authenticated:
            raise ValueError("Not authenticated")
        
        url = f"{self.BASE_URL}/marketdata/v1/{symbol}/quotes"
        response = requests.get(url, headers=self._get_headers())
        response.raise_for_status()
        
        quote = response.json()
        return {
            'symbol': symbol,
            'bid': quote.get('bidPrice'),
            'ask': quote.get('askPrice'),
            'last': quote.get('lastPrice'),
            'volume': quote.get('totalVolume')
        }

