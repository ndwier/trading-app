"""
Price Service for market data.

Uses yfinance for free, delayed market data.
Provides price context for insider trades.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import yfinance as yf
from decimal import Decimal

logger = logging.getLogger(__name__)


class PriceService:
    """Manages price data and comparisons."""
    
    def __init__(self):
        self.cache = {}  # Simple in-memory cache
        self.cache_duration = timedelta(minutes=15)
    
    def get_current_price(self, ticker: str) -> Optional[Dict]:
        """Get current price and basic info."""
        cache_key = f"{ticker}_current"
        
        # Check cache
        if cache_key in self.cache:
            cached_data, cached_time = self.cache[cache_key]
            if datetime.now() - cached_time < self.cache_duration:
                return cached_data
        
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period='5d')
            
            if hist.empty:
                return None
            
            current_price = float(hist['Close'].iloc[-1])
            
            data = {
                'ticker': ticker,
                'current_price': current_price,
                'prev_close': float(hist['Close'].iloc[-2]) if len(hist) > 1 else current_price,
                'change': current_price - float(hist['Close'].iloc[-2]) if len(hist) > 1 else 0,
                'change_pct': ((current_price - float(hist['Close'].iloc[-2])) / float(hist['Close'].iloc[-2]) * 100) if len(hist) > 1 else 0,
                'volume': int(hist['Volume'].iloc[-1]) if 'Volume' in hist else 0,
                'market_cap': info.get('marketCap', 0),
                'timestamp': datetime.now().isoformat()
            }
            
            # Cache it
            self.cache[cache_key] = (data, datetime.now())
            
            return data
            
        except Exception as e:
            logger.error(f"Error getting current price for {ticker}: {e}")
            return None
    
    def get_price_at_date(self, ticker: str, date: datetime) -> Optional[float]:
        """Get historical price at a specific date."""
        try:
            stock = yf.Ticker(ticker)
            
            # Get a range around the date
            start = date - timedelta(days=5)
            end = date + timedelta(days=5)
            
            hist = stock.history(start=start, end=end)
            
            if hist.empty:
                return None
            
            # Try to get exact date, or closest
            date_str = date.strftime('%Y-%m-%d')
            
            if date_str in hist.index.strftime('%Y-%m-%d'):
                idx = hist.index.strftime('%Y-%m-%d').tolist().index(date_str)
                return float(hist['Close'].iloc[idx])
            
            # Return closest date
            return float(hist['Close'].iloc[0])
            
        except Exception as e:
            logger.error(f"Error getting historical price for {ticker} at {date}: {e}")
            return None
    
    def get_price_context(self, ticker: str, trade_date: datetime, trade_price: Optional[float] = None) -> Dict:
        """
        Get price context for a trade.
        
        Returns comparison of insider's price vs current price.
        """
        current_data = self.get_current_price(ticker)
        
        if not current_data:
            return {
                'error': 'Could not fetch price data',
                'ticker': ticker
            }
        
        current_price = current_data['current_price']
        
        # Get price at trade date if not provided
        if not trade_price:
            trade_price = self.get_price_at_date(ticker, trade_date)
        
        if not trade_price:
            return {
                'ticker': ticker,
                'current_price': current_price,
                'trade_date': trade_date.strftime('%Y-%m-%d'),
                'error': 'Could not find historical price'
            }
        
        # Calculate comparison
        price_change = current_price - trade_price
        price_change_pct = (price_change / trade_price) * 100
        
        # Determine if current price is better/worse for buying
        better_entry = current_price < trade_price
        
        return {
            'ticker': ticker,
            'current_price': current_price,
            'trade_price': trade_price,
            'trade_date': trade_date.strftime('%Y-%m-%d'),
            'price_change': price_change,
            'price_change_pct': price_change_pct,
            'better_entry': better_entry,
            'message': self._generate_message(current_price, trade_price, better_entry),
            'days_since_trade': (datetime.now() - trade_date).days
        }
    
    def get_price_history_with_trades(
        self, 
        ticker: str, 
        trades: List[Dict],
        period: str = '1y'
    ) -> Dict:
        """
        Get price history with insider trade markers.
        
        Args:
            ticker: Stock ticker
            trades: List of trades with date, price, type
            period: '1mo', '3mo', '6mo', '1y', '2y', '5y'
        """
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)
            
            if hist.empty:
                return {'error': 'No price data available'}
            
            # Format price data
            price_data = []
            for date, row in hist.iterrows():
                price_data.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'open': float(row['Open']),
                    'high': float(row['High']),
                    'low': float(row['Low']),
                    'close': float(row['Close']),
                    'volume': int(row['Volume'])
                })
            
            # Match trades to price data
            trade_markers = []
            for trade in trades:
                trade_date = trade['date'] if isinstance(trade['date'], datetime) else datetime.strptime(trade['date'], '%Y-%m-%d')
                
                # Find closest price data point
                closest_price = None
                for p in price_data:
                    p_date = datetime.strptime(p['date'], '%Y-%m-%d')
                    if abs((p_date - trade_date).days) <= 3:
                        closest_price = p['close']
                        break
                
                trade_markers.append({
                    'date': trade_date.strftime('%Y-%m-%d'),
                    'type': trade.get('type', 'BUY'),
                    'price': trade.get('price', closest_price),
                    'amount': trade.get('amount', 0),
                    'insider': trade.get('insider', 'Unknown')
                })
            
            # Get current price
            current = self.get_current_price(ticker)
            
            return {
                'ticker': ticker,
                'period': period,
                'current_price': current['current_price'] if current else price_data[-1]['close'],
                'price_data': price_data,
                'trade_markers': trade_markers,
                'stats': {
                    'high': max([p['high'] for p in price_data]),
                    'low': min([p['low'] for p in price_data]),
                    'avg_volume': sum([p['volume'] for p in price_data]) / len(price_data)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting price history for {ticker}: {e}")
            return {'error': str(e)}
    
    def _generate_message(self, current_price: float, trade_price: float, better_entry: bool) -> str:
        """Generate human-readable message about price comparison."""
        diff_pct = abs(((current_price - trade_price) / trade_price) * 100)
        
        if better_entry:
            if diff_pct < 2:
                return f"Current price is similar to insider's price (within 2%)"
            elif diff_pct < 5:
                return f"Current price is {diff_pct:.1f}% LOWER than insider's price - slightly better entry!"
            elif diff_pct < 10:
                return f"Current price is {diff_pct:.1f}% LOWER than insider's price - good entry!"
            else:
                return f"Current price is {diff_pct:.1f}% LOWER than insider's price - great entry opportunity!"
        else:
            if diff_pct < 2:
                return f"Current price is similar to insider's price (within 2%)"
            elif diff_pct < 5:
                return f"Current price is {diff_pct:.1f}% HIGHER than insider's price - slightly worse entry"
            elif diff_pct < 10:
                return f"Current price is {diff_pct:.1f}% HIGHER than insider's price - consider waiting"
            else:
                return f"Current price is {diff_pct:.1f}% HIGHER than insider's price - may want to wait for pullback"
    
    def get_batch_prices(self, tickers: List[str]) -> Dict[str, Dict]:
        """Get current prices for multiple tickers."""
        results = {}
        
        for ticker in tickers:
            data = self.get_current_price(ticker)
            if data:
                results[ticker] = data
        
        return results
    
    def calculate_entry_quality(self, ticker: str, trades: List[Dict]) -> Dict:
        """
        Calculate overall entry quality based on multiple insider trades.
        
        Returns aggregated view of whether current price is good entry.
        """
        current_data = self.get_current_price(ticker)
        
        if not current_data:
            return {'error': 'Could not fetch price data'}
        
        current_price = current_data['current_price']
        
        trade_prices = []
        for trade in trades:
            if trade.get('price'):
                trade_prices.append(float(trade['price']))
        
        if not trade_prices:
            return {'error': 'No trade prices available'}
        
        avg_insider_price = sum(trade_prices) / len(trade_prices)
        min_insider_price = min(trade_prices)
        max_insider_price = max(trade_prices)
        
        # Calculate scores
        vs_avg = ((current_price - avg_insider_price) / avg_insider_price) * 100
        vs_min = ((current_price - min_insider_price) / min_insider_price) * 100
        vs_max = ((current_price - max_insider_price) / max_insider_price) * 100
        
        # Entry quality score (0-100, higher is better)
        # Better if current price is lower than insider average
        if current_price <= min_insider_price:
            entry_score = 100
        elif current_price <= avg_insider_price:
            entry_score = 75 + ((avg_insider_price - current_price) / (avg_insider_price - min_insider_price)) * 25
        elif current_price <= max_insider_price:
            entry_score = 50 + ((max_insider_price - current_price) / (max_insider_price - avg_insider_price)) * 25
        else:
            # Price above all insider trades
            entry_score = max(0, 50 - (vs_max * 2))
        
        return {
            'ticker': ticker,
            'current_price': current_price,
            'avg_insider_price': avg_insider_price,
            'min_insider_price': min_insider_price,
            'max_insider_price': max_insider_price,
            'vs_avg_pct': vs_avg,
            'vs_min_pct': vs_min,
            'vs_max_pct': vs_max,
            'entry_score': round(entry_score, 1),
            'entry_rating': self._get_entry_rating(entry_score),
            'num_insider_trades': len(trade_prices),
            'recommendation': self._get_entry_recommendation(entry_score, vs_avg)
        }
    
    def _get_entry_rating(self, score: float) -> str:
        """Convert entry score to rating."""
        if score >= 90:
            return 'EXCELLENT'
        elif score >= 75:
            return 'VERY GOOD'
        elif score >= 60:
            return 'GOOD'
        elif score >= 40:
            return 'FAIR'
        else:
            return 'POOR'
    
    def _get_entry_recommendation(self, score: float, vs_avg: float) -> str:
        """Generate entry recommendation."""
        if score >= 90:
            return f"Outstanding entry - current price is {abs(vs_avg):.1f}% below average insider price!"
        elif score >= 75:
            return f"Great entry - current price is {abs(vs_avg):.1f}% below average insider price"
        elif score >= 60:
            return "Good entry point compared to insider activity"
        elif score >= 40:
            return "Fair entry - consider your conviction level"
        else:
            return f"Poor entry - current price is {vs_avg:.1f}% above average insider price. Consider waiting."

