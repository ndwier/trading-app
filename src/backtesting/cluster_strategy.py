"""Cluster strategy that looks for multiple insiders buying the same stock."""

from collections import defaultdict
from datetime import date, timedelta
from typing import Dict, List

from .base_strategy import BaseStrategy, StrategyResult, StrategySignal, SignalType
from src.database import Trade


class ClusterStrategy(BaseStrategy):
    """Strategy that identifies clusters of insider buying."""
    
    def __init__(self, cluster_window_days: int = 30, 
                 min_cluster_size: int = 3, **parameters):
        """Initialize cluster strategy.
        
        Args:
            cluster_window_days: Days within which trades are considered clustered
            min_cluster_size: Minimum number of trades to form a cluster
            **parameters: Other strategy parameters
        """
        super().__init__("Cluster Strategy", 
                        cluster_window_days=cluster_window_days,
                        min_cluster_size=min_cluster_size, 
                        **parameters)
        self.cluster_window_days = cluster_window_days
        self.min_cluster_size = min_cluster_size
    
    def generate_signals(self, trades: List[Trade], 
                        start_date: date, end_date: date) -> StrategyResult:
        """Generate cluster-based trading signals."""
        
        # Filter relevant trades
        filtered_trades = self.filter_trades(trades, start_date, end_date)
        
        # Only look at buy transactions
        buy_trades = [t for t in filtered_trades 
                     if t.transaction_type.value in ['buy', 'option_buy']]
        
        # Find clusters
        clusters = self._find_clusters(buy_trades)
        
        signals = []
        
        for ticker, cluster_trades in clusters.items():
            if len(cluster_trades) >= self.min_cluster_size:
                # Create signal based on cluster
                signal = self._create_cluster_signal(ticker, cluster_trades)
                if signal and signal.entry_date >= start_date and signal.entry_date <= end_date:
                    signals.append(signal)
        
        return StrategyResult(
            strategy_name=self.name,
            signals=signals,
            start_date=start_date,
            end_date=end_date,
            parameters={
                "cluster_window_days": self.cluster_window_days,
                "min_cluster_size": self.min_cluster_size,
                **self.parameters
            }
        )
    
    def _find_clusters(self, trades: List[Trade]) -> Dict[str, List[Trade]]:
        """Find clusters of trades by ticker and time proximity."""
        
        # Group trades by ticker
        ticker_trades = self.group_trades_by_ticker(trades)
        
        clusters = {}
        
        for ticker, trade_list in ticker_trades.items():
            # Sort trades by date
            sorted_trades = sorted(trade_list, 
                                 key=lambda t: t.reported_date or t.trade_date or date.min)
            
            # Find clusters within the time window
            current_cluster = []
            cluster_start_date = None
            
            for trade in sorted_trades:
                trade_date = trade.reported_date or trade.trade_date
                if not trade_date:
                    continue
                
                if not cluster_start_date:
                    # Start new cluster
                    current_cluster = [trade]
                    cluster_start_date = trade_date
                elif (trade_date - cluster_start_date).days <= self.cluster_window_days:
                    # Add to current cluster
                    current_cluster.append(trade)
                else:
                    # Finalize current cluster if it meets minimum size
                    if len(current_cluster) >= self.min_cluster_size:
                        clusters[f"{ticker}_{cluster_start_date}"] = current_cluster.copy()
                    
                    # Start new cluster
                    current_cluster = [trade]
                    cluster_start_date = trade_date
            
            # Don't forget the last cluster
            if len(current_cluster) >= self.min_cluster_size:
                clusters[f"{ticker}_{cluster_start_date}"] = current_cluster
        
        # Clean up cluster keys (remove date suffix)
        cleaned_clusters = {}
        for key, cluster_trades in clusters.items():
            ticker = key.split('_')[0]
            if ticker not in cleaned_clusters:
                cleaned_clusters[ticker] = []
            cleaned_clusters[ticker].extend(cluster_trades)
        
        return cleaned_clusters
    
    def _create_cluster_signal(self, ticker: str, 
                             cluster_trades: List[Trade]) -> StrategySignal:
        """Create a trading signal from a cluster of trades."""
        
        if not cluster_trades:
            return None
        
        # Sort trades by date to find the latest one
        sorted_trades = sorted(cluster_trades, 
                             key=lambda t: t.reported_date or t.trade_date or date.min)
        
        # Use the date of the latest trade as trigger
        latest_trade = sorted_trades[-1]
        trigger_date = latest_trade.reported_date or latest_trade.trade_date
        
        if not trigger_date:
            return None
        
        # Entry date is trigger date + 1 day (to be realistic)
        entry_date = trigger_date + timedelta(days=1)
        exit_date = self.calculate_exit_date(entry_date)
        
        # Calculate position size based on total cluster amount
        total_amount = sum(t.amount_usd for t in cluster_trades if t.amount_usd)
        avg_amount = total_amount / len(cluster_trades) if cluster_trades else 0
        
        # Create a representative trade for position sizing
        representative_trade = Trade()
        representative_trade.amount_usd = avg_amount
        position_size = self.calculate_position_size(representative_trade)
        
        # Calculate signal strength
        strength = self.calculate_signal_strength(cluster_trades)
        
        # Boost strength based on cluster characteristics
        unique_filers = len(set(t.filer_id for t in cluster_trades))
        filer_diversity_boost = min(unique_filers / 5.0, 0.5)  # Up to 50% boost
        strength = min(1.0, strength + filer_diversity_boost)
        
        # Create reasoning text
        filer_names = list(set(t.filer.name for t in cluster_trades if t.filer))
        reasoning = (f"Cluster signal: {len(cluster_trades)} buys by "
                    f"{len(filer_names)} filers including {', '.join(filer_names[:3])}"
                    f"{' and others' if len(filer_names) > 3 else ''}")
        
        return StrategySignal(
            ticker=ticker,
            signal_type=SignalType.BUY,
            strength=strength,
            entry_date=entry_date,
            exit_date=exit_date,
            position_size=position_size,
            trigger_trades=[t.trade_id for t in cluster_trades],
            reasoning=reasoning
        )


class BipartisanStrategy(BaseStrategy):
    """Strategy that looks for bipartisan political buying (both parties)."""
    
    def __init__(self, **parameters):
        """Initialize bipartisan strategy."""
        super().__init__("Bipartisan Strategy", **parameters)
    
    def generate_signals(self, trades: List[Trade], 
                        start_date: date, end_date: date) -> StrategyResult:
        """Generate signals when both parties are buying."""
        
        # Filter to political trades only
        filtered_trades = self.filter_trades(trades, start_date, end_date)
        political_trades = [t for t in filtered_trades 
                          if t.filer and hasattr(t.filer, 'party') and t.filer.party]
        
        # Only buy transactions
        buy_trades = [t for t in political_trades 
                     if t.transaction_type.value in ['buy', 'option_buy']]
        
        # Group by ticker
        ticker_trades = self.group_trades_by_ticker(buy_trades)
        
        signals = []
        
        for ticker, trade_list in ticker_trades.items():
            # Check if both parties are represented
            parties = set(t.filer.party for t in trade_list if t.filer.party)
            
            if len(parties) >= 2 and 'Republican' in parties and 'Democrat' in parties:
                # We have bipartisan interest!
                
                # Find the most recent trade date
                latest_date = max(t.reported_date or t.trade_date or date.min 
                                for t in trade_list)
                
                if latest_date == date.min:
                    continue
                
                entry_date = latest_date + timedelta(days=1)
                if entry_date < start_date or entry_date > end_date:
                    continue
                
                exit_date = self.calculate_exit_date(entry_date)
                
                # Calculate position size based on total bipartisan amount
                total_amount = sum(t.amount_usd for t in trade_list if t.amount_usd)
                avg_amount = total_amount / len(trade_list) if trade_list else 0
                
                representative_trade = Trade()
                representative_trade.amount_usd = avg_amount
                position_size = self.calculate_position_size(representative_trade)
                
                # High strength for bipartisan signals
                base_strength = self.calculate_signal_strength(trade_list)
                bipartisan_boost = 0.3  # 30% boost for bipartisan agreement
                strength = min(1.0, base_strength + bipartisan_boost)
                
                # Create reasoning
                party_counts = {}
                for trade in trade_list:
                    if trade.filer and trade.filer.party:
                        party = trade.filer.party
                        party_counts[party] = party_counts.get(party, 0) + 1
                
                reasoning = (f"Bipartisan signal: {len(trade_list)} trades "
                           f"({', '.join(f'{count} {party}' for party, count in party_counts.items())})")
                
                signal = StrategySignal(
                    ticker=ticker,
                    signal_type=SignalType.BUY,
                    strength=strength,
                    entry_date=entry_date,
                    exit_date=exit_date,
                    position_size=position_size,
                    trigger_trades=[t.trade_id for t in trade_list],
                    reasoning=reasoning
                )
                
                signals.append(signal)
        
        return StrategyResult(
            strategy_name=self.name,
            signals=signals,
            start_date=start_date,
            end_date=end_date,
            parameters=self.parameters.copy()
        )
