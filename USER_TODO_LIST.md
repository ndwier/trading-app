# 📋 Your TODO List - API Keys & Manual Setup

**Last Updated**: October 17, 2025

---

## 🔑 REQUIRED: Free API Keys (30 Minutes Total)

These will unlock additional data sources and features:

### Priority 1: High Value, Easy Setup (10 min)

#### 1. Alpha Vantage (Stock Prices + News)
- **Sign up**: https://www.alphavantage.co/support/#api-key
- **Cost**: FREE (500 calls/day)
- **Value**: Price data backup, news sentiment
- **Add to `.env`**:
  ```
  ALPHA_VANTAGE_API_KEY=your_key_here
  ```

#### 2. FRED API (Economic Data)
- **Sign up**: https://fred.stlouisfed.org/docs/api/api_key.html
- **Cost**: FREE (unlimited)
- **Value**: GDP, inflation, interest rates
- **Add to `.env`**:
  ```
  FRED_API_KEY=your_key_here
  ```

#### 3. Tiingo (Reliable EOD Prices)
- **Sign up**: https://www.tiingo.com/
- **Cost**: FREE tier (excellent)
- **Value**: Very reliable price data
- **Add to `.env`**:
  ```
  TIINGO_API_KEY=your_key_here
  ```

### Priority 2: Additional Coverage (10 min)

#### 4. Polygon.io (News + Price Data)
- **Sign up**: https://polygon.io/
- **Cost**: FREE tier (limited but good)
- **Value**: Real-time news, tick data
- **Add to `.env`**:
  ```
  POLYGON_API_KEY=your_key_here
  ```

#### 5. IEX Cloud (Market Data)
- **Sign up**: https://iexcloud.io/
- **Cost**: FREE tier available
- **Value**: Fundamentals, market data
- **Add to `.env`**:
  ```
  IEX_API_KEY=your_key_here
  ```

#### 6. OpenSecrets (Political Donations)
- **Sign up**: https://www.opensecrets.org/api/admin/
- **Cost**: FREE
- **Value**: Correlate politician trades with donors
- **Add to `.env`**:
  ```
  OPENSECRETS_API_KEY=your_key_here
  ```

### Priority 3: Bulk Data (10 min)

#### 7. Kaggle (Historical Datasets)
- **Sign up**: https://www.kaggle.com/
- **Get API Key**: Account → Settings → Create New API Token
- **Cost**: FREE
- **Value**: Years of historical trading data
- **Add to `.env`**:
  ```
  KAGGLE_USERNAME=your_username
  KAGGLE_KEY=your_api_key
  ```

---

## 💰 OPTIONAL: Paid API Keys (High Value)

These are worth considering if you want premium data:

### Option 1: Politician Trading ($30-50/month)

#### Quiver Quantitative ⭐ RECOMMENDED
- **Sign up**: https://www.quiverquant.com/
- **Cost**: $30-50/month
- **Value**: Best politician trading data, cleaned and structured
- **What you get**: Congress, Senate, House trades + committee data
- **Add to `.env`**:
  ```
  QUIVER_API_KEY=your_key_here
  ```

### Option 2: Options Flow ($50-300/month)

#### Unusual Whales
- **Sign up**: https://unusualwhales.com/
- **Cost**: $50-300/month depending on tier
- **Value**: Options flow, dark pool, unusual activity
- **What you get**: Smart money tracking, institutional flows
- **Add to `.env`**:
  ```
  UNUSUAL_WHALES_API_KEY=your_key_here
  ```

#### FlowAlgo (Alternative)
- **Sign up**: https://www.flowalgo.com/
- **Cost**: Similar to Unusual Whales
- **Value**: Options flow alerts
- **Add to `.env`**:
  ```
  FLOWALGO_API_KEY=your_key_here
  ```

### Option 3: Institutional Data ($200-500/month)

#### WhaleWisdom
- **Sign up**: https://whalewisdom.com/api
- **Cost**: $200-500/month
- **Value**: Deep 13F analysis, institutional ownership
- **What you get**: Billionaire portfolio tracking, ownership changes
- **Add to `.env`**:
  ```
  WHALE_WISDOM_API_KEY=your_key_here
  ```

#### Quandl Premium
- **Sign up**: https://data.nasdaq.com/
- **Cost**: Varies by dataset
- **Value**: Premium financial datasets
- **Add to `.env`**:
  ```
  QUANDL_API_KEY=your_key_here
  ```

---

## 🏦 BROKER APIs (For Live Trading)

### Schwab API
- **Sign up**: https://developer.schwab.com/
- **Requirements**: 
  - Active Schwab brokerage account
  - Apply for developer access
  - OAuth 2.0 setup
- **Timeline**: 1-2 weeks approval
- **What you get**: Live trading, portfolio management
- **Add to `.env`**:
  ```
  SCHWAB_CLIENT_ID=your_client_id
  SCHWAB_CLIENT_SECRET=your_secret
  ```

### E-Trade API
- **Sign up**: https://developer.etrade.com/
- **Requirements**:
  - Active E-Trade account
  - Developer application
  - API keys approval
- **Timeline**: 1-2 weeks approval
- **What you get**: Trading API, account management
- **Add to `.env`**:
  ```
  ETRADE_CONSUMER_KEY=your_key
  ETRADE_CONSUMER_SECRET=your_secret
  ```

### Interactive Brokers (Alternative)
- **Sign up**: https://www.interactivebrokers.com/
- **Requirements**: Active IB account
- **Timeline**: Immediate (after account opening)
- **What you get**: TWS API, very powerful
- **Best for**: Advanced traders, algorithmic trading

---

## 🛠️ MANUAL SETUP TASKS

### 1. Install Optional Dependencies

#### For House PDF Scraping:
```bash
pip install pdfplumber
```

#### For Kaggle Datasets:
```bash
pip install kaggle
```

#### For Advanced Analysis:
```bash
pip install lxml html5lib statsmodels
```

### 2. Schedule Overnight Automation

Run once to set up nightly updates:
```bash
cd /Users/natewier/Projects/trading-app
./scripts/setup_automation.sh

# Then schedule:
(crontab -l 2>/dev/null; echo "0 2 * * * /Users/natewier/Projects/trading-app/scripts/overnight_update.sh >> /Users/natewier/Projects/trading-app/logs/overnight.log 2>&1") | crontab -
```

### 3. Enable macOS Permissions (If automation not working)

**System Preferences → Security & Privacy → Privacy**
- ✅ Full Disk Access → Add `/usr/sbin/cron`
- ✅ Full Disk Access → Add Terminal
- ✅ Automation → Allow Terminal

---

## 📊 RECOMMENDED SETUP ORDER

### Week 1: Free Essentials (Do Now)
1. ✅ Alpha Vantage (10 min)
2. ✅ FRED (5 min)
3. ✅ Tiingo (10 min)
4. ✅ Schedule overnight automation (5 min)

**Total**: 30 minutes, $0 cost

### Week 2: Enhanced Coverage
5. ✅ Polygon.io (10 min)
6. ✅ IEX Cloud (10 min)
7. ✅ OpenSecrets (5 min)
8. ✅ Kaggle (10 min)

**Total**: 35 minutes, $0 cost

### Month 1: Consider Paid (Optional)
9. 💰 Quiver Quantitative ($30-50/month)
   - If you want politician trading data
10. 💰 Unusual Whales ($50-300/month)
    - If you want options flow data

### Month 2-3: Broker APIs (For Live Trading)
11. 🏦 Apply for Schwab API (1-2 weeks)
12. 🏦 Apply for E-Trade API (1-2 weeks)

---

## ✅ QUICK START (30 Minutes)

Copy this into your terminal and follow the links:

```bash
# 1. Open .env file
cd /Users/natewier/Projects/trading-app
nano .env

# 2. Visit these sites and get API keys:
# - https://www.alphavantage.co/support/#api-key
# - https://fred.stlouisfed.org/docs/api/api_key.html
# - https://www.tiingo.com/

# 3. Add keys to .env:
# ALPHA_VANTAGE_API_KEY=your_key
# FRED_API_KEY=your_key
# TIINGO_API_KEY=your_key

# 4. Save and test:
# Ctrl+X, Y, Enter

# 5. Test data collection:
python scripts/run_ingestion.py --source all --days 7

# 6. Check dashboard:
python app.py
# Visit: http://localhost:5000
```

---

## 📈 IMPACT BY TIER

### Free Keys Only ($0/month)
- ✅ 2,500+ trades/month
- ✅ 6 data sources active
- ✅ Economic indicators
- ✅ News sentiment
- ✅ Historical datasets (Kaggle)
- **Good for**: Most retail traders

### Free + Quiver ($30-50/month)
- ✅ Everything above, plus:
- ✅ 3,000+ trades/month
- ✅ Politician trading data
- ✅ Committee assignments
- ✅ Full Congress coverage
- **Good for**: Serious investors

### Free + Quiver + Unusual Whales ($80-350/month)
- ✅ Everything above, plus:
- ✅ Options flow tracking
- ✅ Dark pool activity
- ✅ Smart money alerts
- ✅ Institutional positioning
- **Good for**: Active traders

### Full Suite ($300-600/month)
- ✅ Everything above, plus:
- ✅ WhaleWisdom (institutional)
- ✅ Premium datasets (Quandl)
- ✅ Real-time everything
- ✅ Broker API integration
- **Good for**: Professional traders

---

## 🎯 RECOMMENDATION

**Start with FREE tier** (Tasks 1-8 above, 65 minutes total):
- You'll have 6+ data sources
- 2,500+ trades per month
- Economic indicators
- News sentiment
- Historical analysis via Kaggle
- **Cost**: $0/month

**After 1 month**, if you love the app:
- Add Quiver ($30-50/month) for politician trades
- This unlocks another 500+ trades/month
- **Total cost**: $30-50/month

**After 3 months**, if you're actively trading:
- Add Unusual Whales ($50-300/month) for options flow
- Apply for broker APIs for live trading
- **Total cost**: $80-350/month

---

## 📋 CHECKLIST

Print this and check off as you go:

**Free APIs (Do First):**
- [ ] Alpha Vantage API key
- [ ] FRED API key  
- [ ] Tiingo API key
- [ ] Polygon.io API key
- [ ] IEX Cloud API key
- [ ] OpenSecrets API key
- [ ] Kaggle credentials

**Optional Dependencies:**
- [ ] Install pdfplumber
- [ ] Install kaggle package
- [ ] Install advanced analysis packages

**Automation:**
- [ ] Schedule nightly updates (cron)
- [ ] Schedule weekly backtests (cron)
- [ ] Test automation scripts
- [ ] Verify logs are being created

**Paid APIs (Optional):**
- [ ] Quiver Quantitative ($30-50/mo)
- [ ] Unusual Whales ($50-300/mo)
- [ ] WhaleWisdom ($200-500/mo)

**Broker APIs (For Live Trading):**
- [ ] Apply for Schwab developer access
- [ ] Apply for E-Trade developer access
- [ ] Set up OAuth credentials
- [ ] Test paper trading first

---

## ❓ FAQ

**Q: Do I need ALL the API keys?**
A: No! Start with the free ones (Alpha Vantage, FRED, Tiingo). You already have 2,500+ trades with Finnhub + OpenInsider.

**Q: Which paid API should I get first?**
A: Quiver Quantitative ($30-50/month) for politician trades. Best value.

**Q: How long do API approvals take?**
A: Free APIs: Instant. Paid APIs: Instant. Broker APIs: 1-2 weeks.

**Q: Can I use this without any new API keys?**
A: Yes! You already have 2,584 trades from Finnhub + OpenInsider. New keys just add more data.

**Q: What if I can't afford paid APIs?**
A: The free tier is excellent! You have institutional-grade data with $0/month cost.

---

## 🚀 NEXT STEPS

1. **Today**: Get 3 free API keys (Alpha Vantage, FRED, Tiingo) - 30 min
2. **This Week**: Get remaining free keys - 30 min
3. **This Month**: Consider Quiver if you want politician data - $30-50/mo
4. **Later**: Apply for broker APIs when ready for live trading

---

**Questions?** Everything is documented in `ALL_DATA_SOURCES.md`

**Ready to start?** Pick the free APIs above and spend 30 minutes setting up!

