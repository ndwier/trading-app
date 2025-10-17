"""Enrichment API integrations (OpenSecrets, GovTrack, FRED)."""

import logging
from typing import Dict, List, Optional

import requests

from config.config import config


class OpenSecretsAPI:
    """OpenSecrets API for political donations and lobbying data."""
    
    def __init__(self):
        self.api_key = config.api.OPENSECRETS_API_KEY
        self.base_url = config.api.OPENSECRETS_BASE_URL
        self.logger = logging.getLogger("opensecrets")
        
    def get_legislator_summary(self, cid: str) -> Dict:
        """Get summary data for a legislator by CID."""
        if not self.api_key:
            return {}
        
        params = {
            'method': 'candSummary',
            'cid': cid,
            'apikey': self.api_key,
            'output': 'json'
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch legislator {cid}: {e}")
            return {}
    
    def get_legislator_contributors(self, cid: str, cycle: str = "2024") -> Dict:
        """Get top contributors for a legislator."""
        if not self.api_key:
            return {}
        
        params = {
            'method': 'candContrib',
            'cid': cid,
            'cycle': cycle,
            'apikey': self.api_key,
            'output': 'json'
        }
        
        try:
            response = requests.get(self.base_url, params=params, timeout=10)
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch contributors for {cid}: {e}")
            return {}


class GovTrackAPI:
    """GovTrack API for legislative activity."""
    
    def __init__(self):
        self.base_url = config.api.GOVTRACK_BASE_URL
        self.logger = logging.getLogger("govtrack")
        
    def get_legislator(self, name: str = None, state: str = None) -> List[Dict]:
        """Search for legislators."""
        params = {}
        if name:
            params['name__contains'] = name
        if state:
            params['state'] = state
        
        url = f"{self.base_url}/person"
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            return data.get('objects', [])
        except Exception as e:
            self.logger.error(f"Failed to search legislators: {e}")
            return []
    
    def get_recent_bills(self, sponsor_id: int = None, limit: int = 20) -> List[Dict]:
        """Get recent bills, optionally by sponsor."""
        params = {'limit': limit, 'order_by': '-introduced_date'}
        if sponsor_id:
            params['sponsor'] = sponsor_id
        
        url = f"{self.base_url}/bill"
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            return data.get('objects', [])
        except Exception as e:
            self.logger.error(f"Failed to fetch bills: {e}")
            return []
    
    def get_legislator_committees(self, person_id: int) -> List[Dict]:
        """Get committees for a legislator."""
        url = f"{self.base_url}/role"
        params = {'current': 'true', 'person': person_id}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            roles = data.get('objects', [])
            
            # Extract committee info
            committees = []
            for role in roles:
                if role.get('committee'):
                    committees.append({
                        'name': role['committee'].get('name'),
                        'type': role.get('role_type'),
                        'leadership': role.get('leadership_title')
                    })
            
            return committees
        except Exception as e:
            self.logger.error(f"Failed to fetch committees: {e}")
            return []


class FREDAPI:
    """FRED (Federal Reserve Economic Data) API."""
    
    def __init__(self):
        self.api_key = config.api.FRED_API_KEY
        self.base_url = config.api.FRED_BASE_URL
        self.logger = logging.getLogger("fred")
        
    def get_series(self, series_id: str, observation_start: str = None) -> Dict:
        """Get economic series data.
        
        Common series:
        - DFF: Federal Funds Rate
        - GDP: Gross Domestic Product
        - UNRATE: Unemployment Rate
        - CPIAUCSL: Consumer Price Index
        - SP500: S&P 500
        """
        if not self.api_key:
            return {}
        
        url = f"{self.base_url}/series/observations"
        params = {
            'series_id': series_id,
            'api_key': self.api_key,
            'file_type': 'json'
        }
        
        if observation_start:
            params['observation_start'] = observation_start
        
        try:
            response = requests.get(url, params=params, timeout=10)
            return response.json()
        except Exception as e:
            self.logger.error(f"Failed to fetch series {series_id}: {e}")
            return {}


# Test function
def main():
    """Test enrichment APIs."""
    logging.basicConfig(level=logging.INFO)
    
    print("Testing Enrichment APIs...\n")
    
    # OpenSecrets
    os_api = OpenSecretsAPI()
    if os_api.api_key:
        print("✅ OpenSecrets: API key found")
    else:
        print("❌ OpenSecrets: No API key")
        print("   Sign up: https://www.opensecrets.org/open-data/api")
    
    # GovTrack (no key needed)
    gt_api = GovTrackAPI()
    print("\n✅ GovTrack: No API key needed (free)")
    legislators = gt_api.get_legislator(name="Pelosi")
    if legislators:
        print(f"   Found {len(legislators)} legislators named Pelosi")
        if legislators[0].get('id'):
            committees = gt_api.get_legislator_committees(legislators[0]['id'])
            print(f"   Committees: {len(committees)}")
    
    # FRED
    fred = FREDAPI()
    if fred.api_key:
        print("\n✅ FRED: API key found")
        data = fred.get_series('DFF')  # Federal Funds Rate
        if data.get('observations'):
            print(f"   Got {len(data['observations'])} observations")
    else:
        print("\n❌ FRED: No API key")
        print("   Sign up: https://fred.stlouisfed.org/docs/api/api_key.html")


if __name__ == "__main__":
    main()

