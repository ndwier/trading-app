"""Price data API integrations (Alpha Vantage, Tiingo, Polygon)."""

import logging
from datetime import datetime, date
from typing import Dict, List, Optional
from decimal import Decimal

import requests

from config.config import config


class AlphaVantageAPI:
    """Alpha Vantage API for stock prices and fundamentals."""
    
    def __init__(self):
        self.api_key = config.api.ALPHA_VANTAGE_API_KEY
        self.base_url = config.api.ALPHA_VANTAGE_BASE_URL
        self.logger = logging.getLogger("alphavantage")
        
    def get_daily_prices(self, ticker: str, outputsize: str = "compact") -> Dict:
        """Get daily prices for a ticker."""
        if not self.api_key:
            self.logger.warning("No Alpha Vantage API key")
            return {}
        
        params = {
            'function': 'TIME_SERIES_DAILY_ADJUSTED',
            'symbol': ticker,
            'outputsize': outputsize,  # compact = 100 days, full = 20+ years
            'apikey': self.api_key
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch {ticker}: {e}")
            return {}


class TiingoAPI:
    """Tiingo API for reliable EOD prices."""
    
    def __init__(self):
        self.api_key = config.api.TIINGO_API_KEY
        self.base_url = config.api.TIINGO_BASE_URL
        self.logger = logging.getLogger("tiingo")
        
    def get_daily_prices(self, ticker: str, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Get daily prices for a ticker."""
        if not self.api_key:
            self.logger.warning("No Tiingo API key")
            return []
        
        url = f"{self.base_url}/tiingo/daily/{ticker}/prices"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Token {self.api_key}'
        }
        
        params = {}
        if start_date:
            params['startDate'] = start_date
        if end_date:
            params['endDate'] = end_date
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch {ticker}: {e}")
            return []


class PolygonAPI:
    """Polygon.io API for market data and news."""
    
    def __init__(self):
        self.api_key = config.api.POLYGON_API_KEY
        self.base_url = config.api.POLYGON_BASE_URL
        self.logger = logging.getLogger("polygon")
        
    def get_daily_prices(self, ticker: str, from_date: str, to_date: str) -> Dict:
        """Get daily prices (aggregates)."""
        if not self.api_key:
            self.logger.warning("No Polygon API key")
            return {}
        
        url = f"{self.base_url}/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
        params = {'apiKey': self.api_key}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch {ticker}: {e}")
            return {}
    
    def get_ticker_news(self, ticker: str, limit: int = 10) -> List[Dict]:
        """Get news for a ticker."""
        if not self.api_key:
            return []
        
        url = f"{self.base_url}/v2/reference/news"
        params = {
            'ticker': ticker,
            'limit': limit,
            'apiKey': self.api_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            return data.get('results', [])
        except Exception as e:
            self.logger.error(f"Failed to fetch news for {ticker}: {e}")
            return []


# Test function
def main():
    """Test price APIs."""
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Price Data APIs...\n")
    
    # Alpha Vantage
    av = AlphaVantageAPI()
    if av.api_key:
        print("✅ Alpha Vantage: API key found")
        data = av.get_daily_prices("NVDA")
        if data:
            print(f"   Sample data: {list(data.keys())[:3]}")
    else:
        print("❌ Alpha Vantage: No API key")
        print("   Sign up: https://www.alphavantage.co/support/#api-key")
    
    # Tiingo  
    tiingo = TiingoAPI()
    if tiingo.api_key:
        print("\n✅ Tiingo: API key found")
        data = tiingo.get_daily_prices("NVDA")
        if data:
            print(f"   Got {len(data)} data points")
    else:
        print("\n❌ Tiingo: No API key")
        print("   Sign up: https://www.tiingo.com")
    
    # Polygon
    poly = PolygonAPI()
    if poly.api_key:
        print("\n✅ Polygon.io: API key found")
        data = poly.get_daily_prices("NVDA", "2024-10-01", "2024-10-17")
        if data.get('results'):
            print(f"   Got {len(data['results'])} data points")
    else:
        print("\n❌ Polygon.io: No API key")
        print("   Sign up: https://polygon.io")


if __name__ == "__main__":
    main()

