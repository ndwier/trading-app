"""
Trade Backtesting Engine.

Analyzes historical performance of insider trades to show:
- What returns you'd get following insiders
- Win rates at different time periods
- Best entry timing
- Benchmark comparisons
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)


class TradeBacktester:
    """Backtests insider trades against historical price data."""
    
    def __init__(self):
        self.holding_periods = [7, 14, 30, 60, 90, 180, 365]  # Days
    
    def backtest_trade(self, ticker: str, trade_date: datetime, entry_price: float) -> Dict:
        """
        Backtest a single trade.
        
        Returns performance at multiple time horizons.
        """
        try:
            stock = yf.Ticker(ticker)
            
            # Get price data from trade date to now
            end_date = min(datetime.now(), trade_date + timedelta(days=400))
            hist = stock.history(start=trade_date, end=end_date)
            
            if hist.empty:
                return {'error': 'No price data available'}
            
            # Get actual entry price (close on trade date or next available)
            if not entry_price:
                entry_price = float(hist['Close'].iloc[0])
            
            results = {
                'ticker': ticker,
                'trade_date': trade_date.strftime('%Y-%m-%d'),
                'entry_price': entry_price,
                'current_price': float(hist['Close'].iloc[-1]),
                'days_held': (datetime.now() - trade_date).days,
                'periods': {}
            }
            
            # Calculate returns at each holding period
            for days in self.holding_periods:
                target_date = trade_date + timedelta(days=days)
                
                # Skip if target date is in the future
                if target_date > datetime.now():
                    continue
                
                # Find closest price to target date
                # Convert target_date to pandas Timestamp and localize to match hist.index timezone
                import pandas as pd
                target_ts = pd.Timestamp(target_date).tz_localize(hist.index.tz) if hist.index.tz else pd.Timestamp(target_date)
                period_data = hist[hist.index <= target_ts]
                
                if not period_data.empty:
                    exit_price = float(period_data['Close'].iloc[-1])
                    return_pct = ((exit_price - entry_price) / entry_price) * 100
                    
                    # Calculate max gain/loss during period
                    trade_ts = pd.Timestamp(trade_date).tz_localize(hist.index.tz) if hist.index.tz else pd.Timestamp(trade_date)
                    period_prices = hist[(hist.index >= trade_ts) & (hist.index <= target_ts)]
                    if not period_prices.empty:
                        max_price = float(period_prices['High'].max())
                        min_price = float(period_prices['Low'].min())
                        max_gain = ((max_price - entry_price) / entry_price) * 100
                        max_drawdown = ((min_price - entry_price) / entry_price) * 100
                    else:
                        max_gain = return_pct
                        max_drawdown = return_pct
                    
                    results['periods'][f'{days}d'] = {
                        'days': days,
                        'exit_price': exit_price,
                        'return_pct': round(return_pct, 2),
                        'max_gain': round(max_gain, 2),
                        'max_drawdown': round(max_drawdown, 2),
                        'profitable': return_pct > 0
                    }
            
            return results
            
        except Exception as e:
            logger.error(f"Error backtesting {ticker}: {e}")
            return {'error': str(e)}
    
    def backtest_ticker_history(self, ticker: str, trades: List[Dict]) -> Dict:
        """
        Backtest all insider trades for a ticker.
        
        Returns aggregated statistics.
        """
        results = []
        
        for trade in trades:
            # Handle date formats
            trade_date = trade['date']
            if isinstance(trade_date, str):
                trade_date = datetime.strptime(trade_date, '%Y-%m-%d')
            elif hasattr(trade_date, 'year'):  # datetime.date object
                trade_date = datetime.combine(trade_date, datetime.min.time())
            
            entry_price = trade.get('price')
            
            # Only backtest trades old enough to have meaningful data
            if (datetime.now() - trade_date).days < 7:
                continue
            
            backtest = self.backtest_trade(ticker, trade_date, entry_price)
            
            if 'error' not in backtest:
                backtest['insider'] = trade.get('insider', 'Unknown')
                backtest['amount'] = trade.get('amount', 0)
                results.append(backtest)
        
        if not results:
            return {'error': 'No trades to backtest'}
        
        # Aggregate statistics
        stats = self._calculate_aggregate_stats(results)
        
        return {
            'ticker': ticker,
            'total_trades_analyzed': len(results),
            'aggregate_stats': stats,
            'individual_trades': results[:10],  # Return top 10 for detail
            'best_trade': max(results, key=lambda x: x.get('periods', {}).get('30d', {}).get('return_pct', -999)),
            'worst_trade': min(results, key=lambda x: x.get('periods', {}).get('30d', {}).get('return_pct', 999))
        }
    
    def _calculate_aggregate_stats(self, results: List[Dict]) -> Dict:
        """Calculate aggregated statistics across all trades."""
        stats = {}
        
        for days in self.holding_periods:
            period_key = f'{days}d'
            period_returns = []
            
            for r in results:
                if period_key in r.get('periods', {}):
                    period_returns.append(r['periods'][period_key]['return_pct'])
            
            if period_returns:
                winning = [r for r in period_returns if r > 0]
                losing = [r for r in period_returns if r <= 0]
                
                stats[period_key] = {
                    'avg_return': round(sum(period_returns) / len(period_returns), 2),
                    'median_return': round(sorted(period_returns)[len(period_returns)//2], 2),
                    'win_rate': round((len(winning) / len(period_returns)) * 100, 1),
                    'avg_winner': round(sum(winning) / len(winning), 2) if winning else 0,
                    'avg_loser': round(sum(losing) / len(losing), 2) if losing else 0,
                    'best_return': round(max(period_returns), 2),
                    'worst_return': round(min(period_returns), 2),
                    'total_trades': len(period_returns)
                }
        
        return stats
    
    def analyze_entry_timing(self, ticker: str, trades: List[Dict]) -> Dict:
        """
        Analyze optimal entry timing after insider trade disclosure.
        
        Tests different entry delays (0, 1, 3, 5, 10 days after disclosure).
        """
        entry_delays = [0, 1, 3, 5, 10]
        delay_results = {delay: [] for delay in entry_delays}
        
        for trade in trades:
            # Handle date formats
            trade_date = trade['date']
            if isinstance(trade_date, str):
                trade_date = datetime.strptime(trade_date, '%Y-%m-%d')
            elif hasattr(trade_date, 'year'):  # datetime.date object
                trade_date = datetime.combine(trade_date, datetime.min.time())
            
            # Skip if too recent
            if (datetime.now() - trade_date).days < 30:
                continue
            
            try:
                stock = yf.Ticker(ticker)
                
                for delay in entry_delays:
                    entry_date = trade_date + timedelta(days=delay)
                    target_date = entry_date + timedelta(days=30)  # 30-day holding period
                    
                    hist = stock.history(start=entry_date, end=target_date + timedelta(days=5))
                    
                    if not hist.empty and len(hist) > 1:
                        entry_price = float(hist['Close'].iloc[0])
                        
                        # Find exit price
                        exit_data = hist[hist.index >= target_date]
                        if not exit_data.empty:
                            exit_price = float(exit_data['Close'].iloc[0])
                            return_pct = ((exit_price - entry_price) / entry_price) * 100
                            delay_results[delay].append(return_pct)
                
            except Exception as e:
                logger.error(f"Error analyzing entry timing for {ticker}: {e}")
                continue
        
        # Calculate stats for each delay
        timing_stats = {}
        for delay, returns in delay_results.items():
            if returns:
                timing_stats[f'{delay}_days'] = {
                    'avg_return': round(sum(returns) / len(returns), 2),
                    'win_rate': round((len([r for r in returns if r > 0]) / len(returns)) * 100, 1),
                    'sample_size': len(returns)
                }
        
        # Find optimal entry
        if timing_stats:
            optimal = max(timing_stats.items(), key=lambda x: x[1]['avg_return'])
            
            return {
                'ticker': ticker,
                'timing_analysis': timing_stats,
                'optimal_entry': {
                    'delay_days': int(optimal[0].split('_')[0]),
                    'avg_return': optimal[1]['avg_return'],
                    'win_rate': optimal[1]['win_rate'],
                    'recommendation': self._get_timing_recommendation(int(optimal[0].split('_')[0]))
                }
            }
        
        return {'error': 'Insufficient data for timing analysis'}
    
    def _get_timing_recommendation(self, delay_days: int) -> str:
        """Generate timing recommendation."""
        if delay_days == 0:
            return "Buy immediately upon disclosure for best results"
        elif delay_days == 1:
            return "Wait 1 day after disclosure for optimal entry"
        elif delay_days <= 3:
            return f"Wait {delay_days} days after disclosure for better entry"
        else:
            return f"Wait {delay_days} days for potential pullback before entry"
    
    def compare_to_benchmark(self, ticker: str, trades: List[Dict], benchmark: str = 'SPY') -> Dict:
        """
        Compare insider trade performance to benchmark (default S&P 500).
        """
        trade_returns = []
        benchmark_returns = []
        
        for trade in trades[:20]:  # Limit to 20 most recent
            # Handle date formats
            trade_date = trade['date']
            if isinstance(trade_date, str):
                trade_date = datetime.strptime(trade_date, '%Y-%m-%d')
            elif hasattr(trade_date, 'year'):  # datetime.date object
                trade_date = datetime.combine(trade_date, datetime.min.time())
            
            # Skip if too recent
            if (datetime.now() - trade_date).days < 30:
                continue
            
            try:
                # Get stock performance
                stock = yf.Ticker(ticker)
                stock_hist = stock.history(start=trade_date, end=trade_date + timedelta(days=35))
                
                # Get benchmark performance
                bench = yf.Ticker(benchmark)
                bench_hist = bench.history(start=trade_date, end=trade_date + timedelta(days=35))
                
                if len(stock_hist) > 5 and len(bench_hist) > 5:
                    stock_return = ((float(stock_hist['Close'].iloc[-1]) - float(stock_hist['Close'].iloc[0])) / 
                                   float(stock_hist['Close'].iloc[0])) * 100
                    
                    bench_return = ((float(bench_hist['Close'].iloc[-1]) - float(bench_hist['Close'].iloc[0])) / 
                                   float(bench_hist['Close'].iloc[0])) * 100
                    
                    trade_returns.append(stock_return)
                    benchmark_returns.append(bench_return)
                    
            except Exception as e:
                logger.error(f"Error comparing to benchmark: {e}")
                continue
        
        if not trade_returns:
            return {'error': 'Insufficient data for benchmark comparison'}
        
        avg_stock = sum(trade_returns) / len(trade_returns)
        avg_bench = sum(benchmark_returns) / len(benchmark_returns)
        alpha = avg_stock - avg_bench
        
        stock_wins = len([r for r in trade_returns if r > 0])
        bench_wins = len([r for r in benchmark_returns if r > 0])
        
        return {
            'ticker': ticker,
            'benchmark': benchmark,
            'sample_size': len(trade_returns),
            'avg_stock_return': round(avg_stock, 2),
            'avg_benchmark_return': round(avg_bench, 2),
            'alpha': round(alpha, 2),
            'stock_win_rate': round((stock_wins / len(trade_returns)) * 100, 1),
            'benchmark_win_rate': round((bench_wins / len(benchmark_returns)) * 100, 1),
            'outperformance': alpha > 0,
            'summary': self._get_benchmark_summary(alpha, avg_stock)
        }
    
    def _get_benchmark_summary(self, alpha: float, avg_return: float) -> str:
        """Generate benchmark comparison summary."""
        if alpha > 10:
            return f"🚀 Massively outperforms S&P 500 by {alpha:.1f}pp - following insiders is highly profitable!"
        elif alpha > 5:
            return f"✅ Strongly outperforms S&P 500 by {alpha:.1f}pp - insider trades show edge"
        elif alpha > 2:
            return f"📈 Outperforms S&P 500 by {alpha:.1f}pp - positive alpha"
        elif alpha > -2:
            return f"➖ Roughly matches S&P 500 (±{abs(alpha):.1f}pp)"
        else:
            return f"❌ Underperforms S&P 500 by {abs(alpha):.1f}pp - insiders may not have edge here"
    
    def get_comprehensive_analysis(self, ticker: str, trades: List[Dict]) -> Dict:
        """
        Get comprehensive backtesting analysis.
        
        Combines all backtesting metrics into one report.
        """
        logger.info(f"Running comprehensive analysis for {ticker} with {len(trades)} trades")
        
        # 1. Backtest all trades
        backtest_results = self.backtest_ticker_history(ticker, trades)
        
        # 2. Analyze entry timing
        timing_analysis = self.analyze_entry_timing(ticker, trades)
        
        # 3. Compare to benchmark
        benchmark_comp = self.compare_to_benchmark(ticker, trades)
        
        # 4. Calculate overall score
        score = self._calculate_strategy_score(backtest_results, benchmark_comp)
        
        return {
            'ticker': ticker,
            'total_insider_trades': len(trades),
            'backtest_results': backtest_results,
            'timing_analysis': timing_analysis,
            'benchmark_comparison': benchmark_comp,
            'strategy_score': score,
            'recommendation': self._generate_final_recommendation(score, backtest_results, benchmark_comp),
            'generated_at': datetime.now().isoformat()
        }
    
    def _calculate_strategy_score(self, backtest: Dict, benchmark: Dict) -> Dict:
        """Calculate overall strategy score (0-100)."""
        score = 50  # Start at neutral
        
        # Factor 1: 30-day win rate
        if 'aggregate_stats' in backtest and '30d' in backtest['aggregate_stats']:
            win_rate = backtest['aggregate_stats']['30d']['win_rate']
            if win_rate > 70:
                score += 20
            elif win_rate > 60:
                score += 15
            elif win_rate > 50:
                score += 10
            elif win_rate < 40:
                score -= 10
        
        # Factor 2: Average return
        if 'aggregate_stats' in backtest and '30d' in backtest['aggregate_stats']:
            avg_return = backtest['aggregate_stats']['30d']['avg_return']
            score += min(avg_return / 2, 15)  # Max 15 points
        
        # Factor 3: Alpha vs benchmark
        if 'alpha' in benchmark:
            alpha = benchmark['alpha']
            score += min(alpha, 15)  # Max 15 points
        
        score = max(0, min(100, score))  # Clamp to 0-100
        
        return {
            'score': round(score, 1),
            'rating': self._get_rating(score)
        }
    
    def _get_rating(self, score: float) -> str:
        """Convert score to rating."""
        if score >= 80:
            return 'EXCELLENT'
        elif score >= 70:
            return 'VERY GOOD'
        elif score >= 60:
            return 'GOOD'
        elif score >= 50:
            return 'AVERAGE'
        else:
            return 'POOR'
    
    def _generate_final_recommendation(self, score: Dict, backtest: Dict, benchmark: Dict) -> str:
        """Generate final recommendation."""
        rating = score['rating']
        score_val = score['score']
        
        if rating == 'EXCELLENT':
            return f"🌟 STRONG BUY - Following insiders in {backtest.get('ticker', 'this stock')} has historically been highly profitable (Score: {score_val}/100)"
        elif rating == 'VERY GOOD':
            return f"✅ BUY - Insider trades show strong positive edge (Score: {score_val}/100)"
        elif rating == 'GOOD':
            return f"👍 CONSIDER - Insiders have decent track record (Score: {score_val}/100)"
        elif rating == 'AVERAGE':
            return f"⚠️ NEUTRAL - Insider performance is average (Score: {score_val}/100)"
        else:
            return f"❌ AVOID - Following insiders here has not been profitable (Score: {score_val}/100)"

