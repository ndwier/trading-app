"""
Broker manager for handling multiple brokerage connections.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
import os

from .schwab import SchwabBroker
from .etrade import ETradeBroker

logger = logging.getLogger(__name__)


class BrokerManager:
    """Manages multiple brokerage connections."""
    
    def __init__(self):
        self.brokers: Dict[str, any] = {}
        self.active_broker = None
        
    def add_schwab(self, app_key: str, app_secret: str, redirect_uri: str) -> bool:
        """Add Schwab broker connection."""
        try:
            broker = SchwabBroker(app_key, app_secret, redirect_uri)
            self.brokers['schwab'] = broker
            logger.info("Schwab broker added successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to add Schwab broker: {e}")
            return False
    
    def add_etrade(self, consumer_key: str, consumer_secret: str, sandbox: bool = True) -> bool:
        """Add E*TRADE broker connection."""
        try:
            broker = ETradeBroker(consumer_key, consumer_secret, sandbox)
            self.brokers['etrade'] = broker
            logger.info(f"E*TRADE broker added successfully (sandbox={sandbox})")
            return True
        except Exception as e:
            logger.error(f"Failed to add E*TRADE broker: {e}")
            return False
    
    def set_active_broker(self, broker_name: str) -> bool:
        """Set the active broker."""
        if broker_name in self.brokers:
            self.active_broker = broker_name
            logger.info(f"Active broker set to: {broker_name}")
            return True
        logger.warning(f"Broker '{broker_name}' not found")
        return False
    
    def get_broker(self, broker_name: str = None):
        """Get a specific broker or the active broker."""
        if broker_name:
            return self.brokers.get(broker_name)
        if self.active_broker:
            return self.brokers.get(self.active_broker)
        return None
    
    def authenticate_broker(self, broker_name: str) -> Dict:
        """
        Authenticate a broker.
        
        Note: This is a placeholder. Real OAuth flows need browser interaction.
        """
        broker = self.brokers.get(broker_name)
        if not broker:
            return {'success': False, 'error': f'Broker {broker_name} not found'}
        
        try:
            success = broker.authenticate()
            return {
                'success': success,
                'broker': broker_name,
                'message': 'Authentication flow initiated' if success else 'Authentication requires OAuth flow'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_all_statuses(self) -> List[Dict]:
        """Get status of all configured brokers."""
        statuses = []
        
        for broker_name, broker in self.brokers.items():
            status = {
                'name': broker_name,
                'connected': broker.authenticated,
                'active': broker_name == self.active_broker
            }
            
            if broker.authenticated:
                try:
                    account = broker.get_account_info()
                    status['account'] = account
                except Exception as e:
                    status['error'] = str(e)
            
            statuses.append(status)
        
        return statuses
    
    def get_positions(self, broker_name: str = None) -> List[Dict]:
        """Get positions from a broker."""
        broker = self.get_broker(broker_name)
        if not broker:
            return []
        
        try:
            return broker.get_positions()
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    def preview_signal_order(self, signal_dict: Dict, broker_name: str = None) -> Dict:
        """
        Preview an order based on a signal.
        
        Args:
            signal_dict: Signal with ticker, action, target_price, confidence
            broker_name: Which broker to use (None = active)
        
        Returns:
            Order preview with estimated cost, fees, etc.
        """
        broker = self.get_broker(broker_name)
        if not broker:
            return {'error': 'No active broker'}
        
        try:
            # Get current quote
            quote = broker.get_quote(signal_dict['ticker'])
            
            # Calculate order details
            ticker = signal_dict['ticker']
            action = signal_dict.get('action', 'BUY')
            target_price = signal_dict.get('target_price')
            confidence = signal_dict.get('confidence', 0.5)
            
            # Simple position sizing (could be much more sophisticated)
            # For now: higher confidence = larger position
            max_position_value = 1000  # $1000 max per trade for safety
            position_value = max_position_value * confidence
            
            current_price = quote.get('last') or quote.get('ask')
            if not current_price:
                return {'error': 'Could not get current price'}
            
            quantity = int(position_value / current_price)
            if quantity == 0:
                quantity = 1
            
            order_preview = {
                'ticker': ticker,
                'side': action.lower(),
                'quantity': quantity,
                'order_type': 'limit',
                'limit_price': target_price if target_price else current_price,
                'current_price': current_price,
                'estimated_cost': quantity * (target_price if target_price else current_price),
                'confidence': confidence,
                'quote': quote,
                'broker': broker_name or self.active_broker
            }
            
            return order_preview
            
        except Exception as e:
            logger.error(f"Failed to preview order: {e}")
            return {'error': str(e)}
    
    def execute_signal(
        self,
        signal_dict: Dict,
        broker_name: str = None,
        quantity_override: int = None
    ) -> Dict:
        """
        Execute a trade based on a signal.
        
        Args:
            signal_dict: Signal with ticker, action, target_price
            broker_name: Which broker to use
            quantity_override: Override calculated quantity
        
        Returns:
            Order execution result
        """
        broker = self.get_broker(broker_name)
        if not broker or not broker.authenticated:
            return {'error': 'Broker not authenticated'}
        
        try:
            # Preview first
            preview = self.preview_signal_order(signal_dict, broker_name)
            if 'error' in preview:
                return preview
            
            quantity = quantity_override if quantity_override else preview['quantity']
            
            # Place the order
            result = broker.place_order(
                symbol=signal_dict['ticker'],
                quantity=quantity,
                order_type='limit',
                side=signal_dict.get('action', 'BUY').lower(),
                limit_price=preview['limit_price']
            )
            
            return {
                'success': True,
                'order': result,
                'signal': signal_dict,
                'broker': broker_name or self.active_broker
            }
            
        except Exception as e:
            logger.error(f"Failed to execute signal: {e}")
            return {'error': str(e)}


# Global broker manager instance
_broker_manager = None


def get_broker_manager() -> BrokerManager:
    """Get or create the global broker manager."""
    global _broker_manager
    if _broker_manager is None:
        _broker_manager = BrokerManager()
        
        # Auto-configure from environment
        schwab_key = os.getenv('SCHWAB_APP_KEY')
        schwab_secret = os.getenv('SCHWAB_APP_SECRET')
        if schwab_key and schwab_secret:
            _broker_manager.add_schwab(
                schwab_key,
                schwab_secret,
                os.getenv('SCHWAB_REDIRECT_URI', 'https://localhost:8080/callback')
            )
        
        etrade_key = os.getenv('ETRADE_CONSUMER_KEY')
        etrade_secret = os.getenv('ETRADE_CONSUMER_SECRET')
        if etrade_key and etrade_secret:
            _broker_manager.add_etrade(
                etrade_key,
                etrade_secret,
                os.getenv('ETRADE_SANDBOX', 'true').lower() == 'true'
            )
    
    return _broker_manager

