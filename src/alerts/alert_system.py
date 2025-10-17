"""
Alert System for high-value signals.

Supports email, SMS (Twilio), and Telegram notifications.
"""

import logging
import os
from datetime import datetime
from typing import List, Dict
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


class AlertSystem:
    """Manages alerts for high-confidence signals."""
    
    def __init__(self):
        # Email config
        self.smtp_host = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.alert_email = os.getenv('ALERT_EMAIL')
        
        # Twilio config (for SMS)
        self.twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.twilio_from = os.getenv('TWILIO_PHONE_NUMBER')
        self.alert_phone = os.getenv('ALERT_PHONE_NUMBER')
        
        # Telegram config
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
    
    def send_signal_alert(self, signal: Dict, alert_type: str = 'all') -> Dict:
        """
        Send alert for a high-confidence signal.
        
        Args:
            signal: Signal dict with ticker, confidence, reasoning, etc.
            alert_type: 'email', 'sms', 'telegram', or 'all'
        
        Returns:
            Dict with success status for each channel
        """
        results = {'timestamp': datetime.now().isoformat()}
        
        # Build message
        subject = f"🚨 High-Confidence Signal: {signal['ticker']}"
        message = self._format_signal_message(signal)
        
        # Send via requested channels
        if alert_type in ['email', 'all']:
            results['email'] = self._send_email(subject, message)
        
        if alert_type in ['sms', 'all']:
            results['sms'] = self._send_sms(message)
        
        if alert_type in ['telegram', 'all']:
            results['telegram'] = self._send_telegram(message)
        
        return results
    
    def send_daily_digest(self, summary: Dict) -> Dict:
        """Send daily summary of signals and performance."""
        subject = f"📊 Daily Insider Intelligence Summary - {datetime.now().strftime('%Y-%m-%d')}"
        
        message = f"""
Daily Insider Trading Intelligence Summary

===========================================

NEW SIGNALS TODAY: {summary.get('new_signals', 0)}
Average Confidence: {summary.get('avg_confidence', 0):.1f}%

TOP 3 SIGNALS:
{self._format_top_signals(summary.get('top_signals', []))}

PORTFOLIO PERFORMANCE:
Total Return: {summary.get('portfolio_return', 0):.2f}%
Win Rate: {summary.get('win_rate', 0):.1f}%
Current Value: ${summary.get('portfolio_value', 0):,.2f}

INSIDER ACTIVITY:
Most Active: {summary.get('most_active_insider', 'N/A')}
Hottest Sector: {summary.get('hottest_sector', 'N/A')}

View full dashboard: http://localhost:8000/premium

===========================================
"""
        
        return self._send_email(subject, message)
    
    def _format_signal_message(self, signal: Dict) -> str:
        """Format signal into alert message."""
        return f"""
🚨 HIGH-CONFIDENCE INSIDER TRADING SIGNAL

Ticker: {signal['ticker']}
Confidence: {signal['confidence']}%
Signal Type: {signal.get('type', 'BUY')}

Number of Insiders: {signal.get('num_insiders', 1)}
Total Volume: ${signal.get('total_volume', 0):,.0f}

Reasoning:
{signal.get('reasoning', 'No details provided')}

View full details: http://localhost:8000/premium

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    def _format_top_signals(self, signals: List[Dict]) -> str:
        """Format top signals for digest."""
        if not signals:
            return "No signals today"
        
        formatted = []
        for i, sig in enumerate(signals[:3], 1):
            formatted.append(
                f"{i}. {sig['ticker']} - {sig['confidence']}% confidence\n"
                f"   {sig.get('reasoning', '')[:100]}..."
            )
        
        return "\n\n".join(formatted)
    
    def _send_email(self, subject: str, body: str) -> Dict:
        """Send email alert."""
        if not all([self.smtp_user, self.smtp_password, self.alert_email]):
            logger.warning("Email not configured")
            return {'success': False, 'error': 'Email not configured'}
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_user
            msg['To'] = self.alert_email
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email sent to {self.alert_email}")
            return {'success': True, 'to': self.alert_email}
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return {'success': False, 'error': str(e)}
    
    def _send_sms(self, message: str) -> Dict:
        """Send SMS via Twilio."""
        if not all([self.twilio_sid, self.twilio_token, self.twilio_from, self.alert_phone]):
            logger.warning("SMS not configured")
            return {'success': False, 'error': 'SMS not configured'}
        
        try:
            from twilio.rest import Client
            
            client = Client(self.twilio_sid, self.twilio_token)
            
            # Truncate message to 1600 chars (SMS limit)
            sms_message = message[:1600] if len(message) > 1600 else message
            
            msg = client.messages.create(
                body=sms_message,
                from_=self.twilio_from,
                to=self.alert_phone
            )
            
            logger.info(f"SMS sent to {self.alert_phone}: {msg.sid}")
            return {'success': True, 'to': self.alert_phone, 'sid': msg.sid}
            
        except ImportError:
            return {'success': False, 'error': 'Twilio library not installed (pip install twilio)'}
        except Exception as e:
            logger.error(f"Failed to send SMS: {e}")
            return {'success': False, 'error': str(e)}
    
    def _send_telegram(self, message: str) -> Dict:
        """Send Telegram message."""
        if not all([self.telegram_bot_token, self.telegram_chat_id]):
            logger.warning("Telegram not configured")
            return {'success': False, 'error': 'Telegram not configured'}
        
        try:
            import requests
            
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            
            payload = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Telegram message sent to {self.telegram_chat_id}")
            return {'success': True, 'to': self.telegram_chat_id}
            
        except Exception as e:
            logger.error(f"Failed to send Telegram: {e}")
            return {'success': False, 'error': str(e)}


def check_and_send_alerts():
    """
    Check for high-confidence signals and send alerts.
    
    This function should be called periodically (e.g., via cron).
    """
    from src.database import get_session
    from src.database.models import Signal
    from datetime import timedelta
    
    alert_system = AlertSystem()
    
    # Get signals from last hour with >90% confidence
    cutoff = datetime.now() - timedelta(hours=1)
    
    with get_session() as session:
        high_conf_signals = session.query(Signal).filter(
            Signal.generated_at >= cutoff,
            Signal.strength >= 0.9,
            Signal.is_active == True
        ).all()
        
        sent = 0
        for signal in high_conf_signals:
            signal_dict = {
                'ticker': signal.ticker,
                'confidence': signal.strength * 100,
                'type': signal.signal_type.value if hasattr(signal.signal_type, 'value') else signal.signal_type,
                'reasoning': signal.reasoning or 'No details available'
            }
            
            result = alert_system.send_signal_alert(signal_dict, alert_type='email')
            if result.get('email', {}).get('success'):
                sent += 1
        
        return {'sent': sent, 'checked': len(high_conf_signals)}

