# Insider Trading Analysis Platform

A comprehensive platform for analyzing trading patterns of politicians, executives, billionaires, and renowned investors to identify profitable trading signals and strategies.

## Features

### 🎯 Personal Investment Signals
- **AI-Powered Recommendations**: Actionable buy/sell/hold signals for your portfolio
- **Risk-Adjusted Position Sizing**: Automatic position sizing based on confidence and risk tolerance
- **Target Prices & Stop Losses**: Clear entry and exit points for each recommendation
- **Portfolio Allocation**: Comprehensive allocation recommendations with cash management

### 📊 Data Sources
- **Political Trades**: Congressional trading disclosures (STOCK Act)
- **Corporate Insiders**: SEC Forms 3, 4, 5 filings
- **Billionaires/Investors**: High-profile investor portfolio changes
- **Free APIs**: SEC EDGAR, Quiver Quantitative (limited), OpenInsider

### 🔍 Pattern Recognition
- **Unusual Volume**: Detect abnormal insider trading activity
- **Consensus Buying**: Multiple insiders buying same stock
- **Bipartisan Interest**: Cross-party political agreement
- **Insider Momentum**: Repeated buying by same insiders
- **Signal Strength Classification**: Weak, Moderate, Strong, Very Strong

### 📈 Analytics & Backtesting
- Historical pattern analysis and signal generation
- Strategy backtesting with realistic transaction costs
- Performance metrics: Sharpe ratio, alpha, max drawdown
- Portfolio simulation with configurable parameters
- Signal performance tracking and validation

### Key Strategies
1. **Lag Trade**: Buy/sell X days after disclosure
2. **Clustering**: Multiple insiders trading same ticker
3. **Repeat Behavior**: Follow historically profitable traders
4. **Thematic Flow**: Sector-based insider momentum
5. **Conviction Filter**: Large position size requirements
6. **Alignment**: Corporate + political insider convergence

## Quick Start

```bash
# Clone and setup
git clone <repository_url>
cd trading-app
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Setup database
python scripts/setup_db.py

# Collect insider trading data
python scripts/run_ingestion.py --source all --days 30

# Generate personal investment signals
python scripts/generate_signals.py --portfolio-value 100000 --risk-tolerance moderate

# Start web dashboard
python app.py
# Visit http://localhost:5000

# Run backtests (optional)
python -m src.backtesting.backtester --strategy all
```

## Project Structure

```
trading-app/
├── src/
│   ├── ingestion/          # Data collection modules
│   ├── database/           # Database models and operations
│   ├── backtesting/        # Strategy testing framework
│   ├── analysis/           # Pattern recognition and signals
│   └── web/               # Flask web interface
├── config/                # Configuration files
├── scripts/               # Utility scripts
├── tests/                 # Unit tests
├── data/                  # Local data storage
└── docs/                  # Documentation
```

## Legal Disclaimer

This tool is for educational and research purposes only. It provides information about publicly disclosed trading activities and should not be considered financial advice. Always conduct your own research and consult with financial professionals before making investment decisions.

## Contributing

This is a personal research project. Feel free to fork and adapt for your own use.
