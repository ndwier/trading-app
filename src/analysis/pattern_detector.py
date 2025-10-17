"""Pattern detection and analysis for insider trades."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import pandas as pd
import numpy as np

from src.database import get_session, Trade, Filer, FilerType


@dataclass
class TradingPattern:
    """Represents a detected trading pattern."""
    
    pattern_type: str
    ticker: str
    confidence: float  # 0.0 to 1.0
    
    # Pattern details
    trades: List[int]  # Trade IDs
    filers: List[int]  # Filer IDs
    time_span_days: int
    total_amount: float
    
    # Pattern-specific metadata
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class PatternDetector:
    """Detects patterns in insider trading data."""
    
    def __init__(self):
        self.pattern_detectors = {
            "unusual_volume": self._detect_unusual_volume,
            "consensus_buying": self._detect_consensus_buying,
            "insider_momentum": self._detect_insider_momentum,
            "sector_rotation": self._detect_sector_rotation,
            "bipartisan_interest": self._detect_bipartisan_interest
        }
    
    def detect_all_patterns(self, days: int = 90) -> List[TradingPattern]:
        """Detect all types of patterns in recent trades."""
        
        patterns = []
        
        for pattern_name, detector_func in self.pattern_detectors.items():
            try:
                detected = detector_func(days)
                patterns.extend(detected)
            except Exception as e:
                print(f"Error detecting {pattern_name}: {e}")
                continue
        
        # Sort by confidence
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        return patterns
    
    def _detect_unusual_volume(self, days: int) -> List[TradingPattern]:
        """Detect tickers with unusually high trading volume."""
        
        patterns = []
        
        with get_session() as session:
            # Get recent trades
            cutoff_date = date.today() - timedelta(days=days)
            
            recent_trades = session.query(Trade).filter(
                Trade.reported_date >= cutoff_date,
                Trade.ticker.isnot(None),
                Trade.amount_usd.isnot(None)
            ).all()
            
            # Group by ticker and calculate volume metrics
            ticker_stats = defaultdict(lambda: {
                'trades': [],
                'total_amount': 0,
                'unique_filers': set(),
                'time_span': 0
            })
            
            for trade in recent_trades:
                stats = ticker_stats[trade.ticker]
                stats['trades'].append(trade)
                stats['total_amount'] += float(trade.amount_usd)
                stats['unique_filers'].add(trade.filer_id)
            
            # Calculate historical averages (simple approach)
            historical_cutoff = cutoff_date - timedelta(days=days * 3)
            historical_trades = session.query(Trade).filter(
                Trade.reported_date >= historical_cutoff,
                Trade.reported_date < cutoff_date,
                Trade.ticker.isnot(None),
                Trade.amount_usd.isnot(None)
            ).all()
            
            # Group historical trades by ticker
            historical_stats = defaultdict(lambda: {'count': 0, 'amount': 0})
            for trade in historical_trades:
                hist_stats = historical_stats[trade.ticker]
                hist_stats['count'] += 1
                hist_stats['amount'] += float(trade.amount_usd)
            
            # Detect unusual volume
            for ticker, stats in ticker_stats.items():
                if len(stats['trades']) < 2:
                    continue
                
                current_count = len(stats['trades'])
                current_amount = stats['total_amount']
                
                # Get historical baseline
                hist_stats = historical_stats.get(ticker, {'count': 0, 'amount': 0})
                
                # Calculate average historical activity per period
                historical_avg_count = hist_stats['count'] / 3 if hist_stats['count'] > 0 else 1
                historical_avg_amount = hist_stats['amount'] / 3 if hist_stats['amount'] > 0 else current_amount
                
                # Check for unusual activity (2x or more than historical average)
                count_ratio = current_count / historical_avg_count
                amount_ratio = current_amount / historical_avg_amount
                
                if count_ratio >= 2.0 or amount_ratio >= 2.0:
                    # Calculate time span
                    trade_dates = [t.reported_date for t in stats['trades'] if t.reported_date]
                    if trade_dates:
                        time_span = (max(trade_dates) - min(trade_dates)).days
                    else:
                        time_span = 0
                    
                    # Calculate confidence based on ratios and other factors
                    confidence = min(0.9, (count_ratio + amount_ratio) / 6.0)  # Max 90%
                    confidence += min(0.1, len(stats['unique_filers']) / 10)  # Boost for more filers
                    
                    pattern = TradingPattern(
                        pattern_type="unusual_volume",
                        ticker=ticker,
                        confidence=min(1.0, confidence),
                        trades=[t.trade_id for t in stats['trades']],
                        filers=list(stats['unique_filers']),
                        time_span_days=time_span,
                        total_amount=current_amount,
                        metadata={
                            'count_ratio': count_ratio,
                            'amount_ratio': amount_ratio,
                            'trade_count': current_count,
                            'filer_count': len(stats['unique_filers'])
                        }
                    )
                    
                    patterns.append(pattern)
        
        return patterns
    
    def _detect_consensus_buying(self, days: int) -> List[TradingPattern]:
        """Detect consensus buying (multiple different filers buying same stock)."""
        
        patterns = []
        
        with get_session() as session:
            cutoff_date = date.today() - timedelta(days=days)
            
            # Get recent buy trades
            recent_buys = session.query(Trade).filter(
                Trade.reported_date >= cutoff_date,
                Trade.ticker.isnot(None),
                Trade.transaction_type.in_(['buy', 'option_buy'])
            ).all()
            
            # Group by ticker
            ticker_buys = defaultdict(list)
            for trade in recent_buys:
                ticker_buys[trade.ticker].append(trade)
            
            # Look for consensus (3+ different filers buying same ticker)
            for ticker, trades in ticker_buys.items():
                unique_filers = set(t.filer_id for t in trades)
                
                if len(unique_filers) >= 3:  # At least 3 different buyers
                    
                    # Calculate time span
                    trade_dates = [t.reported_date for t in trades if t.reported_date]
                    if trade_dates:
                        time_span = (max(trade_dates) - min(trade_dates)).days
                    else:
                        time_span = 0
                    
                    total_amount = sum(float(t.amount_usd) for t in trades if t.amount_usd)
                    
                    # Higher confidence for more filers and larger amounts
                    base_confidence = min(0.8, len(unique_filers) / 10)
                    amount_boost = min(0.2, total_amount / 10000000)  # Boost for $10M+
                    confidence = base_confidence + amount_boost
                    
                    pattern = TradingPattern(
                        pattern_type="consensus_buying",
                        ticker=ticker,
                        confidence=min(1.0, confidence),
                        trades=[t.trade_id for t in trades],
                        filers=list(unique_filers),
                        time_span_days=time_span,
                        total_amount=total_amount,
                        metadata={
                            'filer_count': len(unique_filers),
                            'trade_count': len(trades),
                            'avg_amount_per_filer': total_amount / len(unique_filers)
                        }
                    )
                    
                    patterns.append(pattern)
        
        return patterns
    
    def _detect_insider_momentum(self, days: int) -> List[TradingPattern]:
        """Detect momentum patterns (repeated buying by same filers)."""
        
        patterns = []
        
        with get_session() as session:
            cutoff_date = date.today() - timedelta(days=days)
            
            # Get recent trades grouped by filer
            recent_trades = session.query(Trade).filter(
                Trade.reported_date >= cutoff_date,
                Trade.ticker.isnot(None),
                Trade.transaction_type.in_(['buy', 'option_buy'])
            ).all()
            
            # Group by filer and ticker
            filer_ticker_trades = defaultdict(lambda: defaultdict(list))
            for trade in recent_trades:
                filer_ticker_trades[trade.filer_id][trade.ticker].append(trade)
            
            # Look for repeated buying patterns
            for filer_id, ticker_trades in filer_ticker_trades.items():
                for ticker, trades in ticker_trades.items():
                    if len(trades) >= 3:  # At least 3 trades by same filer
                        
                        # Check if trades are spread over time (not just one-off)
                        trade_dates = sorted([t.reported_date for t in trades if t.reported_date])
                        if len(trade_dates) >= 2:
                            time_span = (trade_dates[-1] - trade_dates[0]).days
                            
                            # Must be spread over at least a week
                            if time_span >= 7:
                                total_amount = sum(float(t.amount_usd) for t in trades if t.amount_usd)
                                
                                # Confidence based on consistency and amount
                                consistency = len(trades) / 10  # More trades = higher confidence
                                amount_factor = min(0.3, total_amount / 5000000)  # Up to 30% for $5M+
                                time_factor = min(0.2, time_span / 90)  # Up to 20% for 3 months
                                
                                confidence = min(1.0, consistency + amount_factor + time_factor)
                                
                                pattern = TradingPattern(
                                    pattern_type="insider_momentum",
                                    ticker=ticker,
                                    confidence=confidence,
                                    trades=[t.trade_id for t in trades],
                                    filers=[filer_id],
                                    time_span_days=time_span,
                                    total_amount=total_amount,
                                    metadata={
                                        'filer_name': trades[0].filer.name if trades[0].filer else 'Unknown',
                                        'trade_count': len(trades),
                                        'avg_trade_size': total_amount / len(trades),
                                        'trade_frequency_days': time_span / len(trades)
                                    }
                                )
                                
                                patterns.append(pattern)
        
        return patterns
    
    def _detect_sector_rotation(self, days: int) -> List[TradingPattern]:
        """Detect sector rotation patterns (coordinated moves within sectors)."""
        
        # This is a simplified implementation - would need sector mapping
        # For now, return empty list
        return []
    
    def _detect_bipartisan_interest(self, days: int) -> List[TradingPattern]:
        """Detect bipartisan political interest in stocks."""
        
        patterns = []
        
        with get_session() as session:
            cutoff_date = date.today() - timedelta(days=days)
            
            # Get political trades only
            political_trades = session.query(Trade).join(Filer).filter(
                Trade.reported_date >= cutoff_date,
                Trade.ticker.isnot(None),
                Filer.filer_type == FilerType.POLITICIAN,
                Filer.party.isnot(None),
                Trade.transaction_type.in_(['buy', 'option_buy'])
            ).all()
            
            # Group by ticker and party
            ticker_party_trades = defaultdict(lambda: defaultdict(list))
            for trade in political_trades:
                if trade.filer.party:
                    ticker_party_trades[trade.ticker][trade.filer.party].append(trade)
            
            # Look for bipartisan interest
            for ticker, party_trades in ticker_party_trades.items():
                parties = set(party_trades.keys())
                
                # Check if both major parties are represented
                if 'Republican' in parties and 'Democrat' in parties:
                    
                    all_trades = []
                    for party_trade_list in party_trades.values():
                        all_trades.extend(party_trade_list)
                    
                    # Calculate metrics
                    trade_dates = [t.reported_date for t in all_trades if t.reported_date]
                    if trade_dates:
                        time_span = (max(trade_dates) - min(trade_dates)).days
                    else:
                        time_span = 0
                    
                    total_amount = sum(float(t.amount_usd) for t in all_trades if t.amount_usd)
                    unique_filers = set(t.filer_id for t in all_trades)
                    
                    # High confidence for bipartisan agreement
                    party_balance = min(len(party_trades['Republican']), len(party_trades['Democrat']))
                    balance_factor = min(0.6, party_balance / 3)  # Up to 60% for balanced representation
                    amount_factor = min(0.3, total_amount / 5000000)  # Up to 30% for large amounts
                    
                    confidence = balance_factor + amount_factor + 0.1  # Base 10% for bipartisan
                    
                    pattern = TradingPattern(
                        pattern_type="bipartisan_interest",
                        ticker=ticker,
                        confidence=min(1.0, confidence),
                        trades=[t.trade_id for t in all_trades],
                        filers=list(unique_filers),
                        time_span_days=time_span,
                        total_amount=total_amount,
                        metadata={
                            'republican_trades': len(party_trades.get('Republican', [])),
                            'democrat_trades': len(party_trades.get('Democrat', [])),
                            'other_party_trades': sum(len(trades) for party, trades in party_trades.items() 
                                                    if party not in ['Republican', 'Democrat']),
                            'party_count': len(parties)
                        }
                    )
                    
                    patterns.append(pattern)
        
        return patterns


if __name__ == "__main__":
    # CLI for running pattern detection
    import argparse
    
    parser = argparse.ArgumentParser(description="Detect trading patterns")
    parser.add_argument("--days", type=int, default=90,
                       help="Number of days to analyze")
    parser.add_argument("--pattern", choices=list(PatternDetector().pattern_detectors.keys()) + ["all"],
                       default="all", help="Pattern type to detect")
    
    args = parser.parse_args()
    
    detector = PatternDetector()
    
    if args.pattern == "all":
        patterns = detector.detect_all_patterns(args.days)
    else:
        detector_func = detector.pattern_detectors[args.pattern]
        patterns = detector_func(args.days)
    
    print(f"\nDetected {len(patterns)} patterns:")
    print("-" * 60)
    
    for pattern in patterns[:20]:  # Show top 20
        print(f"{pattern.pattern_type:20} | {pattern.ticker:6} | "
              f"{pattern.confidence:6.2%} | {len(pattern.trades):3d} trades | "
              f"${pattern.total_amount:10,.0f}")
    
    if len(patterns) > 20:
        print(f"... and {len(patterns) - 20} more patterns")
