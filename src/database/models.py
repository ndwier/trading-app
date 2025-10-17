"""Database models for the trading app."""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, Integer, String, DateTime, Date, Numeric, Text, Boolean, 
    ForeignKey, Index, JSON, Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session
from sqlalchemy.sql import func
from enum import Enum
import json

Base = declarative_base()


class FilerType(Enum):
    """Types of filers/traders we track."""
    POLITICIAN = "politician"
    CORPORATE_INSIDER = "corporate_insider"
    BILLIONAIRE = "billionaire"
    INVESTOR = "investor"
    HEDGE_FUND = "hedge_fund"


class TransactionType(Enum):
    """Types of transactions."""
    BUY = "buy"
    SELL = "sell"
    OPTION_BUY = "option_buy"
    OPTION_SELL = "option_sell"
    GIFT = "gift"
    EXCHANGE = "exchange"


class DataSource(Enum):
    """Sources of trading data."""
    SEC_EDGAR = "sec_edgar"
    QUIVER = "quiver"
    FINNHUB = "finnhub"
    OPENINSIDER = "openinsider"
    MANUAL = "manual"
    SCRAPED = "scraped"


class Filer(Base):
    """Individual who files trading disclosures."""
    
    __tablename__ = "filers"
    
    filer_id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    filer_type = Column(SQLEnum(FilerType), nullable=False)
    
    # Political information
    party = Column(String(50))  # Republican, Democrat, Independent
    state = Column(String(2))   # State abbreviation
    chamber = Column(String(20))  # House, Senate
    position = Column(String(255))  # Chairman of Energy Committee, etc.
    
    # Corporate information
    company = Column(String(255))  # For corporate insiders
    title = Column(String(255))    # CEO, CFO, Director, etc.
    
    # Contact and profile information
    profile_url = Column(Text)
    image_url = Column(Text)
    
    # Metadata
    first_seen = Column(DateTime, default=func.now())
    last_seen = Column(DateTime, default=func.now())
    is_active = Column(Boolean, default=True)
    
    # Performance tracking
    total_trades = Column(Integer, default=0)
    total_volume = Column(Numeric(15, 2), default=0)
    win_rate = Column(Numeric(5, 4))  # Percentage of profitable trades
    avg_return = Column(Numeric(8, 6))  # Average return per trade
    
    # JSON field for additional metadata
    metadata_json = Column(JSON)
    
    # Relationships
    trades = relationship("Trade", back_populates="filer", lazy="dynamic")
    
    def __repr__(self):
        return f"<Filer {self.name} ({self.filer_type.value})>"
    
    def update_performance_metrics(self, session: Session):
        """Update calculated performance metrics for this filer."""
        trades = session.query(Trade).filter(
            Trade.filer_id == self.filer_id,
            Trade.return_pct.isnot(None)
        ).all()
        
        if trades:
            returns = [float(t.return_pct) for t in trades if t.return_pct]
            self.total_trades = len(trades)
            self.total_volume = sum(float(t.amount_usd or 0) for t in trades)
            self.win_rate = len([r for r in returns if r > 0]) / len(returns)
            self.avg_return = sum(returns) / len(returns)


class Trade(Base):
    """Individual trading transaction."""
    
    __tablename__ = "trades"
    
    trade_id = Column(Integer, primary_key=True)
    filer_id = Column(Integer, ForeignKey("filers.filer_id"), nullable=False)
    
    # Trade identification
    source = Column(SQLEnum(DataSource), nullable=False)
    source_id = Column(String(100))  # ID from source system
    filing_url = Column(Text)
    
    # Dates
    reported_date = Column(Date, nullable=False)  # When disclosed
    trade_date = Column(Date)  # When trade occurred (if known)
    
    # Security information
    ticker = Column(String(10), nullable=False)
    company_name = Column(String(255))
    cusip = Column(String(9))  # CUSIP identifier
    
    # Transaction details
    transaction_type = Column(SQLEnum(TransactionType), nullable=False)
    quantity = Column(Numeric(15, 4))
    price = Column(Numeric(10, 4))
    amount_usd = Column(Numeric(15, 2))
    
    # Additional details
    insider_relationship = Column(String(100))  # Self, Spouse, Trust, etc.
    ownership_type = Column(String(50))  # Direct, Indirect
    
    # Performance tracking
    entry_price = Column(Numeric(10, 4))  # Price when we would have entered
    exit_price = Column(Numeric(10, 4))   # Price when we would have exited
    return_pct = Column(Numeric(8, 6))    # Calculated return percentage
    hold_days = Column(Integer)           # Days between entry and exit
    
    # Metadata
    raw_data = Column(JSON)  # Original data from source
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # Relationships
    filer = relationship("Filer", back_populates="trades")
    
    # Indexes for performance
    __table_args__ = (
        Index("idx_trades_ticker", "ticker"),
        Index("idx_trades_reported_date", "reported_date"),
        Index("idx_trades_filer_ticker", "filer_id", "ticker"),
        Index("idx_trades_source", "source"),
        UniqueConstraint("source", "source_id", name="uq_trade_source_id"),
    )
    
    def __repr__(self):
        return (f"<Trade {self.ticker} {self.transaction_type.value} "
                f"${self.amount_usd} on {self.trade_date}>")
    
    def calculate_return(self, exit_price: Decimal, exit_date: date) -> Optional[Decimal]:
        """Calculate return percentage for this trade."""
        if not self.entry_price or not exit_price:
            return None
        
        if self.transaction_type in [TransactionType.BUY, TransactionType.OPTION_BUY]:
            return_pct = (exit_price - self.entry_price) / self.entry_price
        elif self.transaction_type in [TransactionType.SELL, TransactionType.OPTION_SELL]:
            return_pct = (self.entry_price - exit_price) / self.entry_price
        else:
            return None
        
        self.exit_price = exit_price
        self.return_pct = return_pct
        if self.trade_date:
            self.hold_days = (exit_date - self.trade_date).days
        
        return return_pct


class Strategy(Base):
    """Trading strategy definitions."""
    
    __tablename__ = "strategies"
    
    strategy_id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    
    # Strategy parameters (stored as JSON)
    parameters = Column(JSON, nullable=False)
    
    # Strategy metadata
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    
    # Relationships
    backtests = relationship("Backtest", back_populates="strategy")
    
    def __repr__(self):
        return f"<Strategy {self.name}>"


class Backtest(Base):
    """Backtest results for strategies."""
    
    __tablename__ = "backtests"
    
    backtest_id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey("strategies.strategy_id"), nullable=False)
    
    # Backtest parameters
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    initial_capital = Column(Numeric(15, 2), nullable=False)
    
    # Performance metrics
    total_return = Column(Numeric(10, 6))
    annual_return = Column(Numeric(8, 6))
    sharpe_ratio = Column(Numeric(6, 4))
    sortino_ratio = Column(Numeric(6, 4))
    max_drawdown = Column(Numeric(8, 6))
    win_rate = Column(Numeric(5, 4))
    total_trades = Column(Integer)
    
    # Risk metrics
    volatility = Column(Numeric(8, 6))
    beta = Column(Numeric(6, 4))
    alpha = Column(Numeric(8, 6))
    
    # Detailed results (stored as JSON)
    detailed_results = Column(JSON)
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    strategy = relationship("Strategy", back_populates="backtests")
    
    def __repr__(self):
        return (f"<Backtest {self.strategy.name} "
                f"{self.start_date} to {self.end_date}>")


class Signal(Base):
    """Trading signals generated by strategies."""
    
    __tablename__ = "signals"
    
    signal_id = Column(Integer, primary_key=True)
    strategy_id = Column(Integer, ForeignKey("strategies.strategy_id"), nullable=False)
    
    # Signal details
    ticker = Column(String(10), nullable=False)
    signal_type = Column(SQLEnum(TransactionType), nullable=False)
    strength = Column(Numeric(4, 3), nullable=False)  # 0.0 to 1.0
    
    # Signal metadata
    generated_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    # Supporting data
    trigger_trades = Column(JSON)  # Trade IDs that triggered this signal
    reasoning = Column(Text)
    
    # Relationships
    strategy = relationship("Strategy")
    
    # Indexes
    __table_args__ = (
        Index("idx_signals_ticker", "ticker"),
        Index("idx_signals_generated", "generated_at"),
        Index("idx_signals_active", "is_active"),
    )
    
    def __repr__(self):
        return (f"<Signal {self.ticker} {self.signal_type.value} "
                f"strength={self.strength}>")


class PriceData(Base):
    """Historical price data for backtesting."""
    
    __tablename__ = "price_data"
    
    price_id = Column(Integer, primary_key=True)
    ticker = Column(String(10), nullable=False)
    date = Column(Date, nullable=False)
    
    # OHLCV data
    open_price = Column(Numeric(10, 4))
    high_price = Column(Numeric(10, 4))
    low_price = Column(Numeric(10, 4))
    close_price = Column(Numeric(10, 4), nullable=False)
    volume = Column(Integer)
    
    # Adjusted prices
    adj_close = Column(Numeric(10, 4))
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    
    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_price_ticker_date"),
        Index("idx_price_ticker", "ticker"),
        Index("idx_price_date", "date"),
    )
    
    def __repr__(self):
        return f"<Price {self.ticker} {self.date} ${self.close_price}>"


class PortfolioTransaction(Base):
    """Portfolio transaction tracking for personal investing."""
    
    __tablename__ = "portfolio_transactions"
    
    transaction_id = Column(Integer, primary_key=True)
    
    # Transaction details
    ticker = Column(String(10), nullable=False)
    action = Column(String(10), nullable=False)  # buy, sell
    shares = Column(Numeric(15, 4), nullable=False)
    price = Column(Numeric(10, 4), nullable=False)
    transaction_date = Column(Date, nullable=False)
    
    # Costs
    commission = Column(Numeric(8, 2), default=0)
    total_cost = Column(Numeric(15, 2))  # shares * price + commission
    
    # Signal tracking
    signal_id = Column(Integer, ForeignKey("signals.signal_id"))
    signal_confidence = Column(Numeric(4, 3))
    
    # Metadata
    notes = Column(String(500))
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    signal = relationship("Signal", foreign_keys=[signal_id])
    
    def __repr__(self):
        return f"<PortfolioTransaction {self.action} {self.shares} {self.ticker} @ ${self.price}>"


class SignalPerformance(Base):
    """Track performance of generated signals."""
    
    __tablename__ = "signal_performance"
    
    performance_id = Column(Integer, primary_key=True)
    signal_id = Column(Integer, ForeignKey("signals.signal_id"), nullable=False)
    
    # Performance tracking
    evaluation_date = Column(Date, nullable=False)
    days_since_signal = Column(Integer, nullable=False)
    
    # Price performance
    signal_price = Column(Numeric(10, 4))  # Price when signal was generated
    current_price = Column(Numeric(10, 4))  # Price at evaluation
    return_pct = Column(Numeric(8, 6))     # Performance since signal
    
    # Signal accuracy
    target_hit = Column(Boolean)           # Did price reach target?
    stop_loss_hit = Column(Boolean)        # Did price hit stop loss?
    
    # Metadata
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    signal = relationship("Signal")
    
    def __repr__(self):
        return f"<SignalPerformance {self.signal.ticker} {self.return_pct:.2%}>"


# Utility functions for database operations
def create_all_tables(engine):
    """Create all tables in the database."""
    Base.metadata.create_all(engine)


def get_or_create_filer(session: Session, name: str, filer_type: FilerType, **kwargs) -> Filer:
    """Get existing filer or create a new one."""
    filer = session.query(Filer).filter(
        Filer.name == name,
        Filer.filer_type == filer_type
    ).first()
    
    if not filer:
        filer = Filer(
            name=name,
            filer_type=filer_type,
            **kwargs
        )
        session.add(filer)
        session.flush()  # Get the ID without committing
    else:
        # Update last seen
        filer.last_seen = func.now()
        for key, value in kwargs.items():
            if value is not None:
                setattr(filer, key, value)
    
    return filer
