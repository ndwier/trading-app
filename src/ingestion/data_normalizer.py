"""Data normalizer for cleaning and standardizing trade data."""

import re
import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Set, Tuple, Any
from decimal import Decimal
import yfinance as yf
import pandas as pd

from src.database import get_session, Trade, Filer, PriceData
from config.config import config


logger = logging.getLogger(__name__)


class DataNormalizer:
    """Normalizes and validates trade data."""
    
    def __init__(self):
        self.logger = logger
        
        # Cache for ticker validation
        self._valid_tickers = set()
        self._invalid_tickers = set()
        
        # Common ticker mappings and corrections
        self.ticker_corrections = {
            # Common misspellings or alternative formats
            "APPLE": "AAPL",
            "MICROSOFT": "MSFT", 
            "AMAZON": "AMZN",
            "TESLA MOTORS": "TSLA",
            "FACEBOOK": "META",
            # Add more as needed
        }
        
        # Transaction type normalization
        self.transaction_type_mapping = {
            # Buy variations
            "purchase": "buy",
            "acquired": "buy", 
            "grant": "buy",
            "award": "buy",
            "p": "buy",
            "a": "buy",
            
            # Sell variations  
            "sale": "sell",
            "sold": "sell",
            "disposed": "sell",
            "disposition": "sell", 
            "s": "sell",
            "d": "sell",
            
            # Option variations
            "option_purchase": "option_buy",
            "option_sale": "option_sell",
            "call_option": "option_buy",
            "put_option": "option_sell",
        }
    
    def normalize_trade(self, trade: Trade) -> bool:
        """Normalize a single trade record.
        
        Args:
            trade: Trade object to normalize
            
        Returns:
            True if successfully normalized, False otherwise
        """
        try:
            # Normalize ticker
            if trade.ticker:
                trade.ticker = self._normalize_ticker(trade.ticker)
                
                # Validate ticker exists
                if not self._validate_ticker(trade.ticker):
                    self.logger.warning(f"Invalid ticker: {trade.ticker}")
                    return False
            
            # Normalize transaction type
            if trade.transaction_type:
                normalized_type = self._normalize_transaction_type(str(trade.transaction_type.value))
                if normalized_type != trade.transaction_type.value:
                    # Would need to update enum value - for now just log
                    self.logger.debug(f"Transaction type normalized: {trade.transaction_type.value} -> {normalized_type}")
            
            # Normalize amounts and quantities
            trade.amount_usd = self._normalize_amount(trade.amount_usd)
            trade.quantity = self._normalize_quantity(trade.quantity)
            trade.price = self._normalize_price(trade.price)
            
            # Calculate missing values
            if not trade.amount_usd and trade.quantity and trade.price:
                trade.amount_usd = float(trade.quantity) * float(trade.price)
            elif not trade.quantity and trade.amount_usd and trade.price:
                trade.quantity = float(trade.amount_usd) / float(trade.price)
            elif not trade.price and trade.amount_usd and trade.quantity:
                trade.price = float(trade.amount_usd) / float(trade.quantity)
            
            # Normalize filer name
            if hasattr(trade, 'filer') and trade.filer:
                trade.filer.name = self._normalize_filer_name(trade.filer.name)
            
            # Validate dates
            if not self._validate_dates(trade.trade_date, trade.reported_date):
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to normalize trade {trade.trade_id}: {e}")
            return False
    
    def normalize_batch(self, limit: Optional[int] = None) -> Dict[str, int]:
        """Normalize all trades in the database.
        
        Args:
            limit: Optional limit on number of trades to process
            
        Returns:
            Statistics about normalization process
        """
        stats = {
            "processed": 0,
            "normalized": 0,
            "errors": 0,
            "invalid_tickers": 0,
            "invalid_dates": 0
        }
        
        with get_session() as session:
            # Get trades that need normalization
            query = session.query(Trade).filter(
                Trade.ticker.isnot(None)
            )
            
            if limit:
                query = query.limit(limit)
            
            trades = query.all()
            
            self.logger.info(f"Normalizing {len(trades)} trades")
            
            for trade in trades:
                stats["processed"] += 1
                
                try:
                    if self.normalize_trade(trade):
                        stats["normalized"] += 1
                    else:
                        stats["errors"] += 1
                        
                        # Categorize error type
                        if trade.ticker and not self._validate_ticker(trade.ticker):
                            stats["invalid_tickers"] += 1
                        if not self._validate_dates(trade.trade_date, trade.reported_date):
                            stats["invalid_dates"] += 1
                            
                except Exception as e:
                    self.logger.error(f"Error normalizing trade {trade.trade_id}: {e}")
                    stats["errors"] += 1
                
                if stats["processed"] % 1000 == 0:
                    self.logger.info(f"Processed {stats['processed']} trades...")
            
            session.commit()
        
        self.logger.info(f"Normalization complete: {stats}")
        return stats
    
    def _normalize_ticker(self, ticker: str) -> str:
        """Normalize ticker symbol."""
        if not ticker:
            return ticker
        
        # Clean up ticker
        ticker = ticker.upper().strip()
        
        # Remove common suffixes and prefixes
        ticker = re.sub(r'[^\w]', '', ticker)  # Remove non-alphanumeric
        
        # Apply corrections
        if ticker in self.ticker_corrections:
            return self.ticker_corrections[ticker]
        
        # Length validation
        if len(ticker) > 5 or len(ticker) < 1:
            self.logger.warning(f"Unusual ticker length: {ticker}")
        
        return ticker
    
    def _normalize_transaction_type(self, transaction_type: str) -> str:
        """Normalize transaction type."""
        if not transaction_type:
            return transaction_type
        
        # Clean and lowercase
        normalized = transaction_type.lower().strip()
        
        # Apply mappings
        if normalized in self.transaction_type_mapping:
            return self.transaction_type_mapping[normalized]
        
        return normalized
    
    def _normalize_filer_name(self, name: str) -> str:
        """Normalize filer name."""
        if not name:
            return name
        
        # Remove extra whitespace
        name = ' '.join(name.split())
        
        # Title case for readability
        name = name.title()
        
        # Common corrections
        name = re.sub(r'\bJr\.?\b', 'Jr.', name)
        name = re.sub(r'\bSr\.?\b', 'Sr.', name)
        name = re.sub(r'\bIii?\b', 'III', name)
        name = re.sub(r'\bIi\b', 'II', name)
        
        return name
    
    def _normalize_amount(self, amount) -> Optional[float]:
        """Normalize monetary amount."""
        if amount is None:
            return None
        
        try:
            if isinstance(amount, str):
                # Remove currency symbols and commas
                amount_clean = re.sub(r'[$,\s]', '', amount)
                
                # Handle ranges (take midpoint)
                if '-' in amount_clean:
                    parts = amount_clean.split('-')
                    if len(parts) == 2:
                        low = float(parts[0])
                        high = float(parts[1])
                        return (low + high) / 2
                
                return float(amount_clean)
            
            return float(amount)
            
        except (ValueError, TypeError):
            self.logger.warning(f"Could not normalize amount: {amount}")
            return None
    
    def _normalize_quantity(self, quantity) -> Optional[float]:
        """Normalize share quantity."""
        if quantity is None:
            return None
        
        try:
            if isinstance(quantity, str):
                # Remove commas
                quantity = re.sub(r'[,\s]', '', quantity)
            
            return float(quantity)
            
        except (ValueError, TypeError):
            self.logger.warning(f"Could not normalize quantity: {quantity}")
            return None
    
    def _normalize_price(self, price) -> Optional[float]:
        """Normalize share price."""
        if price is None:
            return None
        
        try:
            if isinstance(price, str):
                # Remove currency symbols and commas
                price = re.sub(r'[$,\s]', '', price)
            
            return float(price)
            
        except (ValueError, TypeError):
            self.logger.warning(f"Could not normalize price: {price}")
            return None
    
    def _validate_ticker(self, ticker: str) -> bool:
        """Validate ticker symbol exists in market."""
        if not ticker:
            return False
        
        # Check cache first
        if ticker in self._valid_tickers:
            return True
        if ticker in self._invalid_tickers:
            return False
        
        try:
            # Use yfinance to validate ticker
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Check if we got valid info
            if info and 'symbol' in info:
                self._valid_tickers.add(ticker)
                return True
            else:
                self._invalid_tickers.add(ticker)
                return False
                
        except Exception as e:
            self.logger.debug(f"Ticker validation failed for {ticker}: {e}")
            self._invalid_tickers.add(ticker)
            return False
    
    def _validate_dates(self, trade_date: Optional[date], 
                       reported_date: Optional[date]) -> bool:
        """Validate trade and reporting dates."""
        
        # Must have at least reported date
        if not reported_date:
            return False
        
        # Reported date should not be in the future
        if reported_date > date.today():
            return False
        
        # If both dates exist, trade should be before or same as reported
        if trade_date and reported_date and trade_date > reported_date:
            return False
        
        # Trade date should not be too far in the past (sanity check)
        if trade_date and trade_date < date(2000, 1, 1):
            return False
        
        return True
    
    def get_ticker_stats(self) -> Dict[str, int]:
        """Get statistics about ticker validation."""
        return {
            "valid_tickers": len(self._valid_tickers),
            "invalid_tickers": len(self._invalid_tickers),
            "total_checked": len(self._valid_tickers) + len(self._invalid_tickers)
        }


class PriceDataNormalizer:
    """Normalizes historical price data for backtesting."""
    
    def __init__(self):
        self.logger = logger
    
    def fetch_and_store_prices(self, tickers: List[str], 
                              start_date: date, end_date: date) -> Dict[str, Any]:
        """Fetch and store price data for tickers."""
        
        stats = {
            "tickers_processed": 0,
            "prices_stored": 0,
            "errors": 0
        }
        
        with get_session() as session:
            for ticker in tickers:
                try:
                    self.logger.info(f"Fetching price data for {ticker}")
                    
                    # Get price data from yfinance
                    stock = yf.Ticker(ticker)
                    hist = stock.history(start=start_date, end=end_date)
                    
                    if hist.empty:
                        self.logger.warning(f"No price data found for {ticker}")
                        stats["errors"] += 1
                        continue
                    
                    # Store price data
                    for date_idx, row in hist.iterrows():
                        price_date = date_idx.date()
                        
                        # Check if price already exists
                        existing = session.query(PriceData).filter(
                            PriceData.ticker == ticker,
                            PriceData.date == price_date
                        ).first()
                        
                        if existing:
                            continue
                        
                        # Create new price record
                        price_data = PriceData(
                            ticker=ticker,
                            date=price_date,
                            open_price=float(row['Open']) if not pd.isna(row['Open']) else None,
                            high_price=float(row['High']) if not pd.isna(row['High']) else None,
                            low_price=float(row['Low']) if not pd.isna(row['Low']) else None,
                            close_price=float(row['Close']),
                            volume=int(row['Volume']) if not pd.isna(row['Volume']) else None,
                            adj_close=float(row['Close'])  # yfinance already returns adjusted
                        )
                        
                        session.add(price_data)
                        stats["prices_stored"] += 1
                    
                    stats["tickers_processed"] += 1
                    
                except Exception as e:
                    self.logger.error(f"Failed to fetch price data for {ticker}: {e}")
                    stats["errors"] += 1
        
        self.logger.info(f"Price data fetch complete: {stats}")
        return stats


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run data normalization")
    parser.add_argument("--trades", action="store_true",
                       help="Normalize trade data")
    parser.add_argument("--prices", action="store_true", 
                       help="Fetch and normalize price data")
    parser.add_argument("--limit", type=int,
                       help="Limit number of records to process")
    
    args = parser.parse_args()
    
    if args.trades:
        normalizer = DataNormalizer()
        results = normalizer.normalize_batch(limit=args.limit)
        print(f"Trade normalization results: {results}")
    
    if args.prices:
        # Get unique tickers from database
        with get_session() as session:
            tickers = session.query(Trade.ticker).distinct().all()
            ticker_list = [t[0] for t in tickers if t[0]]
        
        price_normalizer = PriceDataNormalizer()
        results = price_normalizer.fetch_and_store_prices(
            ticker_list[:args.limit] if args.limit else ticker_list,
            start_date=date(2020, 1, 1),
            end_date=date.today()
        )
        print(f"Price data results: {results}")
