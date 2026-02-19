#!/usr/bin/env python3
"""
Institutional Flow Tracker - Main Screening Script

Screens for stocks with significant institutional ownership changes by analyzing
13F filings data. Identifies stocks where smart money is accumulating or distributing.

Uses data_quality module for holder classification and reliability grading
to filter out misleading signals from asymmetric 13F data.

Usage:
    python3 track_institutional_flow.py --limit 100 --min-change-percent 10
    python3 track_institutional_flow.py --sector Technology --min-institutions 20
    python3 track_institutional_flow.py --api-key YOUR_KEY --output results.json

Requirements:
    - FMP API key (set FMP_API_KEY environment variable or pass --api-key)
    - Free tier: 250 requests/day (sufficient for ~40-50 stocks)
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional
import time

try:
    import requests
except ImportError:
    print("Error: 'requests' library not installed. Install with: pip install requests")
    sys.exit(1)

# Add scripts directory to path for data_quality import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_quality import (
    calculate_coverage_ratio,
    calculate_match_ratio,
    calculate_filtered_metrics,
    reliability_grade,
    is_tradable_stock,
    deduplicate_share_classes,
)


class InstitutionalFlowTracker:
    """Track institutional ownership changes across stocks"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://financialmodelingprep.com/api/v3"

    def get_stock_screener(
        self,
        market_cap_min: int = 1000000000,
        limit: int = 100
    ) -> List[Dict]:
        """Get list of stocks meeting market cap criteria"""
        url = f"{self.base_url}/stock-screener"
        params = {
            "marketCapMoreThan": market_cap_min,
            "limit": limit,
            "apikey": self.api_key
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching stock screener: {e}")
            return []

    def get_institutional_holders(self, symbol: str) -> List[Dict]:
        """Get institutional holders for a specific stock"""
        url = f"{self.base_url}/institutional-holder/{symbol}"
        params = {"apikey": self.api_key}

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
        except requests.exceptions.RequestException as e:
            print(f"Error fetching institutional holders for {symbol}: {e}")
            return []

    def calculate_ownership_metrics(
        self,
        symbol: str,
        company_name: str,
        market_cap: float
    ) -> Optional[Dict]:
        """Calculate institutional ownership metrics for a stock.

        Uses data_quality.calculate_filtered_metrics() to compute changes
        from genuine holders only. Returns None for grade C (unreliable) stocks.
        """
        holders = self.get_institutional_holders(symbol)

        if not holders or len(holders) < 2:
            return None

        # Group by date to get quarterly snapshots
        quarters = {}
        for holder in holders:
            date = holder.get('dateReported', '')
            if not date:
                continue
            if date not in quarters:
                quarters[date] = []
            quarters[date].append(holder)

        if not quarters:
            return None

        # Get most recent quarter and previous quarter
        sorted_quarters = sorted(quarters.keys(), reverse=True)
        current_q = sorted_quarters[0]
        previous_q = sorted_quarters[1] if len(sorted_quarters) >= 2 else None

        current_holders = quarters[current_q]
        previous_holders = quarters[previous_q] if previous_q else []

        # Data quality assessment
        filtered = calculate_filtered_metrics(current_holders)
        total_count = len(current_holders)
        genuine_ratio = filtered["genuine_count"] / total_count if total_count > 0 else 0
        coverage = calculate_coverage_ratio(current_holders, previous_holders)
        match = calculate_match_ratio(current_holders, previous_holders)
        grade = reliability_grade(coverage, match, genuine_ratio)

        # Skip unreliable stocks (grade C)
        if grade == "C":
            return None

        # Use filtered metrics (genuine holders only) for percent change
        net_change = filtered["net_change"]
        total_shares_genuine = filtered["total_shares_genuine"]
        pct_change = filtered["pct_change"]

        # Total shares (all holders, for display)
        current_total_shares = sum(h.get('shares', 0) for h in current_holders)

        # Count institutions with increases vs decreases (genuine only)
        buyers = filtered["buyers"]
        sellers = filtered["sellers"]
        unchanged = filtered["genuine_count"] - buyers - sellers

        # Previous quarter institution count (if available)
        previous_count = len(previous_holders)
        current_count = total_count
        institution_change = current_count - previous_count if previous_q else 0

        # Get top holders sorted by shares held
        top_holders = sorted(
            current_holders,
            key=lambda x: x.get('shares', 0),
            reverse=True
        )[:10]

        top_holder_names = [
            {
                'name': h.get('holder', 'Unknown'),
                'shares': h.get('shares', 0),
                'change': h.get('change', 0)
            }
            for h in top_holders
        ]

        return {
            'symbol': symbol,
            'company_name': company_name,
            'market_cap': market_cap,
            'current_quarter': current_q,
            'previous_quarter': previous_q or 'N/A',
            'current_total_shares': current_total_shares,
            'previous_total_shares': total_shares_genuine - net_change,
            'shares_change': net_change,
            'percent_change': round(pct_change, 2),
            'current_institution_count': current_count,
            'previous_institution_count': previous_count,
            'institution_count_change': institution_change,
            'buyers': buyers,
            'sellers': sellers,
            'unchanged': unchanged,
            'top_holders': top_holder_names,
            'reliability_grade': grade,
            'genuine_ratio': round(genuine_ratio, 4),
        }

    def screen_stocks(
        self,
        min_market_cap: int = 1000000000,
        min_change_percent: float = 10.0,
        min_institutions: int = 10,
        sector: Optional[str] = None,
        top: int = 50,
        sort_by: str = 'ownership_change',
        limit: int = 100,
    ) -> List[Dict]:
        """Screen for stocks with significant institutional changes"""

        print(f"Fetching stocks with market cap >= ${min_market_cap:,}...")
        stocks = self.get_stock_screener(market_cap_min=min_market_cap, limit=limit)

        if not stocks:
            print("No stocks found in screener")
            return []

        # Filter by sector if specified
        if sector:
            stocks = [s for s in stocks if s.get('sector', '').lower() == sector.lower()]
            print(f"Filtered to {len(stocks)} stocks in {sector} sector")

        # Filter out ETFs and non-tradable stocks early (saves API calls)
        tradable_stocks = []
        for s in stocks:
            profile = {
                'symbol': s.get('symbol', ''),
                'companyName': s.get('companyName', ''),
                'isEtf': s.get('isEtf', False),
                'isFund': s.get('isFund', False),
                'isActivelyTrading': s.get('isActivelyTrading', True),
            }
            if is_tradable_stock(profile):
                tradable_stocks.append(s)

        skipped = len(stocks) - len(tradable_stocks)
        if skipped > 0:
            print(f"Skipped {skipped} ETFs/funds/inactive stocks")

        stocks = tradable_stocks
        print(f"Analyzing institutional ownership for {len(stocks)} stocks...")
        print("This may take a few minutes. Please wait...\n")

        results = []
        for i, stock in enumerate(stocks, 1):
            symbol = stock.get('symbol', '')
            company_name = stock.get('companyName', '')
            market_cap = stock.get('marketCap', 0)

            if i % 10 == 0:
                print(f"Progress: {i}/{len(stocks)} stocks analyzed...")

            # Rate limiting: max 5 requests per second
            time.sleep(0.2)

            metrics = self.calculate_ownership_metrics(symbol, company_name, market_cap)

            if metrics:
                # Apply filters
                if abs(metrics['percent_change']) >= min_change_percent:
                    if metrics['current_institution_count'] >= min_institutions:
                        results.append(metrics)

        # Deduplicate share classes (BRK-A/B, GOOG/GOOGL, etc.)
        results = deduplicate_share_classes(results)

        print(f"\nFound {len(results)} stocks meeting criteria")

        # Sort results
        if sort_by == 'ownership_change':
            results.sort(key=lambda x: abs(x['percent_change']), reverse=True)
        elif sort_by == 'institution_count_change':
            results.sort(key=lambda x: abs(x['institution_count_change']), reverse=True)

        return results[:top]

    def generate_report(self, results: List[Dict], output_file: str = None,
                        output_dir: str = None):
        """Generate markdown report from screening results"""

        if not results:
            print("No results to report")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        report = f"""# Institutional Flow Analysis Report
**Generated:** {timestamp}
**Stocks Analyzed:** {len(results)}

## Summary

This report identifies stocks with significant institutional ownership changes based on 13F filings data.
Only stocks with **Grade A or B** data reliability are included. Grade C (unreliable) stocks are excluded.

### Key Findings

**Top Accumulators (Institutions Buying):**
"""

        # Top accumulators
        accumulators = [r for r in results if r['percent_change'] > 0][:10]
        if accumulators:
            report += "\n| Symbol | Company | Ownership Change | Grade | Institution Change | Top Holder |\n"
            report += "|--------|---------|-----------------|-------|-------------------|------------|\n"
            for r in accumulators:
                top_holder = r['top_holders'][0]['name'] if r['top_holders'] else 'N/A'
                report += (f"| {r['symbol']} | {r['company_name'][:30]} "
                          f"| **+{r['percent_change']}%** | {r['reliability_grade']} "
                          f"| +{r['institution_count_change']} | {top_holder[:30]} |\n")
        else:
            report += "\nNo significant accumulation detected.\n"

        report += "\n**Top Distributors (Institutions Selling):**\n"

        # Top distributors
        distributors = [r for r in results if r['percent_change'] < 0][:10]
        if distributors:
            report += "\n| Symbol | Company | Ownership Change | Grade | Institution Change | Previously Top Holder |\n"
            report += "|--------|---------|-----------------|-------|-------------------|-----------------------|\n"
            for r in distributors:
                top_holder = r['top_holders'][0]['name'] if r['top_holders'] else 'N/A'
                report += (f"| {r['symbol']} | {r['company_name'][:30]} "
                          f"| **{r['percent_change']}%** | {r['reliability_grade']} "
                          f"| {r['institution_count_change']} | {top_holder[:30]} |\n")
        else:
            report += "\nNo significant distribution detected.\n"

        report += "\n## Detailed Results\n\n"

        for r in results[:20]:  # Top 20 detailed
            direction = "Accumulation" if r['percent_change'] > 0 else "Distribution"
            grade_label = f"Grade {r['reliability_grade']}"
            if r['reliability_grade'] == 'B':
                grade_label += " (Reference Only)"

            report += f"""### {r['symbol']} - {r['company_name']}

**Signal:** {direction} ({r['percent_change']:+.2f}% institutional ownership change)
**Data Reliability:** {grade_label} (genuine ratio: {r['genuine_ratio']:.1%})

**Metrics:**
- Market Cap: ${r['market_cap']:,.0f}
- Current Quarter: {r['current_quarter']}
- Institutions: {r['current_institution_count']} (Buyers: {r.get('buyers', 'N/A')}, Sellers: {r.get('sellers', 'N/A')}, Unchanged: {r.get('unchanged', 'N/A')})
- Net Shares Change (genuine only): {r['shares_change']:+,.0f}
- Estimated Previous Total (genuine): {r['previous_total_shares']:,.0f} shares

**Top 5 Current Holders:**
"""
            for i, holder in enumerate(r['top_holders'][:5], 1):
                report += f"{i}. {holder['name']}: {holder['shares']:,} shares (Change: {holder['change']:+,})\n"

            report += "\n---\n\n"

        report += f"""
## Methodology

### Data Quality Filtering

This report uses **holder classification** to ensure reliable metrics:

- **Genuine holders:** Present in both quarters, partial position change
- **New-full entries:** First-time appearance (change == shares) - excluded from % calculation
- **Exited holders:** Fully sold (shares == 0) - excluded from % calculation

**Reliability Grades:**
- **Grade A:** Coverage ratio < 3x, match ratio >= 50%, genuine ratio >= 70% - Safe for investment decisions
- **Grade B:** Genuine ratio >= 30% - Reference only (use with caution)
- **Grade C:** Genuine ratio < 30% - EXCLUDED from this report

### Interpretation Guide

**Strong Accumulation (>15% increase):**
- Monitor for potential breakout
- Validate with fundamental analysis
- Consider initiating/adding to position

**Moderate Accumulation (7-15% increase):**
- Positive signal
- Combine with other analysis
- Watch for continuation

**Strong Distribution (>15% decrease):**
- Warning sign
- Re-evaluate thesis
- Consider trimming/exiting

**Moderate Distribution (7-15% decrease):**
- Early warning
- Monitor closely
- Tighten stop-loss

For detailed interpretation framework, see:
`institutional-flow-tracker/references/interpretation_framework.md`

---

**Data Source:** Financial Modeling Prep API (13F Filings)
**Note:** 13F data has ~45-day reporting lag. Use as confirming indicator, not real-time signal.
**Note:** Percent changes are calculated from genuine holders only to prevent inflated metrics.
"""

        # Determine output path
        if output_file:
            output_path = output_file if output_file.endswith('.md') else f"{output_file}.md"
        else:
            filename = f"institutional_flow_screening_{datetime.now().strftime('%Y%m%d')}.md"
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, filename)
            else:
                output_path = filename

        with open(output_path, 'w') as f:
            f.write(report)
        print(f"\nReport saved to: {output_path}")

        return report


def main():
    parser = argparse.ArgumentParser(
        description='Track institutional ownership changes across stocks',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Screen top 50 stocks by institutional change (>10%)
  python3 track_institutional_flow.py --top 50 --min-change-percent 10

  # Focus on Technology sector
  python3 track_institutional_flow.py --sector Technology --min-institutions 20

  # Custom screening with limited API calls (free tier friendly)
  python3 track_institutional_flow.py --limit 50 --min-change-percent 5

  # Custom output directory
  python3 track_institutional_flow.py --output-dir reports/
        """
    )

    parser.add_argument(
        '--api-key',
        type=str,
        default=os.getenv('FMP_API_KEY'),
        help='FMP API key (or set FMP_API_KEY environment variable)'
    )
    parser.add_argument(
        '--top',
        type=int,
        default=50,
        help='Number of top stocks to return (default: 50)'
    )
    parser.add_argument(
        '--min-change-percent',
        type=float,
        default=10.0,
        help='Minimum %% change in institutional ownership (default: 10.0)'
    )
    parser.add_argument(
        '--min-market-cap',
        type=int,
        default=1000000000,
        help='Minimum market cap in dollars (default: 1B)'
    )
    parser.add_argument(
        '--sector',
        type=str,
        help='Filter by specific sector (e.g., Technology, Healthcare)'
    )
    parser.add_argument(
        '--min-institutions',
        type=int,
        default=10,
        help='Minimum number of institutional holders (default: 10)'
    )
    parser.add_argument(
        '--sort-by',
        type=str,
        choices=['ownership_change', 'institution_count_change'],
        default='ownership_change',
        help='Sort results by metric (default: ownership_change)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=100,
        help='Number of stocks to fetch from screener (default: 100). '
             'Lower values save API calls for free tier.'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Output file path for JSON results'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='reports/',
        help='Output directory for reports (default: reports/)'
    )

    args = parser.parse_args()

    # Validate API key
    if not args.api_key:
        print("Error: FMP API key required")
        print("Set FMP_API_KEY environment variable or pass --api-key argument")
        print("Get free API key at: https://financialmodelingprep.com/developer/docs")
        sys.exit(1)

    # Initialize tracker
    tracker = InstitutionalFlowTracker(args.api_key)

    # Run screening
    results = tracker.screen_stocks(
        min_market_cap=args.min_market_cap,
        min_change_percent=args.min_change_percent,
        min_institutions=args.min_institutions,
        sector=args.sector,
        top=args.top,
        sort_by=args.sort_by,
        limit=args.limit,
    )

    # Save JSON results if requested
    if args.output:
        json_output = args.output if args.output.endswith('.json') else f"{args.output}.json"
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            json_output = os.path.join(args.output_dir, os.path.basename(json_output))
        with open(json_output, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"JSON results saved to: {json_output}")

    # Generate markdown report
    tracker.generate_report(results, output_dir=args.output_dir)

    # Print summary
    if results:
        print("\n" + "="*80)
        print("TOP 10 INSTITUTIONAL FLOW CHANGES (Grade A/B only)")
        print("="*80)
        print(f"{'Symbol':<8} {'Company':<25} {'Change':>10} {'Grade':>6} {'Institutions':>12}")
        print("-"*80)
        for r in results[:10]:
            print(f"{r['symbol']:<8} {r['company_name'][:25]:<25} "
                  f"{r['percent_change']:>9.2f}% {r['reliability_grade']:>5} "
                  f"{r['institution_count_change']:>+11d}")


if __name__ == '__main__':
    main()
