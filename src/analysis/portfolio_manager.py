"""Portfolio management and tracking for personal investing."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
import yfinance as yf
import pandas as pd

from src.database import get_session
from .signal_generator import SignalGenerator, TradingSignal, SignalAction


class PositionStatus(Enum):
    """Portfolio position status."""
    OPEN = "open"
    CLOSED = "closed"
    PARTIAL = "partial"


@dataclass
class PortfolioPosition:
    """Represents a position in the personal portfolio."""
    
    ticker: str
    shares: float
    avg_cost: float
    current_price: Optional[float] = None
    
    # Entry details
    entry_date: Optional[date] = None
    entry_signal_id: Optional[int] = None
    
    # Exit details (for closed positions)
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None
    
    # Performance
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    total_return_pct: Optional[float] = None
    
    # Metadata
    notes: str = ""
    status: PositionStatus = PositionStatus.OPEN
    
    def update_current_price(self, price: float):
        """Update current price and calculate unrealized P&L."""
        self.current_price = price
        if self.shares and self.avg_cost:
            market_value = self.shares * price
            cost_basis = self.shares * self.avg_cost
            self.unrealized_pnl = market_value - cost_basis
            self.total_return_pct = (price - self.avg_cost) / self.avg_cost
    
    def close_position(self, exit_price: float, exit_date: date, shares_sold: Optional[float] = None):
        """Close position (full or partial)."""
        shares_to_close = shares_sold or self.shares
        
        self.realized_pnl = shares_to_close * (exit_price - self.avg_cost)
        
        if shares_to_close >= self.shares:
            # Full close
            self.status = PositionStatus.CLOSED
            self.shares = 0
            self.exit_date = exit_date
            self.exit_price = exit_price
        else:
            # Partial close
            self.status = PositionStatus.PARTIAL
            self.shares -= shares_to_close


# Import the PortfolioTransaction from the main models
from src.database import PortfolioTransaction


class PortfolioManager:
    """Manages personal portfolio positions and performance."""
    
    def __init__(self, portfolio_value: float = 100000, 
                 risk_tolerance: str = 'moderate'):
        """Initialize portfolio manager.
        
        Args:
            portfolio_value: Total portfolio value
            risk_tolerance: Risk tolerance level
        """
        self.portfolio_value = portfolio_value
        self.risk_tolerance = risk_tolerance
        self.signal_generator = SignalGenerator()
        
        # Portfolio tracking
        self.positions: Dict[str, PortfolioPosition] = {}
        self.cash_balance = portfolio_value
        self.last_update = None
        
        # Load existing positions
        self._load_portfolio_from_db()
    
    def get_current_recommendations(self) -> Dict:
        """Get current buy/sell/hold recommendations."""
        
        # Generate fresh signals
        recommendations = self.signal_generator.get_portfolio_recommendations(
            portfolio_value=self.portfolio_value,
            risk_tolerance=self.risk_tolerance
        )
        
        # Add position context to signals
        for signal in recommendations.get('signals', []):
            current_position = self.positions.get(signal.ticker)
            if current_position:
                signal.current_position = {
                    'shares': current_position.shares,
                    'avg_cost': current_position.avg_cost,
                    'unrealized_pnl': current_position.unrealized_pnl,
                    'return_pct': current_position.total_return_pct
                }
                
                # Modify action based on existing position
                if current_position.status == PositionStatus.OPEN:
                    if signal.action == SignalAction.BUY and current_position.total_return_pct and current_position.total_return_pct < -0.10:
                        signal.action = SignalAction.HOLD  # Don't add to losing positions
        
        # Add hold recommendations for existing positions
        hold_recommendations = self._generate_hold_recommendations()
        recommendations['hold_recommendations'] = hold_recommendations
        
        return recommendations
    
    def _generate_hold_recommendations(self) -> List[Dict]:
        """Generate hold/sell recommendations for existing positions."""
        
        recommendations = []
        
        for ticker, position in self.positions.items():
            if position.status != PositionStatus.OPEN:
                continue
            
            # Update current price
            try:
                current_price = self._get_current_price(ticker)
                position.update_current_price(current_price)
            except Exception:
                continue
            
            recommendation = {
                'ticker': ticker,
                'action': 'hold',
                'current_position': {
                    'shares': position.shares,
                    'avg_cost': position.avg_cost,
                    'current_price': position.current_price,
                    'unrealized_pnl': position.unrealized_pnl,
                    'return_pct': position.total_return_pct,
                    'market_value': position.shares * position.current_price if position.current_price else 0
                }
            }
            
            # Determine hold vs sell recommendation
            if position.total_return_pct:
                if position.total_return_pct > 0.25:  # >25% gain
                    recommendation['action'] = 'consider_sell'
                    recommendation['reasoning'] = f"Strong gains ({position.total_return_pct:.1%}) - consider taking profits"
                elif position.total_return_pct < -0.15:  # >15% loss
                    recommendation['action'] = 'consider_sell'
                    recommendation['reasoning'] = f"Significant loss ({position.total_return_pct:.1%}) - consider cutting losses"
                else:
                    recommendation['reasoning'] = f"Position performing normally ({position.total_return_pct:.1%})"
            
            recommendations.append(recommendation)
        
        return recommendations
    
    def execute_signal(self, signal: TradingSignal, shares: Optional[float] = None) -> bool:
        """Execute a trading signal (simulated)."""
        
        if signal.action != SignalAction.BUY:
            return False  # Only handle buy signals for now
        
        # Get current price
        try:
            current_price = self._get_current_price(signal.ticker)
        except Exception as e:
            print(f"Failed to get price for {signal.ticker}: {e}")
            return False
        
        # Calculate shares if not provided
        if shares is None:
            position_value = self.portfolio_value * (signal.position_size_pct or 0.05)
            shares = position_value / current_price
        
        total_cost = shares * current_price
        
        # Check if we have enough cash
        if total_cost > self.cash_balance:
            print(f"Insufficient cash: ${total_cost:.2f} > ${self.cash_balance:.2f}")
            return False
        
        # Execute transaction
        self._record_transaction(
            ticker=signal.ticker,
            action='buy',
            shares=shares,
            price=current_price,
            signal_confidence=signal.confidence
        )
        
        # Update position
        if signal.ticker in self.positions:
            # Add to existing position
            position = self.positions[signal.ticker]
            new_total_cost = (position.shares * position.avg_cost) + total_cost
            new_total_shares = position.shares + shares
            position.avg_cost = new_total_cost / new_total_shares
            position.shares = new_total_shares
        else:
            # Create new position
            self.positions[signal.ticker] = PortfolioPosition(
                ticker=signal.ticker,
                shares=shares,
                avg_cost=current_price,
                entry_date=date.today()
            )
        
        # Update cash balance
        self.cash_balance -= total_cost
        
        print(f"Executed: Bought {shares:.2f} shares of {signal.ticker} at ${current_price:.2f}")
        return True
    
    def sell_position(self, ticker: str, shares: Optional[float] = None) -> bool:
        """Sell a position (full or partial)."""
        
        if ticker not in self.positions:
            print(f"No position in {ticker}")
            return False
        
        position = self.positions[ticker]
        if position.status != PositionStatus.OPEN:
            print(f"Position in {ticker} is not open")
            return False
        
        # Get current price
        try:
            current_price = self._get_current_price(ticker)
        except Exception as e:
            print(f"Failed to get price for {ticker}: {e}")
            return False
        
        # Calculate shares to sell
        shares_to_sell = shares or position.shares
        shares_to_sell = min(shares_to_sell, position.shares)
        
        # Execute sale
        sale_proceeds = shares_to_sell * current_price
        
        self._record_transaction(
            ticker=ticker,
            action='sell',
            shares=shares_to_sell,
            price=current_price
        )
        
        # Update position
        position.close_position(current_price, date.today(), shares_to_sell)
        
        # Update cash balance
        self.cash_balance += sale_proceeds
        
        print(f"Executed: Sold {shares_to_sell:.2f} shares of {ticker} at ${current_price:.2f}")
        return True
    
    def get_portfolio_summary(self) -> Dict:
        """Get comprehensive portfolio summary."""
        
        # Update all position prices
        self._update_all_positions()
        
        total_market_value = self.cash_balance
        total_unrealized_pnl = 0
        total_cost_basis = 0
        
        position_summaries = []
        
        for ticker, position in self.positions.items():
            if position.status == PositionStatus.OPEN and position.shares > 0:
                market_value = position.shares * (position.current_price or position.avg_cost)
                cost_basis = position.shares * position.avg_cost
                
                total_market_value += market_value
                total_cost_basis += cost_basis
                total_unrealized_pnl += position.unrealized_pnl or 0
                
                position_summaries.append({
                    'ticker': ticker,
                    'shares': position.shares,
                    'avg_cost': position.avg_cost,
                    'current_price': position.current_price,
                    'market_value': market_value,
                    'cost_basis': cost_basis,
                    'unrealized_pnl': position.unrealized_pnl,
                    'return_pct': position.total_return_pct,
                    'allocation_pct': market_value / total_market_value if total_market_value > 0 else 0
                })
        
        # Calculate overall portfolio performance
        total_return_pct = (total_market_value - self.portfolio_value) / self.portfolio_value if self.portfolio_value > 0 else 0
        
        return {
            'total_value': total_market_value,
            'cash_balance': self.cash_balance,
            'invested_amount': total_market_value - self.cash_balance,
            'total_return_pct': total_return_pct,
            'total_unrealized_pnl': total_unrealized_pnl,
            'positions': sorted(position_summaries, key=lambda x: x['market_value'], reverse=True),
            'position_count': len([p for p in self.positions.values() if p.status == PositionStatus.OPEN]),
            'cash_allocation_pct': self.cash_balance / total_market_value if total_market_value > 0 else 1.0,
            'last_updated': datetime.now()
        }
    
    def _load_portfolio_from_db(self):
        """Load portfolio positions from database transactions."""
        
        with get_session() as session:
            transactions = session.query(PortfolioTransaction).order_by(
                PortfolioTransaction.transaction_date.asc()
            ).all()
        
        # Rebuild positions from transactions
        for transaction in transactions:
            ticker = transaction.ticker
            
            if ticker not in self.positions:
                self.positions[ticker] = PortfolioPosition(
                    ticker=ticker,
                    shares=0,
                    avg_cost=0
                )
            
            position = self.positions[ticker]
            
            if transaction.action.lower() == 'buy':
                # Add to position
                new_cost = (position.shares * position.avg_cost) + (transaction.shares * transaction.price)
                position.shares += transaction.shares
                if position.shares > 0:
                    position.avg_cost = new_cost / position.shares
                
                if not position.entry_date:
                    position.entry_date = transaction.transaction_date
                
            elif transaction.action.lower() == 'sell':
                # Remove from position
                position.shares -= transaction.shares
                if position.shares <= 0:
                    position.status = PositionStatus.CLOSED
                    position.exit_date = transaction.transaction_date
                    position.exit_price = transaction.price
        
        # Remove closed positions with zero shares
        self.positions = {k: v for k, v in self.positions.items() 
                         if v.shares > 0 or v.status == PositionStatus.CLOSED}
    
    def _record_transaction(self, ticker: str, action: str, shares: float, price: float,
                           signal_confidence: Optional[float] = None):
        """Record a transaction in the database."""
        
        with get_session() as session:
            transaction = PortfolioTransaction(
                ticker=ticker,
                action=action,
                shares=shares,
                price=price,
                transaction_date=date.today(),
                total_cost=shares * price,
                signal_confidence=signal_confidence
            )
            
            session.add(transaction)
            session.commit()
    
    def _get_current_price(self, ticker: str) -> float:
        """Get current stock price."""
        
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d")
            
            if hist.empty:
                raise ValueError(f"No price data for {ticker}")
            
            return float(hist['Close'].iloc[-1])
            
        except Exception as e:
            raise ValueError(f"Failed to get price for {ticker}: {e}")
    
    def _update_all_positions(self):
        """Update current prices for all positions."""
        
        tickers = list(self.positions.keys())
        
        if not tickers:
            return
        
        try:
            # Batch fetch prices for efficiency
            tickers_str = " ".join(tickers)
            stocks_data = yf.download(tickers_str, period="1d", group_by='ticker')
            
            for ticker in tickers:
                position = self.positions[ticker]
                if position.status != PositionStatus.OPEN:
                    continue
                
                try:
                    if len(tickers) > 1:
                        price_data = stocks_data[ticker]['Close']
                    else:
                        price_data = stocks_data['Close']
                    
                    if not price_data.empty:
                        current_price = float(price_data.iloc[-1])
                        position.update_current_price(current_price)
                
                except Exception as e:
                    print(f"Failed to update price for {ticker}: {e}")
                    continue
        
        except Exception as e:
            print(f"Failed to batch update prices: {e}")
            # Fall back to individual updates
            for ticker, position in self.positions.items():
                if position.status == PositionStatus.OPEN:
                    try:
                        current_price = self._get_current_price(ticker)
                        position.update_current_price(current_price)
                    except Exception:
                        continue


if __name__ == "__main__":
    # CLI for portfolio management
    import argparse
    
    parser = argparse.ArgumentParser(description="Manage personal portfolio")
    parser.add_argument("--action", choices=['summary', 'recommendations', 'execute'], 
                       default='summary', help="Action to perform")
    parser.add_argument("--portfolio-value", type=float, default=100000,
                       help="Portfolio value")
    parser.add_argument("--risk-tolerance", choices=['conservative', 'moderate', 'aggressive'],
                       default='moderate', help="Risk tolerance")
    
    args = parser.parse_args()
    
    manager = PortfolioManager(
        portfolio_value=args.portfolio_value,
        risk_tolerance=args.risk_tolerance
    )
    
    if args.action == 'summary':
        summary = manager.get_portfolio_summary()
        
        print(f"\n=== PORTFOLIO SUMMARY ===")
        print(f"Total Value: ${summary['total_value']:,.2f}")
        print(f"Cash Balance: ${summary['cash_balance']:,.2f} ({summary['cash_allocation_pct']:.1%})")
        print(f"Total Return: {summary['total_return_pct']:.2%}")
        print(f"Unrealized P&L: ${summary['total_unrealized_pnl']:,.2f}")
        
        print(f"\n{'TICKER':<8} {'SHARES':<10} {'AVG COST':<10} {'CURRENT':<10} {'P&L':<12} {'RETURN':<10}")
        print("-" * 70)
        
        for position in summary['positions']:
            pnl = position['unrealized_pnl'] or 0
            return_pct = position['return_pct'] or 0
            print(f"{position['ticker']:<8} {position['shares']:<10.2f} ${position['avg_cost']:<9.2f} "
                  f"${position['current_price']:<9.2f} ${pnl:<11.2f} {return_pct:<10.2%}")
    
    elif args.action == 'recommendations':
        recommendations = manager.get_current_recommendations()
        
        print(f"\n=== CURRENT RECOMMENDATIONS ===")
        
        signals = recommendations.get('signals', [])
        if signals:
            print(f"\nBUY SIGNALS:")
            print(f"{'TICKER':<8} {'STRENGTH':<12} {'CONF':<6} {'SIZE':<6} {'TARGET':<8} {'REASONING'}")
            print("-" * 80)
            
            for signal in signals[:10]:
                target_return = 0
                if signal.target_price and signal.current_price:
                    target_return = (signal.target_price - signal.current_price) / signal.current_price
                
                size_pct = (signal.position_size_pct or 0) * 100
                reasoning = signal.reasoning[:40] + "..." if len(signal.reasoning) > 40 else signal.reasoning
                
                print(f"{signal.ticker:<8} {signal.strength.value:<12} {signal.confidence:<6.1%} "
                      f"{size_pct:<6.1f}% {target_return:<8.1%} {reasoning}")
        
        hold_recs = recommendations.get('hold_recommendations', [])
        if hold_recs:
            print(f"\nCURRENT POSITIONS:")
            print(f"{'TICKER':<8} {'ACTION':<12} {'RETURN':<8} {'VALUE':<10} {'REASONING'}")
            print("-" * 60)
            
            for rec in hold_recs:
                pos = rec['current_position']
                return_pct = pos.get('return_pct', 0) or 0
                market_value = pos.get('market_value', 0)
                reasoning = rec.get('reasoning', '')[:30]
                
                print(f"{rec['ticker']:<8} {rec['action']:<12} {return_pct:<8.2%} "
                      f"${market_value:<9.0f} {reasoning}")
    
    elif args.action == 'execute':
        print("Signal execution simulation - use web interface for actual execution")
