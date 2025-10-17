#!/usr/bin/env python3
"""Switch from demo data to real data."""

import sys
from pathlib import Path
from datetime import date, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import get_session, Trade, Filer, DataSource

def clear_demo_data():
    """Clear all demo/manual data from the database."""
    
    print("🗑️  Clearing demo data...")
    
    with get_session() as session:
        # Count before
        before_trades = session.query(Trade).count()
        before_filers = session.query(Filer).count()
        
        # Delete all MANUAL source trades (demo data)
        demo_trades = session.query(Trade).filter(Trade.source == DataSource.MANUAL).all()
        for trade in demo_trades:
            session.delete(trade)
        
        # Delete filers with no trades
        all_filers = session.query(Filer).all()
        for filer in all_filers:
            trade_count = session.query(Trade).filter(Trade.filer_id == filer.filer_id).count()
            if trade_count == 0:
                session.delete(filer)
        
        session.commit()
        
        # Count after
        after_trades = session.query(Trade).count()
        after_filers = session.query(Filer).count()
        
        print(f"✅ Removed {before_trades - after_trades} demo trades")
        print(f"✅ Removed {before_filers - after_filers} demo filers")
        print(f"📊 Remaining: {after_trades} trades, {after_filers} filers\n")

def main():
    """Main function."""
    
    print("=" * 60)
    print("🔄 SWITCHING TO REAL DATA")
    print("=" * 60)
    print()
    
    # Step 1: Clear demo data
    clear_demo_data()
    
    # Step 2: Instructions for getting real data
    print("=" * 60)
    print("📥 NEXT STEPS: Fetch Real Data")
    print("=" * 60)
    print()
    print("Now run ONE of these commands to get real trading data:")
    print()
    print("🆓 Option 1: Free Scrapers (Limited Data)")
    print("-" * 60)
    print("  # Get 90 days of politician trades from Capitol Trades")
    print("  python scripts/run_ingestion.py --source politicians --days 90")
    print()
    print("  # Get SEC insider trades (5-35 days ago due to SEC delay)")
    print("  python scripts/run_ingestion.py --source sec --days 30")
    print()
    print("  # Or get both:")
    print("  python scripts/run_ingestion.py --source all --days 90")
    print()
    print("💰 Option 2: Paid APIs (High Quality, Real-Time)")
    print("-" * 60)
    print("  1. Sign up for one of these services:")
    print("     • Quiver Quantitative: https://www.quiverquant.com")
    print("       - $30-50/month, best politician data")
    print("     • Finnhub: https://finnhub.io")
    print("       - $60/month, congress trading API")
    print()
    print("  2. Add your API key to .env file:")
    print("     QUIVER_API_KEY=your_key_here")
    print("     # or")
    print("     FINNHUB_API_KEY=your_key_here")
    print()
    print("  3. Run ingestion:")
    print("     python scripts/run_ingestion.py --source all --days 365")
    print()
    print("=" * 60)
    print("⚠️  NOTE: Free scrapers have limitations:")
    print("   • Capitol Trades: May be slow, limited history")
    print("   • SEC EDGAR: 5-day delay, complex parsing")
    print("   • For serious trading, consider paid APIs")
    print("=" * 60)

if __name__ == "__main__":
    main()

