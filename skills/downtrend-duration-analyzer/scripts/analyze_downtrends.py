#!/usr/bin/env python3
"""
Downtrend Duration Analyzer

Analyzes historical price data to identify downtrend periods (peak-to-trough)
and computes duration statistics segmented by sector and market cap.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

# Market cap tier thresholds (in billions USD)
MARKET_CAP_TIERS = {
    "Mega": 200_000_000_000,  # >= $200B
    "Large": 10_000_000_000,  # $10B - $200B
    "Mid": 2_000_000_000,  # $2B - $10B
    "Small": 0,  # < $2B
}

# Default sectors for analysis
DEFAULT_SECTORS = [
    "Technology",
    "Healthcare",
    "Financial Services",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Industrials",
    "Energy",
    "Basic Materials",
    "Utilities",
    "Real Estate",
    "Communication Services",
]


def get_api_key(api_key_arg: str | None) -> str:
    """Get FMP API key from argument or environment variable."""
    if api_key_arg:
        return api_key_arg
    api_key = os.environ.get("FMP_API_KEY")
    if not api_key:
        print(
            "Error: FMP API key required. Set FMP_API_KEY environment variable or use --api-key",
            file=sys.stderr,
        )
        sys.exit(1)
    return api_key


def get_market_cap_tier(market_cap: float | None) -> str:
    """Classify market cap into tier."""
    if market_cap is None:
        return "Unknown"
    if market_cap >= MARKET_CAP_TIERS["Mega"]:
        return "Mega"
    elif market_cap >= MARKET_CAP_TIERS["Large"]:
        return "Large"
    elif market_cap >= MARKET_CAP_TIERS["Mid"]:
        return "Mid"
    else:
        return "Small"


def fetch_stock_list(api_key: str, sector: str | None = None) -> list[dict]:
    """Fetch list of stocks, optionally filtered by sector."""
    url = f"https://financialmodelingprep.com/api/v3/stock-screener?apikey={api_key}"
    if sector:
        url += f"&sector={sector.replace(' ', '%20')}"
    url += "&isActivelyTrading=true&limit=500"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching stock list: {e}", file=sys.stderr)
        return []


def fetch_historical_prices(
    api_key: str, symbol: str, from_date: str, to_date: str
) -> pd.DataFrame:
    """Fetch historical daily prices for a symbol."""
    url = (
        f"https://financialmodelingprep.com/api/v3/historical-price-full/{symbol}"
        f"?from={from_date}&to={to_date}&apikey={api_key}"
    )

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "historical" not in data:
            return pd.DataFrame()

        df = pd.DataFrame(data["historical"])
        df["date"] = pd.to_datetime(df["date"])
        df = df.sort_values("date").reset_index(drop=True)
        return df[["date", "open", "high", "low", "close", "volume"]]
    except requests.RequestException as e:
        print(f"Error fetching prices for {symbol}: {e}", file=sys.stderr)
        return pd.DataFrame()


def detect_peaks_troughs(
    prices: pd.DataFrame, peak_window: int = 20, trough_window: int = 20
) -> tuple[list[int], list[int]]:
    """
    Detect local peaks and troughs using rolling window.

    Returns indices of peaks and troughs in the price dataframe.
    """
    closes = prices["close"].values
    n = len(closes)
    peaks = []
    troughs = []

    for i in range(peak_window, n - peak_window):
        window_start = i - peak_window
        window_end = i + peak_window + 1
        window = closes[window_start:window_end]

        # Peak: highest in window
        if closes[i] == np.max(window):
            peaks.append(i)

        # Trough: lowest in window
        if closes[i] == np.min(window):
            troughs.append(i)

    return peaks, troughs


def find_downtrends(
    prices: pd.DataFrame,
    peaks: list[int],
    troughs: list[int],
    min_depth_pct: float = 5.0,
    min_duration_days: int = 3,
) -> list[dict]:
    """
    Identify downtrend periods from peaks to subsequent troughs.

    Returns list of downtrend dictionaries with duration and depth.
    """
    downtrends = []
    closes = prices["close"].values
    dates = prices["date"].values

    for peak_idx in peaks:
        peak_price = closes[peak_idx]
        peak_date = dates[peak_idx]

        # Find the next trough after this peak
        subsequent_troughs = [t for t in troughs if t > peak_idx]
        if not subsequent_troughs:
            continue

        # Find the lowest trough before the next peak
        next_peaks = [p for p in peaks if p > peak_idx]
        end_idx = next_peaks[0] if next_peaks else len(closes)

        valid_troughs = [t for t in subsequent_troughs if t < end_idx]
        if not valid_troughs:
            continue

        # Find the deepest trough
        trough_idx = min(valid_troughs, key=lambda t: closes[t])
        trough_price = closes[trough_idx]
        trough_date = dates[trough_idx]

        # Calculate depth and duration
        depth_pct = ((trough_price - peak_price) / peak_price) * 100
        duration_days = int(trough_idx - peak_idx)

        # Apply filters
        if abs(depth_pct) < min_depth_pct:
            continue
        if duration_days < min_duration_days:
            continue

        downtrends.append(
            {
                "peak_idx": peak_idx,
                "trough_idx": trough_idx,
                "peak_date": pd.Timestamp(peak_date).strftime("%Y-%m-%d"),
                "trough_date": pd.Timestamp(trough_date).strftime("%Y-%m-%d"),
                "peak_price": float(peak_price),
                "trough_price": float(trough_price),
                "duration_days": duration_days,
                "depth_pct": round(depth_pct, 2),
            }
        )

    return downtrends


def analyze_symbol(
    api_key: str,
    symbol: str,
    sector: str,
    market_cap: float | None,
    from_date: str,
    to_date: str,
    peak_window: int,
    trough_window: int,
    min_depth_pct: float,
) -> list[dict]:
    """Analyze downtrends for a single symbol."""
    prices = fetch_historical_prices(api_key, symbol, from_date, to_date)

    if prices.empty or len(prices) < peak_window * 2 + 1:
        return []

    peaks, troughs = detect_peaks_troughs(prices, peak_window, trough_window)

    if not peaks or not troughs:
        return []

    downtrends = find_downtrends(prices, peaks, troughs, min_depth_pct)

    market_cap_tier = get_market_cap_tier(market_cap)

    # Add metadata to each downtrend
    for dt in downtrends:
        dt["symbol"] = symbol
        dt["sector"] = sector
        dt["market_cap_tier"] = market_cap_tier

    return downtrends


def compute_statistics(downtrends: list[dict]) -> dict[str, Any]:
    """Compute summary statistics from downtrend list."""
    if not downtrends:
        return {
            "total_downtrends": 0,
            "median_duration_days": 0,
            "mean_duration_days": 0,
            "p25_duration_days": 0,
            "p75_duration_days": 0,
            "p90_duration_days": 0,
        }

    durations = [dt["duration_days"] for dt in downtrends]
    return {
        "total_downtrends": len(downtrends),
        "median_duration_days": int(np.median(durations)),
        "mean_duration_days": round(np.mean(durations), 1),
        "p25_duration_days": int(np.percentile(durations, 25)),
        "p75_duration_days": int(np.percentile(durations, 75)),
        "p90_duration_days": int(np.percentile(durations, 90)),
    }


def group_statistics(downtrends: list[dict], group_key: str) -> dict[str, dict[str, Any]]:
    """Compute statistics grouped by a key (sector or market_cap_tier)."""
    groups: dict[str, list[dict]] = {}

    for dt in downtrends:
        key = dt.get(group_key, "Unknown")
        if key not in groups:
            groups[key] = []
        groups[key].append(dt)

    result = {}
    for key, group_downtrends in groups.items():
        durations = [dt["duration_days"] for dt in group_downtrends]
        result[key] = {
            "count": len(group_downtrends),
            "median_days": int(np.median(durations)),
            "mean_days": round(np.mean(durations), 1),
        }

    return result


def generate_markdown_report(analysis_result: dict[str, Any], output_path: Path) -> None:
    """Generate markdown report from analysis results."""
    params = analysis_result["parameters"]
    summary = analysis_result["summary"]
    by_sector = analysis_result.get("by_sector", {})
    by_market_cap = analysis_result.get("by_market_cap", {})

    lines = [
        "# Downtrend Duration Analysis",
        "",
        f"**Date**: {analysis_result['analysis_date'][:10]}",
        f"**Lookback**: {params['lookback_years']} years",
    ]

    if params.get("sector_filter"):
        lines.append(f"**Sector**: {params['sector_filter']}")

    lines.extend(
        [
            "",
            "## Summary Statistics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Downtrends | {summary['total_downtrends']:,} |",
            f"| Median Duration | {summary['median_duration_days']} days |",
            f"| Mean Duration | {summary['mean_duration_days']} days |",
            f"| 25th Percentile | {summary['p25_duration_days']} days |",
            f"| 75th Percentile | {summary['p75_duration_days']} days |",
            f"| 90th Percentile | {summary['p90_duration_days']} days |",
            "",
        ]
    )

    if by_market_cap:
        lines.extend(
            [
                "## By Market Cap Tier",
                "",
                "| Tier | Count | Median | Mean |",
                "|------|-------|--------|------|",
            ]
        )
        tier_order = ["Mega", "Large", "Mid", "Small"]
        for tier in tier_order:
            if tier in by_market_cap:
                stats = by_market_cap[tier]
                lines.append(
                    f"| {tier} | {stats['count']} | {stats['median_days']} days | {stats['mean_days']} days |"
                )
        lines.append("")

    if by_sector:
        lines.extend(
            [
                "## By Sector",
                "",
                "| Sector | Count | Median | Mean |",
                "|--------|-------|--------|------|",
            ]
        )
        for sector, stats in sorted(by_sector.items(), key=lambda x: x[1]["median_days"]):
            lines.append(
                f"| {sector} | {stats['count']} | {stats['median_days']} days | {stats['mean_days']} days |"
            )
        lines.append("")

    lines.extend(
        [
            "## Key Insights",
            "",
            "1. **Percentile Guidance**: Use P50 (median) for typical expectations; P75-P90 for conservative planning",
            "2. **Market Cap Effect**: Larger companies typically recover faster from corrections",
            "3. **Sector Variation**: Defensive sectors show shorter corrections than cyclical sectors",
            "",
        ]
    )

    output_path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze historical downtrend durations by sector and market cap"
    )
    parser.add_argument(
        "--api-key",
        help="FMP API key (or set FMP_API_KEY env var)",
    )
    parser.add_argument(
        "--sector",
        help="Filter to specific sector (e.g., 'Technology')",
    )
    parser.add_argument(
        "--lookback-years",
        type=int,
        default=5,
        help="Years of historical data to analyze (default: 5)",
    )
    parser.add_argument(
        "--peak-window",
        type=int,
        default=20,
        help="Rolling window size for peak detection (default: 20)",
    )
    parser.add_argument(
        "--trough-window",
        type=int,
        default=20,
        help="Rolling window size for trough detection (default: 20)",
    )
    parser.add_argument(
        "--min-depth",
        type=float,
        default=5.0,
        help="Minimum depth percentage for a downtrend (default: 5.0)",
    )
    parser.add_argument(
        "--max-stocks",
        type=int,
        default=100,
        help="Maximum stocks to analyze (default: 100)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="reports",
        help="Output directory for reports (default: reports)",
    )

    args = parser.parse_args()

    api_key = get_api_key(args.api_key)

    # Calculate date range
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=365 * args.lookback_years)).strftime("%Y-%m-%d")

    print(f"Analyzing downtrends from {from_date} to {to_date}")

    # Get stock list
    stocks = fetch_stock_list(api_key, args.sector)
    if not stocks:
        print("No stocks found matching criteria", file=sys.stderr)
        sys.exit(1)

    stocks = stocks[: args.max_stocks]
    print(f"Analyzing {len(stocks)} stocks...")

    # Analyze each stock
    all_downtrends: list[dict] = []
    for i, stock in enumerate(stocks):
        symbol = stock.get("symbol", "")
        sector = stock.get("sector", "Unknown")
        market_cap = stock.get("marketCap")

        if i % 10 == 0:
            print(f"  Progress: {i}/{len(stocks)} stocks processed")

        downtrends = analyze_symbol(
            api_key,
            symbol,
            sector,
            market_cap,
            from_date,
            to_date,
            args.peak_window,
            args.trough_window,
            args.min_depth,
        )
        all_downtrends.extend(downtrends)

    print(f"Found {len(all_downtrends)} downtrend periods")

    # Compute statistics
    summary = compute_statistics(all_downtrends)
    by_sector = group_statistics(all_downtrends, "sector")
    by_market_cap = group_statistics(all_downtrends, "market_cap_tier")

    # Build result
    result = {
        "schema_version": "1.0",
        "analysis_date": datetime.now().isoformat() + "Z",
        "parameters": {
            "lookback_years": args.lookback_years,
            "sector_filter": args.sector,
            "peak_window": args.peak_window,
            "trough_window": args.trough_window,
            "min_depth_pct": args.min_depth,
        },
        "summary": summary,
        "by_sector": by_sector,
        "by_market_cap": by_market_cap,
        "downtrends": all_downtrends,
    }

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # Write JSON
    json_path = output_dir / f"downtrend_analysis_{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"JSON report saved to: {json_path}")

    # Write Markdown
    md_path = output_dir / f"downtrend_analysis_{timestamp}.md"
    generate_markdown_report(result, md_path)
    print(f"Markdown report saved to: {md_path}")


if __name__ == "__main__":
    main()
