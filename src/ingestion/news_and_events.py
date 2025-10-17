"""News aggregator and event calendar for market intelligence."""

import logging
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from config.config import config


class NewsAggregator:
    """Aggregate news from multiple sources."""
    
    def __init__(self):
        self.logger = logging.getLogger("news_aggregator")
        
        # API keys
        self.polygon_key = config.api.POLYGON_API_KEY
        self.finnhub_key = config.api.FINNHUB_API_KEY
        self.alpha_vantage_key = config.api.ALPHA_VANTAGE_API_KEY
        
    def get_ticker_news(self, ticker: str, limit: int = 10) -> List[Dict]:
        """Get news for a specific ticker from all available sources."""
        
        all_news = []
        
        # Polygon.io news
        if self.polygon_key:
            all_news.extend(self._get_polygon_news(ticker, limit))
        
        # Finnhub news
        if self.finnhub_key:
            all_news.extend(self._get_finnhub_news(ticker))
        
        # Alpha Vantage news
        if self.alpha_vantage_key:
            all_news.extend(self._get_alpha_vantage_news(ticker))
        
        # Sort by date
        all_news.sort(key=lambda x: x.get('published_date', ''), reverse=True)
        
        return all_news[:limit]
    
    def _get_polygon_news(self, ticker: str, limit: int) -> List[Dict]:
        """Get news from Polygon.io."""
        
        url = "https://api.polygon.io/v2/reference/news"
        params = {
            'ticker': ticker,
            'limit': limit,
            'apiKey': self.polygon_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            news_items = []
            for item in data.get('results', []):
                news_items.append({
                    'source': 'polygon',
                    'title': item.get('title'),
                    'description': item.get('description'),
                    'url': item.get('article_url'),
                    'published_date': item.get('published_utc'),
                    'publisher': item.get('publisher', {}).get('name'),
                    'tickers': item.get('tickers', [])
                })
            
            return news_items
            
        except Exception as e:
            self.logger.error(f"Failed to fetch Polygon news: {e}")
            return []
    
    def _get_finnhub_news(self, ticker: str) -> List[Dict]:
        """Get news from Finnhub."""
        
        url = "https://finnhub.io/api/v1/company-news"
        today = date.today()
        week_ago = today - timedelta(days=7)
        
        params = {
            'symbol': ticker,
            'from': week_ago.isoformat(),
            'to': today.isoformat(),
            'token': self.finnhub_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            news_items = []
            for item in data:
                news_items.append({
                    'source': 'finnhub',
                    'title': item.get('headline'),
                    'description': item.get('summary'),
                    'url': item.get('url'),
                    'published_date': datetime.fromtimestamp(item.get('datetime', 0)).isoformat(),
                    'publisher': item.get('source'),
                    'category': item.get('category')
                })
            
            return news_items
            
        except Exception as e:
            self.logger.error(f"Failed to fetch Finnhub news: {e}")
            return []
    
    def _get_alpha_vantage_news(self, ticker: str) -> List[Dict]:
        """Get news sentiment from Alpha Vantage."""
        
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'NEWS_SENTIMENT',
            'tickers': ticker,
            'apikey': self.alpha_vantage_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            news_items = []
            for item in data.get('feed', []):
                news_items.append({
                    'source': 'alphavantage',
                    'title': item.get('title'),
                    'description': item.get('summary'),
                    'url': item.get('url'),
                    'published_date': item.get('time_published'),
                    'publisher': item.get('source'),
                    'sentiment': item.get('overall_sentiment_label'),
                    'sentiment_score': item.get('overall_sentiment_score')
                })
            
            return news_items
            
        except Exception as e:
            self.logger.error(f"Failed to fetch Alpha Vantage news: {e}")
            return []
    
    def get_market_news(self, limit: int = 20) -> List[Dict]:
        """Get general market news."""
        
        all_news = []
        
        # Finnhub general news
        if self.finnhub_key:
            url = "https://finnhub.io/api/v1/news"
            params = {'category': 'general', 'token': self.finnhub_key}
            
            try:
                response = requests.get(url, params=params, timeout=10)
                data = response.json()
                
                for item in data[:limit]:
                    all_news.append({
                        'source': 'finnhub',
                        'title': item.get('headline'),
                        'description': item.get('summary'),
                        'url': item.get('url'),
                        'published_date': datetime.fromtimestamp(item.get('datetime', 0)).isoformat(),
                        'category': item.get('category')
                    })
            except Exception as e:
                self.logger.error(f"Failed to fetch market news: {e}")
        
        return all_news


class EventCalendar:
    """Track important market events."""
    
    def __init__(self):
        self.logger = logging.getLogger("event_calendar")
        self.finnhub_key = config.api.FINNHUB_API_KEY
        self.alpha_vantage_key = config.api.ALPHA_VANTAGE_API_KEY
        
    def get_earnings_calendar(self, from_date: date = None, to_date: date = None) -> List[Dict]:
        """Get earnings calendar."""
        
        if not from_date:
            from_date = date.today()
        if not to_date:
            to_date = from_date + timedelta(days=7)
        
        events = []
        
        # Finnhub earnings calendar
        if self.finnhub_key:
            events.extend(self._get_finnhub_earnings(from_date, to_date))
        
        # Alpha Vantage earnings
        if self.alpha_vantage_key:
            events.extend(self._get_alpha_vantage_earnings())
        
        return events
    
    def _get_finnhub_earnings(self, from_date: date, to_date: date) -> List[Dict]:
        """Get earnings from Finnhub."""
        
        url = "https://finnhub.io/api/v1/calendar/earnings"
        params = {
            'from': from_date.isoformat(),
            'to': to_date.isoformat(),
            'token': self.finnhub_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            events = []
            for item in data.get('earningsCalendar', []):
                events.append({
                    'type': 'earnings',
                    'ticker': item.get('symbol'),
                    'date': item.get('date'),
                    'eps_estimate': item.get('epsEstimate'),
                    'eps_actual': item.get('epsActual'),
                    'revenue_estimate': item.get('revenueEstimate'),
                    'revenue_actual': item.get('revenueActual'),
                    'hour': item.get('hour')  # 'bmo' or 'amc' (before/after market)
                })
            
            return events
            
        except Exception as e:
            self.logger.error(f"Failed to fetch Finnhub earnings: {e}")
            return []
    
    def _get_alpha_vantage_earnings(self) -> List[Dict]:
        """Get earnings from Alpha Vantage."""
        
        url = "https://www.alphavantage.co/query"
        params = {
            'function': 'EARNINGS_CALENDAR',
            'horizon': '3month',
            'apikey': self.alpha_vantage_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            # Alpha Vantage returns CSV
            lines = response.text.strip().split('\n')
            
            events = []
            if len(lines) > 1:
                headers = lines[0].split(',')
                for line in lines[1:]:
                    values = line.split(',')
                    if len(values) >= 3:
                        events.append({
                            'type': 'earnings',
                            'ticker': values[0],
                            'date': values[1],
                            'eps_estimate': values[2] if len(values) > 2 else None
                        })
            
            return events[:50]  # Limit to 50
            
        except Exception as e:
            self.logger.error(f"Failed to fetch Alpha Vantage earnings: {e}")
            return []
    
    def get_economic_calendar(self) -> List[Dict]:
        """Get economic events (FOMC, GDP, etc.)."""
        
        if not self.finnhub_key:
            return []
        
        url = "https://finnhub.io/api/v1/calendar/economic"
        params = {'token': self.finnhub_key}
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            events = []
            for item in data.get('economicCalendar', []):
                events.append({
                    'type': 'economic',
                    'event': item.get('event'),
                    'date': item.get('time'),
                    'country': item.get('country'),
                    'actual': item.get('actual'),
                    'estimate': item.get('estimate'),
                    'previous': item.get('previous'),
                    'impact': item.get('impact')
                })
            
            return events
            
        except Exception as e:
            self.logger.error(f"Failed to fetch economic calendar: {e}")
            return []
    
    def get_ipo_calendar(self) -> List[Dict]:
        """Get IPO calendar."""
        
        if not self.finnhub_key:
            return []
        
        today = date.today()
        from_date = today - timedelta(days=30)
        to_date = today + timedelta(days=30)
        
        url = "https://finnhub.io/api/v1/calendar/ipo"
        params = {
            'from': from_date.isoformat(),
            'to': to_date.isoformat(),
            'token': self.finnhub_key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            events = []
            for item in data.get('ipoCalendar', []):
                events.append({
                    'type': 'ipo',
                    'ticker': item.get('symbol'),
                    'date': item.get('date'),
                    'company': item.get('name'),
                    'exchange': item.get('exchange'),
                    'actions': item.get('actions'),
                    'shares': item.get('numberOfShares'),
                    'price': item.get('price'),
                    'status': item.get('status')
                })
            
            return events
            
        except Exception as e:
            self.logger.error(f"Failed to fetch IPO calendar: {e}")
            return []
    
    def get_fed_calendar(self) -> List[Dict]:
        """Get Federal Reserve meeting calendar."""
        
        # Federal Reserve publishes calendar on their website
        # This is a simplified version
        
        fed_meetings_2024 = [
            {'date': '2024-01-31', 'type': 'FOMC Meeting'},
            {'date': '2024-03-20', 'type': 'FOMC Meeting'},
            {'date': '2024-05-01', 'type': 'FOMC Meeting'},
            {'date': '2024-06-12', 'type': 'FOMC Meeting'},
            {'date': '2024-07-31', 'type': 'FOMC Meeting'},
            {'date': '2024-09-18', 'type': 'FOMC Meeting'},
            {'date': '2024-11-07', 'type': 'FOMC Meeting'},
            {'date': '2024-12-18', 'type': 'FOMC Meeting'},
        ]
        
        fed_meetings_2025 = [
            {'date': '2025-01-29', 'type': 'FOMC Meeting'},
            {'date': '2025-03-19', 'type': 'FOMC Meeting'},
            {'date': '2025-04-30', 'type': 'FOMC Meeting'},
            {'date': '2025-06-18', 'type': 'FOMC Meeting'},
            {'date': '2025-07-30', 'type': 'FOMC Meeting'},
            {'date': '2025-09-17', 'type': 'FOMC Meeting'},
            {'date': '2025-11-05', 'type': 'FOMC Meeting'},
            {'date': '2025-12-10', 'type': 'FOMC Meeting'},
        ]
        
        all_meetings = fed_meetings_2024 + fed_meetings_2025
        
        # Filter to upcoming meetings
        today = date.today().isoformat()
        upcoming = [m for m in all_meetings if m['date'] >= today]
        
        return upcoming[:3]  # Next 3 meetings


# Test function
def main():
    """Test news and events."""
    logging.basicConfig(level=logging.INFO)
    
    print("Testing News & Events...\n")
    
    # News
    news = NewsAggregator()
    print("📰 News Aggregator:")
    ticker_news = news.get_ticker_news('NVDA', limit=3)
    if ticker_news:
        print(f"   ✅ Found {len(ticker_news)} news items for NVDA")
        for item in ticker_news[:2]:
            print(f"   - {item.get('title', 'No title')[:60]}...")
    else:
        print("   ⚠️  No news (may need API keys)")
    
    # Events
    calendar = EventCalendar()
    print("\n📅 Event Calendar:")
    
    earnings = calendar.get_earnings_calendar()
    if earnings:
        print(f"   ✅ Found {len(earnings)} earnings events")
        for event in earnings[:3]:
            print(f"   - {event.get('ticker')}: {event.get('date')}")
    else:
        print("   ⚠️  No earnings data (may need API keys)")
    
    fed_meetings = calendar.get_fed_calendar()
    print(f"\n   📊 Next FOMC meetings:")
    for meeting in fed_meetings:
        print(f"   - {meeting['date']}: {meeting['type']}")


if __name__ == "__main__":
    main()

