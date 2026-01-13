#!/usr/bin/env python3
"""
CANSLIM Stock Screener - Phase 3 (Full CANSLIM)

Screens US stocks using William O'Neil's CANSLIM methodology.
Phase 3 implements all 7 components: C, A, N, S, L, I, M (100% coverage)

Usage:
    python3 screen_canslim.py --api-key YOUR_KEY --max-candidates 40
    python3 screen_canslim.py  # Uses FMP_API_KEY environment variable

Output:
    - JSON: canslim_screener_YYYY-MM-DD_HHMMSS.json
    - Markdown: canslim_screener_YYYY-MM-DD_HHMMSS.md
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Add calculators directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'calculators'))

from fmp_client import FMPClient
from calculators.earnings_calculator import calculate_quarterly_growth
from calculators.growth_calculator import calculate_annual_growth
from calculators.new_highs_calculator import calculate_newness
from calculators.supply_demand_calculator import calculate_supply_demand
from calculators.leadership_calculator import calculate_leadership
from calculators.institutional_calculator import calculate_institutional_sponsorship
from calculators.market_calculator import calculate_market_direction
from scorer import (
    calculate_composite_score, check_minimum_thresholds,
    calculate_composite_score_phase2, check_minimum_thresholds_phase2,
    calculate_composite_score_phase3, check_minimum_thresholds_phase3
)
from report_generator import generate_json_report, generate_markdown_report


# S&P 500 sample tickers (top 40 by market cap)
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B", "UNH", "JNJ",
    "XOM", "V", "PG", "JPM", "MA", "HD", "CVX", "MRK", "ABBV", "PEP",
    "COST", "AVGO", "KO", "ADBE", "LLY", "TMO", "WMT", "MCD", "CSCO", "ACN",
    "ORCL", "ABT", "NKE", "CRM", "DHR", "VZ", "TXN", "AMD", "QCOM", "INTC"
]


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="CANSLIM Stock Screener - Phase 1 MVP (C, A, N, M components)"
    )

    parser.add_argument(
        "--api-key",
        help="FMP API key (defaults to FMP_API_KEY environment variable)"
    )

    parser.add_argument(
        "--max-candidates",
        type=int,
        default=40,
        help="Maximum number of stocks to analyze (default: 40, stays within free tier)"
    )

    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of top stocks to include in report (default: 20)"
    )

    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for reports (default: current directory)"
    )

    parser.add_argument(
        "--universe",
        nargs="+",
        help="Custom list of stock symbols to screen (overrides default S&P 500)"
    )

    return parser.parse_args()


def analyze_stock(symbol: str, client: FMPClient, market_data: Dict, sp500_historical: List[Dict] = None) -> Optional[Dict]:
    """
    Analyze a single stock using CANSLIM Phase 3 components (7 components: C, A, N, S, L, I, M)

    Args:
        symbol: Stock ticker
        client: FMP API client
        market_data: Pre-calculated market direction data
        sp500_historical: S&P 500 historical prices for L component RS calculation

    Returns:
        Dict with analysis results, or None if analysis failed
    """
    print(f"  Analyzing {symbol}...", end=" ", flush=True)

    try:
        # Get company profile
        profile = client.get_profile(symbol)
        if not profile:
            print("✗ Profile unavailable")
            return None

        company_name = profile[0].get("companyName", symbol)
        sector = profile[0].get("sector", "Unknown")
        market_cap = profile[0].get("mktCap", 0)

        # Get quote
        quote = client.get_quote(symbol)
        if not quote:
            print("✗ Quote unavailable")
            return None

        price = quote[0].get("price", 0)

        # C Component: Current Quarterly Earnings
        quarterly_income = client.get_income_statement(symbol, period="quarter", limit=8)
        c_result = calculate_quarterly_growth(quarterly_income) if quarterly_income else {
            "score": 0, "error": "No quarterly data"
        }

        # A Component: Annual Growth
        annual_income = client.get_income_statement(symbol, period="annual", limit=5)
        a_result = calculate_annual_growth(annual_income) if annual_income else {
            "score": 50, "error": "No annual data"
        }

        # N Component: Newness / New Highs
        n_result = calculate_newness(quote[0])

        # S Component: Supply/Demand (uses existing historical_prices data - no extra API call)
        historical_prices = client.get_historical_prices(symbol, days=90)
        s_result = calculate_supply_demand(historical_prices) if historical_prices else {
            "score": 0, "error": "No price history data"
        }

        # L Component: Leadership / Relative Strength (52-week performance vs S&P 500)
        # Use 365-day historical data for full year comparison
        historical_prices_52w_data = client.get_historical_prices(symbol, days=365)
        # Extract 'historical' list from FMP response format
        historical_prices_52w = historical_prices_52w_data.get("historical", []) if historical_prices_52w_data else []
        # Prepare S&P 500 historical list (extract from FMP response format)
        sp500_historical_list = sp500_historical.get("historical", []) if sp500_historical else None
        l_result = calculate_leadership(
            historical_prices_52w,
            sp500_historical=sp500_historical_list
        ) if historical_prices_52w else {
            "score": 0, "error": "No 52-week price history"
        }

        # I Component: Institutional Sponsorship (with Finviz fallback)
        institutional_holders = client.get_institutional_holders(symbol)
        i_result = calculate_institutional_sponsorship(
            institutional_holders, profile[0], symbol=symbol, use_finviz_fallback=True
        ) if institutional_holders else {
            "score": 0, "error": "No institutional holder data"
        }

        # M Component: Market Direction (use pre-calculated)
        m_result = market_data

        # Calculate composite score (Phase 3: 7 components - FULL CANSLIM)
        composite = calculate_composite_score_phase3(
            c_score=c_result.get("score", 0),
            a_score=a_result.get("score", 50),
            n_score=n_result.get("score", 0),
            s_score=s_result.get("score", 0),
            l_score=l_result.get("score", 0),
            i_score=i_result.get("score", 0),
            m_score=m_result.get("score", 50)
        )

        # Check minimum thresholds (Phase 3)
        threshold_check = check_minimum_thresholds_phase3(
            c_score=c_result.get("score", 0),
            a_score=a_result.get("score", 50),
            n_score=n_result.get("score", 0),
            s_score=s_result.get("score", 0),
            l_score=l_result.get("score", 0),
            i_score=i_result.get("score", 0),
            m_score=m_result.get("score", 50)
        )

        print(f"✓ Score: {composite['composite_score']:.1f} ({composite['rating']})")

        return {
            "symbol": symbol,
            "company_name": company_name,
            "sector": sector,
            "price": price,
            "market_cap": market_cap,
            "composite_score": composite["composite_score"],
            "rating": composite["rating"],
            "rating_description": composite["rating_description"],
            "guidance": composite["guidance"],
            "weakest_component": composite["weakest_component"],
            "weakest_score": composite["weakest_score"],
            "c_component": c_result,
            "a_component": a_result,
            "n_component": n_result,
            "s_component": s_result,
            "l_component": l_result,  # NEW: Phase 3
            "i_component": i_result,
            "m_component": m_result,
            "threshold_check": threshold_check
        }

    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def main():
    """Main screening workflow"""
    args = parse_arguments()

    print("=" * 60)
    print("CANSLIM Stock Screener - Phase 3 (Full CANSLIM)")
    print("Components: C (Earnings), A (Growth), N (Newness), S (Supply/Demand), L (Leadership), I (Institutional), M (Market)")
    print("=" * 60)
    print()

    # Initialize FMP client
    try:
        client = FMPClient(api_key=args.api_key)
        print("✓ FMP API client initialized")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine universe
    if args.universe:
        universe = args.universe[:args.max_candidates]
        print(f"✓ Custom universe: {len(universe)} stocks")
    else:
        universe = DEFAULT_UNIVERSE[:args.max_candidates]
        print(f"✓ Default universe (S&P 500 top {len(universe)}): {len(universe)} stocks")

    print()

    # Step 1: Calculate market direction (M component) once for all stocks
    print("Step 1: Analyzing Market Direction (M Component)")
    print("-" * 60)

    sp500_quote = client.get_quote("^GSPC")
    vix_quote = client.get_quote("^VIX")

    if not sp500_quote:
        print("ERROR: Unable to fetch S&P 500 data", file=sys.stderr)
        sys.exit(1)

    market_data = calculate_market_direction(
        sp500_quote=sp500_quote[0],
        vix_quote=vix_quote[0] if vix_quote else None
    )

    print(f"S&P 500: ${market_data['sp500_price']:.2f}")
    print(f"Distance from 50-EMA: {market_data['distance_from_ema_pct']:+.2f}%")
    print(f"Trend: {market_data['trend']}")
    print(f"M Score: {market_data['score']}/100")
    print(f"Interpretation: {market_data['interpretation']}")

    if market_data.get('warning'):
        print()
        print(f"⚠️  WARNING: {market_data['warning']}")
        print("    Consider raising cash allocation. CANSLIM doesn't work in bear markets.")

    print()

    # Fetch S&P 500 historical prices for L component (Relative Strength calculation)
    print("Fetching S&P 500 52-week data for Leadership (L) component...")
    sp500_historical = client.get_historical_prices("SPY", days=365)  # Use SPY as S&P 500 proxy
    if sp500_historical and sp500_historical.get("historical"):
        sp500_days = len(sp500_historical.get("historical", []))
        print(f"✓ S&P 500 historical data: {sp500_days} days")
    else:
        print("⚠️  S&P 500 historical data unavailable - L component will use absolute performance")
    print()

    # Step 2: Progressive filtering and analysis
    print(f"Step 2: Analyzing {len(universe)} Stocks")
    print("-" * 60)

    results = []
    for symbol in universe:
        analysis = analyze_stock(symbol, client, market_data, sp500_historical)
        if analysis:
            results.append(analysis)

    print()
    print(f"✓ Successfully analyzed {len(results)} stocks")
    print()

    # Step 3: Rank by composite score
    print("Step 3: Ranking Results")
    print("-" * 60)

    results.sort(key=lambda x: x['composite_score'], reverse=True)

    # Display top 5
    print("Top 5 Stocks:")
    for i, stock in enumerate(results[:5], 1):
        print(f"  {i}. {stock['symbol']:6} - {stock['composite_score']:5.1f} ({stock['rating']})")

    print()

    # Step 4: Generate reports
    print("Step 4: Generating Reports")
    print("-" * 60)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_file = os.path.join(args.output_dir, f"canslim_screener_{timestamp}.json")
    md_file = os.path.join(args.output_dir, f"canslim_screener_{timestamp}.md")

    metadata = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "phase": "3 (7 components - FULL CANSLIM)",
        "components_included": ["C", "A", "N", "S", "L", "I", "M"],
        "candidates_analyzed": len(results),
        "universe_size": len(universe),
        "market_condition": {
            "trend": market_data['trend'],
            "M_score": market_data['score'],
            "warning": market_data.get('warning')
        }
    }

    # Limit to top N for report
    top_results = results[:args.top]

    generate_json_report(top_results, metadata, json_file)
    generate_markdown_report(top_results, metadata, md_file)

    print()
    print("=" * 60)
    print("✓ CANSLIM Screening Complete")
    print("=" * 60)
    print(f"  JSON Report: {json_file}")
    print(f"  Markdown Report: {md_file}")
    print()

    # API stats
    api_stats = client.get_api_stats()
    print(f"API Usage:")
    print(f"  Cache entries: {api_stats['cache_entries']}")
    print(f"  Estimated calls: ~{len(universe) * 6 + 4} (market data + S&P 500 history + {len(universe)} stocks × 6 API calls)")
    print(f"  Phase 3 includes all 7 CANSLIM components (C, A, N, S, L, I, M)")
    print()


if __name__ == "__main__":
    main()
