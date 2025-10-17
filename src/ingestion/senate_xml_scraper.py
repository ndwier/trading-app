"""Senate eFilings XML scraper for senator trading disclosures."""

import logging
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Iterator
from decimal import Decimal

import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET

from config.config import config
from src.database import get_session, Filer, Trade, FilerType, TransactionType, DataSource
from .base import ScrapingIngester, RawTradeData, IngestionError


class SenateXMLScraper(ScrapingIngester):
    """Scraper for Senate eFilings XML feed - periodic transaction reports."""
    
    def __init__(self):
        super().__init__(
            name="senate_xml",
            base_url="https://efdsearch.senate.gov"
        )
        
    def fetch_recent_trades(self, days: int = 30) -> Iterator[RawTradeData]:
        """Fetch recent senator trading disclosures."""
        
        # Senate search page
        search_url = f"{self.base_url}/search/"
        
        try:
            # Get recent PTR (Periodic Transaction Report) filings
            filings = self._search_recent_filings(days)
            
            for filing in filings:
                trades = self._parse_filing(filing)
                for trade in trades:
                    yield trade
                    
        except Exception as e:
            self.logger.error(f"Failed to fetch Senate filings: {e}")
    
    def _search_recent_filings(self, days: int) -> List[Dict]:
        """Search for recent PTR filings."""
        
        filings = []
        
        # Senate search endpoint (may require POST with search params)
        search_url = f"{self.base_url}/search/home/"
        
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # Search parameters
        payload = {
            'report_type': 'PTR',  # Periodic Transaction Report
            'senator': '',  # All senators
            'date_received_from': start_date.strftime('%m/%d/%Y'),
            'date_received_to': end_date.strftime('%m/%d/%Y'),
            'submitted': 'Search'
        }
        
        try:
            response = self.session.post(search_url, data=payload, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Parse results table
            table = soup.find('table', {'class': 'table'})
            if table:
                rows = table.find_all('tr')[1:]  # Skip header
                
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 4:
                        # Extract filing info
                        name_cell = cols[0]
                        date_cell = cols[1]
                        link_cell = cols[3]
                        
                        link = link_cell.find('a')
                        if link and link.get('href'):
                            filings.append({
                                'name': name_cell.text.strip(),
                                'date': date_cell.text.strip(),
                                'url': self.base_url + link['href']
                            })
            
            self.logger.info(f"Found {len(filings)} Senate PTR filings")
            
        except Exception as e:
            self.logger.error(f"Failed to search Senate filings: {e}")
        
        return filings
    
    def _parse_filing(self, filing: Dict) -> List[RawTradeData]:
        """Parse a Senate PTR filing."""
        
        trades = []
        
        try:
            response = self._make_request(filing['url'])
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Senate filings may have structured data or be PDFs
            # Look for transaction tables
            tables = soup.find_all('table')
            
            for table in tables:
                # Look for transaction table (contains Asset, Type, Date, Amount columns)
                headers = [th.text.strip().lower() for th in table.find_all('th')]
                
                if any(h in headers for h in ['asset', 'ticker', 'transaction']):
                    rows = table.find_all('tr')[1:]  # Skip header
                    
                    for row in rows:
                        cols = row.find_all('td')
                        if len(cols) >= 4:
                            trade_data = self._parse_transaction_row(cols, filing)
                            if trade_data:
                                trades.append(trade_data)
            
            # Also check for XML data in the page
            xml_link = soup.find('a', href=re.compile(r'\.xml$'))
            if xml_link:
                xml_url = self.base_url + xml_link['href']
                xml_trades = self._parse_xml_filing(xml_url, filing)
                trades.extend(xml_trades)
            
        except Exception as e:
            self.logger.warning(f"Failed to parse filing {filing['url']}: {e}")
        
        return trades
    
    def _parse_transaction_row(self, cols: List, filing: Dict) -> Optional[RawTradeData]:
        """Parse a transaction row from Senate filing table."""
        
        try:
            # Common column patterns:
            # Asset/Security | Type | Date | Amount | Ticker
            
            asset_name = cols[0].text.strip() if len(cols) > 0 else ''
            trans_type = cols[1].text.strip() if len(cols) > 1 else ''
            trans_date = cols[2].text.strip() if len(cols) > 2 else ''
            amount = cols[3].text.strip() if len(cols) > 3 else ''
            ticker = cols[4].text.strip() if len(cols) > 4 else ''
            
            # Extract ticker if not in separate column
            if not ticker:
                # Look for ticker in parentheses
                match = re.search(r'\(([A-Z]{1,5})\)', asset_name)
                if match:
                    ticker = match.group(1)
                    asset_name = re.sub(r'\s*\([A-Z]{1,5}\)', '', asset_name)
            
            # Parse transaction type
            trans_type_lower = trans_type.lower()
            if 'purchase' in trans_type_lower or 'buy' in trans_type_lower:
                transaction_type = 'BUY'
            elif 'sale' in trans_type_lower or 'sell' in trans_type_lower:
                transaction_type = 'SELL'
            elif 'exchange' in trans_type_lower:
                transaction_type = 'EXCHANGE'
            else:
                transaction_type = 'OTHER'
            
            # Parse amount (often ranges like "$15,001 - $50,000")
            amount_value = self._parse_amount_range(amount)
            
            # Parse date
            try:
                trade_date = datetime.strptime(trans_date, '%m/%d/%Y').date()
            except:
                trade_date = date.today()
            
            return RawTradeData(
                source="senate_xml",
                source_id=f"senate_{filing['name']}_{ticker}_{trade_date}_{amount_value}",
                reported_date=datetime.strptime(filing['date'], '%m/%d/%Y').date() if filing.get('date') else trade_date,
                trade_date=trade_date,
                ticker=ticker.upper() if ticker else asset_name[:10].upper(),
                company_name=asset_name,
                filer_name=filing['name'],
                filer_type=FilerType.POLITICIAN.value,
                transaction_type=transaction_type,
                amount_usd=amount_value,
                raw_data={
                    'source': 'senate_xml',
                    'filing_url': filing['url'],
                    'amount_range': amount
                }
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to parse transaction row: {e}")
            return None
    
    def _parse_xml_filing(self, xml_url: str, filing: Dict) -> List[RawTradeData]:
        """Parse XML version of Senate filing."""
        
        trades = []
        
        try:
            response = self._make_request(xml_url)
            root = ET.fromstring(response.text)
            
            # XML structure varies, look for transaction elements
            for trans in root.findall('.//Transaction'):
                asset = trans.find('AssetName')
                ticker_elem = trans.find('Ticker')
                trans_type = trans.find('TransactionType')
                trans_date = trans.find('TransactionDate')
                amount = trans.find('Amount')
                
                if asset is not None:
                    ticker = ticker_elem.text if ticker_elem is not None else ''
                    
                    trade_data = RawTradeData(
                        source="senate_xml",
                        source_id=f"senate_xml_{filing['name']}_{ticker}_{trans_date.text if trans_date is not None else ''}",
                        reported_date=datetime.strptime(filing['date'], '%m/%d/%Y').date(),
                        trade_date=datetime.strptime(trans_date.text, '%Y-%m-%d').date() if trans_date is not None else date.today(),
                        ticker=ticker.upper() if ticker else asset.text[:10].upper(),
                        company_name=asset.text,
                        filer_name=filing['name'],
                        filer_type=FilerType.POLITICIAN.value,
                        transaction_type='BUY' if trans_type is not None and 'purchase' in trans_type.text.lower() else 'SELL',
                        amount_usd=self._parse_amount_range(amount.text) if amount is not None else 0,
                        raw_data={
                            'source': 'senate_xml',
                            'filing_url': filing['url']
                        }
                    )
                    trades.append(trade_data)
            
        except Exception as e:
            self.logger.warning(f"Failed to parse XML filing: {e}")
        
        return trades
    
    def _parse_amount_range(self, amount_str: str) -> float:
        """Parse amount range (e.g., '$15,001 - $50,000') to midpoint."""
        
        if not amount_str:
            return 0
        
        # Remove $ and commas
        amount_str = amount_str.replace('$', '').replace(',', '')
        
        # Check for range
        if '-' in amount_str:
            parts = amount_str.split('-')
            try:
                low = float(parts[0].strip())
                high = float(parts[1].strip())
                return (low + high) / 2
            except:
                return 0
        
        # Single value
        try:
            return float(amount_str.strip())
        except:
            return 0
    
    def fetch_historical_trades(self, start_date: date, end_date: date) -> Iterator[RawTradeData]:
        """Fetch historical trades."""
        days = (end_date - start_date).days
        return self.fetch_recent_trades(days)
    
    def fetch_filer_trades(self, filer_name: str) -> Iterator[RawTradeData]:
        """Fetch trades for specific senator."""
        # Would need to implement senator-specific search
        return iter([])
    
    def run_ingestion(self, mode: str = "recent", days: int = 30, **kwargs) -> Dict:
        """Run Senate XML ingestion."""
        
        start_time = datetime.now()
        self.logger.info(f"Starting {self.name} ingestion")
        
        try:
            trades_collected = 0
            trades_processed = 0
            errors = 0
            
            for trade_data in self.fetch_recent_trades(days):
                trades_processed += 1
                
                try:
                    self._save_trade(trade_data)
                    trades_collected += 1
                except Exception as e:
                    self.logger.warning(f"Failed to save trade: {e}")
                    errors += 1
            
            end_time = datetime.now()
            runtime = (end_time - start_time).total_seconds()
            
            self.logger.info(f"Ingestion completed: {trades_collected}/{trades_processed} trades in {runtime:.1f}s")
            
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
            raise IngestionError(f"Senate XML ingestion failed: {e}")
    
    def _save_trade(self, trade_data: RawTradeData):
        """Save trade to database."""
        
        with get_session() as session:
            # Get or create filer
            filer = session.query(Filer).filter(Filer.name == trade_data.filer_name).first()
            
            if not filer:
                filer = Filer(
                    name=trade_data.filer_name,
                    filer_type=FilerType.POLITICIAN,
                    chamber='Senate'
                )
                session.add(filer)
                session.flush()
            
            # Check if exists
            existing = session.query(Trade).filter(
                Trade.source == DataSource.SCRAPED,
                Trade.source_id == trade_data.source_id
            ).first()
            
            if existing:
                return
            
            # Create trade
            trade = Trade(
                filer_id=filer.filer_id,
                source=DataSource.SCRAPED,
                source_id=trade_data.source_id,
                reported_date=trade_data.reported_date,
                trade_date=trade_data.trade_date,
                ticker=trade_data.ticker,
                company_name=trade_data.company_name,
                transaction_type=TransactionType[trade_data.transaction_type],
                amount_usd=Decimal(str(trade_data.amount_usd)) if trade_data.amount_usd else None,
                filing_url=trade_data.raw_data.get('filing_url'),
                raw_data=trade_data.raw_data
            )
            
            session.add(trade)
            session.commit()


def main():
    """Test Senate XML scraper."""
    logging.basicConfig(level=logging.INFO)
    
    print("Note: Senate eFilings system may require authentication or have CAPTCHAs.")
    print("Testing basic scraping...\n")
    
    scraper = SenateXMLScraper()
    result = scraper.run_ingestion(mode="recent", days=14)
    
    print(f"\n✅ Senate XML Ingestion Complete:")
    print(f"   Trades collected: {result.get('trades_collected', 0)}")
    print(f"   Trades processed: {result.get('trades_processed', 0)}")


if __name__ == "__main__":
    main()

