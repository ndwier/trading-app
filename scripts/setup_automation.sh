#!/bin/bash
#
# Setup Automation - Schedule overnight tasks
#

PROJECT_DIR="/Users/natewier/Projects/trading-app"

echo "=================================================================="
echo "🤖 SETTING UP AUTOMATION"
echo "=================================================================="

# Make scripts executable
echo ""
echo "Step 1: Making scripts executable..."
chmod +x "$PROJECT_DIR/scripts/overnight_update.sh"
chmod +x "$PROJECT_DIR/scripts/weekly_backtest.sh"
echo "✅ Scripts are now executable"

# Create logs directory if needed
echo ""
echo "Step 2: Setting up logs directory..."
mkdir -p "$PROJECT_DIR/logs"
echo "✅ Logs directory ready"

# Show current crontab
echo ""
echo "Step 3: Current cron jobs:"
crontab -l 2>/dev/null || echo "   (No cron jobs scheduled yet)"

# Provide setup instructions
echo ""
echo "=================================================================="
echo "📋 TO SCHEDULE AUTOMATED TASKS:"
echo "=================================================================="
echo ""
echo "Run: crontab -e"
echo ""
echo "Then add these lines:"
echo ""
echo "# Trading App: Nightly data collection at 2 AM"
echo "0 2 * * * $PROJECT_DIR/scripts/overnight_update.sh >> $PROJECT_DIR/logs/overnight.log 2>&1"
echo ""
echo "# Trading App: Weekly backtest on Sundays at 3 AM"
echo "0 3 * * 0 $PROJECT_DIR/scripts/weekly_backtest.sh >> $PROJECT_DIR/logs/weekly.log 2>&1"
echo ""
echo "=================================================================="
echo ""
echo "OR, to schedule them NOW automatically:"
echo ""
echo "Run this command:"
echo "=================================================================="
cat << 'EOF'
(crontab -l 2>/dev/null; echo "# Trading App Automation"; echo "0 2 * * * /Users/natewier/Projects/trading-app/scripts/overnight_update.sh >> /Users/natewier/Projects/trading-app/logs/overnight.log 2>&1"; echo "0 3 * * 0 /Users/natewier/Projects/trading-app/scripts/weekly_backtest.sh >> /Users/natewier/Projects/trading-app/logs/weekly.log 2>&1") | crontab -
EOF
echo "=================================================================="
echo ""
echo "To verify: crontab -l"
echo ""
echo "To test manually:"
echo "  $PROJECT_DIR/scripts/overnight_update.sh"
echo "  $PROJECT_DIR/scripts/weekly_backtest.sh"
echo ""
echo "=================================================================="

