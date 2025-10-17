# Getting Started with the Insider Trading Analysis Platform

This guide will help you set up and start using the insider trading analysis platform to track and analyze trades from politicians, corporate insiders, and other high-profile investors.

## 🚀 Quick Setup (5 minutes)

### 1. Install Dependencies

```bash
# Navigate to the project directory
cd /Users/natewier/Projects/trading-app

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy environment template
cp env_template.txt .env

# Edit .env file with your preferences (optional - works with defaults)
nano .env  # or your preferred editor
```

### 3. Initialize Database

```bash
# Set up database and directories
python scripts/setup_db.py
```

### 4. Start the Application

```bash
# Start the web interface
python app.py
```

Visit `http://localhost:5000` to see your dashboard!

## 📊 Basic Usage

### Running Data Ingestion

The platform can collect data from multiple free sources:

```bash
# Collect recent politician trades (last 30 days)
python scripts/run_ingestion.py --source politicians --days 30

# Collect SEC insider filings (last 7 days - high volume)
python scripts/run_ingestion.py --source sec --days 7

# Collect from all sources with normalization
python scripts/run_ingestion.py --source all --days 14 --normalize
```

### Running Backtests

Test trading strategies based on insider activity:

```bash
# Test lag trade strategy (buy 2 days after disclosure)
python -m src.backtesting.backtester --strategy lag --start 2023-01-01 --end 2024-01-01

# Compare multiple strategies
python -m src.backtesting.backtester --strategy all --start 2023-01-01 --end 2024-01-01
```

### Pattern Detection

Identify interesting trading patterns:

```bash
# Detect all patterns in last 90 days
python -m src.analysis.pattern_detector --days 90

# Look for unusual volume patterns
python -m src.analysis.pattern_detector --pattern unusual_volume --days 60
```

## 🔧 Configuration Options

### API Keys (Optional)

While the platform works with free data sources, paid APIs provide more comprehensive data:

```bash
# Add to your .env file:
QUIVER_API_KEY=your_quiver_key_here
FINNHUB_API_KEY=your_finnhub_key_here
ALPHA_VANTAGE_API_KEY=your_av_key_here
```

### Database Options

**SQLite (Default - No Setup Required):**
```bash
DATABASE_URL=sqlite:///data/trading_app.db
```

**PostgreSQL (For Production):**
```bash
DATABASE_URL=postgresql://username:password@localhost:5432/trading_app
```

## 📈 Core Features

### 1. Data Sources
- **Politicians**: Congressional trading disclosures (STOCK Act)
- **Corporate Insiders**: SEC Forms 3, 4, 5
- **Free APIs**: Capitol Trades, OpenInsider, SEC EDGAR
- **Paid APIs**: Quiver Quantitative, Finnhub (optional)

### 2. Trading Strategies
- **Lag Trade**: Buy X days after insider disclosure
- **Cluster Strategy**: Multiple insiders buying same stock
- **Bipartisan Strategy**: Both political parties buying
- **Custom Strategies**: Extend BaseStrategy class

### 3. Pattern Recognition
- **Unusual Volume**: Stocks with abnormal insider activity
- **Consensus Buying**: Multiple different insiders buying
- **Insider Momentum**: Repeated buying by same insiders
- **Bipartisan Interest**: Cross-party political interest

### 4. Performance Analysis
- **Returns**: Total, annual, risk-adjusted
- **Risk Metrics**: Sharpe ratio, max drawdown, VaR
- **Trade Analysis**: Win rate, profit factor, average returns
- **Benchmarking**: Compare against market indices

## 🎯 Example Workflows

### Workflow 1: Daily Monitoring
```bash
# Morning routine - collect overnight data
python scripts/run_ingestion.py --source all --days 1

# Detect new patterns
python -m src.analysis.pattern_detector --days 7

# Check dashboard
python app.py  # Visit localhost:5000
```

### Workflow 2: Strategy Development
```bash
# 1. Collect historical data
python scripts/run_ingestion.py --source all --days 365

# 2. Normalize and clean data
python -m src.ingestion.data_normalizer --trades

# 3. Fetch price data for backtesting
python -m src.ingestion.data_normalizer --prices

# 4. Run backtests
python -m src.backtesting.backtester --strategy all --start 2023-01-01 --end 2024-01-01

# 5. Analyze results in dashboard
python app.py
```

### Workflow 3: Research & Analysis
```bash
# 1. Large data collection
python scripts/run_ingestion.py --source all --days 730  # 2 years

# 2. Pattern analysis
python -m src.analysis.pattern_detector --days 180

# 3. Strategy comparison
python -m src.backtesting.backtester --strategy all --start 2022-01-01 --end 2024-01-01

# 4. Export results for further analysis
# Results available in dashboard and database
```

## 📁 Project Structure

```
trading-app/
├── src/
│   ├── ingestion/          # Data collection
│   │   ├── politician_scraper.py
│   │   ├── sec_scraper.py
│   │   └── data_normalizer.py
│   ├── database/           # Database models
│   │   ├── models.py
│   │   └── connection.py
│   ├── backtesting/        # Strategy testing
│   │   ├── base_strategy.py
│   │   ├── backtester.py
│   │   └── performance_metrics.py
│   ├── analysis/           # Pattern recognition
│   │   └── pattern_detector.py
│   └── web/               # Web interface
├── scripts/               # Utility scripts
│   ├── setup_db.py
│   └── run_ingestion.py
├── config/               # Configuration
│   └── config.py
├── data/                 # Local data storage
└── app.py               # Main web application
```

## 🔍 Understanding the Data

### Trade Types
- **Buy/Sell**: Standard stock transactions
- **Options**: Call and put option trades
- **Gifts/Transfers**: Non-market transactions

### Filer Types
- **Politicians**: Congress members and their families
- **Corporate Insiders**: Executives, directors, major shareholders
- **Billionaires/Investors**: High-profile investors (future feature)

### Key Metrics
- **Amount**: Transaction value in USD
- **Disclosure Lag**: Days between trade and public disclosure
- **Position Size**: Relative to filer's reported net worth
- **Clustering**: Multiple filers trading same stock

## ⚠️ Important Notes

### Legal & Ethical
- **Educational Purpose**: This tool is for research and education only
- **Not Financial Advice**: Do not use as sole basis for investment decisions
- **Public Data**: Only uses publicly disclosed information
- **Reporting Delays**: Insider trades may not be disclosed for 45+ days

### Data Limitations
- **Disclosure Delays**: Trades may be reported weeks after execution
- **Incomplete Data**: Not all trades are properly disclosed
- **Estimated Values**: Some amounts are ranges or estimates
- **False Positives**: Pattern detection may identify noise as signals

### Performance Considerations
- **Rate Limiting**: APIs have request limits
- **Data Volume**: SEC filings generate large amounts of data
- **Storage**: Historical data can require significant disk space
- **Processing**: Backtests on large datasets may take time

## 🛠️ Troubleshooting

### Common Issues

**Database Connection Errors:**
```bash
# Reset database
python scripts/setup_db.py

# Check database status
python -m src.database.connection info
```

**No Data After Ingestion:**
```bash
# Check ingestion logs
ls logs/
cat logs/ingestion_*.log

# Verify data sources
python -m src.ingestion.politician_scraper --days 1
```

**Backtest Errors:**
```bash
# Ensure price data is available
python -m src.ingestion.data_normalizer --prices

# Check for data normalization issues
python -m src.ingestion.data_normalizer --trades --limit 100
```

**Web Interface Issues:**
```bash
# Check configuration
python -c "from config.config import config; print(config.web.HOST, config.web.PORT)"

# Reset Flask session
rm -rf flask_session/
```

## 📚 Next Steps

1. **Explore the Dashboard**: Start with the web interface to understand your data
2. **Run Sample Backtests**: Test the provided strategies on historical data
3. **Develop Custom Strategies**: Extend BaseStrategy for your own trading logic
4. **Set Up Monitoring**: Create automated ingestion and alerting
5. **Analyze Patterns**: Use pattern detection to find interesting opportunities

## 🤝 Contributing

This is a personal research project, but you can:
- Fork the repository for your own use
- Extend strategies and analysis modules
- Add new data sources
- Improve pattern detection algorithms

## 📞 Support

For issues:
1. Check the logs in `logs/` directory
2. Review configuration in `config/config.py`
3. Verify database status with `python -m src.database.connection info`
4. Test individual components separately

Happy trading analysis! 📊🚀
