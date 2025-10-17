"""Performance metrics calculator for backtesting results."""

import numpy as np
import pandas as pd
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import math

from config.config import config


class PerformanceCalculator:
    """Calculate various performance metrics for trading strategies."""
    
    def __init__(self, daily_values: Dict[date, float], initial_capital: float):
        """Initialize performance calculator.
        
        Args:
            daily_values: Dictionary mapping dates to portfolio values
            initial_capital: Initial portfolio value
        """
        self.daily_values = daily_values
        self.initial_capital = initial_capital
        
        # Convert to pandas Series for easier calculations
        if daily_values:
            self.values_series = pd.Series(daily_values).sort_index()
            self.returns_series = self.values_series.pct_change().dropna()
        else:
            self.values_series = pd.Series(dtype=float)
            self.returns_series = pd.Series(dtype=float)
        
        # Risk-free rate from config
        self.risk_free_rate = config.backtesting.RISK_FREE_RATE
    
    def calculate_total_return(self) -> float:
        """Calculate total return over the period."""
        if self.values_series.empty:
            return 0.0
        
        final_value = self.values_series.iloc[-1]
        return (final_value - self.initial_capital) / self.initial_capital
    
    def calculate_annual_return(self) -> Optional[float]:
        """Calculate annualized return."""
        if len(self.values_series) < 2:
            return None
        
        total_return = self.calculate_total_return()
        
        # Calculate time period in years
        start_date = self.values_series.index[0]
        end_date = self.values_series.index[-1]
        days = (end_date - start_date).days
        
        if days <= 0:
            return None
        
        years = days / 365.25
        
        # Annualized return formula: (1 + total_return)^(1/years) - 1
        return (1 + total_return) ** (1 / years) - 1
    
    def calculate_volatility(self, annualized: bool = True) -> Optional[float]:
        """Calculate portfolio volatility (standard deviation of returns)."""
        if self.returns_series.empty:
            return None
        
        daily_vol = self.returns_series.std()
        
        if annualized:
            # Annualize daily volatility
            return daily_vol * np.sqrt(252)  # 252 trading days per year
        else:
            return daily_vol
    
    def calculate_sharpe_ratio(self) -> Optional[float]:
        """Calculate Sharpe ratio (excess return per unit of risk)."""
        annual_return = self.calculate_annual_return()
        annual_vol = self.calculate_volatility(annualized=True)
        
        if annual_return is None or annual_vol is None or annual_vol == 0:
            return None
        
        excess_return = annual_return - self.risk_free_rate
        return excess_return / annual_vol
    
    def calculate_sortino_ratio(self) -> Optional[float]:
        """Calculate Sortino ratio (downside deviation version of Sharpe)."""
        annual_return = self.calculate_annual_return()
        
        if annual_return is None or self.returns_series.empty:
            return None
        
        # Calculate downside deviation (only negative returns)
        negative_returns = self.returns_series[self.returns_series < 0]
        
        if len(negative_returns) == 0:
            return float('inf')  # No downside risk
        
        daily_downside_dev = negative_returns.std()
        annual_downside_dev = daily_downside_dev * np.sqrt(252)
        
        if annual_downside_dev == 0:
            return float('inf')
        
        excess_return = annual_return - self.risk_free_rate
        return excess_return / annual_downside_dev
    
    def calculate_max_drawdown(self) -> Optional[float]:
        """Calculate maximum drawdown (largest peak-to-trough decline)."""
        if self.values_series.empty:
            return None
        
        # Calculate running maximum (peak values)
        rolling_max = self.values_series.expanding().max()
        
        # Calculate drawdown series
        drawdown = (self.values_series - rolling_max) / rolling_max
        
        # Return the maximum (most negative) drawdown
        return drawdown.min()
    
    def calculate_calmar_ratio(self) -> Optional[float]:
        """Calculate Calmar ratio (annual return / max drawdown)."""
        annual_return = self.calculate_annual_return()
        max_drawdown = self.calculate_max_drawdown()
        
        if annual_return is None or max_drawdown is None or max_drawdown == 0:
            return None
        
        return annual_return / abs(max_drawdown)
    
    def calculate_beta(self, benchmark_returns: pd.Series) -> Optional[float]:
        """Calculate beta relative to a benchmark.
        
        Args:
            benchmark_returns: Series of benchmark returns (same dates as portfolio)
            
        Returns:
            Beta coefficient
        """
        if self.returns_series.empty or benchmark_returns.empty:
            return None
        
        # Align the series by dates
        aligned_data = pd.DataFrame({
            'portfolio': self.returns_series,
            'benchmark': benchmark_returns
        }).dropna()
        
        if len(aligned_data) < 2:
            return None
        
        # Calculate covariance and benchmark variance
        covariance = aligned_data['portfolio'].cov(aligned_data['benchmark'])
        benchmark_variance = aligned_data['benchmark'].var()
        
        if benchmark_variance == 0:
            return None
        
        return covariance / benchmark_variance
    
    def calculate_alpha(self, benchmark_returns: pd.Series) -> Optional[float]:
        """Calculate alpha (excess return over benchmark, adjusted for beta).
        
        Args:
            benchmark_returns: Series of benchmark returns
            
        Returns:
            Alpha (annualized)
        """
        portfolio_return = self.calculate_annual_return()
        beta = self.calculate_beta(benchmark_returns)
        
        if portfolio_return is None or beta is None:
            return None
        
        # Calculate benchmark return
        if benchmark_returns.empty:
            return None
        
        # Annualize benchmark return
        total_benchmark_return = (1 + benchmark_returns).prod() - 1
        days = len(benchmark_returns)
        years = days / 252  # Trading days
        
        if years <= 0:
            return None
        
        annual_benchmark_return = (1 + total_benchmark_return) ** (1 / years) - 1
        
        # Alpha = Portfolio Return - Risk Free Rate - Beta * (Benchmark Return - Risk Free Rate)
        expected_return = self.risk_free_rate + beta * (annual_benchmark_return - self.risk_free_rate)
        alpha = portfolio_return - expected_return
        
        return alpha
    
    def calculate_information_ratio(self, benchmark_returns: pd.Series) -> Optional[float]:
        """Calculate information ratio (alpha / tracking error)."""
        if self.returns_series.empty or benchmark_returns.empty:
            return None
        
        # Align the series
        aligned_data = pd.DataFrame({
            'portfolio': self.returns_series,
            'benchmark': benchmark_returns
        }).dropna()
        
        if len(aligned_data) < 2:
            return None
        
        # Calculate excess returns
        excess_returns = aligned_data['portfolio'] - aligned_data['benchmark']
        
        # Information ratio = mean excess return / std of excess returns
        mean_excess = excess_returns.mean()
        std_excess = excess_returns.std()
        
        if std_excess == 0:
            return None
        
        # Annualize
        annual_mean_excess = mean_excess * 252
        annual_std_excess = std_excess * np.sqrt(252)
        
        return annual_mean_excess / annual_std_excess
    
    def calculate_value_at_risk(self, confidence_level: float = 0.05) -> Optional[float]:
        """Calculate Value at Risk (VaR) at given confidence level.
        
        Args:
            confidence_level: Confidence level (0.05 = 5% VaR)
            
        Returns:
            VaR as a percentage
        """
        if self.returns_series.empty:
            return None
        
        return self.returns_series.quantile(confidence_level)
    
    def calculate_expected_shortfall(self, confidence_level: float = 0.05) -> Optional[float]:
        """Calculate Expected Shortfall (Conditional VaR).
        
        Args:
            confidence_level: Confidence level
            
        Returns:
            Expected Shortfall as a percentage
        """
        var = self.calculate_value_at_risk(confidence_level)
        
        if var is None:
            return None
        
        # Expected shortfall is the mean of returns below VaR
        tail_returns = self.returns_series[self.returns_series <= var]
        
        if tail_returns.empty:
            return var  # If no returns below VaR, return VaR itself
        
        return tail_returns.mean()
    
    def calculate_win_rate(self, positions: List) -> float:
        """Calculate win rate from a list of positions.
        
        Args:
            positions: List of Position objects with return_pct attribute
            
        Returns:
            Win rate as a percentage (0.0 to 1.0)
        """
        if not positions:
            return 0.0
        
        profitable_positions = sum(1 for p in positions 
                                 if hasattr(p, 'return_pct') and p.return_pct and p.return_pct > 0)
        
        return profitable_positions / len(positions)
    
    def calculate_profit_factor(self, positions: List) -> Optional[float]:
        """Calculate profit factor (gross profit / gross loss).
        
        Args:
            positions: List of Position objects
            
        Returns:
            Profit factor
        """
        if not positions:
            return None
        
        gross_profit = sum(p.return_dollars for p in positions 
                          if hasattr(p, 'return_dollars') and p.return_dollars and p.return_dollars > 0)
        gross_loss = abs(sum(p.return_dollars for p in positions 
                            if hasattr(p, 'return_dollars') and p.return_dollars and p.return_dollars < 0))
        
        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else None
        
        return gross_profit / gross_loss
    
    def calculate_average_trade_return(self, positions: List) -> Optional[float]:
        """Calculate average return per trade.
        
        Args:
            positions: List of Position objects
            
        Returns:
            Average trade return as percentage
        """
        if not positions:
            return None
        
        returns = [p.return_pct for p in positions 
                  if hasattr(p, 'return_pct') and p.return_pct is not None]
        
        if not returns:
            return None
        
        return sum(returns) / len(returns)
    
    def get_performance_summary(self, positions: List = None) -> Dict[str, float]:
        """Get a comprehensive performance summary.
        
        Args:
            positions: Optional list of positions for trade-level metrics
            
        Returns:
            Dictionary with all performance metrics
        """
        summary = {
            'total_return': self.calculate_total_return(),
            'annual_return': self.calculate_annual_return(),
            'volatility': self.calculate_volatility(),
            'sharpe_ratio': self.calculate_sharpe_ratio(),
            'sortino_ratio': self.calculate_sortino_ratio(),
            'max_drawdown': self.calculate_max_drawdown(),
            'calmar_ratio': self.calculate_calmar_ratio(),
            'var_5pct': self.calculate_value_at_risk(0.05),
            'expected_shortfall': self.calculate_expected_shortfall(0.05)
        }
        
        # Add position-based metrics if positions provided
        if positions:
            summary.update({
                'win_rate': self.calculate_win_rate(positions),
                'profit_factor': self.calculate_profit_factor(positions),
                'avg_trade_return': self.calculate_average_trade_return(positions),
                'total_trades': len(positions)
            })
        
        return summary


def compare_performance(results: Dict[str, 'BacktestResult']) -> pd.DataFrame:
    """Compare performance across multiple backtest results.
    
    Args:
        results: Dictionary mapping strategy names to BacktestResult objects
        
    Returns:
        DataFrame with performance comparison
    """
    comparison_data = []
    
    for name, result in results.items():
        perf_calc = PerformanceCalculator(result.daily_values, result.initial_capital)
        summary = perf_calc.get_performance_summary(result.positions)
        
        row = {
            'Strategy': name,
            'Total Return': summary['total_return'],
            'Annual Return': summary['annual_return'],
            'Sharpe Ratio': summary['sharpe_ratio'],
            'Max Drawdown': summary['max_drawdown'],
            'Win Rate': summary.get('win_rate'),
            'Total Trades': summary.get('total_trades'),
            'Profit Factor': summary.get('profit_factor')
        }
        
        comparison_data.append(row)
    
    return pd.DataFrame(comparison_data).set_index('Strategy')


if __name__ == "__main__":
    # Example usage
    from datetime import date, timedelta
    
    # Create sample daily values
    start_date = date(2023, 1, 1)
    end_date = date(2023, 12, 31)
    
    # Simulate daily portfolio values (random walk)
    np.random.seed(42)
    dates = pd.date_range(start_date, end_date, freq='D')
    daily_returns = np.random.normal(0.0005, 0.02, len(dates))  # ~12% annual return, 20% vol
    
    initial_capital = 100000
    portfolio_values = initial_capital * (1 + pd.Series(daily_returns).cumsum().apply(np.exp))
    
    daily_values = dict(zip(dates.date, portfolio_values))
    
    # Calculate performance metrics
    perf_calc = PerformanceCalculator(daily_values, initial_capital)
    summary = perf_calc.get_performance_summary()
    
    print("Performance Summary:")
    print("-" * 30)
    for metric, value in summary.items():
        if value is not None:
            if 'return' in metric.lower() or 'ratio' in metric.lower():
                print(f"{metric:20}: {value:8.2%}")
            else:
                print(f"{metric:20}: {value:8.4f}")
        else:
            print(f"{metric:20}: N/A")
