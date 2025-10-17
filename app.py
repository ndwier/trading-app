#!/usr/bin/env python3
"""Main Flask application for the Trading App."""

import os
import sys
from pathlib import Path
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.config import config
from src.database import get_session, Trade, Filer, Strategy, Backtest, Signal, PortfolioTransaction
from src.ingestion.politician_scraper import PoliticianScraper
from src.ingestion.sec_scraper import SECScraper
from src.analysis.signal_generator import SignalGenerator
from src.analysis.portfolio_manager import PortfolioManager


def create_app():
    """Create Flask application."""
    app = Flask(__name__)
    
    # Configuration
    app.config['SECRET_KEY'] = config.web.SECRET_KEY
    app.config['DEBUG'] = config.web.DEBUG
    
    # Enable CORS
    CORS(app, origins=config.web.CORS_ORIGINS)
    
    return app


app = create_app()


@app.route('/')
def index():
    """Main dashboard."""
    return render_template('dashboard.html')


@app.route('/premium')
def premium_dashboard():
    """Premium trading dashboard."""
    return render_template('premium.html')


@app.route('/api/trades')
def get_trades():
    """API endpoint to get recent trades."""
    
    # Query parameters
    limit = request.args.get('limit', 50, type=int)
    ticker = request.args.get('ticker')
    filer_type = request.args.get('filer_type')
    days = request.args.get('days', 30, type=int)
    
    try:
        with get_session() as session:
            # Base query
            query = session.query(Trade).join(Filer)
            
            # Apply filters
            if ticker:
                query = query.filter(Trade.ticker == ticker.upper())
            
            if filer_type:
                from src.database.models import FilerType
                query = query.filter(Filer.filer_type == FilerType(filer_type))
            
            if days:
                cutoff_date = datetime.now().date() - timedelta(days=days)
                query = query.filter(Trade.reported_date >= cutoff_date)
            
            # Order and limit
            trades = query.order_by(Trade.reported_date.desc()).limit(limit).all()
            
            # Convert to JSON
            trades_data = []
            for trade in trades:
                trade_dict = {
                    'trade_id': trade.trade_id,
                    'filer_name': trade.filer.name,
                    'filer_type': trade.filer.filer_type.value,
                    'ticker': trade.ticker,
                    'company_name': trade.company_name,
                    'transaction_type': trade.transaction_type.value,
                    'amount_usd': float(trade.amount_usd) if trade.amount_usd else None,
                    'quantity': float(trade.quantity) if trade.quantity else None,
                    'price': float(trade.price) if trade.price else None,
                    'reported_date': trade.reported_date.isoformat() if trade.reported_date else None,
                    'trade_date': trade.trade_date.isoformat() if trade.trade_date else None,
                    'source': trade.source.value,
                    'filing_url': trade.filing_url
                }
                trades_data.append(trade_dict)
            
            return jsonify({
                'trades': trades_data,
                'total': len(trades_data),
                'limit': limit
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/filers')
def get_filers():
    """API endpoint to get filers."""
    
    try:
        with get_session() as session:
            filers = session.query(Filer).order_by(Filer.name).all()
            
            filers_data = []
            for filer in filers:
                filer_dict = {
                    'filer_id': filer.filer_id,
                    'name': filer.name,
                    'filer_type': filer.filer_type.value,
                    'party': filer.party,
                    'state': filer.state,
                    'chamber': filer.chamber,
                    'company': filer.company,
                    'title': filer.title,
                    'total_trades': filer.total_trades,
                    'win_rate': float(filer.win_rate) if filer.win_rate else None,
                    'avg_return': float(filer.avg_return) if filer.avg_return else None
                }
                filers_data.append(filer_dict)
            
            return jsonify({'filers': filers_data})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats')
def get_stats():
    """API endpoint to get database statistics."""
    
    try:
        # Version marker to force reload
        _version = "v2_fixed"
        
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
            from sqlalchemy import func
            top_tickers = session.query(
                Trade.ticker,
                func.count(Trade.trade_id).label('count')
            ).group_by(Trade.ticker).order_by(func.count(Trade.trade_id).desc()).limit(10).all()
            
            stats['top_tickers'] = [{'ticker': t[0], 'count': t[1]} for t in top_tickers]
            
            return jsonify(stats)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500


@app.route('/api/ingestion/run', methods=['POST'])
def run_ingestion():
    """API endpoint to trigger data ingestion."""
    
    try:
        data = request.get_json() or {}
        source = data.get('source', 'all')
        days = data.get('days', 7)
        
        results = {}
        
        if source in ['all', 'politicians']:
            politician_scraper = PoliticianScraper()
            results['politicians'] = politician_scraper.run_full_ingestion(days=days)
        
        if source in ['all', 'sec']:
            sec_scraper = SECScraper()
            results['sec'] = sec_scraper.run_full_ingestion(days=days)
        
        return jsonify({
            'status': 'success',
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error', 
            'message': str(e)
        }), 500


@app.route('/api/signals')
def get_signals():
    """API endpoint to get current trading signals."""
    
    try:
        portfolio_value = request.args.get('portfolio_value', 100000, type=float)
        risk_tolerance = request.args.get('risk_tolerance', 'moderate')
        
        generator = SignalGenerator()
        signals = generator.generate_current_signals()
        
        signals_data = []
        for signal in signals:
            signal_dict = {
                'ticker': signal.ticker,
                'action': signal.action.value,
                'strength': signal.strength.value,
                'confidence': signal.confidence,
                'current_price': signal.current_price,
                'target_price': signal.target_price,
                'stop_loss': signal.stop_loss,
                'position_size_pct': signal.position_size_pct,
                'time_horizon_days': signal.time_horizon_days,
                'reasoning': signal.reasoning,
                'supporting_patterns': signal.supporting_patterns,
                'risk_factors': signal.risk_factors,
                'generated_at': signal.generated_at.isoformat() if signal.generated_at else None,
                'expires_at': signal.expires_at.isoformat() if signal.expires_at else None,
                'insider_trades_count': signal.insider_trades_count,
                'total_insider_amount': signal.total_insider_amount
            }
            signals_data.append(signal_dict)
        
        return jsonify({
            'signals': signals_data,
            'total': len(signals_data),
            'parameters': {
                'portfolio_value': portfolio_value,
                'risk_tolerance': risk_tolerance
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/signals/enhanced')
def get_enhanced_signals():
    """Enhanced API endpoint with filtering and more signals."""
    
    try:
        # Query parameters
        limit = request.args.get('limit', 50, type=int)  # Show 50 instead of 10!
        risk_tolerance = request.args.get('risk', 'moderate')
        market_cap = request.args.get('market_cap', 'all')  # all, large, mid, small, micro
        min_confidence = request.args.get('min_confidence', 0, type=float)
        
        with get_session() as session:
            from sqlalchemy import desc, func
            
            # Get active signals
            query = session.query(Signal).filter(Signal.is_active == True)
            
            # Apply confidence filter
            if min_confidence > 0:
                query = query.filter(Signal.strength >= min_confidence / 100.0)
            
            # Get signals
            signals = query.order_by(desc(Signal.strength)).limit(limit).all()
            
            # Enrich with additional data and apply filters
            result = []
            for sig in signals:
                # Get trades for this ticker
                trades = session.query(Trade).filter(
                    Trade.ticker == sig.ticker,
                    Trade.trade_date >= (datetime.now().date() - timedelta(days=90))
                ).all()
                
                # Calculate insider details
                unique_insiders = set()
                total_amount = 0
                buy_trades = []
                
                for t in trades:
                    if t.filer:
                        unique_insiders.add(t.filer.name)
                    if t.amount_usd:
                        total_amount += float(t.amount_usd)
                    if t.transaction_type.value.lower() in ['buy', 'option_buy']:
                        buy_trades.append(t)
                
                # Get market cap if available
                market_cap_value = None
                market_cap_category = 'unknown'
                try:
                    import yfinance as yf
                    ticker_obj = yf.Ticker(sig.ticker)
                    info = ticker_obj.info
                    market_cap_value = info.get('marketCap', 0)
                    
                    # Categorize market cap
                    if market_cap_value > 200_000_000_000:
                        market_cap_category = 'mega'
                    elif market_cap_value > 10_000_000_000:
                        market_cap_category = 'large'
                    elif market_cap_value > 2_000_000_000:
                        market_cap_category = 'mid'
                    elif market_cap_value > 300_000_000:
                        market_cap_category = 'small'
                    else:
                        market_cap_category = 'micro'
                except:
                    pass
                
                # Apply market cap filter
                if market_cap != 'all' and market_cap != market_cap_category:
                    continue
                
                # Adjust strength based on risk tolerance
                adjusted_strength = float(sig.strength) * 100
                if risk_tolerance == 'conservative':
                    # Only show very high confidence signals
                    if adjusted_strength < 80:
                        continue
                elif risk_tolerance == 'aggressive':
                    # Show lower confidence signals too
                    adjusted_strength = min(100, adjusted_strength * 1.1)  # Boost by 10%
                
                result.append({
                    'ticker': sig.ticker,
                    'signal_type': sig.signal_type.value,
                    'strength': adjusted_strength,
                    'reasoning': sig.reasoning,
                    'market_cap': market_cap_value,
                    'market_cap_category': market_cap_category,
                    
                    # Enhanced data
                    'num_trades': len(trades),
                    'num_insiders': len(unique_insiders),
                    'total_volume': total_amount,
                    'num_buys': len(buy_trades),
                    'insiders': list(unique_insiders)[:5],  # Top 5
                    
                    # Timestamps
                    'generated_at': sig.generated_at.isoformat() if sig.generated_at else None
                })
            
            return jsonify({
                'signals': result,
                'total': len(result),
                'filters': {
                    'risk_tolerance': risk_tolerance,
                    'market_cap': market_cap,
                    'min_confidence': min_confidence
                }
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/insider_buys/<ticker>')
def get_insider_buy_history(ticker):
    """Get detailed insider buying history for a ticker."""
    
    try:
        ticker = ticker.upper()
        days = request.args.get('days', 365, type=int)
        
        with get_session() as session:
            from src.database.models import TransactionType
            
            # Get buy trades for this ticker
            trades = session.query(Trade).join(Filer).filter(
                Trade.ticker == ticker,
                Trade.transaction_type == TransactionType.BUY,
                Trade.trade_date >= (datetime.now().date() - timedelta(days=days))
            ).order_by(Trade.trade_date.desc()).all()
            
            result = []
            for trade in trades:
                role = trade.filer.title or trade.filer.position or 'Insider' if trade.filer else 'Unknown'
                result.append({
                    'date': trade.trade_date.isoformat(),
                    'insider_name': trade.filer.name if trade.filer else 'Unknown',
                    'insider_role': role,
                    'price': float(trade.price) if trade.price else None,
                    'quantity': float(trade.quantity) if trade.quantity else None,
                    'amount': float(trade.amount_usd) if trade.amount_usd else None,
                    'filing_url': trade.filing_url
                })
            
            # Calculate average buy price
            prices = [t['price'] for t in result if t['price']]
            avg_buy_price = sum(prices) / len(prices) if prices else None
            
            # Get current price (would need yfinance here, placeholder for now)
            current_price = None  # TODO: Fetch from yfinance
            
            return jsonify({
                'ticker': ticker,
                'buy_trades': result,
                'total_buys': len(result),
                'total_amount': sum([t['amount'] for t in result if t['amount']]),
                'avg_buy_price': avg_buy_price,
                'current_price': current_price,
                'potential_return': None  # Would calculate if we had current price
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/insider_info/<name>')
def get_insider_info(name):
    """Get detailed info about an insider with their trading history."""
    try:
        with get_session() as session:
            filer = session.query(Filer).filter(Filer.name.ilike(f'%{name}%')).first()
            
            if not filer:
                return jsonify({'error': 'Insider not found'}), 404
            
            # Get all trades by this insider
            trades = session.query(Trade).filter(Trade.filer_id == filer.filer_id)\
                .order_by(Trade.trade_date.desc()).limit(50).all()
            
            # Calculate stats
            buy_trades = [t for t in trades if t.transaction_type.value.lower() in ['buy', 'option_buy']]
            sell_trades = [t for t in trades if t.transaction_type.value.lower() in ['sell', 'option_sell']]
            
            total_bought = sum([float(t.amount_usd or 0) for t in buy_trades])
            total_sold = sum([float(t.amount_usd or 0) for t in sell_trades])
            
            # Get unique tickers
            tickers = list(set([t.ticker for t in trades if t.ticker]))
            
            # Get REAL enriched data about this person
            try:
                from src.enrichment import get_enriched_insider_data
                enriched = get_enriched_insider_data(
                    name=filer.name,
                    filer_type=filer.filer_type.value,
                    company=filer.company,
                    state=filer.state
                )
            except Exception as e:
                logger.error(f"Enrichment failed for {filer.name}: {e}")
                enriched = {}
            
            # Build bio/description - NEVER show generic types
            # Helper to check if value is meaningful (not None, not "Unknown", not empty)
            def is_meaningful(val):
                return val and val not in ['Unknown', 'N/A', 'None', '']
            
            role_parts = []
            if is_meaningful(filer.title):
                role_parts.append(filer.title)
            if is_meaningful(filer.position):
                role_parts.append(filer.position)
            if is_meaningful(filer.chamber):
                role_parts.append(f"{filer.chamber}")
            if is_meaningful(filer.party):
                role_parts.append(f"({filer.party})")
            
            # Smart fallback for role
            if role_parts:
                role = " ".join(role_parts)
            else:
                # Use descriptive role based on type and data
                if filer.filer_type.value == 'politician':
                    role = "Political Insider"
                elif filer.filer_type.value == 'corporate_insider':
                    if filer.company:
                        role = f"{filer.company} Executive"
                    else:
                        role = "Corporate Executive"
                elif filer.filer_type.value == 'institutional_investor':
                    role = "Institutional Fund Manager"
                else:
                    role = filer.filer_type.value.replace('_', ' ').title()
            
            # Use enriched data if available
            bio = enriched.get('bio')
            committees = enriched.get('committees', [])
            leadership = enriched.get('leadership')
            significance = enriched.get('why_matters')
            
            # Generate useful bio if Wikipedia failed
            if not bio:
                bio_parts = [f"{filer.name} is a"]
                
                if filer.filer_type.value == 'politician':
                    if is_meaningful(filer.chamber) and is_meaningful(filer.state):
                        bio_parts.append(f"{filer.chamber} member representing {filer.state}")
                    elif is_meaningful(filer.chamber):
                        bio_parts.append(f"{filer.chamber} member")
                    elif is_meaningful(filer.state):
                        bio_parts.append(f"politician from {filer.state}")
                    else:
                        bio_parts.append("political insider")
                    
                    if is_meaningful(filer.party):
                        bio_parts.append(f"affiliated with the {filer.party}")
                    
                    bio_parts.append(f"with {len(trades)} recorded trades")
                    
                elif filer.filer_type.value == 'corporate_insider':
                    if filer.company:
                        bio_parts.append(f"corporate insider at {filer.company}")
                    else:
                        bio_parts.append("corporate executive")
                    
                    if filer.title:
                        bio_parts.append(f"serving as {filer.title}")
                    
                    bio_parts.append(f"with {len(trades)} disclosed transactions")
                    
                else:
                    bio_parts.append(f"{filer.filer_type.value.replace('_', ' ')}")
                    bio_parts.append(f"with {len(trades)} tracked trades")
                
                # Add top holdings
                if tickers:
                    if len(tickers) <= 3:
                        bio_parts.append(f". Primary holdings: {', '.join(tickers)}")
                    else:
                        bio_parts.append(f". Trades {len(tickers)} stocks including {', '.join(tickers[:3])}")
                
                bio = " ".join(bio_parts) + "."
            
            # Generate smart significance even without Wikipedia
            if not significance:
                # Build significance from trading data
                sig_parts = []
                
                if filer.filer_type.value == 'politician':
                    sig_parts.append(f"{filer.name} is a political insider")
                    if is_meaningful(filer.party):
                        sig_parts.append(f"({filer.party})")
                    if is_meaningful(filer.chamber):
                        sig_parts.append(f"in the {filer.chamber}")
                elif filer.filer_type.value == 'corporate_insider':
                    sig_parts.append(f"{filer.name} is a corporate insider")
                    if is_meaningful(filer.company):
                        sig_parts.append(f"at {filer.company}")
                else:
                    sig_parts.append(f"{filer.name} is a {filer.filer_type.value.replace('_', ' ')}")
                
                significance = " ".join(sig_parts) + ". "
                
                # Add trading pattern insights
                if len(trades) > 10:
                    significance += f"Highly active trader with {len(trades)} recorded transactions. "
                elif len(trades) > 5:
                    significance += f"Active trader with {len(trades)} transactions. "
                
                # Add ticker insights
                if len(tickers) == 1:
                    significance += f"Exclusively trades {tickers[0]}. "
                elif len(tickers) <= 3:
                    significance += f"Focuses on {', '.join(tickers[:3])}. "
                else:
                    significance += f"Trades {len(tickers)} different stocks including {', '.join(tickers[:3])}. "
                
                # Add buy/sell pattern
                if len(buy_trades) > 0 and len(sell_trades) == 0:
                    significance += "Only buying (no recorded sales) suggests strong conviction. "
                elif len(sell_trades) > len(buy_trades) * 3:
                    significance += "Heavy selling activity may indicate profit-taking or portfolio rebalancing. "
                
                # Add volume context
                if total_bought > 1000000:
                    significance += f"Large purchase volume (${total_bought:,.0f}) indicates significant conviction. "
                elif total_sold > 1000000:
                    significance += f"Large sale volume (${total_sold:,.0f}) may signal important portfolio changes. "
                
                # Add context based on role
                if filer.filer_type.value == 'politician':
                    significance += "Political insider trades often precede regulatory changes, committee actions, or policy shifts that could affect specific industries."
                elif filer.filer_type.value == 'corporate_insider':
                    significance += "Corporate insiders have access to non-public information about company performance, products, and strategic decisions."
                else:
                    significance += "Their trades may reflect privileged access to market-moving information."
            
            # Recent activity summary
            if buy_trades:
                recent_buys = sorted(buy_trades, key=lambda t: t.trade_date, reverse=True)[:3]
                recent_tickers = [t.ticker for t in recent_buys if t.ticker]
                if recent_tickers:
                    significance += f" Recently bought: {', '.join(recent_tickers[:3])}."
            
            return jsonify({
                'name': filer.name,
                'role': role,
                'filer_type': filer.filer_type.value,
                'title': filer.title,
                'position': filer.position,
                'chamber': filer.chamber,
                'state': filer.state,
                'party': filer.party,
                'significance': significance,
                'bio': bio,  # NEW: Real biographical data
                'committees': committees,  # NEW: Committee memberships
                'leadership': leadership,  # NEW: Leadership positions
                'total_trades': len(trades),
                'buy_trades': len(buy_trades),
                'sell_trades': len(sell_trades),
                'total_bought': total_bought,
                'total_sold': total_sold,
                'unique_tickers': len(tickers),
                'favorite_tickers': tickers[:5],
                'recent_trades': [
                    {
                        'ticker': t.ticker,
                        'type': t.transaction_type.value,
                        'date': t.trade_date.isoformat(),
                        'amount': float(t.amount_usd) if t.amount_usd else None
                    }
                    for t in trades[:10]
                ]
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/signal_details/<ticker>')
def get_signal_details(ticker):
    """Get comprehensive signal details including confidence breakdown, targets, and hold time."""
    try:
        ticker = ticker.upper()
        
        with get_session() as session:
            # Get the signal
            signal = session.query(Signal).filter(
                Signal.ticker == ticker,
                Signal.is_active == True
            ).first()
            
            if not signal:
                return jsonify({'error': 'No active signal found for this ticker'}), 404
            
            # Get recent trades (last 90 days)
            from src.database.models import TransactionType
            trades = session.query(Trade).filter(
                Trade.ticker == ticker,
                Trade.trade_date >= (datetime.now().date() - timedelta(days=90))
            ).order_by(Trade.trade_date.desc()).all()
            
            # Calculate confidence score breakdown
            confidence_factors = {
                'insider_count': 0,
                'trade_volume': 0,
                'buy_sell_ratio': 0,
                'recent_activity': 0,
                'position_concentration': 0
            }
            
            unique_insiders = set()
            buy_trades = []
            sell_trades = []
            total_amount = 0
            
            for t in trades:
                if t.filer:
                    unique_insiders.add(t.filer.filer_id)
                if t.amount_usd:
                    total_amount += float(t.amount_usd)
                if t.transaction_type == TransactionType.BUY:
                    buy_trades.append(t)
                elif t.transaction_type == TransactionType.SELL:
                    sell_trades.append(t)
            
            # Insider count factor (0-25 points)
            confidence_factors['insider_count'] = min(25, len(unique_insiders) * 5)
            
            # Trade volume factor (0-25 points)
            if total_amount > 10000000:  # $10M+
                confidence_factors['trade_volume'] = 25
            elif total_amount > 1000000:  # $1M+
                confidence_factors['trade_volume'] = 20
            elif total_amount > 100000:  # $100K+
                confidence_factors['trade_volume'] = 15
            else:
                confidence_factors['trade_volume'] = 10
            
            # Buy/Sell ratio factor (0-25 points)
            if len(buy_trades) > 0 and len(sell_trades) == 0:
                confidence_factors['buy_sell_ratio'] = 25
            elif len(buy_trades) > len(sell_trades) * 3:
                confidence_factors['buy_sell_ratio'] = 20
            elif len(buy_trades) > len(sell_trades):
                confidence_factors['buy_sell_ratio'] = 15
            else:
                confidence_factors['buy_sell_ratio'] = 5
            
            # Recent activity factor (0-15 points)
            recent_trades = [t for t in trades if t.trade_date >= (datetime.now().date() - timedelta(days=30))]
            if len(recent_trades) >= 5:
                confidence_factors['recent_activity'] = 15
            elif len(recent_trades) >= 3:
                confidence_factors['recent_activity'] = 10
            elif len(recent_trades) >= 1:
                confidence_factors['recent_activity'] = 5
            
            # Position concentration factor (0-10 points)
            if len(unique_insiders) >= 3:
                confidence_factors['position_concentration'] = 10
            elif len(unique_insiders) >= 2:
                confidence_factors['position_concentration'] = 5
            
            total_confidence = sum(confidence_factors.values())
            
            # Calculate hold time recommendation
            hold_time_days = None
            avg_hold_time = None
            
            # Look at historical trades to estimate hold times
            # For now, use a simple heuristic based on signal strength
            if signal.strength >= 0.8:
                hold_time_days = 90  # 3 months for high confidence
            elif signal.strength >= 0.6:
                hold_time_days = 60  # 2 months for medium confidence
            else:
                hold_time_days = 30  # 1 month for lower confidence
            
            # Calculate exit price targets
            # Get average buy price from recent trades
            buy_prices = [float(t.price) for t in buy_trades if t.price]
            avg_buy_price = sum(buy_prices) / len(buy_prices) if buy_prices else None
            
            targets = {
                'conservative': None,
                'moderate': None,
                'aggressive': None,
                'stop_loss': None
            }
            
            if avg_buy_price:
                # Conservative: 10% upside
                targets['conservative'] = round(avg_buy_price * 1.10, 2)
                # Moderate: 25% upside
                targets['moderate'] = round(avg_buy_price * 1.25, 2)
                # Aggressive: 50% upside
                targets['aggressive'] = round(avg_buy_price * 1.50, 2)
                # Stop loss: 15% downside
                targets['stop_loss'] = round(avg_buy_price * 0.85, 2)
            
            # Build detailed reasoning
            reasoning_parts = []
            reasoning_parts.append(f"🎯 Signal generated based on {len(trades)} trades from {len(unique_insiders)} unique insiders.")
            reasoning_parts.append(f"💰 Total insider volume: ${total_amount:,.0f}")
            reasoning_parts.append(f"📊 Buy/Sell ratio: {len(buy_trades)} buys vs {len(sell_trades)} sells")
            
            if confidence_factors['insider_count'] >= 20:
                reasoning_parts.append(f"✅ Strong insider participation ({len(unique_insiders)} insiders)")
            if confidence_factors['recent_activity'] >= 10:
                reasoning_parts.append(f"⚡ High recent activity ({len(recent_trades)} trades in last 30 days)")
            if confidence_factors['trade_volume'] >= 20:
                reasoning_parts.append(f"💎 Large volume trades indicating strong conviction")
            
            return jsonify({
                'ticker': ticker,
                'signal_type': signal.signal_type.value,
                'strength': float(signal.strength) * 100,
                'confidence_breakdown': {
                    'total_score': total_confidence,
                    'factors': {
                        'Insider Count': confidence_factors['insider_count'],
                        'Trade Volume': confidence_factors['trade_volume'],
                        'Buy/Sell Ratio': confidence_factors['buy_sell_ratio'],
                        'Recent Activity': confidence_factors['recent_activity'],
                        'Position Concentration': confidence_factors['position_concentration']
                    },
                    'explanation': 'Confidence score is calculated from multiple factors: insider participation (25%), trade volume (25%), buy/sell ratio (25%), recent activity (15%), and position concentration (10%)'
                },
                'hold_time': {
                    'recommended_days': hold_time_days,
                    'explanation': f"Hold for approximately {hold_time_days} days based on signal strength and historical patterns"
                },
                'price_targets': {
                    'avg_insider_buy_price': avg_buy_price,
                    'targets': targets,
                    'explanation': 'Price targets calculated based on average insider buy prices with different risk profiles'
                },
                'detailed_reasoning': '\n'.join(reasoning_parts),
                'trade_summary': {
                    'total_trades': len(trades),
                    'buy_trades': len(buy_trades),
                    'sell_trades': len(sell_trades),
                    'unique_insiders': len(unique_insiders),
                    'total_volume': total_amount,
                    'recent_trades_30d': len(recent_trades)
                }
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/query/trades', methods=['POST'])
def custom_trade_query():
    """Custom query builder for trades."""
    
    try:
        filters = request.json or {}
        
        with get_session() as session:
            query = session.query(Trade).join(Filer)
            
            # Apply filters
            if filters.get('ticker'):
                query = query.filter(Trade.ticker == filters['ticker'].upper())
            
            if filters.get('start_date'):
                query = query.filter(Trade.trade_date >= filters['start_date'])
            
            if filters.get('end_date'):
                query = query.filter(Trade.trade_date <= filters['end_date'])
            
            if filters.get('min_amount'):
                query = query.filter(Trade.amount_usd >= filters['min_amount'])
            
            if filters.get('max_amount'):
                query = query.filter(Trade.amount_usd <= filters['max_amount'])
            
            if filters.get('transaction_type'):
                from src.database.models import TransactionType
                query = query.filter(Trade.transaction_type == TransactionType[filters['transaction_type']])
            
            if filters.get('filer_type'):
                from src.database.models import FilerType
                query = query.filter(Filer.filer_type == FilerType[filters['filer_type']])
            
            # Limit
            limit = filters.get('limit', 100)
            trades = query.order_by(Trade.trade_date.desc()).limit(limit).all()
            
            # Format results
            result = []
            for t in trades:
                result.append({
                    'ticker': t.ticker,
                    'company': t.company_name,
                    'insider': t.filer.name if t.filer else 'Unknown',
                    'date': t.trade_date.isoformat(),
                    'type': t.transaction_type.value,
                    'amount': float(t.amount_usd) if t.amount_usd else None,
                    'price': float(t.price) if t.price else None
                })
            
            return jsonify({
                'trades': result,
                'count': len(result),
                'filters_applied': filters
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/recommendations')
def get_recommendations():
    """API endpoint to get portfolio recommendations."""
    
    try:
        portfolio_value = request.args.get('portfolio_value', 100000, type=float)
        risk_tolerance = request.args.get('risk_tolerance', 'moderate')
        
        manager = PortfolioManager(portfolio_value, risk_tolerance)
        recommendations = manager.get_current_recommendations()
        
        # Convert signals to JSON-serializable format
        signals_data = []
        for signal in recommendations.get('signals', []):
            signal_dict = {
                'ticker': signal.ticker,
                'action': signal.action.value,
                'strength': signal.strength.value,
                'confidence': signal.confidence,
                'current_price': signal.current_price,
                'target_price': signal.target_price,
                'stop_loss': signal.stop_loss,
                'position_size_pct': signal.position_size_pct,
                'reasoning': signal.reasoning,
                'risk_factors': signal.risk_factors
            }
            signals_data.append(signal_dict)
        
        return jsonify({
            'signals': signals_data,
            'allocation': recommendations.get('allocation', {}),
            'summary': recommendations.get('summary', {}),
            'total_recommended_allocation': recommendations.get('total_recommended_allocation', 0),
            'cash_allocation': recommendations.get('cash_allocation', 1.0),
            'hold_recommendations': recommendations.get('hold_recommendations', []),
            'generated_at': recommendations.get('generated_at').isoformat() if recommendations.get('generated_at') else None
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio')
def get_portfolio():
    """API endpoint to get current portfolio status."""
    
    try:
        portfolio_value = request.args.get('portfolio_value', 100000, type=float)
        risk_tolerance = request.args.get('risk_tolerance', 'moderate')
        
        manager = PortfolioManager(portfolio_value, risk_tolerance)
        summary = manager.get_portfolio_summary()
        
        return jsonify(summary)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/execute_signal', methods=['POST'])
def execute_signal():
    """API endpoint to execute a trading signal (simulation)."""
    
    try:
        data = request.get_json()
        ticker = data.get('ticker')
        action = data.get('action')
        shares = data.get('shares')
        portfolio_value = data.get('portfolio_value', 100000)
        
        if not ticker or not action:
            return jsonify({'error': 'Missing ticker or action'}), 400
        
        manager = PortfolioManager(portfolio_value)
        
        if action.lower() == 'buy':
            # This would need a signal object, simplified for demo
            return jsonify({
                'status': 'simulated',
                'message': f'Would buy {shares or "calculated"} shares of {ticker}',
                'note': 'This is a simulation - integrate with your broker for actual trading'
            })
        elif action.lower() == 'sell':
            success = manager.sell_position(ticker, shares)
            return jsonify({
                'status': 'success' if success else 'failed',
                'message': f'{"Executed" if success else "Failed"} sell of {ticker}'
            })
        else:
            return jsonify({'error': 'Invalid action'}), 400
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/search')
def search():
    """API endpoint for searching trades."""
    
    query_text = request.args.get('q', '')
    if not query_text:
        return jsonify({'trades': []})
    
    try:
        with get_session() as session:
            # Search in filer names, tickers, and company names
            trades = session.query(Trade).join(Filer).filter(
                (Filer.name.ilike(f'%{query_text}%')) |
                (Trade.ticker.ilike(f'%{query_text}%')) |
                (Trade.company_name.ilike(f'%{query_text}%'))
            ).order_by(Trade.reported_date.desc()).limit(50).all()
            
            trades_data = []
            for trade in trades:
                trade_dict = {
                    'trade_id': trade.trade_id,
                    'filer_name': trade.filer.name,
                    'ticker': trade.ticker,
                    'company_name': trade.company_name,
                    'transaction_type': trade.transaction_type.value,
                    'amount_usd': float(trade.amount_usd) if trade.amount_usd else None,
                    'reported_date': trade.reported_date.isoformat() if trade.reported_date else None
                }
                trades_data.append(trade_dict)
            
            return jsonify({'trades': trades_data})
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/backtest/run')
def run_backtest_api():
    """Run backtest and return results."""
    try:
        from src.backtesting.advanced_backtest import AdvancedBacktester
        
        # Get parameters
        days = request.args.get('days', 365, type=int)
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        backtester = AdvancedBacktester(start_date=start_date, end_date=end_date)
        results = backtester.run_all_strategies()
        
        # Convert results to JSON
        json_results = {}
        for name, result in results.items():
            json_results[name] = {
                'strategy_name': result.strategy_name,
                'period': f"{result.start_date.date()} to {result.end_date.date()}",
                'total_trades': result.total_trades,
                'winning_trades': result.winning_trades,
                'losing_trades': result.losing_trades,
                'total_return': f"{result.total_return*100:.2f}%",
                'total_return_pct': result.total_return * 100,
                'sharpe_ratio': round(result.sharpe_ratio, 2),
                'max_drawdown': f"{result.max_drawdown*100:.2f}%",
                'win_rate': f"{result.win_rate*100:.1f}%",
                'win_rate_pct': result.win_rate * 100,
                'avg_win': f"{result.avg_win*100:.2f}%",
                'avg_loss': f"{result.avg_loss*100:.2f}%",
                'profit_factor': round(result.profit_factor, 2)
            }
        
        # Find best strategy
        best = max(results.values(), key=lambda r: r.sharpe_ratio) if results else None
        
        return jsonify({
            'results': json_results,
            'best_strategy': {
                'name': best.strategy_name,
                'sharpe_ratio': round(best.sharpe_ratio, 2),
                'total_return': f"{best.total_return*100:.2f}%",
                'win_rate': f"{best.win_rate*100:.1f}%"
            } if best else None
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# BROKER API ENDPOINTS
# ============================================================================

@app.route('/api/brokers/status')
def brokers_status():
    """Get status of all configured brokers."""
    try:
        from src.brokers import get_broker_manager
        
        manager = get_broker_manager()
        statuses = manager.get_all_statuses()
        
        return jsonify({
            'brokers': statuses,
            'active_broker': manager.active_broker
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/brokers/connect', methods=['POST'])
def brokers_connect():
    """Initiate broker authentication."""
    try:
        from src.brokers import get_broker_manager
        
        data = request.get_json()
        broker_name = data.get('broker')
        
        if not broker_name:
            return jsonify({'error': 'broker name required'}), 400
        
        manager = get_broker_manager()
        result = manager.authenticate_broker(broker_name)
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/brokers/set_active', methods=['POST'])
def brokers_set_active():
    """Set the active broker."""
    try:
        from src.brokers import get_broker_manager
        
        data = request.get_json()
        broker_name = data.get('broker')
        
        if not broker_name:
            return jsonify({'error': 'broker name required'}), 400
        
        manager = get_broker_manager()
        success = manager.set_active_broker(broker_name)
        
        if success:
            return jsonify({'success': True, 'active_broker': broker_name})
        else:
            return jsonify({'error': 'Broker not found'}), 404
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/brokers/positions')
def brokers_positions():
    """Get positions from active broker."""
    try:
        from src.brokers import get_broker_manager
        
        broker_name = request.args.get('broker')
        manager = get_broker_manager()
        
        positions = manager.get_positions(broker_name)
        
        return jsonify({
            'positions': positions,
            'broker': broker_name or manager.active_broker
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/brokers/preview', methods=['POST'])
def brokers_preview_order():
    """Preview an order based on a signal."""
    try:
        from src.brokers import get_broker_manager
        
        data = request.get_json()
        signal = data.get('signal')
        broker_name = data.get('broker')
        
        if not signal:
            return jsonify({'error': 'signal required'}), 400
        
        manager = get_broker_manager()
        preview = manager.preview_signal_order(signal, broker_name)
        
        return jsonify(preview)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/brokers/execute', methods=['POST'])
def brokers_execute_order():
    """Execute an order based on a signal."""
    try:
        from src.brokers import get_broker_manager
        
        data = request.get_json()
        signal = data.get('signal')
        broker_name = data.get('broker')
        quantity = data.get('quantity')
        
        if not signal:
            return jsonify({'error': 'signal required'}), 400
        
        manager = get_broker_manager()
        result = manager.execute_signal(signal, broker_name, quantity)
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@app.route('/api/export/signals/csv')
def export_signals_csv():
    """Export signals to CSV."""
    try:
        from flask import Response
        import csv
        from io import StringIO
        from sqlalchemy import func, desc
        
        # Get filters
        risk_tolerance = request.args.get('risk_tolerance', 'moderate')
        market_cap = request.args.get('market_cap', 'all')
        min_confidence = float(request.args.get('min_confidence', 0))
        limit = int(request.args.get('limit', 100))
        
        with get_session() as session:
            # Build query
            query = session.query(Signal).filter(Signal.signal_type == 'BUY')
            
            # Apply confidence filter based on risk tolerance
            if risk_tolerance == 'conservative':
                query = query.filter(Signal.strength >= 0.8)
            
            # Apply min confidence
            if min_confidence > 0:
                query = query.filter(Signal.strength >= min_confidence / 100.0)
            
            query = query.order_by(desc(Signal.strength)).limit(limit)
            signals = query.all()
            
            # Create CSV
            output = StringIO()
            writer = csv.writer(output)
            
            # Header
            writer.writerow([
                'Ticker',
                'Confidence %',
                'Signal Type',
                'Reasoning',
                'Strategy',
                'Generated Date',
                'Expires',
                'Active'
            ])
            
            # Data rows
            for signal in signals:
                writer.writerow([
                    signal.ticker,
                    f"{signal.strength * 100:.1f}",
                    signal.signal_type.value if hasattr(signal.signal_type, 'value') else signal.signal_type,
                    signal.reasoning or '',
                    signal.strategy.name if signal.strategy else '',
                    signal.generated_at.strftime('%Y-%m-%d %H:%M') if signal.generated_at else '',
                    signal.expires_at.strftime('%Y-%m-%d') if signal.expires_at else '',
                    'Yes' if signal.is_active else 'No'
                ])
            
            # Create response
            output.seek(0)
            response = Response(output.getvalue(), mimetype='text/csv')
            response.headers['Content-Disposition'] = f'attachment; filename=insider_signals_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            
            return response
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats/top_insiders')
def top_insiders_week():
    """Get top insiders by trade volume this week."""
    try:
        from sqlalchemy import func
        
        days = int(request.args.get('days', 7))
        limit = int(request.args.get('limit', 10))
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        with get_session() as session:
            # Get top filers by trade volume
            top_filers = session.query(
                Filer.name,
                Filer.filer_type,
                Filer.title,
                Filer.company,
                func.count(Trade.trade_id).label('trade_count'),
                func.sum(Trade.amount_usd).label('total_volume'),
                func.count(func.distinct(Trade.ticker)).label('unique_tickers')
            ).join(Trade).filter(
                Trade.trade_date >= cutoff_date
            ).group_by(
                Filer.filer_id, Filer.name, Filer.filer_type, Filer.title, Filer.company
            ).order_by(
                func.sum(Trade.amount_usd).desc()
            ).limit(limit).all()
            
            results = []
            for filer in top_filers:
                results.append({
                    'name': filer.name,
                    'type': filer.filer_type.value if hasattr(filer.filer_type, 'value') else filer.filer_type,
                    'title': filer.title or filer.company or '',
                    'trade_count': filer.trade_count,
                    'total_volume': float(filer.total_volume or 0),
                    'unique_tickers': filer.unique_tickers
                })
            
            return jsonify({
                'period_days': days,
                'top_insiders': results
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/signals/performance/summary')
def signal_performance_summary():
    """Get signal performance summary."""
    try:
        from src.analysis.signal_tracker import SignalTracker
        
        days = int(request.args.get('days', 30))
        tracker = SignalTracker()
        summary = tracker.get_signal_performance_summary(days)
        
        return jsonify(summary)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/signals/performance/top')
def signal_performance_top():
    """Get top performing signals."""
    try:
        from src.analysis.signal_tracker import SignalTracker
        
        limit = int(request.args.get('limit', 10))
        tracker = SignalTracker()
        top = tracker.get_top_performers(limit)
        
        return jsonify({'top_performers': top})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/signals/performance/evaluate', methods=['POST'])
def evaluate_signals():
    """Evaluate all active signals (admin/cron endpoint)."""
    try:
        from src.analysis.signal_tracker import SignalTracker
        
        tracker = SignalTracker()
        result = tracker.evaluate_all_signals()
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper/portfolio')
def paper_portfolio_summary():
    """Get paper trading portfolio summary."""
    try:
        from src.analysis.paper_trading import PaperTradingPortfolio
        
        portfolio = PaperTradingPortfolio()
        summary = portfolio.get_portfolio_summary()
        
        return jsonify(summary)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper/execute', methods=['POST'])
def paper_execute_signal():
    """Execute a paper trade from a signal."""
    try:
        from src.analysis.paper_trading import PaperTradingPortfolio
        
        data = request.get_json()
        signal_id = data.get('signal_id')
        quantity = data.get('quantity')
        
        if not signal_id:
            return jsonify({'error': 'signal_id required'}), 400
        
        with get_session() as session:
            signal = session.query(Signal).filter(Signal.signal_id == signal_id).first()
            
            if not signal:
                return jsonify({'error': 'Signal not found'}), 404
            
            portfolio = PaperTradingPortfolio()
            result = portfolio.execute_signal(signal, quantity)
            
            return jsonify(result)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper/history')
def paper_trade_history():
    """Get paper trading history."""
    try:
        from src.analysis.paper_trading import PaperTradingPortfolio
        
        limit = int(request.args.get('limit', 50))
        portfolio = PaperTradingPortfolio()
        history = portfolio.get_trade_history(limit)
        
        return jsonify({'trades': history})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts/test', methods=['POST'])
def test_alert():
    """Test alert system."""
    try:
        from src.alerts import AlertSystem
        
        data = request.get_json() or {}
        alert_type = data.get('type', 'email')
        
        test_signal = {
            'ticker': 'TEST',
            'confidence': 95.0,
            'type': 'BUY',
            'reasoning': 'This is a test alert from the Insider Intelligence Platform.',
            'num_insiders': 1,
            'total_volume': 100000
        }
        
        alert_system = AlertSystem()
        result = alert_system.send_signal_alert(test_signal, alert_type)
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/alerts/check', methods=['POST'])
def check_alerts():
    """Check for high-confidence signals and send alerts."""
    try:
        from src.alerts import check_and_send_alerts
        
        result = check_and_send_alerts()
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/paper/reset', methods=['POST'])
def paper_reset_portfolio():
    """Reset paper trading portfolio."""
    try:
        from src.analysis.paper_trading import PaperTradingPortfolio
        
        portfolio = PaperTradingPortfolio()
        result = portfolio.reset_portfolio()
        
        return jsonify(result)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/insiders/accuracy')
def insider_accuracy_rankings():
    """Get insider accuracy rankings."""
    try:
        from src.analysis.signal_tracker import SignalTracker
        
        limit = int(request.args.get('limit', 20))
        tracker = SignalTracker()
        rankings = tracker.get_insider_accuracy(limit)
        
        return jsonify({'rankings': rankings})
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats/sector_breakdown')
def sector_breakdown():
    """Get sector breakdown of recent trades."""
    try:
        days = int(request.args.get('days', 30))
        cutoff_date = datetime.now() - timedelta(days=days)
        
        # Simplified sector mapping (in production, use proper sector API)
        sector_map = {
            'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology', 'AMZN': 'Consumer', 
            'TSLA': 'Automotive', 'META': 'Technology', 'NVDA': 'Technology', 'JPM': 'Finance',
            'BAC': 'Finance', 'GS': 'Finance', 'WFC': 'Finance', 'C': 'Finance',
            'JNJ': 'Healthcare', 'UNH': 'Healthcare', 'PFE': 'Healthcare', 'ABBV': 'Healthcare',
            'XOM': 'Energy', 'CVX': 'Energy', 'COP': 'Energy',
            'BA': 'Industrial', 'CAT': 'Industrial', 'GE': 'Industrial'
        }
        
        with get_session() as session:
            trades = session.query(
                Trade.ticker,
                func.count(Trade.trade_id).label('count'),
                func.sum(Trade.amount_usd).label('volume')
            ).filter(
                Trade.trade_date >= cutoff_date,
                Trade.ticker.isnot(None)
            ).group_by(Trade.ticker).all()
            
            sector_stats = {}
            for trade in trades:
                sector = sector_map.get(trade.ticker, 'Other')
                if sector not in sector_stats:
                    sector_stats[sector] = {'count': 0, 'volume': 0}
                sector_stats[sector]['count'] += trade.count
                sector_stats[sector]['volume'] += float(trade.volume or 0)
            
            results = [
                {'sector': k, 'trade_count': v['count'], 'total_volume': v['volume']}
                for k, v in sector_stats.items()
            ]
            
            return jsonify({
                'period_days': days,
                'sectors': sorted(results, key=lambda x: x['total_volume'], reverse=True)
            })
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/export/trades/csv')
def export_trades_csv():
    """Export trades to CSV."""
    try:
        from flask import Response
        import csv
        from io import StringIO
        
        # Get filters from query params (from query builder)
        ticker = request.args.get('ticker')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        min_amount = request.args.get('min_amount', type=float)
        max_amount = request.args.get('max_amount', type=float)
        transaction_type = request.args.get('transaction_type')
        filer_type = request.args.get('filer_type')
        limit = int(request.args.get('limit', 1000))
        
        with get_session() as session:
            query = session.query(Trade).join(Filer)
            
            # Apply filters
            if ticker:
                query = query.filter(Trade.ticker == ticker.upper())
            if start_date:
                query = query.filter(Trade.trade_date >= start_date)
            if end_date:
                query = query.filter(Trade.trade_date <= end_date)
            if min_amount:
                query = query.filter(Trade.amount_usd >= min_amount)
            if max_amount:
                query = query.filter(Trade.amount_usd <= max_amount)
            if transaction_type:
                query = query.filter(Trade.transaction_type == transaction_type)
            if filer_type:
                query = query.filter(Filer.filer_type == filer_type)
            
            query = query.order_by(Trade.trade_date.desc()).limit(limit)
            trades = query.all()
            
            # Create CSV
            output = StringIO()
            writer = csv.writer(output)
            
            # Header
            writer.writerow([
                'Date',
                'Ticker',
                'Filer Name',
                'Filer Type',
                'Transaction Type',
                'Amount USD',
                'Quantity',
                'Price',
                'Source',
                'Filing URL'
            ])
            
            # Data rows
            for trade in trades:
                writer.writerow([
                    trade.trade_date.strftime('%Y-%m-%d') if trade.trade_date else '',
                    trade.ticker or '',
                    trade.filer.name if trade.filer else '',
                    trade.filer.filer_type.value if trade.filer and hasattr(trade.filer.filer_type, 'value') else '',
                    trade.transaction_type.value if hasattr(trade.transaction_type, 'value') else trade.transaction_type,
                    f"{trade.amount_usd:.2f}" if trade.amount_usd else '',
                    trade.quantity or '',
                    f"{trade.price_per_share:.2f}" if trade.price_per_share else '',
                    trade.source.value if hasattr(trade.source, 'value') else trade.source,
                    trade.filing_url or ''
                ])
            
            # Create response
            output.seek(0)
            response = Response(output.getvalue(), mimetype='text/csv')
            response.headers['Content-Disposition'] = f'attachment; filename=insider_trades_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            
            return response
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500


if __name__ == '__main__':
    # Ensure templates directory exists
    templates_dir = project_root / 'templates'
    templates_dir.mkdir(exist_ok=True)
    
    # Create a basic HTML template if it doesn't exist
    dashboard_template = templates_dir / 'dashboard.html'
    if not dashboard_template.exists():
        dashboard_html = '''<!DOCTYPE html>
<html>
<head>
    <title>Insider Trading Analysis Platform</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 0; background: #f8f9fa; }
        .header { background: linear-gradient(135deg, #2c3e50, #3498db); color: white; padding: 30px 40px; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .nav-tabs { display: flex; gap: 5px; margin-bottom: 20px; border-bottom: 2px solid #dee2e6; }
        .nav-tab { padding: 12px 24px; background: #e9ecef; border: none; cursor: pointer; border-radius: 5px 5px 0 0; }
        .nav-tab.active { background: #007bff; color: white; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-card h3 { margin: 0 0 10px 0; font-size: 2rem; color: #2c3e50; }
        .stat-card p { margin: 0; color: #666; font-weight: 500; }
        .signals-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .signal-card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); border-left: 4px solid #28a745; }
        .signal-card.moderate { border-left-color: #ffc107; }
        .signal-card.weak { border-left-color: #6c757d; }
        .signal-card.very_strong { border-left-color: #dc3545; }
        .signal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .signal-ticker { font-size: 1.5rem; font-weight: bold; color: #2c3e50; }
        .signal-strength { padding: 4px 12px; border-radius: 20px; font-size: 0.8rem; font-weight: bold; text-transform: uppercase; }
        .signal-strength.strong { background: #28a745; color: white; }
        .signal-strength.moderate { background: #ffc107; color: black; }
        .signal-strength.weak { background: #6c757d; color: white; }
        .signal-strength.very_strong { background: #dc3545; color: white; }
        .signal-metrics { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 15px; }
        .signal-metric { text-align: center; }
        .signal-metric .value { font-size: 1.2rem; font-weight: bold; color: #2c3e50; }
        .signal-metric .label { font-size: 0.8rem; color: #666; text-transform: uppercase; }
        .signal-reasoning { background: #f8f9fa; padding: 10px; border-radius: 4px; font-size: 0.9rem; color: #495057; margin-bottom: 15px; }
        .signal-actions { display: flex; gap: 10px; }
        .btn { padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; font-weight: 500; transition: all 0.2s; }
        .btn-primary { background: #007bff; color: white; }
        .btn-primary:hover { background: #0056b3; }
        .btn-success { background: #28a745; color: white; }
        .btn-success:hover { background: #1e7e34; }
        .btn-secondary { background: #6c757d; color: white; }
        .btn-secondary:hover { background: #545b62; }
        .table { width: 100%; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .table th, .table td { padding: 12px; border-bottom: 1px solid #dee2e6; }
        .table th { background: #f8f9fa; font-weight: 600; }
        .portfolio-summary { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .risk-selector { margin-bottom: 20px; }
        .risk-selector select { padding: 8px 16px; border: 1px solid #ced4da; border-radius: 4px; }
        .loading { text-align: center; padding: 40px; color: #666; }
        .error { background: #f8d7da; color: #721c24; padding: 15px; border-radius: 4px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Insider Trading Analysis Platform</h1>
        <p>AI-powered insights for smarter investment decisions</p>
    </div>
    
    <div class="container">
        <!-- Navigation Tabs -->
        <div class="nav-tabs">
            <button class="nav-tab active" onclick="showTab('overview')">Overview</button>
            <button class="nav-tab" onclick="showTab('signals')">Buy Signals</button>
            <button class="nav-tab" onclick="showTab('portfolio')">My Portfolio</button>
            <button class="nav-tab" onclick="showTab('trades')">Recent Trades</button>
        </div>
        
        <!-- Overview Tab -->
        <div id="overview-tab" class="tab-content active">
            <div class="risk-selector">
                <label for="riskTolerance">Risk Tolerance: </label>
                <select id="riskTolerance" onchange="updateRiskTolerance()">
                    <option value="conservative">Conservative</option>
                    <option value="moderate" selected>Moderate</option>
                    <option value="aggressive">Aggressive</option>
                </select>
                
                <label for="portfolioValue" style="margin-left: 20px;">Portfolio Value: $</label>
                <input type="number" id="portfolioValue" value="100000" onchange="updatePortfolioValue()" style="width: 120px; padding: 8px; border: 1px solid #ced4da; border-radius: 4px;">
            </div>
            
            <div id="stats" class="stats">
                <div class="stat-card">
                    <h3>Loading...</h3>
                    <p>Please wait while we load the dashboard</p>
                </div>
            </div>
            
            <div id="quick-signals" class="signals-grid">
                <!-- Quick signals will be loaded here -->
            </div>
        </div>
        
        <!-- Signals Tab -->
        <div id="signals-tab" class="tab-content">
            <h2>Current Buy Signals</h2>
            <div class="loading">Loading signals...</div>
            <div id="signals-container" class="signals-grid"></div>
        </div>
        
        <!-- Portfolio Tab -->
        <div id="portfolio-tab" class="tab-content">
            <h2>Portfolio Management</h2>
            <div id="portfolio-summary" class="portfolio-summary">
                <div class="loading">Loading portfolio...</div>
            </div>
            <div id="recommendations-container"></div>
        </div>
        
        <!-- Trades Tab -->
        <div id="trades-tab" class="tab-content">
            <h2>Recent Insider Trades</h2>
            <button class="btn btn-primary" onclick="runIngestion()">Refresh Data</button>
            <table id="trades-table" class="table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Filer</th>
                        <th>Ticker</th>
                        <th>Type</th>
                        <th>Amount</th>
                        <th>Source</th>
                    </tr>
                </thead>
                <tbody>
                    <tr><td colspan="6" class="loading">Loading trades...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        // Load dashboard data
        async function loadDashboard() {
            try {
                // Load stats
                const statsResponse = await fetch('/api/stats');
                const stats = await statsResponse.json();
                
                document.getElementById('stats').innerHTML = `
                    <div class="stat-card">
                        <h3>${stats.total_trades}</h3>
                        <p>Total Trades</p>
                    </div>
                    <div class="stat-card">
                        <h3>${stats.total_filers}</h3>
                        <p>Total Filers</p>
                    </div>
                    <div class="stat-card">
                        <h3>${stats.politician_trades}</h3>
                        <p>Politician Trades</p>
                    </div>
                    <div class="stat-card">
                        <h3>${stats.insider_trades}</h3>
                        <p>Insider Trades</p>
                    </div>
                `;
                
                // Load recent trades
                const tradesResponse = await fetch('/api/trades?limit=20');
                const tradesData = await tradesResponse.json();
                
                const tbody = document.querySelector('#trades-table tbody');
                if (tradesData.trades.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6">No trades found. Try running data ingestion.</td></tr>';
                } else {
                    tbody.innerHTML = tradesData.trades.map(trade => `
                        <tr>
                            <td>${trade.reported_date || 'N/A'}</td>
                            <td>${trade.filer_name}</td>
                            <td>${trade.ticker || 'N/A'}</td>
                            <td>${trade.transaction_type}</td>
                            <td>$${trade.amount_usd ? trade.amount_usd.toLocaleString() : 'N/A'}</td>
                            <td>${trade.source}</td>
                        </tr>
                    `).join('');
                }
            } catch (error) {
                console.error('Failed to load dashboard:', error);
                document.getElementById('stats').innerHTML = `
                    <div class="stat-card">
                        <h3>Error</h3>
                        <p>Failed to load data: ${error.message}</p>
                    </div>
                `;
            }
        }
        
        async function runIngestion() {
            try {
                const response = await fetch('/api/ingestion/run', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({source: 'all', days: 7})
                });
                
                const result = await response.json();
                alert('Ingestion started. Check console for progress.');
                console.log('Ingestion result:', result);
                
                // Reload dashboard after a delay
                setTimeout(loadDashboard, 3000);
            } catch (error) {
                alert('Ingestion failed: ' + error.message);
            }
        }
        
        // Global state
        let currentRiskTolerance = 'moderate';
        let currentPortfolioValue = 100000;
        
        // Tab management
        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));
            
            document.getElementById(tabName + '-tab').classList.add('active');
            event.target.classList.add('active');
            
            if (tabName === 'signals') loadSignals();
            else if (tabName === 'portfolio') loadPortfolio();
            else if (tabName === 'trades') loadTrades();
        }
        
        function updateRiskTolerance() {
            currentRiskTolerance = document.getElementById('riskTolerance').value;
            loadQuickSignals();
        }
        
        function updatePortfolioValue() {
            currentPortfolioValue = parseFloat(document.getElementById('portfolioValue').value) || 100000;
            loadQuickSignals();
        }
        
        async function loadQuickSignals() {
            try {
                const response = await fetch(`/api/recommendations?portfolio_value=${currentPortfolioValue}&risk_tolerance=${currentRiskTolerance}`);
                const data = await response.json();
                const signals = data.signals || [];
                
                const container = document.getElementById('quick-signals');
                if (signals.length === 0) {
                    container.innerHTML = '<div class="stat-card"><h3>No Signals</h3><p>Run data ingestion to find opportunities</p></div>';
                    return;
                }
                
                container.innerHTML = signals.slice(0, 3).map(signal => `
                    <div class="signal-card ${signal.strength}">
                        <div class="signal-header">
                            <div class="signal-ticker">${signal.ticker}</div>
                            <div class="signal-strength ${signal.strength}">${signal.strength.replace('_', ' ')}</div>
                        </div>
                        <div class="signal-metrics">
                            <div class="signal-metric">
                                <div class="value">${Math.round(signal.confidence * 100)}%</div>
                                <div class="label">Confidence</div>
                            </div>
                            <div class="signal-metric">
                                <div class="value">${signal.current_price ? '$' + signal.current_price.toFixed(2) : 'N/A'}</div>
                                <div class="label">Price</div>
                            </div>
                        </div>
                        <div class="signal-reasoning">${signal.reasoning || 'No details available'}</div>
                    </div>
                `).join('');
            } catch (error) {
                console.error('Failed to load signals:', error);
            }
        }
        
        async function loadSignals() {
            const container = document.getElementById('signals-container');
            container.innerHTML = '<div class="loading">Loading detailed signals...</div>';
            
            try {
                const response = await fetch(`/api/signals?portfolio_value=${currentPortfolioValue}&risk_tolerance=${currentRiskTolerance}`);
                const data = await response.json();
                const signals = data.signals || [];
                
                if (signals.length === 0) {
                    container.innerHTML = '<div class="stat-card"><h3>No Signals</h3><p>No trading opportunities found</p></div>';
                    return;
                }
                
                container.innerHTML = signals.map(signal => {
                    const targetReturn = signal.target_price && signal.current_price ? 
                        ((signal.target_price - signal.current_price) / signal.current_price * 100).toFixed(1) : 'N/A';
                    
                    return `
                        <div class="signal-card ${signal.strength}">
                            <div class="signal-header">
                                <div class="signal-ticker">${signal.ticker}</div>
                                <div class="signal-strength ${signal.strength}">${signal.strength.replace('_', ' ')}</div>
                            </div>
                            <div class="signal-metrics">
                                <div class="signal-metric">
                                    <div class="value">${Math.round(signal.confidence * 100)}%</div>
                                    <div class="label">Confidence</div>
                                </div>
                                <div class="signal-metric">
                                    <div class="value">${targetReturn}%</div>
                                    <div class="label">Target Return</div>
                                </div>
                            </div>
                            <div class="signal-reasoning">${signal.reasoning}</div>
                            <div class="signal-actions">
                                <button class="btn btn-success" onclick="simulateExecute('${signal.ticker}')">Simulate Buy</button>
                            </div>
                        </div>
                    `;
                }).join('');
            } catch (error) {
                container.innerHTML = '<div class="error">Failed to load signals</div>';
            }
        }
        
        async function loadPortfolio() {
            document.getElementById('portfolio-summary').innerHTML = '<div class="loading">Loading portfolio...</div>';
            // Portfolio functionality would be implemented here
            document.getElementById('portfolio-summary').innerHTML = `
                <h3>Portfolio Summary</h3>
                <p>Portfolio tracking will be available once you start executing signals.</p>
                <p>This is a simulation environment - integrate with your broker API for live trading.</p>
            `;
        }
        
        async function loadTrades() {
            const tradesResponse = await fetch('/api/trades?limit=50');
            const tradesData = await tradesResponse.json();
            
            const tbody = document.querySelector('#trades-table tbody');
            if (tradesData.trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6">No trades found. Try running data ingestion.</td></tr>';
            } else {
                tbody.innerHTML = tradesData.trades.map(trade => `
                    <tr>
                        <td>${trade.reported_date || 'N/A'}</td>
                        <td>${trade.filer_name}</td>
                        <td>${trade.ticker || 'N/A'}</td>
                        <td>${trade.transaction_type}</td>
                        <td>$${trade.amount_usd ? trade.amount_usd.toLocaleString() : 'N/A'}</td>
                        <td>${trade.source}</td>
                    </tr>
                `).join('');
            }
        }
        
        function simulateExecute(ticker) {
            alert(`This would execute a buy order for ${ticker}\\n\\nIn a real implementation, this would:\\n• Calculate position size\\n• Submit order to broker\\n• Track the position\\n• Monitor performance`);
        }
        
        // Load dashboard on page load
        loadDashboard();
        setTimeout(loadQuickSignals, 1000);
    </script>
</body>
</html>'''
        dashboard_template.write_text(dashboard_html)
    
    # Run the application
    print(f"Starting Trading App on http://{config.web.HOST}:{config.web.PORT}")
    print("Dashboard features:")
    print("- View recent insider/politician trades")
    print("- Trigger data ingestion")
    print("- Search trades and filers")
    print("- View database statistics")
    
    app.run(
        host=config.web.HOST,
        port=config.web.PORT,
        debug=config.web.DEBUG
    )
