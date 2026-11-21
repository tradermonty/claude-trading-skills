"""Validated, standalone sector-analyst handoff for Exposure Coach (#831).

The consumer-owned mapping is an uncalibrated heuristic, not a forecast. Reuse
Uptrend Analyzer's ratio bands and slope adjustment, averaged equally across
all 11 sectors. Do not substitute the producer's relative rotation score.
"""

import math
from dataclasses import dataclass
from datetime import date
from typing import Optional

from evaluation_coverage import evaluation_input_usable

MAPPING_VERSION = "sector_uptrend_health_v1"
SECTORS = (
    "Technology",
    "Consumer Cyclical",
    "Communication Services",
    "Financial",
    "Industrials",
    "Utilities",
    "Consumer Defensive",
    "Healthcare",
    "Real Estate",
    "Energy",
    "Basic Materials",
)
_SECTOR_NAMES = {name.casefold(): name for name in SECTORS}
_CANONICAL_KEYS = {"ranking", "groups", "trends", "cycle_phase"}


@dataclass(frozen=True)
class SectorInput:
    """Keep scoring, optional legacy context, and diagnostics together."""

    score: Optional[int] = None
    context: Optional[dict] = None
    details: Optional[dict] = None
    warnings: tuple[str, ...] = ()
    error: Optional[str] = None
    canonical: bool = False


def _finite_number(value: object, lower: float, upper: float) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and lower <= value <= upper
        and math.isfinite(value)
    )


def _sector_name(value: object) -> Optional[str]:
    return _SECTOR_NAMES.get(value.strip().casefold()) if isinstance(value, str) else None


def _ratio_to_score(ratio: float) -> float:
    """Use Uptrend Analyzer's v1 absolute ratio bands (vendored for packaging).

    Source: uptrend-analyzer/scripts/calculators/market_breadth_calculator.py.
    Round only after averaging the adjusted sector values, not at each sector.
    """
    if ratio >= 0.50:
        return min(100, 90 + (ratio - 0.50) / 0.10 * 10)
    if ratio >= 0.37:
        return 70 + (ratio - 0.37) / (0.50 - 0.37) * 19
    if ratio >= 0.25:
        return 40 + (ratio - 0.25) / (0.37 - 0.25) * 29
    if ratio >= 0.097:
        return 10 + (ratio - 0.097) / (0.25 - 0.097) * 29
    return max(0, ratio / 0.097 * 9)


def _validate_trends(trends: object, rows: dict[str, dict]) -> Optional[str]:
    if not isinstance(trends, dict):
        return "canonical trends must contain counts and sector lists"
    for direction in ("up", "down"):
        expected = {name for name, row in rows.items() if row["trend"] == direction}
        count = trends.get(f"{direction}trend_count")
        names = trends.get(f"{direction}trend_sectors")
        if type(count) is not int or count != len(expected):
            return f"trends.{direction}trend_count does not match ranking"
        if not isinstance(names, list):
            return f"trends.{direction}trend_sectors must be a sector list"
        normalized = [_sector_name(name) for name in names]
        if len(normalized) != len(expected) or set(normalized) != expected:
            return f"trends.{direction}trend_sectors does not match ranking"
    return None


def _read_freshness(meta: object) -> tuple[Optional[dict], list[str], Optional[str]]:
    """Preserve producer claims; do not imply a consumer freshness validation."""
    if not isinstance(meta, dict):
        return None, [], "canonical meta must be an object"
    freshness = meta.get("freshness")
    if freshness is None:
        return None, ["Sector source freshness is unknown (producer did not verify it)."], None
    if not isinstance(freshness, dict):
        return None, [], "meta.freshness must be an object or null"
    label = freshness.get("date")
    if not isinstance(label, str):
        return None, [], "meta.freshness.date must be an ISO date"
    try:
        parsed = date.fromisoformat(label)
    except ValueError:
        return None, [], "meta.freshness.date must be an ISO date"
    if parsed.isoformat() != label:
        return None, [], "meta.freshness.date must use YYYY-MM-DD"
    is_fresh = freshness.get("is_fresh")
    warning = freshness.get("warning")
    if type(is_fresh) is not bool:
        return None, [], "meta.freshness.is_fresh must be boolean"
    if warning is not None and not isinstance(warning, str):
        return None, [], "meta.freshness.warning must be a string or null"
    warnings = []
    if not is_fresh:
        warnings.append(f"Sector producer reports stale source data (source date: {label}).")
    if warning:
        warnings.append(warning)
    return {"date": label, "is_fresh": is_fresh, "warning": warning}, warnings, None


def _canonical_sector(data: dict) -> SectorInput:
    def reject(reason: str) -> SectorInput:
        return SectorInput(error=reason, canonical=True)

    ranking = data.get("ranking")
    if not isinstance(ranking, list) or len(ranking) != len(SECTORS):
        return reject("canonical ranking must contain all 11 sectors exactly once")
    rows = {}
    row_warnings: list[str] = []
    for row in ranking:
        if not isinstance(row, dict):
            return reject("canonical ranking entries must be objects")
        name = _sector_name(row.get("sector"))
        if name is None or name in rows:
            return reject("canonical ranking has an unknown or duplicate sector")
        ratio, slope = row.get("ratio"), row.get("slope")
        if not _finite_number(ratio, 0, 1):
            return reject(f"{name}: ratio must be a finite number from 0 to 1")
        # The producer emits slope=None for a blank CSV cell, and the provider
        # contract allows a null Slope per row. Mirror Uptrend Analyzer: a null
        # slope, or a label that disagrees with the slope sign, gets no trend
        # adjustment instead of rejecting the whole report.
        if slope is not None and not _finite_number(slope, -1, 1):
            return reject(f"{name}: slope must be null or a finite number from -1 to 1")
        trend = row.get("trend")
        if not isinstance(trend, str):
            return reject(f"{name}: trend must be a string")
        trend = trend.lower().strip()
        if trend == "up" and slope is not None and slope > 0:
            adjustment = 5
        elif trend == "down" and slope is not None and slope < 0:
            adjustment = -5
        else:
            adjustment = 0
            if slope is None:
                row_warnings.append(f"{name}: slope unavailable; no trend adjustment applied.")
            elif trend not in {"up", "down"} or (trend == "up") != (slope > 0):
                row_warnings.append(
                    f"{name}: trend label does not match slope; no trend adjustment applied."
                )
        health = min(100, max(0, _ratio_to_score(ratio) + adjustment))
        rows[name] = {
            "sector": name,
            "ratio": ratio,
            "slope": slope,
            "trend": trend,
            "health_score": health,
        }
    # Provider contract (uptrend-sector-summary.v1): Slope may be null per row
    # but not for every row.
    if all(row["slope"] is None for row in rows.values()):
        return reject("canonical ranking has no slope values (all null)")
    error = _validate_trends(data.get("trends"), rows)
    if error:
        return reject(error)
    freshness, warnings, error = _read_freshness(data.get("meta"))
    if error:
        return reject(error)
    warnings = warnings + row_warnings

    ordered = [rows[name] for name in SECTORS]
    score = round(math.fsum(row["health_score"] for row in ordered) / len(SECTORS))
    details = {
        "mapping_version": MAPPING_VERSION,
        "score": score,
        "sector_count": len(SECTORS),
        "positive_slope_count": sum(
            row["slope"] is not None and row["slope"] > 0 for row in ordered
        ),
        "mean_ratio": math.fsum(row["ratio"] for row in ordered) / len(SECTORS),
        "source_freshness": freshness,
        "freshness_verified": False,
        "scope": "composite score only; bias and participation use other accepted inputs",
        "sector_health": ordered,
    }
    # Canonical ratio spread is not legacy return dispersion; do not fabricate
    # leadership/dispersion fields for the separate bias/participation rules.
    return SectorInput(score=score, details=details, warnings=tuple(warnings), canonical=True)


def _legacy_sector(data: dict) -> SectorInput:
    # Validate context even with an explicit score: otherwise malformed optional
    # fields can crash or influence the separate bias/participation calculations.
    if "dispersion" in data and not _finite_number(data["dispersion"], 0, 1):
        return SectorInput(error="legacy dispersion must be a finite number from 0 to 1")
    if "leadership" in data and (
        not isinstance(data["leadership"], str) or not data["leadership"].strip()
    ):
        return SectorInput(error="legacy leadership must be a nonempty string")
    context = {key: data[key] for key in ("dispersion", "leadership") if key in data}
    if "sector_score" in data:
        if not _finite_number(data["sector_score"], 0, 100):
            return SectorInput(error="legacy sector_score must be a finite number from 0 to 100")
        return SectorInput(score=int(data["sector_score"]), context=context)
    if "dispersion" not in data or "leadership" not in data:
        return SectorInput(
            error="unsupported sector schema; expected canonical ranking/trends or supported legacy sector fields"
        )
    dispersion, leadership = data["dispersion"], data["leadership"].lower()
    if dispersion < 0.1 and leadership in {"technology", "consumer discretionary"}:
        score = 85
    elif dispersion < 0.2:
        score = 65
    elif leadership in {"utilities", "staples", "healthcare"}:
        score = 35
    else:
        score = 50
    return SectorInput(score=score, context=context)


def parse_sector_input(data: object) -> SectorInput:
    """Validate a complete canonical report or a supported legacy input.

    A canonical-shaped payload never falls back to injected legacy fields when
    validation fails. Rejected data never contributes posture context.
    """
    if not isinstance(data, dict):
        return SectorInput(error="sector JSON must be an object")
    canonical = bool(_CANONICAL_KEYS.intersection(data))
    if not evaluation_input_usable(data):
        return SectorInput(
            error="evaluation_coverage is incomplete or invalid", canonical=canonical
        )
    return _canonical_sector(data) if canonical else _legacy_sector(data)
