#!/usr/bin/env python3
"""
Earnings Trade Analyzer - Main Orchestrator

Analyzes recent post-earnings stocks using a 5-factor scoring system:
  1. Gap Size (25%)
  2. Pre-Earnings Trend (30%)
  3. Volume Trend (20%)
  4. MA200 Position (15%)
  5. MA50 Position (10%)

Scores each stock 0-100 and assigns A/B/C/D grades.

4-Phase Pipeline:
  Phase 1:   Fetch earnings calendar, profiles, filter by market cap + US exchange
  Phase 1.5: Budget check - estimate remaining API calls, trim if needed
  Phase 2:   Fetch historical daily prices (250 days) for each candidate
  Phase 3:   Score all 5 factors, composite score, grade, optional entry filter
  Phase 4:   Generate JSON + Markdown reports

Usage:
    python3 analyze_earnings_trades.py --output-dir reports/
    python3 analyze_earnings_trades.py --lookback-days 5 --min-market-cap 1000000000
    python3 analyze_earnings_trades.py --apply-entry-filter --top 30
"""

import argparse
import math
import os
import sys
from datetime import datetime, timedelta

# Add scripts directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from calculators.gap_size_calculator import calculate_gap
from calculators.ma50_calculator import calculate_ma50_position
from calculators.ma200_calculator import calculate_ma200_position
from calculators.pre_earnings_trend_calculator import calculate_pre_earnings_trend
from calculators.volume_trend_calculator import calculate_volume_trend
from fmp_client import ApiCallBudgetExceeded, FMPClient
from report_generator import generate_json_report, generate_markdown_report
from scorer import calculate_composite_score


def normalize_timing(time_value):
    """Normalize FMP time field to bmo/amc/unknown."""
    if not time_value:
        return "unknown"
    t = time_value.lower().strip()
    if t in ("bmo", "pre-market", "before market open"):
        return "bmo"
    elif t in ("amc", "after-market", "after market close"):
        return "amc"
    else:
        return "unknown"


# ZERO_RESULT_REASON -> (exit_code, one-line explanation). `no_earnings_rows`
# and `calendar_fetch_failed` are evaluated in `classify_empty_calendar`
# (falsy calendar responses, before candidate selection); the rest in
# `explain_empty_selection` in fixed order; see docs/dev/provider-contracts.md.
_ZERO_RESULT_MESSAGES = {
    "no_earnings_rows": (
        0,
        "The earnings calendar carried no rows with a symbol for the lookback window.",
    ),
    "calendar_fetch_failed": (
        1,
        "The earnings calendar fetch failed (no usable response body); "
        "the provider may be down or the response shape may have changed.",
    ),
    "profiles_budget_exhausted": (
        0,
        "API budget was exhausted before any company profile could be fetched.",
    ),
    "no_profiles_returned": (
        1,
        "The FMP API returned earnings symbols but no company profiles for any of them.",
    ),
    "profiles_missing_required_field:marketCap": (
        1,
        "None of the returned profiles contain a usable marketCap field; "
        "the FMP response shape may have changed.",
    ),
    "profiles_missing_required_field:exchange": (
        1,
        "None of the returned profiles contain a string exchange field; "
        "the FMP response shape may have changed.",
    ),
    "all_below_market_cap_floor": (
        0,
        "All candidates were below the minimum market cap floor.",
    ),
    "all_non_us_exchange": (
        0,
        "All candidates trade on non-US exchanges.",
    ),
    "mixed_filters_rejected_all": (
        0,
        "Every candidate was rejected, but by different filters (cap floor for some, "
        "exchange for others) rather than a uniform cause; this looks like an "
        "ordinary empty day, not a schema drift.",
    ),
}


def classify_empty_calendar(earnings) -> str:
    """Classify a falsy earnings-calendar response (issue #355).

    Only a clean empty list is benign: the provider returns HTTP 200 with
    ``[]`` for a window with no announcements. ``None`` (transport/HTTP
    failure, rate limit) and any non-list body (wrong shape, including a
    200-with-``null`` body) fail closed as ``calendar_fetch_failed``.
    Truthy lists — including symbol-less ones — never reach this helper;
    they fall through to ``select_candidates``/``explain_empty_selection``.
    """
    if isinstance(earnings, list) and not earnings:
        return "no_earnings_rows"
    return "calendar_fetch_failed"


def explain_empty_selection(earnings, profiles, min_market_cap, api_stats):
    """Explain why ``select_candidates(...)`` returned no candidates.

    Called only when ``select_candidates`` returns ``[]``. Conditions are
    evaluated in the fixed order below (each returns the first matching
    ``ZERO_RESULT_REASON`` code); see docs/dev/provider-contracts.md.

    Codes, in evaluation order: ``no_earnings_rows`` (no calendar row carried a
    symbol -- a genuine empty window), ``profiles_budget_exhausted``,
    ``no_profiles_returned``, ``profiles_missing_required_field:marketCap``,
    ``profiles_missing_required_field:exchange``, ``all_below_market_cap_floor``
    (every usable profile fails the same cap-floor filter),
    ``all_non_us_exchange`` (every usable profile fails the same exchange
    filter), ``mixed_filters_rejected_all`` (usable profiles exist but are
    rejected by a *mix* of the cap-floor and exchange filters -- an ordinary
    empty day, not a schema-drift signal), and ``unknown`` as a last-resort
    fallback for a case not covered above.
    """
    symbols = [e.get("symbol") for e in earnings if isinstance(e, dict) and e.get("symbol")]
    if not symbols:
        return "no_earnings_rows"

    budget_exhausted = api_stats.get("budget_remaining") == 0 or api_stats.get(
        "rate_limit_reached", False
    )
    if budget_exhausted and not profiles:
        return "profiles_budget_exhausted"

    if symbols and not profiles:
        return "no_profiles_returned"

    usable = []  # (symbol, market_cap, exchange)
    any_profile = False
    for symbol, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        any_profile = True
        cap = profile.get("marketCap")
        if isinstance(cap, bool) or not isinstance(cap, (int, float)):
            continue
        if isinstance(cap, float) and not math.isfinite(cap):
            continue
        usable.append((symbol, cap, profile.get("exchange")))

    if any_profile and not usable:
        return "profiles_missing_required_field:marketCap"

    if usable and not any(isinstance(exch, str) for _, _, exch in usable):
        return "profiles_missing_required_field:exchange"

    if usable and all(cap < min_market_cap for _, cap, _ in usable):
        return "all_below_market_cap_floor"

    if usable and all(
        isinstance(exch, str) and exch not in FMPClient.US_EXCHANGES for _, _, exch in usable
    ):
        return "all_non_us_exchange"

    if usable:
        return "mixed_filters_rejected_all"

    return "unknown"


def select_candidates(earnings, profiles, min_market_cap):
    """Select unique US-listed earnings candidates from stable profile payloads."""
    candidates = []
    seen = set()

    for earning in earnings:
        if not isinstance(earning, dict):
            continue

        symbol = earning.get("symbol")
        if not isinstance(symbol, str) or not symbol or symbol in seen:
            continue

        profile = profiles.get(symbol)
        if not isinstance(profile, dict):
            continue

        market_cap = profile.get("marketCap")
        if isinstance(market_cap, bool) or not isinstance(market_cap, (int, float)):
            continue
        if isinstance(market_cap, float) and not math.isfinite(market_cap):
            continue
        if market_cap < min_market_cap:
            continue

        exchange = profile.get("exchange")
        if not isinstance(exchange, str) or exchange not in FMPClient.US_EXCHANGES:
            continue

        candidates.append(
            {
                "symbol": symbol,
                "company_name": profile.get("companyName", symbol),
                "earnings_date": earning.get("date"),
                "earnings_timing": normalize_timing(earning.get("time")),
                "market_cap": market_cap,
                "sector": profile.get("sector", "N/A"),
                "industry": profile.get("industry", "N/A"),
                "price": profile.get("price", 0),
            }
        )
        seen.add(symbol)

    return candidates


def analyze_stock(daily_prices, earnings_date, timing):
    """Score a single stock across all 5 factors.

    Args:
        daily_prices: List of price dicts (most-recent-first)
        earnings_date: YYYY-MM-DD string
        timing: 'bmo', 'amc', or 'unknown'

    Returns:
        dict with component results and composite score
    """
    gap_result = calculate_gap(daily_prices, earnings_date, timing)
    trend_result = calculate_pre_earnings_trend(daily_prices, earnings_date)
    volume_result = calculate_volume_trend(daily_prices, earnings_date)
    ma200_result = calculate_ma200_position(daily_prices)
    ma50_result = calculate_ma50_position(daily_prices)

    composite = calculate_composite_score(
        gap_score=gap_result["score"],
        trend_score=trend_result["score"],
        volume_score=volume_result["score"],
        ma200_score=ma200_result["score"],
        ma50_score=ma50_result["score"],
    )

    return {
        "gap": gap_result,
        "pre_earnings_trend": trend_result,
        "volume_trend": volume_result,
        "ma200_position": ma200_result,
        "ma50_position": ma50_result,
        "composite": composite,
    }


def apply_entry_filter(results):
    """Apply entry quality filter to exclude poor setups.

    Based on 517-trade backtest analysis (entry_filter.py):
      1. Exclude price < $30: Win Rate 40.6% for $10-$30 range (vs 54.5% baseline)
      2. Exclude gap >= 10% AND score >= 85: Win Rate 33.3% (paradox pattern)
    """
    filtered = []
    for r in results:
        price = r.get("current_price", 0)
        gap_pct = abs(r.get("gap_pct", 0))
        score = r.get("composite_score", 0)

        # Rule 1: Low price band exclusion (< $30)
        if price < 30:
            continue

        # Rule 2: High gap + high score paradox exclusion
        if gap_pct >= 10 and score >= 85:
            continue

        filtered.append(r)
    return filtered


def main():
    parser = argparse.ArgumentParser(
        description="Earnings Trade Analyzer - 5-Factor Post-Earnings Scoring"
    )
    parser.add_argument(
        "--api-key", type=str, default=None, help="FMP API key (or set FMP_API_KEY env var)"
    )
    parser.add_argument(
        "--lookback-days", type=int, default=2, help="Days back for earnings (default: 2)"
    )
    parser.add_argument(
        "--min-market-cap",
        type=float,
        default=500_000_000,
        help="Minimum market cap in dollars (default: 500000000)",
    )
    parser.add_argument("--min-gap", type=float, default=0, help="Minimum gap %% (default: 0)")
    parser.add_argument(
        "--max-api-calls",
        type=int,
        default=200,
        help="API call budget (default: 200)",
    )
    parser.add_argument(
        "--apply-entry-filter",
        action="store_true",
        help="Apply entry quality filter (exclude price < $30, exclude gap>=10%% AND score>=85)",
    )
    parser.add_argument("--top", type=int, default=20, help="Top results to include (default: 20)")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports/",
        help="Output directory (default: reports/)",
    )

    args = parser.parse_args()

    # Initialize FMP client
    try:
        client = FMPClient(api_key=args.api_key, max_api_calls=args.max_api_calls)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print("=" * 60, file=sys.stderr)
    print("Earnings Trade Analyzer - 5-Factor Scoring", file=sys.stderr)
    print("=" * 60, file=sys.stderr)

    # Phase 1: Fetch earnings calendar and profiles
    print("\n--- Phase 1: Fetch Earnings Calendar ---", file=sys.stderr)

    today = datetime.now()
    from_date = (today - timedelta(days=args.lookback_days)).strftime("%Y-%m-%d")
    to_date = today.strftime("%Y-%m-%d")

    print(f"Date range: {from_date} to {to_date}", file=sys.stderr)

    try:
        earnings = client.get_earnings_calendar(from_date, to_date)
    except ApiCallBudgetExceeded as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(earnings, list) or not earnings:
        api_stats = client.get_api_stats()
        reason = classify_empty_calendar(earnings)
        exit_code, message = _ZERO_RESULT_MESSAGES.get(
            reason, (1, f"No candidates found (reason: {reason}).")
        )
        print(f"ZERO_RESULT_REASON={reason}", file=sys.stderr)
        print(
            f"api_stats: budget_remaining={api_stats.get('budget_remaining')} "
            f"rate_limit_reached={api_stats.get('rate_limit_reached')}",
            file=sys.stderr,
        )
        print(message, file=sys.stderr)
        sys.exit(exit_code)

    print(f"Raw earnings announcements: {len(earnings)}", file=sys.stderr)

    # Get unique symbols
    symbols = list(set(e.get("symbol") for e in earnings if e.get("symbol")))
    print(f"Unique symbols: {len(symbols)}", file=sys.stderr)

    # Fetch profiles in batch
    print("Fetching company profiles...", file=sys.stderr)
    try:
        profiles = client.get_company_profiles(symbols)
    except ApiCallBudgetExceeded as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Profiles retrieved: {len(profiles)}", file=sys.stderr)

    # Filter stable profile payloads by market cap and US exchange.
    candidates = select_candidates(earnings, profiles, args.min_market_cap)

    print(f"Candidates after filtering: {len(candidates)}", file=sys.stderr)

    if not candidates:
        api_stats = client.get_api_stats()
        reason = explain_empty_selection(earnings, profiles, args.min_market_cap, api_stats)
        exit_code, message = _ZERO_RESULT_MESSAGES.get(
            reason, (1, f"No candidates found (reason: {reason}).")
        )
        print(f"ZERO_RESULT_REASON={reason}", file=sys.stderr)
        print(message, file=sys.stderr)
        sys.exit(exit_code)

    # Phase 1.5: Budget check
    print("\n--- Phase 1.5: Budget Check ---", file=sys.stderr)
    remaining_calls = args.max_api_calls - client.api_calls_made
    estimated_calls = len(candidates)  # 1 historical price call per candidate

    if estimated_calls > remaining_calls:
        print(
            f"WARNING: Estimated {estimated_calls} calls needed, "
            f"but only {remaining_calls} remaining in budget.",
            file=sys.stderr,
        )
        # Trim candidates by market cap (descending) to fit budget
        candidates.sort(key=lambda x: x.get("market_cap", 0), reverse=True)
        candidates = candidates[:remaining_calls]
        print(f"Trimmed to {len(candidates)} candidates (by market cap).", file=sys.stderr)
    else:
        print(
            f"Budget OK: {estimated_calls} calls needed, {remaining_calls} remaining.",
            file=sys.stderr,
        )

    # Phase 2: Fetch historical prices
    print("\n--- Phase 2: Fetch Historical Prices ---", file=sys.stderr)

    results = []
    for i, candidate in enumerate(candidates):
        symbol = candidate["symbol"]
        print(
            f"  [{i + 1}/{len(candidates)}] Fetching {symbol}...",
            file=sys.stderr,
            end="",
        )

        try:
            daily_prices = client.get_historical_prices(symbol, days=250)
        except ApiCallBudgetExceeded:
            print(
                f"\nWARNING: API budget exceeded at {symbol}. "
                f"Proceeding with {len(results)} results.",
                file=sys.stderr,
            )
            break

        if not daily_prices or len(daily_prices) < 50:
            print(
                f" SKIP (insufficient data: {len(daily_prices) if daily_prices else 0} days)",
                file=sys.stderr,
            )
            continue

        # Phase 3: Score all 5 factors
        analysis = analyze_stock(
            daily_prices,
            candidate["earnings_date"],
            candidate["earnings_timing"],
        )

        composite = analysis["composite"]
        gap_pct = analysis["gap"]["gap_pct"]

        # Apply min gap filter
        if abs(gap_pct) < args.min_gap:
            print(f" SKIP (gap {gap_pct:.1f}% < min {args.min_gap}%)", file=sys.stderr)
            continue

        current_price = daily_prices[0]["close"] if daily_prices else candidate["price"]

        result = {
            "symbol": symbol,
            "company_name": candidate["company_name"],
            "earnings_date": candidate["earnings_date"],
            "earnings_timing": candidate["earnings_timing"],
            "gap_pct": gap_pct,
            "composite_score": composite["composite_score"],
            "grade": composite["grade"],
            "grade_description": composite["grade_description"],
            "guidance": composite["guidance"],
            "weakest_component": composite["weakest_component"],
            "strongest_component": composite["strongest_component"],
            "component_breakdown": composite["component_breakdown"],
            "current_price": round(current_price, 2),
            "market_cap": candidate["market_cap"],
            "sector": candidate["sector"],
            "industry": candidate["industry"],
            "components": {
                "gap_size": analysis["gap"],
                "pre_earnings_trend": analysis["pre_earnings_trend"],
                "volume_trend": analysis["volume_trend"],
                "ma200_position": analysis["ma200_position"],
                "ma50_position": analysis["ma50_position"],
            },
        }
        results.append(result)
        print(
            f" Grade {composite['grade']} (score: {composite['composite_score']:.1f})",
            file=sys.stderr,
        )

    print(f"\nScored {len(results)} stocks.", file=sys.stderr)

    # Apply entry quality filter if requested
    all_results = results[:]
    if args.apply_entry_filter:
        results = apply_entry_filter(results)
        print(f"After entry filter: {len(results)} stocks.", file=sys.stderr)
        all_results = results[:]

    # Sort by composite score descending
    results.sort(key=lambda x: x.get("composite_score", 0), reverse=True)
    all_results.sort(key=lambda x: x.get("composite_score", 0), reverse=True)

    # Take top N
    top_results = results[: args.top]

    # Phase 4: Generate reports
    print("\n--- Phase 4: Generate Reports ---", file=sys.stderr)

    api_stats = client.get_api_stats()
    metadata = {
        "generated_at": datetime.now().isoformat(),
        "generator": "earnings-trade-analyzer",
        "generator_version": "1.0.0",
        "lookback_days": args.lookback_days,
        "total_screened": len(all_results),
        "min_market_cap": args.min_market_cap,
        "min_gap": args.min_gap,
        "entry_filter_applied": args.apply_entry_filter,
        "api_stats": api_stats,
    }

    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    json_path = os.path.join(args.output_dir, f"earnings_trade_analyzer_{timestamp}.json")
    md_path = os.path.join(args.output_dir, f"earnings_trade_analyzer_{timestamp}.md")

    generate_json_report(top_results, metadata, json_path, all_results=all_results)
    generate_markdown_report(top_results, metadata, md_path, all_results=all_results)

    print(f"JSON report: {json_path}", file=sys.stderr)
    print(f"Markdown report: {md_path}", file=sys.stderr)
    print(
        f"API calls used: {api_stats['api_calls_made']}/{api_stats['max_api_calls']}",
        file=sys.stderr,
    )
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
