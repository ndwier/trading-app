#!/usr/bin/env python3
"""Add demo trading data to test the platform."""

import sys
from pathlib import Path
from datetime import date, timedelta
from decimal import Decimal

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import get_session, Filer, Trade, FilerType, TransactionType, DataSource

def add_demo_data():
    """Add demo insider trading data."""
    
    with get_session() as session:
        # Check if we already have data
        existing_trades = session.query(Trade).count()
        if existing_trades > 10:
            print(f"Database already has {existing_trades} trades. Skipping demo data.")
            return
        
        print("Adding demo insider trading data...")
        
        # Create demo filers
        pelosi = session.query(Filer).filter(Filer.name == "Nancy Pelosi").first()
        if not pelosi:
            pelosi = Filer(
                name="Nancy Pelosi",
                filer_type=FilerType.POLITICIAN,
                party="Democrat",
                state="CA",
                chamber="House",
                position="Former Speaker"
            )
            session.add(pelosi)
            session.flush()
        
        # Add some demo trades for various stocks
        demo_trades = [
            # NVDA - Multiple buyers (Consensus buying pattern)
            {"filer": "Nancy Pelosi", "ticker": "NVDA", "amount": 500000, "days_ago": 15},
            {"filer": "Dan Crenshaw", "ticker": "NVDA", "amount": 250000, "days_ago": 12},
            {"filer": "Josh Gottheimer", "ticker": "NVDA", "amount": 180000, "days_ago": 10},
            
            # MSFT - Bipartisan interest
            {"filer": "Nancy Pelosi", "ticker": "MSFT", "amount": 350000, "days_ago": 20},
            {"filer": "Marjorie Taylor Greene", "ticker": "MSFT", "amount": 200000, "days_ago": 18},
            
            # TSLA - Large trades
            {"filer": "Elon Musk", "ticker": "TSLA", "amount": 5000000, "days_ago": 7, "is_insider": True},
            
            # AAPL - Multiple smaller trades
            {"filer": "Nancy Pelosi", "ticker": "AAPL", "amount": 150000, "days_ago": 25},
            {"filer": "Josh Gottheimer", "ticker": "AAPL", "amount": 100000, "days_ago": 22},
            
            # META - Recent activity
            {"filer": "Dan Crenshaw", "ticker": "META", "amount": 180000, "days_ago": 8},
            
            # GOOGL - Tech sector
            {"filer": "Josh Gottheimer", "ticker": "GOOGL", "amount": 220000, "days_ago": 14},
        ]
        
        for trade_info in demo_trades:
            # Get or create filer
            filer_name = trade_info["filer"]
            is_insider = trade_info.get("is_insider", False)
            
            filer = session.query(Filer).filter(Filer.name == filer_name).first()
            if not filer:
                if is_insider:
                    filer = Filer(
                        name=filer_name,
                        filer_type=FilerType.CORPORATE_INSIDER,
                        company="Tesla Inc" if "Musk" in filer_name else "Unknown",
                        title="CEO" if "Musk" in filer_name else "Executive"
                    )
                else:
                    # Political filer
                    party = "Republican" if filer_name in ["Dan Crenshaw", "Marjorie Taylor Greene"] else "Democrat"
                    filer = Filer(
                        name=filer_name,
                        filer_type=FilerType.POLITICIAN,
                        party=party,
                        chamber="House"
                    )
                session.add(filer)
                session.flush()
            
            # Create trade
            trade_date = date.today() - timedelta(days=trade_info["days_ago"])
            reported_date = trade_date + timedelta(days=2)  # Report 2 days after trade
            
            trade = Trade(
                filer_id=filer.filer_id,
                source=DataSource.MANUAL,
                source_id=f"demo_{trade_info['ticker']}_{trade_info['days_ago']}",
                reported_date=reported_date,
                trade_date=trade_date,
                ticker=trade_info["ticker"],
                transaction_type=TransactionType.BUY,
                amount_usd=Decimal(trade_info["amount"]),
                raw_data={"note": "Demo data for testing"}
            )
            session.add(trade)
        
        session.commit()
        print(f"✅ Added {len(demo_trades)} demo trades")
        print("\n📊 Demo Data Summary:")
        print("• 10 insider/politician trades")
        print("• Multiple patterns: Consensus buying, Bipartisan interest, Large trades")
        print("• Tickers: NVDA, MSFT, TSLA, AAPL, META, GOOGL")
        print("\n🎯 Now refresh your dashboard to see buy signals!")

if __name__ == "__main__":
    add_demo_data()

