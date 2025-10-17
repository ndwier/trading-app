"""
Advanced backtesting module with multiple alpha-generating strategies.
"""

from .advanced_backtest import AdvancedBacktester, BacktestResult, print_backtest_report
from .trade_backtest import TradeBacktester

__all__ = ['AdvancedBacktester', 'BacktestResult', 'print_backtest_report', 'TradeBacktester']
