"""SEC EDGAR scraper for corporate insider trading disclosures."""

import xml.etree.ElementTree as ET
import re
import json
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Iterator, Union, Any
from urllib.parse import urljoin
import requests

from config.config import config
from src.database import get_session, Filer, Trade, FilerType, TransactionType, DataSource
from .base import APIIngester, RawTradeData, IngestionError


class SECEdgarScraper(APIIngester):
    """Scraper for SEC EDGAR insider trading forms."""
    
    def __init__(self):
        super().__init__(
            name="sec_edgar",
            base_url=config.api.SEC_EDGAR_BASE_URL,
            rate_limit=config.api.SEC_RATE_LIMIT
        )
        
        # SEC requires specific headers
        self.session.headers.update(config.api.SEC_HEADERS)
        
        # Form types we're interested in
        self.form_types = ["3", "4", "5"]  # Initial, Changes, Annual
        
        # Common XML namespaces used in SEC filings
        self.xml_namespaces = {
            'edgar': 'http://www.sec.gov/edgar/common',
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance'
        }
    
    def fetch_recent_trades(self, days: int = 30) -> Iterator[RawTradeData]:
        """Fetch recent insider trades from SEC EDGAR."""
        
        # Get recent filings index
        # SEC data has a 3-5 day publishing delay, so go back at least 5 days
        end_date = date.today() - timedelta(days=5)
        start_date = end_date - timedelta(days=days)
        
        for current_date in self._date_range(start_date, end_date):
            try:
                filings = self._get_daily_filings(current_date)
                
                for filing in filings:
                    if filing.get('form') in self.form_types:
                        trades = self._process_filing(filing)
                        for trade in trades:
                            yield trade
                            
            except Exception as e:
                self.logger.warning(f"Failed to process filings for {current_date}: {e}")
                continue
    
    def fetch_historical_trades(self, start_date: date, end_date: date) -> Iterator[RawTradeData]:
        """Fetch historical insider trades for date range."""
        
        for current_date in self._date_range(start_date, end_date):
            try:
                filings = self._get_daily_filings(current_date)
                
                for filing in filings:
                    if filing.get('form') in self.form_types:
                        trades = self._process_filing(filing)
                        for trade in trades:
                            yield trade
                            
            except Exception as e:
                self.logger.warning(f"Failed to process filings for {current_date}: {e}")
                continue
    
    def fetch_filer_trades(self, filer_identifier: str) -> Iterator[RawTradeData]:
        """Fetch trades for specific CIK (Central Index Key)."""
        
        # CIK should be padded to 10 digits
        cik = filer_identifier.zfill(10)
        
        try:
            # Get company filings
            url = f"{self.base_url}/submissions/CIK{cik}.json"
            response = self._make_request(url)
            company_data = response.json()
            
            # Process recent filings
            filings = company_data.get('filings', {}).get('recent', {})
            
            if filings:
                forms = filings.get('form', [])
                dates = filings.get('filingDate', [])
                accession_numbers = filings.get('accessionNumber', [])
                
                for i, form in enumerate(forms):
                    if form in self.form_types:
                        filing_info = {
                            'form': form,
                            'filingDate': dates[i] if i < len(dates) else None,
                            'accessionNumber': accession_numbers[i] if i < len(accession_numbers) else None,
                            'cik': cik
                        }
                        
                        trades = self._process_filing(filing_info)
                        for trade in trades:
                            yield trade
                            
        except Exception as e:
            self.logger.error(f"Failed to fetch trades for CIK {cik}: {e}")
    
    def _get_daily_filings(self, filing_date: date) -> List[Dict]:
        """Get all filings for a specific date."""
        
        # SEC daily index format: https://www.sec.gov/Archives/edgar/daily-index/2023/QTR4/master.20231215.idx
        year = filing_date.year
        quarter = f"QTR{((filing_date.month - 1) // 3) + 1}"
        date_str = filing_date.strftime("%Y%m%d")
        
        index_url = f"{self.base_url}/Archives/edgar/daily-index/{year}/{quarter}/master.{date_str}.idx"
        
        try:
            response = self._make_request(index_url)
            return self._parse_daily_index(response.text, filing_date)
            
        except Exception as e:
            self.logger.warning(f"Failed to get daily index for {filing_date}: {e}")
            return []
    
    def _parse_daily_index(self, index_content: str, filing_date: date) -> List[Dict]:
        """Parse SEC daily index file."""
        
        filings = []
        lines = index_content.split('\n')
        
        # Skip header lines (usually first 10 lines are header)
        data_lines = lines[10:]
        
        for line in data_lines:
            if not line.strip():
                continue
                
            parts = line.split('|')
            if len(parts) >= 5:
                cik = parts[0].strip()
                company_name = parts[1].strip()
                form_type = parts[2].strip()
                date_filed = parts[3].strip()
                filename = parts[4].strip()
                
                # Filter for insider trading forms
                if form_type in self.form_types:
                    filings.append({
                        'cik': cik,
                        'companyName': company_name,
                        'form': form_type,
                        'filingDate': date_filed,
                        'filename': filename,
                        'url': f"{self.base_url}/Archives/{filename}"
                    })
        
        return filings
    
    def _process_filing(self, filing_info: Dict) -> List[RawTradeData]:
        """Process a single SEC filing and extract trades."""
        
        try:
            # Download the filing document
            filing_url = filing_info.get('url')
            if not filing_url:
                # Construct URL from accession number
                accession = filing_info.get('accessionNumber', '').replace('-', '')
                cik = filing_info.get('cik', '').zfill(10)
                filing_url = f"{self.base_url}/Archives/edgar/data/{int(cik)}/{accession}/{accession}.txt"
            
            response = self._make_request(filing_url)
            
            # Parse the filing (can be XML or text format)
            if '<XML>' in response.text.upper():
                return self._parse_xml_filing(response.text, filing_info)
            else:
                return self._parse_text_filing(response.text, filing_info)
                
        except Exception as e:
            self.logger.warning(f"Failed to process filing {filing_info.get('accessionNumber', '')}: {e}")
            return []
    
    def _parse_xml_filing(self, content: str, filing_info: Dict) -> List[RawTradeData]:
        """Parse XML format SEC filing."""
        
        trades = []
        
        try:
            # Extract XML section
            xml_start = content.upper().find('<XML>')
            xml_end = content.upper().find('</XML>')
            
            if xml_start == -1 or xml_end == -1:
                return trades
            
            xml_content = content[xml_start + 5:xml_end]
            
            # Parse XML
            root = ET.fromstring(xml_content)
            
            # Extract filer information
            filer_info = self._extract_filer_info(root)
            
            # Extract transactions
            transactions = self._extract_transactions(root)
            
            for transaction in transactions:
                trade_data = self._create_trade_data(
                    filer_info, 
                    transaction, 
                    filing_info
                )
                if trade_data:
                    trades.append(trade_data)
                    
        except Exception as e:
            self.logger.warning(f"XML parsing error: {e}")
        
        return trades
    
    def _parse_text_filing(self, content: str, filing_info: Dict) -> List[RawTradeData]:
        """Parse text format SEC filing (older format)."""
        
        # This is more complex as text filings have various formats
        # For now, return empty list - would need specific parsing logic
        self.logger.debug("Text filing parsing not yet implemented")
        return []
    
    def _extract_filer_info(self, root: ET.Element) -> Dict:
        """Extract filer information from XML."""
        
        filer_info = {}
        
        # Try to find reporting owner info
        for elem in root.iter():
            tag = elem.tag.lower()
            
            if 'reportingowner' in tag or 'rptowner' in tag:
                # Get name
                name_elem = elem.find('.//rptOwnerName') or elem.find('.//reportingOwnerName')
                if name_elem is not None:
                    filer_info['name'] = name_elem.text
                
                # Get title/relationship
                title_elem = elem.find('.//officerTitle') or elem.find('.//directorTitle')
                if title_elem is not None:
                    filer_info['title'] = title_elem.text
                
                # Get CIK
                cik_elem = elem.find('.//rptOwnerCik') or elem.find('.//reportingOwnerCik')
                if cik_elem is not None:
                    filer_info['cik'] = cik_elem.text
        
        return filer_info
    
    def _extract_transactions(self, root: ET.Element) -> List[Dict]:
        """Extract transaction information from XML."""
        
        transactions = []
        
        # Look for non-derivative and derivative transactions
        for transaction_type in ['nonderivativeTable', 'derivativeTable']:
            
            # Find transaction elements
            for elem in root.iter():
                tag = elem.tag.lower()
                
                if 'transaction' in tag and transaction_type.lower() in elem.getparent().tag.lower():
                    
                    transaction = {}
                    
                    # Extract transaction details
                    for child in elem.iter():
                        child_tag = child.tag.lower()
                        
                        if 'transactiondate' in child_tag:
                            transaction['date'] = child.text
                        elif 'transactioncode' in child_tag:
                            transaction['code'] = child.text
                        elif 'securitytitle' in child_tag:
                            transaction['security'] = child.text
                        elif 'transactionshares' in child_tag:
                            transaction['shares'] = child.text
                        elif 'transactionpricepershare' in child_tag:
                            transaction['price'] = child.text
                        elif 'transactionacquireddisposed' in child_tag:
                            transaction['acquired_disposed'] = child.text
                    
                    if transaction:
                        transactions.append(transaction)
        
        return transactions
    
    def _create_trade_data(self, filer_info: Dict, transaction: Dict, 
                          filing_info: Dict) -> Optional[RawTradeData]:
        """Create RawTradeData from parsed information."""
        
        try:
            # Determine transaction type
            transaction_code = transaction.get('code', '').upper()
            transaction_type = self._map_transaction_code(transaction_code)
            
            if not transaction_type:
                return None
            
            # Parse amounts and dates
            shares = self._parse_float(transaction.get('shares'))
            price = self._parse_float(transaction.get('price'))
            amount_usd = None
            
            if shares and price:
                amount_usd = shares * price
            
            trade_date = self._parse_sec_date(transaction.get('date'))
            filing_date = self._parse_sec_date(filing_info.get('filingDate'))
            
            return RawTradeData(
                source="sec_edgar",
                source_id=filing_info.get('accessionNumber', ''),
                filer_name=filer_info.get('name', ''),
                filer_type="corporate_insider",
                reported_date=filing_date,
                trade_date=trade_date,
                ticker=self._extract_ticker(transaction.get('security', '')),
                company_name=filing_info.get('companyName', ''),
                transaction_type=transaction_type,
                quantity=shares,
                price=price,
                amount_usd=amount_usd,
                insider_relationship=filer_info.get('title', ''),
                filing_url=filing_info.get('url', ''),
                raw_data={
                    'filer_info': filer_info,
                    'transaction': transaction,
                    'filing_info': filing_info
                }
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to create trade data: {e}")
            return None
    
    def _map_transaction_code(self, code: str) -> Optional[str]:
        """Map SEC transaction codes to our standard types."""
        
        code_mapping = {
            'P': 'buy',      # Purchase
            'S': 'sell',     # Sale
            'A': 'buy',      # Grant/Award
            'D': 'sell',     # Disposition
            'F': 'sell',     # Payment of exercise price or tax liability
            'I': 'buy',      # Discretionary transaction
            'M': 'buy',      # Exercise or conversion
            'C': 'sell',     # Conversion
            'E': 'sell',     # Expiration
            'H': 'buy',      # Expiration (short position)
            'O': 'buy',      # Exercise of out-of-the-money option
            'X': 'sell'      # Exercise of in-the-money option
        }
        
        return code_mapping.get(code)
    
    def _extract_ticker(self, security_title: str) -> Optional[str]:
        """Extract ticker symbol from security title."""
        
        if not security_title:
            return None
        
        # Common patterns for tickers in security titles
        ticker_patterns = [
            r'\b([A-Z]{1,5})\b',  # 1-5 uppercase letters
            r'ticker[:\s]+([A-Z]+)',  # "ticker: AAPL"
            r'symbol[:\s]+([A-Z]+)'   # "symbol: AAPL"
        ]
        
        for pattern in ticker_patterns:
            match = re.search(pattern, security_title.upper())
            if match:
                return match.group(1)
        
        return None
    
    def _parse_sec_date(self, date_str: Optional[str]) -> Optional[date]:
        """Parse SEC date format."""
        
        if not date_str:
            return None
        
        try:
            # SEC typically uses YYYY-MM-DD format
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            try:
                # Alternative format
                return datetime.strptime(date_str, "%m/%d/%Y").date()
            except ValueError:
                self.logger.warning(f"Could not parse SEC date: {date_str}")
                return None
    
    def _parse_float(self, value_str: Optional[str]) -> Optional[float]:
        """Parse float value from string."""
        
        if not value_str:
            return None
        
        try:
            # Remove commas and convert to float
            clean_value = re.sub(r'[,\s]', '', str(value_str))
            return float(clean_value)
        except ValueError:
            return None
    
    def _date_range(self, start_date: date, end_date: date) -> Iterator[date]:
        """Generate date range."""
        
        current = start_date
        while current <= end_date:
            yield current
            current += timedelta(days=1)


class SECScraper:
    """Main SEC scraper coordinator."""
    
    def __init__(self):
        self.edgar_scraper = SECEdgarScraper()
        self.logger = self.edgar_scraper.logger
    
    def run_full_ingestion(self, days: int = 7) -> Dict[str, Any]:
        """Run SEC ingestion (shorter default period due to data volume)."""
        
        try:
            self.logger.info(f"Starting SEC ingestion for {days} days")
            result = self.edgar_scraper.run_ingestion(mode="recent", days=days)
            
            # Save trades to database
            self._save_trades_to_db(self.edgar_scraper.fetch_recent_trades(days))
            
            return result
            
        except Exception as e:
            self.logger.error(f"SEC ingestion failed: {e}")
            return {"error": str(e)}
    
    def _save_trades_to_db(self, trades_iter: Iterator[RawTradeData]):
        """Save trades to database."""
        
        with get_session() as session:
            for trade_data in trades_iter:
                try:
                    # Get or create filer
                    filer = self._get_or_create_filer(session, trade_data)
                    
                    # Check if trade already exists
                    existing_trade = session.query(Trade).filter(
                        Trade.source == DataSource.SEC_EDGAR,
                        Trade.source_id == trade_data.source_id
                    ).first()
                    
                    if existing_trade:
                        continue
                    
                    # Create new trade
                    trade = Trade(
                        filer_id=filer.filer_id,
                        source=DataSource.SEC_EDGAR,
                        source_id=trade_data.source_id,
                        reported_date=trade_data.reported_date,
                        trade_date=trade_data.trade_date,
                        ticker=trade_data.ticker,
                        company_name=trade_data.company_name,
                        transaction_type=TransactionType(trade_data.transaction_type)
                            if trade_data.transaction_type in [t.value for t in TransactionType]
                            else TransactionType.BUY,
                        quantity=trade_data.quantity,
                        price=trade_data.price,
                        amount_usd=trade_data.amount_usd,
                        insider_relationship=trade_data.insider_relationship,
                        filing_url=trade_data.filing_url,
                        raw_data=trade_data.raw_data
                    )
                    
                    session.add(trade)
                    
                except Exception as e:
                    self.logger.warning(f"Failed to save SEC trade: {e}")
                    continue
    
    def _get_or_create_filer(self, session, trade_data: RawTradeData) -> Filer:
        """Get or create filer from trade data."""
        
        filer = session.query(Filer).filter(
            Filer.name == trade_data.filer_name,
            Filer.filer_type == FilerType.CORPORATE_INSIDER
        ).first()
        
        if not filer:
            filer = Filer(
                name=trade_data.filer_name,
                filer_type=FilerType.CORPORATE_INSIDER,
                company=trade_data.company_name,
                title=trade_data.insider_relationship
            )
            session.add(filer)
            session.flush()
        
        return filer


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run SEC insider trade scraper")
    parser.add_argument("--days", type=int, default=7,
                       help="Number of days to look back")
    
    args = parser.parse_args()
    
    scraper = SECScraper()
    results = scraper.run_full_ingestion(days=args.days)
    
    print(json.dumps(results, indent=2, default=str))
