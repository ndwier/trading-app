"""Configuration settings for the trading app."""

import os
from pathlib import Path
from typing import Dict, Any
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    
    # Primary database (PostgreSQL for production, SQLite for development)
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{PROJECT_ROOT}/data/trading_app.db"
    )
    
    # Redis for caching and task queue
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Connection pool settings
    POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
    MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))


@dataclass
class APIConfig:
    """API keys and endpoints configuration."""
    
    # Free APIs (no key required)
    SEC_EDGAR_BASE_URL = "https://data.sec.gov"
    OPENINSIDER_BASE_URL = "http://openinsider.com"
    
    # Paid APIs (require keys)
    QUIVER_API_KEY = os.getenv("QUIVER_API_KEY")
    QUIVER_BASE_URL = "https://api.quiverquant.com"
    
    FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
    FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
    
    ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
    ALPHA_VANTAGE_BASE_URL = "https://www.alphavantage.co/query"
    
    # Rate limiting (requests per minute)
    SEC_RATE_LIMIT = 10  # SEC recommends no more than 10 requests per second
    QUIVER_RATE_LIMIT = 60
    FINNHUB_RATE_LIMIT = 60
    
    # Request headers
    SEC_HEADERS = {
        "User-Agent": "TradingApp/1.0 (contact@example.com)",
        "Accept-Encoding": "gzip, deflate"
    }


@dataclass
class ScrapingConfig:
    """Web scraping configuration."""
    
    # Selenium settings
    HEADLESS_BROWSER = True
    BROWSER_TIMEOUT = 30
    IMPLICIT_WAIT = 10
    
    # Data directories
    RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
    PROCESSED_DATA_DIR = PROJECT_ROOT / "data" / "processed"
    
    # Scraping intervals (hours)
    POLITICIAN_SCRAPE_INTERVAL = 6
    SEC_SCRAPE_INTERVAL = 4
    INSIDER_SCRAPE_INTERVAL = 12


@dataclass
class BacktestingConfig:
    """Backtesting framework configuration."""
    
    # Default parameters
    INITIAL_CAPITAL = 100000.0
    COMMISSION = 0.001  # 0.1% per trade
    SLIPPAGE = 0.0005   # 0.05% market impact
    
    # Risk management
    MAX_POSITION_SIZE = 0.1  # 10% of portfolio per position
    STOP_LOSS_PCT = -0.15    # 15% stop loss
    TAKE_PROFIT_PCT = 0.30   # 30% take profit
    
    # Backtesting periods
    LOOKBACK_YEARS = 5
    MINIMUM_TRADES = 30  # Minimum trades for statistical significance
    
    # Performance metrics
    RISK_FREE_RATE = 0.02  # 2% annual risk-free rate
    BENCHMARK_TICKER = "SPY"


@dataclass
class StrategyConfig:
    """Trading strategy configuration."""
    
    # Lag trade parameters
    LAG_TRADE_DELAY_DAYS = [1, 2, 5]  # Days after disclosure
    LAG_TRADE_HOLD_DAYS = [30, 45, 60]  # Holding periods
    
    # Minimum trade size filters (USD)
    MIN_POLITICIAN_TRADE = 15000
    MIN_INSIDER_TRADE = 100000
    MIN_BILLIONAIRE_TRADE = 1000000
    
    # Clustering parameters
    CLUSTER_WINDOW_DAYS = 30  # Look for trades within this window
    MIN_CLUSTER_SIZE = 3      # Minimum number of similar trades
    
    # Signal strength thresholds
    STRONG_BUY_THRESHOLD = 0.7
    BUY_THRESHOLD = 0.5
    SELL_THRESHOLD = 0.3
    STRONG_SELL_THRESHOLD = 0.1


@dataclass
class WebConfig:
    """Web interface configuration."""
    
    # Flask settings
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.getenv("FLASK_DEBUG", "False").lower() == "true"
    
    # Server settings
    HOST = os.getenv("FLASK_HOST", "127.0.0.1")
    PORT = int(os.getenv("FLASK_PORT", "5000"))
    
    # CORS settings
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")


@dataclass
class LoggingConfig:
    """Logging configuration."""
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_DIR = PROJECT_ROOT / "logs"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Log file rotation
    MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
    BACKUP_COUNT = 5


# Main configuration class
class Config:
    """Main configuration class combining all settings."""
    
    def __init__(self):
        self.database = DatabaseConfig()
        self.api = APIConfig()
        self.scraping = ScrapingConfig()
        self.backtesting = BacktestingConfig()
        self.strategy = StrategyConfig()
        self.web = WebConfig()
        self.logging = LoggingConfig()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "database": self.database.__dict__,
            "api": self.api.__dict__,
            "scraping": self.scraping.__dict__,
            "backtesting": self.backtesting.__dict__,
            "strategy": self.strategy.__dict__,
            "web": self.web.__dict__,
            "logging": self.logging.__dict__,
        }


# Global configuration instance
config = Config()

# Ensure data directories exist
config.scraping.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
config.scraping.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
config.logging.LOG_DIR.mkdir(parents=True, exist_ok=True)
