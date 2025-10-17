"""
E*TRADE API integration using the official E*TRADE API.

Setup instructions:
1. Register at https://developer.etrade.com/
2. Create an app and get your Consumer Key and Secret
3. Set up OAuth1 authentication
4. Add credentials to .env:
   ETRADE_CONSUMER_KEY=your_consumer_key
   ETRADE_CONSUMER_SECRET=your_consumer_secret
   ETRADE_SANDBOX=true  # Set to false for production
"""

import requests
from requests_oauthlib import OAuth1Session
import logging
from typing import Dict, List, Optional
from decimal import Decimal
from .base import BaseBroker, Order


logger = logging.getLogger(__name__)


class ETradeBroker(BaseBroker):
    """E*TRADE brokerage integration."""
    
    # Sandbox URLs (for testing)
    SANDBOX_BASE_URL = "https://apisb.etrade.com"
    SANDBOX_AUTH_URL = "https://apisb.etrade.com/oauth"
    
    # Production URLs
    PROD_BASE_URL = "https://api.etrade.com"
    PROD_AUTH_URL = "https://api.etrade.com/oauth"
    
    def __init__(self, consumer_key: str, consumer_secret: str, sandbox: bool = True):
        super().__init__(consumer_key, consumer_secret)
        self.sandbox = sandbox
        self.base_url = self.SANDBOX_BASE_URL if sandbox else self.PROD_BASE_URL
        self.auth_url = self.SANDBOX_AUTH_URL if sandbox else self.PROD_AUTH_URL
        self.oauth_session = None
        self.account_id = None
    
    def authenticate(self) -> bool:
        """
        Authenticate with E*TRADE API using OAuth1.
        
        This is a placeholder - actual implementation requires:
        1. Request token
        2. User authorization (browser-based)
        3. Access token exchange
        """
        logger.warning("E*TRADE authentication requires OAuth1 flow - implement in production")
        return False
    
    def _get_session(self) -> OAuth1Session:
        """Get authenticated OAuth1 session."""
        if not self.oauth_session:
            raise ValueError("Not authenticated. Call authenticate() first.")
        return self.oauth_session
    
    def get_account_info(self) -> Dict:
        """Get E*TRADE account information."""
        if not self.authenticated:
            raise ValueError("Not authenticated")
        
        url = f"{self.base_url}/v1/accounts/list"
        session = self._get_session()
        response = session.get(url)
        response.raise_for_status()
        
        accounts = response.json().get('AccountListResponse', {}).get('Accounts', {}).get('Account', [])
        if accounts:
            self.account_id = accounts[0]['accountId']
            return {
                'account_id': accounts[0]['accountId'],
                'account_type': accounts[0].get('accountType'),
                'account_mode': accounts[0].get('accountMode'),
                'account_desc': accounts[0].get('accountDesc')
            }
        return {}
    
    def get_positions(self) -> List[Dict]:
        """Get current positions."""
        if not self.authenticated or not self.account_id:
            raise ValueError("Not authenticated or no account selected")
        
        url = f"{self.base_url}/v1/accounts/{self.account_id}/portfolio"
        session = self._get_session()
        response = session.get(url)
        response.raise_for_status()
        
        data = response.json()
        positions = data.get('PortfolioResponse', {}).get('AccountPortfolio', [{}])[0].get('Position', [])
        
        return [
            {
                'symbol': pos['symbolDescription'],
                'quantity': pos['quantity'],
                'market_value': pos['marketValue'],
                'average_price': pos['pricePaid'],
                'current_price': pos['Quick']['lastTrade'],
                'unrealized_pl': pos['totalGain']
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
        """Place an order with E*TRADE."""
        if not self.authenticated or not self.account_id:
            raise ValueError("Not authenticated or no account selected")
        
        # Build order request
        order_data = {
            "PlaceEquityOrder": {
                "orderType": order_type.upper(),
                "clientOrderId": f"insider-{symbol}-{int(datetime.now().timestamp())}",
                "Order": [
                    {
                        "allOrNone": "false",
                        "priceType": order_type.upper(),
                        "orderTerm": "GOOD_FOR_DAY",
                        "marketSession": "REGULAR",
                        "Instrument": [
                            {
                                "Product": {
                                    "securityType": "EQ",
                                    "symbol": symbol
                                },
                                "orderAction": "BUY" if side.lower() == 'buy' else "SELL",
                                "quantityType": "QUANTITY",
                                "quantity": quantity
                            }
                        ]
                    }
                ]
            }
        }
        
        if order_type.lower() == 'limit' and limit_price:
            order_data["PlaceEquityOrder"]["Order"][0]["limitPrice"] = float(limit_price)
        elif order_type.lower() == 'stop' and stop_price:
            order_data["PlaceEquityOrder"]["Order"][0]["stopPrice"] = float(stop_price)
        
        # First, preview the order
        url = f"{self.base_url}/v1/accounts/{self.account_id}/orders/preview"
        session = self._get_session()
        
        preview_response = session.post(url, json=order_data)
        preview_response.raise_for_status()
        
        preview_id = preview_response.json().get('PreviewOrderResponse', {}).get('PreviewIds', [{}])[0].get('previewId')
        
        # Place the order
        place_url = f"{self.base_url}/v1/accounts/{self.account_id}/orders/place"
        place_data = {
            "PlaceOrderRequest": {
                "orderType": order_type.upper(),
                "clientOrderId": order_data["PlaceEquityOrder"]["clientOrderId"],
                "PreviewIds": [{"previewId": preview_id}],
                "Order": order_data["PlaceEquityOrder"]["Order"]
            }
        }
        
        place_response = session.post(place_url, json=place_data)
        place_response.raise_for_status()
        
        result = place_response.json().get('PlaceOrderResponse', {})
        order_id = result.get('OrderIds', [{}])[0].get('orderId')
        
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
        if not self.authenticated or not self.account_id:
            raise ValueError("Not authenticated or no account selected")
        
        url = f"{self.base_url}/v1/accounts/{self.account_id}/orders/cancel"
        session = self._get_session()
        
        cancel_data = {
            "CancelOrderRequest": {
                "orderId": order_id
            }
        }
        
        response = session.put(url, json=cancel_data)
        return response.status_code == 200
    
    def get_order_status(self, order_id: str) -> Dict:
        """Get order status."""
        if not self.authenticated or not self.account_id:
            raise ValueError("Not authenticated or no account selected")
        
        url = f"{self.base_url}/v1/accounts/{self.account_id}/orders"
        session = self._get_session()
        response = session.get(url)
        response.raise_for_status()
        
        orders = response.json().get('OrdersResponse', {}).get('Order', [])
        for order in orders:
            if str(order.get('orderId')) == str(order_id):
                return {
                    'order_id': order_id,
                    'status': order.get('orderStatus'),
                    'filled_quantity': order.get('filledQuantity', 0),
                    'remaining_quantity': order.get('remainingQuantity', 0)
                }
        
        return {'order_id': order_id, 'status': 'not_found'}
    
    def get_quote(self, symbol: str) -> Dict:
        """Get quote for a symbol."""
        if not self.authenticated:
            raise ValueError("Not authenticated")
        
        url = f"{self.base_url}/v1/market/quote/{symbol}"
        session = self._get_session()
        response = session.get(url)
        response.raise_for_status()
        
        quote_data = response.json().get('QuoteResponse', {}).get('QuoteData', [{}])[0]
        all_quote = quote_data.get('All', {})
        
        return {
            'symbol': symbol,
            'bid': all_quote.get('bid'),
            'ask': all_quote.get('ask'),
            'last': all_quote.get('lastTrade'),
            'volume': all_quote.get('totalVolume')
        }


# Import datetime for client_order_id generation
from datetime import datetime

