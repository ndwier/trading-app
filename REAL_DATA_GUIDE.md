# 🚀 Getting Real Trading Data

## The Reality: Free vs Paid Data Sources

### ❌ Why Free Scrapers Don't Work Well

**Capitol Trades Scraper:**
- Website likely blocks automated scraping
- HTML structure changes frequently
- Rate limiting and CAPTCHAs
- **Result**: 0 trades collected

**SEC EDGAR Scraper:**
- Data has 5-10 day publishing delay
- Complex XML/text parsing
- Rate limiting (10 requests/second)
- Historical data only (Oct 2025 not available yet)
- **Result**: Works for old data only

### ✅ Why Paid APIs Are Worth It

For **serious trading analysis**, paid APIs are essential:
- ✅ Real-time or near-real-time data
- ✅ Clean, structured data (no parsing errors)
- ✅ Historical data going back years
- ✅ Reliable, no scraping issues
- ✅ Support and documentation

---

## 💰 Recommended Paid Data Sources

### 1. **Quiver Quantitative** (Best Overall)
- **Price**: $30-50/month
- **Data**: Congressional trading, lobbying, government contracts
- **Quality**: ⭐⭐⭐⭐⭐ Excellent
- **Coverage**: Politicians, some corporate insiders
- **API**: REST API, very clean

**Sign up**: https://www.quiverquant.com/sources/congresstrading

**Setup**:
```bash
# 1. Sign up and get API key
# 2. Add to your .env file:
QUIVER_API_KEY=your_key_here

# 3. Run ingestion:
cd /Users/natewier/Projects/trading-app
source venv/bin/activate
python scripts/run_ingestion.py --source politicians --days 365
```

### 2. **Finnhub** (Good Alternative)
- **Price**: $60/month
- **Data**: Congress trading + stock data
- **Quality**: ⭐⭐⭐⭐ Very good
- **Coverage**: Politicians, market data
- **API**: REST API

**Sign up**: https://finnhub.io/

**Setup**:
```bash
# 1. Sign up and get API key
# 2. Add to your .env file:
FINNHUB_API_KEY=your_key_here

# 3. Run ingestion:
python scripts/run_ingestion.py --source politicians --days 365
```

### 3. **Unusual Whales** (Premium Option)
- **Price**: $50-100/month
- **Data**: Options flow, dark pool, congress trades
- **Quality**: ⭐⭐⭐⭐⭐ Excellent
- **Coverage**: Very comprehensive
- **API**: REST API

**Sign up**: https://unusualwhales.com/

---

## 🆓 Using Demo Data (Current Setup)

**What you have now**:
- 89 realistic insider trades
- 20 filers (politicians + CEOs)
- 31 different stocks across sectors
- Multiple trading patterns
- 20 generated buy signals

**This is perfect for**:
- ✅ Learning the platform
- ✅ Testing strategies
- ✅ Developing features
- ✅ Understanding patterns
- ✅ Backtesting algorithms

**Demo data includes**:
- Cluster buying patterns (NVDA, MSFT, META, etc.)
- Bipartisan political interest
- CEO conviction trades
- Multiple sectors (tech, finance, defense, energy)
- Realistic amounts ($25K - $5M per trade)

---

## 📊 Comparison Table

| Source | Cost | Data Quality | Real-Time | Historical | Recommended |
|--------|------|-------------|-----------|------------|-------------|
| **Demo Data** | Free | Good | No | Yes | ✅ For learning |
| **Capitol Trades (free)** | Free | Poor | No | No | ❌ Doesn't work |
| **SEC EDGAR (free)** | Free | Medium | No | Yes (old) | ⚠️ Limited |
| **Quiver Quantitative** | $30-50/mo | Excellent | Near real-time | 5+ years | ✅✅ **Best** |
| **Finnhub** | $60/mo | Very Good | Real-time | 3+ years | ✅ Good |
| **Unusual Whales** | $50-100/mo | Excellent | Real-time | 2+ years | ✅ Premium |

---

## 🎯 Recommendation

### **For Development/Learning**: 
👉 **Use demo data** (already set up!)

### **For Live Trading**:
👉 **Get Quiver Quantitative** ($30-50/month)
- Best bang for buck
- Excellent politician trading data
- Easy API integration
- Historical data for backtesting

---

## 🛠️ How to Switch to Real Data

### Step 1: Get API Key
Sign up for Quiver Quantitative or Finnhub

### Step 2: Add to .env
```bash
cd /Users/natewier/Projects/trading-app
nano .env  # or open in your editor

# Add this line:
QUIVER_API_KEY=your_actual_key_here
```

### Step 3: Clear Demo Data
```bash
python scripts/switch_to_real_data.py
```

### Step 4: Fetch Real Data
```bash
# Get 1 year of historical data
python scripts/run_ingestion.py --source politicians --days 365

# Then generate signals
python scripts/generate_signals.py --portfolio-value 100000 --risk-tolerance moderate
```

### Step 5: Refresh Dashboard
Open `http://localhost:5000` and see real trades!

---

## 📝 Notes

- Free scrapers are unreliable by nature
- For $30-50/month, you get professional-grade data
- Demo data is sufficient for learning and testing
- Real trading requires real data

---

## ❓ Questions?

**Q: Can I try to fix the free scrapers?**
A: Yes, but it's time-consuming and fragile. Capitol Trades likely blocks scrapers, and SEC data requires complex parsing. For the time investment, $30/month is worth it.

**Q: Is demo data realistic enough?**
A: Yes! It includes realistic amounts, dates, patterns, and 89 trades across 31 stocks. Perfect for learning and testing strategies.

**Q: Which paid service should I choose?**
A: Start with **Quiver Quantitative** ($30-50/mo). Best value, excellent politician data, easy API.

**Q: Can I backtest with demo data?**
A: Absolutely! The demo data has realistic patterns and is great for developing and testing strategies.

