"""
Signal Performance Tracking System.

Tracks the performance of generated signals over time to measure accuracy
and identify which insiders/strategies produce the best results.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List
import yfinance as yf

from src.database import get_session
from src.database.models import Signal, SignalPerformance, Filer, Trade

logger = logging.getLogger(__name__)


class SignalTracker:
    """Tracks and evaluates signal performance over time."""
    
    def __init__(self):
        self.evaluation_periods = [1, 7, 14, 30, 60, 90]  # Days to track
    
    def evaluate_all_signals(self) -> Dict:
        """Evaluate performance of all active signals."""
        with get_session() as session:
            signals = session.query(Signal).filter(
                Signal.is_active == True,
                Signal.generated_at.isnot(None)
            ).all()
            
            evaluated = 0
            updated = 0
            
            for signal in signals:
                try:
                    if self._evaluate_signal(signal, session):
                        updated += 1
                    evaluated += 1
                except Exception as e:
                    logger.error(f"Error evaluating signal {signal.signal_id}: {e}")
                    continue
            
            session.commit()
            
            return {
                'evaluated': evaluated,
                'updated': updated,
                'timestamp': datetime.now().isoformat()
            }
    
    def _evaluate_signal(self, signal: Signal, session) -> bool:
        """Evaluate a single signal's performance."""
        days_since = (datetime.now() - signal.generated_at).days
        
        if days_since < 1:
            return False  # Too soon to evaluate
        
        # Get current price
        try:
            ticker_data = yf.Ticker(signal.ticker)
            hist = ticker_data.history(period='5d')
            
            if hist.empty:
                logger.warning(f"No price data for {signal.ticker}")
                return False
            
            current_price = float(hist['Close'].iloc[-1])
            
            # Get price when signal was generated
            signal_date = signal.generated_at.date()
            hist_at_signal = ticker_data.history(start=signal_date, end=signal_date + timedelta(days=3))
            
            if hist_at_signal.empty:
                logger.warning(f"No historical price for {signal.ticker} at {signal_date}")
                return False
            
            signal_price = float(hist_at_signal['Close'].iloc[0])
            
            # Calculate return
            return_pct = (current_price - signal_price) / signal_price
            
            # Check if we already have a performance record for this evaluation period
            existing = session.query(SignalPerformance).filter(
                SignalPerformance.signal_id == signal.signal_id,
                SignalPerformance.days_since_signal == days_since
            ).first()
            
            if existing:
                # Update existing record
                existing.evaluation_date = datetime.now().date()
                existing.current_price = current_price
                existing.return_pct = return_pct
            else:
                # Create new performance record
                perf = SignalPerformance(
                    signal_id=signal.signal_id,
                    evaluation_date=datetime.now().date(),
                    days_since_signal=days_since,
                    signal_price=signal_price,
                    current_price=current_price,
                    return_pct=return_pct
                )
                session.add(perf)
            
            return True
            
        except Exception as e:
            logger.error(f"Error getting price for {signal.ticker}: {e}")
            return False
    
    def get_signal_performance_summary(self, days: int = 30) -> Dict:
        """Get summary statistics of signal performance."""
        cutoff = datetime.now() - timedelta(days=days)
        
        with get_session() as session:
            # Get all evaluated signals
            performances = session.query(SignalPerformance).join(Signal).filter(
                Signal.generated_at >= cutoff
            ).all()
            
            if not performances:
                return {
                    'period_days': days,
                    'total_signals': 0,
                    'avg_return': 0,
                    'win_rate': 0,
                    'best_performer': None,
                    'worst_performer': None
                }
            
            returns = [p.return_pct for p in performances if p.return_pct is not None]
            winning = [r for r in returns if r > 0]
            
            # Get best and worst
            best = max(performances, key=lambda p: p.return_pct or 0)
            worst = min(performances, key=lambda p: p.return_pct or 0)
            
            return {
                'period_days': days,
                'total_signals': len(performances),
                'avg_return': sum(returns) / len(returns) if returns else 0,
                'win_rate': len(winning) / len(returns) if returns else 0,
                'best_performer': {
                    'ticker': best.signal.ticker,
                    'return_pct': float(best.return_pct or 0),
                    'days_held': best.days_since_signal
                } if best else None,
                'worst_performer': {
                    'ticker': worst.signal.ticker,
                    'return_pct': float(worst.return_pct or 0),
                    'days_held': worst.days_since_signal
                } if worst else None
            }
    
    def get_top_performers(self, limit: int = 10) -> List[Dict]:
        """Get top performing signals."""
        with get_session() as session:
            # Get latest performance for each signal
            performances = session.query(SignalPerformance).join(Signal).filter(
                SignalPerformance.return_pct.isnot(None)
            ).order_by(
                SignalPerformance.return_pct.desc()
            ).limit(limit).all()
            
            results = []
            for perf in performances:
                signal = perf.signal
                results.append({
                    'ticker': signal.ticker,
                    'signal_type': signal.signal_type.value if hasattr(signal.signal_type, 'value') else signal.signal_type,
                    'strength': float(signal.strength),
                    'return_pct': float(perf.return_pct * 100),
                    'days_held': perf.days_since_signal,
                    'signal_date': signal.generated_at.strftime('%Y-%m-%d'),
                    'strategy': signal.strategy.name if signal.strategy else 'Unknown'
                })
            
            return results
    
    def get_insider_accuracy(self, limit: int = 20) -> List[Dict]:
        """
        Calculate which insiders have the best track record.
        
        This is a proxy - we look at which insiders' trades led to signals
        that performed well.
        """
        with get_session() as session:
            # This is complex - we need to:
            # 1. Get all signals with performance data
            # 2. Find which trades triggered those signals
            # 3. Aggregate by filer
            
            performances = session.query(SignalPerformance).join(Signal).filter(
                SignalPerformance.return_pct.isnot(None),
                Signal.trigger_trades.isnot(None)
            ).all()
            
            filer_stats = {}
            
            for perf in performances:
                signal = perf.signal
                
                # Parse trigger_trades JSON to get trade IDs
                if signal.trigger_trades:
                    try:
                        trigger_ids = signal.trigger_trades if isinstance(signal.trigger_trades, list) else []
                        
                        for trade_id in trigger_ids[:5]:  # Limit to first 5 to avoid over-counting
                            trade = session.query(Trade).filter(Trade.trade_id == trade_id).first()
                            
                            if trade and trade.filer:
                                filer_name = trade.filer.name
                                
                                if filer_name not in filer_stats:
                                    filer_stats[filer_name] = {
                                        'name': filer_name,
                                        'type': trade.filer.filer_type.value if hasattr(trade.filer.filer_type, 'value') else trade.filer.filer_type,
                                        'total_signals': 0,
                                        'total_return': 0,
                                        'wins': 0
                                    }
                                
                                filer_stats[filer_name]['total_signals'] += 1
                                filer_stats[filer_name]['total_return'] += float(perf.return_pct)
                                if perf.return_pct > 0:
                                    filer_stats[filer_name]['wins'] += 1
                    
                    except Exception as e:
                        logger.error(f"Error parsing trigger_trades for signal {signal.signal_id}: {e}")
                        continue
            
            # Calculate averages and sort
            results = []
            for name, stats in filer_stats.items():
                if stats['total_signals'] >= 2:  # Min 2 signals to be ranked
                    results.append({
                        'name': name,
                        'type': stats['type'],
                        'signal_count': stats['total_signals'],
                        'avg_return': (stats['total_return'] / stats['total_signals']) * 100,
                        'win_rate': (stats['wins'] / stats['total_signals']) * 100,
                        'accuracy_score': (stats['wins'] / stats['total_signals']) * (stats['total_return'] / stats['total_signals']) * 100
                    })
            
            # Sort by accuracy score
            results.sort(key=lambda x: x['accuracy_score'], reverse=True)
            
            return results[:limit]

