"""
Paper Trading Portfolio System.

Allows users to test signals without risking real money.
Tracks hypothetical trades, P/L, and performance metrics.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from decimal import Decimal
import yfinance as yf

from src.database import get_session
from src.database.models import PortfolioTransaction, Signal, TransactionType

logger = logging.getLogger(__name__)


class PaperTradingPortfolio:
    """Manages a paper trading portfolio."""
    
    def __init__(self, starting_capital: float = 100000.0):
        self.starting_capital = starting_capital
    
    def get_portfolio_summary(self) -> Dict:
        """Get current portfolio summary."""
        with get_session() as session:
            transactions = session.query(PortfolioTransaction).order_by(
                PortfolioTransaction.transaction_date.desc()
            ).all()
            
            if not transactions:
                return {
                    'starting_capital': self.starting_capital,
                    'current_value': self.starting_capital,
                    'cash': self.starting_capital,
                    'positions': [],
                    'total_return': 0,
                    'total_return_pct': 0,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0
                }
            
            # Calculate current positions
            positions = self._calculate_positions(transactions)
            
            # Get current prices
            total_position_value = 0
            for ticker, pos in positions.items():
                if pos['quantity'] > 0:
                    current_price = self._get_current_price(ticker)
                    if current_price:
                        pos['current_price'] = current_price
                        pos['market_value'] = current_price * pos['quantity']
                        pos['unrealized_pl'] = pos['market_value'] - (pos['avg_price'] * pos['quantity'])
                        pos['unrealized_pl_pct'] = (pos['unrealized_pl'] / (pos['avg_price'] * pos['quantity'])) * 100
                        total_position_value += pos['market_value']
            
            # Calculate cash (starting capital - money spent + money from sales)
            money_out = sum([t.total_amount for t in transactions if t.transaction_type in [TransactionType.BUY, TransactionType.OPTION_BUY]])
            money_in = sum([t.total_amount for t in transactions if t.transaction_type in [TransactionType.SELL, TransactionType.OPTION_SELL]])
            cash = self.starting_capital - money_out + money_in
            
            current_value = cash + total_position_value
            total_return = current_value - self.starting_capital
            total_return_pct = (total_return / self.starting_capital) * 100
            
            # Count wins/losses
            closed_trades = self._get_closed_trades(transactions)
            winning = len([t for t in closed_trades if t['profit'] > 0])
            losing = len([t for t in closed_trades if t['profit'] < 0])
            
            return {
                'starting_capital': self.starting_capital,
                'current_value': current_value,
                'cash': cash,
                'positions_value': total_position_value,
                'positions': [
                    {
                        'ticker': ticker,
                        **pos
                    }
                    for ticker, pos in positions.items() if pos['quantity'] > 0
                ],
                'total_return': total_return,
                'total_return_pct': total_return_pct,
                'total_trades': len(transactions),
                'winning_trades': winning,
                'losing_trades': losing,
                'win_rate': (winning / len(closed_trades) * 100) if closed_trades else 0
            }
    
    def _calculate_positions(self, transactions: List[PortfolioTransaction]) -> Dict:
        """Calculate current positions from transaction history."""
        positions = {}
        
        for t in transactions:
            ticker = t.ticker
            
            if ticker not in positions:
                positions[ticker] = {
                    'quantity': 0,
                    'avg_price': 0,
                    'total_cost': 0
                }
            
            pos = positions[ticker]
            
            if t.transaction_type in [TransactionType.BUY, TransactionType.OPTION_BUY]:
                # Buying - increase position
                new_quantity = pos['quantity'] + t.quantity
                new_cost = pos['total_cost'] + t.total_amount
                pos['quantity'] = new_quantity
                pos['total_cost'] = new_cost
                pos['avg_price'] = new_cost / new_quantity if new_quantity > 0 else 0
                
            elif t.transaction_type in [TransactionType.SELL, TransactionType.OPTION_SELL]:
                # Selling - decrease position
                pos['quantity'] -= t.quantity
                if pos['quantity'] < 0:
                    pos['quantity'] = 0  # Safety check
        
        return positions
    
    def _get_closed_trades(self, transactions: List[PortfolioTransaction]) -> List[Dict]:
        """Identify closed trades (buy + sell pairs) and calculate profit."""
        closed = []
        positions_tracker = {}
        
        for t in transactions:
            ticker = t.ticker
            
            if ticker not in positions_tracker:
                positions_tracker[ticker] = []
            
            if t.transaction_type in [TransactionType.BUY, TransactionType.OPTION_BUY]:
                # Add to open positions
                positions_tracker[ticker].append({
                    'quantity': t.quantity,
                    'price': t.price_per_share,
                    'date': t.transaction_date
                })
            
            elif t.transaction_type in [TransactionType.SELL, TransactionType.OPTION_SELL]:
                # Close positions FIFO
                qty_to_close = t.quantity
                sell_price = t.price_per_share
                
                while qty_to_close > 0 and positions_tracker[ticker]:
                    buy_pos = positions_tracker[ticker][0]
                    
                    close_qty = min(qty_to_close, buy_pos['quantity'])
                    profit = (sell_price - buy_pos['price']) * close_qty
                    
                    closed.append({
                        'ticker': ticker,
                        'quantity': close_qty,
                        'buy_price': buy_pos['price'],
                        'sell_price': sell_price,
                        'profit': profit,
                        'profit_pct': ((sell_price - buy_pos['price']) / buy_pos['price']) * 100,
                        'buy_date': buy_pos['date'],
                        'sell_date': t.transaction_date,
                        'hold_days': (t.transaction_date - buy_pos['date']).days
                    })
                    
                    buy_pos['quantity'] -= close_qty
                    qty_to_close -= close_qty
                    
                    if buy_pos['quantity'] <= 0:
                        positions_tracker[ticker].pop(0)
        
        return closed
    
    def _get_current_price(self, ticker: str) -> Optional[float]:
        """Get current price for a ticker."""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period='1d')
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
        except Exception as e:
            logger.error(f"Error getting price for {ticker}: {e}")
        return None
    
    def execute_signal(self, signal: Signal, quantity_override: Optional[int] = None) -> Dict:
        """Execute a paper trade based on a signal."""
        try:
            # Get current price
            current_price = self._get_current_price(signal.ticker)
            
            if not current_price:
                return {'success': False, 'error': 'Could not get current price'}
            
            # Calculate quantity (simple for now - $1000 per trade * signal strength)
            base_amount = 1000 * signal.strength
            quantity = quantity_override if quantity_override else int(base_amount / current_price)
            
            if quantity == 0:
                quantity = 1
            
            total_amount = current_price * quantity
            
            # Create transaction
            with get_session() as session:
                transaction = PortfolioTransaction(
                    ticker=signal.ticker,
                    transaction_type=signal.signal_type,
                    quantity=quantity,
                    price_per_share=Decimal(str(current_price)),
                    total_amount=Decimal(str(total_amount)),
                    transaction_date=datetime.now(),
                    signal_id=signal.signal_id,
                    notes=f"Auto-executed from signal (confidence: {signal.strength*100:.1f}%)"
                )
                
                session.add(transaction)
                session.commit()
                
                return {
                    'success': True,
                    'transaction_id': transaction.transaction_id,
                    'ticker': signal.ticker,
                    'quantity': quantity,
                    'price': current_price,
                    'total': total_amount,
                    'type': signal.signal_type.value if hasattr(signal.signal_type, 'value') else signal.signal_type
                }
                
        except Exception as e:
            logger.error(f"Error executing paper trade: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Get trade history."""
        with get_session() as session:
            transactions = session.query(PortfolioTransaction).order_by(
                PortfolioTransaction.transaction_date.desc()
            ).limit(limit).all()
            
            history = []
            for t in transactions:
                history.append({
                    'date': t.transaction_date.strftime('%Y-%m-%d %H:%M'),
                    'ticker': t.ticker,
                    'type': t.transaction_type.value if hasattr(t.transaction_type, 'value') else t.transaction_type,
                    'quantity': t.quantity,
                    'price': float(t.price_per_share),
                    'total': float(t.total_amount),
                    'notes': t.notes or ''
                })
            
            return history
    
    def reset_portfolio(self) -> Dict:
        """Reset portfolio to starting capital (delete all transactions)."""
        with get_session() as session:
            deleted = session.query(PortfolioTransaction).delete()
            session.commit()
            
            return {
                'success': True,
                'deleted_transactions': deleted,
                'new_balance': self.starting_capital
            }

