"""House of Representatives PDF scraper for financial disclosures."""

import logging
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Iterator
from decimal import Decimal
import io

import requests
from bs4 import BeautifulSoup

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logging.warning("pdfplumber not available. Install with: pip install pdfplumber")

from config.config import config
from src.database import get_session, Filer, Trade, FilerType, TransactionType, DataSource
from .base import ScrapingIngester, RawTradeData, IngestionError


class HousePDFScraper(ScrapingIngester):
    """Scraper for House of Representatives financial disclosure PDFs."""
    
    def __init__(self):
        super().__init__(
            name="house_pdf",
            base_url="https://disclosures-clerk.house.gov"
        )
        
        if not PDFPLUMBER_AVAILABLE:
            self.logger.warning("pdfplumber not installed - House PDF scraping will be limited")
    
    def fetch_recent_trades(self, days: int = 30) -> Iterator[RawTradeData]:
        """Fetch recent House trading disclosures from PDFs."""
        
        # House Financial Disclosure search
        search_url = f"{self.base_url}/FinancialDisclosure"
        
        try:
            # Get list of recent PTR (Periodic Transaction Report) filings
            filings = self._search_recent_filings(days)
            
            for filing in filings:
                # Download and parse PDF
                trades = self._parse_pdf_filing(filing)
                for trade in trades:
                    yield trade
                    
        except Exception as e:
            self.logger.error(f"Failed to fetch House filings: {e}")
    
    def _search_recent_filings(self, days: int) -> List[Dict]:
        """Search for recent PTR filings."""
        
        filings = []
        
        # House disclosure search endpoint
        search_url = f"{self.base_url}/public_disc/financial-pdfs/"
        
        # Calculate year range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # House organizes by year
        years = list(range(start_date.year, end_date.year + 1))
        
        for year in years:
            year_url = f"{search_url}{year}/"
            
            try:
                response = self._make_request(year_url)
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find PTR PDFs (Periodic Transaction Reports)
                pdf_links = soup.find_all('a', href=re.compile(r'.*PTR.*\.pdf', re.IGNORECASE))
                
                for link in pdf_links[:20]:  # Limit to 20 per year
                    pdf_url = link.get('href')
                    if not pdf_url.startswith('http'):
                        pdf_url = self.base_url + pdf_url
                    
                    # Extract member name from filename or link text
                    filename = pdf_url.split('/')[-1]
                    member_name = self._extract_name_from_filename(filename, link.text)
                    
                    filings.append({
                        'url': pdf_url,
                        'name': member_name,
                        'year': year,
                        'filename': filename
                    })
                
            except Exception as e:
                self.logger.warning(f"Failed to search {year}: {e}")
                continue
        
        self.logger.info(f"Found {len(filings)} House PTR filings")
        return filings
    
    def _extract_name_from_filename(self, filename: str, link_text: str) -> str:
        """Extract member name from PDF filename or link text."""
        
        # Remove extension and PTR prefix/suffix
        name = filename.replace('.pdf', '').replace('.PDF', '')
        name = re.sub(r'PTR.*', '', name, flags=re.IGNORECASE)
        name = re.sub(r'.*PTR', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\d{8,}', '', name)  # Remove date stamps
        name = re.sub(r'[_-]+', ' ', name)
        
        # Clean up
        name = name.strip()
        
        # If name is too short or unclear, try link text
        if len(name) < 3 and link_text:
            name = link_text.strip()
        
        return name if name else "Unknown House Member"
    
    def _parse_pdf_filing(self, filing: Dict) -> List[RawTradeData]:
        """Parse a House PTR PDF filing."""
        
        trades = []
        
        if not PDFPLUMBER_AVAILABLE:
            self.logger.warning("Cannot parse PDF - pdfplumber not installed")
            return trades
        
        try:
            # Download PDF
            response = self._make_request(filing['url'])
            pdf_bytes = io.BytesIO(response.content)
            
            # Parse PDF
            with pdfplumber.open(pdf_bytes) as pdf:
                for page in pdf.pages:
                    # Extract text
                    text = page.extract_text()
                    
                    if text:
                        # Look for transaction tables
                        page_trades = self._extract_trades_from_text(text, filing)
                        trades.extend(page_trades)
                    
                    # Also try table extraction
                    tables = page.extract_tables()
                    for table in tables:
                        if table:
                            table_trades = self._extract_trades_from_table(table, filing)
                            trades.extend(table_trades)
            
        except Exception as e:
            self.logger.warning(f"Failed to parse PDF {filing['filename']}: {e}")
        
        return trades
    
    def _extract_trades_from_text(self, text: str, filing: Dict) -> List[RawTradeData]:
        """Extract trades from PDF text using pattern matching."""
        
        trades = []
        
        # Common patterns in House PTR forms
        # Format varies, but often includes:
        # Asset | Transaction Type | Date | Amount
        
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            # Look for transaction indicators
            if any(word in line.lower() for word in ['purchase', 'sale', 'buy', 'sell', 'exchange']):
                # Try to extract trade info from this line and surrounding lines
                trade_data = self._parse_trade_line(line, lines[max(0, i-2):min(len(lines), i+3)], filing)
                
                if trade_data:
                    trades.append(trade_data)
        
        return trades
    
    def _parse_trade_line(self, line: str, context_lines: List[str], filing: Dict) -> Optional[RawTradeData]:
        """Parse a single trade line with context."""
        
        try:
            # Combine context for better parsing
            full_text = ' '.join(context_lines)
            
            # Extract ticker (if present)
            ticker_match = re.search(r'\b([A-Z]{1,5})\b', line)
            ticker = ticker_match.group(1) if ticker_match else ''
            
            # Extract transaction type
            trans_type = 'BUY'
            if any(word in line.lower() for word in ['sale', 'sell']):
                trans_type = 'SELL'
            elif 'exchange' in line.lower():
                trans_type = 'EXCHANGE'
            
            # Extract date (various formats)
            date_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', full_text)
            if date_match:
                date_str = date_match.group(1)
                try:
                    trade_date = datetime.strptime(date_str.replace('-', '/'), '%m/%d/%Y').date()
                except:
                    try:
                        trade_date = datetime.strptime(date_str.replace('-', '/'), '%m/%d/%y').date()
                    except:
                        trade_date = date.today()
            else:
                trade_date = date.today()
            
            # Extract amount (often ranges like "$15,001 - $50,000")
            amount_match = re.search(r'\$[\d,]+\s*-\s*\$[\d,]+', full_text)
            if amount_match:
                amount_str = amount_match.group(0)
                amount = self._parse_amount_range(amount_str)
            else:
                # Try single amount
                amount_match = re.search(r'\$([\d,]+)', full_text)
                amount = float(amount_match.group(1).replace(',', '')) if amount_match else 0
            
            # Extract asset name (first capitalized phrase)
            asset_match = re.search(r'([A-Z][a-zA-Z\s&\.]+(?:[A-Z][a-zA-Z\s&\.]+)*)', line)
            asset_name = asset_match.group(1).strip() if asset_match else 'Unknown'
            
            return RawTradeData(
                source="house_pdf",
                source_id=f"house_{filing['name']}_{ticker}_{trade_date}_{amount}",
                reported_date=date.today(),  # PDF date not always clear
                trade_date=trade_date,
                ticker=ticker if ticker else asset_name[:10].upper(),
                company_name=asset_name,
                filer_name=filing['name'],
                filer_type=FilerType.POLITICIAN.value,
                transaction_type=trans_type,
                amount_usd=amount,
                raw_data={
                    'source': 'house_pdf',
                    'pdf_url': filing['url'],
                    'year': filing['year']
                }
            )
            
        except Exception as e:
            self.logger.debug(f"Failed to parse trade line: {e}")
            return None
    
    def _extract_trades_from_table(self, table: List[List], filing: Dict) -> List[RawTradeData]:
        """Extract trades from PDF table."""
        
        trades = []
        
        if not table or len(table) < 2:
            return trades
        
        # Try to identify header row
        header = [str(cell).lower() if cell else '' for cell in table[0]]
        
        # Find column indices
        asset_col = next((i for i, h in enumerate(header) if 'asset' in h or 'security' in h), 0)
        type_col = next((i for i, h in enumerate(header) if 'type' in h or 'transaction' in h), 1)
        date_col = next((i for i, h in enumerate(header) if 'date' in h), 2)
        amount_col = next((i for i, h in enumerate(header) if 'amount' in h or 'value' in h), 3)
        
        # Parse rows
        for row in table[1:]:
            if not row or len(row) < 2:
                continue
            
            try:
                asset = str(row[asset_col]) if asset_col < len(row) else ''
                trans_type = str(row[type_col]) if type_col < len(row) else ''
                date_str = str(row[date_col]) if date_col < len(row) else ''
                amount_str = str(row[amount_col]) if amount_col < len(row) else ''
                
                # Skip if no meaningful data
                if not asset or asset.lower() in ['none', 'n/a', '']:
                    continue
                
                # Parse transaction type
                trans_type_clean = 'BUY'
                if 'sale' in trans_type.lower() or 'sell' in trans_type.lower():
                    trans_type_clean = 'SELL'
                
                # Parse date
                try:
                    trade_date = datetime.strptime(date_str, '%m/%d/%Y').date()
                except:
                    trade_date = date.today()
                
                # Parse amount
                amount = self._parse_amount_range(amount_str)
                
                # Extract ticker
                ticker_match = re.search(r'\(([A-Z]{1,5})\)', asset)
                ticker = ticker_match.group(1) if ticker_match else asset[:5].upper()
                
                trade_data = RawTradeData(
                    source="house_pdf",
                    source_id=f"house_table_{filing['name']}_{ticker}_{trade_date}",
                    reported_date=date.today(),
                    trade_date=trade_date,
                    ticker=ticker,
                    company_name=asset,
                    filer_name=filing['name'],
                    filer_type=FilerType.POLITICIAN.value,
                    transaction_type=trans_type_clean,
                    amount_usd=amount,
                    raw_data={
                        'source': 'house_pdf',
                        'pdf_url': filing['url']
                    }
                )
                
                trades.append(trade_data)
                
            except Exception as e:
                self.logger.debug(f"Failed to parse table row: {e}")
                continue
        
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
        """Fetch trades for specific House member."""
        # Would need member-specific search
        return iter([])
    
    def run_ingestion(self, mode: str = "recent", days: int = 30, **kwargs) -> Dict:
        """Run House PDF ingestion."""
        
        start_time = datetime.now()
        self.logger.info(f"Starting {self.name} ingestion")
        
        if not PDFPLUMBER_AVAILABLE:
            return {
                "error": "pdfplumber not installed. Run: pip install pdfplumber"
            }
        
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
            raise IngestionError(f"House PDF ingestion failed: {e}")
    
    def _save_trade(self, trade_data: RawTradeData):
        """Save trade to database."""
        
        with get_session() as session:
            # Get or create filer
            filer = session.query(Filer).filter(Filer.name == trade_data.filer_name).first()
            
            if not filer:
                filer = Filer(
                    name=trade_data.filer_name,
                    filer_type=FilerType.POLITICIAN,
                    chamber='House'
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
                filing_url=trade_data.raw_data.get('pdf_url'),
                raw_data=trade_data.raw_data
            )
            
            session.add(trade)
            session.commit()


def main():
    """Test House PDF scraper."""
    logging.basicConfig(level=logging.INFO)
    
    if not PDFPLUMBER_AVAILABLE:
        print("❌ pdfplumber not installed")
        print("Install with: pip install pdfplumber")
        return
    
    print("Testing House PDF scraper...")
    print("Note: House PDFs can be complex and parsing may be slow.\n")
    
    scraper = HousePDFScraper()
    result = scraper.run_ingestion(mode="recent", days=14)
    
    if "error" in result:
        print(f"\n❌ Error: {result['error']}")
    else:
        print(f"\n✅ House PDF Ingestion Complete:")
        print(f"   Trades collected: {result.get('trades_collected', 0)}")
        print(f"   Trades processed: {result.get('trades_processed', 0)}")


if __name__ == "__main__":
    main()

