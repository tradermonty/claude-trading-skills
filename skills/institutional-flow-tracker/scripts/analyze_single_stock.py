#!/usr/bin/env python3
"""
Institutional Flow Tracker - Single Stock Deep Dive

Provides detailed analysis of institutional ownership for a specific stock,
including the multi-quarter ownership trend, top holders, and the largest
holders' position changes.

Reads FMP's aggregate 13F summary (institutional-ownership/symbol-positions-summary)
for the quarter-over-quarter trend, and extract-analytics/holder for the named
top holders. Reliability is graded from FMP's coverage signals (holder breadth +
whether a comparable prior quarter exists) via data_quality.coverage_grade.

Usage:
    python3 analyze_single_stock.py AAPL
    python3 analyze_single_stock.py MSFT --quarters 12 --api-key YOUR_KEY
    python3 analyze_single_stock.py TSLA --output-dir reports/

Requirements:
    - FMP API key (set FMP_API_KEY environment variable or pass --api-key)
"""

import argparse
import datetime
import os
import sys
from typing import Optional

try:
    import requests
except ImportError:
    print("Error: 'requests' library not installed. Install with: pip install requests")
    sys.exit(1)

# Add scripts directory to path for data_quality import
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_quality import (
    coverage_grade,
    current_quarter,
    iter_quarters,
    normalize_holder,
    quarter_end_date,
)

STABLE_URL = "https://financialmodelingprep.com/stable"


class SingleStockAnalyzer:
    """Analyze institutional ownership for a single stock"""

    def __init__(self, api_key: str, as_of: Optional[datetime.date] = None):
        self.api_key = api_key
        self.base_url = STABLE_URL
        self._as_of = as_of or datetime.date.today()
        self._latest_yq: Optional[tuple[int, int]] = None

    def _get(self, path: str, **params) -> Optional[object]:
        """GET a /stable endpoint, returning parsed JSON or None.

        The API key is sent via header (not query string) so it never appears
        in a URL — including any URL embedded in a raised exception message.
        """
        symbol = params.get("symbol", "")
        try:
            response = requests.get(
                f"{self.base_url}/{path}",
                params=params,
                headers={"apikey": self.api_key},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {path} for {symbol}: {e}")
            return None

    def get_company_profile(self, symbol: str) -> dict:
        """Get company profile information (/stable profile)."""
        data = self._get("profile", symbol=symbol)
        profile = data[0] if isinstance(data, list) and data else {}
        # /stable returns marketCap; expose mktCap alias for legacy readers.
        if profile and "mktCap" not in profile and "marketCap" in profile:
            profile = {**profile, "mktCap": profile["marketCap"]}
        return profile

    def get_ownership_summary(self, symbol: str, year: int, quarter: int) -> Optional[dict]:
        """Get the aggregate 13F positions summary for one symbol/quarter."""
        data = self._get(
            "institutional-ownership/symbol-positions-summary",
            symbol=symbol,
            year=year,
            quarter=quarter,
        )
        if isinstance(data, list) and data:
            return data[0]
        return None

    def latest_summary(
        self, symbol: str, max_lookback: int = 5
    ) -> tuple[Optional[int], Optional[int], Optional[dict]]:
        """Return (year, quarter, summary) for the most recent filed quarter.

        13F data lags quarter end by ~45 days, so probe backward from the
        current calendar quarter until a quarter with data is found.
        """
        y0, q0 = current_quarter(self._as_of)
        for year, quarter in iter_quarters(y0, q0, max_lookback):
            summary = self.get_ownership_summary(symbol, year, quarter)
            if summary:
                self._latest_yq = (year, quarter)
                return (year, quarter, summary)
        return (None, None, None)

    def get_top_holders(self, symbol: str, year: int, quarter: int, limit: int = 20) -> list[dict]:
        """Get the top institutional holders (by market value) for a quarter.

        extract-analytics/holder returns 10 rows per page, sorted by position
        size. Pages forward (bounded) until ``limit`` holders are collected.
        """
        holders: list[dict] = []
        page = 0
        while len(holders) < limit and page < 5:
            rows = self._get(
                "institutional-ownership/extract-analytics/holder",
                symbol=symbol,
                year=year,
                quarter=quarter,
                page=page,
            )
            if not isinstance(rows, list) or not rows:
                break
            holders.extend(normalize_holder(r) for r in rows)
            if len(rows) < 10:
                break
            page += 1
        return holders[:limit]

    def analyze_stock(self, symbol: str, quarters: int = 8) -> dict:
        """Perform institutional ownership analysis on a stock.

        Builds the multi-quarter ownership trend from FMP's aggregate summary
        and the named top holders from extract-analytics/holder. Position-change
        lists reflect the largest holders (top of the holder list).
        """

        print(f"Analyzing institutional ownership for {symbol}...")

        # Get company profile
        profile = self.get_company_profile(symbol)
        company_name = profile.get("companyName", symbol)
        sector = profile.get("sector", "Unknown")
        market_cap = profile.get("marketCap", profile.get("mktCap", 0)) or 0

        print(f"Company: {company_name}")
        print(f"Sector: {sector}")
        print(f"Market Cap: ${market_cap:,}")

        # Find the most recent filed quarter, then walk back N quarters.
        year, quarter, latest = self.latest_summary(symbol)
        if not latest:
            print(f"No institutional ownership data available for {symbol}")
            return {}

        summaries = []
        for yy, qq in iter_quarters(year, quarter, quarters):
            summary = self.get_ownership_summary(symbol, yy, qq)
            if summary:
                summaries.append((yy, qq, summary))

        if len(summaries) < 2:
            print(f"Insufficient data (need at least 2 quarters, found {len(summaries)})")
            return {}

        # Named top holders for the most recent quarter only.
        top_year, top_quarter, current_summary = summaries[0]
        top_holders = self.get_top_holders(symbol, top_year, top_quarter, limit=20)

        # Build quarterly metrics (most recent first).
        quarterly_metrics = []
        for idx, (yy, qq, summary) in enumerate(summaries):
            quarterly_metrics.append(
                {
                    "quarter": summary.get("date") or quarter_end_date(yy, qq),
                    "total_shares": summary.get("numberOf13Fshares", 0) or 0,
                    "num_holders": summary.get("investorsHolding", 0) or 0,
                    "top_holders": top_holders if idx == 0 else [],
                }
            )

        # Reliability assessment for the most recent quarter.
        cur_investors = current_summary.get("investorsHolding", 0) or 0
        last_investors = current_summary.get("lastInvestorsHolding", 0) or 0
        grade = coverage_grade(cur_investors, last_investors)

        data_quality = {
            "grade": grade,
            "institution_count": cur_investors,
            "ownership_percent": round(current_summary.get("ownershipPercent", 0) or 0, 2),
            "ownership_percent_change": round(
                current_summary.get("ownershipPercentChange", 0) or 0, 2
            ),
            "prior_quarter_available": last_investors > 0,
            "increased": current_summary.get("increasedPositions", 0) or 0,
            "reduced": current_summary.get("reducedPositions", 0) or 0,
            "new": current_summary.get("newPositions", 0) or 0,
            "closed": current_summary.get("closedPositions", 0) or 0,
        }

        # Trends across the available quarters (oldest is the last entry).
        most_recent = quarterly_metrics[0]
        oldest = quarterly_metrics[-1]
        shares_trend = (
            (most_recent["total_shares"] - oldest["total_shares"]) / oldest["total_shares"] * 100
            if oldest["total_shares"] > 0
            else None
        )
        holders_trend = most_recent["num_holders"] - oldest["num_holders"]

        # Position changes from the largest holders (named, bounded to top holders).
        new_positions = []
        increased_positions = []
        decreased_positions = []
        for holder in top_holders:
            shares = holder["shares"]
            change = holder["change"]
            if holder["is_new"]:
                new_positions.append({"name": holder["name"], "shares": shares})
            elif change > 0:
                previous_shares = shares - change
                pct_change = (change / previous_shares * 100) if previous_shares > 0 else 0
                increased_positions.append(
                    {
                        "name": holder["name"],
                        "current_shares": shares,
                        "change": change,
                        "pct_change": pct_change,
                    }
                )
            elif change < 0:
                previous_shares = shares - change
                pct_change = (change / previous_shares * 100) if previous_shares > 0 else 0
                decreased_positions.append(
                    {
                        "name": holder["name"],
                        "current_shares": shares,
                        "change": change,
                        "pct_change": pct_change,
                    }
                )

        increased_positions.sort(key=lambda x: x["change"], reverse=True)
        decreased_positions.sort(key=lambda x: x["change"])

        return {
            "symbol": symbol,
            "company_name": company_name,
            "sector": sector,
            "market_cap": market_cap,
            "quarterly_metrics": quarterly_metrics,
            "shares_trend": shares_trend,
            "holders_trend": holders_trend,
            "new_positions": new_positions,
            "increased_positions": increased_positions,
            "decreased_positions": decreased_positions,
            "data_quality": data_quality,
        }

    def generate_report(
        self, analysis: dict, output_file: Optional[str] = None, output_dir: Optional[str] = None
    ):
        """Generate detailed markdown report"""

        if not analysis:
            print("No analysis data available")
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        symbol = analysis["symbol"]
        data_quality = analysis.get("data_quality", {})
        grade = data_quality.get("grade", "N/A")

        report = f"""# Institutional Ownership Analysis: {symbol}

**Company:** {analysis["company_name"]}
**Sector:** {analysis["sector"]}
**Market Cap:** ${analysis["market_cap"]:,}
**Analysis Date:** {timestamp}
**Data Reliability:** Grade {grade}

"""

        # Data quality warning
        if grade == "C":
            report += """**WARNING: INSUFFICIENT COVERAGE**
This stock has too few 13F holders (or no comparable prior quarter) to rank
reliably. Metrics below may be misleading. Do NOT use for investment decisions.

"""
        elif grade == "B":
            report += """**CAUTION: Reference Only**
This stock has thin institutional coverage (fewer than 50 13F holders).
Use metrics as reference only, with additional verification.

"""

        report += "## Executive Summary\n\n"

        # Determine overall signal
        shares_trend = analysis["shares_trend"]
        holders_trend = analysis["holders_trend"]

        if shares_trend is None:
            signal = "**DATA QUALITY INSUFFICIENT**"
            interpretation = (
                "Shares trend cannot be reliably calculated due to insufficient "
                "institutional coverage in the endpoint quarters."
            )
            trend_str = "N/A (insufficient data quality)"
        else:
            if shares_trend > 15 and holders_trend > 5:
                signal = "**STRONG ACCUMULATION**"
                interpretation = (
                    "Strong institutional buying with increasing participation. Positive signal."
                )
            elif shares_trend > 7 and holders_trend > 0:
                signal = "**MODERATE ACCUMULATION**"
                interpretation = "Steady institutional buying. Moderately positive signal."
            elif shares_trend < -15 or holders_trend < -5:
                signal = "**STRONG DISTRIBUTION**"
                interpretation = (
                    "Significant institutional selling. Warning sign - investigate further."
                )
            elif shares_trend < -7:
                signal = "**MODERATE DISTRIBUTION**"
                interpretation = "Institutional selling detected. Monitor closely."
            else:
                signal = "**NEUTRAL**"
                interpretation = "No significant institutional flow changes. Stable ownership."
            trend_str = f"{shares_trend:+.2f}%"

        report += f"""**Signal:** {signal}

**Interpretation:** {interpretation}

**Trend ({len(analysis["quarterly_metrics"])} Quarters):**
- Institutional Shares: {trend_str}
- Number of Institutions: {holders_trend:+d}

## Data Quality Assessment

| Metric | Value |
|--------|-------|
| Reliability Grade | **{grade}** |
| Institutional Holders (breadth) | {data_quality.get("institution_count", 0):,} |
| Institutional Ownership | {data_quality.get("ownership_percent", 0):.2f}% |
| Ownership Change (QoQ) | {data_quality.get("ownership_percent_change", 0):+.2f} pp |
| Prior Quarter Available | {"Yes" if data_quality.get("prior_quarter_available") else "No"} |
| Increased / Reduced / New / Closed | {data_quality.get("increased", 0)} / {data_quality.get("reduced", 0)} / {data_quality.get("new", 0)} / {data_quality.get("closed", 0)} |

## Historical Institutional Ownership Trend

| Quarter | Total Shares Held | Number of Institutions | QoQ Change |
|---------|-------------------|----------------------|------------|
"""

        # Add quarterly data
        metrics = analysis["quarterly_metrics"]
        for i, q in enumerate(metrics):
            if i < len(metrics) - 1:
                prev_shares = metrics[i + 1]["total_shares"]
                qoq_change = (
                    ((q["total_shares"] - prev_shares) / prev_shares * 100)
                    if prev_shares > 0
                    else 0
                )
                qoq_str = f"{qoq_change:+.2f}%"
            else:
                qoq_str = "N/A"

            report += (
                f"| {q['quarter']} | {q['total_shares']:,} | {q['num_holders']} | {qoq_str} |\n"
            )

        # Recent changes
        report += f"""
## Largest Holders' Changes ({metrics[0]["quarter"]})

> Position-change lists below reflect the **largest institutional holders**
> (top of the holder list), not every filer.

### New Positions (largest holders that newly initiated)

"""
        if analysis["new_positions"]:
            report += "| Institution | Shares Acquired |\n"
            report += "|-------------|----------------|\n"
            for pos in analysis["new_positions"][:10]:
                report += f"| {pos['name']} | {pos['shares']:,} |\n"
            if len(analysis["new_positions"]) > 10:
                report += f"\n*...and {len(analysis['new_positions']) - 10} more new positions*\n"
        else:
            report += "No new institutional positions among the largest holders.\n"

        report += "\n### Increased Positions (Top 10)\n\n"
        if analysis["increased_positions"]:
            report += "| Institution | Current Shares | Change | % Change |\n"
            report += "|-------------|----------------|--------|----------|\n"
            for pos in analysis["increased_positions"][:10]:
                report += f"| {pos['name']} | {pos['current_shares']:,} | {pos['change']:+,} | {pos['pct_change']:+.2f}% |\n"
        else:
            report += "No significant position increases among the largest holders.\n"

        report += "\n### Decreased Positions (Top 10)\n\n"
        if analysis["decreased_positions"]:
            report += "| Institution | Current Shares | Change | % Change |\n"
            report += "|-------------|----------------|--------|----------|\n"
            for pos in analysis["decreased_positions"][:10]:
                report += f"| {pos['name']} | {pos['current_shares']:,} | {pos['change']:,} | {pos['pct_change']:.2f}% |\n"
        else:
            report += "No significant position decreases among the largest holders.\n"

        # Top current holders
        report += f"\n## Top 20 Current Institutional Holders ({metrics[0]['quarter']})\n\n"
        report += "| Rank | Institution | Shares Held | % of Institutional | Latest Change |\n"
        report += "|------|-------------|-------------|-------------------|---------------|\n"

        total_inst_shares = metrics[0]["total_shares"]
        for i, holder in enumerate(metrics[0]["top_holders"], 1):
            shares = holder.get("shares", 0)
            pct_of_inst = (shares / total_inst_shares * 100) if total_inst_shares > 0 else 0
            change = holder.get("change", 0)
            report += f"| {i} | {holder.get('name', 'Unknown')} | {shares:,} | {pct_of_inst:.2f}% | {change:+,} |\n"

        # Concentration analysis
        if len(metrics[0]["top_holders"]) >= 10:
            top_10_shares = sum(h.get("shares", 0) for h in metrics[0]["top_holders"][:10])
            concentration = (
                (top_10_shares / total_inst_shares * 100) if total_inst_shares > 0 else 0
            )

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

This analysis reads FMP's aggregate 13F summary
(`institutional-ownership/symbol-positions-summary`), which reconciles
quarter-over-quarter deltas across all filing managers at source:

- **Ownership trend:** total 13F shares (`numberOf13Fshares`) and holder
  breadth (`investorsHolding`) per quarter
- **Flow counts:** managers that increased, reduced, newly opened, or closed
  positions

Named top holders and their position changes come from
`extract-analytics/holder` (sorted by position size), so the New / Increased /
Decreased lists reflect the **largest** holders rather than the full tail.

## Interpretation Guide

**For detailed interpretation framework, see:**
`institutional-flow-tracker/references/interpretation_framework.md`

**Next Steps:**
1. Validate institutional signal with fundamental analysis
2. Check technical setup for entry timing
3. Review sector-wide institutional trends
4. Monitor quarterly for trend continuation/reversal

---

**Data Source:** FMP API (13F SEC Filings, /stable)
**Data Lag:** ~45 days after quarter end
**Note:** Use as confirming indicator alongside fundamental and technical analysis
"""

        # Determine output path
        if output_file:
            output_path = output_file if output_file.endswith(".md") else f"{output_file}.md"
        else:
            filename = (
                f"institutional_analysis_{symbol}_{datetime.datetime.now().strftime('%Y%m%d')}.md"
            )
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, filename)
            else:
                output_path = filename

        with open(output_path, "w") as f:
            f.write(report)

        print(f"\nReport saved to: {output_path}")
        return report


def main():
    parser = argparse.ArgumentParser(
        description="Analyze institutional ownership for a specific stock",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic analysis
  python3 analyze_single_stock.py AAPL

  # Extended history (12 quarters)
  python3 analyze_single_stock.py MSFT --quarters 12

  # With custom output directory
  python3 analyze_single_stock.py TSLA --output-dir reports/
        """,
    )

    parser.add_argument("symbol", type=str, help="Stock ticker symbol to analyze")
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("FMP_API_KEY"),
        help="FMP API key (or set FMP_API_KEY environment variable)",
    )
    parser.add_argument(
        "--quarters",
        type=int,
        default=8,
        help="Number of quarters to analyze (default: 8, i.e., 2 years)",
    )
    parser.add_argument("--output", type=str, help="Output file path for markdown report")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/",
        help="Output directory for reports (default: reports/)",
    )
    parser.add_argument(
        "--compare-to", type=str, help="Compare to another stock (optional, future feature)"
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
    dq = analysis.get("data_quality", {})
    trend = analysis["shares_trend"]
    trend_str = f"{trend:+.2f}%" if trend is not None else "N/A"

    print("\n" + "=" * 80)
    print(f"INSTITUTIONAL OWNERSHIP SUMMARY: {args.symbol}")
    print("=" * 80)
    print(
        f"Data Reliability: Grade {dq.get('grade', 'N/A')} "
        f"({dq.get('institution_count', 0):,} holders, "
        f"{dq.get('ownership_percent', 0):.1f}% ownership)"
    )
    print(
        f"Trend ({args.quarters} quarters): {trend_str} shares, "
        f"{analysis['holders_trend']:+d} institutions"
    )
    print("Largest-Holder Activity:")
    print(f"  - New Positions: {len(analysis['new_positions'])}")
    print(f"  - Increased: {len(analysis['increased_positions'])}")
    print(f"  - Decreased: {len(analysis['decreased_positions'])}")


if __name__ == "__main__":
    main()
