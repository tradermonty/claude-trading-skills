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

import argparse
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

# Ensure scripts directory is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from calculators.industry_ranker import rank_industries, get_top_bottom_industries
from calculators.theme_classifier import classify_themes
from calculators.heat_calculator import (
    momentum_strength_score,
    volume_intensity_score,
    uptrend_signal_score,
    breadth_signal_score,
    calculate_theme_heat,
)
from calculators.lifecycle_calculator import (
    estimate_duration_score,
    extremity_clustering_score,
    price_extreme_saturation_score,
    valuation_premium_score,
    etf_proliferation_score,
    classify_stage,
    calculate_lifecycle_maturity,
)
from scorer import (
    score_theme,
    get_heat_label,
    calculate_confidence,
    determine_data_mode,
)
from report_generator import generate_json_report, generate_markdown_report, save_reports
from finviz_performance_client import get_sector_performance, get_industry_performance
from etf_scanner import ETFScanner
from uptrend_client import fetch_sector_uptrend_data, is_data_stale


# ---------------------------------------------------------------------------
# Industry-to-sector mapping (FINVIZ industry names -> sector)
# ---------------------------------------------------------------------------
INDUSTRY_TO_SECTOR: Dict[str, str] = {
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
# Default cross-sector themes configuration
# ---------------------------------------------------------------------------
DEFAULT_THEMES_CONFIG: Dict = {
    "cross_sector_min_matches": 2,
    "vertical_min_industries": 3,
    "cross_sector": [
        {
            "theme_name": "AI & Semiconductors",
            "matching_keywords": [
                "Semiconductors",
                "Semiconductor Equipment & Materials",
                "Software - Application",
                "Software - Infrastructure",
                "Information Technology Services",
                "Computer Hardware",
                "Electronic Components",
            ],
            "proxy_etfs": ["SMH", "SOXX", "AIQ", "BOTZ"],
            "static_stocks": [
                "NVDA", "AVGO", "AMD", "INTC", "QCOM",
                "MRVL", "AMAT", "LRCX", "KLAC", "TSM",
            ],
        },
        {
            "theme_name": "Clean Energy & EV",
            "matching_keywords": [
                "Solar",
                "Utilities - Renewable",
                "Auto Manufacturers",
                "Electrical Equipment & Parts",
                "Specialty Chemicals",
            ],
            "proxy_etfs": ["ICLN", "QCLN", "TAN", "LIT"],
            "static_stocks": [
                "ENPH", "SEDG", "FSLR", "RUN", "TSLA",
                "RIVN", "ALB", "PLUG", "BE", "NEE",
            ],
        },
        {
            "theme_name": "Cybersecurity",
            "matching_keywords": [
                "Software - Infrastructure",
                "Software - Application",
                "Information Technology Services",
            ],
            "proxy_etfs": ["CIBR", "HACK", "BUG"],
            "static_stocks": [
                "CRWD", "PANW", "FTNT", "ZS", "S",
                "OKTA", "NET", "CYBR", "QLYS", "RPD",
            ],
        },
        {
            "theme_name": "Cloud Computing & SaaS",
            "matching_keywords": [
                "Software - Application",
                "Software - Infrastructure",
                "Information Technology Services",
            ],
            "proxy_etfs": ["SKYY", "WCLD", "CLOU"],
            "static_stocks": [
                "CRM", "NOW", "SNOW", "DDOG", "MDB",
                "NET", "ZS", "HUBS", "WDAY", "TEAM",
            ],
        },
        {
            "theme_name": "Biotech & Genomics",
            "matching_keywords": [
                "Biotechnology",
                "Drug Manufacturers - General",
                "Drug Manufacturers - Specialty & Generic",
                "Diagnostics & Research",
            ],
            "proxy_etfs": ["XBI", "IBB", "ARKG"],
            "static_stocks": [
                "AMGN", "GILD", "VRTX", "REGN", "MRNA",
                "BIIB", "ILMN", "SGEN", "ALNY", "BMRN",
            ],
        },
        {
            "theme_name": "Infrastructure & Construction",
            "matching_keywords": [
                "Engineering & Construction",
                "Building Products & Equipment",
                "Building Materials",
                "Specialty Industrial Machinery",
                "Farm & Heavy Construction Machinery",
                "Infrastructure Operations",
            ],
            "proxy_etfs": ["PAVE", "IFRA"],
            "static_stocks": [
                "CAT", "DE", "VMC", "MLM", "URI",
                "PWR", "EME", "J", "ACM", "FAST",
            ],
        },
        {
            "theme_name": "Gold & Precious Metals",
            "matching_keywords": [
                "Gold",
                "Silver",
                "Other Precious Metals & Mining",
            ],
            "proxy_etfs": ["GDX", "GDXJ", "SLV", "GLD"],
            "static_stocks": [
                "NEM", "GOLD", "AEM", "FNV", "WPM",
                "RGLD", "KGC", "AGI", "HL", "PAAS",
            ],
        },
        {
            "theme_name": "Oil & Gas (Energy)",
            "matching_keywords": [
                "Oil & Gas E&P",
                "Oil & Gas Equipment & Services",
                "Oil & Gas Integrated",
                "Oil & Gas Midstream",
                "Oil & Gas Refining & Marketing",
                "Oil & Gas Drilling",
            ],
            "proxy_etfs": ["XLE", "XOP", "OIH"],
            "static_stocks": [
                "XOM", "CVX", "COP", "EOG", "SLB",
                "PXD", "MPC", "PSX", "OXY", "DVN",
            ],
        },
        {
            "theme_name": "Financial Services & Banks",
            "matching_keywords": [
                "Banks - Diversified",
                "Banks - Regional",
                "Capital Markets",
                "Insurance - Diversified",
                "Financial Data & Stock Exchanges",
                "Asset Management",
            ],
            "proxy_etfs": ["XLF", "KBE", "KRE"],
            "static_stocks": [
                "JPM", "BAC", "GS", "MS", "WFC",
                "C", "BLK", "SCHW", "ICE", "CME",
            ],
        },
        {
            "theme_name": "Healthcare & Pharma",
            "matching_keywords": [
                "Drug Manufacturers - General",
                "Medical Devices",
                "Medical Instruments & Supplies",
                "Healthcare Plans",
                "Medical Care Facilities",
            ],
            "proxy_etfs": ["XLV", "IHI", "XBI"],
            "static_stocks": [
                "UNH", "JNJ", "LLY", "PFE", "ABT",
                "TMO", "DHR", "SYK", "ISRG", "MDT",
            ],
        },
        {
            "theme_name": "Defense & Aerospace",
            "matching_keywords": [
                "Aerospace & Defense",
                "Communication Equipment",
                "Scientific & Technical Instruments",
            ],
            "proxy_etfs": ["ITA", "PPA", "XAR"],
            "static_stocks": [
                "LMT", "RTX", "NOC", "GD", "BA",
                "LHX", "HII", "TDG", "HWM", "AXON",
            ],
        },
        {
            "theme_name": "Real Estate & REITs",
            "matching_keywords": [
                "REIT - Diversified",
                "REIT - Industrial",
                "REIT - Residential",
                "REIT - Retail",
                "REIT - Specialty",
                "REIT - Office",
                "Real Estate - Development",
                "Real Estate Services",
            ],
            "proxy_etfs": ["VNQ", "IYR", "XLRE"],
            "static_stocks": [
                "PLD", "AMT", "EQIX", "CCI", "SPG",
                "O", "WELL", "DLR", "PSA", "AVB",
            ],
        },
        {
            "theme_name": "Retail & Consumer",
            "matching_keywords": [
                "Internet Retail",
                "Specialty Retail",
                "Apparel Retail",
                "Discount Stores",
                "Home Improvement Retail",
                "Department Stores",
            ],
            "proxy_etfs": ["XRT", "XLY"],
            "static_stocks": [
                "AMZN", "HD", "LOW", "TJX", "COST",
                "WMT", "TGT", "ROST", "BURL", "LULU",
            ],
        },
        {
            "theme_name": "Crypto & Blockchain",
            "matching_keywords": [
                "Capital Markets",
                "Software - Infrastructure",
                "Financial Data & Stock Exchanges",
            ],
            "proxy_etfs": ["BITO", "BLOK", "BITQ"],
            "static_stocks": [
                "COIN", "MSTR", "MARA", "RIOT", "CLSK",
                "HUT", "BITF", "HIVE", "SQ", "PYPL",
            ],
        },
        {
            "theme_name": "Nuclear & Uranium",
            "matching_keywords": [
                "Uranium",
                "Utilities - Independent Power Producers",
                "Utilities - Regulated Electric",
            ],
            "proxy_etfs": ["URA", "URNM", "NLR"],
            "static_stocks": [
                "CCJ", "UEC", "NXE", "DNN", "LEU",
                "SMR", "UUUU", "URG", "OKLO", "VST",
            ],
        },
    ],
}

# ---------------------------------------------------------------------------
# ETF catalog for proliferation scoring (theme_name -> count)
# ---------------------------------------------------------------------------
ETF_CATALOG: Dict[str, int] = {
    "AI & Semiconductors": 8,
    "Clean Energy & EV": 7,
    "Cybersecurity": 4,
    "Cloud Computing & SaaS": 4,
    "Biotech & Genomics": 5,
    "Infrastructure & Construction": 3,
    "Gold & Precious Metals": 4,
    "Oil & Gas (Energy)": 5,
    "Financial Services & Banks": 5,
    "Healthcare & Pharma": 5,
    "Defense & Aerospace": 5,
    "Real Estate & REITs": 4,
    "Retail & Consumer": 3,
    "Crypto & Blockchain": 4,
    "Nuclear & Uranium": 3,
}


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
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _add_sector_info(industries: List[Dict]) -> List[Dict]:
    """Add sector field to each industry dict from INDUSTRY_TO_SECTOR mapping."""
    for ind in industries:
        name = ind.get("name", "")
        ind["sector"] = INDUSTRY_TO_SECTOR.get(name, "Unknown")
    return industries


def _convert_perf_to_pct(industries: List[Dict]) -> List[Dict]:
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
    theme: Dict,
    fmp_api_key: Optional[str],
    finviz_elite_key: Optional[str],
    max_stocks: int,
) -> List[str]:
    """Get representative stocks for a theme using fallback chain.

    Priority:
    1. FINVIZ Elite CSV export (if key available)
    2. FMP ETF Holdings (if key available)
    3. Static stocks from theme config
    4. Empty list (flag as unavailable)
    """
    # Phase 1: Use static stocks from theme config
    static = theme.get("static_stocks", [])
    if static:
        return static[:max_stocks]

    # No stocks available
    return []


def _calculate_breadth_ratio(theme: Dict) -> Optional[float]:
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


def _get_theme_uptrend_data(
    theme: Dict, sector_uptrend: Dict
) -> List[Dict]:
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
            sector_data.append({
                "sector": sector_name,
                "ratio": uptrend_entry["ratio"],
                "ma_10": uptrend_entry.get("ma_10", 0),
                "slope": uptrend_entry.get("slope", 0),
                "weight": weight,
            })

    return sector_data


def _get_theme_weighted_return(theme: Dict) -> float:
    """Calculate aggregate weighted return for a theme from its industries."""
    industries = theme.get("matching_industries", [])
    if not industries:
        return 0.0

    returns = [ind.get("weighted_return", 0.0) for ind in industries]
    return sum(returns) / len(returns)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
def main():
    args = parse_args()
    start_time = time.time()

    # Determine data mode
    finviz_mode = args.finviz_mode
    if finviz_mode is None:
        finviz_mode = "elite" if args.finviz_api_key else "public"
    fmp_available = args.fmp_api_key is not None
    data_mode = determine_data_mode(fmp_available, finviz_mode == "elite")

    print(f"Theme Detector starting...", file=sys.stderr)
    print(f"  Data mode: {data_mode}", file=sys.stderr)
    print(f"  FINVIZ mode: {finviz_mode}", file=sys.stderr)
    print(f"  FMP API: {'available' if fmp_available else 'not available'}",
          file=sys.stderr)
    print(f"  Max themes: {args.max_themes}", file=sys.stderr)
    print(f"  Max stocks/theme: {args.max_stocks_per_theme}", file=sys.stderr)

    metadata = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data_mode": data_mode,
        "finviz_mode": finviz_mode,
        "fmp_available": fmp_available,
        "max_themes": args.max_themes,
        "max_stocks_per_theme": args.max_stocks_per_theme,
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

    # Convert decimal to percentage and add sector info
    industries = _convert_perf_to_pct(raw_industries)
    industries = _add_sector_info(industries)

    # -----------------------------------------------------------------------
    # Step 2: Rank industries by momentum
    # -----------------------------------------------------------------------
    print("Ranking industries by momentum...", file=sys.stderr)
    ranked = rank_industries(industries)
    industry_rankings = get_top_bottom_industries(ranked, n=15)
    print(f"  Top: {ranked[0]['name']} ({ranked[0]['momentum_score']})" if ranked else "",
          file=sys.stderr)

    # -----------------------------------------------------------------------
    # Step 3: Classify themes
    # -----------------------------------------------------------------------
    print("Classifying themes...", file=sys.stderr)
    themes = classify_themes(ranked, DEFAULT_THEMES_CONFIG)
    print(f"  Detected {len(themes)} themes", file=sys.stderr)

    if not themes:
        print("WARNING: No themes detected. Generating empty report.",
              file=sys.stderr)

    # Limit to max_themes (sort by number of matching industries, descending)
    themes.sort(key=lambda t: len(t.get("matching_industries", [])), reverse=True)
    themes = themes[:args.max_themes]

    # -----------------------------------------------------------------------
    # Step 4: Collect all stock symbols for batch download
    # -----------------------------------------------------------------------
    print("Selecting representative stocks...", file=sys.stderr)
    theme_stocks: Dict[str, List[str]] = {}
    all_symbols = set()

    for theme in themes:
        stocks = _get_representative_stocks(
            theme, args.fmp_api_key, args.finviz_api_key, args.max_stocks_per_theme
        )
        theme_stocks[theme["theme_name"]] = stocks
        all_symbols.update(stocks)

    all_symbols_list = sorted(all_symbols)
    print(f"  Total unique stocks: {len(all_symbols_list)}", file=sys.stderr)

    # -----------------------------------------------------------------------
    # Step 5: Batch fetch stock metrics (yfinance)
    # -----------------------------------------------------------------------
    stock_metrics_map: Dict[str, Dict] = {}
    scanner = ETFScanner()

    if all_symbols_list:
        print(f"Batch downloading {len(all_symbols_list)} stocks...", file=sys.stderr)
        all_metrics = scanner.batch_stock_metrics(all_symbols_list)
        for m in all_metrics:
            stock_metrics_map[m["symbol"]] = m
        metadata["data_sources"]["yfinance_stocks"] = len(all_metrics)
        print(f"  Got metrics for {len(all_metrics)} stocks", file=sys.stderr)

    # -----------------------------------------------------------------------
    # Step 6: Fetch ETF volume ratios for each theme's proxy ETFs
    # -----------------------------------------------------------------------
    print("Fetching ETF volume data...", file=sys.stderr)
    etf_volume_map: Dict[str, Dict] = {}
    all_etfs = set()
    for theme in themes:
        for etf in theme.get("proxy_etfs", []):
            all_etfs.add(etf)

    for etf in sorted(all_etfs):
        vol_data = scanner.get_etf_volume_ratio(etf)
        etf_volume_map[etf] = vol_data

    metadata["data_sources"]["etf_volume"] = len(etf_volume_map)

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
        stale_data = is_data_stale(latest_date, threshold_days=2)
        if stale_data:
            print(f"  WARNING: Uptrend data is stale (latest: {latest_date})",
                  file=sys.stderr)
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

    for theme in themes:
        theme_name = theme["theme_name"]
        direction = theme["direction"]
        is_bearish = direction == "bearish"
        stocks = theme_stocks.get(theme_name, [])

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
            volume = None  # defaults to 50

        # Uptrend signal
        sector_data = _get_theme_uptrend_data(theme, sector_uptrend)
        if sector_data:
            uptrend = uptrend_signal_score(sector_data, is_bearish)
        else:
            uptrend = None  # defaults to 50

        # Breadth signal
        breadth_ratio = _calculate_breadth_ratio(theme)
        breadth = breadth_signal_score(breadth_ratio)

        heat = calculate_theme_heat(momentum, volume, uptrend, breadth)

        heat_breakdown = {
            "momentum_strength": round(momentum, 2),
            "volume_intensity": round(volume, 2) if volume is not None else 50.0,
            "uptrend_signal": round(uptrend, 2) if uptrend is not None else 50.0,
            "breadth_signal": round(breadth, 2),
        }

        # --- Lifecycle Maturity ---
        # Get stock-level metrics for this theme
        theme_stock_metrics = [
            stock_metrics_map[s] for s in stocks if s in stock_metrics_map
        ]

        # Remap keys: rsi_14 -> rsi (lifecycle_calculator expects "rsi")
        for sm in theme_stock_metrics:
            if "rsi_14" in sm:
                sm["rsi"] = sm["rsi_14"]

        # Duration: from industry performance timeframes
        avg_perfs = _average_industry_perfs(theme.get("matching_industries", []))
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
        etf_count = ETF_CATALOG.get(theme_name, 0)
        etf_prolif = etf_proliferation_score(etf_count)

        maturity = calculate_lifecycle_maturity(
            duration, extremity, price_extreme, valuation, etf_prolif
        )
        stage = classify_stage(maturity)

        maturity_breakdown = {
            "duration_estimate": round(duration, 2),
            "extremity_clustering": round(extremity, 2),
            "price_extreme_saturation": round(price_extreme, 2),
            "valuation_premium": round(valuation, 2),
            "etf_proliferation": round(etf_prolif, 2),
        }

        # --- Confidence ---
        quant_confirmed = momentum > 50
        breadth_confirmed = (uptrend is not None and uptrend > 55) if uptrend else False
        narrative_confirmed = False  # Pending Claude WebSearch
        confidence = calculate_confidence(
            quant_confirmed, breadth_confirmed, narrative_confirmed, stale_data
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

        # Build full theme result
        scored_theme = {
            "name": theme_name,
            "direction": direction,
            "heat": round(heat, 2),
            "maturity": round(maturity, 2),
            "stage": stage,
            "confidence": confidence,
            "heat_label": score["heat_label"],
            "heat_breakdown": heat_breakdown,
            "maturity_breakdown": maturity_breakdown,
            "representative_stocks": stocks,
            "proxy_etfs": theme.get("proxy_etfs", []),
            "industries": [ind.get("name", "") for ind in
                          theme.get("matching_industries", [])],
            "sector_weights": theme.get("sector_weights", {}),
            "stock_data": "available" if theme_stock_metrics else "unavailable",
            "data_mode": data_mode,
            "stale_data_penalty": stale_data,
        }
        scored_themes.append(scored_theme)

    # Sort by heat descending
    scored_themes.sort(key=lambda t: t["heat"], reverse=True)

    # -----------------------------------------------------------------------
    # Step 9: Generate reports
    # -----------------------------------------------------------------------
    print("Generating reports...", file=sys.stderr)

    json_report = generate_json_report(
        scored_themes, industry_rankings, sector_uptrend, metadata
    )
    md_report = generate_markdown_report(json_report)

    # Resolve output directory relative to repo root if relative
    output_dir = args.output_dir
    if not os.path.isabs(output_dir):
        # Look for reports/ relative to repo root
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )))
        output_dir = os.path.join(repo_root, output_dir)

    paths = save_reports(json_report, md_report, output_dir)

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.1f}s", file=sys.stderr)
    print(f"  JSON:     {paths['json']}", file=sys.stderr)
    print(f"  Markdown: {paths['markdown']}", file=sys.stderr)
    print(f"  Themes:   {len(scored_themes)}", file=sys.stderr)

    # Print JSON to stdout for programmatic consumption
    print(json.dumps(json_report, indent=2, default=str))


def _average_industry_perfs(industries: List[Dict]) -> Dict:
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
