#!/usr/bin/env python3
"""
Institutional Flow Tracker - Main Screening Script

Screens for stocks with significant institutional ownership changes by reading
FMP's aggregate 13F summary (institutional-ownership/symbol-positions-summary).
Identifies stocks where smart money is accumulating or distributing.

Reliability is graded from FMP's coverage signals (holder breadth + whether a
comparable prior quarter exists) via data_quality.coverage_grade.

Usage:
    python3 track_institutional_flow.py --limit 100 --min-change-percent 10
    python3 track_institutional_flow.py --sector Technology --min-institutions 20
    python3 track_institutional_flow.py --api-key YOUR_KEY --output results.json

Requirements:
    - FMP API key (set FMP_API_KEY environment variable or pass --api-key)
    - ~2 API calls per analyzed stock (summary + top holders), plus a one-time
      quarter probe. Free tier (250 req/day) covers roughly 100 stocks/day.
"""

import argparse
import datetime
import json
import os
import sys
import time
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
    deduplicate_share_classes,
    is_tradable_stock,
    iter_quarters,
    normalize_holder,
    quarter_end_date,
)

STABLE_URL = "https://financialmodelingprep.com/stable"


class InstitutionalFlowTracker:
    """Track institutional ownership changes across stocks"""

    def __init__(self, api_key: str, as_of: Optional[datetime.date] = None):
        self.api_key = api_key
        self.base_url = STABLE_URL
        self._as_of = as_of or datetime.date.today()
        # Cache of the most recent quarter that has filed 13F data, so we don't
        # re-probe the lag window for every symbol.
        self._latest_yq: Optional[tuple[int, int]] = None

    def _get(self, path: str, **params) -> Optional[object]:
        """GET a /stable endpoint, returning parsed JSON or None.

        The API key is sent via header (not query string) so it never appears
        in a URL — including any URL embedded in a raised exception message.
        """
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
            print(f"Error fetching {path}: {e}", file=sys.stderr)
            return None

    def get_company_screener(
        self, market_cap_min: int = 1000000000, limit: int = 100
    ) -> list[dict]:
        """Get list of stocks meeting market cap criteria (/stable company-screener)."""
        data = self._get("company-screener", marketCapMoreThan=market_cap_min, limit=limit)
        return data if isinstance(data, list) else []

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

        13F data lags the quarter end by ~45 days, so the current calendar
        quarter is usually not yet filed. Probe backward until a quarter with
        data is found, caching the result for subsequent symbols.
        """
        if self._latest_yq is not None:
            summary = self.get_ownership_summary(symbol, *self._latest_yq)
            if summary:
                return (*self._latest_yq, summary)

        y0, q0 = current_quarter(self._as_of)
        for year, quarter in iter_quarters(y0, q0, max_lookback):
            summary = self.get_ownership_summary(symbol, year, quarter)
            if summary:
                self._latest_yq = (year, quarter)
                return (year, quarter, summary)
        return (None, None, None)

    def get_top_holders(self, symbol: str, year: int, quarter: int, limit: int = 10) -> list[dict]:
        """Get the top institutional holders (by market value) for a quarter.

        Reads page 0 of extract-analytics/holder, which the feed returns sorted
        by position size. Returns compact {name, shares, change, ...} records.
        """
        rows = self._get(
            "institutional-ownership/extract-analytics/holder",
            symbol=symbol,
            year=year,
            quarter=quarter,
            page=0,
        )
        if not isinstance(rows, list):
            return []
        return [normalize_holder(r) for r in rows[:limit]]

    def calculate_ownership_metrics(
        self, symbol: str, company_name: str, market_cap: float
    ) -> Optional[dict]:
        """Calculate institutional ownership metrics for a stock.

        Reads FMP's aggregate summary (deltas reconciled server-side). Returns
        None for stocks graded C (no comparable prior quarter or breadth too
        thin to rank).
        """
        year, quarter, summary = self.latest_summary(symbol)
        if not summary:
            return None

        investors = summary.get("investorsHolding", 0) or 0
        last_investors = summary.get("lastInvestorsHolding", 0) or 0
        grade = coverage_grade(investors, last_investors)

        # Skip stocks with insufficient coverage (grade C)
        if grade == "C":
            return None

        current_shares = summary.get("numberOf13Fshares", 0) or 0
        previous_shares = summary.get("lastNumberOf13Fshares", 0) or 0
        shares_change = summary.get("numberOf13FsharesChange")
        if shares_change is None:
            shares_change = current_shares - previous_shares
        pct_change = (shares_change / previous_shares * 100) if previous_shares > 0 else 0.0

        increased = summary.get("increasedPositions", 0) or 0
        reduced = summary.get("reducedPositions", 0) or 0
        new_positions = summary.get("newPositions", 0) or 0
        closed_positions = summary.get("closedPositions", 0) or 0
        unchanged = max(0, investors - increased - reduced - new_positions)

        institution_change = summary.get("investorsHoldingChange")
        if institution_change is None:
            institution_change = investors - last_investors

        prev_year, prev_quarter = list(iter_quarters(year, quarter, 2))[1]
        top_holders = self.get_top_holders(symbol, year, quarter, limit=10)

        return {
            "symbol": symbol,
            "company_name": company_name,
            "market_cap": market_cap,
            "current_quarter": summary.get("date") or quarter_end_date(year, quarter),
            "previous_quarter": quarter_end_date(prev_year, prev_quarter),
            "current_total_shares": current_shares,
            "previous_total_shares": previous_shares,
            "shares_change": shares_change,
            "percent_change": round(pct_change, 2),
            "current_institution_count": investors,
            "previous_institution_count": last_investors,
            "institution_count_change": institution_change,
            "buyers": increased,
            "sellers": reduced,
            "unchanged": unchanged,
            "new_positions": new_positions,
            "closed_positions": closed_positions,
            "ownership_percent": round(summary.get("ownershipPercent", 0) or 0, 2),
            "ownership_percent_change": round(summary.get("ownershipPercentChange", 0) or 0, 2),
            "top_holders": top_holders,
            "reliability_grade": grade,
        }

    def screen_stocks(
        self,
        min_market_cap: int = 1000000000,
        min_change_percent: float = 10.0,
        min_institutions: int = 10,
        sector: Optional[str] = None,
        top: int = 50,
        sort_by: str = "ownership_change",
        limit: int = 100,
    ) -> list[dict]:
        """Screen for stocks with significant institutional changes"""

        print(f"Fetching stocks with market cap >= ${min_market_cap:,}...")
        stocks = self.get_company_screener(market_cap_min=min_market_cap, limit=limit)

        if not stocks:
            print("No stocks found in screener")
            return []

        # Filter by sector if specified
        if sector:
            stocks = [s for s in stocks if s.get("sector", "").lower() == sector.lower()]
            print(f"Filtered to {len(stocks)} stocks in {sector} sector")

        # Filter out ETFs and non-tradable stocks early (saves API calls)
        tradable_stocks = []
        for s in stocks:
            profile = {
                "symbol": s.get("symbol", ""),
                "companyName": s.get("companyName", ""),
                "isEtf": s.get("isEtf", False),
                "isFund": s.get("isFund", False),
                "isActivelyTrading": s.get("isActivelyTrading", True),
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
            symbol = stock.get("symbol", "")
            company_name = stock.get("companyName", "")
            market_cap = stock.get("marketCap", 0)

            if i % 10 == 0:
                print(f"Progress: {i}/{len(stocks)} stocks analyzed...")

            # Rate limiting: max 5 requests per second
            time.sleep(0.2)

            metrics = self.calculate_ownership_metrics(symbol, company_name, market_cap)

            if metrics:
                # Apply filters
                if abs(metrics["percent_change"]) >= min_change_percent:
                    if metrics["current_institution_count"] >= min_institutions:
                        results.append(metrics)

        # Deduplicate share classes (BRK-A/B, GOOG/GOOGL, etc.)
        results = deduplicate_share_classes(results)

        print(f"\nFound {len(results)} stocks meeting criteria")

        # Sort results
        if sort_by == "ownership_change":
            results.sort(key=lambda x: abs(x["percent_change"]), reverse=True)
        elif sort_by == "institution_count_change":
            results.sort(key=lambda x: abs(x["institution_count_change"]), reverse=True)

        return results[:top]

    def generate_report(self, results: list[dict], output_file: str = None, output_dir: str = None):
        """Generate markdown report from screening results"""

        if not results:
            print("No results to report")
            return

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        report = f"""# Institutional Flow Analysis Report
**Generated:** {timestamp}
**Stocks Analyzed:** {len(results)}

## Summary

This report identifies stocks with significant institutional ownership changes based on FMP's
aggregate 13F summary data. Only stocks with **Grade A or B** coverage are included; Grade C
(no comparable prior quarter, or too few 13F holders to rank) is excluded.

### Key Findings

**Top Accumulators (Institutions Buying):**
"""

        # Top accumulators
        accumulators = [r for r in results if r["percent_change"] > 0][:10]
        if accumulators:
            report += "\n| Symbol | Company | Ownership Change | Grade | Institution Change | Top Holder |\n"
            report += (
                "|--------|---------|-----------------|-------|-------------------|------------|\n"
            )
            for r in accumulators:
                top_holder = r["top_holders"][0]["name"] if r["top_holders"] else "N/A"
                report += (
                    f"| {r['symbol']} | {r['company_name'][:30]} "
                    f"| **+{r['percent_change']}%** | {r['reliability_grade']} "
                    f"| +{r['institution_count_change']} | {top_holder[:30]} |\n"
                )
        else:
            report += "\nNo significant accumulation detected.\n"

        report += "\n**Top Distributors (Institutions Selling):**\n"

        # Top distributors
        distributors = [r for r in results if r["percent_change"] < 0][:10]
        if distributors:
            report += "\n| Symbol | Company | Ownership Change | Grade | Institution Change | Previously Top Holder |\n"
            report += "|--------|---------|-----------------|-------|-------------------|-----------------------|\n"
            for r in distributors:
                top_holder = r["top_holders"][0]["name"] if r["top_holders"] else "N/A"
                report += (
                    f"| {r['symbol']} | {r['company_name'][:30]} "
                    f"| **{r['percent_change']}%** | {r['reliability_grade']} "
                    f"| {r['institution_count_change']} | {top_holder[:30]} |\n"
                )
        else:
            report += "\nNo significant distribution detected.\n"

        report += "\n## Detailed Results\n\n"

        for r in results[:20]:  # Top 20 detailed
            direction = "Accumulation" if r["percent_change"] > 0 else "Distribution"
            grade_label = f"Grade {r['reliability_grade']}"
            if r["reliability_grade"] == "B":
                grade_label += " (Reference Only)"

            report += f"""### {r["symbol"]} - {r["company_name"]}

**Signal:** {direction} ({r["percent_change"]:+.2f}% institutional ownership change)
**Data Reliability:** {grade_label} (institutional ownership: {r["ownership_percent"]:.1f}%)

**Metrics:**
- Market Cap: ${r["market_cap"]:,.0f}
- Current Quarter: {r["current_quarter"]}
- Institutions: {r["current_institution_count"]} (Increased: {r.get("buyers", "N/A")}, Reduced: {r.get("sellers", "N/A")}, New: {r.get("new_positions", "N/A")}, Closed: {r.get("closed_positions", "N/A")})
- Net Shares Change: {r["shares_change"]:+,.0f}
- Previous Total 13F Shares: {r["previous_total_shares"]:,.0f}

**Top 5 Current Holders:**
"""
            for i, holder in enumerate(r["top_holders"][:5], 1):
                report += f"{i}. {holder['name']}: {holder['shares']:,} shares (Change: {holder['change']:+,})\n"

            report += "\n---\n\n"

        report += """
## Methodology

### Data Source

Metrics come from FMP's aggregate 13F summary
(`institutional-ownership/symbol-positions-summary`), which reconciles
quarter-over-quarter deltas across all filing managers at source:

- **Net shares change / % change:** `numberOf13FsharesChange` vs prior quarter
- **Breadth:** number of 13F holders (`investorsHolding`) and its change
- **Buyers / Sellers / New / Closed:** managers that increased, reduced, newly
  opened, or closed positions

### Reliability Grades (coverage-based)

- **Grade A:** prior quarter present and >= 50 institutional holders -> dense, rankable
- **Grade B:** prior quarter present and >= 10 holders -> usable, reference only
- **Grade C:** no comparable prior quarter, or < 10 holders -> EXCLUDED

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

**Data Source:** Financial Modeling Prep API (13F Filings, /stable)
**Note:** 13F data has ~45-day reporting lag. Use as confirming indicator, not real-time signal.
"""

        # Determine output path
        if output_file:
            output_path = output_file if output_file.endswith(".md") else f"{output_file}.md"
        else:
            filename = (
                f"institutional_flow_screening_{datetime.datetime.now().strftime('%Y%m%d')}.md"
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
        description="Track institutional ownership changes across stocks",
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
        """,
    )

    parser.add_argument(
        "--api-key",
        type=str,
        default=os.getenv("FMP_API_KEY"),
        help="FMP API key (or set FMP_API_KEY environment variable)",
    )
    parser.add_argument(
        "--top", type=int, default=50, help="Number of top stocks to return (default: 50)"
    )
    parser.add_argument(
        "--min-change-percent",
        type=float,
        default=10.0,
        help="Minimum %% change in institutional ownership (default: 10.0)",
    )
    parser.add_argument(
        "--min-market-cap",
        type=int,
        default=1000000000,
        help="Minimum market cap in dollars (default: 1B)",
    )
    parser.add_argument(
        "--sector", type=str, help="Filter by specific sector (e.g., Technology, Healthcare)"
    )
    parser.add_argument(
        "--min-institutions",
        type=int,
        default=10,
        help="Minimum number of institutional holders (default: 10)",
    )
    parser.add_argument(
        "--sort-by",
        type=str,
        choices=["ownership_change", "institution_count_change"],
        default="ownership_change",
        help="Sort results by metric (default: ownership_change)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Number of stocks to fetch from screener (default: 100). "
        "Lower values save API calls for free tier.",
    )
    parser.add_argument("--output", type=str, help="Output file path for JSON results")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/",
        help="Output directory for reports (default: reports/)",
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
        json_output = args.output if args.output.endswith(".json") else f"{args.output}.json"
        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            json_output = os.path.join(args.output_dir, os.path.basename(json_output))
        with open(json_output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"JSON results saved to: {json_output}")

    # Generate markdown report
    tracker.generate_report(results, output_dir=args.output_dir)

    # Print summary
    if results:
        print("\n" + "=" * 80)
        print("TOP 10 INSTITUTIONAL FLOW CHANGES (Grade A/B only)")
        print("=" * 80)
        print(f"{'Symbol':<8} {'Company':<25} {'Change':>10} {'Grade':>6} {'Institutions':>12}")
        print("-" * 80)
        for r in results[:10]:
            print(
                f"{r['symbol']:<8} {r['company_name'][:25]:<25} "
                f"{r['percent_change']:>9.2f}% {r['reliability_grade']:>5} "
                f"{r['institution_count_change']:>+11d}"
            )


if __name__ == "__main__":
    main()
