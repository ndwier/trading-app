#!/usr/bin/env python3
"""
Run comprehensive backtesting across multiple strategies.
"""

import sys
import os
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.backtesting.advanced_backtest import AdvancedBacktester, print_backtest_report
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Run backtests."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run backtest strategies')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)', 
                       default=(datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'))
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)', 
                       default=datetime.now().strftime('%Y-%m-%d'))
    
    args = parser.parse_args()
    
    logger.info(f"Starting backtest from {args.start} to {args.end}")
    
    backtester = AdvancedBacktester(start_date=args.start, end_date=args.end)
    
    print("\n🚀 Running all strategies...\n")
    results = backtester.run_all_strategies()
    
    print_backtest_report(results)
    
    # Find best strategy
    best_strategy = None
    best_sharpe = -999
    
    for name, result in results.items():
        if result.sharpe_ratio > best_sharpe:
            best_sharpe = result.sharpe_ratio
            best_strategy = result
    
    if best_strategy:
        print("="*80)
        print(f"🏆 BEST STRATEGY: {best_strategy.strategy_name}")
        print(f"   Sharpe Ratio: {best_strategy.sharpe_ratio:.2f}")
        print(f"   Total Return: {best_strategy.total_return*100:.2f}%")
        print(f"   Win Rate: {best_strategy.win_rate*100:.1f}%")
        print("="*80 + "\n")


if __name__ == '__main__':
    main()

