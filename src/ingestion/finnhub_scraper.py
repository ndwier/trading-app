"""Finnhub API scraper for congress trading and insider transactions."""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Iterator
from decimal import Decimal

import requests

from config.config import config
from src.database import get_session, Filer, Trade, FilerType, TransactionType, DataSource
from .base import APIIngester, RawTradeData, IngestionError


class FinnhubScraper(APIIngester):
    """Scraper for Finnhub API - congress trading + insider transactions."""
    
    def __init__(self):
        super().__init__(
            name="finnhub",
            base_url=config.api.FINNHUB_BASE_URL,
            api_key=config.api.FINNHUB_API_KEY,
            rate_limit=config.api.FINNHUB_RATE_LIMIT
        )
        
        if not self.api_key:
            self.logger.warning("No Finnhub API key found")
    
    def fetch_recent_trades(self, days: int = 30) -> Iterator[RawTradeData]:
        """Fetch recent trades from Finnhub."""
        
        if not self.api_key:
            self.logger.warning("Skipping Finnhub - no API key")
            return
        
        # Congressional trading requires paid plan
        # Use insider transactions (available on free tier)
        for trade in self._fetch_insider_trades_by_popular_tickers(days):
            yield trade
    
    def _fetch_congress_trades(self, days: int) -> Iterator[RawTradeData]:
        """Fetch congressional trading data."""
        
        # Finnhub congress trading endpoint
        # GET /stock/congressional-trading
        url = f"{self.base_url}/stock/congressional-trading"
        
        # Calculate date range
        to_date = date.today().isoformat()
        from_date = (date.today() - timedelta(days=days)).isoformat()
        
        params = {
            'token': self.api_key,
            'from': from_date,
            'to': to_date
        }
        
        try:
            response = self._make_request(url, params=params)
            data = response.json()
            
            if 'data' not in data:
                self.logger.warning("No congressional data in Finnhub response")
                return
            
            for trade_data in data['data']:
                yield self._parse_congress_trade(trade_data)
                
        except Exception as e:
            self.logger.error(f"Failed to fetch congress trades: {e}")
    
    def _fetch_insider_trades_by_popular_tickers(self, days: int) -> Iterator[RawTradeData]:
        """Fetch insider trades for popular tickers."""
        
        # Popular tickers to fetch (can expand this list)
        popular_tickers = [
            # Mega caps
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA',
            # Tech
            'AMD', 'INTC', 'ORCL', 'CRM', 'ADBE', 'NFLX',
            # Finance
            'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C',
            # Healthcare
            'UNH', 'JNJ', 'PFE', 'ABBV', 'MRK', 'TMO',
            # Consumer
            'WMT', 'HD', 'NKE', 'COST', 'TGT',
            # Defense
            'LMT', 'RTX', 'BA', 'NOC', 'GD'
        ]
        
        for ticker in popular_tickers:
            try:
                url = f"{self.base_url}/stock/insider-transactions"
                params = {
                    'symbol': ticker,
                    'token': self.api_key
                }
                
                response = self._make_request(url, params=params)
                data = response.json()
                
                if not data.get('data'):
                    continue
                
                # Parse insider transactions
                for transaction in data['data']:
                    trade_data = self._parse_insider_transaction(transaction, ticker)
                    if trade_data:
                        # Filter by date
                        from datetime import timedelta
                        if trade_data.trade_date >= (date.today() - timedelta(days=days)):
                            yield trade_data
                
                self.logger.info(f"Fetched {len(data['data'])} insider trades for {ticker}")
                
            except Exception as e:
                self.logger.warning(f"Failed to fetch insider trades for {ticker}: {e}")
                continue
    
    def _parse_insider_transaction(self, data: Dict, ticker: str) -> Optional[RawTradeData]:
        """Parse insider transaction from Finnhub format.
        
        Example:
        {
            "name": "John Smith",
            "share": 1000,
            "change": 1000,
            "filingDate": "2024-10-15",
            "transactionDate": "2024-10-13",
            "transactionCode": "P"
        }
        """
        try:
            name = data.get('name', 'Unknown')
            shares = data.get('change', 0)
            filing_date_str = data.get('filingDate', '')
            trans_date_str = data.get('transactionDate', '')
            trans_code = data.get('transactionCode', '')
            
            # Parse dates
            from datetime import datetime
            filing_date = datetime.strptime(filing_date_str, '%Y-%m-%d').date() if filing_date_str else date.today()
            trans_date = datetime.strptime(trans_date_str, '%Y-%m-%d').date() if trans_date_str else filing_date
            
            # Parse transaction type
            # P = Purchase, S = Sale, A = Award, M = Option Exercise
            if trans_code == 'P':
                transaction_type = 'BUY'
            elif trans_code == 'S':
                transaction_type = 'SELL'
            elif trans_code == 'A':
                transaction_type = 'AWARD'
            elif trans_code == 'M':
                transaction_type = 'OPTION_EXERCISE'
            else:
                transaction_type = 'OTHER'
            
            # Calculate approximate value (we don't have price, so estimate)
            value = abs(shares) * 100  # Rough estimate
            
            return RawTradeData(
                source="finnhub",
                source_id=f"fh_insider_{ticker}_{name}_{trans_date}_{shares}",
                reported_date=filing_date,
                trade_date=trans_date,
                ticker=ticker,
                company_name="",
                filer_name=name,
                filer_type=FilerType.CORPORATE_INSIDER.value,
                transaction_type=transaction_type,
                quantity=abs(shares),
                amount_usd=value,
                raw_data={
                    "source": "finnhub",
                    "transaction_code": trans_code,
                    "original_data": data
                }
            )
            
        except Exception as e:
            self.logger.warning(f"Failed to parse insider transaction: {e}")
            return None
    
    def _parse_congress_trade(self, data: Dict) -> RawTradeData:
        """Parse congressional trade from Finnhub format.
        
        Example format:
        {
            "firstName": "Nancy",
            "lastName": "Pelosi",
            "ticker": "NVDA",
            "transactionDate": "2024-10-15",
            "transactionType": "purchase",
            "amount": 500000,
            "house": "H",
            "link": "https://..."
        }
        """
        
        # Extract data
        first_name = data.get('firstName', '')
        last_name = data.get('lastName', '')
        full_name = f"{first_name} {last_name}".strip()
        
        ticker = data.get('ticker', '').upper()
        trans_date_str = data.get('transactionDate', '')
        trans_type = data.get('transactionType', '').lower()
        amount = data.get('amount', 0)
        house = data.get('house', '')  # 'H' for House, 'S' for Senate
        filing_link = data.get('link', '')
        
        # Parse date
        try:
            trans_date = datetime.strptime(trans_date_str, '%Y-%m-%d').date()
        except:
            trans_date = date.today()
        
        # Parse transaction type
        if 'purchase' in trans_type or 'buy' in trans_type:
            transaction_type = 'BUY'
        elif 'sale' in trans_type or 'sell' in trans_type:
            transaction_type = 'SELL'
        else:
            transaction_type = 'OTHER'
        
        # Determine chamber
        chamber = 'House' if house == 'H' else 'Senate' if house == 'S' else 'Unknown'
        
        return RawTradeData(
            source="finnhub",
            source_id=f"fh_congress_{full_name}_{ticker}_{trans_date}_{amount}",
            reported_date=trans_date,  # Finnhub doesn't separate filing vs trade date
            trade_date=trans_date,
            ticker=ticker,
            company_name="",
            filer_name=full_name,
            filer_type=FilerType.POLITICIAN.value,
            transaction_type=transaction_type,
            amount_usd=amount,
            raw_data={
                "source": "finnhub",
                "house": house,
                "chamber": chamber,
                "filing_link": filing_link
            }
        )
    
    def fetch_historical_trades(self, start_date: date, end_date: date) -> Iterator[RawTradeData]:
        """Fetch historical trades."""
        days = (end_date - start_date).days
        return self.fetch_recent_trades(days)
    
    def fetch_filer_trades(self, filer_name: str) -> Iterator[RawTradeData]:
        """Fetch trades for specific filer (not easily supported)."""
        return iter([])
    
    def run_ingestion(self, mode: str = "recent", days: int = 30, **kwargs) -> Dict:
        """Run Finnhub ingestion."""
        
        start_time = datetime.now()
        self.logger.info(f"Starting {self.name} ingestion in {mode} mode")
        
        if not self.api_key:
            self.logger.error("No Finnhub API key - skipping")
            return {"error": "No API key"}
        
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
            raise IngestionError(f"Finnhub ingestion failed: {e}")
    
    def _save_trade(self, trade_data: RawTradeData):
        """Save trade to database."""
        
        with get_session() as session:
            # Get or create filer
            filer = session.query(Filer).filter(Filer.name == trade_data.filer_name).first()
            
            if not filer:
                filer = Filer(
                    name=trade_data.filer_name,
                    filer_type=FilerType.POLITICIAN,
                    chamber=trade_data.raw_data.get('chamber', 'Unknown')
                )
                session.add(filer)
                session.flush()
            
            # Check if trade exists
            existing = session.query(Trade).filter(
                Trade.source == DataSource.FINNHUB,
                Trade.source_id == trade_data.source_id
            ).first()
            
            if existing:
                return
            
            # Create trade
            trade = Trade(
                filer_id=filer.filer_id,
                source=DataSource.FINNHUB,
                source_id=trade_data.source_id,
                reported_date=trade_data.reported_date,
                trade_date=trade_data.trade_date,
                ticker=trade_data.ticker,
                company_name=trade_data.company_name,
                transaction_type=TransactionType[trade_data.transaction_type],
                amount_usd=Decimal(str(trade_data.amount_usd)) if trade_data.amount_usd else None,
                filing_url=trade_data.raw_data.get('filing_link'),
                raw_data=trade_data.raw_data
            )
            
            session.add(trade)
            session.commit()


# Helper function for testing
def main():
    """Test Finnhub scraper."""
    logging.basicConfig(level=logging.INFO)
    
    scraper = FinnhubScraper()
    
    if not scraper.api_key:
        print("❌ No Finnhub API key found!")
        print("   Sign up at: https://finnhub.io/register")
        print("   Add to .env: FINNHUB_API_KEY=your_key")
        return
    
    result = scraper.run_ingestion(mode="recent", days=30)
    
    print(f"\n✅ Finnhub Ingestion Complete:")
    print(f"   Trades collected: {result.get('trades_collected', 0)}")
    print(f"   Trades processed: {result.get('trades_processed', 0)}")
    print(f"   Runtime: {result.get('runtime_seconds', 0):.1f}s")


if __name__ == "__main__":
    main()

