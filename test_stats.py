#!/usr/bin/env python3
"""Test the stats endpoint logic."""

from datetime import datetime, timedelta
from src.database import get_session, Trade, Filer
from sqlalchemy import func

def test_stats():
    """Test stats generation."""
    
    with get_session() as session:
        # Count trades by type
        from src.database.models import FilerType
        
        stats = {
            'total_trades': session.query(Trade).count(),
            'total_filers': session.query(Filer).count(),
            'politician_trades': session.query(Trade).join(Filer).filter(
                Filer.filer_type == FilerType.POLITICIAN
            ).count(),
            'insider_trades': session.query(Trade).join(Filer).filter(
                Filer.filer_type == FilerType.CORPORATE_INSIDER
            ).count(),
            'recent_trades': session.query(Trade).filter(
                Trade.reported_date >= datetime.now().date() - timedelta(days=30)
            ).count()
        }
        
        # Top tickers
        top_tickers = session.query(
            Trade.ticker,
            func.count(Trade.trade_id).label('count')
        ).group_by(Trade.ticker).order_by(func.count(Trade.trade_id).desc()).limit(10).all()
        
        stats['top_tickers'] = [{'ticker': t[0], 'count': t[1]} for t in top_tickers]
        
        import json
        print(json.dumps(stats, indent=2))
        return stats

if __name__ == "__main__":
    test_stats()

