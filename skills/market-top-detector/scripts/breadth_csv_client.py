#!/usr/bin/env python3
"""
Breadth CSV Client - Fetch 200DMA breadth from TraderMonty's public CSV.

Lightweight client for auto-fetching S&P 500 breadth data (% above 200DMA)
from the market-breadth-analysis GitHub Pages CSV. No API key required.

Data source:
  https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv
"""

import csv
import io
from datetime import datetime
from typing import Dict, Optional

import requests

DEFAULT_DETAIL_URL = (
    "https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv"
)

TIMEOUT = 30


def fetch_breadth_200dma(url: str = DEFAULT_DETAIL_URL) -> Optional[Dict]:
    """
    Fetch the latest 200DMA breadth value from TraderMonty CSV.

    Returns:
        Dict with keys: value (0-100%), date (str), is_fresh (bool),
        days_old (int), source (str).
        None if fetch fails or CSV is empty.
    """
    rows = _fetch_detail_csv(url)
    if not rows:
        return None

    latest = rows[-1]
    raw_value = latest["Breadth_Index_Raw"]
    value = round(raw_value * 100, 2)
    date_str = latest["Date"]

    freshness = _check_data_freshness(date_str)

    return {
        "value": value,
        "date": date_str,
        "is_fresh": freshness["is_fresh"],
        "days_old": freshness["days_old"],
        "source": "TraderMonty CSV",
    }


def _fetch_detail_csv(url: str) -> list:
    """Fetch and parse the detail CSV. Returns rows sorted by date ascending."""
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
    except (requests.RequestException, OSError, ValueError):
        return []

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = []

    for raw_row in reader:
        try:
            row = _parse_detail_row(raw_row)
            rows.append(row)
        except (ValueError, KeyError):
            continue

    if not rows:
        return []

    rows.sort(key=lambda r: r["Date"])
    return rows


def _check_data_freshness(date_str: str, max_stale_days: int = 5) -> Dict:
    """Check if data date is within acceptable freshness window."""
    try:
        data_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return {"is_fresh": False, "days_old": None}

    days_old = (datetime.now() - data_date).days
    return {
        "is_fresh": days_old <= max_stale_days,
        "days_old": days_old,
    }


def _parse_detail_row(raw: Dict) -> Dict:
    """Convert a raw CSV row dict to properly typed values."""
    return {
        "Date": raw["Date"].strip(),
        "S&P500_Price": float(raw["S&P500_Price"]),
        "Breadth_Index_Raw": float(raw["Breadth_Index_Raw"]),
        "Breadth_Index_200MA": float(raw["Breadth_Index_200MA"]),
        "Breadth_Index_8MA": float(raw["Breadth_Index_8MA"]),
        "Breadth_200MA_Trend": int(raw["Breadth_200MA_Trend"]),
        "Bearish_Signal": _parse_bool(raw["Bearish_Signal"]),
        "Is_Peak": _parse_bool(raw["Is_Peak"]),
        "Is_Trough": _parse_bool(raw["Is_Trough"]),
        "Is_Trough_8MA_Below_04": _parse_bool(raw["Is_Trough_8MA_Below_04"]),
    }


def _parse_bool(val: str) -> bool:
    """Parse boolean from CSV string."""
    return val.strip().lower() in ("true", "1", "yes")
