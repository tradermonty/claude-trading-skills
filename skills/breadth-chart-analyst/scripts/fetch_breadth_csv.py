#!/usr/bin/env python3
"""
Fetch and analyze market breadth data from CSV sources.

PRIMARY data source for Breadth analysis, replacing OpenCV image detection.
Uses only stdlib (urllib.request + csv) -- no external dependencies.

Data Sources:
  - Market Breadth: sydcurie.github.io/market-breadth-analysis/market_breadth_data.csv
  - Uptrend Ratio:  raw.githubusercontent.com/sydcurie/uptrend-dashboard/main/data/uptrend_ratio_timeseries.csv
  - Sector Summary: raw.githubusercontent.com/sydcurie/uptrend-dashboard/main/data/sector_summary.csv
"""

import argparse
import csv
import io
import json
import sys
import urllib.request
from dataclasses import asdict, dataclass
from typing import Optional

# --- Constants ---

BREADTH_CSV_URL = "https://sydcurie.github.io/market-breadth-analysis/market_breadth_data.csv"
UPTREND_CSV_URL = (
    "https://raw.githubusercontent.com/sydcurie/uptrend-dashboard/"
    "main/data/uptrend_ratio_timeseries.csv"
)
SECTOR_CSV_URL = (
    "https://raw.githubusercontent.com/sydcurie/uptrend-dashboard/main/data/sector_summary.csv"
)

# --- Threshold classifications ---

BREADTH_200MA_THRESHOLDS = [
    (60.0, "healthy"),
    (50.0, "narrow_rally"),
    (40.0, "caution"),
    (0.0, "fragile"),
]

BREADTH_8MA_THRESHOLDS = [
    (73.0, "overbought"),
    (60.0, "healthy_bullish"),
    (40.0, "neutral"),
    (23.0, "bearish"),
    (0.0, "oversold"),
]

UPTREND_THRESHOLDS = [
    (37.0, "overbought"),
    (30.0, "neutral_bullish"),
    (20.0, "neutral"),
    (15.0, "neutral_bearish"),
    (0.0, "bearish"),
]


# --- Data classes ---


@dataclass
class BreadthData:
    date: str
    sp500_price: Optional[float]
    breadth_raw: Optional[float]
    breadth_200ma: Optional[float]
    breadth_8ma: Optional[float]
    trend: Optional[str]


@dataclass
class UptrendData:
    date: str
    ratio: Optional[float]
    ma_10: Optional[float]
    slope: Optional[float]
    trend: Optional[str]


@dataclass
class SectorData:
    sector: str
    ratio: Optional[float]
    ma_10: Optional[float]
    trend: Optional[str]
    slope: Optional[float]
    status: Optional[str]


@dataclass
class AnalysisResult:
    # Breadth
    breadth_date: str
    breadth_200ma: float
    breadth_200ma_class: str
    breadth_8ma: float
    breadth_8ma_class: str
    dead_cross: bool
    cross_diff: float
    breadth_trend: str
    # Uptrend
    uptrend_date: str
    uptrend_ratio: float
    uptrend_color: str
    uptrend_class: str
    uptrend_ma10: float
    uptrend_slope: float
    uptrend_trend: str
    # Sectors
    sectors: list


# --- Classification helpers ---


def classify_value(value: float, thresholds: list) -> str:
    """Classify a value based on threshold ranges (descending order)."""
    for threshold, label in thresholds:
        if value >= threshold:
            return label
    return thresholds[-1][1]


def classify_breadth_200ma(value: float) -> str:
    return classify_value(value, BREADTH_200MA_THRESHOLDS)


def classify_breadth_8ma(value: float) -> str:
    return classify_value(value, BREADTH_8MA_THRESHOLDS)


def classify_uptrend(value: float) -> str:
    return classify_value(value, UPTREND_THRESHOLDS)


def is_dead_cross(breadth_8ma: float, breadth_200ma: float) -> bool:
    """Dead cross = 8MA below 200MA."""
    return breadth_8ma < breadth_200ma


def uptrend_color(trend: Optional[str]) -> str:
    """Convert trend string to color: up/1 -> GREEN, down/-1 -> RED."""
    if trend is None:
        return "UNKNOWN"
    t = trend.strip().lower()
    if t in ("up", "uptrend", "1"):
        return "GREEN"
    elif t in ("down", "downtrend", "-1"):
        return "RED"
    return "UNKNOWN"


# --- CSV fetching ---


def fetch_csv(url: str, timeout: int = 30) -> list:
    """Fetch CSV from URL and return list of dicts."""
    req = urllib.request.Request(url, headers={"User-Agent": "breadth-csv-fetcher/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def fetch_breadth_data(url: str = BREADTH_CSV_URL) -> list:
    """Fetch market breadth CSV data."""
    rows = fetch_csv(url)
    results = []
    for row in rows:
        try:
            results.append(
                BreadthData(
                    date=row.get("Date", "").strip(),
                    sp500_price=_float_or_none(row.get("S&P500_Price") or row.get("SP500_Price")),
                    breadth_raw=_float_or_none(row.get("Breadth_Index_Raw")),
                    breadth_200ma=_float_or_none(
                        row.get("Breadth_Index_200MA") or row.get("Breadth_200MA")
                    ),
                    breadth_8ma=_float_or_none(
                        row.get("Breadth_Index_8MA") or row.get("Breadth_8MA")
                    ),
                    trend=(row.get("Breadth_200MA_Trend", "") or row.get("Trend", "")).strip()
                    or None,
                )
            )
        except (ValueError, KeyError):
            continue
    return results


def fetch_uptrend_data(url: str = UPTREND_CSV_URL, worksheet: str = "all") -> list:
    """Fetch uptrend ratio CSV data, filtered by worksheet."""
    rows = fetch_csv(url)
    results = []
    for row in rows:
        ws = row.get("worksheet", "").strip().lower()
        if ws != worksheet.lower():
            continue
        try:
            results.append(
                UptrendData(
                    date=row.get("date", "").strip(),
                    ratio=_float_or_none(row.get("ratio")),
                    ma_10=_float_or_none(row.get("ma_10")),
                    slope=_float_or_none(row.get("slope")),
                    trend=row.get("trend", "").strip() or None,
                )
            )
        except (ValueError, KeyError):
            continue
    return results


def fetch_sector_data(url: str = SECTOR_CSV_URL) -> list:
    """Fetch sector summary CSV data."""
    rows = fetch_csv(url)
    results = []
    for row in rows:
        try:
            results.append(
                SectorData(
                    sector=row.get("Sector", "").strip(),
                    ratio=_float_or_none(row.get("Ratio")),
                    ma_10=_float_or_none(row.get("10MA")),
                    trend=row.get("Trend", "").strip() or None,
                    slope=_float_or_none(row.get("Slope")),
                    status=row.get("Status", "").strip() or None,
                )
            )
        except (ValueError, KeyError):
            continue
    return results


def _float_or_none(val) -> Optional[float]:
    """Convert to float or return None."""
    if val is None:
        return None
    val = str(val).strip()
    if val == "" or val.lower() in ("na", "nan", "none", "null"):
        return None
    return float(val)


# --- Analysis ---


def analyze(
    breadth_rows: list,
    uptrend_rows: list,
    sector_rows: list,
    days: int = 1,
) -> AnalysisResult:
    """Analyze the latest breadth data and return structured result."""
    # Latest breadth row(s)
    if not breadth_rows:
        raise ValueError("No breadth data available")
    latest_breadth = breadth_rows[-1]

    # Latest uptrend row(s)
    if not uptrend_rows:
        raise ValueError("No uptrend data available")
    latest_uptrend = uptrend_rows[-1]

    b200 = latest_breadth.breadth_200ma
    b8 = latest_breadth.breadth_8ma
    if b200 is None or b8 is None:
        raise ValueError(f"Missing breadth MA values for {latest_breadth.date}")

    # Convert breadth values from decimal to percentage if needed
    b200_pct = b200 * 100.0 if b200 <= 1.0 else b200
    b8_pct = b8 * 100.0 if b8 <= 1.0 else b8

    ratio = latest_uptrend.ratio
    if ratio is None:
        raise ValueError(f"Missing uptrend ratio for {latest_uptrend.date}")
    ratio_pct = ratio * 100.0 if ratio <= 1.0 else ratio

    ma10 = latest_uptrend.ma_10
    ma10_pct = (ma10 * 100.0 if ma10 <= 1.0 else ma10) if ma10 is not None else 0.0

    slope = latest_uptrend.slope if latest_uptrend.slope is not None else 0.0

    cross_diff = b8_pct - b200_pct

    # Sector analysis
    sectors = []
    for s in sector_rows:
        r = s.ratio
        if r is not None:
            r_pct = r * 100.0 if r <= 1.0 else r
        else:
            r_pct = None
        sectors.append(
            {
                "sector": s.sector,
                "ratio": r_pct,
                "trend": s.trend,
                "status": s.status,
            }
        )

    return AnalysisResult(
        breadth_date=latest_breadth.date,
        breadth_200ma=round(b200_pct, 2),
        breadth_200ma_class=classify_breadth_200ma(b200_pct),
        breadth_8ma=round(b8_pct, 2),
        breadth_8ma_class=classify_breadth_8ma(b8_pct),
        dead_cross=is_dead_cross(b8_pct, b200_pct),
        cross_diff=round(cross_diff, 2),
        breadth_trend=latest_breadth.trend or "UNKNOWN",
        uptrend_date=latest_uptrend.date,
        uptrend_ratio=round(ratio_pct, 2),
        uptrend_color=uptrend_color(latest_uptrend.trend),
        uptrend_class=classify_uptrend(ratio_pct),
        uptrend_ma10=round(ma10_pct, 2),
        uptrend_slope=round(slope, 4),
        uptrend_trend=latest_uptrend.trend or "UNKNOWN",
        sectors=sectors,
    )


# --- Output formatting ---


def format_human(result: AnalysisResult) -> str:
    """Format analysis result as human-readable text."""
    lines = []
    lines.append("=" * 60)
    lines.append(f"Breadth Data (CSV) - {result.breadth_date}")
    lines.append("=" * 60)
    lines.append("")

    # Market Breadth
    lines.append("--- Market Breadth (S&P 500) ---")
    lines.append(
        f"200-Day MA: {result.breadth_200ma:.2f}% ({result.breadth_200ma_class} "
        f"({_threshold_range(result.breadth_200ma, BREADTH_200MA_THRESHOLDS)}))"
    )
    lines.append(
        f"8-Day MA:   {result.breadth_8ma:.2f}% ({result.breadth_8ma_class} "
        f"({_threshold_range(result.breadth_8ma, BREADTH_8MA_THRESHOLDS)}))"
    )

    cross_sign = "+" if result.cross_diff >= 0 else ""
    cross_desc = (
        "8MA ABOVE -- NO dead cross" if not result.dead_cross else "8MA BELOW -- DEAD CROSS"
    )
    lines.append(f"8MA vs 200MA: {cross_sign}{result.cross_diff:.2f}pt ({cross_desc})")
    lines.append(f"Trend: {result.breadth_trend.upper()}")
    lines.append("")

    # Uptrend Ratio
    lines.append("--- Uptrend Ratio (All Markets) ---")
    lines.append(
        f"Current: {result.uptrend_ratio:.2f}% {result.uptrend_color} ({result.uptrend_class})"
    )
    lines.append(
        f"10MA: {result.uptrend_ma10:.2f}%, "
        f"Slope: {result.uptrend_slope:+.4f}, "
        f"Trend: {result.uptrend_trend.upper()}"
    )
    lines.append("")

    # Sector Summary
    if result.sectors:
        lines.append("--- Sector Summary ---")
        overbought = [s for s in result.sectors if s.get("status", "").lower() == "overbought"]
        oversold = [s for s in result.sectors if s.get("status", "").lower() == "oversold"]
        uptrend_sectors = [
            s for s in result.sectors if s.get("trend", "").lower() in ("up", "uptrend")
        ]
        downtrend_sectors = [
            s for s in result.sectors if s.get("trend", "").lower() in ("down", "downtrend")
        ]

        if overbought:
            ob_str = ", ".join(
                f"{s['sector']} ({s['ratio']:.1f}%)" if s["ratio"] else s["sector"]
                for s in overbought
            )
            lines.append(f"Overbought: {ob_str}")
        if oversold:
            os_str = ", ".join(
                f"{s['sector']} ({s['ratio']:.1f}%)" if s["ratio"] else s["sector"]
                for s in oversold
            )
            lines.append(f"Oversold: {os_str}")
        if uptrend_sectors:
            up_str = ", ".join(
                f"{s['sector']} ({s['ratio']:.1f}%)" if s["ratio"] else s["sector"]
                for s in uptrend_sectors
            )
            lines.append(f"Uptrend: {up_str}")
        if downtrend_sectors:
            dn_str = ", ".join(
                f"{s['sector']} ({s['ratio']:.1f}%)" if s["ratio"] else s["sector"]
                for s in downtrend_sectors
            )
            lines.append(f"Downtrend: {dn_str}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_json(result: AnalysisResult) -> str:
    """Format analysis result as JSON."""
    return json.dumps(asdict(result), indent=2, ensure_ascii=False)


def _threshold_range(value: float, thresholds: list) -> str:
    """Return a human-readable description of the threshold range."""
    for i, (threshold, _) in enumerate(thresholds):
        if value >= threshold:
            if i == 0:
                return f">={threshold}%"
            else:
                upper = thresholds[i - 1][0]
                return f"{threshold}-{upper}%"
    last_threshold = thresholds[-1][0]
    return f"<{last_threshold}%"


# --- CLI ---


def main():
    parser = argparse.ArgumentParser(
        description="Fetch and analyze market breadth data from CSV sources"
    )
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of recent days to analyze (default: 1)",
    )
    args = parser.parse_args()

    try:
        breadth_rows = fetch_breadth_data()
        uptrend_rows = fetch_uptrend_data()
        sector_rows = fetch_sector_data()

        result = analyze(breadth_rows, uptrend_rows, sector_rows, days=args.days)

        if args.json:
            print(format_json(result))
        else:
            print(format_human(result))

    except urllib.error.URLError as e:
        print(f"ERROR: Failed to fetch CSV data: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"ERROR: Data analysis failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
