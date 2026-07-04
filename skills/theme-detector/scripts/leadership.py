#!/usr/bin/env python3
"""Stock leadership evidence for Theme Detector v2.

The module accepts either pre-labeled scan hits or raw daily metric rows.
Raw rows are expanded into one ScanHit per matched condition so a single
symbol can count as both EP9M and range expansion on the same day.
"""

import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

SCAN_TYPES = ["five_day_20pct", "ep9m", "range_expansion", "new_high", "high_rs"]
LEADERSHIP_WEIGHTS = {
    "five_day_20pct": 0.30,
    "ep9m": 0.25,
    "range_expansion": 0.20,
    "new_high": 0.15,
    "high_rs": 0.10,
}


@dataclass
class ScanHit:
    date: str
    symbol: str
    scan_type: str
    return_5d: Optional[float] = None
    change_pct: Optional[float] = None
    volume: Optional[float] = None
    avg_volume_50d: Optional[float] = None
    relative_volume: Optional[float] = None
    dollar_volume: Optional[float] = None
    close_location: Optional[float] = None
    atr_expansion: Optional[float] = None
    close: Optional[float] = None
    industry: Optional[str] = None
    sector: Optional[str] = None
    theme_guess: Optional[str] = None
    catalyst: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def load_scan_hits(path: str, run_date: str) -> tuple[list[ScanHit], dict]:
    """Load scan hits from JSON/JSONL/CSV and derive missing scan types."""
    rows = _load_rows(path)
    hits: list[ScanHit] = []
    skipped_rows = 0
    skipped_date_rows = 0
    for row in rows:
        if not _row_matches_run_date(row, run_date):
            skipped_date_rows += 1
            continue
        row_hits = detect_scan_hits_from_row(row, run_date)
        if row_hits:
            hits.extend(row_hits)
        else:
            skipped_rows += 1

    summary = {
        "path": path,
        "rows": len(rows),
        "hits": len(hits),
        "skipped_rows": skipped_rows,
        "skipped_date_rows": skipped_date_rows,
    }
    return hits, summary


def detect_scan_hits_from_row(row: dict, run_date: str) -> list[ScanHit]:
    """Derive one or more ScanHit records from a raw or pre-labeled row."""
    symbol = str(row.get("symbol") or "").strip().upper()
    if not symbol:
        return []
    if not _row_matches_run_date(row, run_date):
        return []

    enriched = _enrich_row(row)
    date = str(row.get("date") or run_date)
    scan_types = _extract_scan_types(row)
    if not scan_types:
        scan_types = _derive_scan_types(enriched)

    return [_scan_hit_from_row(enriched, date, symbol, scan_type) for scan_type in scan_types]


def aggregate_leadership(
    themes: list[dict], scan_hits: list[ScanHit], history: dict
) -> dict[str, dict]:
    """Aggregate leadership evidence for each theme."""
    result: dict[str, dict] = {}
    hits_by_theme: dict[str, list[ScanHit]] = {}

    for hit in scan_hits:
        matched_names = _matched_theme_names(hit, themes)
        for name in matched_names:
            hits_by_theme.setdefault(name, []).append(hit)

    for theme in themes:
        name = theme.get("theme_name") or theme.get("name")
        hits = hits_by_theme.get(name, [])
        counts = {scan_type: 0 for scan_type in SCAN_TYPES}
        for hit in hits:
            if hit.scan_type in counts:
                counts[hit.scan_type] += 1

        if hits:
            score = calculate_leadership_score(name, counts, history)
            coverage = 1.0
        else:
            score = None
            coverage = 0.0

        result[name] = {
            "leadership_score": score,
            "leadership_coverage": coverage,
            "leadership_counts": counts,
            "leader_symbols": sorted({hit.symbol for hit in hits}),
            "scan_hits": [hit.to_dict() for hit in hits],
        }

    return result


def calculate_leadership_score(theme_name: str, counts: dict[str, int], history: dict) -> float:
    """Calculate 0-100 leadership score from hit counts and prior history."""
    weighted = 0.0
    for scan_type, weight in LEADERSHIP_WEIGHTS.items():
        value = counts.get(scan_type, 0)
        prior = _prior_counts(history, theme_name, scan_type)
        component = _count_component_score(value, prior)
        weighted += component * weight
    weight_sum = sum(LEADERSHIP_WEIGHTS.values())
    return round(min(100.0, max(0.0, weighted / weight_sum if weight_sum else 0.0)), 2)


def blend_theme_heat(base_heat: float, leadership_score: Optional[float]) -> float:
    """Blend leadership only when actual leadership evidence exists."""
    if leadership_score is None:
        return base_heat
    blended = 0.70 * base_heat + 0.30 * leadership_score
    return round(max(base_heat, blended), 2)


def _load_rows(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".csv":
        with p.open(newline="") as f:
            return list(csv.DictReader(f))
    with p.open() as f:
        if p.suffix.lower() == ".jsonl":
            return [json.loads(line) for line in f if line.strip()]
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("scan_hits", "rows", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    return []


def _extract_scan_types(row: dict) -> list[str]:
    raw = row.get("scan_types", row.get("scan_type"))
    if raw is None:
        return []
    if isinstance(raw, str):
        values = [part.strip() for part in raw.replace(";", ",").split(",")]
    elif isinstance(raw, list):
        values = [str(part).strip() for part in raw]
    else:
        values = [str(raw).strip()]
    return [value for value in values if value in SCAN_TYPES]


def _derive_scan_types(row: dict) -> list[str]:
    scan_types = []
    if _is_five_day_20pct(row):
        scan_types.append("five_day_20pct")
    if _is_ep9m(row):
        scan_types.append("ep9m")
    if _is_range_expansion(row):
        scan_types.append("range_expansion")
    if _is_new_high(row):
        scan_types.append("new_high")
    if _is_high_rs(row):
        scan_types.append("high_rs")
    return scan_types


def _row_matches_run_date(row: dict, run_date: str) -> bool:
    row_date = _date_key(row.get("date"))
    if row_date is None:
        return True
    return row_date == _date_key(run_date)


def _date_key(value) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else text


def _scan_hit_from_row(row: dict, date: str, symbol: str, scan_type: str) -> ScanHit:
    return ScanHit(
        date=date,
        symbol=symbol,
        scan_type=scan_type,
        return_5d=_float(row.get("return_5d")),
        change_pct=_float(row.get("change_pct")),
        volume=_float(row.get("volume")),
        avg_volume_50d=_float(row.get("avg_volume_50d")),
        relative_volume=_float(row.get("relative_volume")),
        dollar_volume=_float(row.get("dollar_volume")),
        close_location=_float(row.get("close_location")),
        atr_expansion=_float(row.get("atr_expansion")),
        close=_float(row.get("close")),
        industry=_clean(row.get("industry")),
        sector=_clean(row.get("sector")),
        theme_guess=_clean(row.get("theme_guess")),
        catalyst=_clean(row.get("catalyst")),
    )


def _enrich_row(row: dict) -> dict:
    enriched = dict(row)
    volume = _float(enriched.get("volume"))
    avg_volume = _float(enriched.get("avg_volume_50d"))
    close = _float(enriched.get("close"))
    true_range = _float(enriched.get("true_range"))
    atr_20 = _float(enriched.get("atr_20"))

    if _float(enriched.get("relative_volume")) is None and volume is not None and avg_volume:
        enriched["relative_volume"] = volume / avg_volume
    if _float(enriched.get("dollar_volume")) is None and volume is not None and close is not None:
        enriched["dollar_volume"] = volume * close
    if _float(enriched.get("atr_expansion")) is None and true_range is not None and atr_20:
        enriched["atr_expansion"] = true_range / atr_20
    return enriched


def _is_five_day_20pct(row: dict) -> bool:
    value = _float(row.get("return_5d"))
    return value is not None and value >= 20.0


def _is_ep9m(row: dict) -> bool:
    volume = _float(row.get("volume"))
    rel_volume = _float(row.get("relative_volume"))
    change = _float(row.get("change_pct"))
    return (
        volume is not None
        and rel_volume is not None
        and change is not None
        and volume >= 9_000_000
        and rel_volume >= 2.0
        and change >= 4.0
    )


def _is_range_expansion(row: dict) -> bool:
    change = _float(row.get("change_pct"))
    atr_expansion = _float(row.get("atr_expansion"))
    close_location = _float(row.get("close_location"))
    return (
        change is not None
        and atr_expansion is not None
        and close_location is not None
        and change >= 4.0
        and atr_expansion >= 1.5
        and close_location >= 0.75
    )


def _is_new_high(row: dict) -> bool:
    if _truthy(row.get("new_high")) or _truthy(row.get("is_new_high")):
        return True
    close = _float(row.get("close"))
    high_52w = _float(row.get("high_52w"))
    dist = _float(row.get("dist_from_52w_high"))
    if close is not None and high_52w is not None and high_52w > 0:
        return close >= high_52w
    return dist is not None and dist <= 0.01


def _is_high_rs(row: dict) -> bool:
    rs = _float(row.get("rs_rating", row.get("relative_strength")))
    if rs is None:
        return False
    threshold = 0.90 if rs <= 1.0 else 90.0
    return rs >= threshold


def _matched_theme_names(hit: ScanHit, themes: list[dict]) -> list[str]:
    if hit.theme_guess:
        return [hit.theme_guess]
    matches = []
    for theme in themes:
        name = theme.get("theme_name") or theme.get("name")
        industries = {ind.get("name") for ind in theme.get("matching_industries", [])}
        stocks = set(theme.get("static_stocks", []) or theme.get("representative_stocks", []))
        if (hit.industry and hit.industry in industries) or hit.symbol in stocks:
            matches.append(name)
    return matches


def _prior_counts(history: dict, theme_name: str, scan_type: str) -> list[int]:
    records = history.get(theme_name, [])
    counts = []
    for record in records:
        leadership_counts = record.get("leadership_counts") or {}
        counts.append(int(leadership_counts.get(scan_type, 0) or 0))
    return counts[-20:]


def _count_component_score(value: int, prior: list[int]) -> float:
    if not prior:
        return min(100.0, 50.0 + value * 25.0) if value > 0 else 0.0
    if len(prior) >= 2:
        mean = sum(prior) / len(prior)
        variance = sum((x - mean) ** 2 for x in prior) / len(prior)
        std = math.sqrt(variance)
        if std > 0:
            return min(100.0, max(0.0, 50.0 + ((value - mean) / std) * 15.0))
    baseline = max(sum(prior) / len(prior), 1.0)
    return min(100.0, max(0.0, (value / baseline) * 50.0))


def _float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean(value) -> Optional[str]:
    if value in (None, ""):
        return None
    return str(value).strip() or None


def _truthy(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
