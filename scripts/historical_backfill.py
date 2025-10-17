#!/usr/bin/env python3
"""
Historical Data Backfill Script

Backfills historical insider trading data for better signal accuracy.

Usage:
python scripts/historical_backfill.py --years 2
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
import argparse
from datetime import datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def backfill_sec_data(years: int):
    """Backfill SEC Form 4 data."""
    logger.info(f"Backfilling SEC data for {years} years...")
    
    from src.ingestion.sec_scraper import SECScraper
    
    scraper = SECScraper()
    
    # SEC data goes back in chunks
    total_days = years * 365
    chunk_size = 30  # 30-day chunks
    
    trades_collected = 0
    
    for chunk_start in range(0, total_days, chunk_size):
        try:
            trades = scraper.fetch_recent_trades(days=chunk_size, offset_days=chunk_start)
            chunk_trades = len(list(trades))
            trades_collected += chunk_trades
            
            logger.info(f"  Days {chunk_start}-{chunk_start+chunk_size}: {chunk_trades} trades")
            
        except Exception as e:
            logger.error(f"  Error in chunk {chunk_start}: {e}")
            continue
    
    logger.info(f"SEC backfill complete: {trades_collected} total trades")
    return trades_collected


def backfill_political_data(years: int):
    """Backfill political trading data."""
    logger.info(f"Backfilling political data for {years} years...")
    
    from src.ingestion.politician_scraper import PoliticianScraper
    
    scraper = PoliticianScraper()
    
    # Political data in chunks
    total_days = years * 365
    chunk_size = 90  # 90-day chunks (larger since less frequent)
    
    trades_collected = 0
    
    for chunk_start in range(0, total_days, chunk_size):
        try:
            trades = scraper.fetch_recent_trades(days=chunk_size, offset_days=chunk_start)
            chunk_trades = len(list(trades))
            trades_collected += chunk_trades
            
            logger.info(f"  Days {chunk_start}-{chunk_start+chunk_size}: {chunk_trades} trades")
            
        except Exception as e:
            logger.error(f"  Error in chunk {chunk_start}: {e}")
            continue
    
    logger.info(f"Political backfill complete: {trades_collected} total trades")
    return trades_collected


def backfill_openinsider_data(years: int):
    """Backfill OpenInsider data."""
    logger.info(f"Backfilling OpenInsider data for {years} years...")
    
    from src.ingestion.openinsider_scraper import OpenInsiderScraper
    
    scraper = OpenInsiderScraper()
    
    # OpenInsider in chunks
    total_days = years * 365
    chunk_size = 30
    
    trades_collected = 0
    
    for chunk_start in range(0, total_days, chunk_size):
        try:
            trades = scraper.fetch_recent_trades(days=chunk_size, offset_days=chunk_start)
            chunk_trades = len(list(trades))
            trades_collected += chunk_trades
            
            logger.info(f"  Days {chunk_start}-{chunk_start+chunk_size}: {chunk_trades} trades")
            
        except Exception as e:
            logger.error(f"  Error in chunk {chunk_start}: {e}")
            continue
    
    logger.info(f"OpenInsider backfill complete: {trades_collected} total trades")
    return trades_collected


def main():
    """Run historical backfill."""
    parser = argparse.ArgumentParser(description='Backfill historical insider trading data')
    parser.add_argument('--years', type=int, default=2, help='Number of years to backfill (default: 2)')
    parser.add_argument('--sources', nargs='+', default=['all'], 
                       choices=['all', 'sec', 'political', 'openinsider'],
                       help='Data sources to backfill')
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    logger.info("="*60)
    logger.info(f"Starting historical backfill: {args.years} years")
    logger.info(f"Sources: {', '.join(args.sources)}")
    logger.info("="*60)
    
    total_trades = 0
    
    # Backfill requested sources
    sources = args.sources if 'all' not in args.sources else ['sec', 'political', 'openinsider']
    
    if 'sec' in sources:
        try:
            total_trades += backfill_sec_data(args.years)
        except Exception as e:
            logger.error(f"SEC backfill failed: {e}")
    
    if 'political' in sources:
        try:
            total_trades += backfill_political_data(args.years)
        except Exception as e:
            logger.error(f"Political backfill failed: {e}")
    
    if 'openinsider' in sources:
        try:
            total_trades += backfill_openinsider_data(args.years)
        except Exception as e:
            logger.error(f"OpenInsider backfill failed: {e}")
    
    # Generate signals from historical data
    logger.info("Generating signals from historical data...")
    try:
        from src.analysis.signal_generator import SignalGenerator
        
        generator = SignalGenerator()
        signals = generator.generate_signals()
        logger.info(f"Generated {len(signals)} signals from historical data")
        
    except Exception as e:
        logger.error(f"Historical signal generation failed: {e}")
    
    # Summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    logger.info("="*60)
    logger.info(f"Backfill completed in {duration/60:.1f} minutes")
    logger.info(f"Total trades collected: {total_trades}")
    logger.info("="*60)


if __name__ == '__main__':
    main()

