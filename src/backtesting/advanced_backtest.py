"""
Advanced backtesting engine with historical data.
Implements multiple alpha-generating strategies.
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import logging
from dataclasses import dataclass
from sqlalchemy import and_

from src.database import get_session, Trade, Filer, Signal
from src.database.models import TransactionType, FilerType


logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    strategy_name: str
    start_date: datetime
    end_date: datetime
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    

class AdvancedBacktester:
    """Advanced backtesting engine with multiple alpha strategies."""
    
    def __init__(self, start_date: str = None, end_date: str = None):
        """
        Initialize backtester.
        
        Args:
            start_date: Start date for backtest (YYYY-MM-DD)
            end_date: End date for backtest (YYYY-MM-DD)
        """
        self.start_date = datetime.strptime(start_date, '%Y-%m-%d') if start_date else datetime.now() - timedelta(days=365)
        self.end_date = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.now()
        self.price_cache = {}
    
    def get_historical_prices(self, ticker: str, start: datetime, end: datetime) -> pd.DataFrame:
        """Fetch historical prices using yfinance."""
        cache_key = f"{ticker}_{start}_{end}"
        
        if cache_key in self.price_cache:
            return self.price_cache[cache_key]
        
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(start=start, end=end)
            self.price_cache[cache_key] = df
            return df
        except Exception as e:
            logger.error(f"Error fetching prices for {ticker}: {e}")
            return pd.DataFrame()
    
    def strategy_insider_cluster(self) -> BacktestResult:
        """
        STRATEGY: Insider Cluster Buying
        
        Buy when 3+ insiders buy within 30 days.
        Hold for 90 days or until 20% gain.
        """
        logger.info("Running Insider Cluster strategy backtest...")
        
        trades_made = []
        
        with get_session() as session:
            # Get all buy trades in date range
            buys = session.query(Trade).filter(
                and_(
                    Trade.transaction_type == TransactionType.BUY,
                    Trade.trade_date >= self.start_date.date(),
                    Trade.trade_date <= self.end_date.date()
                )
            ).all()
            
            # Group by ticker and find clusters
            ticker_buys = {}
            for trade in buys:
                if not trade.ticker:
                    continue
                    
                if trade.ticker not in ticker_buys:
                    ticker_buys[trade.ticker] = []
                ticker_buys[trade.ticker].append(trade)
            
            # Find clusters (3+ buys within 30 days)
            for ticker, buy_trades in ticker_buys.items():
                buy_trades.sort(key=lambda t: t.trade_date)
                
                for i, trade in enumerate(buy_trades):
                    # Count buys within 30 days
                    cluster_start = trade.trade_date
                    cluster_end = cluster_start + timedelta(days=30)
                    
                    cluster_trades = [
                        t for t in buy_trades[i:]
                        if cluster_start <= t.trade_date <= cluster_end
                    ]
                    
                    if len(cluster_trades) >= 3:
                        # SIGNAL: Buy this ticker!
                        entry_date = cluster_start
                        exit_date = min(entry_date + timedelta(days=90), self.end_date.date())
                        
                        # Get prices
                        prices = self.get_historical_prices(
                            ticker,
                            entry_date,
                            exit_date
                        )
                        
                        if not prices.empty:
                            entry_price = prices['Close'].iloc[0] if len(prices) > 0 else None
                            
                            if entry_price:
                                # Check for 20% gain or hold to exit_date
                                max_price = prices['Close'].max()
                                exit_price = prices['Close'].iloc[-1] if len(prices) > 0 else entry_price
                                
                                # If hit 20% target, exit there
                                if max_price >= entry_price * 1.20:
                                    # Find first date hitting target
                                    for date, row in prices.iterrows():
                                        if row['Close'] >= entry_price * 1.20:
                                            exit_price = row['Close']
                                            exit_date = date
                                            break
                                
                                return_pct = (exit_price - entry_price) / entry_price
                                
                                trades_made.append({
                                    'ticker': ticker,
                                    'entry_date': entry_date,
                                    'exit_date': exit_date,
                                    'entry_price': entry_price,
                                    'exit_price': exit_price,
                                    'return': return_pct,
                                    'cluster_size': len(cluster_trades)
                                })
                        
                        # Skip ahead to avoid overlapping signals
                        break
        
        return self._calculate_results("Insider Cluster", trades_made)
    
    def strategy_politician_conviction(self) -> BacktestResult:
        """
        STRATEGY: Politician Conviction Plays
        
        Buy when a politician makes a large trade (>$100K).
        Politicians with advance knowledge often make big bets.
        """
        logger.info("Running Politician Conviction strategy backtest...")
        
        trades_made = []
        
        with get_session() as session:
            # Get large politician buys
            large_buys = session.query(Trade).join(Filer).filter(
                and_(
                    Filer.filer_type == FilerType.POLITICIAN,
                    Trade.transaction_type == TransactionType.BUY,
                    Trade.amount_usd >= 100000,
                    Trade.trade_date >= self.start_date.date(),
                    Trade.trade_date <= self.end_date.date()
                )
            ).all()
            
            for trade in large_buys:
                if not trade.ticker:
                    continue
                
                entry_date = trade.trade_date
                exit_date = min(entry_date + timedelta(days=60), self.end_date.date())
                
                prices = self.get_historical_prices(trade.ticker, entry_date, exit_date)
                
                if not prices.empty and len(prices) > 0:
                    entry_price = prices['Close'].iloc[0]
                    exit_price = prices['Close'].iloc[-1]
                    return_pct = (exit_price - entry_price) / entry_price
                    
                    trades_made.append({
                        'ticker': trade.ticker,
                        'entry_date': entry_date,
                        'exit_date': exit_date,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'return': return_pct,
                        'amount': float(trade.amount_usd)
                    })
        
        return self._calculate_results("Politician Conviction", trades_made)
    
    def strategy_unusual_volume(self) -> BacktestResult:
        """
        STRATEGY: Unusual Insider Volume
        
        Buy when insider buying volume is 3x the normal.
        """
        logger.info("Running Unusual Volume strategy backtest...")
        
        trades_made = []
        
        with get_session() as session:
            # Get all tickers with multiple trades
            all_buys = session.query(Trade).filter(
                and_(
                    Trade.transaction_type == TransactionType.BUY,
                    Trade.trade_date >= self.start_date.date(),
                    Trade.trade_date <= self.end_date.date(),
                    Trade.amount_usd.isnot(None)
                )
            ).all()
            
            # Group by ticker and calculate rolling 30-day average
            ticker_activity = {}
            for trade in all_buys:
                if not trade.ticker:
                    continue
                if trade.ticker not in ticker_activity:
                    ticker_activity[trade.ticker] = []
                ticker_activity[trade.ticker].append({
                    'date': trade.trade_date,
                    'amount': float(trade.amount_usd)
                })
            
            # Find unusual spikes
            for ticker, activity in ticker_activity.items():
                activity.sort(key=lambda x: x['date'])
                
                for i in range(30, len(activity)):
                    current_amount = activity[i]['amount']
                    historical_avg = np.mean([a['amount'] for a in activity[i-30:i]])
                    
                    # If current is 3x historical average = SIGNAL
                    if current_amount >= historical_avg * 3:
                        entry_date = activity[i]['date']
                        exit_date = min(entry_date + timedelta(days=45), self.end_date.date())
                        
                        prices = self.get_historical_prices(ticker, entry_date, exit_date)
                        
                        if not prices.empty and len(prices) > 0:
                            entry_price = prices['Close'].iloc[0]
                            exit_price = prices['Close'].iloc[-1]
                            return_pct = (exit_price - entry_price) / entry_price
                            
                            trades_made.append({
                                'ticker': ticker,
                                'entry_date': entry_date,
                                'exit_date': exit_date,
                                'entry_price': entry_price,
                                'exit_price': exit_price,
                                'return': return_pct,
                                'spike_ratio': current_amount / historical_avg if historical_avg > 0 else 0
                            })
        
        return self._calculate_results("Unusual Volume", trades_made)
    
    def _calculate_results(self, strategy_name: str, trades: List[Dict]) -> BacktestResult:
        """Calculate backtest metrics."""
        if not trades:
            return BacktestResult(
                strategy_name=strategy_name,
                start_date=self.start_date,
                end_date=self.end_date,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                total_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                profit_factor=0.0
            )
        
        returns = [t['return'] for t in trades]
        winners = [r for r in returns if r > 0]
        losers = [r for r in returns if r < 0]
        
        total_return = sum(returns)
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if len(returns) > 1 and np.std(returns) > 0 else 0
        
        # Calculate max drawdown
        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = cumulative - running_max
        max_drawdown = abs(np.min(drawdown)) if len(drawdown) > 0 else 0
        
        win_rate = len(winners) / len(returns) if returns else 0
        avg_win = np.mean(winners) if winners else 0
        avg_loss = np.mean(losers) if losers else 0
        profit_factor = abs(sum(winners) / sum(losers)) if losers and sum(losers) != 0 else 0
        
        return BacktestResult(
            strategy_name=strategy_name,
            start_date=self.start_date,
            end_date=self.end_date,
            total_trades=len(trades),
            winning_trades=len(winners),
            losing_trades=len(losers),
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor
        )
    
    def run_all_strategies(self) -> Dict[str, BacktestResult]:
        """Run all strategies and return results."""
        results = {}
        
        try:
            results['insider_cluster'] = self.strategy_insider_cluster()
        except Exception as e:
            logger.error(f"Error in Insider Cluster strategy: {e}")
        
        try:
            results['politician_conviction'] = self.strategy_politician_conviction()
        except Exception as e:
            logger.error(f"Error in Politician Conviction strategy: {e}")
        
        try:
            results['unusual_volume'] = self.strategy_unusual_volume()
        except Exception as e:
            logger.error(f"Error in Unusual Volume strategy: {e}")
        
        return results


def print_backtest_report(results: Dict[str, BacktestResult]):
    """Print formatted backtest report."""
    print("\n" + "="*80)
    print("🔬 ADVANCED BACKTESTING REPORT")
    print("="*80 + "\n")
    
    for name, result in results.items():
        print(f"📊 {result.strategy_name}")
        print("-" * 60)
        print(f"Period: {result.start_date.date()} to {result.end_date.date()}")
        print(f"Total Trades: {result.total_trades}")
        print(f"Win Rate: {result.win_rate*100:.1f}%")
        print(f"Total Return: {result.total_return*100:.2f}%")
        print(f"Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"Max Drawdown: {result.max_drawdown*100:.2f}%")
        print(f"Avg Win: {result.avg_win*100:.2f}%")
        print(f"Avg Loss: {result.avg_loss*100:.2f}%")
        print(f"Profit Factor: {result.profit_factor:.2f}")
        print()

