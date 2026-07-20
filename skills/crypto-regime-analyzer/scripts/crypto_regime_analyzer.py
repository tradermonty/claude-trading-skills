#!/usr/bin/env python3
"""
Crypto Regime Analyzer - Main Orchestrator

Computes a 6-component crypto market regime composite (0-100, 100 = risk-on)
from free, keyless public data, and writes JSON + Markdown reports.

Usage:
  # Live fetch (CoinGecko + Binance public endpoints, no API keys)
  python3 crypto_regime_analyzer.py --output-dir reports/2026-07-01

  # Offline mode from a snapshot file (schema in references/)
  python3 crypto_regime_analyzer.py --input-json snapshot.json --output-dir reports/

Exit codes: 0 = success, 1 = fatal error (no BTC data / bad input).
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calculators.alt_breadth_calculator import calculate_alt_breadth
from calculators.btc_trend_calculator import calculate_btc_trend
from calculators.dominance_calculator import calculate_dominance_regime
from calculators.drawdown_vol_calculator import calculate_drawdown_vol
from calculators.funding_calculator import calculate_funding_regime
from calculators.momentum_thrust_calculator import calculate_momentum_thrust
from data_client import DataClient, load_snapshot_from_json, validate_snapshot
from report_generator import generate_json_report, generate_markdown_report, print_summary
from scorer import calculate_composite_score

BTC_CONSTRUCTIVE_THRESHOLD = 60


def run_analysis(snapshot: dict) -> dict:
    """Run all six components + composite over a snapshot."""
    validate_snapshot(snapshot)
    series = snapshot["series"]
    btc_closes = series.get("BTC", [])
    alt_series = {sym: s for sym, s in series.items() if sym != "BTC"}

    btc_trend = calculate_btc_trend(btc_closes)
    btc_trend_up = (
        btc_trend.get("data_available", False) and btc_trend["score"] >= BTC_CONSTRUCTIVE_THRESHOLD
    )

    components = {
        "btc_trend": btc_trend,
        "alt_breadth": calculate_alt_breadth(alt_series),
        "dominance": calculate_dominance_regime(snapshot.get("dominance_series", []), btc_trend_up),
        "funding": calculate_funding_regime(snapshot.get("funding", {})),
        "drawdown_vol": calculate_drawdown_vol(btc_closes),
        "momentum_thrust": calculate_momentum_thrust(series),
    }

    return {
        "metadata": {
            "as_of": snapshot.get("as_of", "unknown"),
            "universe_size": len(series),
        },
        "components": components,
        "composite": calculate_composite_score(components),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Crypto market regime analyzer")
    parser.add_argument("--input-json", help="Offline snapshot file (skips all fetches)")
    parser.add_argument("--output-dir", default="reports", help="Report output directory")
    parser.add_argument("--cache-dir", default=".crypto_regime_cache", help="Fetch cache dir")
    parser.add_argument("--top-n", type=int, default=20, help="Universe size (live mode)")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress logging")
    args = parser.parse_args()

    try:
        if args.input_json:
            snapshot = load_snapshot_from_json(args.input_json)
        else:
            client = DataClient(args.cache_dir, top_n=args.top_n, quiet=args.quiet)
            snapshot = client.build_snapshot()
    except Exception as exc:
        print(f"ERROR: could not build data snapshot: {exc}", file=sys.stderr)
        return 1

    if not snapshot.get("series", {}).get("BTC"):
        print("ERROR: snapshot contains no BTC series", file=sys.stderr)
        return 1

    analysis = run_analysis(snapshot)

    os.makedirs(args.output_dir, exist_ok=True)
    generate_json_report(analysis, os.path.join(args.output_dir, "crypto_regime.json"))
    generate_markdown_report(analysis, os.path.join(args.output_dir, "crypto_regime.md"))
    print_summary(analysis)
    return 0


if __name__ == "__main__":
    sys.exit(main())
