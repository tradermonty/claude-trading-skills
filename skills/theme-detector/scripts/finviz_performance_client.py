#!/usr/bin/env python3
"""
Theme Detector - FINVIZ Performance Client

Fetches sector and industry performance data from FINVIZ using the
finvizfinance library. No API key required (public data).

Data Source: finvizfinance.group.performance
"""

import math
import sys
from typing import Dict, List, Optional


try:
    from finvizfinance.group import performance as fvperf
    HAS_FINVIZFINANCE = True
except ImportError:
    HAS_FINVIZFINANCE = False


# Hard caps for performance values (absolute %).
# Applied before z-score winsorization to handle corrupted FINVIZ data
# (e.g., Luxury Goods: -100%, Biotechnology: +87% in perf_1w).
HARD_CAPS = {
    "perf_1w": 30.0,
    "perf_1m": 60.0,
    "perf_3m": 100.0,
    "perf_6m": 100.0,
    "perf_1y": 200.0,
    "perf_ytd": 200.0,
}


# Mapping from finvizfinance DataFrame columns to standardized keys
COLUMN_MAP = {
    "Name": "name",
    "Perf Week": "perf_1w",
    "Perf Month": "perf_1m",
    "Perf Quart": "perf_3m",
    "Perf Half": "perf_6m",
    "Perf Year": "perf_1y",
    "Perf YTD": "perf_ytd",
}


def _parse_perf_value(val) -> Optional[float]:
    """Parse a performance value to float.

    The finvizfinance library may return:
    - float already (e.g., 0.12 for 12%)
    - string like "0.12%" or "12.34%"
    - None or NaN
    """
    if val is None:
        return None
    try:
        import math
        if isinstance(val, float) and math.isnan(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        cleaned = val.strip().rstrip("%")
        if not cleaned:
            return None
        try:
            num = float(cleaned)
            # If original had % sign but value looks like it's already in
            # decimal form (e.g., "0.12%"), it's ambiguous.
            # finvizfinance typically returns decimal (0.12 = 12%).
            # If string had % and value > 1, it's likely a percentage.
            if "%" in val and abs(num) > 1:
                return num / 100.0
            return num
        except ValueError:
            return None
    return None


def _dataframe_to_dicts(df) -> List[Dict]:
    """Convert a finvizfinance DataFrame to standardized list of dicts."""
    rows = []
    for _, row in df.iterrows():
        entry = {}
        for src_col, dst_key in COLUMN_MAP.items():
            if src_col in row.index:
                if dst_key == "name":
                    entry[dst_key] = str(row[src_col]).strip()
                else:
                    entry[dst_key] = _parse_perf_value(row[src_col])
            else:
                if dst_key != "name":
                    entry[dst_key] = None
        if entry.get("name"):
            rows.append(entry)
    return rows


def _apply_hard_caps(industries: List[Dict]) -> List[Dict]:
    """Apply absolute hard caps to performance values.

    Caps each perf_* field to ±HARD_CAPS[key]. Original values are saved in
    raw_perf_* only if raw_perf_* does not already exist (preserves the
    two-stage pipeline: hard cap -> z-score winsorization).

    Args:
        industries: List of industry dicts with perf_* fields.

    Returns:
        Same list, mutated in place.
    """
    for ind in industries:
        for key, cap in HARD_CAPS.items():
            val = ind.get(key)
            if val is None:
                continue
            if abs(val) > cap:
                raw_key = f"raw_{key}"
                if raw_key not in ind:
                    ind[raw_key] = val
                ind[key] = cap if val > 0 else -cap
    return industries


def cap_outlier_performances(industries: List[Dict],
                              z_threshold: float = 3.0) -> List[Dict]:
    """Winsorize performance values exceeding z_threshold standard deviations.

    For each perf_* field, computes mean and std across all industries,
    then caps values exceeding |z| > z_threshold to the boundary value.
    Original values are preserved in raw_perf_* fields.

    Skips winsorization if fewer than 5 industries (insufficient for z-score).

    Args:
        industries: List of industry dicts with perf_* fields.
        z_threshold: Z-score threshold for outlier detection (default 3.0).

    Returns:
        Modified list (same objects, mutated in place).
    """
    # Stage 1: Apply hard caps before z-score calculation
    _apply_hard_caps(industries)

    if len(industries) < 5:
        return industries

    perf_keys = ["perf_1w", "perf_1m", "perf_3m", "perf_6m", "perf_1y", "perf_ytd"]

    for key in perf_keys:
        values = [ind[key] for ind in industries if ind.get(key) is not None]
        if len(values) < 5:
            continue

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std = math.sqrt(variance) if variance > 0 else 0

        if std == 0:
            continue

        cap_high = mean + z_threshold * std
        cap_low = mean - z_threshold * std

        for ind in industries:
            val = ind.get(key)
            if val is None:
                continue
            z = (val - mean) / std
            if abs(z) > z_threshold:
                raw_key = f"raw_{key}"
                if raw_key not in ind:
                    ind[raw_key] = val
                ind[key] = cap_high if val > mean else cap_low

    return industries


def get_sector_performance() -> List[Dict]:
    """Fetch sector-level performance data from FINVIZ.

    Returns:
        List of dicts with keys: name, perf_1w, perf_1m, perf_3m,
        perf_6m, perf_1y, perf_ytd. Values are floats in decimal
        form (e.g., 0.05 = 5%).
    """
    if not HAS_FINVIZFINANCE:
        print("WARNING: finvizfinance not installed. "
              "Install with: pip install finvizfinance", file=sys.stderr)
        return []

    try:
        perf = fvperf.Performance()
        df = perf.screener_view(group="Sector")
        return _dataframe_to_dicts(df)
    except Exception as e:
        print(f"WARNING: Failed to fetch sector performance: {e}",
              file=sys.stderr)
        return []


def get_industry_performance() -> List[Dict]:
    """Fetch industry-level performance data from FINVIZ.

    Returns:
        List of dicts with same structure as get_sector_performance().
        Typically 140+ industries.
    """
    if not HAS_FINVIZFINANCE:
        print("WARNING: finvizfinance not installed. "
              "Install with: pip install finvizfinance", file=sys.stderr)
        return []

    try:
        perf = fvperf.Performance()
        df = perf.screener_view(group="Industry")
        return _dataframe_to_dicts(df)
    except Exception as e:
        print(f"WARNING: Failed to fetch industry performance: {e}",
              file=sys.stderr)
        return []
