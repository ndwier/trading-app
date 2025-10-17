"""Main backtesting engine for evaluating trading strategies."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from config.config import config
from src.database import get_session, Trade, PriceData
from .base_strategy import BaseStrategy, StrategyResult, StrategySignal, SignalType
from .performance_metrics import PerformanceCalculator


logger = logging.getLogger(__name__)


@dataclass
class Position:
    """Represents a trading position."""
    
    ticker: str
    entry_date: date
    entry_price: float
    position_size: float  # Fraction of portfolio
    shares: float
    
    exit_date: Optional[date] = None
    exit_price: Optional[float] = None
    
    # Performance metrics
    return_pct: Optional[float] = None
    return_dollars: Optional[float] = None
    hold_days: Optional[int] = None
    
    # Metadata
    signal_id: Optional[int] = None
    
    def close_position(self, exit_date: date, exit_price: float):
        """Close the position and calculate returns."""
        self.exit_date = exit_date
        self.exit_price = exit_price
        
        if self.entry_price > 0:
            self.return_pct = (exit_price - self.entry_price) / self.entry_price
            self.return_dollars = self.shares * (exit_price - self.entry_price)
            self.hold_days = (exit_date - self.entry_date).days
    
    @property
    def is_closed(self) -> bool:
        """Check if position is closed."""
        return self.exit_date is not None and self.exit_price is not None


@dataclass
class Portfolio:
    """Represents a trading portfolio."""
    
    initial_capital: float
    current_cash: float
    positions: List[Position] = field(default_factory=list)
    
    # Performance tracking
    daily_values: Dict[date, float] = field(default_factory=dict)
    
    def add_position(self, position: Position) -> bool:
        """Add a new position to the portfolio."""
        required_cash = position.shares * position.entry_price
        
        if required_cash > self.current_cash:
            logger.warning(f"Insufficient cash for position: ${required_cash:.2f} > ${self.current_cash:.2f}")
            return False
        
        self.current_cash -= required_cash
        self.positions.append(position)
        return True
    
    def close_position(self, position: Position, exit_date: date, exit_price: float):
        """Close a position and add proceeds to cash."""
        position.close_position(exit_date, exit_price)
        
        # Add proceeds to cash
        proceeds = position.shares * exit_price
        self.current_cash += proceeds
    
    def get_portfolio_value(self, date_val: date, 
                           price_data: Dict[str, Dict[date, float]]) -> float:
        """Calculate total portfolio value on a given date."""
        
        total_value = self.current_cash
        
        for position in self.positions:
            if not position.is_closed:
                # Position is still open, value at current price
                if (position.ticker in price_data and 
                    date_val in price_data[position.ticker]):
                    current_price = price_data[position.ticker][date_val]
                    total_value += position.shares * current_price
                else:
                    # No price data, use entry price as estimate
                    total_value += position.shares * position.entry_price
        
        return total_value
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions."""
        return [p for p in self.positions if not p.is_closed]
    
    def get_closed_positions(self) -> List[Position]:
        """Get all closed positions."""
        return [p for p in self.positions if p.is_closed]


@dataclass
class BacktestResult:
    """Results from a backtest run."""
    
    strategy_name: str
    start_date: date
    end_date: date
    
    # Portfolio results
    initial_capital: float
    final_value: float
    total_return: float
    
    # Performance metrics
    annual_return: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    max_drawdown: Optional[float] = None
    win_rate: Optional[float] = None
    
    # Trade statistics
    total_signals: int = 0
    executed_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    
    # Detailed results
    positions: List[Position] = field(default_factory=list)
    daily_values: Dict[date, float] = field(default_factory=dict)
    
    # Strategy info
    strategy_parameters: Dict = field(default_factory=dict)


class Backtester:
    """Main backtesting engine."""
    
    def __init__(self, initial_capital: float = None):
        """Initialize backtester.
        
        Args:
            initial_capital: Starting capital (uses config default if None)
        """
        self.initial_capital = initial_capital or config.backtesting.INITIAL_CAPITAL
        self.commission = config.backtesting.COMMISSION
        self.slippage = config.backtesting.SLIPPAGE
        
        self.logger = logger
    
    def backtest_strategy(self, strategy: BaseStrategy,
                         start_date: date, end_date: date,
                         trades: Optional[List[Trade]] = None) -> BacktestResult:
        """Run a backtest for a given strategy.
        
        Args:
            strategy: Strategy to test
            start_date: Backtest start date
            end_date: Backtest end date 
            trades: List of trades (loads from DB if None)
            
        Returns:
            BacktestResult with performance metrics
        """
        
        self.logger.info(f"Starting backtest: {strategy.name} from {start_date} to {end_date}")
        
        # Load trades if not provided
        if trades is None:
            trades = self._load_trades(start_date, end_date)
        
        # Generate signals
        strategy_result = strategy.generate_signals(trades, start_date, end_date)
        
        # Load price data for the signals
        tickers = list(set(signal.ticker for signal in strategy_result.signals))
        price_data = self._load_price_data(tickers, start_date, end_date)
        
        # Execute backtest
        portfolio = Portfolio(
            initial_capital=self.initial_capital,
            current_cash=self.initial_capital
        )
        
        executed_signals = self._execute_signals(
            strategy_result.signals, portfolio, price_data
        )
        
        # Calculate daily portfolio values
        self._calculate_daily_values(portfolio, start_date, end_date, price_data)
        
        # Calculate performance metrics
        final_value = portfolio.get_portfolio_value(end_date, price_data)
        total_return = (final_value - self.initial_capital) / self.initial_capital
        
        performance_calc = PerformanceCalculator(
            portfolio.daily_values, 
            self.initial_capital
        )
        
        # Count winning/losing trades
        closed_positions = portfolio.get_closed_positions()
        winning_trades = len([p for p in closed_positions if p.return_pct and p.return_pct > 0])
        losing_trades = len([p for p in closed_positions if p.return_pct and p.return_pct < 0])
        
        result = BacktestResult(
            strategy_name=strategy.name,
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.initial_capital,
            final_value=final_value,
            total_return=total_return,
            annual_return=performance_calc.calculate_annual_return(),
            sharpe_ratio=performance_calc.calculate_sharpe_ratio(),
            max_drawdown=performance_calc.calculate_max_drawdown(),
            win_rate=winning_trades / len(closed_positions) if closed_positions else 0,
            total_signals=len(strategy_result.signals),
            executed_trades=len(executed_signals),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            positions=portfolio.positions,
            daily_values=portfolio.daily_values,
            strategy_parameters=strategy.parameters
        )
        
        self.logger.info(f"Backtest complete: {result.total_return:.2%} return, "
                        f"{result.executed_trades} trades, {result.win_rate:.2%} win rate")
        
        return result
    
    def _load_trades(self, start_date: date, end_date: date) -> List[Trade]:
        """Load trades from database for the given date range."""
        
        with get_session() as session:
            trades = session.query(Trade).filter(
                Trade.reported_date >= start_date,
                Trade.reported_date <= end_date,
                Trade.ticker.isnot(None)
            ).all()
        
        self.logger.info(f"Loaded {len(trades)} trades for backtest period")
        return trades
    
    def _load_price_data(self, tickers: List[str], 
                        start_date: date, end_date: date) -> Dict[str, Dict[date, float]]:
        """Load price data for the given tickers and date range."""
        
        price_data = {}
        
        with get_session() as session:
            for ticker in tickers:
                prices = session.query(PriceData).filter(
                    PriceData.ticker == ticker,
                    PriceData.date >= start_date,
                    PriceData.date <= end_date
                ).order_by(PriceData.date).all()
                
                if prices:
                    price_data[ticker] = {p.date: float(p.close_price) for p in prices}
                else:
                    self.logger.warning(f"No price data found for {ticker}")
        
        self.logger.info(f"Loaded price data for {len(price_data)} tickers")
        return price_data
    
    def _execute_signals(self, signals: List[StrategySignal], 
                        portfolio: Portfolio,
                        price_data: Dict[str, Dict[date, float]]) -> List[StrategySignal]:
        """Execute trading signals and update portfolio."""
        
        executed_signals = []
        
        for signal in signals:
            if signal.signal_type != SignalType.BUY:
                continue  # Only handle buy signals for now
            
            # Check if we have price data for entry
            if (signal.ticker not in price_data or 
                signal.entry_date not in price_data[signal.ticker]):
                self.logger.warning(f"No price data for {signal.ticker} on {signal.entry_date}")
                continue
            
            entry_price = price_data[signal.ticker][signal.entry_date]
            
            # Apply slippage
            entry_price *= (1 + self.slippage)
            
            # Calculate position size in dollars
            position_value = portfolio.initial_capital * signal.position_size
            
            # Calculate number of shares
            shares = position_value / entry_price
            
            # Apply commission
            commission_cost = position_value * self.commission
            actual_cost = position_value + commission_cost
            
            if actual_cost > portfolio.current_cash:
                self.logger.debug(f"Insufficient cash for {signal.ticker}: ${actual_cost:.2f}")
                continue
            
            # Create position
            position = Position(
                ticker=signal.ticker,
                entry_date=signal.entry_date,
                entry_price=entry_price,
                position_size=signal.position_size,
                shares=shares
            )
            
            if portfolio.add_position(position):
                executed_signals.append(signal)
                
                # Schedule exit if exit date is specified
                if signal.exit_date and (signal.ticker in price_data and 
                                       signal.exit_date in price_data[signal.ticker]):
                    exit_price = price_data[signal.ticker][signal.exit_date]
                    exit_price *= (1 - self.slippage)  # Apply slippage
                    
                    portfolio.close_position(position, signal.exit_date, exit_price)
        
        return executed_signals
    
    def _calculate_daily_values(self, portfolio: Portfolio,
                               start_date: date, end_date: date,
                               price_data: Dict[str, Dict[date, float]]):
        """Calculate daily portfolio values."""
        
        current_date = start_date
        
        while current_date <= end_date:
            portfolio_value = portfolio.get_portfolio_value(current_date, price_data)
            portfolio.daily_values[current_date] = portfolio_value
            
            current_date += pd.Timedelta(days=1).to_pytimedelta()
    
    def compare_strategies(self, strategies: List[BaseStrategy],
                          start_date: date, end_date: date) -> Dict[str, BacktestResult]:
        """Compare multiple strategies over the same period."""
        
        self.logger.info(f"Comparing {len(strategies)} strategies")
        
        # Load trades once for all strategies
        trades = self._load_trades(start_date, end_date)
        
        results = {}
        
        for strategy in strategies:
            try:
                result = self.backtest_strategy(strategy, start_date, end_date, trades)
                results[strategy.name] = result
            except Exception as e:
                self.logger.error(f"Strategy {strategy.name} failed: {e}")
                continue
        
        # Log comparison summary
        self.logger.info("\nStrategy Comparison:")
        self.logger.info("-" * 60)
        for name, result in results.items():
            self.logger.info(f"{name:30} | {result.total_return:8.2%} | "
                           f"{result.executed_trades:3d} trades | "
                           f"{result.win_rate:6.2%} win rate")
        
        return results


if __name__ == "__main__":
    # CLI for running backtests
    import argparse
    from datetime import datetime
    from .base_strategy import LagTradeStrategy
    from .cluster_strategy import ClusterStrategy
    
    parser = argparse.ArgumentParser(description="Run strategy backtests")
    parser.add_argument("--start", type=str, default="2023-01-01",
                       help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2024-01-01", 
                       help="End date (YYYY-MM-DD)")
    parser.add_argument("--strategy", type=str, default="all",
                       choices=["all", "lag", "cluster"],
                       help="Strategy to test")
    
    args = parser.parse_args()
    
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    
    backtester = Backtester()
    
    if args.strategy == "all":
        strategies = [
            LagTradeStrategy(lag_days=1),
            LagTradeStrategy(lag_days=2),
            LagTradeStrategy(lag_days=5),
            ClusterStrategy(min_cluster_size=3),
        ]
        results = backtester.compare_strategies(strategies, start_date, end_date)
    elif args.strategy == "lag":
        strategy = LagTradeStrategy(lag_days=2)
        result = backtester.backtest_strategy(strategy, start_date, end_date)
        print(f"Results: {result.total_return:.2%} return, {result.executed_trades} trades")
    elif args.strategy == "cluster":
        strategy = ClusterStrategy()
        result = backtester.backtest_strategy(strategy, start_date, end_date)
        print(f"Results: {result.total_return:.2%} return, {result.executed_trades} trades")
