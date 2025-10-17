# 🌙 Overnight Automation Guide

**Set it and forget it** - Automate your trading data collection and signal generation.

---

## 🎯 What Gets Automated

### Nightly (Every Day at 2 AM)
✅ Collect fresh insider trades (last 7 days)  
✅ Update from Finnhub + OpenInsider  
✅ Generate new trading signals  
✅ Update database statistics  
✅ Clean up old logs (>30 days)  
✅ Auto-commit significant data changes  

### Weekly (Sundays at 3 AM)
✅ Collect full 90-day dataset  
✅ Run backtests (when implemented)  
✅ Generate performance report  
✅ Analyze top tickers  
✅ Email weekly summary (optional)  

---

## 🚀 Quick Setup (2 Minutes)

### Option 1: Automatic Setup
```bash
cd /Users/natewier/Projects/trading-app

# Run the setup script
./scripts/setup_automation.sh

# Schedule the tasks (copy-paste this entire line)
(crontab -l 2>/dev/null; echo "# Trading App Automation"; echo "0 2 * * * /Users/natewier/Projects/trading-app/scripts/overnight_update.sh >> /Users/natewier/Projects/trading-app/logs/overnight.log 2>&1"; echo "0 3 * * 0 /Users/natewier/Projects/trading-app/scripts/weekly_backtest.sh >> /Users/natewier/Projects/trading-app/logs/weekly.log 2>&1") | crontab -

# Verify it's scheduled
crontab -l
```

### Option 2: Manual Setup
```bash
# Open cron editor
crontab -e

# Add these two lines (press 'i' to insert, 'Esc' then ':wq' to save):
0 2 * * * /Users/natewier/Projects/trading-app/scripts/overnight_update.sh >> /Users/natewier/Projects/trading-app/logs/overnight.log 2>&1
0 3 * * 0 /Users/natewier/Projects/trading-app/scripts/weekly_backtest.sh >> /Users/natewier/Projects/trading-app/logs/weekly.log 2>&1
```

---

## 🧪 Test Before Scheduling

### Test Overnight Update
```bash
cd /Users/natewier/Projects/trading-app
./scripts/overnight_update.sh
```

**Expected output:**
```
🌙 OVERNIGHT UPDATE - 2025-10-17 02:00:00
📥 Step 1: Collecting fresh insider trades...
🎯 Step 2: Generating trading signals...
📊 Step 3: Database statistics...
   Total Trades: 2,600+
   Active Signals: 40+
🧹 Step 4: Cleanup old logs...
💾 Step 5: Checking for significant data changes...
✅ OVERNIGHT UPDATE COMPLETE
```

### Test Weekly Backtest
```bash
cd /Users/natewier/Projects/trading-app
./scripts/weekly_backtest.sh
```

**Expected output:**
```
📈 WEEKLY BACKTEST - 2025-10-17 03:00:00
📥 Step 1: Collecting 90-day dataset...
🧪 Step 2: Running backtests...
📊 Step 3: Performance analysis...
📝 Step 4: Generating weekly report...
✅ WEEKLY BACKTEST COMPLETE
```

---

## 📊 What You'll Get

### Daily (After Each Run)
- **Fresh Data**: Latest 7 days of insider trades
- **New Signals**: Updated buy/sell recommendations
- **Log File**: `logs/overnight.log` with full output
- **Stats Update**: Trade count, signal count

### Weekly (Every Sunday)
- **Full Dataset**: 90 days of trades
- **Performance Report**: `logs/weekly_report_YYYYMMDD.txt`
- **Top Tickers**: What's hot this week
- **Signal Analysis**: Which signals are performing

---

## 📝 Monitoring Your Automation

### Check Last Run
```bash
# View overnight log
tail -50 /Users/natewier/Projects/trading-app/logs/overnight.log

# View weekly log
tail -50 /Users/natewier/Projects/trading-app/logs/weekly.log

# Check last weekly report
ls -lt /Users/natewier/Projects/trading-app/logs/weekly_report_*.txt | head -1
```

### View Scheduled Jobs
```bash
crontab -l
```

### Disable Automation
```bash
# Remove scheduled jobs
crontab -r

# Or edit and comment out
crontab -e
# Add # at start of lines to disable
```

---

## 🛠️ Customization

### Change Schedule

Edit cron times (format: minute hour day month weekday):
```bash
crontab -e

# Examples:
# Run at 3 AM instead of 2 AM:
0 3 * * * /path/to/overnight_update.sh

# Run twice daily (2 AM and 2 PM):
0 2,14 * * * /path/to/overnight_update.sh

# Run on weekdays only:
0 2 * * 1-5 /path/to/overnight_update.sh
```

### Customize Collection Period

Edit `scripts/overnight_update.sh`:
```bash
# Change --days parameter
python scripts/run_ingestion.py --source finnhub --days 14  # Get 14 days instead of 7
```

### Add Email Notifications

Install mail utility (if not already):
```bash
# macOS usually has it
which mail

# If not, install with Homebrew:
brew install mailutils
```

Edit scripts to add email:
```bash
# At end of overnight_update.sh:
echo "Overnight update complete. $trades new trades." | mail -s "Trading App Update" your@email.com

# At end of weekly_backtest.sh:
mail -s "Weekly Trading Report" your@email.com < logs/weekly_report_$(date +%Y%m%d).txt
```

---

## 🔍 Troubleshooting

### Scripts Not Running?

**Check cron is working:**
```bash
# macOS: Ensure cron has Full Disk Access
# System Preferences → Security & Privacy → Privacy → Full Disk Access
# Add: /usr/sbin/cron
```

**Check script permissions:**
```bash
ls -la /Users/natewier/Projects/trading-app/scripts/*.sh
# Should show: -rwxr-xr-x (executable)

# If not:
chmod +x /Users/natewier/Projects/trading-app/scripts/*.sh
```

**Check Python virtual environment:**
```bash
# Verify venv exists
ls /Users/natewier/Projects/trading-app/venv/bin/python

# Test manually
source /Users/natewier/Projects/trading-app/venv/bin/activate
python --version
```

### No Data Being Collected?

**Check API keys:**
```bash
# Verify .env file exists and has keys
cat /Users/natewier/Projects/trading-app/.env | grep API_KEY

# Finnhub key should be set
echo $FINNHUB_API_KEY
```

**Test scraper manually:**
```bash
cd /Users/natewier/Projects/trading-app
source venv/bin/activate
python scripts/run_ingestion.py --source finnhub --days 7
```

### Logs Not Being Created?

**Create logs directory:**
```bash
mkdir -p /Users/natewier/Projects/trading-app/logs
chmod 755 /Users/natewier/Projects/trading-app/logs
```

**Check cron redirection:**
```bash
# Cron line should include:
>> /path/to/logs/overnight.log 2>&1
```

---

## 📈 Expected Performance

### Daily Collection
- **Runtime**: 2-5 minutes
- **New Trades**: 20-50 per day
- **Signals**: 30-40 active
- **Database Size**: Grows ~1MB/day

### Weekly Backtest
- **Runtime**: 5-10 minutes
- **Full Dataset**: 90 days refresh
- **Report Size**: ~5KB text file

### Resource Usage
- **CPU**: <5% during run
- **Memory**: ~100MB
- **Disk**: ~1GB total (database + logs)
- **Network**: ~10MB download per run

---

## 🎯 Recommended Schedule

For most users:
```bash
# Nightly at 2 AM (after markets close, before pre-market)
0 2 * * * overnight_update.sh

# Weekly on Sunday at 3 AM (quiet time, full refresh)
0 3 * * 0 weekly_backtest.sh
```

For active traders:
```bash
# Twice daily (morning and evening)
0 2,14 * * * overnight_update.sh

# Twice weekly
0 3 * * 0,3 weekly_backtest.sh
```

---

## 💡 Pro Tips

1. **Start Small**: Run nightly for a week before adding weekly
2. **Monitor Logs**: Check first few runs to ensure working
3. **Set Alerts**: Use email notifications for critical errors
4. **Backup Database**: Weekly `cp data/trading_app.db data/backup_$(date +%Y%m%d).db`
5. **Clean Up**: Old logs are auto-deleted after 30 days

---

## 🚀 Advanced: Run on Remote Server

Want to run this on a cloud server? Here's the setup:

```bash
# SSH into your server
ssh user@your-server.com

# Clone your repo
git clone https://github.com/ndwier/trading-app.git
cd trading-app

# Setup virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy your .env file (with API keys)
scp .env user@your-server.com:~/trading-app/

# Setup automation
./scripts/setup_automation.sh

# Schedule jobs
crontab -e
# Add the cron lines

# Done! Now it runs 24/7 in the cloud
```

---

## 📋 Checklist

Before going live:

- [ ] Scripts are executable (`chmod +x`)
- [ ] Virtual environment works (`source venv/bin/activate`)
- [ ] API keys in `.env` file
- [ ] Tested manually (`./scripts/overnight_update.sh`)
- [ ] Cron jobs scheduled (`crontab -l`)
- [ ] Logs directory created (`mkdir -p logs`)
- [ ] First run completed successfully
- [ ] Dashboard accessible (http://localhost:5000)
- [ ] Email notifications configured (optional)

---

## 🎉 You're All Set!

Your trading app will now:
✅ Collect data every night while you sleep  
✅ Generate fresh signals daily  
✅ Run weekly performance analysis  
✅ Keep everything up-to-date automatically  

**Just wake up and check your dashboard!** ☕📊

---

**Questions?** Check the logs or run scripts manually to debug.

**Working great?** Sit back and let the automation work for you! 🚀

