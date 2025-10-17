#!/usr/bin/env python3
"""
Daily Update Script

Runs daily to:
1. Ingest new data from all sources
2. Generate new signals
3. Evaluate existing signals
4. Send digest email

Schedule with cron:
0 6 * * * cd /path/to/trading-app && ./venv/bin/python scripts/daily_update.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Run daily update process."""
    start_time = datetime.now()
    logger.info("="*60)
    logger.info(f"Starting daily update at {start_time}")
    logger.info("="*60)
    
    # Step 1: Ingest new data
    logger.info("Step 1: Ingesting new data...")
    try:
        from src.ingestion.sec_scraper import SECScraper
        from src.ingestion.politician_scraper import PoliticianScraper
        from src.ingestion.openinsider_scraper import OpenInsiderScraper
        
        # SEC data (last 3 days to catch updates)
        sec = SECScraper()
        sec_trades = sec.fetch_recent_trades(days=3)
        logger.info(f"  SEC: {len(list(sec_trades))} trades")
        
        # Political trades (last 7 days)
        pol = PoliticianScraper()
        pol_trades = pol.fetch_recent_trades(days=7)
        logger.info(f"  Politicians: {len(list(pol_trades))} trades")
        
        # OpenInsider (last 5 days)
        oi = OpenInsiderScraper()
        oi_trades = oi.fetch_recent_trades(days=5)
        logger.info(f"  OpenInsider: {len(list(oi_trades))} trades")
        
    except Exception as e:
        logger.error(f"Data ingestion failed: {e}")
    
    # Step 2: Generate new signals
    logger.info("Step 2: Generating signals...")
    try:
        from src.analysis.signal_generator import SignalGenerator
        
        generator = SignalGenerator()
        signals = generator.generate_signals()
        logger.info(f"  Generated {len(signals)} new signals")
        
    except Exception as e:
        logger.error(f"Signal generation failed: {e}")
    
    # Step 3: Evaluate signal performance
    logger.info("Step 3: Evaluating signal performance...")
    try:
        from src.analysis.signal_tracker import SignalTracker
        
        tracker = SignalTracker()
        result = tracker.evaluate_all_signals()
        logger.info(f"  Evaluated {result['evaluated']} signals, updated {result['updated']}")
        
    except Exception as e:
        logger.error(f"Signal evaluation failed: {e}")
    
    # Step 4: Check for high-confidence alerts
    logger.info("Step 4: Checking for alerts...")
    try:
        from src.alerts import check_and_send_alerts
        
        alert_result = check_and_send_alerts()
        logger.info(f"  Sent {alert_result['sent']} alerts")
        
    except Exception as e:
        logger.error(f"Alert check failed: {e}")
    
    # Step 5: Send daily digest (optional)
    logger.info("Step 5: Sending daily digest...")
    try:
        from src.alerts import AlertSystem
        from src.analysis.paper_trading import PaperTradingPortfolio
        
        # Get summary data
        portfolio = PaperTradingPortfolio()
        portfolio_summary = portfolio.get_portfolio_summary()
        
        digest_data = {
            'new_signals': len(signals) if 'signals' in locals() else 0,
            'avg_confidence': 85.0,  # Placeholder
            'top_signals': [],
            'portfolio_return': portfolio_summary['total_return_pct'],
            'win_rate': portfolio_summary['win_rate'],
            'portfolio_value': portfolio_summary['current_value'],
            'most_active_insider': 'N/A',
            'hottest_sector': 'Technology'
        }
        
        alert_system = AlertSystem()
        digest_result = alert_system.send_daily_digest(digest_data)
        
        if digest_result.get('success'):
            logger.info("  Daily digest sent successfully")
        else:
            logger.warning(f"  Daily digest failed: {digest_result.get('error')}")
            
    except Exception as e:
        logger.error(f"Daily digest failed: {e}")
    
    # Summary
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    logger.info("="*60)
    logger.info(f"Daily update completed in {duration:.1f} seconds")
    logger.info("="*60)


if __name__ == '__main__':
    main()

