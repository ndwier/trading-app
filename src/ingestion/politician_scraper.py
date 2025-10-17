"""Scraper for politician trading disclosures."""

import re
import json
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Iterator, Union, Any
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

from config.config import config
from src.database import get_session, Filer, Trade, FilerType, TransactionType, DataSource
from .base import APIIngester, ScrapingIngester, RawTradeData, IngestionError


class QuiverPoliticianScraper(APIIngester):
    """Scraper for Quiver Quantitative politician trades API."""
    
    def __init__(self):
        super().__init__(
            name="quiver_politician",
            base_url=config.api.QUIVER_BASE_URL,
            api_key=config.api.QUIVER_API_KEY,
            rate_limit=config.api.QUIVER_RATE_LIMIT
        )
        
        if not self.api_key:
            self.logger.warning("No Quiver API key found - will skip Quiver ingestion")
    
    def fetch_recent_trades(self, days: int = 30) -> Iterator[RawTradeData]:
        """Fetch recent politician trades from Quiver API."""
        if not self.api_key:
            self.logger.warning("Skipping Quiver ingestion - no API key")
            return
        
        endpoint = "congresstrading/recent"
        url = self._build_url(endpoint)
        
        try:
            response = self._make_request(url)
            trades_data = response.json()
            
            for trade in trades_data:
                yield self._parse_quiver_trade(trade)
                
        except Exception as e:
            self.logger.error(f"Failed to fetch recent trades from Quiver: {e}")
            raise IngestionError(f"Quiver API error: {e}")
    
    def fetch_historical_trades(self, start_date: date, end_date: date) -> Iterator[RawTradeData]:
        """Fetch historical trades for date range."""
        if not self.api_key:
            return
        
        # Quiver API doesn't support date ranges directly, so we'll get all data
        # and filter by date
        endpoint = "congresstrading/all"
        url = self._build_url(endpoint)
        
        try:
            response = self._make_request(url)
            trades_data = response.json()
            
            for trade in trades_data:
                trade_date = self._parse_date(trade.get("transaction_date"))
                report_date = self._parse_date(trade.get("report_date"))
                
                # Filter by date range
                relevant_date = trade_date or report_date
                if relevant_date and start_date <= relevant_date <= end_date:
                    yield self._parse_quiver_trade(trade)
                    
        except Exception as e:
            self.logger.error(f"Failed to fetch historical trades from Quiver: {e}")
    
    def fetch_filer_trades(self, filer_identifier: str) -> Iterator[RawTradeData]:
        """Fetch trades for specific politician."""
        if not self.api_key:
            return
        
        # Quiver uses politician names as identifiers
        endpoint = f"congresstrading/politician/{filer_identifier}"
        url = self._build_url(endpoint)
        
        try:
            response = self._make_request(url)
            trades_data = response.json()
            
            for trade in trades_data:
                yield self._parse_quiver_trade(trade)
                
        except Exception as e:
            self.logger.error(f"Failed to fetch trades for {filer_identifier}: {e}")
    
    def _parse_quiver_trade(self, trade_data: dict) -> RawTradeData:
        """Parse Quiver trade data into RawTradeData format."""
        return RawTradeData(
            source="quiver",
            source_id=str(trade_data.get("id", "")),
            filer_name=trade_data.get("representative", ""),
            filer_type="politician",
            reported_date=self._parse_date(trade_data.get("report_date")),
            trade_date=self._parse_date(trade_data.get("transaction_date")),
            ticker=trade_data.get("ticker", "").upper(),
            company_name=trade_data.get("asset_description", ""),
            transaction_type=self._normalize_transaction_type(trade_data.get("transaction", "")),
            amount_usd=self._parse_amount(trade_data.get("amount")),
            insider_relationship=trade_data.get("owner", ""),
            filing_url=trade_data.get("source_url", ""),
            raw_data=trade_data
        )
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse date string to date object."""
        if not date_str:
            return None
        
        try:
            # Try different date formats
            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    return datetime.strptime(date_str.split("T")[0], fmt).date()
                except ValueError:
                    continue
            
            self.logger.warning(f"Could not parse date: {date_str}")
            return None
            
        except Exception as e:
            self.logger.warning(f"Date parsing error: {e}")
            return None
    
    def _parse_amount(self, amount_str: Union[str, float, None]) -> Optional[float]:
        """Parse amount string to float."""
        if not amount_str:
            return None
        
        try:
            if isinstance(amount_str, (int, float)):
                return float(amount_str)
            
            # Remove currency symbols and commas
            amount_clean = re.sub(r'[$,]', '', str(amount_str))
            
            # Handle ranges (e.g., "$15,001 - $50,000")
            if " - " in amount_clean:
                parts = amount_clean.split(" - ")
                low = float(re.sub(r'[^\d.]', '', parts[0]))
                high = float(re.sub(r'[^\d.]', '', parts[1]))
                return (low + high) / 2  # Take midpoint
            
            # Single value
            return float(re.sub(r'[^\d.]', '', amount_clean))
            
        except Exception as e:
            self.logger.warning(f"Amount parsing error for '{amount_str}': {e}")
            return None
    
    def _normalize_transaction_type(self, transaction_str: str) -> str:
        """Normalize transaction type to standard format."""
        if not transaction_str:
            return ""
        
        transaction_lower = transaction_str.lower()
        
        if "buy" in transaction_lower or "purchase" in transaction_lower:
            return "buy"
        elif "sell" in transaction_lower or "sale" in transaction_lower:
            return "sell"
        elif "option" in transaction_lower:
            if "buy" in transaction_lower:
                return "option_buy"
            elif "sell" in transaction_lower:
                return "option_sell"
            else:
                return "option"
        else:
            return transaction_str.lower()


class CapitolTradesScraper(ScrapingIngester):
    """Free web scraper for Capitol Trades website."""
    
    def __init__(self):
        super().__init__(
            name="capitol_trades",
            base_url="https://www.capitoltrades.com"
        )
    
    def fetch_recent_trades(self, days: int = 30) -> Iterator[RawTradeData]:
        """Scrape recent trades from Capitol Trades."""
        url = urljoin(self.base_url, "/trades")
        
        try:
            response = self._make_request(url)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Parse trade table
            trade_rows = soup.find_all('tr', {'class': 'q-tr'})
            
            for row in trade_rows:
                try:
                    trade_data = self._parse_capitol_trades_row(row)
                    if trade_data and self._is_recent_trade(trade_data.reported_date, days):
                        yield trade_data
                except Exception as e:
                    self.logger.warning(f"Failed to parse row: {e}")
                    continue
                    
        except Exception as e:
            self.logger.error(f"Failed to scrape Capitol Trades: {e}")
    
    def fetch_historical_trades(self, start_date: date, end_date: date) -> Iterator[RawTradeData]:
        """Capitol Trades doesn't easily support historical queries."""
        # This would require pagination through multiple pages
        # For now, just return recent trades and filter
        for trade in self.fetch_recent_trades(days=365):
            if trade.reported_date and start_date <= trade.reported_date <= end_date:
                yield trade
    
    def fetch_filer_trades(self, filer_identifier: str) -> Iterator[RawTradeData]:
        """Fetch trades for specific politician by searching."""
        # Would need to implement politician-specific pages
        # For now, return all recent trades for that politician
        for trade in self.fetch_recent_trades(days=365):
            if trade.filer_name and filer_identifier.lower() in trade.filer_name.lower():
                yield trade
    
    def _parse_capitol_trades_row(self, row) -> Optional[RawTradeData]:
        """Parse a table row from Capitol Trades."""
        try:
            cells = row.find_all('td')
            if len(cells) < 6:
                return None
            
            # Extract data from cells
            politician = cells[0].get_text(strip=True)
            trade_date = cells[1].get_text(strip=True)
            ticker = cells[2].get_text(strip=True)
            transaction = cells[3].get_text(strip=True)
            amount = cells[4].get_text(strip=True)
            
            return RawTradeData(
                source="capitol_trades",
                source_id=f"ct_{hash(politician + trade_date + ticker)}",
                filer_name=politician,
                filer_type="politician",
                reported_date=self._parse_date_from_text(trade_date),
                ticker=ticker.upper() if ticker else None,
                transaction_type=self._normalize_transaction_type(transaction),
                amount_usd=self._parse_amount(amount),
                filing_url=self.base_url + "/trades",
                raw_data={"cells": [cell.get_text(strip=True) for cell in cells]}
            )
            
        except Exception as e:
            self.logger.warning(f"Row parsing error: {e}")
            return None
    
    def _parse_date_from_text(self, date_text: str) -> Optional[date]:
        """Parse date from text like '2 days ago' or actual date."""
        if not date_text:
            return None
        
        try:
            # Handle relative dates like "2 days ago"
            if "ago" in date_text.lower():
                if "day" in date_text:
                    days = int(re.search(r'(\d+)', date_text).group(1))
                    return date.today() - timedelta(days=days)
                elif "week" in date_text:
                    weeks = int(re.search(r'(\d+)', date_text).group(1))
                    return date.today() - timedelta(weeks=weeks)
                elif "month" in date_text:
                    months = int(re.search(r'(\d+)', date_text).group(1))
                    return date.today() - timedelta(days=months * 30)
            
            # Try actual date formats
            for fmt in ["%m/%d/%Y", "%Y-%m-%d", "%b %d, %Y"]:
                try:
                    return datetime.strptime(date_text, fmt).date()
                except ValueError:
                    continue
            
            return None
            
        except Exception:
            return None
    
    def _is_recent_trade(self, trade_date: Optional[date], days: int) -> bool:
        """Check if trade is within the recent days window."""
        if not trade_date:
            return False
        
        cutoff_date = date.today() - timedelta(days=days)
        return trade_date >= cutoff_date


class PoliticianScraper:
    """Main politician scraper that coordinates multiple sources."""
    
    def __init__(self):
        self.scrapers = []
        
        # Initialize available scrapers
        try:
            quiver_scraper = QuiverPoliticianScraper()
            if quiver_scraper.api_key:
                self.scrapers.append(quiver_scraper)
            else:
                self.logger = logging.getLogger(__name__)
                self.logger.info("Quiver API key not found, using free sources only")
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to initialize Quiver scraper: {e}")
        
        # Add free scraper
        try:
            capitol_scraper = CapitolTradesScraper()
            self.scrapers.append(capitol_scraper)
        except Exception as e:
            logging.getLogger(__name__).warning(f"Failed to initialize Capitol Trades scraper: {e}")
        
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"Initialized {len(self.scrapers)} politician scrapers")
    
    def run_full_ingestion(self, days: int = 30) -> Dict[str, Any]:
        """Run ingestion from all available sources."""
        results = {}
        total_trades = 0
        
        for scraper in self.scrapers:
            try:
                self.logger.info(f"Running ingestion for {scraper.name}")
                result = scraper.run_ingestion(mode="recent", days=days)
                results[scraper.name] = result
                total_trades += result.get("trades_collected", 0)
                
                # Save trades to database
                self._save_trades_to_db(scraper.fetch_recent_trades(days))
                
            except Exception as e:
                self.logger.error(f"Ingestion failed for {scraper.name}: {e}")
                results[scraper.name] = {"error": str(e)}
        
        self.logger.info(f"Political ingestion complete: {total_trades} total trades")
        return {
            "total_trades": total_trades,
            "scraper_results": results
        }
    
    def _save_trades_to_db(self, trades_iter: Iterator[RawTradeData]):
        """Save trades to database."""
        with get_session() as session:
            for trade_data in trades_iter:
                try:
                    # Get or create filer
                    filer = self._get_or_create_filer(session, trade_data)
                    
                    # Check if trade already exists
                    existing_trade = session.query(Trade).filter(
                        Trade.source == DataSource(trade_data.source),
                        Trade.source_id == trade_data.source_id
                    ).first()
                    
                    if existing_trade:
                        continue
                    
                    # Create new trade
                    trade = Trade(
                        filer_id=filer.filer_id,
                        source=DataSource(trade_data.source),
                        source_id=trade_data.source_id,
                        reported_date=trade_data.reported_date,
                        trade_date=trade_data.trade_date,
                        ticker=trade_data.ticker,
                        company_name=trade_data.company_name,
                        transaction_type=TransactionType(trade_data.transaction_type)
                            if trade_data.transaction_type in [t.value for t in TransactionType]
                            else TransactionType.BUY,
                        amount_usd=trade_data.amount_usd,
                        insider_relationship=trade_data.insider_relationship,
                        filing_url=trade_data.filing_url,
                        raw_data=trade_data.raw_data
                    )
                    
                    session.add(trade)
                    
                except Exception as e:
                    self.logger.warning(f"Failed to save trade: {e}")
                    continue
    
    def _get_or_create_filer(self, session, trade_data: RawTradeData) -> Filer:
        """Get or create filer from trade data."""
        filer = session.query(Filer).filter(
            Filer.name == trade_data.filer_name,
            Filer.filer_type == FilerType.POLITICIAN
        ).first()
        
        if not filer:
            filer = Filer(
                name=trade_data.filer_name,
                filer_type=FilerType.POLITICIAN
            )
            session.add(filer)
            session.flush()
        
        return filer


if __name__ == "__main__":
    # CLI for running politician scraper
    import argparse
    
    parser = argparse.ArgumentParser(description="Run politician trade scraper")
    parser.add_argument("--days", type=int, default=30,
                       help="Number of days to look back")
    
    args = parser.parse_args()
    
    scraper = PoliticianScraper()
    results = scraper.run_full_ingestion(days=args.days)
    
    print(json.dumps(results, indent=2, default=str))
