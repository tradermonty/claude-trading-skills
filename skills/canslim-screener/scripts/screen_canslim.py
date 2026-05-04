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
from typing import Optional

# Add calculators directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "calculators"))

from calculators.earnings_calculator import calculate_quarterly_growth
from calculators.growth_calculator import calculate_annual_growth
from calculators.institutional_calculator import calculate_institutional_sponsorship
from calculators.leadership_calculator import calculate_leadership
from calculators.market_calculator import calculate_market_direction
from calculators.new_highs_calculator import calculate_newness
from calculators.supply_demand_calculator import calculate_supply_demand
from fmp_client import FMPClient
from report_generator import generate_json_report, generate_markdown_report
from scorer import (
    calculate_composite_score_phase3,
    check_minimum_thresholds_phase3,
)

# S&P 500 sample tickers (top 40 by market cap)
DEFAULT_UNIVERSE = [
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "NVDA",
    "META",
    "TSLA",
    "BRK.B",
    "UNH",
    "JNJ",
    "XOM",
    "V",
    "PG",
    "JPM",
    "MA",
    "HD",
    "CVX",
    "MRK",
    "ABBV",
    "PEP",
    "COST",
    "AVGO",
    "KO",
    "ADBE",
    "LLY",
    "TMO",
    "WMT",
    "MCD",
    "CSCO",
    "ACN",
    "ORCL",
    "ABT",
    "NKE",
    "CRM",
    "DHR",
    "VZ",
    "TXN",
    "AMD",
    "QCOM",
    "INTC",
]


def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="CANSLIM Stock Screener - Phase 3 (Full CANSLIM: C, A, N, S, L, I, M)"
    )

    parser.add_argument(
        "--api-key", help="FMP API key (defaults to FMP_API_KEY environment variable)"
    )

    parser.add_argument(
        "--max-candidates",
        type=int,
        default=40,
        help="Maximum number of stocks to analyze (default: 40; use 35 for free tier's 250 calls/day limit)",
    )

    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Number of top stocks to include in report (default: 20)",
    )

    parser.add_argument(
        "--output-dir",
        default=".",
        help="Output directory for reports (default: current directory)",
    )

    parser.add_argument(
        "--universe",
        nargs="+",
        help="Custom list of stock symbols to screen (overrides default S&P 500)",
    )

    parser.add_argument(
        "--rs-benchmark",
        default="^GSPC",
        help=(
            "Benchmark symbol for L-component Relative Strength (default: ^GSPC). "
            "Examples: SPY, QQQ, IWM. The M component continues to use ^GSPC for "
            "EMA scale consistency regardless of this flag."
        ),
    )

    parser.add_argument(
        "--disable-rs",
        action="store_true",
        help=(
            "Skip L component calculation (saves the per-stock 365-day price fetch; "
            "also skips the custom RS benchmark fetch when applicable). "
            "L score is set to neutral 50."
        ),
    )

    return parser.parse_args()


def analyze_stock(
    symbol: str,
    client: FMPClient,
    market_data: dict,
    rs_benchmark_historical: Optional[dict] = None,
    rs_benchmark: str = "^GSPC",
    disable_rs: bool = False,
) -> Optional[dict]:
    """
    Analyze a single stock using CANSLIM Phase 3 components (7 components: C, A, N, S, L, I, M)

    Args:
        symbol: Stock ticker
        client: FMP API client
        market_data: Pre-calculated market direction data
        rs_benchmark_historical: RS benchmark historical prices (FMP response shape) for the
                                 L component's relative-strength calculation. May be None when
                                 the benchmark fetch failed; the L calculator falls back to
                                 absolute performance with a 20% penalty in that case.
        rs_benchmark: Benchmark symbol surfaced into the L component output (e.g. "^GSPC", "SPY").
        disable_rs: When True, skip the per-stock 365-day fetch and emit a neutral L=50 result.

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
        c_result = (
            calculate_quarterly_growth(quarterly_income)
            if quarterly_income
            else {"score": 0, "error": "No quarterly data"}
        )

        # A Component: Annual Growth
        annual_income = client.get_income_statement(symbol, period="annual", limit=5)
        a_result = (
            calculate_annual_growth(annual_income)
            if annual_income
            else {"score": 50, "error": "No annual data"}
        )

        # N Component: Newness / New Highs
        n_result = calculate_newness(quote[0])

        # S Component: Supply/Demand (uses existing historical_prices data - no extra API call)
        historical_prices = client.get_historical_prices(symbol, days=90)
        s_result = (
            calculate_supply_demand(historical_prices)
            if historical_prices
            else {"score": 0, "error": "No price history data"}
        )

        # L Component: Leadership / Relative Strength
        # When --disable-rs is set, skip the 365-day fetch entirely and emit a neutral
        # placeholder so downstream composite scoring still has a value to multiply by.
        if disable_rs:
            # Mirror the full Phase 3.1 l_component schema so downstream consumers
            # (JSON parsers, report templates, postmortem tools) can read fields
            # uniformly without special-casing the disable-rs branch. Multi-period
            # numeric fields are None; available_periods is empty; missing_periods
            # lists every configured window.
            l_result = {
                "score": 50,
                "skipped": True,
                "reason": "Disabled by --disable-rs",
                # Legacy fields
                "stock_52w_performance": None,
                "sp500_52w_performance": None,
                "relative_performance": None,
                "rs_rank_estimate": None,
                "days_analyzed": 0,
                "interpretation": "L component skipped via --disable-rs (neutral 50)",
                "quality_warning": None,
                "error": None,
                # Phase 3.1 multi-period fields
                "rs_3m_return": None,
                "rs_6m_return": None,
                "rs_12m_return": None,
                "benchmark_3m_return": None,
                "benchmark_6m_return": None,
                "benchmark_12m_return": None,
                "rel_3m": None,
                "rel_6m": None,
                "rel_12m": None,
                "weighted_stock_performance": None,
                "weighted_relative_performance": None,
                "available_periods": [],
                "missing_periods": ["3m", "6m", "12m"],
                "benchmark_52w_performance": None,
                "rs_benchmark": rs_benchmark,
                "rs_benchmark_relative_return": None,
                "rs_rating": "Skipped",
                "rs_component_score": 50,
                "rs_rank_percentile": None,
            }
        else:
            historical_prices_52w_data = client.get_historical_prices(symbol, days=365)
            historical_prices_52w = (
                historical_prices_52w_data.get("historical", [])
                if historical_prices_52w_data
                else []
            )
            rs_benchmark_list = (
                rs_benchmark_historical.get("historical", []) if rs_benchmark_historical else None
            )
            l_result = (
                calculate_leadership(
                    historical_prices_52w,
                    sp500_historical=rs_benchmark_list,
                    rs_benchmark=rs_benchmark,
                )
                if historical_prices_52w
                else {
                    "score": 0,
                    "error": "No 52-week price history",
                    "rs_benchmark": rs_benchmark,
                    "rs_component_score": 0,
                    "rs_rating": "Weak",
                    "rs_rank_percentile": None,
                }
            )

        # I Component: Institutional Sponsorship (with Finviz fallback)
        institutional_holders = client.get_institutional_holders(symbol)
        i_result = (
            calculate_institutional_sponsorship(
                institutional_holders, profile[0], symbol=symbol, use_finviz_fallback=True
            )
            if institutional_holders
            else {"score": 0, "error": "No institutional holder data"}
        )

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
            m_score=m_result.get("score", 50),
        )

        # Check minimum thresholds (Phase 3)
        threshold_check = check_minimum_thresholds_phase3(
            c_score=c_result.get("score", 0),
            a_score=a_result.get("score", 50),
            n_score=n_result.get("score", 0),
            s_score=s_result.get("score", 0),
            l_score=l_result.get("score", 0),
            i_score=i_result.get("score", 0),
            m_score=m_result.get("score", 50),
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
            "threshold_check": threshold_check,
        }

    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def main():
    """Main screening workflow"""
    args = parse_arguments()

    print("=" * 60)
    print("CANSLIM Stock Screener - Phase 3 (Full CANSLIM)")
    print(
        "Components: C (Earnings), A (Growth), N (Newness), S (Supply/Demand), L (Leadership), I (Institutional), M (Market)"
    )
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
        universe = args.universe[: args.max_candidates]
        print(f"✓ Custom universe: {len(universe)} stocks")
    else:
        universe = DEFAULT_UNIVERSE[: args.max_candidates]
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

    # Fetch ^GSPC historical prices for the M component. ^GSPC must remain the
    # benchmark for the M component to keep scale consistent with the ^GSPC quote
    # (see test_canslim_fixes.py::TestBenchmarkScaleConsistency).
    print("Fetching ^GSPC 52-week data for M component (EMA)...")
    market_sp500_historical = client.get_historical_prices("^GSPC", days=365)
    if market_sp500_historical and market_sp500_historical.get("historical"):
        market_days = len(market_sp500_historical.get("historical", []))
        print(f"✓ ^GSPC historical data: {market_days} days")
    else:
        print("⚠️  ^GSPC historical data unavailable - M component will use EMA fallback")

    # Resolve the L component's benchmark fetch. When the user kept the default
    # ^GSPC, reuse the already-fetched series (FMPClient cache also covers this,
    # but the explicit reuse here documents the intent). When --disable-rs is
    # set, skip the benchmark fetch entirely.
    rs_benchmark_historical = None
    if not args.disable_rs:
        if args.rs_benchmark == "^GSPC":
            rs_benchmark_historical = market_sp500_historical
        else:
            print(
                f"Fetching {args.rs_benchmark} 52-week data for L component (Relative Strength)..."
            )
            rs_benchmark_historical = client.get_historical_prices(args.rs_benchmark, days=365)
            if rs_benchmark_historical and rs_benchmark_historical.get("historical"):
                rs_days = len(rs_benchmark_historical.get("historical", []))
                print(f"✓ {args.rs_benchmark} historical data: {rs_days} days")
            else:
                print(
                    f"⚠️  {args.rs_benchmark} historical data unavailable - "
                    "L component will fall back to absolute performance with 20% penalty"
                )
    else:
        print("⚠️  --disable-rs set: L component will be fixed at neutral 50 (no RS fetch)")

    # Calculate M component using real ^GSPC historical prices for accurate EMA
    market_sp500_list = (
        market_sp500_historical.get("historical", []) if market_sp500_historical else []
    )
    market_data = calculate_market_direction(
        sp500_quote=sp500_quote[0],
        sp500_prices=market_sp500_list if market_sp500_list else None,
        vix_quote=vix_quote[0] if vix_quote else None,
    )

    print(f"S&P 500: ${market_data['sp500_price']:.2f}")
    print(f"Distance from 50-EMA: {market_data['distance_from_ema_pct']:+.2f}%")
    print(f"Trend: {market_data['trend']}")
    print(f"M Score: {market_data['score']}/100")
    print(f"Interpretation: {market_data['interpretation']}")

    if market_data.get("warning"):
        print()
        print(f"⚠️  WARNING: {market_data['warning']}")
        print("    Consider raising cash allocation. CANSLIM doesn't work in bear markets.")

    print()

    # Step 2: Progressive filtering and analysis
    print(f"Step 2: Analyzing {len(universe)} Stocks")
    print("-" * 60)

    results = []
    for symbol in universe:
        analysis = analyze_stock(
            symbol,
            client,
            market_data,
            rs_benchmark_historical=rs_benchmark_historical,
            rs_benchmark=args.rs_benchmark,
            disable_rs=args.disable_rs,
        )
        if analysis:
            results.append(analysis)

    print()
    print(f"✓ Successfully analyzed {len(results)} stocks")
    print()

    # Step 3: Rank by composite score
    print("Step 3: Ranking Results")
    print("-" * 60)

    results.sort(key=lambda x: x["composite_score"], reverse=True)

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
        "schema_version": "3.1",
        "phase": "3.1 (7 components - FULL CANSLIM with multi-period RS)",
        "components_included": ["C", "A", "N", "S", "L", "I", "M"],
        "candidates_analyzed": len(results),
        "universe_size": len(universe),
        "screening_options": {
            "rs_benchmark": args.rs_benchmark,
            "rs_disabled": args.disable_rs,
        },
        "market_condition": {
            "trend": market_data["trend"],
            "M_score": market_data["score"],
            "warning": market_data.get("warning"),
        },
    }

    # Limit to top N for report
    top_results = results[: args.top]

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
    print("API Usage:")
    print(f"  Cache entries: {api_stats['cache_entries']}")
    if args.disable_rs:
        # Per-stock 365-day RS fetch is skipped; M-side market calls remain
        # (^GSPC quote + VIX quote + ^GSPC 365-day = 3 calls).
        print(
            f"  Estimated calls: ~{len(universe) * 6 + 3} "
            f"(3 market data calls + {len(universe)} stocks × 6 API calls each, --disable-rs)"
        )
    else:
        # Custom benchmark adds one extra fetch when it differs from ^GSPC.
        market_calls = 3 if args.rs_benchmark == "^GSPC" else 4
        print(
            f"  Estimated calls: ~{len(universe) * 7 + market_calls} "
            f"({market_calls} market data calls + {len(universe)} stocks × 7 API calls each)"
        )
    print("  Phase 3.1 includes all 7 CANSLIM components (C, A, N, S, L, I, M)")
    print()


if __name__ == "__main__":
    main()
