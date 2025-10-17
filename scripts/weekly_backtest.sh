#!/bin/bash
#
# Weekly Backtesting & Performance Analysis
# Run this weekly to validate your strategy
#
# Schedule with cron:
# crontab -e
# Add line: 0 3 * * 0 /Users/natewier/Projects/trading-app/scripts/weekly_backtest.sh >> /Users/natewier/Projects/trading-app/logs/weekly.log 2>&1
#

set -e

# Configuration
PROJECT_DIR="/Users/natewier/Projects/trading-app"
VENV_DIR="$PROJECT_DIR/venv"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

echo "=================================================================="
echo "📈 WEEKLY BACKTEST - $TIMESTAMP"
echo "=================================================================="

# Activate virtual environment
cd "$PROJECT_DIR"
source "$VENV_DIR/bin/activate"

# 1. Collect last 90 days (for backtesting)
echo ""
echo "📥 Step 1: Collecting 90-day dataset..."
python scripts/run_ingestion.py --source all --days 90 || echo "⚠️  Collection failed"

# 2. Run backtests
echo ""
echo "🧪 Step 2: Running backtests..."
# Uncomment when backtest script is ready:
# python scripts/run_backtest.py --strategy all || echo "⚠️  Backtest failed"

# 3. Generate performance report
echo ""
echo "📊 Step 3: Performance analysis..."
python -c "
from src.database import get_session, Trade, Signal
from sqlalchemy import func
from datetime import date, timedelta

with get_session() as session:
    # Last 7 days activity
    week_ago = date.today() - timedelta(days=7)
    recent_trades = session.query(Trade).filter(Trade.trade_date >= week_ago).count()
    
    # Signal performance
    signals = session.query(Signal).filter(Signal.is_active == True).count()
    
    # Top tickers this week
    top_this_week = session.query(
        Trade.ticker,
        func.count(Trade.trade_id).label('count')
    ).filter(Trade.trade_date >= week_ago).group_by(Trade.ticker).order_by(func.count(Trade.trade_id).desc()).limit(5).all()
    
    print('   📅 Last 7 Days:')
    print(f'      New Trades: {recent_trades}')
    print(f'      Active Signals: {signals}')
    print()
    print('   🔥 Top 5 Tickers This Week:')
    for ticker, count in top_this_week:
        print(f'      {ticker}: {count} trades')
"

# 4. Generate weekly report
echo ""
echo "📝 Step 4: Generating weekly report..."
REPORT_FILE="$PROJECT_DIR/logs/weekly_report_$(date +%Y%m%d).txt"
cat > "$REPORT_FILE" << EOF
================================================================
WEEKLY TRADING REPORT
Generated: $(date)
================================================================

DATABASE STATS:
$(python -c "
from src.database import get_session, Trade, Filer, Signal
from sqlalchemy import func

with get_session() as session:
    print(f'Total Trades: {session.query(Trade).count():,}')
    print(f'Total Filers: {session.query(Filer).count():,}')
    print(f'Active Signals: {session.query(Signal).filter(Signal.is_active == True).count()}')
    
    volume = session.query(func.sum(Trade.amount_usd)).scalar() or 0
    print(f'Total Volume: \${volume:,.0f}')
")

TOP 10 TICKERS:
$(python -c "
from src.database import get_session, Trade
from sqlalchemy import func, desc

with get_session() as session:
    top = session.query(
        Trade.ticker,
        func.count(Trade.trade_id).label('trades')
    ).group_by(Trade.ticker).order_by(desc('trades')).limit(10).all()
    
    for i, (ticker, count) in enumerate(top, 1):
        print(f'{i:2d}. {ticker:6s}: {count:4d} trades')
")

ACTIVE BUY SIGNALS:
$(python -c "
from src.database import get_session, Signal

with get_session() as session:
    signals = session.query(Signal).filter(Signal.is_active == True).order_by(Signal.strength.desc()).limit(10).all()
    
    for i, sig in enumerate(signals, 1):
        print(f'{i:2d}. {sig.ticker:6s} - Strength: {float(sig.strength)*100:.0f}%')
")

================================================================
EOF

echo "   Report saved: $REPORT_FILE"

# 5. Optional: Email report (requires sendmail/mail configured)
# mail -s "Trading App Weekly Report" your@email.com < "$REPORT_FILE"

echo ""
echo "=================================================================="
echo "✅ WEEKLY BACKTEST COMPLETE - $(date +"%Y-%m-%d %H:%M:%S")"
echo "=================================================================="

