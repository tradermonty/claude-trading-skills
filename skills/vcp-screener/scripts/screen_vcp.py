#!/usr/bin/env python3
"""
VCP Stock Screener - Main Orchestrator

Screens S&P 500 stocks for Mark Minervini's Volatility Contraction Pattern (VCP).
Uses a 3-phase pipeline: Pre-filter -> Trend Template -> VCP Detection & Scoring.

Usage:
    # Default (S&P 500, top 100 candidates, free tier API)
    python3 screen_vcp.py --api-key YOUR_KEY

    # Custom universe
    python3 screen_vcp.py --universe AAPL NVDA MSFT AMZN META

    # Full S&P 500 (requires paid API tier)
    python3 screen_vcp.py --full-sp500

Output:
    - JSON: vcp_screener_YYYY-MM-DD_HHMMSS.json
    - Markdown: vcp_screener_YYYY-MM-DD_HHMMSS.md
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from fmp_client import FMPClient
from calculators.trend_template_calculator import calculate_trend_template
from calculators.vcp_pattern_calculator import calculate_vcp_pattern
from calculators.volume_pattern_calculator import calculate_volume_pattern
from calculators.pivot_proximity_calculator import calculate_pivot_proximity
from calculators.relative_strength_calculator import calculate_relative_strength
from scorer import calculate_composite_score
from report_generator import generate_json_report, generate_markdown_report


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="VCP Stock Screener - Minervini Volatility Contraction Pattern"
    )

    parser.add_argument(
        "--api-key",
        help="FMP API key (defaults to FMP_API_KEY environment variable)"
    )
    parser.add_argument(
        "--max-candidates", type=int, default=100,
        help="Max stocks for full VCP analysis after pre-filter (default: 100)"
    )
    parser.add_argument(
        "--top", type=int, default=20,
        help="Top results to include in report (default: 20)"
    )
    parser.add_argument(
        "--output-dir", default=".",
        help="Output directory for reports"
    )
    parser.add_argument(
        "--universe", nargs="+",
        help="Custom symbols to screen (overrides S&P 500)"
    )
    parser.add_argument(
        "--full-sp500", action="store_true",
        help="Screen all S&P 500 stocks (requires paid API tier, ~350 calls)"
    )

    return parser.parse_args()


def pre_filter_stock(quote: Dict) -> tuple:
    """
    Cheap pre-filter using quote data only.

    Criteria:
    - Price > $10
    - At least 20% above 52-week low
    - Within 30% of 52-week high
    - Average volume > 200,000

    Returns:
        (passed: bool, stage2_likelihood_score: float)
    """
    price = quote.get("price", 0)
    year_high = quote.get("yearHigh", 0)
    year_low = quote.get("yearLow", 0)
    avg_volume = quote.get("avgVolume", 0)

    if price <= 10:
        return False, 0
    if avg_volume < 200000:
        return False, 0

    # Check distance from 52w low
    if year_low <= 0:
        return False, 0
    pct_above_low = (price - year_low) / year_low
    if pct_above_low < 0.20:
        return False, 0

    # Check distance from 52w high
    if year_high <= 0:
        return False, 0
    pct_below_high = (year_high - price) / year_high
    if pct_below_high > 0.30:
        return False, 0

    # Stage 2 likelihood score (higher = more likely in uptrend)
    # Combines proximity to high and distance from low
    score = pct_above_low * 50 + (1 - pct_below_high) * 50

    return True, score


def analyze_stock(
    symbol: str,
    historical: List[Dict],
    quote: Dict,
    sp500_history: List[Dict],
    sector: str = "Unknown",
    company_name: str = "",
) -> Optional[Dict]:
    """
    Full VCP analysis for a single stock (Phase 3).
    No additional API calls needed - uses pre-fetched data.
    """
    price = quote.get("price", 0)
    market_cap = quote.get("marketCap", 0)

    # 1. Relative Strength (needed for Trend Template criterion 7)
    rs_result = calculate_relative_strength(historical, sp500_history)
    rs_rank = rs_result.get("rs_rank_estimate", 0)

    # 2. Trend Template
    tt_result = calculate_trend_template(historical, quote, rs_rank=rs_rank)

    # 3. VCP Pattern Detection
    vcp_result = calculate_vcp_pattern(historical, lookback_days=120)

    # 4. Volume Pattern
    pivot_price = vcp_result.get("pivot_price")
    vol_result = calculate_volume_pattern(historical, pivot_price=pivot_price)

    # 5. Pivot Proximity
    last_low = None
    contractions = vcp_result.get("contractions", [])
    if contractions:
        last_low = contractions[-1].get("low_price")

    piv_result = calculate_pivot_proximity(
        current_price=price,
        pivot_price=pivot_price,
        last_contraction_low=last_low,
        breakout_volume=vol_result.get("breakout_volume_detected", False),
    )

    # 6. Composite Score
    composite = calculate_composite_score(
        trend_score=tt_result.get("score", 0),
        contraction_score=vcp_result.get("score", 0),
        volume_score=vol_result.get("score", 0),
        pivot_score=piv_result.get("score", 0),
        rs_score=rs_result.get("score", 0),
    )

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
        "strongest_component": composite["strongest_component"],
        "strongest_score": composite["strongest_score"],
        "trend_template": tt_result,
        "vcp_pattern": vcp_result,
        "volume_pattern": vol_result,
        "pivot_proximity": piv_result,
        "relative_strength": rs_result,
    }


def main():
    args = parse_arguments()

    print("=" * 70)
    print("VCP Stock Screener")
    print("Mark Minervini's Volatility Contraction Pattern")
    print("=" * 70)
    print()

    # Initialize FMP client
    try:
        client = FMPClient(api_key=args.api_key)
        print("FMP API client initialized")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # ========================================================================
    # Phase 1: Pre-Filter (API-efficient)
    # ========================================================================
    print()
    print("Phase 1: Pre-Filter")
    print("-" * 70)

    # Determine universe
    if args.universe:
        symbols = args.universe
        universe_desc = f"Custom ({len(symbols)} stocks)"
        print(f"  Using custom universe: {len(symbols)} stocks")
    else:
        print("  Fetching S&P 500 constituents...", end=" ", flush=True)
        constituents = client.get_sp500_constituents()
        if not constituents:
            print("FAILED")
            print("ERROR: Unable to fetch S&P 500 constituents", file=sys.stderr)
            sys.exit(1)
        symbols = [c["symbol"] for c in constituents]
        universe_desc = f"S&P 500 ({len(symbols)} stocks)"
        print(f"OK ({len(symbols)} stocks)")

    # Build sector/name lookup
    sector_map = {}
    name_map = {}
    if not args.universe and constituents:
        for c in constituents:
            sector_map[c["symbol"]] = c.get("sector", "Unknown")
            name_map[c["symbol"]] = c.get("name", c["symbol"])

    # Batch fetch quotes
    print(f"  Fetching quotes...", end=" ", flush=True)
    all_quotes = client.get_batch_quotes(symbols)
    print(f"OK ({len(all_quotes)} quotes)")

    # Apply pre-filter
    print(f"  Applying pre-filter...", end=" ", flush=True)
    pre_filtered = []
    for sym in symbols:
        quote = all_quotes.get(sym)
        if not quote:
            continue
        passed, likelihood = pre_filter_stock(quote)
        if passed:
            pre_filtered.append((sym, likelihood, quote))

    # Sort by Stage 2 likelihood, take top candidates
    pre_filtered.sort(key=lambda x: x[1], reverse=True)
    max_candidates = len(pre_filtered) if args.full_sp500 else args.max_candidates
    candidates = pre_filtered[:max_candidates]

    print(f"{len(pre_filtered)} passed, taking top {len(candidates)}")
    print()

    # ========================================================================
    # Phase 2: Trend Template Filter
    # ========================================================================
    print("Phase 2: Trend Template Filter")
    print("-" * 70)

    # Fetch SPY historical for RS calculation
    print("  Fetching SPY 260-day history...", end=" ", flush=True)
    spy_data = client.get_historical_prices("SPY", days=260)
    sp500_history = spy_data.get("historical", []) if spy_data else []
    if sp500_history:
        print(f"OK ({len(sp500_history)} days)")
    else:
        print("WARN - SPY data unavailable, RS calculations will be limited")

    # Fetch historical data for candidates
    candidate_symbols = [c[0] for c in candidates]
    print(f"  Fetching 260-day histories for {len(candidate_symbols)} candidates...")

    candidate_histories = {}
    for i, sym in enumerate(candidate_symbols):
        if (i + 1) % 20 == 0 or i == len(candidate_symbols) - 1:
            print(f"    Progress: {i + 1}/{len(candidate_symbols)}", flush=True)
        data = client.get_historical_prices(sym, days=260)
        if data and 'historical' in data:
            candidate_histories[sym] = data['historical']

    # Apply Trend Template filter
    print(f"  Applying 7-point Trend Template...", end=" ", flush=True)
    trend_passed = []

    for sym, likelihood, quote in candidates:
        hist = candidate_histories.get(sym, [])
        if not hist or len(hist) < 50:
            continue

        # Quick RS calculation for criterion 7
        rs_result = calculate_relative_strength(hist, sp500_history)
        rs_rank = rs_result.get("rs_rank_estimate", 0)

        tt_result = calculate_trend_template(hist, quote, rs_rank=rs_rank)
        if tt_result.get("passed"):
            trend_passed.append((sym, quote))

    print(f"{len(trend_passed)} passed")
    print()

    # ========================================================================
    # Phase 3: VCP Detection & Scoring
    # ========================================================================
    print("Phase 3: VCP Detection & Scoring")
    print("-" * 70)

    results = []
    for sym, quote in trend_passed:
        hist = candidate_histories.get(sym, [])
        sector = sector_map.get(sym, "Unknown")
        name = name_map.get(sym, sym)

        # For custom universe, try to get name from quote
        if not name or name == sym:
            name = quote.get("name", sym)
        if not sector or sector == "Unknown":
            sector = quote.get("sector", "Unknown")

        print(f"  Analyzing {sym}...", end=" ", flush=True)
        analysis = analyze_stock(sym, hist, quote, sp500_history, sector, name)

        if analysis:
            score = analysis["composite_score"]
            print(f"Score: {score:.1f} ({analysis['rating']})")
            results.append(analysis)
        else:
            print("FAILED")

    print()

    # Sort by composite score
    results.sort(key=lambda x: x["composite_score"], reverse=True)

    # ========================================================================
    # Generate Reports
    # ========================================================================
    print("Generating Reports")
    print("-" * 70)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_file = os.path.join(args.output_dir, f"vcp_screener_{timestamp}.json")
    md_file = os.path.join(args.output_dir, f"vcp_screener_{timestamp}.md")

    api_stats = client.get_api_stats()

    metadata = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "universe_description": universe_desc,
        "max_candidates": max_candidates,
        "funnel": {
            "universe": len(symbols),
            "pre_filter_passed": len(pre_filtered),
            "trend_template_passed": len(trend_passed),
            "vcp_candidates": len(results),
        },
        "api_stats": api_stats,
    }

    top_results = results[:args.top]

    generate_json_report(top_results, metadata, json_file, all_results=results)
    generate_markdown_report(top_results, metadata, md_file, all_results=results)

    # ========================================================================
    # Summary
    # ========================================================================
    print()
    print("=" * 70)
    print("VCP Screening Complete")
    print("=" * 70)

    # Top 5 display
    if results:
        print()
        print(f"Top {min(5, len(results))} Results:")
        for i, s in enumerate(results[:5], 1):
            pivot = s.get("vcp_pattern", {}).get("pivot_price")
            pivot_str = f"Pivot: ${pivot:.2f}" if pivot else ""
            print(f"  {i}. {s['symbol']:6} Score: {s['composite_score']:5.1f} "
                  f"({s['rating']}) {pivot_str}")
    else:
        print()
        print("  No VCP candidates found in this screening run.")

    print()
    print(f"  JSON Report:    {json_file}")
    print(f"  Markdown Report: {md_file}")
    print()
    print(f"API Usage:")
    print(f"  API calls made: {api_stats['api_calls_made']}")
    print(f"  Cache entries:  {api_stats['cache_entries']}")
    print()


if __name__ == "__main__":
    main()
