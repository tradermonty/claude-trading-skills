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
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from calculators.pivot_proximity_calculator import calculate_pivot_proximity
from calculators.relative_strength_calculator import (
    calculate_relative_strength,
    rank_relative_strength_universe,
)
from calculators.trend_template_calculator import calculate_trend_template
from calculators.vcp_pattern_calculator import calculate_vcp_pattern
from calculators.volume_pattern_calculator import calculate_volume_pattern
from fmp_client import FMPClient
from yfinance_client import YFinanceClient
from report_generator import generate_json_report, generate_markdown_report
from scorer import calculate_composite_score


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="VCP Stock Screener - Minervini Volatility Contraction Pattern"
    )

    parser.add_argument(
        "--api-key",
        help="FMP API key (defaults to FMP_API_KEY env var). "
             "If omitted and FMP_API_KEY is not set, yfinance is used automatically (no key needed).",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=100,
        help="Max stocks for full VCP analysis after pre-filter (default: 100)",
    )
    parser.add_argument(
        "--top", type=int, default=20, help="Top results to include in report (default: 20)"
    )
    parser.add_argument("--output-dir", default=".", help="Output directory for reports")
    parser.add_argument(
        "--universe", nargs="+", help="Custom symbols to screen (overrides S&P 500)"
    )
    parser.add_argument(
        "--full-sp500",
        action="store_true",
        help="Screen all S&P 500 stocks (requires paid API tier, ~350 calls)",
    )
    parser.add_argument(
        "--nasdaq100",
        action="store_true",
        help="Screen Nasdaq-100 stocks instead of S&P 500 (fetched from Wikipedia, no API key needed)",
    )
    parser.add_argument(
        "--mode",
        choices=["all", "prebreakout"],
        default="all",
        help="Output mode: 'all' shows everything, 'prebreakout' shows entry_ready only (default: all)",
    )
    parser.add_argument(
        "--max-above-pivot",
        type=float,
        default=3.0,
        help="Max %% above pivot for entry_ready (default: 3.0)",
    )
    parser.add_argument(
        "--max-risk", type=float, default=15.0, help="Max risk %% for entry_ready (default: 15.0)"
    )
    parser.add_argument(
        "--no-require-valid-vcp",
        action="store_true",
        help="Do not require valid_vcp=True for entry_ready",
    )
    parser.add_argument(
        "--min-atr-pct",
        type=float,
        default=1.0,
        help="Min avg daily range %% to exclude stale/acquired stocks (default: 1.0)",
    )
    parser.add_argument(
        "--ext-threshold",
        type=float,
        default=8.0,
        help="SMA50 distance %% where extended penalty starts (default: 8.0)",
    )
    parser.add_argument(
        "--min-contractions",
        type=int,
        default=2,
        help="Minimum contractions for valid VCP (default: 2)",
    )
    parser.add_argument(
        "--t1-depth-min",
        type=float,
        default=8.0,
        help="Minimum T1 depth %% (default: 8.0)",
    )
    parser.add_argument(
        "--breakout-volume-ratio",
        type=float,
        default=1.5,
        help="Breakout volume ratio vs 50d avg (default: 1.5)",
    )
    parser.add_argument(
        "--trend-min-score",
        type=float,
        default=85.0,
        help="Minimum trend template raw score for Phase 2 pass (default: 85.0)",
    )
    parser.add_argument(
        "--atr-multiplier",
        type=float,
        default=1.5,
        help="ATR multiplier for ZigZag swing detection (default: 1.5)",
    )
    parser.add_argument(
        "--contraction-ratio",
        type=float,
        default=0.75,
        help="Max ratio for successive contractions (default: 0.75)",
    )
    parser.add_argument(
        "--min-contraction-days",
        type=int,
        default=5,
        help="Minimum days per contraction (default: 5)",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=120,
        help="VCP pattern lookback window in days (default: 120)",
    )

    args = parser.parse_args()

    # Lower bound is 2 by design: VCP requires successive contractions, and
    # contraction_ratio scoring needs at least 2 to compute ratios.
    if not (2 <= args.min_contractions <= 4):
        parser.error("--min-contractions must be 2-4")
    if not (1.0 <= args.t1_depth_min <= 50.0):
        parser.error("--t1-depth-min must be 1.0-50.0")
    if not (0.5 <= args.breakout_volume_ratio <= 10.0):
        parser.error("--breakout-volume-ratio must be 0.5-10.0")
    if not (0 <= args.trend_min_score <= 100):
        parser.error("--trend-min-score must be 0-100")
    if not (0.5 <= args.atr_multiplier <= 5.0):
        parser.error("--atr-multiplier must be 0.5-5.0")
    if not (0.1 <= args.contraction_ratio <= 1.0):
        parser.error("--contraction-ratio must be 0.1-1.0")
    if not (1 <= args.min_contraction_days <= 30):
        parser.error("--min-contraction-days must be 1-30")
    if not (30 <= args.lookback_days <= 365):
        parser.error("--lookback-days must be 30-365")

    return args


def passes_trend_filter(tt_result: dict, trend_min_score: float = 85.0) -> bool:
    """Check if a stock passes Phase 2 trend template filter.

    Uses raw_score (before extended penalty) so that the CLI --trend-min-score
    flag can override the calculator's hardcoded 85-point gate.
    """
    return tt_result.get("raw_score", 0) >= trend_min_score


def pre_filter_stock(quote: dict) -> tuple:
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
    historical: list[dict],
    quote: dict,
    sp500_history: list[dict],
    sector: str = "Unknown",
    company_name: str = "",
    ext_threshold: float = 8.0,
    min_contractions: int = 2,
    t1_depth_min: float = 8.0,
    contraction_ratio: float = 0.75,
    atr_multiplier: float = 1.5,
    min_contraction_days: int = 5,
    lookback_days: int = 120,
    breakout_volume_ratio: float = 1.5,
) -> Optional[dict]:
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
    tt_result = calculate_trend_template(
        historical, quote, rs_rank=rs_rank, ext_threshold=ext_threshold
    )

    # 3. VCP Pattern Detection
    vcp_result = calculate_vcp_pattern(
        historical,
        lookback_days=lookback_days,
        atr_multiplier=atr_multiplier,
        min_contraction_days=min_contraction_days,
        min_contractions=min_contractions,
        t1_depth_min=t1_depth_min,
        contraction_ratio=contraction_ratio,
    )

    # 4. Volume Pattern
    pivot_price = vcp_result.get("pivot_price")
    vol_result = calculate_volume_pattern(
        historical,
        pivot_price=pivot_price,
        contractions=vcp_result.get("contractions"),
        breakout_volume_ratio=breakout_volume_ratio,
    )

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
    valid_vcp = vcp_result.get("valid_vcp", False)
    composite = calculate_composite_score(
        trend_score=tt_result.get("score", 0),
        contraction_score=vcp_result.get("score", 0),
        volume_score=vol_result.get("score", 0),
        pivot_score=piv_result.get("score", 0),
        rs_score=rs_result.get("score", 0),
        valid_vcp=valid_vcp,
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
        "valid_vcp": valid_vcp,
        "distance_from_pivot_pct": piv_result.get("distance_from_pivot_pct"),
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


def is_stale_price(
    historical: list[dict],
    lookback: int = 10,
    threshold: float = 1.0,
) -> bool:
    """Detect acquired/pinned stocks with abnormally flat price action.

    Args:
        historical: Price data (most-recent-first)
        lookback: Number of recent days to check
        threshold: Max average daily range % to be considered stale

    Returns:
        True if the stock's price action is stale (likely acquired/pinned)
    """
    if len(historical) < lookback:
        return False

    recent = historical[:lookback]
    ranges = []
    for bar in recent:
        high = bar.get("high", 0)
        low = bar.get("low", 0)
        close = bar.get("close", 0)
        if close > 0:
            ranges.append((high - low) / close * 100)

    if not ranges:
        return False

    avg_range_pct = sum(ranges) / len(ranges)
    return avg_range_pct < threshold


def compute_entry_ready(
    result: dict,
    max_above_pivot: float = 3.0,
    max_risk: float = 15.0,
    require_valid_vcp: bool = True,
) -> bool:
    """Determine if a stock is entry-ready based on configurable thresholds.

    Args:
        result: Analysis result dict from analyze_stock()
        max_above_pivot: Max % above pivot for entry readiness
        max_risk: Max risk % for entry readiness
        require_valid_vcp: Whether valid_vcp=True is required
    """
    valid_vcp = result.get("valid_vcp", False)
    distance = result.get("distance_from_pivot_pct")
    dry_up_ratio = result.get("volume_pattern", {}).get("dry_up_ratio")
    risk_pct = result.get("pivot_proximity", {}).get("risk_pct")

    if require_valid_vcp and not valid_vcp:
        return False
    if distance is None:
        return False
    if not (-8.0 <= distance <= max_above_pivot):
        return False
    if dry_up_ratio is None or dry_up_ratio > 1.0:
        return False
    if risk_pct is None or risk_pct > max_risk:
        return False
    return True


def main():
    args = parse_arguments()

    if not (0 < args.ext_threshold < 50):
        print("ERROR: --ext-threshold must be between 0 and 50 (exclusive)", file=sys.stderr)
        sys.exit(1)

    print("=" * 70)
    print("VCP Stock Screener")
    print("Mark Minervini's Volatility Contraction Pattern")
    print("=" * 70)
    print()

    # Initialize data client: prefer FMP when a key is available, else yfinance
    import os
    use_fmp = args.api_key or os.getenv("FMP_API_KEY")
    if use_fmp:
        try:
            client = FMPClient(api_key=args.api_key)
            print("FMP API client initialized")
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        client = YFinanceClient()
        print("yfinance client initialized (no FMP key — using Yahoo Finance)")

    # ========================================================================
    # Phase 1: Pre-Filter (API-efficient)
    # ========================================================================
    print()
    print("Phase 1: Pre-Filter")
    print("-" * 70)

    # Determine universe
    constituents = []
    if args.universe:
        symbols = args.universe
        universe_desc = f"Custom ({len(symbols)} stocks)"
        print(f"  Using custom universe: {len(symbols)} stocks")
    elif args.nasdaq100:
        print("  Fetching Nasdaq-100 constituents...", end=" ", flush=True)
        constituents = client.get_nasdaq100_constituents()
        if not constituents:
            print("FAILED")
            print("ERROR: Unable to fetch Nasdaq-100 constituents", file=sys.stderr)
            sys.exit(1)
        symbols = [c["symbol"] for c in constituents]
        universe_desc = f"Nasdaq-100 ({len(symbols)} stocks)"
        print(f"OK ({len(symbols)} stocks)")
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
    print("  Fetching quotes...", end=" ", flush=True)
    all_quotes = client.get_batch_quotes(symbols)
    print(f"OK ({len(all_quotes)} quotes)")

    # Apply pre-filter
    print("  Applying pre-filter...", end=" ", flush=True)
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
        if data and "historical" in data:
            candidate_histories[sym] = data["historical"]

    # Apply Trend Template filter
    print("  Applying 7-point Trend Template...", end=" ", flush=True)
    trend_passed = []

    for sym, likelihood, quote in candidates:
        hist = candidate_histories.get(sym, [])
        if not hist or len(hist) < 50:
            continue

        # Quick RS calculation for criterion 7
        rs_result = calculate_relative_strength(hist, sp500_history)
        rs_rank = rs_result.get("rs_rank_estimate", 0)

        tt_result = calculate_trend_template(
            hist, quote, rs_rank=rs_rank, ext_threshold=args.ext_threshold
        )
        if passes_trend_filter(tt_result, args.trend_min_score):
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

        # Skip stale/acquired stocks
        if is_stale_price(hist, threshold=args.min_atr_pct):
            print(f"  Skipping {sym} (stale price - likely acquired/pinned)")
            continue

        print(f"  Analyzing {sym}...", end=" ", flush=True)
        analysis = analyze_stock(
            sym,
            hist,
            quote,
            sp500_history,
            sector,
            name,
            ext_threshold=args.ext_threshold,
            min_contractions=args.min_contractions,
            t1_depth_min=args.t1_depth_min,
            contraction_ratio=args.contraction_ratio,
            atr_multiplier=args.atr_multiplier,
            min_contraction_days=args.min_contraction_days,
            lookback_days=args.lookback_days,
            breakout_volume_ratio=args.breakout_volume_ratio,
        )

        if analysis:
            score = analysis["composite_score"]
            print(f"Score: {score:.1f} ({analysis['rating']})")
            results.append(analysis)
        else:
            print("FAILED")

    print()

    # Re-rank RS across the universe for percentile-based scoring
    if results:
        rs_map = {r["symbol"]: r["relative_strength"] for r in results}
        ranked_rs = rank_relative_strength_universe(rs_map)
        for r in results:
            r["relative_strength"] = ranked_rs[r["symbol"]]
            # Recalculate composite score with updated RS
            composite = calculate_composite_score(
                trend_score=r["trend_template"].get("score", 0),
                contraction_score=r["vcp_pattern"].get("score", 0),
                volume_score=r["volume_pattern"].get("score", 0),
                pivot_score=r["pivot_proximity"].get("score", 0),
                rs_score=r["relative_strength"].get("score", 0),
                valid_vcp=r.get("valid_vcp", False),
            )
            r["composite_score"] = composite["composite_score"]
            r["rating"] = composite["rating"]
            r["rating_description"] = composite["rating_description"]
            r["guidance"] = composite["guidance"]
            r["weakest_component"] = composite["weakest_component"]
            r["weakest_score"] = composite["weakest_score"]
            r["strongest_component"] = composite["strongest_component"]
            r["strongest_score"] = composite["strongest_score"]

    # Compute entry_ready using CLI thresholds
    require_vcp = not args.no_require_valid_vcp
    for r in results:
        r["entry_ready"] = compute_entry_ready(
            r,
            max_above_pivot=args.max_above_pivot,
            max_risk=args.max_risk,
            require_valid_vcp=require_vcp,
        )

    # Sort by composite score
    results.sort(key=lambda x: x["composite_score"], reverse=True)

    # Apply prebreakout filter if requested
    if args.mode == "prebreakout":
        total_before = len(results)
        results = [r for r in results if r.get("entry_ready", False)]
        print(f"  Pre-breakout filter: {total_before} -> {len(results)} candidates")
        print()

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
        "ext_threshold": args.ext_threshold,
        "tuning_params": {
            "min_contractions": args.min_contractions,
            "t1_depth_min": args.t1_depth_min,
            "breakout_volume_ratio": args.breakout_volume_ratio,
            "trend_min_score": args.trend_min_score,
            "atr_multiplier": args.atr_multiplier,
            "contraction_ratio": args.contraction_ratio,
            "min_contraction_days": args.min_contraction_days,
            "lookback_days": args.lookback_days,
        },
        "funnel": {
            "universe": len(symbols),
            "pre_filter_passed": len(pre_filtered),
            "trend_template_passed": len(trend_passed),
            "vcp_candidates": len(results),
        },
        "api_stats": api_stats,
    }

    top_results = results[: args.top]

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
            print(
                f"  {i}. {s['symbol']:6} Score: {s['composite_score']:5.1f} "
                f"({s['rating']}) {pivot_str}"
            )
    else:
        print()
        print("  No VCP candidates found in this screening run.")

    print()
    print(f"  JSON Report:    {json_file}")
    print(f"  Markdown Report: {md_file}")
    print()
    print("API Usage:")
    print(f"  API calls made: {api_stats['api_calls_made']}")
    print(f"  Cache entries:  {api_stats['cache_entries']}")
    print()


if __name__ == "__main__":
    main()
