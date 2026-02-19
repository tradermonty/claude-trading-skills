#!/usr/bin/env python3
"""
Institutional Flow Tracker - Single Stock Deep Dive

Provides detailed analysis of institutional ownership for a specific stock,
including historical trends, top holders, and position changes.

Uses data_quality module for holder classification and reliability grading
to prevent misleading signals from asymmetric 13F data.

Usage:
    python3 analyze_single_stock.py AAPL
    python3 analyze_single_stock.py MSFT --quarters 12 --api-key YOUR_KEY
    python3 analyze_single_stock.py TSLA --output-dir reports/

Requirements:
    - FMP API key (set FMP_API_KEY environment variable or pass --api-key)
"""

import argparse
import os
import sys
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict

try:
    import requests
except ImportError:
    print("Error: 'requests' library not installed. Install with: pip install requests")
    sys.exit(1)

# Add scripts directory to path for data_quality import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_quality import (
    classify_holder,
    calculate_coverage_ratio,
    calculate_match_ratio,
    calculate_filtered_metrics,
    reliability_grade,
)


class SingleStockAnalyzer:
    """Analyze institutional ownership for a single stock"""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://financialmodelingprep.com/api/v3"

    def get_institutional_holders(self, symbol: str) -> List[Dict]:
        """Get all institutional holders data for a stock"""
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

    def get_company_profile(self, symbol: str) -> Dict:
        """Get company profile information"""
        url = f"{self.base_url}/profile/{symbol}"
        params = {"apikey": self.api_key}

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            return data[0] if isinstance(data, list) and data else {}
        except requests.exceptions.RequestException as e:
            print(f"Error fetching company profile for {symbol}: {e}")
            return {}

    def analyze_stock(self, symbol: str, quarters: int = 8) -> Dict:
        """Perform comprehensive institutional analysis on a stock.

        Uses classify_holder() to separate genuine position changes from
        new-full entries and exits, avoiding inflated metrics from
        asymmetric holder counts across quarters.
        """

        print(f"Analyzing institutional ownership for {symbol}...")

        # Get company profile
        profile = self.get_company_profile(symbol)
        company_name = profile.get('companyName', symbol)
        sector = profile.get('sector', 'Unknown')
        market_cap = profile.get('mktCap', 0)

        print(f"Company: {company_name}")
        print(f"Sector: {sector}")
        print(f"Market Cap: ${market_cap:,}")

        # Get institutional holders
        holders = self.get_institutional_holders(symbol)

        if not holders:
            print(f"No institutional holder data available for {symbol}")
            return {}

        # Group by quarter
        quarters_data = defaultdict(list)
        for holder in holders:
            date = holder.get('dateReported', '')
            if date:
                quarters_data[date].append(holder)

        # Get most recent N quarters
        sorted_quarters = sorted(quarters_data.keys(), reverse=True)[:quarters]

        if len(sorted_quarters) < 2:
            print(f"Insufficient data (need at least 2 quarters, found {len(sorted_quarters)})")
            return {}

        # Calculate quarterly metrics using correct FMP v3 field names
        quarterly_metrics = []
        all_holders_by_quarter = {}
        for q in sorted_quarters:
            holders_q = quarters_data[q]
            all_holders_by_quarter[q] = holders_q
            total_shares = sum(h.get('shares', 0) for h in holders_q)
            num_holders = len(holders_q)

            quarterly_metrics.append({
                'quarter': q,
                'total_shares': total_shares,
                'num_holders': num_holders,
                'top_holders': sorted(
                    holders_q,
                    key=lambda x: x.get('shares', 0),
                    reverse=True
                )[:20],
            })

        # Data quality assessment for most recent quarter
        current_all = all_holders_by_quarter[sorted_quarters[0]]
        previous_all = all_holders_by_quarter[sorted_quarters[1]] if len(sorted_quarters) >= 2 else []
        filtered_metrics = calculate_filtered_metrics(current_all)
        total_holder_count = len(current_all)
        genuine_ratio = (
            filtered_metrics["genuine_count"] / total_holder_count
            if total_holder_count > 0 else 0
        )
        coverage_ratio = calculate_coverage_ratio(current_all, previous_all)
        match_ratio = calculate_match_ratio(current_all, previous_all)
        grade = reliability_grade(coverage_ratio, match_ratio, genuine_ratio)

        data_quality = {
            "grade": grade,
            "genuine_ratio": round(genuine_ratio, 4),
            "coverage_ratio": round(coverage_ratio, 2),
            "match_ratio": round(match_ratio, 4),
            "genuine_count": filtered_metrics["genuine_count"],
            "total_holders": total_holder_count,
        }

        # Calculate trends - only if both endpoints have reliable data
        most_recent = quarterly_metrics[0]
        oldest = quarterly_metrics[-1]

        # Check genuine_ratio for both endpoints
        oldest_all = all_holders_by_quarter[sorted_quarters[-1]]
        oldest_metrics = calculate_filtered_metrics(oldest_all)
        oldest_total = len(oldest_all)
        oldest_genuine_ratio = (
            oldest_metrics["genuine_count"] / oldest_total
            if oldest_total > 0 else 0
        )

        if genuine_ratio >= 0.7 and oldest_genuine_ratio >= 0.7:
            shares_trend = (
                (most_recent['total_shares'] - oldest['total_shares'])
                / oldest['total_shares'] * 100
            ) if oldest['total_shares'] > 0 else 0
        else:
            shares_trend = None

        holders_trend = most_recent['num_holders'] - oldest['num_holders']

        # Analyze position changes using classify_holder (all holders, not top 20)
        new_positions = []
        increased_positions = []
        decreased_positions = []

        if len(quarterly_metrics) >= 2:
            for holder in current_all:
                classification = classify_holder(holder)
                name = holder.get('holder', '')
                shares = holder.get('shares', 0)
                change = holder.get('change', 0)

                if classification == "new_full":
                    new_positions.append({
                        'name': name,
                        'shares': shares,
                    })
                elif classification == "genuine":
                    if change > 0:
                        previous_shares = shares - change
                        pct_change = (
                            (change / previous_shares * 100)
                            if previous_shares > 0 else 0
                        )
                        increased_positions.append({
                            'name': name,
                            'current_shares': shares,
                            'change': change,
                            'pct_change': pct_change,
                        })
                    elif change < 0:
                        previous_shares = shares - change
                        pct_change = (
                            (change / previous_shares * 100)
                            if previous_shares > 0 else 0
                        )
                        decreased_positions.append({
                            'name': name,
                            'current_shares': shares,
                            'change': change,
                            'pct_change': pct_change,
                        })

            # Sort by magnitude
            increased_positions.sort(key=lambda x: x['change'], reverse=True)
            decreased_positions.sort(key=lambda x: x['change'])

        return {
            'symbol': symbol,
            'company_name': company_name,
            'sector': sector,
            'market_cap': market_cap,
            'quarterly_metrics': quarterly_metrics,
            'shares_trend': shares_trend,
            'holders_trend': holders_trend,
            'new_positions': new_positions,
            'increased_positions': increased_positions,
            'decreased_positions': decreased_positions,
            'data_quality': data_quality,
        }

    def generate_report(self, analysis: Dict, output_file: Optional[str] = None,
                        output_dir: Optional[str] = None):
        """Generate detailed markdown report"""

        if not analysis:
            print("No analysis data available")
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        symbol = analysis['symbol']
        data_quality = analysis.get('data_quality', {})
        grade = data_quality.get('grade', 'N/A')

        report = f"""# Institutional Ownership Analysis: {symbol}

**Company:** {analysis['company_name']}
**Sector:** {analysis['sector']}
**Market Cap:** ${analysis['market_cap']:,}
**Analysis Date:** {timestamp}
**Data Reliability:** Grade {grade}

"""

        # Data quality warning
        if grade == "C":
            report += """**WARNING: UNRELIABLE DATA**
This stock has highly asymmetric holder data across quarters (genuine ratio < 30%).
Metrics below may be misleading. Do NOT use for investment decisions.

"""
        elif grade == "B":
            report += """**CAUTION: Reference Only**
This stock has moderate data quality (genuine ratio 30-70%).
Use metrics as reference only, with additional verification.

"""

        report += "## Executive Summary\n\n"

        # Determine overall signal
        shares_trend = analysis['shares_trend']
        holders_trend = analysis['holders_trend']

        if shares_trend is None:
            signal = "**DATA QUALITY INSUFFICIENT**"
            interpretation = (
                "Shares trend cannot be reliably calculated due to low genuine holder ratio "
                "in one or both endpoint quarters."
            )
            trend_str = "N/A (insufficient data quality)"
        else:
            if shares_trend > 15 and holders_trend > 5:
                signal = "**STRONG ACCUMULATION**"
                interpretation = "Strong institutional buying with increasing participation. Positive signal."
            elif shares_trend > 7 and holders_trend > 0:
                signal = "**MODERATE ACCUMULATION**"
                interpretation = "Steady institutional buying. Moderately positive signal."
            elif shares_trend < -15 or holders_trend < -5:
                signal = "**STRONG DISTRIBUTION**"
                interpretation = "Significant institutional selling. Warning sign - investigate further."
            elif shares_trend < -7:
                signal = "**MODERATE DISTRIBUTION**"
                interpretation = "Institutional selling detected. Monitor closely."
            else:
                signal = "**NEUTRAL**"
                interpretation = "No significant institutional flow changes. Stable ownership."
            trend_str = f"{shares_trend:+.2f}%"

        report += f"""**Signal:** {signal}

**Interpretation:** {interpretation}

**Trend ({len(analysis['quarterly_metrics'])} Quarters):**
- Institutional Shares: {trend_str}
- Number of Institutions: {holders_trend:+d}

## Data Quality Assessment

| Metric | Value |
|--------|-------|
| Reliability Grade | **{grade}** |
| Genuine Holder Ratio | {data_quality.get('genuine_ratio', 0):.1%} |
| Coverage Ratio (Current/Previous) | {data_quality.get('coverage_ratio', 0):.1f}x |
| Name Match Ratio | {data_quality.get('match_ratio', 0):.1%} |
| Genuine Holders | {data_quality.get('genuine_count', 0)} / {data_quality.get('total_holders', 0)} |

## Historical Institutional Ownership Trend

| Quarter | Total Shares Held | Number of Institutions | QoQ Change |
|---------|-------------------|----------------------|------------|
"""

        # Add quarterly data
        metrics = analysis['quarterly_metrics']
        for i, q in enumerate(metrics):
            if i < len(metrics) - 1:
                prev_shares = metrics[i+1]['total_shares']
                qoq_change = ((q['total_shares'] - prev_shares) / prev_shares * 100) if prev_shares > 0 else 0
                qoq_str = f"{qoq_change:+.2f}%"
            else:
                qoq_str = "N/A"

            report += f"| {q['quarter']} | {q['total_shares']:,} | {q['num_holders']} | {qoq_str} |\n"

        # Recent changes
        report += f"""
## Recent Quarter Changes ({metrics[0]['quarter']} vs {metrics[1]['quarter']})

### New Positions (Institutions that newly initiated)

"""
        if analysis['new_positions']:
            report += "| Institution | Shares Acquired |\n"
            report += "|-------------|----------------|\n"
            for pos in analysis['new_positions'][:10]:
                report += f"| {pos['name']} | {pos['shares']:,} |\n"
            if len(analysis['new_positions']) > 10:
                report += f"\n*...and {len(analysis['new_positions']) - 10} more new positions*\n"
        else:
            report += "No new institutional positions detected.\n"

        report += "\n### Increased Positions (Top 10)\n\n"
        if analysis['increased_positions']:
            report += "| Institution | Current Shares | Change | % Change |\n"
            report += "|-------------|----------------|--------|----------|\n"
            for pos in analysis['increased_positions'][:10]:
                report += f"| {pos['name']} | {pos['current_shares']:,} | {pos['change']:+,} | {pos['pct_change']:+.2f}% |\n"
        else:
            report += "No significant position increases detected.\n"

        report += "\n### Decreased Positions (Top 10)\n\n"
        if analysis['decreased_positions']:
            report += "| Institution | Current Shares | Change | % Change |\n"
            report += "|-------------|----------------|--------|----------|\n"
            for pos in analysis['decreased_positions'][:10]:
                report += f"| {pos['name']} | {pos['current_shares']:,} | {pos['change']:,} | {pos['pct_change']:.2f}% |\n"
        else:
            report += "No significant position decreases detected.\n"

        # Top current holders
        report += f"\n## Top 20 Current Institutional Holders ({metrics[0]['quarter']})\n\n"
        report += "| Rank | Institution | Shares Held | % of Institutional | Latest Change |\n"
        report += "|------|-------------|-------------|-------------------|---------------|\n"

        total_inst_shares = metrics[0]['total_shares']
        for i, holder in enumerate(metrics[0]['top_holders'], 1):
            shares = holder.get('shares', 0)
            pct_of_inst = (shares / total_inst_shares * 100) if total_inst_shares > 0 else 0
            change = holder.get('change', 0)
            report += f"| {i} | {holder.get('holder', 'Unknown')} | {shares:,} | {pct_of_inst:.2f}% | {change:+,} |\n"

        # Concentration analysis
        if len(metrics[0]['top_holders']) >= 10:
            top_10_shares = sum(h.get('shares', 0) for h in metrics[0]['top_holders'][:10])
            concentration = (top_10_shares / total_inst_shares * 100) if total_inst_shares > 0 else 0

            report += f"""
## Concentration Analysis

**Top 10 Holders Concentration:** {concentration:.2f}%

**Interpretation:**
"""
            if concentration > 60:
                report += "- **High Concentration** - Top 10 institutions control majority of institutional ownership\n"
                report += "- **Risk:** Significant price impact if top holders sell\n"
                report += "- **Opportunity:** May indicate high conviction by quality investors\n"
            elif concentration > 40:
                report += "- **Moderate Concentration** - Balanced institutional ownership\n"
                report += "- **Risk:** Moderate concentration risk\n"
            else:
                report += "- **Low Concentration** - Widely distributed institutional ownership\n"
                report += "- **Risk:** Lower concentration risk, more stable ownership\n"

        report += """
## Methodology Note

This analysis uses holder classification to filter unreliable data:
- **Genuine holders:** Institutions present in both current and prior quarters (change != shares, i.e., partial position change)
- **New-full entries:** Institutions appearing for the first time (change == shares)
- **Exited holders:** Institutions that fully sold their position (shares == 0)

Only genuine holders are used for percent-change calculations to prevent
inflated metrics from asymmetric holder counts across quarters.

## Interpretation Guide

**For detailed interpretation framework, see:**
`institutional-flow-tracker/references/interpretation_framework.md`

**Next Steps:**
1. Validate institutional signal with fundamental analysis
2. Check technical setup for entry timing
3. Review sector-wide institutional trends
4. Monitor quarterly for trend continuation/reversal

---

**Data Source:** FMP API (13F SEC Filings)
**Data Lag:** ~45 days after quarter end
**Note:** Use as confirming indicator alongside fundamental and technical analysis
"""

        # Determine output path
        if output_file:
            output_path = output_file if output_file.endswith('.md') else f"{output_file}.md"
        else:
            filename = f"institutional_analysis_{symbol}_{datetime.now().strftime('%Y%m%d')}.md"
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
        description='Analyze institutional ownership for a specific stock',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic analysis
  python3 analyze_single_stock.py AAPL

  # Extended history (12 quarters)
  python3 analyze_single_stock.py MSFT --quarters 12

  # With custom output directory
  python3 analyze_single_stock.py TSLA --output-dir reports/
        """
    )

    parser.add_argument(
        'symbol',
        type=str,
        help='Stock ticker symbol to analyze'
    )
    parser.add_argument(
        '--api-key',
        type=str,
        default=os.getenv('FMP_API_KEY'),
        help='FMP API key (or set FMP_API_KEY environment variable)'
    )
    parser.add_argument(
        '--quarters',
        type=int,
        default=8,
        help='Number of quarters to analyze (default: 8, i.e., 2 years)'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Output file path for markdown report'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='reports/',
        help='Output directory for reports (default: reports/)'
    )
    parser.add_argument(
        '--compare-to',
        type=str,
        help='Compare to another stock (optional, future feature)'
    )

    args = parser.parse_args()

    # Validate API key
    if not args.api_key:
        print("Error: FMP API key required")
        print("Set FMP_API_KEY environment variable or pass --api-key argument")
        print("Get free API key at: https://financialmodelingprep.com/developer/docs")
        sys.exit(1)

    # Initialize analyzer
    analyzer = SingleStockAnalyzer(args.api_key)

    # Run analysis
    analysis = analyzer.analyze_stock(args.symbol.upper(), quarters=args.quarters)

    if not analysis:
        print(f"Unable to complete analysis for {args.symbol}")
        sys.exit(1)

    # Generate report
    analyzer.generate_report(analysis, output_file=args.output, output_dir=args.output_dir)

    # Print summary
    dq = analysis.get('data_quality', {})
    trend = analysis['shares_trend']
    trend_str = f"{trend:+.2f}%" if trend is not None else "N/A"

    print("\n" + "="*80)
    print(f"INSTITUTIONAL OWNERSHIP SUMMARY: {args.symbol}")
    print("="*80)
    print(f"Data Reliability: Grade {dq.get('grade', 'N/A')} "
          f"(genuine ratio: {dq.get('genuine_ratio', 0):.1%})")
    print(f"Trend ({args.quarters} quarters): {trend_str} shares, "
          f"{analysis['holders_trend']:+d} institutions")
    print(f"Recent Activity:")
    print(f"  - New Positions: {len(analysis['new_positions'])}")
    print(f"  - Increased: {len(analysis['increased_positions'])}")
    print(f"  - Decreased: {len(analysis['decreased_positions'])}")


if __name__ == '__main__':
    main()
