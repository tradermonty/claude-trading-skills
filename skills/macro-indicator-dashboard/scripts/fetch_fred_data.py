#!/usr/bin/env python3
"""Fetch a curated set of FRED series and emit a single JSON file.

Usage:
    python3 fetch_fred_data.py [--api-key KEY] [--output PATH] [--years 10]

Environment:
    FRED_API_KEY    (preferred over --api-key)

Output JSON shape:
    {
      "as_of": "YYYY-MM-DD",
      "series": {
        "FEDFUNDS": {"frequency": "monthly", "observations": [{"date": "...", "value": 5.33}, ...]},
        ...
      },
      "fetch_errors": []
    }
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

try:
    import requests
except ImportError:
    print("error: requests not installed. Run: pip3 install --break-system-packages requests", file=sys.stderr)
    sys.exit(2)


# Curated catalog. See references/series_catalog.md for full descriptions.
SERIES = [
    # Rates & yield curve
    ("FEDFUNDS", "monthly"),
    ("DGS2", "daily"),
    ("DGS10", "daily"),
    ("T10Y2Y", "daily"),
    ("T10Y3M", "daily"),
    # Credit conditions
    ("BAMLH0A0HYM2", "daily"),
    ("BAMLC0A0CM", "daily"),
    ("NFCI", "weekly"),
    # Labor
    ("PAYEMS", "monthly"),
    ("UNRATE", "monthly"),
    ("ICSA", "weekly"),
    # Real economy
    ("INDPRO", "monthly"),
    # Inflation
    ("CPIAUCSL", "monthly"),
    ("CPILFESL", "monthly"),
    ("PCEPI", "monthly"),
    ("T5YIE", "daily"),
    # Monetary
    ("M2SL", "monthly"),
    ("RRPONTSYD", "daily"),
]

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"


def fetch_series(series_id: str, api_key: str, start: str) -> dict[str, Any]:
    """Fetch a single FRED series. Returns dict with observations or raises."""
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start,
    }
    url = f"{FRED_BASE}?{urlencode(params)}"
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=20)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"HTTP {r.status_code} for {series_id}: {r.text[:200]}")
        except requests.RequestException as e:
            if attempt == 2:
                raise RuntimeError(f"Network error for {series_id}: {e}") from e
            time.sleep(1 + attempt)
    raise RuntimeError(f"Exhausted retries for {series_id}")


def normalize_observations(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert FRED's observation list to {date, value} pairs, dropping missing data."""
    out = []
    for obs in raw.get("observations", []):
        val = obs.get("value", ".")
        if val == "." or val == "":
            continue
        try:
            out.append({"date": obs["date"], "value": float(val)})
        except (ValueError, KeyError):
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api-key", default=os.environ.get("FRED_API_KEY"))
    ap.add_argument("--output", type=Path, default=None,
                    help="Output JSON path. Defaults to reports/macro_raw_<date>.json")
    ap.add_argument("--years", type=int, default=10,
                    help="Years of history to pull (default 10, min 3 recommended)")
    args = ap.parse_args()

    if not args.api_key:
        print("error: FRED_API_KEY not set. Get a free key at "
              "https://fred.stlouisfed.org/docs/api/api_key.html", file=sys.stderr)
        return 2

    today = dt.date.today()
    start = (today - dt.timedelta(days=365 * args.years)).isoformat()
    output_path = args.output or Path(f"reports/macro_raw_{today.isoformat()}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    out: dict[str, Any] = {
        "as_of": today.isoformat(),
        "series": {},
        "fetch_errors": [],
    }

    for series_id, freq in SERIES:
        print(f"Fetching {series_id} ({freq})...", file=sys.stderr)
        try:
            raw = fetch_series(series_id, args.api_key, start)
            obs = normalize_observations(raw)
            if not obs:
                out["fetch_errors"].append(f"{series_id}: no observations returned")
                continue
            out["series"][series_id] = {
                "frequency": freq,
                "observations": obs,
                "latest_date": obs[-1]["date"],
                "latest_value": obs[-1]["value"],
            }
            time.sleep(0.05)  # be polite
        except Exception as e:
            print(f"  ERROR: {e}", file=sys.stderr)
            out["fetch_errors"].append(f"{series_id}: {e}")

    with output_path.open("w") as f:
        json.dump(out, f, indent=2)

    print(f"\nWrote {output_path}", file=sys.stderr)
    print(f"  Series fetched: {len(out['series'])}/{len(SERIES)}", file=sys.stderr)
    print(f"  Errors: {len(out['fetch_errors'])}", file=sys.stderr)

    return 0 if not out["fetch_errors"] or len(out["series"]) >= len(SERIES) - 2 else 1


if __name__ == "__main__":
    sys.exit(main())
