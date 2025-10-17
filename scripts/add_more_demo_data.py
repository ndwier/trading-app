#!/usr/bin/env python3
"""Add extensive demo trading data to test the platform."""

import sys
from pathlib import Path
from datetime import date, timedelta
from decimal import Decimal
import random

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database import get_session, Filer, Trade, FilerType, TransactionType, DataSource

def add_extensive_demo_data():
    """Add extensive demo insider trading data."""
    
    # Real politicians and insiders
    politicians = [
        ("Nancy Pelosi", "Democrat", "CA", "House", "Former Speaker"),
        ("Dan Crenshaw", "Republican", "TX", "House", "Member"),
        ("Josh Gottheimer", "Democrat", "NJ", "House", "Member"),
        ("Marjorie Taylor Greene", "Republican", "GA", "House", "Member"),
        ("Tommy Tuberville", "Republican", "AL", "Senate", "Senator"),
        ("Mark Warner", "Democrat", "VA", "Senate", "Senator"),
        ("Ro Khanna", "Democrat", "CA", "House", "Member"),
        ("Michael McCaul", "Republican", "TX", "House", "Member"),
        ("Patrick Fallon", "Republican", "TX", "House", "Member"),
        ("Shelley Moore Capito", "Republican", "WV", "Senate", "Senator"),
    ]
    
    corporate_insiders = [
        ("Elon Musk", "Tesla Inc", "CEO"),
        ("Tim Cook", "Apple Inc", "CEO"),
        ("Satya Nadella", "Microsoft Corp", "CEO"),
        ("Jensen Huang", "NVIDIA Corp", "CEO"),
        ("Mary Barra", "General Motors", "CEO"),
        ("Jamie Dimon", "JPMorgan Chase", "CEO"),
        ("Brian Niccol", "Starbucks", "CEO"),
        ("Andy Jassy", "Amazon", "CEO"),
        ("Sundar Pichai", "Alphabet Inc", "CEO"),
        ("Mark Zuckerberg", "Meta Platforms", "CEO"),
    ]
    
    # Diverse stock universe
    stocks = {
        # Tech
        "NVDA": 181.81, "AAPL": 247.45, "MSFT": 511.61, "GOOGL": 174.89, "META": 582.77,
        "AMZN": 189.54, "TSLA": 263.91, "CRM": 289.34, "ORCL": 169.23, "AMD": 163.45,
        # Finance
        "JPM": 224.67, "BAC": 42.34, "WFC": 60.12, "GS": 528.91, "MS": 119.87,
        # Healthcare
        "UNH": 591.23, "JNJ": 160.45, "PFE": 28.91, "ABBV": 196.78, "MRK": 100.23,
        # Defense
        "LMT": 568.23, "RTX": 124.56, "NOC": 489.12, "GD": 289.45, "BA": 155.23,
        # Energy
        "XOM": 118.45, "CVX": 158.90, "COP": 108.23, "SLB": 42.67, "OXY": 53.21,
        # Consumer
        "WMT": 83.45, "TGT": 152.34, "COST": 891.23, "HD": 402.56, "NKE": 78.90,
        # Industrials  
        "CAT": 378.23, "DE": 423.45, "HON": 218.67, "UPS": 135.89, "FDX": 289.12,
    }
    
    with get_session() as session:
        print("🚀 Adding extensive demo data...")
        
        # Create all filers
        filer_objects = {}
        
        # Add politicians
        for name, party, state, chamber, position in politicians:
            existing = session.query(Filer).filter(Filer.name == name).first()
            if not existing:
                filer = Filer(
                    name=name,
                    filer_type=FilerType.POLITICIAN,
                    party=party,
                    state=state,
                    chamber=chamber,
                    position=position
                )
                session.add(filer)
                session.flush()
                filer_objects[name] = filer
            else:
                filer_objects[name] = existing
        
        # Add corporate insiders
        for name, company, title in corporate_insiders:
            existing = session.query(Filer).filter(Filer.name == name).first()
            if not existing:
                filer = Filer(
                    name=name,
                    filer_type=FilerType.CORPORATE_INSIDER,
                    company=company,
                    title=title
                )
                session.add(filer)
                session.flush()
                filer_objects[name] = filer
            else:
                filer_objects[name] = existing
        
        session.commit()
        
        # Generate realistic trading patterns
        trades_added = 0
        
        # Pattern 1: Clustered buying (multiple insiders buying same stock)
        cluster_stocks = ["NVDA", "AMD", "GOOGL", "MSFT", "META"]
        for ticker in cluster_stocks:
            num_buyers = random.randint(3, 6)
            days_ago = random.randint(5, 30)
            filer_names = random.sample(list(filer_objects.keys()), num_buyers)
            
            for filer_name in filer_names:
                amount = random.randint(50000, 500000)
                trade_date = date.today() - timedelta(days=days_ago + random.randint(-2, 2))
                reported_date = trade_date + timedelta(days=random.randint(2, 30))
                
                source_id = f"cluster_{ticker}_{filer_name}_{days_ago}"
                existing = session.query(Trade).filter(Trade.source_id == source_id).first()
                if not existing:
                    trade = Trade(
                        filer_id=filer_objects[filer_name].filer_id,
                        source=DataSource.MANUAL,
                        source_id=source_id,
                        reported_date=reported_date,
                        trade_date=trade_date,
                        ticker=ticker,
                        company_name=f"{ticker} Corp",
                        transaction_type=TransactionType.BUY,
                        amount_usd=Decimal(amount),
                        price=Decimal(stocks[ticker]),
                        quantity=Decimal(amount / stocks[ticker]),
                        raw_data={"pattern": "cluster_buying", "note": "Demo data"}
                    )
                    session.add(trade)
                    trades_added += 1
        
        # Pattern 2: Bipartisan interest
        bipartisan_stocks = ["JPM", "BAC", "XOM", "LMT", "RTX"]
        for ticker in bipartisan_stocks:
            # Get Democrat and Republican politicians
            democrats = [name for name, party, _, _, _ in politicians if party == "Democrat"]
            republicans = [name for name, party, _, _, _ in politicians if party == "Republican"]
            
            for filer_name in random.sample(democrats, 2) + random.sample(republicans, 2):
                amount = random.randint(100000, 750000)
                days_ago = random.randint(10, 45)
                trade_date = date.today() - timedelta(days=days_ago)
                reported_date = trade_date + timedelta(days=random.randint(2, 30))
                
                source_id = f"bipartisan_{ticker}_{filer_name}_{days_ago}"
                existing = session.query(Trade).filter(Trade.source_id == source_id).first()
                if not existing:
                    trade = Trade(
                        filer_id=filer_objects[filer_name].filer_id,
                        source=DataSource.MANUAL,
                        source_id=source_id,
                        reported_date=reported_date,
                        trade_date=trade_date,
                        ticker=ticker,
                        company_name=f"{ticker} Inc",
                        transaction_type=TransactionType.BUY,
                        amount_usd=Decimal(amount),
                        price=Decimal(stocks[ticker]),
                        quantity=Decimal(amount / stocks[ticker]),
                        raw_data={"pattern": "bipartisan_interest", "note": "Demo data"}
                    )
                    session.add(trade)
                    trades_added += 1
        
        # Pattern 3: Insider CEO trades (large, conviction buys)
        ceo_stocks = [("Elon Musk", "TSLA"), ("Tim Cook", "AAPL"), ("Satya Nadella", "MSFT"),
                      ("Jensen Huang", "NVDA"), ("Mark Zuckerberg", "META")]
        for ceo_name, ticker in ceo_stocks:
            for i in range(3):  # Multiple purchases
                amount = random.randint(1000000, 5000000)
                days_ago = random.randint(7, 60)
                trade_date = date.today() - timedelta(days=days_ago)
                reported_date = trade_date + timedelta(days=random.randint(1, 4))
                
                source_id = f"ceo_{ticker}_{ceo_name}_{days_ago}_{i}"
                existing = session.query(Trade).filter(Trade.source_id == source_id).first()
                if not existing:
                    trade = Trade(
                        filer_id=filer_objects[ceo_name].filer_id,
                        source=DataSource.MANUAL,
                        source_id=source_id,
                        reported_date=reported_date,
                        trade_date=trade_date,
                        ticker=ticker,
                        company_name=f"{ticker} Corp",
                        transaction_type=TransactionType.BUY,
                        amount_usd=Decimal(amount),
                        price=Decimal(stocks[ticker]),
                        quantity=Decimal(amount / stocks[ticker]),
                        raw_data={"pattern": "ceo_conviction", "note": "Demo data"}
                    )
                    session.add(trade)
                    trades_added += 1
        
        # Pattern 4: Random diverse trades
        remaining_stocks = [s for s in stocks.keys() if s not in cluster_stocks + bipartisan_stocks + [t for _, t in ceo_stocks]]
        for _ in range(30):  # Add 30 more random trades
            ticker = random.choice(remaining_stocks)
            filer_name = random.choice(list(filer_objects.keys()))
            amount = random.randint(25000, 400000)
            days_ago = random.randint(1, 90)
            trade_date = date.today() - timedelta(days=days_ago)
            reported_date = trade_date + timedelta(days=random.randint(2, 45))
            transaction_type = random.choice([TransactionType.BUY, TransactionType.BUY, TransactionType.BUY, TransactionType.SELL])
            
            source_id = f"random_{ticker}_{filer_name}_{days_ago}"
            existing = session.query(Trade).filter(Trade.source_id == source_id).first()
            if not existing:
                trade = Trade(
                    filer_id=filer_objects[filer_name].filer_id,
                    source=DataSource.MANUAL,
                    source_id=source_id,
                    reported_date=reported_date,
                    trade_date=trade_date,
                    ticker=ticker,
                    company_name=f"{ticker} Corp",
                    transaction_type=transaction_type,
                    amount_usd=Decimal(amount),
                    price=Decimal(stocks[ticker]),
                    quantity=Decimal(amount / stocks[ticker]),
                    raw_data={"pattern": "random", "note": "Demo data"}
                )
                session.add(trade)
                trades_added += 1
        
        session.commit()
        
        total_trades = session.query(Trade).count()
        total_filers = session.query(Filer).count()
        unique_tickers = len(set([t.ticker for t in session.query(Trade).all()]))
        
        print(f"\n✅ Added {trades_added} new trades")
        print(f"\n📊 Database Summary:")
        print(f"• Total Trades: {total_trades}")
        print(f"• Total Filers: {total_filers}")
        print(f"• Unique Stocks: {unique_tickers}")
        print(f"\n🎯 Trading Patterns:")
        print(f"• Cluster Buying: 5+ stocks with multiple insiders")
        print(f"• Bipartisan Interest: Cross-party political trades")
        print(f"• CEO Conviction: Large insider purchases")
        print(f"• Diverse Portfolio: 30+ other stocks")
        print(f"\n🎯 Now regenerate signals to see new opportunities!")

if __name__ == "__main__":
    add_extensive_demo_data()

