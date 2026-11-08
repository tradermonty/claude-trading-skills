#!/usr/bin/env python3
"""
Theme Detector - FINVIZ Performance Client

Fetches sector and industry performance data from FINVIZ using the
authenticated Elite CSV export when configured, with a public finvizfinance fallback.

Data Source: finvizfinance.group.performance
"""

import csv
import io
import math
import os
import sys
from typing import Optional

import requests

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


def _dataframe_to_dicts(df) -> list[dict]:
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


def _apply_hard_caps(industries: list[dict]) -> list[dict]:
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


def cap_outlier_performances(industries: list[dict], z_threshold: float = 3.0) -> list[dict]:
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


GROUP_EXPORT_URL = "https://elite.finviz.com/grp_export"
ELITE_COLUMNS = {
    "Performance (Week)": "perf_1w",
    "Performance (Month)": "perf_1m",
    "Performance (Quarter)": "perf_3m",
    "Performance (Half Year)": "perf_6m",
    "Performance (Year)": "perf_1y",
    "Performance (Year To Date)": "perf_ytd",
}


def _elite_csv_rows(text: str) -> list[dict]:
    """Normalize percentage-point CSV to the public client's decimal ratios."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")), strict=True)
    required = {"Name", *ELITE_COLUMNS}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("missing group columns")
    if len(reader.fieldnames) != len(set(reader.fieldnames)):
        raise ValueError("duplicate group columns")
    rows = []
    for row in reader:
        if None in row or any(row.get(column) is None for column in required):
            raise ValueError("malformed group row")
        name = row["Name"].strip()
        if not name:
            continue
        entry = {"name": name}
        for column, key in ELITE_COLUMNS.items():
            value = row[column].strip()
            if value in {"", "-", "N/A"}:
                entry[key] = None
                continue
            number = float(value.removesuffix("%").replace(",", "")) / 100
            if not math.isfinite(number):
                raise ValueError("nonfinite group performance")
            entry[key] = number
        if any(entry[key] is not None for key in ELITE_COLUMNS.values()):
            rows.append(entry)
    return rows


def _get_performance(group: str, api_key: Optional[str]) -> list[dict]:
    key = os.environ.get("FINVIZ_API_KEY", "") if api_key is None else api_key
    if key:
        try:
            response = requests.get(
                GROUP_EXPORT_URL,
                params={"g": group.lower(), "v": "140", "o": "name", "auth": key},
                timeout=15,
                allow_redirects=False,
            )
            if response.status_code == 200:
                rows = _elite_csv_rows(response.text)
                if rows:
                    return rows
        except (requests.RequestException, ValueError, csv.Error):
            pass  # Report only static text: exceptions and bodies may contain auth.
        print(
            "WARNING: FINVIZ Elite group export unavailable; trying public fallback.",
            file=sys.stderr,
        )

    guidance = (
        "Use Python 3.10+ and install theme-detector requirements "
        "(finvizfinance>=1.5.0), or configure FINVIZ_API_KEY for Elite."
    )
    if sys.version_info < (3, 10) or not HAS_FINVIZFINANCE:
        print(f"WARNING: FINVIZ public group data unavailable. {guidance}", file=sys.stderr)
        return []
    try:
        rows = _dataframe_to_dicts(fvperf.Performance().screener_view(group=group))
        if rows:
            return rows
    except Exception:
        # Third-party scraper exceptions may embed full request URLs/bodies.
        # Keep its failure soft and diagnostic entirely independent of values.
        pass
    print(f"WARNING: FINVIZ public group fetch failed. {guidance}", file=sys.stderr)
    return []


def get_sector_performance(api_key: Optional[str] = None) -> list[dict]:
    """Sector decimal ratios: prefer Elite key, then public Python3.10+ scraper.

    None resolves FINVIZ_API_KEY; an explicit empty string forces public-only.
    """
    return _get_performance("Sector", api_key)


def get_industry_performance(api_key: Optional[str] = None) -> list[dict]:
    """Industry decimal ratios with the same source/key policy as sectors."""
    return _get_performance("Industry", api_key)
