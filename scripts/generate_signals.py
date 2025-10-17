#!/usr/bin/env python3
"""Generate trading signals for personal portfolio decisions."""

import sys
import os
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analysis.signal_generator import SignalGenerator
from src.analysis.portfolio_manager import PortfolioManager


def main():
    parser = argparse.ArgumentParser(description="Generate personalized trading signals")
    parser.add_argument("--portfolio-value", type=float, default=100000,
                       help="Your portfolio value ($)")
    parser.add_argument("--risk-tolerance", choices=['conservative', 'moderate', 'aggressive'],
                       default='moderate', help="Risk tolerance level")
    parser.add_argument("--top-n", type=int, default=10,
                       help="Number of top signals to show")
    parser.add_argument("--min-confidence", type=float, default=0.4,
                       help="Minimum confidence threshold (0.0-1.0)")
    
    args = parser.parse_args()
    
    print("🔍 Generating Personal Investment Signals...")
    print(f"Portfolio Value: ${args.portfolio_value:,.0f}")
    print(f"Risk Tolerance: {args.risk_tolerance.title()}")
    print(f"Min Confidence: {args.min_confidence:.1%}")
    print("=" * 60)
    
    try:
        # Generate recommendations
        manager = PortfolioManager(args.portfolio_value, args.risk_tolerance)
        recommendations = manager.get_current_recommendations()
        
        signals = recommendations.get('signals', [])
        
        # Filter by confidence
        signals = [s for s in signals if s.confidence >= args.min_confidence]
        
        if not signals:
            print("❌ No signals found meeting your criteria")
            print("\nSuggestions:")
            print("• Lower your confidence threshold with --min-confidence")
            print("• Run data ingestion: python scripts/run_ingestion.py")
            print("• Check if there's recent insider activity")
            return
        
        # Show summary
        summary = recommendations.get('summary', {})
        print(f"📊 SUMMARY")
        print(f"• Signals Found: {len(signals)}")
        print(f"• Average Confidence: {summary.get('average_confidence', 0):.1%}")
        print(f"• Recommended Allocation: {summary.get('total_allocation', 0):.1%}")
        print(f"• Cash Allocation: {recommendations.get('cash_allocation', 1.0):.1%}")
        
        print(f"\n🎯 TOP {args.top_n} INVESTMENT OPPORTUNITIES")
        print("=" * 60)
        
        # Show top signals
        for i, signal in enumerate(signals[:args.top_n], 1):
            
            # Calculate metrics
            target_return = 0
            if signal.target_price and signal.current_price:
                target_return = (signal.target_price - signal.current_price) / signal.current_price
            
            position_value = args.portfolio_value * (signal.position_size_pct or 0)
            
            print(f"\n{i}. {signal.ticker} - {signal.strength.value.replace('_', ' ').title()}")
            print(f"   📈 Confidence: {signal.confidence:.1%}")
            print(f"   💰 Current Price: ${signal.current_price:.2f}")
            print(f"   🎯 Target Return: {target_return:.1%}")
            print(f"   📊 Position Size: ${position_value:,.0f} ({signal.position_size_pct:.1%})")
            print(f"   ⏰ Time Horizon: {signal.time_horizon_days} days")
            
            print(f"\n   💡 Why this signal:")
            print(f"   {signal.reasoning}")
            
            if signal.risk_factors:
                print(f"\n   ⚠️  Risk factors:")
                for risk in signal.risk_factors[:2]:
                    print(f"   • {risk}")
            
            print(f"\n   📋 Supporting patterns: {', '.join(signal.supporting_patterns)}")
            print("   " + "-" * 50)
        
        # Show allocation summary
        allocation = recommendations.get('allocation', {})
        if allocation:
            print(f"\n📋 RECOMMENDED PORTFOLIO ALLOCATION")
            print("=" * 60)
            
            total_allocation = 0
            for ticker, pct in sorted(allocation.items(), key=lambda x: x[1], reverse=True):
                dollar_amount = args.portfolio_value * pct
                total_allocation += pct
                print(f"   {ticker}: {pct:.1%} (${dollar_amount:,.0f})")
            
            cash_pct = 1.0 - total_allocation
            cash_amount = args.portfolio_value * cash_pct
            print(f"   CASH: {cash_pct:.1%} (${cash_amount:,.0f})")
        
        # Show actionable next steps
        print(f"\n🚀 NEXT STEPS")
        print("=" * 60)
        print("1. Review each signal's reasoning and risk factors")
        print("2. Do additional research on recommended stocks")
        print("3. Start with smaller position sizes to test the strategy")
        print("4. Monitor performance and adjust based on results")
        print("5. Use stop losses and target prices as suggested")
        
        print(f"\n💡 Pro Tips:")
        print("• This is educational/research use only - not financial advice")
        print("• Consider dollar-cost averaging into positions")
        print("• Diversify across multiple signals to reduce risk")
        print("• Keep detailed records for tax and performance tracking")
        
    except Exception as e:
        print(f"❌ Error generating signals: {e}")
        print("\nTroubleshooting:")
        print("• Make sure the database is set up: python scripts/setup_db.py")
        print("• Run data ingestion: python scripts/run_ingestion.py")
        print("• Check that you have price data: python -m src.ingestion.data_normalizer --prices")


if __name__ == "__main__":
    main()
