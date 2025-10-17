"""SEC 13F filings scraper for institutional holdings (hedge funds, billionaires)."""

import logging
import re
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Iterator
from decimal import Decimal
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

from config.config import config
from src.database import get_session, Filer, Trade, FilerType, TransactionType, DataSource
from .base import ScrapingIngester, RawTradeData, IngestionError


class SEC13FScraper(ScrapingIngester):
    """Scraper for SEC 13F filings - institutional investment managers with >$100M AUM."""
    
    def __init__(self):
        super().__init__(
            name="sec_13f",
            base_url=config.api.SEC_EDGAR_BASE_URL
        )
        self.session.headers.update(config.api.SEC_HEADERS)
        
        # Notable institutional investors to track
        self.tracked_institutions = {
            # Billionaire investors
            'BERKSHIRE HATHAWAY': '0001067983',  # Warren Buffett
            'BRIDGEWATER ASSOCIATES': '0001350694',  # Ray Dalio
            'BILL & MELINDA GATES FOUNDATION': '0001166559',
            'SOROS FUND MANAGEMENT': '0001029160',  # George Soros
            'PERSHING SQUARE': '0001336528',  # Bill Ackman
            'BAUPOST GROUP': '0001061768',  # Seth Klarman
            'APPALOOSA': '0001582982',  # David Tepper
            'TIGER GLOBAL': '0001167483',
            'RENAISSANCE TECHNOLOGIES': '0001037389',  # Jim Simons
            'CITADEL': '0001423053',  # Ken Griffin
            
            # Major hedge funds
            'THIRD POINT': '0001040273',  # Dan Loeb
            'GREENLIGHT CAPITAL': '0001079114',  # David Einhorn
            'VIKING GLOBAL': '0001103804',
            'LONE PINE CAPITAL': '0001061165',
            'MILLENNIUM MANAGEMENT': '0001099191',
            'TWO SIGMA': '0001582961',
            'POINT72': '0001603466',  # Steve Cohen
            
            # Major institutions
            'VANGUARD GROUP': '0000102909',
            'BLACKROCK': '0001086364',
            'STATE STREET': '0000093751',
            'FIDELITY': '0000315066',
        }
    
    def fetch_recent_trades(self, days: int = 90) -> Iterator[RawTradeData]:
        """Fetch recent 13F filings.
        
        Note: 13F filings are quarterly, so 'days' should be 90+ for meaningful data.
        """
        
        # 13F filings are quarterly, get last 2 quarters
        for name, cik in list(self.tracked_institutions.items())[:5]:  # Start with top 5
            try:
                self.logger.info(f"Fetching 13F for {name} (CIK: {cik})")
                filings = self._get_recent_13f_filings(cik, count=2)
                
                for filing in filings:
                    holdings = self._parse_13f_filing(filing)
                    
                    for holding in holdings:
                        yield self._create_trade_from_holding(holding, name, filing)
                        
            except Exception as e:
                self.logger.warning(f"Failed to process {name}: {e}")
                continue
    
    def fetch_historical_trades(self, start_date: date, end_date: date) -> Iterator[RawTradeData]:
        """Fetch historical 13F filings."""
        # 13F filings are quarterly, so date range should span quarters
        for name, cik in self.tracked_institutions.items():
            try:
                filings = self._get_13f_filings_in_range(cik, start_date, end_date)
                
                for filing in filings:
                    holdings = self._parse_13f_filing(filing)
                    
                    for holding in holdings:
                        yield self._create_trade_from_holding(holding, name, filing)
                        
            except Exception as e:
                self.logger.warning(f"Failed to process {name}: {e}")
                continue
    
    def fetch_filer_trades(self, filer_name: str) -> Iterator[RawTradeData]:
        """Fetch 13F filings for specific institution."""
        # Search for CIK by name
        cik = self._search_cik_by_name(filer_name)
        if not cik:
            self.logger.warning(f"Could not find CIK for {filer_name}")
            return
        
        filings = self._get_recent_13f_filings(cik, count=4)
        
        for filing in filings:
            holdings = self._parse_13f_filing(filing)
            
            for holding in holdings:
                yield self._create_trade_from_holding(holding, filer_name, filing)
    
    def _get_recent_13f_filings(self, cik: str, count: int = 2) -> List[Dict]:
        """Get recent 13F-HR filings for a CIK."""
        
        # Use SEC EDGAR submissions API (more reliable)
        # Format: https://data.sec.gov/submissions/CIK##########.json
        cik_padded = cik.zfill(10)  # Pad to 10 digits
        url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
        
        try:
            response = self._make_request(url)
            data = response.json()
            
            # Find 13F-HR filings
            filings = []
            recent_filings = data.get('filings', {}).get('recent', {})
            
            forms = recent_filings.get('form', [])
            accession_numbers = recent_filings.get('accessionNumber', [])
            filing_dates = recent_filings.get('filingDate', [])
            primary_docs = recent_filings.get('primaryDocument', [])
            
            for i, form in enumerate(forms):
                if form == '13F-HR' and len(filings) < count:
                    accession = accession_numbers[i].replace('-', '')
                    filing_date = filing_dates[i] if i < len(filing_dates) else None
                    primary_doc = primary_docs[i] if i < len(primary_docs) else 'primary_doc.xml'
                    
                    # Construct filing URL
                    filing_url = f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={cik_padded}&accession_number={accession_numbers[i]}&xbrl_type=v"
                    
                    filings.append({
                        'url': filing_url,
                        'date': filing_date,
                        'accession': accession_numbers[i],
                        'cik': cik_padded
                    })
            
            return filings
            
        except Exception as e:
            self.logger.error(f"Failed to get 13F filings for {cik}: {e}")
            return []
    
    def _get_13f_filings_in_range(self, cik: str, start_date: date, end_date: date) -> List[Dict]:
        """Get 13F filings within date range."""
        # For simplicity, get recent filings (would need more complex logic for full date range)
        quarters_back = ((end_date.year - start_date.year) * 4 + 
                        (end_date.month - start_date.month) // 3)
        
        return self._get_recent_13f_filings(cik, count=max(quarters_back, 1))
    
    def _parse_13f_filing(self, filing: Dict) -> List[Dict]:
        """Parse 13F-HR filing to extract holdings.
        
        13F filings contain a table of all holdings >$200k or 10k shares.
        """
        
        holdings = []
        
        try:
            # Get the filing page
            response = self._make_request(filing['url'])
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find the information table (primary document)
            # Look for .xml or .txt files containing holdings
            doc_links = soup.find_all('a', href=re.compile(r'\.xml$|primary_doc\.xml'))
            
            if not doc_links:
                # Try alternate format
                doc_links = soup.find_all('a', href=re.compile(r'form13fInfoTable\.xml'))
            
            if doc_links:
                # Parse the information table XML
                doc_url = filing['url'].rsplit('/', 1)[0] + '/' + doc_links[0]['href']
                holdings = self._parse_13f_info_table(doc_url)
            
        except Exception as e:
            self.logger.warning(f"Failed to parse 13F filing: {e}")
        
        return holdings
    
    def _parse_13f_info_table(self, url: str) -> List[Dict]:
        """Parse 13F information table XML."""
        
        holdings = []
        
        try:
            response = self._make_request(url)
            root = ET.fromstring(response.text)
            
            # Find all info table entries
            # XML structure varies, but typically has infoTable elements
            for entry in root.findall('.//{http://www.sec.gov/edgar/document/thirteenf/informationtable}infoTable'):
                holding = {}
                
                # Extract security name and ticker
                name_elem = entry.find('.//{http://www.sec.gov/edgar/document/thirteenf/informationtable}nameOfIssuer')
                ticker_elem = entry.find('.//{http://www.sec.gov/edgar/document/thirteenf/informationtable}titleOfClass')
                
                # Extract position details
                shares_elem = entry.find('.//{http://www.sec.gov/edgar/document/thirteenf/informationtable}sshPrnamt')
                value_elem = entry.find('.//{http://www.sec.gov/edgar/document/thirteenf/informationtable}value')
                
                if name_elem is not None and shares_elem is not None:
                    holding = {
                        'name': name_elem.text,
                        'ticker': ticker_elem.text if ticker_elem is not None else '',
                        'shares': int(shares_elem.text) if shares_elem.text else 0,
                        'value': int(value_elem.text) * 1000 if value_elem is not None and value_elem.text else 0  # Value in thousands
                    }
                    holdings.append(holding)
            
            # Try alternate XML structure (older format)
            if not holdings:
                for entry in root.findall('.//infoTable'):
                    name_elem = entry.find('.//nameOfIssuer')
                    shares_elem = entry.find('.//sshPrnamt')
                    value_elem = entry.find('.//value')
                    
                    if name_elem is not None and shares_elem is not None:
                        holdings.append({
                            'name': name_elem.text,
                            'ticker': '',
                            'shares': int(shares_elem.text),
                            'value': int(value_elem.text) * 1000 if value_elem is not None else 0
                        })
            
        except Exception as e:
            self.logger.error(f"Failed to parse info table: {e}")
        
        return holdings
    
    def _create_trade_from_holding(self, holding: Dict, institution: str, filing: Dict) -> RawTradeData:
        """Create trade data from 13F holding.
        
        Note: 13F shows current holdings, not transactions. We infer "BUY" as position.
        """
        
        # Parse filing date
        filing_date_str = filing.get('date', '')
        try:
            filing_date = datetime.fromisoformat(filing_date_str.replace('Z', '+00:00')).date()
        except:
            filing_date = date.today()
        
        # Clean up ticker (often includes security type like "COM", "CL A", etc.)
        ticker = holding.get('ticker', '')
        ticker = re.sub(r'\s+(COM|CL [A-Z]|SHS).*', '', ticker).strip()
        
        # Try to extract ticker from name if not available
        if not ticker:
            # Common pattern: "COMPANY NAME (TICKER)"
            match = re.search(r'\(([A-Z]{1,5})\)', holding['name'])
            if match:
                ticker = match.group(1)
        
        return RawTradeData(
            source="sec_13f",
            source_id=f"13f_{institution}_{ticker}_{filing_date}_{holding['shares']}",
            reported_date=filing_date,
            trade_date=filing_date,  # 13F shows holdings as of quarter end
            ticker=ticker.upper() if ticker else holding['name'][:10].upper(),
            company_name=holding['name'],
            filer_name=institution,
            filer_type=FilerType.HEDGE_FUND.value,
            transaction_type='BUY',  # 13F shows holdings, we treat as position
            quantity=holding['shares'],
            amount_usd=holding['value'],
            raw_data={
                'source': 'sec_13f',
                'filing_url': filing['url'],
                'quarter_end': filing_date.isoformat()
            }
        )
    
    def _search_cik_by_name(self, name: str) -> Optional[str]:
        """Search for CIK by institution name."""
        # Check if in our tracked list first
        for inst_name, cik in self.tracked_institutions.items():
            if name.upper() in inst_name.upper() or inst_name.upper() in name.upper():
                return cik
        
        # Could implement SEC company search here if needed
        return None
    
    def run_ingestion(self, mode: str = "recent", days: int = 90, **kwargs) -> Dict:
        """Run 13F ingestion."""
        
        start_time = datetime.now()
        self.logger.info(f"Starting {self.name} ingestion (quarterly filings)")
        
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
            
            self.logger.info(f"Ingestion completed: {trades_collected}/{trades_processed} holdings collected in {runtime:.1f} seconds")
            
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
            raise IngestionError(f"13F ingestion failed: {e}")
    
    def _save_trade(self, trade_data: RawTradeData):
        """Save 13F holding to database as institutional position."""
        
        with get_session() as session:
            # Get or create filer
            filer = session.query(Filer).filter(Filer.name == trade_data.filer_name).first()
            
            if not filer:
                filer = Filer(
                    name=trade_data.filer_name,
                    filer_type=FilerType.HEDGE_FUND
                )
                session.add(filer)
                session.flush()
            
            # Check if holding exists
            existing = session.query(Trade).filter(
                Trade.source == DataSource.SEC_EDGAR,
                Trade.source_id == trade_data.source_id
            ).first()
            
            if existing:
                return
            
            # Create trade
            trade = Trade(
                filer_id=filer.filer_id,
                source=DataSource.SEC_EDGAR,
                source_id=trade_data.source_id,
                reported_date=trade_data.reported_date,
                trade_date=trade_data.trade_date,
                ticker=trade_data.ticker,
                company_name=trade_data.company_name,
                transaction_type=TransactionType.BUY,
                quantity=Decimal(str(trade_data.quantity)) if trade_data.quantity else None,
                amount_usd=Decimal(str(trade_data.amount_usd)) if trade_data.amount_usd else None,
                filing_url=trade_data.raw_data.get('filing_url'),
                raw_data=trade_data.raw_data
            )
            
            session.add(trade)
            session.commit()


# Test function
def main():
    """Test 13F scraper."""
    logging.basicConfig(level=logging.INFO)
    
    scraper = SEC13FScraper()
    result = scraper.run_ingestion(mode="recent", days=90)
    
    print(f"\n✅ 13F Ingestion Complete:")
    print(f"   Holdings collected: {result.get('trades_collected', 0)}")
    print(f"   Holdings processed: {result.get('trades_processed', 0)}")
    print(f"   Runtime: {result.get('runtime_seconds', 0):.1f}s")


if __name__ == "__main__":
    main()

