#!/usr/bin/env python3
"""
Theme Detector - Uptrend Ratio Client

Fetches sector uptrend ratio data from Monty's Uptrend Ratio Dashboard
(GitHub CSV). No API key required.

Data Source: https://github.com/tradermonty/uptrend-dashboard
"""

import csv
import io
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


TIMESERIES_URL = (
    "https://raw.githubusercontent.com/tradermonty/uptrend-dashboard/"
    "main/data/uptrend_ratio_timeseries.csv"
)
SECTOR_SUMMARY_URL = (
    "https://raw.githubusercontent.com/tradermonty/uptrend-dashboard/"
    "main/data/sector_summary.csv"
)

# Map FINVIZ sector names to uptrend worksheet names
FINVIZ_TO_WORKSHEET = {
    "Technology": "sec_technology",
    "Healthcare": "sec_healthcare",
    "Financial": "sec_financial",
    "Consumer Cyclical": "sec_consumercyclical",
    "Consumer Defensive": "sec_consumerdefensive",
    "Industrials": "sec_industrials",
    "Energy": "sec_energy",
    "Basic Materials": "sec_basicmaterials",
    "Communication Services": "sec_communicationservices",
    "Real Estate": "sec_realestate",
    "Utilities": "sec_utilities",
}

# Reverse mapping for display
WORKSHEET_TO_DISPLAY = {v: k for k, v in FINVIZ_TO_WORKSHEET.items()}


def _safe_float(value) -> Optional[float]:
    """Convert to float, return None if empty or invalid."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _calculate_slope(values: List[float]) -> Optional[float]:
    """Calculate slope from a list of values using simple linear regression.

    Uses least-squares fit: slope = sum((x-xbar)(y-ybar)) / sum((x-xbar)^2)

    Args:
        values: List of float values (at least 2 required)

    Returns:
        Slope value or None if insufficient data
    """
    if not values or len(values) < 2:
        return None

    n = len(values)
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n

    numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    if denominator == 0:
        return 0.0

    return round(numerator / denominator, 6)


def is_data_stale(latest_date_str: str, threshold_days: int = 2) -> bool:
    """Check if the latest data is older than threshold business days.

    Args:
        latest_date_str: Date string in YYYY-MM-DD format
        threshold_days: Maximum acceptable age in calendar days (default 2)

    Returns:
        True if data is stale (older than threshold)
    """
    try:
        latest = datetime.strptime(latest_date_str, "%Y-%m-%d")
        now = datetime.now()
        diff = (now - latest).days
        return diff > threshold_days
    except (ValueError, TypeError):
        return True


def fetch_sector_uptrend_data() -> Dict[str, Dict]:
    """Fetch sector uptrend ratio data from timeseries CSV.

    Downloads the full timeseries, extracts the latest row per sector,
    and calculates slope from the last 5 data points.

    Returns:
        Dict mapping display sector name to:
        {
            "ratio": float,       # Current uptrend ratio (0.0-1.0)
            "ma_10": float,       # 10-period moving average
            "slope": float,       # Slope from last 5 data points
            "trend": str,         # "up" or "down"
            "latest_date": str,   # YYYY-MM-DD
        }
        Empty dict on failure.
    """
    if not HAS_REQUESTS:
        print("WARNING: requests library not installed.", file=sys.stderr)
        return {}

    try:
        response = requests.get(TIMESERIES_URL, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"WARNING: Failed to fetch uptrend timeseries: {e}",
              file=sys.stderr)
        return {}

    # Parse all rows, grouped by worksheet
    sector_rows: Dict[str, List[Dict]] = {}
    reader = csv.DictReader(io.StringIO(response.text))
    for row in reader:
        ws = row.get("worksheet", "").strip()
        if ws == "all" or not ws.startswith("sec_"):
            continue
        date_str = row.get("date", "").strip()
        ratio = _safe_float(row.get("ratio"))
        ma_10 = _safe_float(row.get("ma_10"))
        slope_csv = _safe_float(row.get("slope"))
        trend = row.get("trend", "").strip()

        if not date_str or ratio is None:
            continue

        if ws not in sector_rows:
            sector_rows[ws] = []
        sector_rows[ws].append({
            "date": date_str,
            "ratio": ratio,
            "ma_10": ma_10,
            "slope_csv": slope_csv,
            "trend": trend,
        })

    # For each sector: sort by date, get latest, calculate slope from last 5
    result = {}
    for ws_name, rows in sector_rows.items():
        rows.sort(key=lambda r: r["date"])
        latest = rows[-1]
        display_name = WORKSHEET_TO_DISPLAY.get(ws_name, ws_name)

        # Calculate slope from last 5 ratio values
        last_n = rows[-5:] if len(rows) >= 5 else rows
        ratio_values = [r["ratio"] for r in last_n if r["ratio"] is not None]
        calculated_slope = _calculate_slope(ratio_values)

        # Prefer CSV slope if available, otherwise use calculated
        slope = latest["slope_csv"] if latest["slope_csv"] is not None else calculated_slope

        result[display_name] = {
            "ratio": latest["ratio"],
            "ma_10": latest["ma_10"],
            "slope": slope,
            "trend": latest["trend"] or ("up" if slope and slope > 0 else "down"),
            "latest_date": latest["date"],
        }

    return result


def build_summary_from_timeseries(sector_timeseries: Dict[str, Dict]) -> List[Dict]:
    """Build a sector summary list from timeseries data.

    Fallback when sector_summary.csv is unavailable.

    Args:
        sector_timeseries: Dict from fetch_sector_uptrend_data()

    Returns:
        List of dicts with: Sector, Ratio, 10MA, Trend, Slope, Status
    """
    OVERBOUGHT = 0.37
    OVERSOLD = 0.097

    rows = []
    for sector_name, data in sector_timeseries.items():
        ratio = data.get("ratio")
        status = ("Overbought" if ratio is not None and ratio > OVERBOUGHT else
                  "Oversold" if ratio is not None and ratio < OVERSOLD else
                  "Normal")
        rows.append({
            "Sector": sector_name,
            "Ratio": ratio,
            "10MA": data.get("ma_10"),
            "Trend": (data.get("trend") or "").capitalize(),
            "Slope": data.get("slope"),
            "Status": status,
        })
    return rows


def get_sector_uptrend_3point(sector_name: str,
                               all_data: Dict[str, Dict]) -> Optional[Dict]:
    """Get ratio + ma_10 + slope for a specific sector.

    Args:
        sector_name: Display name (e.g., "Technology")
        all_data: Output from fetch_sector_uptrend_data()

    Returns:
        Dict with ratio, ma_10, slope, trend, latest_date. None if not found.
    """
    return all_data.get(sector_name)
