#!/usr/bin/env python3
"""Script to run data ingestion from all sources."""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ingestion.politician_scraper import PoliticianScraper
from src.ingestion.sec_scraper import SECScraper
from src.ingestion.openinsider_scraper import OpenInsiderScraper
from src.ingestion.finnhub_scraper import FinnhubScraper
from src.ingestion.data_normalizer import DataNormalizer
from config.config import config


def setup_logging():
    """Setup logging for ingestion."""
    log_file = config.logging.LOG_DIR / f"ingestion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    logging.basicConfig(
        level=getattr(logging, config.logging.LOG_LEVEL),
        format=config.logging.LOG_FORMAT,
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    return logging.getLogger(__name__)


def run_politician_ingestion(days: int = 30) -> dict:
    """Run politician trade ingestion."""
    logger = logging.getLogger(__name__)
    logger.info(f"Starting politician ingestion for {days} days")
    
    try:
        scraper = PoliticianScraper()
        results = scraper.run_full_ingestion(days=days)
        logger.info(f"Politician ingestion completed: {results}")
        return results
    except Exception as e:
        logger.error(f"Politician ingestion failed: {e}")
        return {"error": str(e)}


def run_sec_ingestion(days: int = 7) -> dict:
    """Run SEC insider trade ingestion."""
    logger = logging.getLogger(__name__)
    logger.info(f"Starting SEC ingestion for {days} days")
    
    try:
        scraper = SECScraper()
        results = scraper.run_full_ingestion(days=days)
        logger.info(f"SEC ingestion completed: {results}")
        return results
    except Exception as e:
        logger.error(f"SEC ingestion failed: {e}")
        return {"error": str(e)}


def run_openinsider_ingestion(days: int = 30) -> dict:
    """Run OpenInsider scraping."""
    logger = logging.getLogger(__name__)
    logger.info(f"Starting OpenInsider ingestion for {days} days")
    
    try:
        scraper = OpenInsiderScraper()
        results = scraper.run_ingestion(mode="recent", days=days)
        logger.info(f"OpenInsider ingestion completed: {results}")
        return results
    except Exception as e:
        logger.error(f"OpenInsider ingestion failed: {e}")
        return {"error": str(e)}


def run_finnhub_ingestion(days: int = 30) -> dict:
    """Run Finnhub API ingestion."""
    logger = logging.getLogger(__name__)
    logger.info(f"Starting Finnhub ingestion for {days} days")
    
    try:
        scraper = FinnhubScraper()
        results = scraper.run_ingestion(mode="recent", days=days)
        logger.info(f"Finnhub ingestion completed: {results}")
        return results
    except Exception as e:
        logger.error(f"Finnhub ingestion failed: {e}")
        return {"error": str(e)}


def run_data_normalization() -> dict:
    """Run data normalization."""
    logger = logging.getLogger(__name__)
    logger.info("Starting data normalization")
    
    try:
        normalizer = DataNormalizer()
        results = normalizer.normalize_batch()
        logger.info(f"Data normalization completed: {results}")
        return results
    except Exception as e:
        logger.error(f"Data normalization failed: {e}")
        return {"error": str(e)}


def main():
    """Main ingestion function."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run trading data ingestion")
    parser.add_argument("--source", choices=["all", "politicians", "sec", "openinsider", "finnhub"], 
                       default="all", help="Data source to ingest")
    parser.add_argument("--days", type=int, default=30,
                       help="Number of days to look back")
    parser.add_argument("--normalize", action="store_true",
                       help="Run data normalization after ingestion")
    parser.add_argument("--dry-run", action="store_true",
                       help="Show what would be done without executing")
    
    args = parser.parse_args()
    
    logger = setup_logging()
    
    if args.dry_run:
        logger.info("DRY RUN - No actual ingestion will be performed")
        logger.info(f"Would ingest: {args.source}")
        logger.info(f"Days lookback: {args.days}")
        logger.info(f"Normalize: {args.normalize}")
        return
    
    logger.info("=== Trading Data Ingestion ===")
    logger.info(f"Source: {args.source}")
    logger.info(f"Days: {args.days}")
    logger.info(f"Normalize: {args.normalize}")
    
    results = {}
    
    try:
        # Run ingestion based on source
        if args.source in ["all", "politicians"]:
            results["politicians"] = run_politician_ingestion(args.days)
        
        if args.source in ["all", "sec"]:
            # Use fewer days for SEC due to volume
            sec_days = min(args.days, 7)
            results["sec"] = run_sec_ingestion(sec_days)
        
        if args.source in ["all", "openinsider"]:
            results["openinsider"] = run_openinsider_ingestion(args.days)
        
        if args.source == "finnhub":
            results["finnhub"] = run_finnhub_ingestion(args.days)
        
        # Run normalization if requested
        if args.normalize:
            results["normalization"] = run_data_normalization()
        
        # Summary
        logger.info("\n" + "="*50)
        logger.info("INGESTION SUMMARY")
        logger.info("="*50)
        
        for source, result in results.items():
            if "error" in result:
                logger.error(f"{source.upper()}: Failed - {result['error']}")
            else:
                trades_count = result.get("total_trades", result.get("trades_collected", "Unknown"))
                logger.info(f"{source.upper()}: {trades_count} trades collected")
        
        logger.info("\nNext steps:")
        logger.info("1. Check data quality: python -m src.ingestion.data_normalizer --trades")
        logger.info("2. Run backtests: python -m src.backtesting.backtester")
        logger.info("3. View dashboard: python app.py")
        
    except KeyboardInterrupt:
        logger.warning("Ingestion interrupted by user")
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
