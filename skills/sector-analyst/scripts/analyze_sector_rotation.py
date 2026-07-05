#!/usr/bin/env python3
"""Sector rotation analysis from TraderMonty's public CSV data.

.. note:: Uses ``from __future__ import annotations`` for Python 3.9 compat.

Fetches sector_summary.csv (and uptrend_ratio_timeseries.csv for freshness
check) from GitHub, then produces sector rankings, risk-regime scoring,
overbought/oversold flags, and market-cycle phase estimation.

Data Source:
  https://github.com/tradermonty/uptrend-dashboard

Dependencies: stdlib only (urllib, csv, json, argparse, dataclasses).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SECTOR_CSV_URL = (
    "https://raw.githubusercontent.com/tradermonty/uptrend-dashboard/main/data/sector_summary.csv"
)
UPTREND_CSV_URL = (
    "https://raw.githubusercontent.com/tradermonty/uptrend-dashboard"
    "/main/data/uptrend_ratio_timeseries.csv"
)

# Sector classification — aligned with uptrend-analyzer's
# sector_rotation_calculator.py (L31-47).
CYCLICAL_SECTORS = [
    "Technology",
    "Consumer Cyclical",
    "Communication Services",
    "Financial",
    "Industrials",
]
DEFENSIVE_SECTORS = [
    "Utilities",
    "Consumer Defensive",
    "Healthcare",
    "Real Estate",
]
COMMODITY_SECTORS = [
    "Energy",
    "Basic Materials",
]

# Overbought / oversold thresholds (uptrend ratio scale).
OVERBOUGHT_THRESHOLD = 0.37
OVERSOLD_THRESHOLD = 0.097

# Freshness: warn if data is older than this many days.
FRESHNESS_MAX_DAYS = 5

# Cycle phase definitions: which sectors lead/lag in each phase.
CYCLE_PHASES = {
    "early": {
        "leaders": ["Technology", "Consumer Cyclical", "Industrials", "Financial"],
        "laggards": ["Utilities", "Consumer Defensive", "Healthcare"],
    },
    "mid": {
        "leaders": ["Technology", "Industrials", "Consumer Cyclical", "Energy"],
        "laggards": ["Utilities", "Consumer Defensive"],
    },
    "late": {
        "leaders": ["Energy", "Basic Materials", "Healthcare"],
        "laggards": ["Technology", "Consumer Cyclical", "Industrials"],
    },
    "recession": {
        "leaders": ["Utilities", "Consumer Defensive", "Healthcare"],
        "laggards": ["Technology", "Consumer Cyclical", "Industrials", "Financial"],
    },
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


@dataclass
class SectorData:
    """Parsed sector row."""

    sector: str
    ratio: float
    ma_10: float | None
    trend: str
    slope: float | None
    status: str


# ---------------------------------------------------------------------------
# CSV Fetching
# ---------------------------------------------------------------------------


# Required columns for sector_summary.csv validation.
REQUIRED_COLUMNS = {"Sector", "Ratio"}
EXPECTED_COLUMNS = {"Sector", "Ratio", "10MA", "Trend", "Slope", "Status"}


def fetch_csv(url: str, timeout: int = 30) -> list[dict]:
    """Fetch a CSV from *url* and return rows as list of dicts."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sector-analyst/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
    except urllib.error.URLError as exc:
        print(f"ERROR: Failed to fetch {url}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def validate_columns(raw_rows: list[dict]) -> None:
    """Validate that required columns exist in CSV data.

    Raises ValueError if required columns are missing.
    Prints a warning if optional expected columns are missing.
    """
    if not raw_rows:
        return
    actual = set(raw_rows[0].keys())
    missing_required = REQUIRED_COLUMNS - actual
    if missing_required:
        raise ValueError(f"Missing required columns: {sorted(missing_required)}")
    missing_optional = EXPECTED_COLUMNS - REQUIRED_COLUMNS - actual
    if missing_optional:
        print(
            f"WARNING: Missing optional columns: {sorted(missing_optional)}",
            file=sys.stderr,
        )


def parse_sector_rows(raw_rows: list[dict]) -> list[SectorData]:
    """Convert raw CSV dicts to SectorData, skipping invalid rows."""
    result: list[SectorData] = []
    for row in raw_rows:
        sector = row.get("Sector", "").strip()
        if not sector:
            continue
        ratio_str = row.get("Ratio", "").strip()
        if not ratio_str:
            continue
        try:
            ratio = float(ratio_str)
        except ValueError:
            continue

        ma_10 = _safe_float(row.get("10MA", ""))
        slope = _safe_float(row.get("Slope", ""))
        trend = row.get("Trend", "").strip()
        status = row.get("Status", "").strip()

        result.append(SectorData(sector, ratio, ma_10, trend, slope, status))
    return result


def check_freshness(uptrend_csv_url: str, timeout: int = 30) -> dict | None:
    """Check data freshness using max(date) from uptrend timeseries CSV.

    Returns dict with 'date', 'is_fresh', 'warning' or None on failure.
    Fetch failures are treated as non-fatal (returns None with no ERROR log).
    """
    try:
        req = urllib.request.Request(uptrend_csv_url, headers={"User-Agent": "sector-analyst/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8")
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except (urllib.error.URLError, OSError):
        return None

    if not rows:
        return None

    dates: list[str] = []
    for row in rows:
        d = row.get("date", "").strip()
        if d:
            dates.append(d)

    if not dates:
        return None

    max_date_str = max(dates)
    try:
        max_date = datetime.strptime(max_date_str, "%Y-%m-%d").date()
    except ValueError:
        return None

    days_old = (date.today() - max_date).days
    is_fresh = days_old <= FRESHNESS_MAX_DAYS
    warning = None if is_fresh else f"Data is {days_old} days old (latest: {max_date_str})"

    return {"date": max_date_str, "is_fresh": is_fresh, "warning": warning}


# ---------------------------------------------------------------------------
# Analysis Functions
# ---------------------------------------------------------------------------


def rank_sectors(sectors: list[SectorData]) -> list[dict]:
    """Rank sectors by ratio descending."""
    sorted_sectors = sorted(sectors, key=lambda s: s.ratio, reverse=True)
    return [
        {
            "rank": i + 1,
            "sector": s.sector,
            "ratio": s.ratio,
            "ratio_pct": round(s.ratio * 100, 1),
            "trend": s.trend,
            "slope": s.slope,
            "status": s.status,
        }
        for i, s in enumerate(sorted_sectors)
    ]


def analyze_groups(sectors: list[SectorData]) -> dict:
    """Analyze cyclical/defensive/commodity groups and determine risk regime."""
    sector_map = {s.sector: s for s in sectors}

    cyclical_ratios = _get_group_ratios(sector_map, CYCLICAL_SECTORS)
    defensive_ratios = _get_group_ratios(sector_map, DEFENSIVE_SECTORS)
    commodity_ratios = _get_group_ratios(sector_map, COMMODITY_SECTORS)

    cyclical_avg = _avg(cyclical_ratios) if cyclical_ratios else None
    defensive_avg = _avg(defensive_ratios) if defensive_ratios else None
    commodity_avg = _avg(commodity_ratios) if commodity_ratios else None

    if cyclical_avg is None or defensive_avg is None:
        return {
            "cyclical_avg": cyclical_avg,
            "defensive_avg": defensive_avg,
            "commodity_avg": commodity_avg,
            "difference": None,
            "score": 50,
            "regime": "incomplete data",
            "late_cycle_flag": False,
            "divergence_flag": False,
        }

    difference = cyclical_avg - defensive_avg
    base_score = _difference_to_score(difference)

    # Commodity adjustment
    late_cycle_flag = False
    commodity_penalty = 0
    if commodity_avg is not None:
        if commodity_avg > cyclical_avg and commodity_avg > defensive_avg:
            late_cycle_flag = True
            excess = commodity_avg - max(cyclical_avg, defensive_avg)
            commodity_penalty = -10 if excess > 0.10 else -5

    # Divergence detection
    divergence_result = _calculate_group_divergence(sector_map)
    divergence_penalty = divergence_result.get("divergence_penalty", 0)

    score = round(min(100, max(0, base_score + commodity_penalty + divergence_penalty)))
    regime = _score_to_regime(score)

    return {
        "cyclical_avg": round(cyclical_avg, 4),
        "cyclical_avg_pct": round(cyclical_avg * 100, 1),
        "defensive_avg": round(defensive_avg, 4),
        "defensive_avg_pct": round(defensive_avg * 100, 1),
        "commodity_avg": round(commodity_avg, 4) if commodity_avg is not None else None,
        "commodity_avg_pct": round(commodity_avg * 100, 1) if commodity_avg is not None else None,
        "difference": round(difference, 4),
        "difference_pct": round(difference * 100, 1),
        "score": score,
        "regime": regime,
        "late_cycle_flag": late_cycle_flag,
        "commodity_penalty": commodity_penalty,
        "divergence_flag": divergence_result.get("divergence_flag", False),
        "divergence_penalty": divergence_penalty,
    }


def identify_overbought_oversold(
    sectors: list[SectorData],
) -> tuple[list[dict], list[dict]]:
    """Identify overbought (ratio > 0.37) and oversold (ratio < 0.097) sectors."""
    overbought: list[dict] = []
    oversold: list[dict] = []
    for s in sectors:
        if s.ratio > OVERBOUGHT_THRESHOLD:
            overbought.append(
                {"sector": s.sector, "ratio": s.ratio, "ratio_pct": round(s.ratio * 100, 1)}
            )
        elif s.ratio < OVERSOLD_THRESHOLD:
            oversold.append(
                {"sector": s.sector, "ratio": s.ratio, "ratio_pct": round(s.ratio * 100, 1)}
            )
    return overbought, oversold


def analyze_trends(sectors: list[SectorData]) -> dict:
    """Analyze trend distribution across sectors."""
    up = [s.sector for s in sectors if s.trend.lower() == "up"]
    down = [s.sector for s in sectors if s.trend.lower() == "down"]
    return {
        "uptrend_count": len(up),
        "downtrend_count": len(down),
        "uptrend_sectors": up,
        "downtrend_sectors": down,
    }


def estimate_cycle_phase(sectors: list[SectorData]) -> dict:
    """Estimate market cycle phase based on sector performance patterns.

    Scoring per phase:
      - Leader match in top ranks: weight 0.4
      - Laggard match in bottom ranks: weight 0.3
      - Trend direction alignment: weight 0.3
    """
    if not sectors:
        return {"phase": "unknown", "confidence": "low", "scores": {}, "evidence": []}

    sorted_by_ratio = sorted(sectors, key=lambda s: s.ratio, reverse=True)
    n = len(sorted_by_ratio)
    top_half = {s.sector for s in sorted_by_ratio[: n // 2 + 1]}
    bottom_half = {s.sector for s in sorted_by_ratio[n // 2 :]}
    trend_map = {s.sector: s.trend.lower() for s in sectors}

    scores: dict[str, float] = {}
    evidence: list[str] = []

    for phase_name, phase_def in CYCLE_PHASES.items():
        leaders = phase_def["leaders"]
        laggards = phase_def["laggards"]

        # Leader match: how many expected leaders are in top half
        leader_hits = sum(1 for s in leaders if s in top_half)
        leader_score = leader_hits / len(leaders) if leaders else 0

        # Laggard match: how many expected laggards are in bottom half
        laggard_hits = sum(1 for s in laggards if s in bottom_half)
        laggard_score = laggard_hits / len(laggards) if laggards else 0

        # Trend alignment: leaders trending up, laggards trending down
        trend_hits = 0
        trend_total = 0
        for s in leaders:
            if s in trend_map:
                trend_total += 1
                if trend_map[s] == "up":
                    trend_hits += 1
        for s in laggards:
            if s in trend_map:
                trend_total += 1
                if trend_map[s] == "down":
                    trend_hits += 1
        trend_score = trend_hits / trend_total if trend_total else 0

        total = leader_score * 0.4 + laggard_score * 0.3 + trend_score * 0.3
        scores[phase_name] = round(total * 100, 1)

    # Determine best phase
    sorted_phases = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_phase = sorted_phases[0][0]
    best_score = sorted_phases[0][1]
    second_score = sorted_phases[1][1] if len(sorted_phases) > 1 else 0

    gap = best_score - second_score
    if gap > 20:
        confidence = "high"
    elif gap > 10:
        confidence = "moderate"
    else:
        confidence = "low"

    # Build evidence
    phase_def = CYCLE_PHASES[best_phase]
    matched_leaders = [s for s in phase_def["leaders"] if s in top_half]
    matched_laggards = [s for s in phase_def["laggards"] if s in bottom_half]
    if matched_leaders:
        evidence.append(f"Leaders in top ranks: {', '.join(matched_leaders)}")
    if matched_laggards:
        evidence.append(f"Laggards in bottom ranks: {', '.join(matched_laggards)}")

    return {
        "phase": best_phase,
        "confidence": confidence,
        "scores": scores,
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# Output Formatters
# ---------------------------------------------------------------------------


def format_human(
    ranking: list[dict],
    groups: dict,
    overbought: list[dict],
    oversold: list[dict],
    trends: dict,
    cycle: dict,
    freshness: dict | None,
) -> str:
    """Format analysis results as human-readable markdown."""
    lines: list[str] = []
    lines.append(f"# Sector Rotation Analysis — {date.today().isoformat()}")
    lines.append("")

    # Freshness warning
    if freshness:
        if freshness.get("warning"):
            lines.append(f"> **WARNING**: {freshness['warning']}")
            lines.append("")
        else:
            lines.append(f"> Data as of: {freshness['date']}")
            lines.append("")

    # Risk Regime
    lines.append("## Risk Regime")
    lines.append("")
    regime = groups.get("regime", "N/A").upper()
    score = groups.get("score", "N/A")
    lines.append(f"**{regime}** (score: {score}/100)")
    lines.append("")
    if groups.get("cyclical_avg") is not None:
        lines.append(f"- Cyclical avg: {groups['cyclical_avg_pct']}%")
        lines.append(f"- Defensive avg: {groups['defensive_avg_pct']}%")
        lines.append(f"- Difference: {groups['difference_pct']}pp")
        if groups.get("commodity_avg") is not None:
            lines.append(f"- Commodity avg: {groups['commodity_avg_pct']}%")
        if groups.get("late_cycle_flag"):
            lines.append(
                "- **Late Cycle Flag**: Commodity sectors leading both cyclical and defensive"
            )
        if groups.get("divergence_flag"):
            lines.append("- **Divergence Flag**: High intra-group spread detected")
    lines.append("")

    # Cycle Phase
    lines.append("## Cycle Phase Estimate")
    lines.append("")
    phase = cycle.get("phase", "unknown").replace("_", " ").title()
    conf = cycle.get("confidence", "N/A")
    lines.append(f"**{phase}** (confidence: {conf})")
    lines.append("")
    if cycle.get("scores"):
        for p, s in sorted(cycle["scores"].items(), key=lambda x: x[1], reverse=True):
            marker = " ←" if p == cycle["phase"] else ""
            lines.append(f"- {p.title()}: {s}{marker}")
    lines.append("")
    if cycle.get("evidence"):
        lines.append("Evidence:")
        for e in cycle["evidence"]:
            lines.append(f"- {e}")
        lines.append("")

    # Sector Ranking
    lines.append("## Sector Ranking (by uptrend ratio)")
    lines.append("")
    lines.append("| Rank | Sector | Ratio | Trend | Status |")
    lines.append("|------|--------|-------|-------|--------|")
    for r in ranking:
        lines.append(
            f"| {r['rank']} | {r['sector']} | {r['ratio_pct']}% | {r['trend']} | {r['status']} |"
        )
    lines.append("")

    # Trends
    lines.append("## Trend Summary")
    lines.append("")
    lines.append(f"- Uptrending: {trends['uptrend_count']} sectors")
    lines.append(f"- Downtrending: {trends['downtrend_count']} sectors")
    lines.append("")

    # Overbought / Oversold
    if overbought or oversold:
        lines.append("## Overbought / Oversold")
        lines.append("")
        if overbought:
            lines.append("**Overbought** (ratio > 37%):")
            for s in overbought:
                lines.append(f"- {s['sector']}: {s['ratio_pct']}%")
        if oversold:
            lines.append("**Oversold** (ratio < 9.7%):")
            for s in oversold:
                lines.append(f"- {s['sector']}: {s['ratio_pct']}%")
        lines.append("")

    lines.append("---")
    lines.append(f"*Generated: {datetime.now().isoformat(timespec='seconds')}*")
    return "\n".join(lines)


def format_json(
    ranking: list[dict],
    groups: dict,
    overbought: list[dict],
    oversold: list[dict],
    trends: dict,
    cycle: dict,
    freshness: dict | None,
) -> str:
    """Format analysis results as JSON."""
    data = {
        "meta": {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "date": date.today().isoformat(),
            "freshness": freshness,
        },
        "groups": groups,
        "cycle_phase": cycle,
        "ranking": ranking,
        "overbought": overbought,
        "oversold": oversold,
        "trends": trends,
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_float(value: str) -> float | None:
    """Parse float, return None on failure."""
    try:
        return float(value.strip())
    except (ValueError, AttributeError):
        return None


def _avg(values: list[float]) -> float:
    """Simple average."""
    return sum(values) / len(values)


def _get_group_ratios(sector_map: dict[str, SectorData], sector_names: list[str]) -> list[float]:
    """Extract ratios for a group of sectors."""
    ratios: list[float] = []
    for name in sector_names:
        sector = sector_map.get(name)
        if sector is not None:
            ratios.append(sector.ratio)
    return ratios


def _difference_to_score(diff: float) -> float:
    """Map cyclical-defensive difference to score (0-100).

    Aligned with sector_rotation_calculator.py L171-189.
    """
    if diff > 0.15:
        return min(100, 90 + (diff - 0.15) / 0.10 * 10)
    elif diff > 0.05:
        return 70 + (diff - 0.05) / 0.10 * 19
    elif diff > -0.05:
        return 45 + (diff + 0.05) / 0.10 * 24
    elif diff > -0.15:
        return 20 + (diff + 0.15) / 0.10 * 24
    else:
        return max(0, 19 + (diff + 0.15) / 0.10 * 19)


def _score_to_regime(score: int) -> str:
    """Map score to risk regime label."""
    if score >= 90:
        return "strong risk-on"
    elif score >= 70:
        return "risk-on"
    elif score >= 45:
        return "balanced"
    elif score >= 20:
        return "defensive tilt"
    else:
        return "strong risk-off"


def _calculate_group_divergence(sector_map: dict[str, SectorData]) -> dict:
    """Detect intra-group divergence.

    Aligned with sector_rotation_calculator.py L209-232.
    """
    cyclical_div = _analyze_group(sector_map, CYCLICAL_SECTORS)
    defensive_div = _analyze_group(sector_map, DEFENSIVE_SECTORS)

    flag = cyclical_div["flagged"] or defensive_div["flagged"]
    penalty = -5 if flag else 0

    return {
        "divergence_flag": flag,
        "divergence_penalty": penalty,
        "cyclical_divergence": cyclical_div,
        "defensive_divergence": defensive_div,
    }


def _analyze_group(sector_map: dict[str, SectorData], sector_names: list[str]) -> dict:
    """Analyze divergence within a sector group."""
    ratios: list[float] = []
    trends: list[str] = []
    names_with_data: list[str] = []

    for name in sector_names:
        sector = sector_map.get(name)
        if sector is not None:
            ratios.append(sector.ratio)
            trends.append(sector.trend.lower())
            names_with_data.append(name)

    if len(ratios) < 2:
        return {
            "flagged": False,
            "std_dev": None,
            "spread": None,
            "outliers": [],
            "trend_dissenters": [],
        }

    mean = sum(ratios) / len(ratios)
    variance = sum((r - mean) ** 2 for r in ratios) / len(ratios)
    std_dev = math.sqrt(variance)
    spread = max(ratios) - min(ratios)

    # Outlier detection
    outliers: list[dict] = []
    for name, ratio in zip(names_with_data, ratios):
        if abs(ratio - mean) > 1.5 * std_dev and std_dev > 0:
            outliers.append({"sector": name, "ratio": ratio, "deviation": round(ratio - mean, 4)})

    # Trend dissenter detection
    trend_dissenters: list[dict] = []
    if trends:
        up_count = sum(1 for t in trends if t == "up")
        down_count = sum(1 for t in trends if t == "down")
        majority = "up" if up_count >= down_count else "down"

        for name, trend in zip(names_with_data, trends):
            if trend and trend != majority:
                trend_dissenters.append({"sector": name, "trend": trend, "majority": majority})

    flagged = std_dev > 0.08 or spread > 0.20 or len(trend_dissenters) > 0

    return {
        "flagged": flagged,
        "std_dev": round(std_dev, 4),
        "spread": round(spread, 4),
        "outliers": outliers,
        "trend_dissenters": trend_dissenters,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Sector rotation analysis from TraderMonty CSV data"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument(
        "--output-dir", default="reports/", help="Output directory (default: reports/)"
    )
    parser.add_argument("--save", action="store_true", help="Save output to file")
    parser.add_argument("--url", default=SECTOR_CSV_URL, help="Custom sector CSV URL")
    parser.add_argument(
        "--uptrend-url", default=UPTREND_CSV_URL, help="Custom uptrend timeseries CSV URL"
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout in seconds")
    args = parser.parse_args()

    # 1. Freshness check
    print("Checking data freshness...", file=sys.stderr)
    freshness = check_freshness(args.uptrend_url, timeout=args.timeout)
    if freshness is None:
        print("WARNING: Could not check data freshness (continuing)", file=sys.stderr)
    elif freshness.get("warning"):
        print(f"WARNING: {freshness['warning']}", file=sys.stderr)
    else:
        print(f"Data is fresh (latest: {freshness['date']})", file=sys.stderr)

    # 2. Fetch and parse sector data
    print("Fetching sector summary...", file=sys.stderr)
    raw_rows = fetch_csv(args.url, timeout=args.timeout)
    try:
        validate_columns(raw_rows)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    sectors = parse_sector_rows(raw_rows)

    if not sectors:
        print("ERROR: No valid sector data found", file=sys.stderr)
        raise SystemExit(1)

    print(f"Parsed {len(sectors)} sectors", file=sys.stderr)

    # 3. Analyze
    ranking = rank_sectors(sectors)
    groups = analyze_groups(sectors)
    overbought, oversold = identify_overbought_oversold(sectors)
    trends = analyze_trends(sectors)
    cycle = estimate_cycle_phase(sectors)

    # 4. Format output
    if args.json:
        output = format_json(ranking, groups, overbought, oversold, trends, cycle, freshness)
    else:
        output = format_human(ranking, groups, overbought, oversold, trends, cycle, freshness)

    print(output)

    # 5. Save to file
    if args.save:
        import os

        os.makedirs(args.output_dir, exist_ok=True)
        ext = ".json" if args.json else ".md"
        filename = f"sector_rotation_{date.today().isoformat()}{ext}"
        filepath = os.path.join(args.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Saved to {filepath}", file=sys.stderr)


if __name__ == "__main__":
    main()
