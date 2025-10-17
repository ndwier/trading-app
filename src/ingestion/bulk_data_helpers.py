"""Helpers for importing bulk historical data from Kaggle, Data.gov, GitHub repos."""

import logging
import os
import zipfile
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import requests
import pandas as pd

from config.config import config


class KaggleDatasetImporter:
    """Import datasets from Kaggle."""
    
    def __init__(self):
        self.logger = logging.getLogger("kaggle_importer")
        self.kaggle_username = os.getenv('KAGGLE_USERNAME')
        self.kaggle_key = os.getenv('KAGGLE_KEY')
        
        # Setup kaggle API if credentials exist
        if self.kaggle_username and self.kaggle_key:
            self._setup_kaggle_credentials()
    
    def _setup_kaggle_credentials(self):
        """Setup Kaggle API credentials."""
        kaggle_dir = Path.home() / '.kaggle'
        kaggle_dir.mkdir(exist_ok=True)
        
        creds_file = kaggle_dir / 'kaggle.json'
        creds = {
            'username': self.kaggle_username,
            'key': self.kaggle_key
        }
        
        with open(creds_file, 'w') as f:
            json.dump(creds, f)
        
        creds_file.chmod(0o600)
    
    def download_dataset(self, dataset: str, output_dir: str = 'data/kaggle') -> Path:
        """Download a Kaggle dataset.
        
        Args:
            dataset: Dataset identifier (e.g., 'username/dataset-name')
            output_dir: Where to save the downloaded data
        
        Example datasets:
        - 'nelgiriyewithana/most-traded-stocks-by-congress-members'
        - 'unanimad/us-election-2020'
        - 'stefanoleone992/mutual-funds-and-etfs'
        """
        
        if not self.kaggle_username or not self.kaggle_key:
            self.logger.error("Kaggle credentials not found. Set KAGGLE_USERNAME and KAGGLE_KEY in .env")
            return None
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # Use kaggle API
            from kaggle.api.kaggle_api_extended import KaggleApi
            
            api = KaggleApi()
            api.authenticate()
            
            self.logger.info(f"Downloading {dataset}...")
            api.dataset_download_files(dataset, path=output_path, unzip=True)
            
            self.logger.info(f"Dataset downloaded to {output_path}")
            return output_path
            
        except ImportError:
            self.logger.error("Kaggle package not installed. Run: pip install kaggle")
            return None
        except Exception as e:
            self.logger.error(f"Failed to download dataset: {e}")
            return None
    
    def list_popular_finance_datasets(self) -> List[str]:
        """List popular finance-related datasets on Kaggle."""
        
        return [
            # Congress/Political Trading
            'nelgiriyewithana/most-traded-stocks-by-congress-members',
            'heyytanay/senate-stock-trading-data',
            
            # Insider Trading
            'quickdata/insider-trades-dataset',
            
            # Stock Data
            'borismarjanovic/price-volume-data-for-all-us-stocks-etfs',
            'jacksoncrow/stock-market-dataset',
            
            # Institutional
            'stefanoleone992/mutual-funds-and-etfs',
            
            # Economic
            'unanimad/us-election-2020',
            'federal-reserve/interest-rates'
        ]


class DataGovImporter:
    """Import datasets from Data.gov."""
    
    def __init__(self):
        self.logger = logging.getLogger("datagov_importer")
        self.base_url = "https://catalog.data.gov/api/3"
        
    def search_datasets(self, query: str, rows: int = 10) -> List[Dict]:
        """Search Data.gov datasets."""
        
        url = f"{self.base_url}/action/package_search"
        params = {'q': query, 'rows': rows}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            datasets = []
            for result in data.get('result', {}).get('results', []):
                datasets.append({
                    'name': result.get('name'),
                    'title': result.get('title'),
                    'notes': result.get('notes', '')[:200],
                    'organization': result.get('organization', {}).get('title'),
                    'url': f"https://catalog.data.gov/dataset/{result.get('name')}"
                })
            
            return datasets
            
        except Exception as e:
            self.logger.error(f"Failed to search Data.gov: {e}")
            return []
    
    def download_dataset(self, dataset_id: str, output_dir: str = 'data/datagov') -> Optional[Path]:
        """Download a dataset from Data.gov."""
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Get dataset metadata
        url = f"{self.base_url}/action/package_show"
        params = {'id': dataset_id}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            dataset = data.get('result', {})
            resources = dataset.get('resources', [])
            
            if not resources:
                self.logger.error(f"No resources found for {dataset_id}")
                return None
            
            # Download first resource
            resource = resources[0]
            resource_url = resource.get('url')
            resource_format = resource.get('format', 'data')
            
            if resource_url:
                filename = f"{dataset_id}.{resource_format.lower()}"
                filepath = output_path / filename
                
                self.logger.info(f"Downloading {resource_url}...")
                response = requests.get(resource_url, timeout=60)
                
                with open(filepath, 'wb') as f:
                    f.write(response.content)
                
                self.logger.info(f"Downloaded to {filepath}")
                return filepath
            
        except Exception as e:
            self.logger.error(f"Failed to download dataset: {e}")
            return None
    
    def get_congress_datasets(self) -> List[Dict]:
        """Get congressional/political datasets."""
        
        queries = [
            'congress stock trading',
            'congressional disclosure',
            'politician financial',
            'lobbying disclosure'
        ]
        
        all_datasets = []
        for query in queries:
            all_datasets.extend(self.search_datasets(query, rows=5))
        
        # Deduplicate
        seen = set()
        unique_datasets = []
        for ds in all_datasets:
            if ds['name'] not in seen:
                seen.add(ds['name'])
                unique_datasets.append(ds)
        
        return unique_datasets


class GitHubRepoImporter:
    """Import data from GitHub repositories."""
    
    def __init__(self):
        self.logger = logging.getLogger("github_importer")
        self.github_token = os.getenv('GITHUB_TOKEN')
        
    def clone_repo(self, repo_url: str, output_dir: str = 'data/github') -> Optional[Path]:
        """Clone a GitHub repository."""
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Extract repo name
        repo_name = repo_url.rstrip('/').split('/')[-1].replace('.git', '')
        repo_path = output_path / repo_name
        
        if repo_path.exists():
            self.logger.info(f"Repository already exists at {repo_path}")
            return repo_path
        
        try:
            import subprocess
            
            cmd = ['git', 'clone', repo_url, str(repo_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode == 0:
                self.logger.info(f"Cloned repository to {repo_path}")
                return repo_path
            else:
                self.logger.error(f"Failed to clone: {result.stderr}")
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to clone repository: {e}")
            return None
    
    def download_file(self, file_url: str, output_dir: str = 'data/github') -> Optional[Path]:
        """Download a single file from GitHub."""
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Convert github.com URL to raw.githubusercontent.com
        if 'github.com' in file_url and '/blob/' in file_url:
            file_url = file_url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
        
        filename = file_url.split('/')[-1]
        filepath = output_path / filename
        
        try:
            headers = {}
            if self.github_token:
                headers['Authorization'] = f'token {self.github_token}'
            
            response = requests.get(file_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            self.logger.info(f"Downloaded {filename} to {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Failed to download file: {e}")
            return None
    
    def list_useful_repos(self) -> List[Dict]:
        """List useful GitHub repos with financial/trading data."""
        
        return [
            {
                'name': 'Capitol Trades Scraper',
                'url': 'https://github.com/joshuaptfan/capitol-trades-scraper',
                'description': 'Scraper for Capitol Trades website'
            },
            {
                'name': 'Congress Trading',
                'url': 'https://github.com/pdichone/stock-trading-tracker',
                'description': 'Congressional stock trading tracker'
            },
            {
                'name': 'Senate Stock Watcher',
                'url': 'https://github.com/rkdawenterprises/senate_stock_watcher',
                'description': 'Monitor Senate stock trades'
            },
            {
                'name': 'Financial Datasets',
                'url': 'https://github.com/datasets/finance-vix',
                'description': 'Various financial datasets'
            }
        ]


# Test and usage functions
def main():
    """Test bulk data importers."""
    logging.basicConfig(level=logging.INFO)
    
    print("📦 Bulk Data Import Helpers\n")
    print("=" * 60)
    
    # Kaggle
    print("\n1️⃣  Kaggle Datasets:")
    kaggle = KaggleDatasetImporter()
    
    if kaggle.kaggle_username:
        print("   ✅ Kaggle credentials found")
        datasets = kaggle.list_popular_finance_datasets()
        print(f"   📊 {len(datasets)} popular finance datasets available")
        print("\n   Examples:")
        for ds in datasets[:3]:
            print(f"   - {ds}")
    else:
        print("   ❌ No Kaggle credentials")
        print("   Setup: Add to .env:")
        print("      KAGGLE_USERNAME=your_username")
        print("      KAGGLE_KEY=your_api_key")
        print("   Get key: https://www.kaggle.com/settings")
    
    # Data.gov
    print("\n2️⃣  Data.gov:")
    datagov = DataGovImporter()
    congress_datasets = datagov.get_congress_datasets()
    
    if congress_datasets:
        print(f"   ✅ Found {len(congress_datasets)} congressional datasets")
        print("\n   Examples:")
        for ds in congress_datasets[:3]:
            print(f"   - {ds['title'][:60]}")
    else:
        print("   ⚠️  No datasets found (may be API issue)")
    
    # GitHub
    print("\n3️⃣  GitHub Repos:")
    github = GitHubRepoImporter()
    repos = github.list_useful_repos()
    
    print(f"   📚 {len(repos)} useful repositories:")
    for repo in repos:
        print(f"   - {repo['name']}: {repo['description']}")
    
    print("\n" + "=" * 60)
    print("\n💡 Usage Examples:")
    print("   # Download Kaggle dataset")
    print("   kaggle.download_dataset('nelgiriyewithana/most-traded-stocks-by-congress-members')")
    print("\n   # Clone GitHub repo")
    print("   github.clone_repo('https://github.com/joshuaptfan/capitol-trades-scraper')")
    print("\n   # Search Data.gov")
    print("   datagov.search_datasets('insider trading')")


if __name__ == "__main__":
    main()

