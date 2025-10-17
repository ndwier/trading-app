#!/bin/bash
#
# Overnight Data Collection & Signal Generation
# Run this script nightly to keep your data fresh
#
# Schedule with cron:
# crontab -e
# Add line: 0 2 * * * /Users/natewier/Projects/trading-app/scripts/overnight_update.sh >> /Users/natewier/Projects/trading-app/logs/overnight.log 2>&1
#

set -e

# Configuration
PROJECT_DIR="/Users/natewier/Projects/trading-app"
VENV_DIR="$PROJECT_DIR/venv"
TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

echo "=================================================================="
echo "🌙 OVERNIGHT UPDATE - $TIMESTAMP"
echo "=================================================================="

# Activate virtual environment
cd "$PROJECT_DIR"
source "$VENV_DIR/bin/activate"

# 1. Collect fresh data (last 7 days)
echo ""
echo "📥 Step 1: Collecting fresh insider trades..."
python scripts/run_ingestion.py --source finnhub --days 7 || echo "⚠️  Finnhub failed"
python scripts/run_ingestion.py --source openinsider --days 7 || echo "⚠️  OpenInsider failed"

# 2. Generate new signals
echo ""
echo "🎯 Step 2: Generating trading signals..."
python scripts/generate_signals.py \
    --portfolio-value 100000 \
    --risk-tolerance moderate \
    --top-n 20 || echo "⚠️  Signal generation failed"

# 3. Check database stats
echo ""
echo "📊 Step 3: Database statistics..."
python -c "
from src.database import get_session, Trade, Signal
from sqlalchemy import func

with get_session() as session:
    trades = session.query(Trade).count()
    signals = session.query(Signal).filter(Signal.is_active == True).count()
    
    print(f'   Total Trades: {trades:,}')
    print(f'   Active Signals: {signals}')
"

# 4. Cleanup old logs (keep last 30 days)
echo ""
echo "🧹 Step 4: Cleanup old logs..."
find "$PROJECT_DIR/logs" -name "*.log" -mtime +30 -delete 2>/dev/null || true
echo "   Cleanup complete"

# 5. Git commit if significant changes
echo ""
echo "💾 Step 5: Checking for significant data changes..."
TRADE_CHANGE=$(git diff data/ | wc -l)
if [ "$TRADE_CHANGE" -gt 100 ]; then
    echo "   Significant changes detected, committing..."
    git add data/ || true
    git commit -m "chore: Overnight data update - $TIMESTAMP" || true
    # Uncomment to auto-push:
    # git push origin main || echo "⚠️  Push failed"
else
    echo "   No significant changes"
fi

echo ""
echo "=================================================================="
echo "✅ OVERNIGHT UPDATE COMPLETE - $(date +"%Y-%m-%d %H:%M:%S")"
echo "=================================================================="

