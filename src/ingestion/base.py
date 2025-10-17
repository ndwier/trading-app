"""Base classes for data ingestion."""

import time
import logging
from abc import ABC, abstractmethod
from datetime import datetime, date
from typing import Dict, List, Optional, Any, Iterator
from dataclasses import dataclass
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.config import config


logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Base exception for ingestion errors."""
    pass


class RateLimitError(IngestionError):
    """Exception raised when API rate limits are exceeded."""
    pass


class DataQualityError(IngestionError):
    """Exception raised when data quality checks fail."""
    pass


@dataclass
class RawTradeData:
    """Raw trade data before normalization."""
    
    source: str
    source_id: str
    filer_name: str
    filer_type: str
    
    # Dates
    reported_date: Optional[date] = None
    trade_date: Optional[date] = None
    
    # Security information
    ticker: Optional[str] = None
    company_name: Optional[str] = None
    cusip: Optional[str] = None
    
    # Transaction details
    transaction_type: Optional[str] = None
    quantity: Optional[float] = None
    price: Optional[float] = None
    amount_usd: Optional[float] = None
    
    # Additional fields
    insider_relationship: Optional[str] = None
    ownership_type: Optional[str] = None
    filing_url: Optional[str] = None
    
    # Raw data for debugging
    raw_data: Optional[Dict[str, Any]] = None
    
    def validate(self) -> List[str]:
        """Validate the trade data and return list of errors."""
        errors = []
        
        if not self.filer_name:
            errors.append("Missing filer name")
        
        if not self.reported_date:
            errors.append("Missing reported date")
            
        if not self.ticker and not self.company_name:
            errors.append("Missing ticker or company name")
            
        if not self.transaction_type:
            errors.append("Missing transaction type")
            
        return errors


class BaseIngester(ABC):
    """Base class for all data ingesters."""
    
    def __init__(self, name: str):
        """Initialize the ingester.
        
        Args:
            name: Name of the ingester for logging
        """
        self.name = name
        self.logger = logging.getLogger(f"ingester.{name}")
        
        # Request session with retry logic
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            status_forcelist=[429, 500, 502, 503, 504],
            backoff_factor=1,
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 1.0  # Minimum seconds between requests
        
        # Statistics
        self.stats = {
            "requests_made": 0,
            "trades_collected": 0,
            "errors": 0,
            "last_run": None
        }
    
    def _rate_limit(self):
        """Implement rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            self.logger.debug(f"Rate limiting: sleeping {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        self.last_request_time = time.time()
    
    def _make_request(self, url: str, headers: Optional[Dict[str, str]] = None,
                      params: Optional[Dict[str, Any]] = None,
                      timeout: int = 30) -> requests.Response:
        """Make an HTTP request with rate limiting and error handling.
        
        Args:
            url: Request URL
            headers: Optional headers
            params: Optional query parameters
            timeout: Request timeout in seconds
            
        Returns:
            Response object
            
        Raises:
            IngestionError: If request fails after retries
        """
        self._rate_limit()
        
        try:
            self.stats["requests_made"] += 1
            
            response = self.session.get(
                url,
                headers=headers or {},
                params=params or {},
                timeout=timeout
            )
            
            # Check for rate limiting
            if response.status_code == 429:
                raise RateLimitError("Rate limit exceeded")
            
            response.raise_for_status()
            return response
            
        except requests.exceptions.RequestException as e:
            self.stats["errors"] += 1
            self.logger.error(f"Request failed: {url} - {e}")
            raise IngestionError(f"Request failed: {e}")
    
    def _validate_trade_data(self, trade_data: RawTradeData) -> bool:
        """Validate trade data quality.
        
        Args:
            trade_data: Trade data to validate
            
        Returns:
            True if valid, False otherwise
        """
        errors = trade_data.validate()
        
        if errors:
            self.logger.warning(
                f"Trade data validation failed for {trade_data.filer_name}: "
                f"{', '.join(errors)}"
            )
            return False
        
        return True
    
    @abstractmethod
    def fetch_recent_trades(self, days: int = 30) -> Iterator[RawTradeData]:
        """Fetch recent trades from the data source.
        
        Args:
            days: Number of days to look back
            
        Yields:
            RawTradeData: Individual trade records
        """
        pass
    
    @abstractmethod
    def fetch_historical_trades(self, start_date: date, end_date: date) -> Iterator[RawTradeData]:
        """Fetch historical trades for a date range.
        
        Args:
            start_date: Start date for data collection
            end_date: End date for data collection
            
        Yields:
            RawTradeData: Individual trade records
        """
        pass
    
    @abstractmethod
    def fetch_filer_trades(self, filer_identifier: str) -> Iterator[RawTradeData]:
        """Fetch all trades for a specific filer.
        
        Args:
            filer_identifier: Identifier for the filer (varies by source)
            
        Yields:
            RawTradeData: Individual trade records
        """
        pass
    
    def run_ingestion(self, mode: str = "recent", **kwargs) -> Dict[str, Any]:
        """Run the ingestion process.
        
        Args:
            mode: Ingestion mode ('recent', 'historical', 'filer')
            **kwargs: Additional arguments for specific modes
            
        Returns:
            Statistics about the ingestion run
        """
        start_time = datetime.now()
        self.logger.info(f"Starting {self.name} ingestion in {mode} mode")
        
        trades_processed = 0
        trades_collected = 0
        errors = 0
        
        try:
            if mode == "recent":
                days = kwargs.get("days", 30)
                trades_iter = self.fetch_recent_trades(days)
            elif mode == "historical":
                start_date = kwargs.get("start_date")
                end_date = kwargs.get("end_date")
                if not start_date or not end_date:
                    raise IngestionError("Historical mode requires start_date and end_date")
                trades_iter = self.fetch_historical_trades(start_date, end_date)
            elif mode == "filer":
                filer_id = kwargs.get("filer_identifier")
                if not filer_id:
                    raise IngestionError("Filer mode requires filer_identifier")
                trades_iter = self.fetch_filer_trades(filer_id)
            else:
                raise IngestionError(f"Unknown ingestion mode: {mode}")
            
            # Process trades
            for trade_data in trades_iter:
                trades_processed += 1
                
                if self._validate_trade_data(trade_data):
                    trades_collected += 1
                    # Here we would normally save to database
                    # This will be implemented in the specific scrapers
                else:
                    errors += 1
                
                if trades_processed % 100 == 0:
                    self.logger.info(f"Processed {trades_processed} trades...")
        
        except Exception as e:
            self.logger.error(f"Ingestion failed: {e}")
            errors += 1
        
        # Update statistics
        end_time = datetime.now()
        runtime = (end_time - start_time).total_seconds()
        
        run_stats = {
            "mode": mode,
            "trades_processed": trades_processed,
            "trades_collected": trades_collected,
            "errors": errors,
            "runtime_seconds": runtime,
            "start_time": start_time,
            "end_time": end_time
        }
        
        self.stats["trades_collected"] += trades_collected
        self.stats["errors"] += errors
        self.stats["last_run"] = end_time
        
        self.logger.info(
            f"Ingestion completed: {trades_collected}/{trades_processed} trades "
            f"collected in {runtime:.1f} seconds"
        )
        
        return run_stats
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the ingester."""
        return {
            "name": self.name,
            "stats": self.stats.copy(),
            "min_request_interval": self.min_request_interval,
        }


class APIIngester(BaseIngester):
    """Base class for API-based ingesters."""
    
    def __init__(self, name: str, base_url: str, api_key: Optional[str] = None,
                 rate_limit: int = 60):
        """Initialize API ingester.
        
        Args:
            name: Name of the ingester
            base_url: Base URL for the API
            api_key: API key if required
            rate_limit: Requests per minute
        """
        super().__init__(name)
        self.base_url = base_url
        self.api_key = api_key
        
        # Set rate limiting based on API limits
        self.min_request_interval = 60.0 / rate_limit if rate_limit > 0 else 1.0
        
        # Set up authentication headers
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})
    
    def _build_url(self, endpoint: str) -> str:
        """Build full URL for API endpoint."""
        return f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"


class ScrapingIngester(BaseIngester):
    """Base class for web scraping ingesters."""
    
    def __init__(self, name: str, base_url: str):
        """Initialize scraping ingester.
        
        Args:
            name: Name of the ingester
            base_url: Base URL for scraping
        """
        super().__init__(name)
        self.base_url = base_url
        
        # Slower rate limiting for web scraping to be respectful
        self.min_request_interval = 2.0
        
        # Set user agent for web scraping
        self.session.headers.update({
            "User-Agent": (
                "TradingApp/1.0 (Educational Research; "
                "contact@example.com)"
            )
        })
