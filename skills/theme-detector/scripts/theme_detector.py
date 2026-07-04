#!/usr/bin/env python3
"""
Theme Detector - Main Orchestrator

Detects trending market themes (bullish and bearish) by combining:
- FINVIZ industry/sector performance data
- yfinance ETF volume and stock metrics
- Monty's Uptrend Ratio Dashboard data

Outputs: JSON + Markdown report saved to reports/ directory.

Usage:
    python3 theme_detector.py --output-dir reports/
    python3 theme_detector.py --fmp-api-key $FMP_API_KEY --finviz-api-key $FINVIZ_API_KEY
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

# Ensure scripts directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calculators.heat_calculator import (
    breadth_signal_score,
    calculate_theme_heat_detailed,
    momentum_strength_score,
    uptrend_signal_score,
    volume_intensity_score,
)
from calculators.industry_ranker import get_top_bottom_industries, rank_industries
from calculators.lifecycle_calculator import (
    calculate_lifecycle_maturity_detailed,
    classify_stage,
    estimate_duration_score,
    etf_proliferation_score,
    extremity_clustering_score,
    price_extreme_saturation_score,
    valuation_premium_score,
)
from calculators.theme_classifier import classify_themes
from leadership import aggregate_leadership, blend_theme_heat, load_scan_hits
from report_generator import generate_json_report, generate_markdown_report, save_reports
from scorer import (
    calculate_confidence,
    determine_data_mode,
    score_theme,
)
from theme_history import (
    append_observations,
    build_observation,
    compute_history_metrics,
    load_history,
    resolve_run_date,
    save_history,
)

# Heavy-dependency modules (pandas/numpy/yfinance/finvizfinance) are imported
# lazily inside main() to allow lightweight helpers like _get_representative_stocks
# to be imported without triggering sys.exit(1) when pandas is absent.


# ---------------------------------------------------------------------------
# Industry-to-sector mapping (FINVIZ industry names -> sector)
# ---------------------------------------------------------------------------
INDUSTRY_TO_SECTOR: dict[str, str] = {
    # Technology
    "Semiconductors": "Technology",
    "Semiconductor Equipment & Materials": "Technology",
    "Software - Application": "Technology",
    "Software - Infrastructure": "Technology",
    "Information Technology Services": "Technology",
    "Computer Hardware": "Technology",
    "Electronic Components": "Technology",
    "Electronics & Computer Distribution": "Technology",
    "Scientific & Technical Instruments": "Technology",
    "Communication Equipment": "Technology",
    "Consumer Electronics": "Technology",
    # Healthcare
    "Biotechnology": "Healthcare",
    "Drug Manufacturers - General": "Healthcare",
    "Drug Manufacturers - Specialty & Generic": "Healthcare",
    "Medical Devices": "Healthcare",
    "Medical Instruments & Supplies": "Healthcare",
    "Diagnostics & Research": "Healthcare",
    "Healthcare Plans": "Healthcare",
    "Health Information Services": "Healthcare",
    "Medical Care Facilities": "Healthcare",
    "Pharmaceutical Retailers": "Healthcare",
    "Medical Distribution": "Healthcare",
    # Financial
    "Banks - Diversified": "Financial",
    "Banks - Regional": "Financial",
    "Insurance - Life": "Financial",
    "Insurance - Property & Casualty": "Financial",
    "Insurance - Diversified": "Financial",
    "Insurance - Specialty": "Financial",
    "Insurance Brokers": "Financial",
    "Asset Management": "Financial",
    "Capital Markets": "Financial",
    "Financial Data & Stock Exchanges": "Financial",
    "Credit Services": "Financial",
    "Mortgage Finance": "Financial",
    "Financial Conglomerates": "Financial",
    "Shell Companies": "Financial",
    # Consumer Cyclical
    "Auto Manufacturers": "Consumer Cyclical",
    "Auto Parts": "Consumer Cyclical",
    "Auto & Truck Dealerships": "Consumer Cyclical",
    "Recreational Vehicles": "Consumer Cyclical",
    "Furnishings, Fixtures & Appliances": "Consumer Cyclical",
    "Residential Construction": "Consumer Cyclical",
    "Textile Manufacturing": "Consumer Cyclical",
    "Apparel Manufacturing": "Consumer Cyclical",
    "Footwear & Accessories": "Consumer Cyclical",
    "Packaging & Containers": "Consumer Cyclical",
    "Personal Services": "Consumer Cyclical",
    "Restaurants": "Consumer Cyclical",
    "Apparel Retail": "Consumer Cyclical",
    "Department Stores": "Consumer Cyclical",
    "Home Improvement Retail": "Consumer Cyclical",
    "Luxury Goods": "Consumer Cyclical",
    "Internet Retail": "Consumer Cyclical",
    "Specialty Retail": "Consumer Cyclical",
    "Gambling": "Consumer Cyclical",
    "Leisure": "Consumer Cyclical",
    "Lodging": "Consumer Cyclical",
    "Resorts & Casinos": "Consumer Cyclical",
    "Travel Services": "Consumer Cyclical",
    # Consumer Defensive
    "Beverages - Non-Alcoholic": "Consumer Defensive",
    "Beverages - Brewers": "Consumer Defensive",
    "Beverages - Wineries & Distilleries": "Consumer Defensive",
    "Confectioners": "Consumer Defensive",
    "Farm Products": "Consumer Defensive",
    "Household & Personal Products": "Consumer Defensive",
    "Packaged Foods": "Consumer Defensive",
    "Education & Training Services": "Consumer Defensive",
    "Discount Stores": "Consumer Defensive",
    "Food Distribution": "Consumer Defensive",
    "Grocery Stores": "Consumer Defensive",
    "Tobacco": "Consumer Defensive",
    # Industrials
    "Aerospace & Defense": "Industrials",
    "Airlines": "Industrials",
    "Building Products & Equipment": "Industrials",
    "Business Equipment & Supplies": "Industrials",
    "Conglomerates": "Industrials",
    "Consulting Services": "Industrials",
    "Electrical Equipment & Parts": "Industrials",
    "Engineering & Construction": "Industrials",
    "Farm & Heavy Construction Machinery": "Industrials",
    "Industrial Distribution": "Industrials",
    "Infrastructure Operations": "Industrials",
    "Integrated Freight & Logistics": "Industrials",
    "Marine Shipping": "Industrials",
    "Metal Fabrication": "Industrials",
    "Pollution & Treatment Controls": "Industrials",
    "Railroads": "Industrials",
    "Rental & Leasing Services": "Industrials",
    "Security & Protection Services": "Industrials",
    "Specialty Business Services": "Industrials",
    "Specialty Industrial Machinery": "Industrials",
    "Staffing & Employment Services": "Industrials",
    "Tools & Accessories": "Industrials",
    "Trucking": "Industrials",
    "Waste Management": "Industrials",
    # Energy
    "Oil & Gas E&P": "Energy",
    "Oil & Gas Equipment & Services": "Energy",
    "Oil & Gas Integrated": "Energy",
    "Oil & Gas Midstream": "Energy",
    "Oil & Gas Refining & Marketing": "Energy",
    "Oil & Gas Drilling": "Energy",
    "Thermal Coal": "Energy",
    "Uranium": "Energy",
    "Solar": "Energy",
    # Basic Materials
    "Gold": "Basic Materials",
    "Silver": "Basic Materials",
    "Aluminum": "Basic Materials",
    "Copper": "Basic Materials",
    "Steel": "Basic Materials",
    "Other Industrial Metals & Mining": "Basic Materials",
    "Other Precious Metals & Mining": "Basic Materials",
    "Coking Coal": "Basic Materials",
    "Lumber & Wood Production": "Basic Materials",
    "Paper & Paper Products": "Basic Materials",
    "Chemicals": "Basic Materials",
    "Specialty Chemicals": "Basic Materials",
    "Agricultural Inputs": "Basic Materials",
    "Building Materials": "Basic Materials",
    # Communication Services
    "Telecom Services": "Communication Services",
    "Advertising Agencies": "Communication Services",
    "Publishing": "Communication Services",
    "Broadcasting": "Communication Services",
    "Entertainment": "Communication Services",
    "Internet Content & Information": "Communication Services",
    "Electronic Gaming & Multimedia": "Communication Services",
    # Real Estate
    "REIT - Diversified": "Real Estate",
    "REIT - Healthcare Facilities": "Real Estate",
    "REIT - Hotel & Motel": "Real Estate",
    "REIT - Industrial": "Real Estate",
    "REIT - Mortgage": "Real Estate",
    "REIT - Office": "Real Estate",
    "REIT - Residential": "Real Estate",
    "REIT - Retail": "Real Estate",
    "REIT - Specialty": "Real Estate",
    "Real Estate - Development": "Real Estate",
    "Real Estate - Diversified": "Real Estate",
    "Real Estate Services": "Real Estate",
    # Utilities
    "Utilities - Diversified": "Utilities",
    "Utilities - Independent Power Producers": "Utilities",
    "Utilities - Regulated Electric": "Utilities",
    "Utilities - Regulated Gas": "Utilities",
    "Utilities - Regulated Water": "Utilities",
    "Utilities - Renewable": "Utilities",
}


# ---------------------------------------------------------------------------
# Theme configuration is loaded from YAML / inline fallback via config_loader.
# DEFAULT_THEMES_CONFIG and ETF_CATALOG live in default_theme_config.py
# to avoid circular imports.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect trending market themes from FINVIZ industry data"
    )
    parser.add_argument(
        "--fmp-api-key",
        default=os.environ.get("FMP_API_KEY"),
        help="Financial Modeling Prep API key (env: FMP_API_KEY)",
    )
    parser.add_argument(
        "--finviz-api-key",
        default=os.environ.get("FINVIZ_API_KEY"),
        help="FINVIZ Elite API key (env: FINVIZ_API_KEY)",
    )
    parser.add_argument(
        "--finviz-mode",
        choices=["public", "elite"],
        default=None,
        help="FINVIZ mode (auto-detected if not specified)",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/",
        help="Output directory for reports (default: reports/)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=3,
        help="Number of top themes to show in detail (default: 3)",
    )
    parser.add_argument(
        "--max-themes",
        type=int,
        default=10,
        help="Maximum themes to analyze (default: 10)",
    )
    parser.add_argument(
        "--max-stocks-per-theme",
        type=int,
        default=10,
        help="Maximum stocks per theme (default: 10)",
    )
    parser.add_argument(
        "--themes-config",
        default=None,
        help="Path to custom themes.yaml (default: bundled)",
    )
    parser.add_argument(
        "--discover-themes",
        action="store_true",
        default=False,
        help="Enable automatic theme discovery for unmatched industries",
    )
    parser.add_argument(
        "--dynamic-stocks",
        action="store_true",
        default=False,
        help="Enable dynamic stock selection via FINVIZ screener (default: off)",
    )
    parser.add_argument(
        "--dynamic-min-cap",
        choices=["micro", "small", "mid"],
        default="small",
        help="Minimum market cap for dynamic stock selection (default: small=$300mln+)",
    )
    parser.add_argument(
        "--scan-hits",
        default=None,
        help="Optional JSON/JSONL/CSV stock leadership scan rows or hits",
    )
    parser.add_argument(
        "--history-file",
        default=None,
        help="Theme history JSON path (default: <output-dir>/theme_detector_history.json)",
    )
    parser.add_argument(
        "--no-history-update",
        action="store_true",
        default=False,
        help="Read history metrics without writing the current run",
    )
    parser.add_argument(
        "--as-of-date",
        default=None,
        help="Run date for deterministic history/scan processing (YYYY-MM-DD)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _add_sector_info(industries: list[dict]) -> list[dict]:
    """Add sector field to each industry dict from INDUSTRY_TO_SECTOR mapping."""
    for ind in industries:
        name = ind.get("name", "")
        ind["sector"] = INDUSTRY_TO_SECTOR.get(name, "Unknown")
    return industries


def _convert_perf_to_pct(industries: list[dict]) -> list[dict]:
    """Convert FINVIZ decimal performance values to percentage.

    finvizfinance returns 0.05 for 5%. Our calculators expect 5.0.
    """
    perf_keys = ["perf_1w", "perf_1m", "perf_3m", "perf_6m", "perf_1y", "perf_ytd"]
    for ind in industries:
        for key in perf_keys:
            val = ind.get(key)
            if val is not None:
                ind[key] = val * 100.0
    return industries


def _get_representative_stocks(
    theme: dict,
    selector,  # Optional[RepresentativeStockSelector]
    max_stocks: int,
) -> tuple[list[str], list[dict]]:
    """Get representative stocks and metadata for a theme.

    When selector is provided (--dynamic-stocks), uses FINVIZ/FMP fallback chain.
    Otherwise falls back to static_stocks from config.

    Returns:
        (tickers, stock_details)
        tickers: ["NVDA", "AVGO", ...] (backward compatible)
        stock_details: [{symbol, source, market_cap, matched_industries,
                         reasons, composite_score}, ...]
    """
    if selector is not None:
        details = selector.select_stocks(theme, max_stocks)
        tickers = [d["symbol"] for d in details]
        return tickers, details

    # Static fallback (selector is None = --dynamic-stocks not set)
    static = theme.get("static_stocks", [])[:max_stocks]
    details = [
        {
            "symbol": s,
            "source": "static",
            "market_cap": 0,
            "matched_industries": [],
            "reasons": ["Static config"],
            "composite_score": 0,
        }
        for s in static
    ]
    return static, details


def detect_divergence(heat_breakdown: dict, direction: str) -> dict | None:
    """Detect divergence between price momentum and breadth signals."""
    momentum = heat_breakdown.get("momentum_strength")
    uptrend = heat_breakdown.get("uptrend_signal")
    if momentum is None or uptrend is None:
        return None
    gap = momentum - uptrend
    if abs(gap) < 25:
        return None
    if gap > 0:
        return {
            "type": "narrow_rally",
            "gap": round(gap, 1),
            "description": "Price momentum strong but breadth weak — concentrated/fragile move",
        }
    else:
        desc = (
            "Breadth improving ahead of price — potential reversal candidate"
            if direction == "bearish"
            else "Breadth improving ahead of price — potential acceleration candidate"
        )
        return {
            "type": "internal_recovery",
            "gap": round(abs(gap), 1),
            "description": desc,
        }


def _calculate_breadth_ratio(theme: dict) -> float | None:
    """Estimate breadth ratio from theme's matching industries.

    For bullish: ratio of industries with positive weighted_return.
    For bearish: ratio of industries with negative weighted_return.
    """
    industries = theme.get("matching_industries", [])
    if not industries:
        return None

    is_bearish = theme.get("direction") == "bearish"
    if is_bearish:
        count = sum(1 for ind in industries if ind.get("weighted_return", 0) < 0)
    else:
        count = sum(1 for ind in industries if ind.get("weighted_return", 0) > 0)

    return count / len(industries)


def _get_theme_uptrend_data(theme: dict, sector_uptrend: dict) -> list[dict]:
    """Build sector_data for uptrend_signal_score from theme's sector weights.

    Maps theme sectors to uptrend data with weights.
    """
    sector_weights = theme.get("sector_weights", {})
    if not sector_weights or not sector_uptrend:
        return []

    sector_data = []
    for sector_name, weight in sector_weights.items():
        uptrend_entry = sector_uptrend.get(sector_name)
        if uptrend_entry and uptrend_entry.get("ratio") is not None:
            sector_data.append(
                {
                    "sector": sector_name,
                    "ratio": uptrend_entry["ratio"],
                    "ma_10": uptrend_entry.get("ma_10") or 0,
                    "slope": uptrend_entry.get("slope") or 0,
                    "weight": weight,
                }
            )

    return sector_data


def _get_theme_weighted_return(theme: dict) -> float:
    """Calculate aggregate weighted return for a theme from its industries."""
    industries = theme.get("matching_industries", [])
    if not industries:
        return 0.0

    returns = [ind.get("weighted_return", 0.0) for ind in industries]
    return sum(returns) / len(returns)


def _resolve_output_dir(output_dir: str) -> str:
    """Resolve output directory relative to repo root if needed."""
    if os.path.isabs(output_dir):
        return output_dir
    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    return os.path.join(repo_root, output_dir)


def _round_optional(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


def _coverage_penalties(
    heat_detail: dict, maturity_detail: dict, scan_hits_available: bool
) -> list[str]:
    penalties = []
    if heat_detail.get("coverage", 0.0) < 0.75:
        penalties.append("heat_low_coverage")
    if maturity_detail.get("coverage", 0.0) < 0.60:
        penalties.append("lifecycle_low_coverage")
    if not scan_hits_available:
        penalties.append("leadership_scan_hits_missing")
    return penalties


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
def main():
    # Lazy imports: these modules depend on pandas/numpy/yfinance/finvizfinance
    # and are only needed at runtime, not when importing helpers for testing.
    from calculators.theme_classifier import deduplicate_themes, enrich_vertical_themes
    from config_loader import load_themes_config
    from etf_scanner import ETFScanner
    from finviz_performance_client import cap_outlier_performances, get_industry_performance
    from uptrend_client import fetch_sector_uptrend_data, is_data_stale

    args = parse_args()
    run_date = resolve_run_date(args.as_of_date)
    output_dir = _resolve_output_dir(args.output_dir)
    history_file = args.history_file or os.path.join(output_dir, "theme_detector_history.json")
    history = load_history(history_file)

    # -----------------------------------------------------------------------
    # Step 0: Load theme configuration (YAML or inline fallback)
    # -----------------------------------------------------------------------
    themes_config, etf_catalog = load_themes_config(args.themes_config)
    start_time = time.time()

    # Determine data mode
    finviz_mode = args.finviz_mode
    if finviz_mode is None:
        finviz_mode = "elite" if args.finviz_api_key else "public"
    fmp_available = args.fmp_api_key is not None
    data_mode = determine_data_mode(fmp_available, finviz_mode == "elite")

    print("Theme Detector starting...", file=sys.stderr)
    print(f"  Data mode: {data_mode}", file=sys.stderr)
    print(f"  FINVIZ mode: {finviz_mode}", file=sys.stderr)
    print(f"  FMP API: {'available' if fmp_available else 'not available'}", file=sys.stderr)
    print(f"  Max themes: {args.max_themes}", file=sys.stderr)
    print(f"  Max stocks/theme: {args.max_stocks_per_theme}", file=sys.stderr)

    metadata = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "run_date": run_date,
        "data_mode": data_mode,
        "finviz_mode": finviz_mode,
        "fmp_available": fmp_available,
        "max_themes": args.max_themes,
        "max_stocks_per_theme": args.max_stocks_per_theme,
        "history_file": history_file,
        "history_update": not args.no_history_update,
        "data_sources": {},
    }

    # -----------------------------------------------------------------------
    # Step 1: Fetch FINVIZ industry performance
    # -----------------------------------------------------------------------
    print("Fetching FINVIZ industry performance...", file=sys.stderr)
    raw_industries = get_industry_performance()
    if not raw_industries:
        print("ERROR: No industry data from FINVIZ. Exiting.", file=sys.stderr)
        sys.exit(1)

    metadata["data_sources"]["finviz_industries"] = len(raw_industries)
    print(f"  Got {len(raw_industries)} industries", file=sys.stderr)

    # Convert decimal to percentage, filter outliers, and add sector info
    industries = _convert_perf_to_pct(raw_industries)
    industries = cap_outlier_performances(industries)
    industries = _add_sector_info(industries)

    # -----------------------------------------------------------------------
    # Step 2: Rank industries by momentum
    # -----------------------------------------------------------------------
    print("Ranking industries by momentum...", file=sys.stderr)
    ranked = rank_industries(industries)
    industry_rankings = get_top_bottom_industries(ranked, n=15)
    print(
        f"  Top: {ranked[0]['name']} ({ranked[0]['momentum_score']})" if ranked else "",
        file=sys.stderr,
    )

    # -----------------------------------------------------------------------
    # Step 3: Classify themes
    # -----------------------------------------------------------------------
    print("Classifying themes...", file=sys.stderr)
    themes = classify_themes(ranked, themes_config)
    print(f"  Detected {len(themes)} themes (seed + vertical)", file=sys.stderr)

    if not themes:
        print("WARNING: No themes detected. Generating empty report.", file=sys.stderr)

    # Step 3.3: Enrich vertical themes with ETFs + deduplicate
    enrich_vertical_themes(themes)
    themes = deduplicate_themes(themes)
    print(f"  After enrich/dedup: {len(themes)} themes", file=sys.stderr)

    # Step 3.5: Discover new themes from unmatched industries
    if args.discover_themes:
        from calculators.theme_classifier import get_matched_industry_names
        from calculators.theme_discoverer import discover_themes

        matched_names = get_matched_industry_names(themes)
        discovered = discover_themes(ranked, matched_names, themes, top_n=30)
        themes.extend(discovered)
        metadata["data_sources"]["discovered_themes"] = len(discovered)
        print(f"  Discovered {len(discovered)} new themes", file=sys.stderr)

    # Step 3.9: Limit to max_themes using composite priority (size + strength)
    def _theme_priority(t):
        inds = t.get("matching_industries", [])
        n_industries = len(inds)
        avg_strength = sum(abs(ind.get("weighted_return", 0)) for ind in inds) / max(len(inds), 1)
        size_norm = min(n_industries / 10.0, 1.0)
        strength_norm = min(avg_strength / 30.0, 1.0)
        return size_norm * 0.5 + strength_norm * 0.5

    themes.sort(key=_theme_priority, reverse=True)
    themes = themes[: args.max_themes]

    # -----------------------------------------------------------------------
    # Step 3.95: Load stock leadership scan hits
    # -----------------------------------------------------------------------
    scan_hits = []
    scan_hits_available = args.scan_hits is not None
    if args.scan_hits:
        print(f"Loading leadership scan hits from {args.scan_hits}...", file=sys.stderr)
        scan_hits, scan_summary = load_scan_hits(args.scan_hits, run_date)
        metadata["data_sources"]["scan_hits"] = scan_summary
        print(
            f"  Scan rows: {scan_summary['rows']}, hits: {scan_summary['hits']}",
            file=sys.stderr,
        )
    else:
        metadata["data_sources"]["scan_hits"] = {
            "path": None,
            "rows": 0,
            "hits": 0,
            "skipped_rows": 0,
        }

    leadership_by_theme = aggregate_leadership(themes, scan_hits, history)

    # -----------------------------------------------------------------------
    # Step 4: Collect all stock symbols for batch download
    # -----------------------------------------------------------------------
    print("Selecting representative stocks...", file=sys.stderr)

    # Create dynamic selector if requested
    selector = None
    if args.dynamic_stocks:
        from representative_stock_selector import RepresentativeStockSelector

        selector = RepresentativeStockSelector(
            finviz_elite_key=args.finviz_api_key,
            fmp_api_key=args.fmp_api_key,
            finviz_mode=finviz_mode,
            rate_limit_sec=1.0,
            min_cap=args.dynamic_min_cap,
        )
        print("  Dynamic stock selection: ON", file=sys.stderr)

    # Use index-based keys to avoid collisions when multiple themes share
    # the same name (e.g. two "{Sector} Sector Concentration" themes for
    # top and bottom, or duplicate auto-names from the discoverer).
    theme_stocks: dict[int, list[str]] = {}
    theme_stock_details: dict[int, list[dict]] = {}
    all_symbols = set()

    for idx, theme in enumerate(themes):
        tickers, stock_details = _get_representative_stocks(
            theme, selector, args.max_stocks_per_theme
        )
        theme_stocks[idx] = tickers
        theme_stock_details[idx] = stock_details
        all_symbols.update(tickers)

    all_symbols_list = sorted(all_symbols)
    print(f"  Total unique stocks: {len(all_symbols_list)}", file=sys.stderr)

    if selector:
        print(f"  Dynamic stock queries: {selector.query_count}", file=sys.stderr)
        print(f"  Dynamic stock failures: {selector.failure_count}", file=sys.stderr)
        print(f"  Dynamic stock status: {selector.status}", file=sys.stderr)
        metadata["data_sources"]["dynamic_stocks_status"] = selector.status
        metadata["data_sources"]["dynamic_stocks_queries"] = selector.query_count
        metadata["data_sources"]["dynamic_stocks_failures"] = selector.failure_count
        metadata["data_sources"]["dynamic_stocks_source_states"] = {
            name: {"disabled": s.disabled, "failures": s.total_failures}
            for name, s in selector.source_states.items()
        }

    # -----------------------------------------------------------------------
    # Step 5: Batch fetch stock metrics (yfinance)
    # -----------------------------------------------------------------------
    stock_metrics_map: dict[str, dict] = {}
    scanner = ETFScanner(fmp_api_key=args.fmp_api_key)

    if all_symbols_list:
        print(f"Batch downloading {len(all_symbols_list)} stocks...", file=sys.stderr)
        all_metrics = scanner.batch_stock_metrics(all_symbols_list)
        for m in all_metrics:
            stock_metrics_map[m["symbol"]] = m
        # Backward compatible key (1 release coexistence)
        metadata["data_sources"]["yfinance_stocks"] = len(all_metrics)
        print(f"  Got metrics for {len(all_metrics)} stocks", file=sys.stderr)

    # -----------------------------------------------------------------------
    # Step 6: Fetch ETF volume ratios for each theme's proxy ETFs
    # -----------------------------------------------------------------------
    print("Fetching ETF volume data...", file=sys.stderr)
    etf_volume_map: dict[str, dict] = {}
    all_etfs = set()
    for theme in themes:
        for etf in theme.get("proxy_etfs", []):
            all_etfs.add(etf)

    etf_volume_map = scanner.batch_etf_volume_ratios(sorted(all_etfs))

    metadata["data_sources"]["etf_volume"] = len(etf_volume_map)

    # Capture backend stats after all scanner calls (stock + ETF)
    scanner_stats = scanner.backend_stats()
    metadata["data_sources"]["scanner_backend"] = scanner_stats
    stock_s = scanner_stats.get("stock", {})
    etf_s = scanner_stats.get("etf", {})
    print(
        f"  Scanner (stock): FMP {stock_s.get('fmp_calls', 0)} calls "
        f"({stock_s.get('fmp_failures', 0)} failures), "
        f"yfinance: {stock_s.get('yf_calls', 0)} calls "
        f"({stock_s.get('yf_fallbacks', 0)} fallbacks)",
        file=sys.stderr,
    )
    print(
        f"  Scanner (ETF):   FMP {etf_s.get('fmp_calls', 0)} calls "
        f"({etf_s.get('fmp_failures', 0)} failures), "
        f"yfinance: {etf_s.get('yf_calls', 0)} calls "
        f"({etf_s.get('yf_fallbacks', 0)} fallbacks)",
        file=sys.stderr,
    )

    # -----------------------------------------------------------------------
    # Step 7: Fetch uptrend-dashboard data
    # -----------------------------------------------------------------------
    print("Fetching uptrend ratio data...", file=sys.stderr)
    sector_uptrend = fetch_sector_uptrend_data()
    stale_data = False

    if sector_uptrend:
        # Check freshness from any sector's latest_date
        any_sector = next(iter(sector_uptrend.values()), {})
        latest_date = any_sector.get("latest_date", "")
        stale_data = is_data_stale(latest_date, threshold_bdays=2)
        if stale_data:
            print(f"  WARNING: Uptrend data is stale (latest: {latest_date})", file=sys.stderr)
        metadata["data_sources"]["uptrend_sectors"] = len(sector_uptrend)
        metadata["data_sources"]["uptrend_stale"] = stale_data
    else:
        print("  WARNING: Uptrend data unavailable", file=sys.stderr)
        metadata["data_sources"]["uptrend_error"] = "fetch failed"

    # -----------------------------------------------------------------------
    # Step 8: Score each theme
    # -----------------------------------------------------------------------
    print("Scoring themes...", file=sys.stderr)
    scored_themes = []

    for idx, theme in enumerate(themes):
        theme_name = theme["theme_name"]
        direction = theme["direction"]
        is_bearish = direction == "bearish"
        stocks = theme_stocks.get(idx, [])

        # --- Theme Heat ---
        # Momentum: average weighted_return of matching industries
        theme_wr = _get_theme_weighted_return(theme)
        momentum = momentum_strength_score(theme_wr)

        # Volume: average ETF volume ratio
        etf_vol_ratios = []
        for etf_sym in theme.get("proxy_etfs", []):
            vol = etf_volume_map.get(etf_sym, {})
            if vol.get("vol_20d") is not None and vol.get("vol_60d") is not None:
                etf_vol_ratios.append((vol["vol_20d"], vol["vol_60d"]))

        if etf_vol_ratios:
            avg_20d = sum(r[0] for r in etf_vol_ratios) / len(etf_vol_ratios)
            avg_60d = sum(r[1] for r in etf_vol_ratios) / len(etf_vol_ratios)
            volume = volume_intensity_score(avg_20d, avg_60d)
        else:
            volume = None

        # Uptrend signal
        sector_data = _get_theme_uptrend_data(theme, sector_uptrend)
        if sector_data:
            uptrend = uptrend_signal_score(sector_data, is_bearish)
        else:
            uptrend = None

        # Breadth signal
        breadth_ratio = _calculate_breadth_ratio(theme)
        n_industries = len(theme.get("matching_industries", []))
        breadth = breadth_signal_score(breadth_ratio, industry_count=n_industries)

        heat_detail = calculate_theme_heat_detailed(momentum, volume, uptrend, breadth)
        base_heat = round(heat_detail["score"] or 0.0, 2)

        leadership = leadership_by_theme.get(theme_name, {})
        leadership_score = leadership.get("leadership_score")
        heat = blend_theme_heat(base_heat, leadership_score)
        history_metrics = compute_history_metrics(history, theme_name, run_date, heat)

        heat_breakdown = {
            "momentum_strength": _round_optional(momentum),
            "volume_intensity": _round_optional(volume),
            "uptrend_signal": _round_optional(uptrend),
            "breadth_signal": _round_optional(breadth),
            "leadership_score": _round_optional(leadership_score),
        }

        # --- Divergence detection ---
        divergence = detect_divergence(heat_breakdown, direction)

        # --- Lifecycle Maturity ---
        # Get stock-level metrics for this theme
        theme_stock_metrics = [stock_metrics_map[s] for s in stocks if s in stock_metrics_map]

        # Remap keys: rsi_14 -> rsi (lifecycle_calculator expects "rsi")
        for sm in theme_stock_metrics:
            if "rsi_14" in sm:
                sm["rsi"] = sm["rsi_14"]

        # Duration: prefer actual theme history, fall back to performance horizons
        avg_perfs = _average_industry_perfs(theme.get("matching_industries", []))
        duration = history_metrics["duration_score"]
        if not history_metrics["prior_observations"] and duration == 0:
            duration = estimate_duration_score(
                avg_perfs.get("perf_1m"),
                avg_perfs.get("perf_3m"),
                avg_perfs.get("perf_6m"),
                avg_perfs.get("perf_1y"),
                is_bearish,
            )

        # Extremity clustering
        extremity = extremity_clustering_score(theme_stock_metrics, is_bearish)

        # Price extreme saturation
        price_extreme = price_extreme_saturation_score(theme_stock_metrics, is_bearish)

        # Valuation premium
        valuation = valuation_premium_score(theme_stock_metrics)

        # ETF proliferation
        etf_count = etf_catalog.get(theme_name, 0)
        etf_prolif = etf_proliferation_score(etf_count)

        maturity_detail = calculate_lifecycle_maturity_detailed(
            duration, extremity, price_extreme, valuation, etf_prolif
        )
        maturity = round(maturity_detail["score"] or 0.0, 2)
        stage = classify_stage(maturity)

        maturity_breakdown = {
            "duration_score": _round_optional(duration),
            "extremity_clustering": _round_optional(extremity),
            "price_extreme_saturation": _round_optional(price_extreme),
            "valuation_premium": _round_optional(valuation),
            "etf_proliferation": _round_optional(etf_prolif),
        }

        # --- Confidence ---
        quant_confirmed = momentum > 50
        breadth_confirmed = (uptrend is not None and uptrend > 55) if uptrend else False
        narrative_confirmed = False  # Pending Claude WebSearch
        confidence_penalties = _coverage_penalties(
            heat_detail, maturity_detail, scan_hits_available
        )
        confidence = calculate_confidence(
            quant_confirmed,
            breadth_confirmed,
            narrative_confirmed,
            stale_data,
            coverage_penalty_count=len(confidence_penalties),
        )

        # --- Score theme ---
        score = score_theme(
            round(heat, 2),
            round(maturity, 2),
            stage,
            direction,
            confidence,
            data_mode,
        )

        # Lifecycle data quality flag
        lifecycle_quality = "sufficient" if theme_stock_metrics else "insufficient"

        # Build full theme result
        scored_theme = {
            "name": theme_name,
            "direction": direction,
            "heat": round(heat, 2),
            "base_heat": base_heat,
            "maturity": round(maturity, 2),
            "stage": stage,
            "confidence": confidence,
            "heat_label": score["heat_label"],
            "heat_breakdown": heat_breakdown,
            "heat_coverage": round(heat_detail["coverage"], 4),
            "heat_missing_components": heat_detail["missing_components"],
            "maturity_breakdown": maturity_breakdown,
            "maturity_coverage": round(maturity_detail["coverage"], 4),
            "maturity_missing_components": maturity_detail["missing_components"],
            "lifecycle_data_quality": lifecycle_quality,
            "representative_stocks": stocks,
            "stock_details": theme_stock_details.get(idx, []),
            "proxy_etfs": theme.get("proxy_etfs", []),
            "industries": [ind.get("name", "") for ind in theme.get("matching_industries", [])],
            "sector_weights": theme.get("sector_weights", {}),
            "stock_data": "available" if theme_stock_metrics else "unavailable",
            "data_mode": data_mode,
            "stale_data_penalty": stale_data,
            "confidence_penalties": confidence_penalties,
            "theme_origin": theme.get("theme_origin", "seed"),
            "name_confidence": theme.get("name_confidence", "high"),
            "divergence": divergence,
            "leadership_score": leadership_score,
            "leadership_coverage": leadership.get("leadership_coverage", 0.0),
            "leadership_counts": leadership.get("leadership_counts", {}),
            "leader_symbols": leadership.get("leader_symbols", []),
            "history_metrics": history_metrics,
        }
        scored_themes.append(scored_theme)

    # Sort by heat descending
    scored_themes.sort(key=lambda t: t["heat"], reverse=True)

    # -----------------------------------------------------------------------
    # Step 9: Generate reports
    # -----------------------------------------------------------------------
    print("Generating reports...", file=sys.stderr)

    json_report = generate_json_report(scored_themes, industry_rankings, sector_uptrend, metadata)
    md_report = generate_markdown_report(json_report, top_n_detail=args.top)

    paths = save_reports(json_report, md_report, output_dir)

    if not args.no_history_update:
        observations = [build_observation(theme, run_date) for theme in scored_themes]
        save_history(history_file, append_observations(history, observations))

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.1f}s", file=sys.stderr)
    print(f"  JSON:     {paths['json']}", file=sys.stderr)
    print(f"  Markdown: {paths['markdown']}", file=sys.stderr)
    print(f"  Themes:   {len(scored_themes)}", file=sys.stderr)

    # Print JSON to stdout for programmatic consumption
    print(json.dumps(json_report, indent=2, default=str))


def _average_industry_perfs(industries: list[dict]) -> dict:
    """Average performance across theme's matching industries."""
    if not industries:
        return {}

    perf_keys = ["perf_1m", "perf_3m", "perf_6m", "perf_1y"]
    result = {}
    for key in perf_keys:
        vals = [ind.get(key) for ind in industries if ind.get(key) is not None]
        result[key] = sum(vals) / len(vals) if vals else None
    return result


if __name__ == "__main__":
    main()
