"""OpenInsider scraper for clean insider transaction data."""

import logging
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Iterator
from decimal import Decimal

import requests
from bs4 import BeautifulSoup
import pandas as pd

from config.config import config
from src.database import get_session, Filer, Trade, FilerType, TransactionType, DataSource
from .base import ScrapingIngester, RawTradeData, IngestionError


class OpenInsiderScraper(ScrapingIngester):
    """Scraper for OpenInsider.com - cleaned insider transaction data."""
    
    def __init__(self):
        super().__init__(
            name="openinsider",
            base_url=config.api.OPENINSIDER_BASE_URL
        )
        self.rate_limit = config.api.OPENINSIDER_RATE_LIMIT
        
    def fetch_historical_trades(self, start_date: date, end_date: date) -> Iterator[RawTradeData]:
        """Fetch historical trades (OpenInsider doesn't support specific date ranges)."""
        # OpenInsider doesn't have date range filtering, so just fetch recent
        days = (end_date - start_date).days
        return self.fetch_recent_trades(min(days, 90))  # Cap at 90 days
    
    def fetch_filer_trades(self, filer_name: str) -> Iterator[RawTradeData]:
        """Fetch trades for specific filer (not easily supported by OpenInsider)."""
        # OpenInsider doesn't have per-filer endpoints easily accessible
        # Would need to search or filter post-fetch
        return iter([])
    
    def fetch_recent_trades(self, days: int = 30) -> Iterator[RawTradeData]:
        """Fetch recent insider trades from OpenInsider."""
        
        all_trades = []
        seen_ids = set()
        
        # OpenInsider pages to scrape (each has tinytable with data)
        pages = [
            "",  # Homepage - latest cluster buys
            "latest-insider-trading",
            "latest-cluster-buys", 
            "top-insider-purchases-by-value"
        ]
        
        for page in pages:
            try:
                url = f"{self.base_url}/{page}" if page else self.base_url
                response = self._make_request(url)
                trades = self._parse_page(response.text)
                
                # Deduplicate
                for trade in trades:
                    trade_id = f"{trade.ticker}_{trade.filer_name}_{trade.trade_date}_{trade.amount_usd}"
                    if trade_id not in seen_ids:
                        seen_ids.add(trade_id)
                        all_trades.append(trade)
                
                self.logger.info(f"Fetched {len(trades)} trades from {page or 'homepage'}")
                
            except Exception as e:
                self.logger.warning(f"Failed to fetch from {page}: {e}")
                continue
        
        # Filter by date
        cutoff_date = date.today() - timedelta(days=days)
        for trade in all_trades:
            if trade.trade_date and trade.trade_date >= cutoff_date:
                yield trade
    
    def _parse_page(self, html: str) -> List[RawTradeData]:
        """Parse OpenInsider page with tinytable."""
        
        trades = []
        soup = BeautifulSoup(html, 'html.parser')
        
        # Find all tinytable tables (homepage has multiple)
        tables = soup.find_all('table', {'class': 'tinytable'})
        if not tables:
            self.logger.warning("No tinytable found in OpenInsider response")
            return trades
        
        for table in tables:
            # Parse table rows (skip header row)
            rows = table.find_all('tr')[1:]
            
            for row in rows:
                try:
                    cols = row.find_all('td')
                    if len(cols) < 13:
                        continue
                    
                    # Column order based on actual structure:
                    # 0: X, 1: Filing Date, 2: Trade Date, 3: Ticker, 4: Company Name,
                    # 5: Industry, 6: Ins (insider count), 7: Trade Type, 8: Price,
                    # 9: Qty, 10: Owned, 11: ΔOwn, 12: Value, 13-16: performance
                    
                    filing_date_str = cols[1].text.strip()
                    trade_date_str = cols[2].text.strip()
                    ticker = cols[3].text.strip()
                    company_name = cols[4].text.strip()
                    industry = cols[5].text.strip() if len(cols) > 5 else ""
                    trade_type_str = cols[7].text.strip() if len(cols) > 7 else "P"
                    price_str = cols[8].text.strip() if len(cols) > 8 else ""
                    qty_str = cols[9].text.strip() if len(cols) > 9 else ""
                    value_str = cols[12].text.strip() if len(cols) > 12 else ""
                    
                    # Parse dates (format: YYYY-MM-DD HH:MM:SS or YYYY-MM-DD)
                    filing_date = self._parse_date(filing_date_str.split()[0] if ' ' in filing_date_str else filing_date_str)
                    trade_date = self._parse_date(trade_date_str.split()[0] if ' ' in trade_date_str else trade_date_str)
                    
                    if not trade_date or not ticker:
                        continue
                    
                    # Parse transaction type (returns string like 'BUY', 'SELL', etc.)
                    transaction_type = self._parse_transaction_type(trade_type_str)
                    
                    # Parse amounts
                    price = self._parse_amount(price_str)
                    quantity = self._parse_amount(qty_str)
                    value = self._parse_amount(value_str)
                    
                    # Calculate value if not provided
                    if not value and price and quantity:
                        value = price * quantity
                    
                    # Get insider name from linked page (or use company for now)
                    insider_link = cols[3].find('a')
                    insider_name = insider_link.get('title', company_name) if insider_link else company_name
                    
                    # Create trade data
                    trade_data = RawTradeData(
                        source="openinsider",
                        source_id=f"oi_{ticker}_{trade_date}_{value}",
                        reported_date=filing_date or trade_date,
                        trade_date=trade_date,
                        ticker=ticker.upper(),
                        company_name=company_name,
                        filer_name=insider_name,
                        filer_type=FilerType.CORPORATE_INSIDER.value,
                        transaction_type=transaction_type,
                        quantity=quantity,
                        price=price,
                        amount_usd=value,
                        insider_relationship=industry,
                        raw_data={
                            "source": "openinsider",
                            "industry": industry,
                            "filing_url": f"{self.base_url}/{ticker}"
                        }
                    )
                    
                    trades.append(trade_data)
                    
                except Exception as e:
                    self.logger.warning(f"Failed to parse row: {e}")
                    continue
        
        return trades
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date from OpenInsider format (YYYY-MM-DD)."""
        if not date_str or date_str == "-":
            return None
        
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except:
            return None
    
    def _parse_transaction_type(self, type_str: str) -> str:
        """Parse transaction type from OpenInsider code."""
        type_str = type_str.upper().strip()
        
        if type_str in ["P", "P - Purchase"]:
            return "BUY"
        elif type_str in ["S", "S - Sale"]:
            return "SELL"
        elif type_str in ["A", "A - Award"]:
            return "AWARD"
        elif type_str in ["G", "G - Gift"]:
            return "GIFT"
        elif type_str in ["M", "M - Option Exercise"]:
            return "OPTION_EXERCISE"
        else:
            return "OTHER"
    
    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Parse amount from OpenInsider format (with commas, +/- signs)."""
        if not amount_str or amount_str == "-":
            return None
        
        try:
            # Remove commas, $, and +/- signs
            cleaned = amount_str.replace(",", "").replace("$", "").replace("+", "").replace("−", "-")
            cleaned = cleaned.strip()
            
            # Handle K/M/B suffixes
            multiplier = 1
            if cleaned.endswith("K"):
                multiplier = 1_000
                cleaned = cleaned[:-1]
            elif cleaned.endswith("M"):
                multiplier = 1_000_000
                cleaned = cleaned[:-1]
            elif cleaned.endswith("B"):
                multiplier = 1_000_000_000
                cleaned = cleaned[:-1]
            
            return float(cleaned) * multiplier
        except:
            return None
    
    def run_ingestion(self, mode: str = "recent", days: int = 30, **kwargs) -> Dict:
        """Run OpenInsider ingestion."""
        
        start_time = datetime.now()
        self.logger.info(f"Starting {self.name} ingestion in {mode} mode")
        
        try:
            trades_collected = 0
            trades_processed = 0
            errors = 0
            
            # Fetch trades
            for trade_data in self.fetch_recent_trades(days):
                trades_processed += 1
                
                # Save to database
                try:
                    self._save_trade(trade_data)
                    trades_collected += 1
                except Exception as e:
                    self.logger.warning(f"Failed to save trade: {e}")
                    errors += 1
            
            end_time = datetime.now()
            runtime = (end_time - start_time).total_seconds()
            
            self.logger.info(f"Ingestion completed: {trades_collected}/{trades_processed} trades collected in {runtime:.1f} seconds")
            
            return {
                "mode": mode,
                "trades_processed": trades_processed,
                "trades_collected": trades_collected,
                "errors": errors,
                "runtime_seconds": runtime,
                "start_time": start_time,
                "end_time": end_time
            }
            
        except Exception as e:
            self.logger.error(f"Ingestion failed: {e}")
            raise IngestionError(f"OpenInsider ingestion failed: {e}")
    
    def _save_trade(self, trade_data: RawTradeData):
        """Save trade to database."""
        
        with get_session() as session:
            # Get or create filer
            filer = session.query(Filer).filter(Filer.name == trade_data.filer_name).first()
            
            if not filer:
                filer = Filer(
                    name=trade_data.filer_name,
                    filer_type=FilerType.CORPORATE_INSIDER,
                    company=trade_data.company_name,
                    title=trade_data.insider_relationship
                )
                session.add(filer)
                session.flush()
            
            # Check if trade exists
            existing = session.query(Trade).filter(
                Trade.source == DataSource.OPENINSIDER,
                Trade.source_id == trade_data.source_id
            ).first()
            
            if existing:
                return
            
            # Create trade
            trade = Trade(
                filer_id=filer.filer_id,
                source=DataSource.OPENINSIDER,
                source_id=trade_data.source_id,
                reported_date=trade_data.reported_date,
                trade_date=trade_data.trade_date,
                ticker=trade_data.ticker,
                company_name=trade_data.company_name,
                transaction_type=TransactionType[trade_data.transaction_type],  # Use bracket notation for enum by name
                quantity=Decimal(str(trade_data.quantity)) if trade_data.quantity else None,
                price=Decimal(str(trade_data.price)) if trade_data.price else None,
                amount_usd=Decimal(str(trade_data.amount_usd)) if trade_data.amount_usd else None,
                insider_relationship=trade_data.insider_relationship,
                raw_data=trade_data.raw_data
            )
            
            session.add(trade)
            session.commit()


# Helper function for testing
def main():
    """Test OpenInsider scraper."""
    logging.basicConfig(level=logging.INFO)
    
    scraper = OpenInsiderScraper()
    result = scraper.run_ingestion(mode="recent", days=7)
    
    print(f"\n✅ OpenInsider Ingestion Complete:")
    print(f"   Trades collected: {result['trades_collected']}")
    print(f"   Trades processed: {result['trades_processed']}")
    print(f"   Runtime: {result['runtime_seconds']:.1f}s")


if __name__ == "__main__":
    main()

