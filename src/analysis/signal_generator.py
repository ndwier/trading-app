"""Generate actionable buy/sell/hold signals from detected patterns."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum
import yfinance as yf
import pandas as pd
import numpy as np

from src.database import get_session, Trade, Filer, Signal, Strategy
from src.database.models import TransactionType, DataSource
from .pattern_detector import PatternDetector, TradingPattern
from config.config import config


class SignalStrength(Enum):
    """Signal strength levels."""
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"


class SignalAction(Enum):
    """Signal actions."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    WATCH = "watch"


@dataclass
class TradingSignal:
    """Actionable trading signal for portfolio decisions."""
    
    ticker: str
    action: SignalAction
    strength: SignalStrength
    confidence: float  # 0.0 to 1.0
    
    # Price and timing
    current_price: Optional[float] = None
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    time_horizon_days: Optional[int] = None
    
    # Position sizing
    position_size_pct: Optional[float] = None  # % of portfolio
    max_position_size: Optional[float] = None
    
    # Signal details
    reasoning: str = ""
    supporting_patterns: List[str] = None
    risk_factors: List[str] = None
    
    # Metadata
    generated_at: datetime = None
    expires_at: Optional[datetime] = None
    insider_trades_count: int = 0
    total_insider_amount: float = 0
    
    def __post_init__(self):
        if self.supporting_patterns is None:
            self.supporting_patterns = []
        if self.risk_factors is None:
            self.risk_factors = []
        if self.generated_at is None:
            self.generated_at = datetime.now()


class SignalGenerator:
    """Generates actionable trading signals from patterns."""
    
    def __init__(self):
        self.pattern_detector = PatternDetector()
        
        # Signal configuration
        self.min_confidence = 0.3
        self.max_signals_per_run = 20
        self.default_time_horizon = 60  # days
        
        # Risk management
        self.max_position_size = getattr(config.backtesting, 'MAX_POSITION_SIZE', 0.1)  # 10%
        self.min_position_size = 0.02  # 2%
        
        # Signal strength thresholds
        self.strength_thresholds = {
            SignalStrength.WEAK: 0.3,
            SignalStrength.MODERATE: 0.5,
            SignalStrength.STRONG: 0.7,
            SignalStrength.VERY_STRONG: 0.85
        }
    
    def generate_current_signals(self, days_lookback: int = 90) -> List[TradingSignal]:
        """Generate current buy/sell signals based on recent patterns."""
        
        # Detect patterns
        patterns = self.pattern_detector.detect_all_patterns(days_lookback)
        
        # Filter high-confidence patterns
        high_confidence_patterns = [
            p for p in patterns if p.confidence >= self.min_confidence
        ]
        
        signals = []
        
        # Group patterns by ticker
        ticker_patterns = {}
        for pattern in high_confidence_patterns:
            if pattern.ticker not in ticker_patterns:
                ticker_patterns[pattern.ticker] = []
            ticker_patterns[pattern.ticker].append(pattern)
        
        # Generate signals for each ticker
        for ticker, patterns_list in ticker_patterns.items():
            try:
                signal = self._create_signal_from_patterns(ticker, patterns_list)
                if signal:
                    signals.append(signal)
            except Exception as e:
                print(f"Error generating signal for {ticker}: {e}")
                continue
        
        # Sort by confidence and limit
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals[:self.max_signals_per_run]
    
    def _create_signal_from_patterns(self, ticker: str, 
                                   patterns: List[TradingPattern]) -> Optional[TradingSignal]:
        """Create a trading signal from multiple patterns for the same ticker."""
        
        if not patterns:
            return None
        
        # Calculate aggregate confidence
        total_confidence = sum(p.confidence for p in patterns)
        pattern_count = len(patterns)
        avg_confidence = total_confidence / pattern_count
        
        # Boost confidence for multiple confirming patterns
        pattern_boost = min(0.2, (pattern_count - 1) * 0.05)  # Up to 20% boost
        final_confidence = min(1.0, avg_confidence + pattern_boost)
        
        # Determine signal strength
        strength = self._classify_signal_strength(final_confidence)
        
        # Get current market data
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="5d")
            
            if hist.empty:
                return None
            
            current_price = float(hist['Close'].iloc[-1])
            
        except Exception as e:
            print(f"Failed to get price data for {ticker}: {e}")
            return None
        
        # Calculate position sizing
        position_size = self._calculate_position_size(patterns, final_confidence)
        
        # Calculate target price and stop loss
        target_price, stop_loss = self._calculate_price_targets(
            current_price, patterns, strength
        )
        
        # Generate reasoning
        reasoning = self._generate_reasoning(patterns, ticker)
        
        # Identify risk factors
        risk_factors = self._identify_risk_factors(ticker, patterns, info)
        
        # Calculate metadata
        total_trades = sum(len(p.trades) for p in patterns)
        total_amount = sum(p.total_amount for p in patterns)
        
        # Determine time horizon
        avg_time_span = sum(p.time_span_days for p in patterns) / len(patterns)
        time_horizon = max(30, min(120, int(avg_time_span * 1.5)))  # 1.5x pattern timespan
        
        signal = TradingSignal(
            ticker=ticker,
            action=SignalAction.BUY,  # Currently only generating buy signals
            strength=strength,
            confidence=final_confidence,
            current_price=current_price,
            target_price=target_price,
            stop_loss=stop_loss,
            time_horizon_days=time_horizon,
            position_size_pct=position_size,
            reasoning=reasoning,
            supporting_patterns=[p.pattern_type for p in patterns],
            risk_factors=risk_factors,
            expires_at=datetime.now() + timedelta(days=7),  # Signals expire in 1 week
            insider_trades_count=total_trades,
            total_insider_amount=total_amount
        )
        
        return signal
    
    def _classify_signal_strength(self, confidence: float) -> SignalStrength:
        """Classify signal strength based on confidence."""
        
        if confidence >= self.strength_thresholds[SignalStrength.VERY_STRONG]:
            return SignalStrength.VERY_STRONG
        elif confidence >= self.strength_thresholds[SignalStrength.STRONG]:
            return SignalStrength.STRONG
        elif confidence >= self.strength_thresholds[SignalStrength.MODERATE]:
            return SignalStrength.MODERATE
        else:
            return SignalStrength.WEAK
    
    def _calculate_position_size(self, patterns: List[TradingPattern], 
                               confidence: float) -> float:
        """Calculate recommended position size as % of portfolio."""
        
        # Base position size on confidence
        base_size = confidence * self.max_position_size
        
        # Adjust based on pattern types
        pattern_multipliers = {
            'bipartisan_interest': 1.3,    # Higher confidence
            'consensus_buying': 1.2,       # Multiple buyers
            'unusual_volume': 1.1,         # Unusual activity
            'insider_momentum': 1.0,       # Normal weight
        }
        
        pattern_boost = 1.0
        for pattern in patterns:
            multiplier = pattern_multipliers.get(pattern.pattern_type, 1.0)
            pattern_boost = max(pattern_boost, multiplier)
        
        adjusted_size = base_size * pattern_boost
        
        # Clamp to reasonable bounds
        return max(self.min_position_size, min(self.max_position_size, adjusted_size))
    
    def _calculate_price_targets(self, current_price: float, 
                               patterns: List[TradingPattern],
                               strength: SignalStrength) -> Tuple[Optional[float], Optional[float]]:
        """Calculate target price and stop loss."""
        
        # Target returns based on signal strength
        target_returns = {
            SignalStrength.WEAK: 0.10,        # 10%
            SignalStrength.MODERATE: 0.15,    # 15%
            SignalStrength.STRONG: 0.25,      # 25%
            SignalStrength.VERY_STRONG: 0.35, # 35%
        }
        
        # Stop loss based on signal strength (tighter stops for weaker signals)
        stop_losses = {
            SignalStrength.WEAK: -0.08,       # -8%
            SignalStrength.MODERATE: -0.10,   # -10%
            SignalStrength.STRONG: -0.12,     # -12%
            SignalStrength.VERY_STRONG: -0.15, # -15%
        }
        
        target_return = target_returns.get(strength, 0.15)
        stop_loss_return = stop_losses.get(strength, -0.10)
        
        target_price = current_price * (1 + target_return)
        stop_loss = current_price * (1 + stop_loss_return)
        
        return target_price, stop_loss
    
    def _generate_reasoning(self, patterns: List[TradingPattern], ticker: str) -> str:
        """Generate human-readable reasoning for the signal."""
        
        pattern_descriptions = {
            'unusual_volume': 'Unusual insider trading volume',
            'consensus_buying': 'Multiple insiders buying',
            'insider_momentum': 'Repeated insider buying',
            'bipartisan_interest': 'Bipartisan political interest',
        }
        
        reasons = []
        
        for pattern in patterns:
            desc = pattern_descriptions.get(pattern.pattern_type, pattern.pattern_type)
            
            if pattern.pattern_type == 'consensus_buying':
                filer_count = len(pattern.filers)
                reasons.append(f"{desc} ({filer_count} different insiders)")
            elif pattern.pattern_type == 'bipartisan_interest':
                reasons.append(f"{desc} (both parties trading)")
            elif pattern.pattern_type == 'unusual_volume':
                volume_ratio = pattern.metadata.get('amount_ratio', 1.0)
                reasons.append(f"{desc} ({volume_ratio:.1f}x normal activity)")
            else:
                reasons.append(desc)
        
        # Add aggregate information
        total_amount = sum(p.total_amount for p in patterns)
        total_trades = sum(len(p.trades) for p in patterns)
        
        base_reason = f"{ticker}: {', '.join(reasons[:3])}"
        if len(reasons) > 3:
            base_reason += f" and {len(reasons) - 3} more patterns"
        
        base_reason += f". {total_trades} insider trades totaling ${total_amount:,.0f}"
        
        return base_reason
    
    def _identify_risk_factors(self, ticker: str, patterns: List[TradingPattern], 
                             stock_info: dict) -> List[str]:
        """Identify potential risk factors for the signal."""
        
        risks = []
        
        # Market cap risk
        market_cap = stock_info.get('marketCap', 0)
        if market_cap < 1e9:  # < $1B
            risks.append("Small cap stock - higher volatility risk")
        elif market_cap > 500e9:  # > $500B
            risks.append("Large cap stock - limited upside potential")
        
        # Sector concentration risk
        sector = stock_info.get('sector', '')
        volatile_sectors = ['Technology', 'Biotechnology', 'Energy']
        if sector in volatile_sectors:
            risks.append(f"High volatility {sector.lower()} sector")
        
        # Insider selling risk - check if there's recent selling
        with get_session() as session:
            recent_sells = session.query(Trade).filter(
                Trade.ticker == ticker,
                Trade.transaction_type.in_([TransactionType.SELL]),
                Trade.reported_date >= date.today() - timedelta(days=30)
            ).count()
            
            if recent_sells > 0:
                risks.append(f"Recent insider selling activity ({recent_sells} sells)")
        
        # Pattern-specific risks
        pattern_types = [p.pattern_type for p in patterns]
        if 'unusual_volume' in pattern_types:
            risks.append("Based on unusual volume - may be temporary")
        
        if len([p for p in patterns if p.time_span_days > 90]) > 0:
            risks.append("Some patterns span long periods - momentum may be slowing")
        
        # Beta/volatility risk
        beta = stock_info.get('beta', 1.0)
        if beta and beta > 1.5:
            risks.append(f"High beta stock ({beta:.1f}) - market sensitive")
        
        return risks[:5]  # Limit to 5 most important risks
    
    def save_signals_to_db(self, signals: List[TradingSignal]):
        """Save signals to database for tracking."""
        
        with get_session() as session:
            # Get or create strategy for signal generation
            strategy = session.query(Strategy).filter(
                Strategy.name == "Pattern-Based Signals"
            ).first()
            
            if not strategy:
                strategy = Strategy(
                    name="Pattern-Based Signals",
                    description="Signals generated from detected insider trading patterns",
                    parameters={
                        "min_confidence": self.min_confidence,
                        "max_position_size": self.max_position_size
                    }
                )
                session.add(strategy)
                session.flush()
            
            # Save each signal
            for trading_signal in signals:
                
                # Check if signal already exists
                existing = session.query(Signal).filter(
                    Signal.ticker == trading_signal.ticker,
                    Signal.strategy_id == strategy.strategy_id,
                    Signal.generated_at >= datetime.now() - timedelta(days=1)
                ).first()
                
                if existing:
                    continue  # Skip duplicate signals
                
                # Convert strength to numeric score
                strength_scores = {
                    SignalStrength.WEAK: 0.25,
                    SignalStrength.MODERATE: 0.50,
                    SignalStrength.STRONG: 0.75,
                    SignalStrength.VERY_STRONG: 1.0
                }
                
                signal = Signal(
                    strategy_id=strategy.strategy_id,
                    ticker=trading_signal.ticker,
                    signal_type=TransactionType.BUY,  # Currently only buy signals
                    strength=strength_scores.get(trading_signal.strength, 0.5),
                    generated_at=trading_signal.generated_at,
                    expires_at=trading_signal.expires_at,
                    reasoning=trading_signal.reasoning
                )
                
                session.add(signal)
    
    def get_portfolio_recommendations(self, portfolio_value: float = 100000,
                                   risk_tolerance: str = 'moderate') -> Dict:
        """Get comprehensive portfolio recommendations."""
        
        # Generate current signals
        signals = self.generate_current_signals()
        
        # Save to database
        self.save_signals_to_db(signals)
        
        # Filter by risk tolerance
        filtered_signals = self._filter_by_risk_tolerance(signals, risk_tolerance)
        
        # Calculate portfolio allocation
        allocation = self._calculate_portfolio_allocation(
            filtered_signals, portfolio_value, risk_tolerance
        )
        
        # Generate summary stats
        summary = self._generate_portfolio_summary(filtered_signals, allocation)
        
        return {
            'signals': filtered_signals,
            'allocation': allocation,
            'summary': summary,
            'total_recommended_allocation': sum(allocation.values()),
            'cash_allocation': 1.0 - sum(allocation.values()),
            'generated_at': datetime.now()
        }
    
    def _filter_by_risk_tolerance(self, signals: List[TradingSignal], 
                                 risk_tolerance: str) -> List[TradingSignal]:
        """Filter signals based on risk tolerance."""
        
        risk_filters = {
            'conservative': {
                'min_confidence': 0.6,
                'max_position_size': 0.05,
                'allowed_strengths': [SignalStrength.STRONG, SignalStrength.VERY_STRONG]
            },
            'moderate': {
                'min_confidence': 0.4,
                'max_position_size': 0.08,
                'allowed_strengths': [SignalStrength.MODERATE, SignalStrength.STRONG, SignalStrength.VERY_STRONG]
            },
            'aggressive': {
                'min_confidence': 0.3,
                'max_position_size': 0.12,
                'allowed_strengths': list(SignalStrength)
            }
        }
        
        filter_criteria = risk_filters.get(risk_tolerance, risk_filters['moderate'])
        
        filtered = []
        for signal in signals:
            if (signal.confidence >= filter_criteria['min_confidence'] and
                signal.strength in filter_criteria['allowed_strengths']):
                
                # Adjust position size for risk tolerance
                signal.position_size_pct = min(
                    signal.position_size_pct,
                    filter_criteria['max_position_size']
                )
                filtered.append(signal)
        
        return filtered
    
    def _calculate_portfolio_allocation(self, signals: List[TradingSignal],
                                      portfolio_value: float,
                                      risk_tolerance: str) -> Dict[str, float]:
        """Calculate recommended portfolio allocation."""
        
        if not signals:
            return {}
        
        # Maximum total allocation to insider signals
        max_allocations = {
            'conservative': 0.30,  # 30% max
            'moderate': 0.50,      # 50% max
            'aggressive': 0.70     # 70% max
        }
        
        max_total_allocation = max_allocations.get(risk_tolerance, 0.50)
        
        # Calculate raw allocations
        raw_allocations = {}
        total_raw = 0
        
        for signal in signals:
            raw_allocations[signal.ticker] = signal.position_size_pct
            total_raw += signal.position_size_pct
        
        # Scale down if total exceeds maximum
        if total_raw > max_total_allocation:
            scale_factor = max_total_allocation / total_raw
            for ticker in raw_allocations:
                raw_allocations[ticker] *= scale_factor
        
        return raw_allocations
    
    def _generate_portfolio_summary(self, signals: List[TradingSignal],
                                   allocation: Dict[str, float]) -> Dict:
        """Generate portfolio summary statistics."""
        
        if not signals:
            return {}
        
        # Count by strength
        strength_counts = {}
        for signal in signals:
            strength_counts[signal.strength.value] = strength_counts.get(signal.strength.value, 0) + 1
        
        # Average confidence
        avg_confidence = sum(s.confidence for s in signals) / len(signals)
        
        # Total expected return (rough estimate)
        expected_returns = []
        for signal in signals:
            if signal.target_price and signal.current_price:
                expected_return = (signal.target_price - signal.current_price) / signal.current_price
                expected_returns.append(expected_return * allocation.get(signal.ticker, 0))
        
        portfolio_expected_return = sum(expected_returns) if expected_returns else 0
        
        # Risk assessment
        total_risk_factors = sum(len(s.risk_factors) for s in signals)
        avg_risk_factors = total_risk_factors / len(signals) if signals else 0
        
        return {
            'signal_count': len(signals),
            'strength_distribution': strength_counts,
            'average_confidence': avg_confidence,
            'estimated_portfolio_return': portfolio_expected_return,
            'average_risk_factors': avg_risk_factors,
            'total_allocation': sum(allocation.values()),
            'diversification_score': len(signals) / max(1, len(set(s.ticker[:2] for s in signals)))  # Rough sector diversification
        }


if __name__ == "__main__":
    # CLI for generating signals
    import argparse
    import json
    
    parser = argparse.ArgumentParser(description="Generate trading signals")
    parser.add_argument("--portfolio-value", type=float, default=100000,
                       help="Portfolio value for position sizing")
    parser.add_argument("--risk-tolerance", choices=['conservative', 'moderate', 'aggressive'],
                       default='moderate', help="Risk tolerance level")
    parser.add_argument("--days", type=int, default=90,
                       help="Days to look back for patterns")
    
    args = parser.parse_args()
    
    generator = SignalGenerator()
    
    print("Generating portfolio recommendations...")
    recommendations = generator.get_portfolio_recommendations(
        portfolio_value=args.portfolio_value,
        risk_tolerance=args.risk_tolerance
    )
    
    print(f"\n=== PORTFOLIO RECOMMENDATIONS ({args.risk_tolerance.upper()}) ===")
    print(f"Portfolio Value: ${args.portfolio_value:,.0f}")
    
    summary = recommendations['summary']
    print(f"\nSummary:")
    print(f"  Signals Found: {summary.get('signal_count', 0)}")
    print(f"  Average Confidence: {summary.get('average_confidence', 0):.1%}")
    print(f"  Recommended Allocation: {summary.get('total_allocation', 0):.1%}")
    print(f"  Cash Allocation: {recommendations.get('cash_allocation', 0):.1%}")
    
    print(f"\n{'TICKER':<8} {'ACTION':<6} {'STRENGTH':<12} {'CONFIDENCE':<10} {'ALLOCATION':<10} {'TARGET':<10}")
    print("-" * 70)
    
    signals = recommendations.get('signals', [])
    allocation = recommendations.get('allocation', {})
    
    for signal in signals[:15]:  # Show top 15
        allocation_pct = allocation.get(signal.ticker, 0) * 100
        target_return = 0
        if signal.target_price and signal.current_price:
            target_return = (signal.target_price - signal.current_price) / signal.current_price
        
        print(f"{signal.ticker:<8} {signal.action.value:<6} {signal.strength.value:<12} "
              f"{signal.confidence:<10.1%} {allocation_pct:<10.1f}% {target_return:<10.1%}")
    
    if len(signals) > 15:
        print(f"\n... and {len(signals) - 15} more signals")
    
    # Show top 3 detailed recommendations
    print(f"\n=== TOP RECOMMENDATIONS ===")
    for i, signal in enumerate(signals[:3], 1):
        print(f"\n{i}. {signal.ticker} - {signal.strength.value.title()} {signal.action.value.title()}")
        print(f"   Confidence: {signal.confidence:.1%}")
        print(f"   Current Price: ${signal.current_price:.2f}")
        print(f"   Target Price: ${signal.target_price:.2f}")
        print(f"   Position Size: {allocation.get(signal.ticker, 0):.1%} of portfolio")
        print(f"   Reasoning: {signal.reasoning[:100]}...")
        if signal.risk_factors:
            print(f"   Risks: {', '.join(signal.risk_factors[:2])}")
