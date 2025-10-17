"""Additional institutional data APIs: WhaleWisdom, Quandl, Options Flow."""

import logging
from datetime import datetime, date
from typing import Dict, List, Optional

import requests

from config.config import config


class WhaleWisdomAPI:
    """WhaleWisdom API for institutional holdings and 13F data."""
    
    def __init__(self):
        # WhaleWisdom requires paid subscription
        # Add support for when user gets API key
        self.api_key = config.api.__dict__.get('WHALE_WISDOM_API_KEY')
        self.base_url = "https://whalewisdom.com/api"
        self.logger = logging.getLogger("whalewisdom")
        
    def get_institution_holdings(self, institution_id: str) -> Dict:
        """Get current holdings for an institution."""
        if not self.api_key:
            self.logger.warning("No WhaleWisdom API key")
            return {}
        
        url = f"{self.base_url}/institution/{institution_id}/holdings"
        headers = {'Authorization': f'Bearer {self.api_key}'}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch holdings: {e}")
            return {}
    
    def get_stock_holders(self, ticker: str) -> Dict:
        """Get institutional holders of a stock."""
        if not self.api_key:
            return {}
        
        url = f"{self.base_url}/stock/{ticker}/holders"
        headers = {'Authorization': f'Bearer {self.api_key}'}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch holders: {e}")
            return {}
    
    def search_institutions(self, query: str) -> List[Dict]:
        """Search for institutions."""
        if not self.api_key:
            return []
        
        url = f"{self.base_url}/search/institutions"
        headers = {'Authorization': f'Bearer {self.api_key}'}
        params = {'q': query}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            return data.get('results', [])
        except Exception as e:
            self.logger.error(f"Failed to search institutions: {e}")
            return []


class QuandlAPI:
    """Quandl API for financial and economic data."""
    
    def __init__(self):
        self.api_key = config.api.__dict__.get('QUANDL_API_KEY')
        self.base_url = "https://data.nasdaq.com/api/v3"
        self.logger = logging.getLogger("quandl")
        
    def get_dataset(self, database: str, dataset: str, **params) -> Dict:
        """Get a Quandl dataset.
        
        Examples:
        - database='WIKI', dataset='AAPL' - Stock prices
        - database='SF1', dataset='AAPL_MARKETCAP_MRQ' - Fundamentals
        """
        if not self.api_key:
            self.logger.warning("No Quandl API key")
            return {}
        
        url = f"{self.base_url}/datasets/{database}/{dataset}/data.json"
        params['api_key'] = self.api_key
        
        try:
            response = requests.get(url, params=params, timeout=10)
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch dataset: {e}")
            return {}
    
    def get_institutional_ownership(self, ticker: str) -> Dict:
        """Get institutional ownership data if available."""
        # Quandl has various institutional datasets depending on subscription
        # Example: SF1 database has institutional holdings
        return self.get_dataset('SF1', f'{ticker}_INSTOWN_MRQ')
    
    def search_datasets(self, query: str) -> List[Dict]:
        """Search for datasets."""
        if not self.api_key:
            return []
        
        url = f"{self.base_url}/datasets.json"
        params = {'query': query, 'api_key': self.api_key}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            return data.get('datasets', [])
        except Exception as e:
            self.logger.error(f"Failed to search datasets: {e}")
            return []


class OptionsFlowAPI:
    """Options flow data API (Unusual Whales, FlowAlgo, etc.)."""
    
    def __init__(self):
        # Support for Unusual Whales or similar
        self.uw_api_key = config.api.__dict__.get('UNUSUAL_WHALES_API_KEY')
        self.uw_base_url = "https://api.unusualwhales.com"
        
        self.flowalgo_key = config.api.__dict__.get('FLOWALGO_API_KEY')
        self.flowalgo_url = "https://api.flowalgo.com"
        
        self.logger = logging.getLogger("options_flow")
        
    def get_unusual_options(self, ticker: str = None, limit: int = 100) -> List[Dict]:
        """Get unusual options activity."""
        
        # Try Unusual Whales first
        if self.uw_api_key:
            return self._get_uw_unusual_options(ticker, limit)
        
        # Try FlowAlgo
        if self.flowalgo_key:
            return self._get_flowalgo_options(ticker, limit)
        
        self.logger.warning("No options flow API key configured")
        return []
    
    def _get_uw_unusual_options(self, ticker: str = None, limit: int = 100) -> List[Dict]:
        """Get options from Unusual Whales."""
        
        url = f"{self.uw_base_url}/api/options/flow"
        headers = {'Authorization': f'Bearer {self.uw_api_key}'}
        params = {'limit': limit}
        
        if ticker:
            params['ticker'] = ticker
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            return data.get('data', [])
        except Exception as e:
            self.logger.error(f"Failed to fetch UW options: {e}")
            return []
    
    def _get_flowalgo_options(self, ticker: str = None, limit: int = 100) -> List[Dict]:
        """Get options from FlowAlgo."""
        
        url = f"{self.flowalgo_url}/v1/flow"
        headers = {'X-API-KEY': self.flowalgo_key}
        params = {'limit': limit}
        
        if ticker:
            params['ticker'] = ticker
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch FlowAlgo options: {e}")
            return []
    
    def get_dark_pool_trades(self, ticker: str = None) -> List[Dict]:
        """Get dark pool trading data (if available)."""
        
        if not self.uw_api_key:
            return []
        
        url = f"{self.uw_base_url}/api/darkpool"
        headers = {'Authorization': f'Bearer {self.uw_api_key}'}
        params = {}
        
        if ticker:
            params['ticker'] = ticker
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            data = response.json()
            return data.get('data', [])
        except Exception as e:
            self.logger.error(f"Failed to fetch dark pool data: {e}")
            return []
    
    def get_congress_trades(self) -> List[Dict]:
        """Get congressional trades from Unusual Whales (if subscribed)."""
        
        if not self.uw_api_key:
            return []
        
        url = f"{self.uw_base_url}/api/congress"
        headers = {'Authorization': f'Bearer {self.uw_api_key}'}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            data = response.json()
            return data.get('data', [])
        except Exception as e:
            self.logger.error(f"Failed to fetch congress trades: {e}")
            return []


# Test function
def main():
    """Test institutional APIs."""
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Institutional Data APIs...\n")
    
    # WhaleWisdom
    ww = WhaleWisdomAPI()
    if ww.api_key:
        print("✅ WhaleWisdom: API key found")
    else:
        print("❌ WhaleWisdom: No API key (paid service)")
        print("   https://whalewisdom.com/api")
    
    # Quandl
    quandl = QuandlAPI()
    if quandl.api_key:
        print("\n✅ Quandl: API key found")
        # Test search
        results = quandl.search_datasets("institutional ownership")
        if results:
            print(f"   Found {len(results)} datasets")
    else:
        print("\n❌ Quandl: No API key")
        print("   https://data.nasdaq.com/ (Quandl)")
    
    # Options Flow
    options = OptionsFlowAPI()
    if options.uw_api_key:
        print("\n✅ Unusual Whales: API key found")
        print("   Can access: Options flow, Dark pool, Congress trades")
    elif options.flowalgo_key:
        print("\n✅ FlowAlgo: API key found")
    else:
        print("\n❌ Options Flow: No API keys")
        print("   Options:")
        print("   - Unusual Whales: https://unusualwhales.com/")
        print("   - FlowAlgo: https://www.flowalgo.com/")
    
    print("\n💡 To enable these services:")
    print("   1. Sign up for the service(s) you want")
    print("   2. Add API keys to .env:")
    print("      WHALE_WISDOM_API_KEY=your_key")
    print("      QUANDL_API_KEY=your_key")
    print("      UNUSUAL_WHALES_API_KEY=your_key")


if __name__ == "__main__":
    main()

