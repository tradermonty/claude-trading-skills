#!/usr/bin/env python3
"""
Market Breadth Analyzer - CSV Data Client

Fetches and parses market breadth CSV data from TraderMonty's public GitHub Pages.
No API key required.

Data sources:
  Detail:  https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv
  Summary: https://tradermonty.github.io/market-breadth-analysis/market_breadth_summary.csv
"""

import csv
import io
import math
import sys
from datetime import datetime
from typing import Optional

import requests

DEFAULT_DETAIL_URL = "https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv"
DEFAULT_SUMMARY_URL = (
    "https://tradermonty.github.io/market-breadth-analysis/market_breadth_summary.csv"
)

DETAIL_COLUMNS = {
    "Date": str,
    "S&P500_Price": float,
    "Breadth_Index_Raw": float,
    "Breadth_Index_200MA": float,
    "Breadth_Index_8MA": float,
    "Breadth_200MA_Trend": int,
    "Bearish_Signal": bool,
    "Is_Peak": bool,
    "Is_Trough": bool,
    "Is_Trough_8MA_Below_04": bool,
}

TIMEOUT = 30

SUMMARY_COLUMNS = ("Metric", "Value")
REQUIRED_SUMMARY_METRICS = ("Average Peaks (200MA)", "Average Troughs (8MA < 0.4)")


def _open_reader(text: str) -> csv.DictReader:
    """Build a DictReader with a BOM-free text and whitespace-stripped header names.

    DictReader row keys come from ``fieldnames``, so stripping them once here keeps
    the header check and the row lookups consistent.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if reader.fieldnames is not None:
        reader.fieldnames = [(name or "").strip() for name in reader.fieldnames]
    return reader


def _read_csv(text: str, filename: str) -> Optional[tuple[list[str], list[dict]]]:
    """Parse a whole CSV body; report an unparsable body (NUL, oversized field) once."""
    try:
        reader = _open_reader(text)
        return list(reader.fieldnames or []), list(reader)
    except csv.Error as exc:
        print("FAILED")
        print(f"ERROR: {filename} schema drift: unparsable CSV ({exc})", file=sys.stderr)
        return None


def _missing_columns(fieldnames, required) -> list[str]:
    """Return sorted required columns absent from a header normalized by _open_reader."""
    return sorted(set(required) - set(fieldnames or []))


def _report_drift(filename: str, missing: list[str]) -> None:
    print(
        f"ERROR: {filename} schema drift: missing columns [{','.join(missing)}]",
        file=sys.stderr,
    )


def fetch_detail_csv(url: str = DEFAULT_DETAIL_URL) -> list[dict]:
    """
    Fetch and parse the detail CSV (market_breadth_data.csv).

    Returns list of dicts sorted by date ascending (oldest first).
    """
    print(f"  Fetching detail CSV from {url}...", end=" ", flush=True)
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print("FAILED")
        print(f"ERROR: Failed to fetch detail CSV: {e}", file=sys.stderr)
        return []

    parsed = _read_csv(resp.text, "market_breadth_data.csv")
    if parsed is None:
        return []
    fieldnames, raw_rows = parsed
    missing = _missing_columns(fieldnames, DETAIL_COLUMNS)
    if missing:
        print("FAILED")
        _report_drift("market_breadth_data.csv", missing)
        return []

    rows = []

    for line_num, raw_row in enumerate(raw_rows, start=2):
        try:
            row = _parse_detail_row(raw_row)
            rows.append(row)
        except (ValueError, KeyError) as e:
            print(f"\n  WARN: Skipping line {line_num}: {e}", file=sys.stderr)

    if not rows:
        print("OK (0 rows)")
        return []

    # Sort by date ascending
    rows.sort(key=lambda r: r["Date"])

    print(f"OK ({len(rows)} rows, {rows[0]['Date']} to {rows[-1]['Date']})")
    return rows


def fetch_summary_csv(url: str = DEFAULT_SUMMARY_URL) -> dict[str, str]:
    """
    Fetch and parse the summary CSV (market_breadth_summary.csv).

    Returns dict mapping Metric -> Value.
    """
    print(f"  Fetching summary CSV from {url}...", end=" ", flush=True)
    try:
        resp = requests.get(url, timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print("FAILED")
        print(f"ERROR: Failed to fetch summary CSV: {e}", file=sys.stderr)
        return {}

    parsed = _read_csv(resp.text, "market_breadth_summary.csv")
    if parsed is None:
        return {}
    fieldnames, raw_rows = parsed
    missing = _missing_columns(fieldnames, SUMMARY_COLUMNS)
    if missing:
        print("FAILED")
        _report_drift("market_breadth_summary.csv", missing)
        return {}

    summary = {}
    for line_num, raw_row in enumerate(raw_rows, start=2):
        raw_metric = raw_row.get("Metric")
        raw_value = raw_row.get("Value")
        if raw_metric is None or raw_value is None:
            print(f"\n  WARN: Skipping summary line {line_num}: truncated row", file=sys.stderr)
            continue
        metric = raw_metric.strip()
        value = raw_value.strip()
        if metric:
            summary[metric] = value

    print(f"OK ({len(summary)} metrics)")
    for name in REQUIRED_SUMMARY_METRICS:
        if name not in summary:
            print(f"WARN: market_breadth_summary.csv missing metric '{name}'", file=sys.stderr)
    return summary


def check_data_freshness(
    rows: list[dict], max_stale_days: int = 5, detail_url: str = DEFAULT_DETAIL_URL
) -> dict:
    """
    Check whether the latest data is reasonably fresh.
    Uses both CSV date and HTTP Last-Modified header for accuracy.

    Args:
        rows: Parsed detail rows (sorted by date ascending).
        max_stale_days: Calendar days before data is considered stale.
        detail_url: URL to check Last-Modified header against.

    Returns:
        Dict with is_fresh, latest_date, days_old, last_modified, warning.
    """
    if not rows:
        return {
            "is_fresh": False,
            "latest_date": None,
            "days_old": None,
            "last_modified": None,
            "warning": "No data available",
        }

    latest_date_str = rows[-1]["Date"]
    try:
        latest_date = datetime.strptime(latest_date_str, "%Y-%m-%d")
    except ValueError:
        return {
            "is_fresh": False,
            "latest_date": latest_date_str,
            "days_old": None,
            "last_modified": None,
            "warning": f"Cannot parse latest date: {latest_date_str}",
        }

    days_old = (datetime.now() - latest_date).days
    is_fresh = days_old <= max_stale_days

    # Check HTTP Last-Modified header for additional freshness info
    last_modified = _check_last_modified(detail_url)

    warning = None
    if last_modified is None:
        warning = "Degraded freshness check: HTTP Last-Modified unavailable; using CSV date only."
    if not is_fresh:
        warning = (
            (warning + " " if warning else "")
            + f"Data is {days_old} days old (latest: {latest_date_str}). "
            f"Threshold: {max_stale_days} days. Results may not reflect current conditions."
        )

    return {
        "is_fresh": is_fresh,
        "latest_date": latest_date_str,
        "days_old": days_old,
        "last_modified": last_modified,
        "warning": warning,
    }


def _check_last_modified(url: str) -> Optional[str]:
    """Check HTTP Last-Modified header via HEAD request."""
    try:
        resp = requests.head(url, timeout=10, allow_redirects=True)
        resp.raise_for_status()
        lm = resp.headers.get("Last-Modified")
        if lm:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(lm)
            return dt.strftime("%Y-%m-%d %H:%M UTC")
    except (requests.RequestException, ValueError, TypeError, OverflowError):
        print("WARN: Degraded freshness check; HTTP Last-Modified unavailable", file=sys.stderr)
    return None


def get_latest_n_rows(rows: list[dict], n: int) -> list[dict]:
    """Return the last n rows (most recent)."""
    return rows[-n:] if len(rows) >= n else rows[:]


def _parse_detail_row(raw: dict) -> dict:
    """Convert a raw CSV row dict to properly typed values."""
    missing = [column for column in DETAIL_COLUMNS if raw.get(column) is None]
    if missing:
        raise ValueError(f"missing values for: {', '.join(missing)}")

    row = {}
    row["Date"] = raw["Date"].strip()
    try:
        parsed_date = datetime.strptime(row["Date"], "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"invalid Date: {row['Date']!r}") from exc
    if parsed_date.strftime("%Y-%m-%d") != row["Date"]:
        raise ValueError(f"invalid Date: {row['Date']!r}")
    row["S&P500_Price"] = _parse_finite_float(raw["S&P500_Price"], "S&P500_Price")
    row["Breadth_Index_Raw"] = _parse_finite_float(raw["Breadth_Index_Raw"], "Breadth_Index_Raw")
    row["Breadth_Index_200MA"] = _parse_finite_float(
        raw["Breadth_Index_200MA"], "Breadth_Index_200MA"
    )
    row["Breadth_Index_8MA"] = _parse_finite_float(raw["Breadth_Index_8MA"], "Breadth_Index_8MA")
    row["Breadth_200MA_Trend"] = int(raw["Breadth_200MA_Trend"])
    row["Bearish_Signal"] = _parse_bool(raw["Bearish_Signal"])
    row["Is_Peak"] = _parse_bool(raw["Is_Peak"])
    row["Is_Trough"] = _parse_bool(raw["Is_Trough"])
    row["Is_Trough_8MA_Below_04"] = _parse_bool(raw["Is_Trough_8MA_Below_04"])
    return row


def _parse_finite_float(val: str, column: str) -> float:
    """Parse a CSV number and reject NaN/Infinity before scoring."""
    parsed = float(val)
    if not math.isfinite(parsed):
        raise ValueError(f"{column} must be finite")
    return parsed


def _parse_bool(val: str) -> bool:
    """Parse boolean from CSV string."""
    normalized = val.strip().lower()
    if normalized in ("true", "1", "yes"):
        return True
    if normalized in ("false", "0", "no"):
        return False
    raise ValueError(f"invalid boolean value: {val!r}")


# Testing
if __name__ == "__main__":
    print("Testing CSV Client...\n")

    detail = fetch_detail_csv()
    print(f"  Detail rows: {len(detail)}")
    if detail:
        print(f"  First row: {detail[0]}")
        print(f"  Last row:  {detail[-1]}")

    print()
    summary = fetch_summary_csv()
    print(f"  Summary metrics: {summary}")

    print()
    freshness = check_data_freshness(detail)
    print(f"  Freshness: {freshness}")

    print("\nAll tests completed.")
