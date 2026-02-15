#!/usr/bin/env python3
"""
FTD Detector - Main Orchestrator

Detects Follow-Through Day (FTD) signals for market bottom confirmation
using William O'Neil's methodology with dual-index tracking.

Usage:
    python3 ftd_detector.py --api-key YOUR_KEY
    python3 ftd_detector.py  # uses FMP_API_KEY env var

Output:
    - JSON: ftd_detector_YYYY-MM-DD_HHMMSS.json
    - Markdown: ftd_detector_YYYY-MM-DD_HHMMSS.md
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Dict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from fmp_client import FMPClient
from rally_tracker import get_market_state
from post_ftd_monitor import assess_post_ftd_health
from report_generator import generate_json_report, generate_markdown_report


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="FTD Detector - Follow-Through Day Bottom Confirmation"
    )
    parser.add_argument(
        "--api-key",
        help="FMP API key (defaults to FMP_API_KEY environment variable)"
    )
    parser.add_argument(
        "--output-dir", default=".",
        help="Output directory for reports (default: current directory)"
    )
    return parser.parse_args()


def main():
    args = parse_arguments()

    print("=" * 70)
    print("FTD Detector - Follow-Through Day Bottom Confirmation")
    print("O'Neil Rally Attempt + FTD State Machine (Dual Index)")
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
    # Step 1: Fetch Market Data (4 API calls)
    # ========================================================================
    print()
    print("Step 1: Fetching Market Data")
    print("-" * 70)

    # S&P 500 history (60 trading days)
    print("  Fetching S&P 500 history...", end=" ", flush=True)
    sp500_history_data = client.get_historical_prices("^GSPC", days=80)
    sp500_history = sp500_history_data.get("historical", []) if sp500_history_data else []
    if sp500_history:
        print(f"OK ({len(sp500_history)} days)")
    else:
        print("FAILED")
        print("ERROR: Cannot proceed without S&P 500 data", file=sys.stderr)
        sys.exit(1)

    # NASDAQ/QQQ history (60 trading days)
    print("  Fetching NASDAQ (QQQ) history...", end=" ", flush=True)
    qqq_history_data = client.get_historical_prices("QQQ", days=80)
    qqq_history = qqq_history_data.get("historical", []) if qqq_history_data else []
    if qqq_history:
        print(f"OK ({len(qqq_history)} days)")
    else:
        print("WARN - NASDAQ data unavailable, using S&P 500 only")

    # S&P 500 quote (for current price)
    print("  Fetching S&P 500 quote...", end=" ", flush=True)
    sp500_quote_list = client.get_quote("^GSPC")
    sp500_quote = sp500_quote_list[0] if sp500_quote_list else None
    if sp500_quote:
        print(f"OK (${sp500_quote.get('price', 0):.2f})")
    else:
        print("WARN - Using historical close as current price")

    # QQQ quote
    print("  Fetching QQQ quote...", end=" ", flush=True)
    qqq_quote_list = client.get_quote("QQQ")
    qqq_quote = qqq_quote_list[0] if qqq_quote_list else None
    if qqq_quote:
        print(f"OK (${qqq_quote.get('price', 0):.2f})")
    else:
        print("WARN - Using historical close as current price")

    print()

    # ========================================================================
    # Step 2: Run State Machine (Rally Tracker)
    # ========================================================================
    print("Step 2: Analyzing Market State")
    print("-" * 70)

    market_state = get_market_state(sp500_history, qqq_history)

    sp500_state = market_state["sp500"]["state"]
    nasdaq_state = market_state["nasdaq"]["state"]
    combined = market_state["combined_state"]

    print(f"  S&P 500 State: {sp500_state}")
    print(f"  NASDAQ State:  {nasdaq_state}")
    print(f"  Combined:      {combined}")

    # Print swing low info if found
    for label, idx_data in [("S&P 500", market_state["sp500"]),
                            ("NASDAQ", market_state["nasdaq"])]:
        swing = idx_data.get("swing_low")
        if swing:
            print(f"  {label} Swing Low: {swing['swing_low_date']} "
                  f"(${swing['swing_low_price']:.2f}, "
                  f"{swing['decline_pct']:.1f}% decline)")
        rally = idx_data.get("rally_attempt")
        if rally and rally.get("day1_date"):
            print(f"  {label} Rally Day 1: {rally['day1_date']} "
                  f"(Day {rally['current_day_count']})")

    print()

    # ========================================================================
    # Step 3: Post-FTD Health Assessment
    # ========================================================================
    print("Step 3: Post-FTD Health Assessment")
    print("-" * 70)

    # Convert to chronological for post-FTD analysis
    sp500_chrono = list(reversed(sp500_history))
    nasdaq_chrono = list(reversed(qqq_history)) if qqq_history else []

    market_state = assess_post_ftd_health(market_state, sp500_chrono, nasdaq_chrono)

    quality = market_state.get("quality_score", {})
    print(f"  Quality Score: {quality.get('total_score', 0)}/100")
    print(f"  Signal: {quality.get('signal', 'N/A')}")
    print(f"  Guidance: {quality.get('guidance', 'N/A')}")
    print(f"  Exposure Range: {quality.get('exposure_range', 'N/A')}")

    # Power trend
    pt = market_state.get("power_trend", {})
    if pt:
        print(f"  Power Trend: {'YES' if pt.get('power_trend') else 'No'} "
              f"({pt.get('conditions_met', 0)}/3 conditions)")

    # Post-FTD distribution
    dist = market_state.get("post_ftd_distribution", {})
    if dist:
        print(f"  Post-FTD Distribution Days: {dist.get('distribution_count', 0)} "
              f"(monitored {dist.get('days_monitored', 0)} days)")

    # Invalidation
    inv = market_state.get("ftd_invalidation", {})
    if inv and inv.get("invalidated"):
        print(f"  FTD INVALIDATED on {inv.get('invalidation_date')} "
              f"({inv.get('days_after_ftd')} days after FTD)")

    print()

    # ========================================================================
    # Step 4: Generate Reports
    # ========================================================================
    print("Step 4: Generating Reports")
    print("-" * 70)

    analysis = {
        "metadata": {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "api_calls": client.get_api_stats(),
            "index_prices": {
                "sp500": sp500_quote.get("price", 0) if sp500_quote else (
                    sp500_history[0].get("close", 0) if sp500_history else None
                ),
                "qqq": qqq_quote.get("price", 0) if qqq_quote else (
                    qqq_history[0].get("close", 0) if qqq_history else None
                ),
            },
        },
        "market_state": {
            "combined_state": market_state["combined_state"],
            "dual_confirmation": market_state["dual_confirmation"],
            "ftd_index": market_state.get("ftd_index"),
        },
        "sp500": _serialize_index(market_state["sp500"]),
        "nasdaq": _serialize_index(market_state["nasdaq"]),
        "quality_score": quality,
        "post_ftd_distribution": market_state.get("post_ftd_distribution", {}),
        "ftd_invalidation": market_state.get("ftd_invalidation", {}),
        "power_trend": market_state.get("power_trend", {}),
    }

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_file = os.path.join(args.output_dir, f"ftd_detector_{timestamp}.json")
    md_file = os.path.join(args.output_dir, f"ftd_detector_{timestamp}.md")

    generate_json_report(analysis, json_file)
    generate_markdown_report(analysis, md_file)

    print()
    print("=" * 70)
    print("FTD Detection Complete")
    print("=" * 70)
    print(f"  Combined State: {market_state['combined_state']}")
    print(f"  Quality Score: {quality.get('total_score', 0)}/100 ({quality.get('signal', 'N/A')})")
    print(f"  JSON Report: {json_file}")
    print(f"  Markdown Report: {md_file}")
    print()

    stats = client.get_api_stats()
    print(f"API Usage:")
    print(f"  API calls made: {stats['api_calls_made']}")
    print(f"  Cache entries: {stats['cache_entries']}")
    print()


def _serialize_index(idx_data: Dict) -> Dict:
    """Serialize index analysis for JSON output, removing large rally_days lists."""
    result = {
        "state": idx_data.get("state"),
        "current_price": idx_data.get("current_price"),
        "lookback_high": idx_data.get("lookback_high"),
        "correction_depth_pct": idx_data.get("correction_depth_pct"),
    }

    swing = idx_data.get("swing_low")
    if swing:
        result["swing_low"] = {
            "date": swing.get("swing_low_date"),
            "price": swing.get("swing_low_price"),
            "decline_pct": swing.get("decline_pct"),
            "down_days": swing.get("down_days"),
            "recent_high_date": swing.get("recent_high_date"),
            "recent_high_price": swing.get("recent_high_price"),
        }

    rally = idx_data.get("rally_attempt")
    if rally:
        result["rally_attempt"] = {
            "day1_date": rally.get("day1_date"),
            "current_day_count": rally.get("current_day_count"),
            "invalidated": rally.get("invalidated"),
            "invalidation_reason": rally.get("invalidation_reason"),
        }

    ftd = idx_data.get("ftd")
    if ftd:
        result["ftd"] = {
            "ftd_detected": ftd.get("ftd_detected"),
            "ftd_date": ftd.get("ftd_date"),
            "ftd_day_number": ftd.get("ftd_day_number"),
            "gain_pct": ftd.get("gain_pct"),
            "gain_tier": ftd.get("gain_tier"),
            "volume_above_avg": ftd.get("volume_above_avg"),
        }

    return result


if __name__ == "__main__":
    main()
