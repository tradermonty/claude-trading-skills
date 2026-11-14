#!/usr/bin/env python3
"""
Stockbee Episodic Pivot Analyzer

Classify Day 1 Episodic Pivot (EP) candidates using catalyst quality,
price/range expansion, volume shock, neglect/revaluation context, liquidity,
and risk-distance checks.

The script is intentionally catalyst-first. It does not try to discover news
by itself; provide an events JSON, an earnings-trade-analyzer JSON file, or
both. Optional OHLCV data enriches price/volume statistics.

Usage examples:
    python3 analyze_ep.py --events-json catalysts.json --prices-json prices.json --output-dir reports/
    python3 analyze_ep.py --earnings-json reports/earnings_trade_analyzer_*.json --output-dir reports/
    python3 analyze_ep.py --events-json catalysts.json --momentum-json reports/stockbee_momentum_burst_*.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - only hit in stripped Python envs
    requests = None


class MissingDependencyError(RuntimeError):
    """A runtime dependency required by the selected CLI path is not installed."""


def _missing_requests_message() -> str:
    return (
        "requests library not found. Install this skill's dependencies: "
        f"pip install -r {Path(__file__).resolve().parents[1] / 'requirements.txt'}"
    )


CATALYST_ALIASES = {
    "earnings": "earnings",
    "earnings_beat": "earnings",
    "earnings_acceleration": "earnings",
    "beat_and_raise": "guidance_raise",
    "guidance": "guidance_raise",
    "guidance_raise": "guidance_raise",
    "raise_guidance": "guidance_raise",
    "m&a": "m_and_a",
    "ma": "m_and_a",
    "m_and_a": "m_and_a",
    "merger": "m_and_a",
    "acquisition": "m_and_a",
    "buyout": "m_and_a",
    "fda": "fda_approval",
    "fda_approval": "fda_approval",
    "approval": "regulatory_approval",
    "regulatory": "regulatory_approval",
    "regulatory_approval": "regulatory_approval",
    "contract": "major_contract",
    "major_contract": "major_contract",
    "partnership": "major_partnership",
    "major_partnership": "major_partnership",
    "analyst": "analyst_upgrade",
    "analyst_upgrade": "analyst_upgrade",
    "upgrade": "analyst_upgrade",
    "product": "product_launch",
    "product_launch": "product_launch",
    "story": "story_theme",
    "theme": "story_theme",
    "story_theme": "story_theme",
    "short_squeeze": "short_squeeze",
}

CATALYST_KEYWORDS = [
    ("guidance_raise", r"\b(raise[sd]?|boost[sed]?|lift[sed]?|increase[sd]?)\b.*\bguidance\b"),
    ("guidance_raise", r"\bguidance\b.*\b(raise[sd]?|boost[sed]?|lift[sed]?|increase[sd]?)\b"),
    ("earnings", r"\b(beat|beats|surprise|eps|earnings|revenue)\b"),
    ("m_and_a", r"\b(acquire[sd]?|acquisition|merger|buyout|takeover|tender offer)\b"),
    ("fda_approval", r"\b(fda|pdufa|phase 3|phase iii|drug approval|approved)\b"),
    ("regulatory_approval", r"\b(regulatory approval|approved by|clearance|authorization)\b"),
    ("major_contract", r"\b(contract|order|backlog|award|customer win|deal)\b"),
    ("major_partnership", r"\b(partnership|collaboration|strategic alliance)\b"),
    (
        "analyst_upgrade",
        r"\b(upgrade[sd]?|price target|initiates coverage|overweight|buy rating)\b",
    ),
    ("product_launch", r"\b(launch|unveil|new product|commercialization)\b"),
    ("short_squeeze", r"\b(short squeeze|squeeze|short interest)\b"),
    (
        "story_theme",
        r"\b(ai|artificial intelligence|crypto|bitcoin|nuclear|uranium|space|robotics|ev|defense)\b",
    ),
]

CATALYST_BASE_SCORES = {
    "guidance_raise": 95,
    "fda_approval": 94,
    "earnings": 88,
    "m_and_a": 84,
    "regulatory_approval": 82,
    "major_contract": 76,
    "major_partnership": 72,
    "product_launch": 66,
    "short_squeeze": 58,
    "analyst_upgrade": 54,
    "story_theme": 50,
    "unknown": 35,
}

EP_TYPE_BY_CATALYST = {
    "earnings": "EARNINGS_EP",
    "guidance_raise": "GUIDANCE_EP",
    "m_and_a": "M_AND_A_EP",
    "fda_approval": "FDA_EP",
    "regulatory_approval": "REGULATORY_EP",
    "major_contract": "CONTRACT_EP",
    "major_partnership": "PARTNERSHIP_EP",
    "analyst_upgrade": "ANALYST_EP",
    "product_launch": "PRODUCT_EP",
    "short_squeeze": "SQUEEZE_EP",
    "story_theme": "STORY_EP",
    "unknown": "UNCLASSIFIED_EP",
}

GRADE_TO_BONUS = {"A": 8, "B": 4, "C": 0, "D": -4}


@dataclass
class PriceStats:
    symbol: str
    event_date: str | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    prev_close: float | None = None
    volume: float | None = None
    avg_volume_20: float | None = None
    avg_volume_50: float | None = None
    gap_pct: float | None = None
    day_gain_pct: float | None = None
    range_pct: float | None = None
    close_location_pct: float | None = None
    volume_ratio_20: float | None = None
    volume_ratio_50: float | None = None
    dollar_volume: float | None = None
    risk_pct_to_low: float | None = None
    prior_5d_return_pct: float | None = None
    prior_20d_return_pct: float | None = None


_SHARED_FMP_MODULE = "_stockbee_episodic_pivot_analyzer_fmp_client"


def _load_shared_fmp():
    """Load the sibling generated client by path (never `import fmp_client`)."""
    module = sys.modules.get(_SHARED_FMP_MODULE)
    if module is None:
        path = Path(__file__).resolve().parent / "fmp_client.py"
        spec = importlib.util.spec_from_file_location(_SHARED_FMP_MODULE, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[_SHARED_FMP_MODULE] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(_SHARED_FMP_MODULE, None)
            raise
    return module


def _delegated(name: str) -> property:
    def getter(self):
        return getattr(self._client, name)

    def setter(self, value):
        setattr(self._client, name, value)

    return property(getter, setter)


class FMPClient:
    """Thin adapter over the generated stable-only FMP client (#495 Batch C)."""

    def __init__(self, api_key: str | None, max_api_calls: int = 200):
        if requests is None:
            raise MissingDependencyError(_missing_requests_message())
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise ValueError("FMP API key required for FMP enrichment")
        shared = _load_shared_fmp()
        self._budget_error = shared.ApiCallBudgetExceeded
        self._client = shared.FMPClient(api_key=self.api_key, max_api_calls=max_api_calls)
        self.cache: dict[str, Any] = {}

    session = _delegated("session")
    api_calls_made = _delegated("api_calls_made")
    api_calls = _delegated("api_calls_made")
    max_api_calls = _delegated("max_api_calls")
    last_call_time = _delegated("last_call_time")
    rate_limit_reached = _delegated("rate_limit_reached")

    def get_historical_prices(self, symbol: str, days: int = 90) -> list[dict[str, Any]]:
        try:
            data = self._client.fetch_eod_rows(symbol, days, pad_days=10)
        except self._budget_error:
            return []  # budget exhaustion stays soft for EP
        if isinstance(data, list) and data:
            return normalize_bars(data)[-days:]
        return []

    def stats(self) -> dict[str, Any]:
        return {"api_calls_made": self.api_calls, "max_api_calls": self.max_api_calls}


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(number) or math.isinf(number):
        return default
    return number


def round_or_none(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def normalize_symbol(symbol: Any) -> str:
    return str(symbol or "").strip().upper()


def normalize_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    # Accept YYYY-MM-DD or ISO timestamp prefixes.
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else None


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def load_json(path: str | None) -> Any:
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_catalyst_type(raw: Any) -> str:
    text = str(raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return "unknown"
    return CATALYST_ALIASES.get(text, text if text in CATALYST_BASE_SCORES else "unknown")


def classify_catalyst(record: dict[str, Any]) -> tuple[str, list[str]]:
    explicit = normalize_catalyst_type(
        record.get("catalyst_type")
        or record.get("event_type")
        or record.get("type")
        or record.get("category")
    )
    reasons: list[str] = []
    if explicit != "unknown":
        reasons.append(f"explicit:{explicit}")
        return explicit, reasons

    text = " ".join(
        str(record.get(key, "")) for key in ("headline", "summary", "description", "notes")
    ).lower()
    for catalyst_type, pattern in CATALYST_KEYWORDS:
        if re.search(pattern, text):
            reasons.append(f"keyword:{catalyst_type}")
            return catalyst_type, reasons
    return "unknown", ["no_clear_catalyst_keyword"]


def infer_event_date(record: dict[str, Any], fallback: str | None = None) -> str | None:
    for key in (
        "event_date",
        "date",
        "earnings_date",
        "published_date",
        "setup_date",
        "signal_date",
    ):
        normalized = normalize_date(record.get(key))
        if normalized:
            return normalized
    return normalize_date(fallback)


def normalize_event_record(
    record: dict[str, Any], source: str, fallback_date: str | None = None
) -> dict[str, Any] | None:
    symbol = normalize_symbol(record.get("symbol") or record.get("ticker"))
    if not symbol:
        return None
    catalyst_type, catalyst_reasons = classify_catalyst(record)
    event_date = infer_event_date(record, fallback=fallback_date)
    normalized = dict(record)
    normalized.update(
        {
            "symbol": symbol,
            "event_date": event_date,
            "source_input": source,
            "catalyst_type": catalyst_type,
            "catalyst_reasons": catalyst_reasons,
        }
    )
    return normalized


def events_from_events_json(data: Any, source: str = "events_json") -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, list):
        raw_events = data
        fallback_date = None
    elif isinstance(data, dict):
        raw_events = (
            data.get("events")
            or data.get("candidates")
            or data.get("results")
            or data.get("signals")
            or []
        )
        fallback_date = data.get("as_of") or data.get("date")
    else:
        return []

    events = []
    for raw in raw_events:
        if not isinstance(raw, dict):
            continue
        event = normalize_event_record(raw, source=source, fallback_date=fallback_date)
        if event:
            events.append(event)
    return events


def events_from_earnings_json(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    results = data.get("results") or data.get("candidates") or []
    events: list[dict[str, Any]] = []
    for raw in results:
        if not isinstance(raw, dict):
            continue
        symbol = normalize_symbol(raw.get("symbol") or raw.get("ticker"))
        if not symbol:
            continue
        gap_pct = safe_float(raw.get("gap_pct") or raw.get("earnings_gap_pct"))
        event = {
            "symbol": symbol,
            "event_date": normalize_date(raw.get("earnings_date") or raw.get("date")),
            "headline": f"Post-earnings reaction for {symbol}",
            "summary": raw.get("summary") or raw.get("notes") or "earnings-trade-analyzer input",
            "catalyst_type": "earnings",
            "source_input": "earnings_trade_analyzer",
            "source_grade": raw.get("grade"),
            "source_score": safe_float(raw.get("score") or raw.get("composite_score")),
            "gap_pct": gap_pct,
            "day_gain_pct": safe_float(raw.get("day_gain_pct") or raw.get("change_pct"), gap_pct),
            "earnings_timing": raw.get("earnings_timing") or raw.get("timing"),
            "raw_earnings_record": raw,
            "catalyst_reasons": ["source:earnings-trade-analyzer"],
        }
        events.append(event)
    return events


def load_momentum_enrichment(path: str | None) -> dict[tuple[str, str | None], dict[str, Any]]:
    data = load_json(path) if path else None
    if not data:
        return {}
    rows = data.get("candidates") or data.get("results") or [] if isinstance(data, dict) else []
    enrichment = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(row.get("symbol") or row.get("ticker"))
        if not symbol:
            continue
        setup_date = normalize_date(row.get("setup_date") or row.get("as_of") or row.get("date"))
        enrichment[(symbol, setup_date)] = row
        enrichment[(symbol, None)] = row
    return enrichment


def normalize_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for bar in bars:
        if not isinstance(bar, dict):
            continue
        d = normalize_date(bar.get("date"))
        if not d:
            continue
        normalized.append(
            {
                "date": d,
                "open": safe_float(bar.get("open")),
                "high": safe_float(bar.get("high")),
                "low": safe_float(bar.get("low")),
                "close": safe_float(bar.get("close") or bar.get("adjClose")),
                "volume": safe_float(bar.get("volume")),
            }
        )
    normalized.sort(key=lambda b: b["date"])
    return normalized


def load_prices_json(path: str | None) -> dict[str, list[dict[str, Any]]]:
    data = load_json(path) if path else None
    if data is None:
        return {}
    if isinstance(data, dict) and isinstance(data.get("prices"), dict):
        data = data["prices"]
    elif isinstance(data, dict) and isinstance(data.get("ohlcv"), dict):
        data = data["ohlcv"]

    prices: dict[str, list[dict[str, Any]]] = {}
    if isinstance(data, dict):
        for symbol, bars in data.items():
            if isinstance(bars, dict) and isinstance(bars.get("historical"), list):
                bars = bars["historical"]
            if isinstance(bars, list):
                norm = normalize_bars(bars)
                if norm:
                    prices[normalize_symbol(symbol)] = norm
    elif isinstance(data, list):
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in data:
            if not isinstance(row, dict):
                continue
            symbol = normalize_symbol(row.get("symbol") or row.get("ticker"))
            if symbol:
                grouped.setdefault(symbol, []).append(row)
        for symbol, bars in grouped.items():
            norm = normalize_bars(bars)
            if norm:
                prices[symbol] = norm
    return prices


def average(values: list[float]) -> float | None:
    cleaned = [v for v in values if v is not None and v > 0]
    if not cleaned:
        return None
    return sum(cleaned) / len(cleaned)


def find_event_index(bars: list[dict[str, Any]], event_date: str | None) -> int | None:
    if not bars:
        return None
    if event_date:
        for idx, bar in enumerate(bars):
            if bar["date"] == event_date:
                return idx
        # For after-hours events, use the next trading bar.
        target = parse_date(event_date)
        if target:
            for idx, bar in enumerate(bars):
                bar_date = parse_date(bar["date"])
                if bar_date and bar_date >= target:
                    return idx
    return len(bars) - 1


def price_stats_from_bars(
    symbol: str, bars: list[dict[str, Any]], event_date: str | None
) -> PriceStats:
    bars = normalize_bars(bars)
    idx = find_event_index(bars, event_date)
    if idx is None or idx <= 0 or idx >= len(bars):
        return PriceStats(symbol=symbol, event_date=event_date)

    bar = bars[idx]
    prev = bars[idx - 1]
    prev_close = safe_float(prev.get("close"))
    open_price = safe_float(bar.get("open"))
    high = safe_float(bar.get("high"))
    low = safe_float(bar.get("low"))
    close = safe_float(bar.get("close"))
    volume = safe_float(bar.get("volume"))

    prior_bars = bars[max(0, idx - 50) : idx]
    avg20 = average([safe_float(b.get("volume"), 0) or 0 for b in prior_bars[-20:]])
    avg50 = average([safe_float(b.get("volume"), 0) or 0 for b in prior_bars])
    gap_pct = None
    day_gain_pct = None
    range_pct = None
    close_location_pct = None
    risk_pct_to_low = None
    dollar_volume = None
    if prev_close and prev_close > 0:
        if open_price:
            gap_pct = ((open_price / prev_close) - 1.0) * 100.0
        if close:
            day_gain_pct = ((close / prev_close) - 1.0) * 100.0
        if high and low:
            range_pct = ((high - low) / prev_close) * 100.0
    if high and low and close and high > low:
        close_location_pct = ((close - low) / (high - low)) * 100.0
    if close and low and close > 0:
        risk_pct_to_low = ((close - low) / close) * 100.0
    if close and volume:
        dollar_volume = close * volume

    volume_ratio_20 = volume / avg20 if volume and avg20 else None
    volume_ratio_50 = volume / avg50 if volume and avg50 else None

    prior_5d = None
    prior_20d = None
    if idx >= 5 and prev_close and safe_float(bars[idx - 5].get("close")):
        base = safe_float(bars[idx - 5].get("close"))
        prior_5d = ((prev_close / base) - 1.0) * 100.0 if base else None
    if idx >= 20 and prev_close and safe_float(bars[idx - 20].get("close")):
        base = safe_float(bars[idx - 20].get("close"))
        prior_20d = ((prev_close / base) - 1.0) * 100.0 if base else None

    return PriceStats(
        symbol=symbol,
        event_date=bar["date"],
        open=open_price,
        high=high,
        low=low,
        close=close,
        prev_close=prev_close,
        volume=volume,
        avg_volume_20=avg20,
        avg_volume_50=avg50,
        gap_pct=gap_pct,
        day_gain_pct=day_gain_pct,
        range_pct=range_pct,
        close_location_pct=close_location_pct,
        volume_ratio_20=volume_ratio_20,
        volume_ratio_50=volume_ratio_50,
        dollar_volume=dollar_volume,
        risk_pct_to_low=risk_pct_to_low,
        prior_5d_return_pct=prior_5d,
        prior_20d_return_pct=prior_20d,
    )


def merge_price_fields(
    record: dict[str, Any], stats: PriceStats, momentum: dict[str, Any] | None = None
) -> dict[str, Any]:
    merged = dict(record)
    if momentum:
        for target, source in (
            ("day_gain_pct", "day_gain_pct"),
            ("volume", "volume"),
            ("volume_ratio_1d", "volume_ratio_1d"),
            ("volume_ratio_50", "volume_ratio_50"),
            ("close_location_pct", "close_location_pct"),
            ("risk_pct_to_low", "risk_pct_to_stop"),
            ("close", "close"),
            ("low", "stop_reference"),
        ):
            if merged.get(target) is None and momentum.get(source) is not None:
                merged[target] = momentum.get(source)
        if not merged.get("momentum_trigger_type"):
            triggers = momentum.get("trigger_types") or momentum.get("triggers") or []
            if isinstance(triggers, list) and triggers:
                merged["momentum_trigger_type"] = triggers[0]
            elif momentum.get("trigger_type"):
                merged["momentum_trigger_type"] = momentum.get("trigger_type")

    stat_map = {
        "open": stats.open,
        "high": stats.high,
        "low": stats.low,
        "close": stats.close,
        "prev_close": stats.prev_close,
        "volume": stats.volume,
        "avg_volume_20": stats.avg_volume_20,
        "avg_volume_50": stats.avg_volume_50,
        "gap_pct": stats.gap_pct,
        "day_gain_pct": stats.day_gain_pct,
        "range_pct": stats.range_pct,
        "close_location_pct": stats.close_location_pct,
        "volume_ratio_20": stats.volume_ratio_20,
        "volume_ratio_50": stats.volume_ratio_50,
        "dollar_volume": stats.dollar_volume,
        "risk_pct_to_low": stats.risk_pct_to_low,
        "prior_5d_return_pct": stats.prior_5d_return_pct,
        "prior_20d_return_pct": stats.prior_20d_return_pct,
    }
    for key, value in stat_map.items():
        if merged.get(key) is None and value is not None:
            merged[key] = value
    if stats.event_date and not merged.get("price_event_date"):
        merged["price_event_date"] = stats.event_date
    return merged


def score_catalyst(record: dict[str, Any]) -> tuple[float, list[str]]:
    catalyst_type = normalize_catalyst_type(record.get("catalyst_type"))
    base = CATALYST_BASE_SCORES.get(catalyst_type, 35)
    reasons = [f"base_{catalyst_type}:{base}"]

    grade = str(record.get("source_grade") or record.get("grade") or "").upper()
    if grade in GRADE_TO_BONUS:
        base += GRADE_TO_BONUS[grade]
        reasons.append(f"earnings_grade_{grade}:{GRADE_TO_BONUS[grade]:+d}")

    text = " ".join(
        str(record.get(k, "")) for k in ("headline", "summary", "description", "notes")
    ).lower()
    if re.search(r"\b(first|record|accelerat|inflect|turnaround|transform|breakthrough)\b", text):
        base += 6
        reasons.append("game_change_language:+6")
    if re.search(
        r"\b(secondary offering|dilution|investigation|downgrade|lawsuit|resignation)\b", text
    ):
        base -= 12
        reasons.append("negative_or_dilutive_language:-12")

    score = max(0.0, min(100.0, base)) * 0.35
    return score, reasons


def score_price_action(record: dict[str, Any]) -> tuple[float, list[str]]:
    gap = safe_float(record.get("gap_pct"))
    day_gain = safe_float(record.get("day_gain_pct"))
    close_loc = safe_float(record.get("close_location_pct"))
    range_pct = safe_float(record.get("range_pct"))
    score = 0.0
    reasons = []

    move = day_gain if day_gain is not None else gap
    if move is None:
        reasons.append("missing_move:0")
    elif move >= 12:
        score += 12
        reasons.append("move_12pct_plus:+12")
    elif move >= 8:
        score += 10
        reasons.append("move_8pct_plus:+10")
    elif move >= 4:
        score += 8
        reasons.append("move_4pct_plus:+8")
    elif move >= 2:
        score += 4
        reasons.append("move_2pct_plus:+4")
    else:
        reasons.append("weak_move:0")

    if gap is not None and gap >= 4:
        score += 4
        reasons.append("gap_confirmation:+4")
    elif gap is not None and gap >= 2:
        score += 2
        reasons.append("small_gap_confirmation:+2")

    if close_loc is not None:
        if close_loc >= 80:
            score += 4
            reasons.append("close_near_high:+4")
        elif close_loc >= 60:
            score += 2
            reasons.append("close_upper_range:+2")
        elif close_loc < 40:
            score -= 4
            reasons.append("weak_close_location:-4")

    if range_pct is not None and range_pct >= 6:
        score += 2
        reasons.append("range_expansion:+2")

    return max(0.0, min(20.0, score)), reasons


def score_volume(record: dict[str, Any]) -> tuple[float, list[str]]:
    ratio = safe_float(
        record.get("volume_ratio_50")
        or record.get("volume_ratio_20")
        or record.get("volume_ratio_1d")
    )
    volume = safe_float(record.get("volume"))
    score = 0.0
    reasons = []
    if ratio is not None:
        if ratio >= 10:
            score = 20
            reasons.append("volume_10x_plus:+20")
        elif ratio >= 5:
            score = 17
            reasons.append("volume_5x_plus:+17")
        elif ratio >= 3:
            score = 14
            reasons.append("volume_3x_plus:+14")
        elif ratio >= 1.5:
            score = 8
            reasons.append("volume_1_5x_plus:+8")
        else:
            score = 2
            reasons.append("weak_volume_ratio:+2")
    elif volume is not None:
        if volume >= 9_000_000:
            score = 14
            reasons.append("absolute_9m_volume:+14")
        elif volume >= 1_000_000:
            score = 8
            reasons.append("absolute_1m_volume:+8")
        elif volume >= 300_000:
            score = 4
            reasons.append("absolute_300k_volume:+4")
        else:
            reasons.append("thin_absolute_volume:0")
    else:
        score = 3
        reasons.append("missing_volume:+3")

    if volume is not None and volume >= 9_000_000 and score < 20:
        score += 3
        reasons.append("9m_ep_bonus:+3")
    return min(20.0, score), reasons


def score_revaluation(record: dict[str, Any]) -> tuple[float, list[str]]:
    prior_20 = safe_float(record.get("prior_20d_return_pct"))
    market_cap = safe_float(record.get("market_cap") or record.get("mktCap"))
    score = 5.0
    reasons = ["default_revaluation:+5"]

    if prior_20 is not None:
        if prior_20 <= 5:
            score = 8
            reasons = ["neglected_or_not_extended:+8"]
        elif prior_20 <= 15:
            score = 6
            reasons = ["moderately_extended:+6"]
        elif prior_20 <= 30:
            score = 3
            reasons = ["extended_prior_run:+3"]
        else:
            score = 1
            reasons = ["very_extended_prior_run:+1"]

    if market_cap is not None:
        if market_cap < 10_000_000_000:
            score += 2
            reasons.append("cap_under_10b:+2")
        elif market_cap > 100_000_000_000:
            score -= 1
            reasons.append("mega_cap_less_revaluation:+-1")
    return max(0.0, min(10.0, score)), reasons


def score_liquidity(record: dict[str, Any]) -> tuple[float, list[str]]:
    price = safe_float(record.get("close") or record.get("price") or record.get("current_price"))
    volume = safe_float(record.get("volume"))
    dollar_volume = safe_float(record.get("dollar_volume"))
    if dollar_volume is None and price and volume:
        dollar_volume = price * volume
    reasons = []
    score = 0.0
    if dollar_volume is not None:
        if dollar_volume >= 50_000_000:
            score = 10
            reasons.append("dollar_volume_50m_plus:+10")
        elif dollar_volume >= 10_000_000:
            score = 8
            reasons.append("dollar_volume_10m_plus:+8")
        elif dollar_volume >= 2_000_000:
            score = 4
            reasons.append("dollar_volume_2m_plus:+4")
        else:
            score = 1
            reasons.append("thin_dollar_volume:+1")
    elif volume is not None:
        if volume >= 1_000_000:
            score = 7
            reasons.append("absolute_volume_liquid:+7")
        elif volume >= 300_000:
            score = 5
            reasons.append("absolute_volume_minimum:+5")
        else:
            score = 1
            reasons.append("low_absolute_volume:+1")
    else:
        score = 3
        reasons.append("missing_liquidity:+3")

    if price is not None and price < 5:
        score = min(score, 3)
        reasons.append("low_price_cap:<=3")
    return score, reasons


def score_risk(record: dict[str, Any]) -> tuple[float, list[str]]:
    risk = safe_float(record.get("risk_pct_to_low") or record.get("risk_pct_to_stop"))
    if risk is None:
        return 2.0, ["missing_risk_distance:+2"]
    if risk <= 4:
        return 5.0, ["tight_risk_4pct_or_less:+5"]
    if risk <= 7:
        return 3.5, ["manageable_risk_7pct_or_less:+3.5"]
    if risk <= 10:
        return 1.5, ["wide_risk_10pct_or_less:+1.5"]
    return 0.0, ["too_wide_risk:0"]


def rating_from_score(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "A-"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    return "D"


def determine_state(
    record: dict[str, Any], score: float, max_risk_pct: float
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    day_gain = safe_float(record.get("day_gain_pct"))
    gap = safe_float(record.get("gap_pct"))
    volume_ratio = safe_float(
        record.get("volume_ratio_50")
        or record.get("volume_ratio_20")
        or record.get("volume_ratio_1d")
    )
    close_loc = safe_float(record.get("close_location_pct"))
    risk = safe_float(record.get("risk_pct_to_low") or record.get("risk_pct_to_stop"))
    catalyst_type = normalize_catalyst_type(record.get("catalyst_type"))

    move_confirmed = (day_gain is not None and day_gain >= 4) or (gap is not None and gap >= 4)
    volume_confirmed = (
        volume_ratio is None
        or volume_ratio >= 1.5
        or safe_float(record.get("volume"), 0) >= 300_000
    )
    weak_close = close_loc is not None and close_loc < 40
    risk_too_wide = risk is not None and risk > max_risk_pct

    if weak_close:
        reasons.append("weak_close_location")
    if risk_too_wide:
        reasons.append("risk_too_wide_for_day1")
    if not move_confirmed:
        reasons.append("price_move_not_confirmed")
    if not volume_confirmed:
        reasons.append("volume_not_confirmed")

    if score >= 85 and move_confirmed and volume_confirmed and not weak_close and not risk_too_wide:
        return "ACTIONABLE_DAY1", reasons
    if score >= 75 and move_confirmed and volume_confirmed and not weak_close and not risk_too_wide:
        return "DAY1_WATCH", reasons
    if score >= 70 and (risk_too_wide or weak_close):
        return "DELAYED_EP_WATCH", reasons
    if catalyst_type != "unknown" and not move_confirmed and score >= 55:
        return "CATALYST_WATCH", reasons
    return "REJECT", reasons


def analyze_candidate(
    event: dict[str, Any],
    prices: dict[str, list[dict[str, Any]]],
    momentum_enrichment: dict[tuple[str, str | None], dict[str, Any]],
    fmp: FMPClient | None,
    max_risk_pct: float,
) -> dict[str, Any]:
    symbol = normalize_symbol(event.get("symbol"))
    event_date = normalize_date(event.get("event_date"))

    bars = prices.get(symbol, [])
    if not bars and fmp:
        bars = fmp.get_historical_prices(symbol, days=100)
        if bars:
            prices[symbol] = bars
    stats = (
        price_stats_from_bars(symbol, bars, event_date) if bars else PriceStats(symbol, event_date)
    )

    momentum = momentum_enrichment.get((symbol, event_date)) or momentum_enrichment.get(
        (symbol, None)
    )
    record = merge_price_fields(event, stats, momentum)
    catalyst_type = normalize_catalyst_type(record.get("catalyst_type"))
    ep_type = EP_TYPE_BY_CATALYST.get(catalyst_type, "UNCLASSIFIED_EP")

    component_scores = {}
    component_reasons = {}
    for name, scorer in (
        ("catalyst_quality", score_catalyst),
        ("price_action", score_price_action),
        ("volume_shock", score_volume),
        ("neglect_revaluation", score_revaluation),
        ("liquidity", score_liquidity),
        ("risk_distance", score_risk),
    ):
        score, reasons = scorer(record)
        component_scores[name] = round(score, 2)
        component_reasons[name] = reasons

    composite = round(sum(component_scores.values()), 2)
    state, state_reasons = determine_state(record, composite, max_risk_pct=max_risk_pct)
    rating = rating_from_score(composite)

    # Downscore obvious fade in final score but preserve component transparency.
    close_loc = safe_float(record.get("close_location_pct"))
    if close_loc is not None and close_loc < 30 and composite >= 55:
        composite = round(max(0.0, composite - 8.0), 2)
        rating = rating_from_score(composite)
        state_reasons.append("fade_deduction_applied")
        state, more_reasons = determine_state(record, composite, max_risk_pct=max_risk_pct)
        state_reasons.extend([r for r in more_reasons if r not in state_reasons])

    pead_handoff = catalyst_type in {"earnings", "guidance_raise"} and state in {
        "ACTIONABLE_DAY1",
        "DAY1_WATCH",
        "DELAYED_EP_WATCH",
    }
    momentum_handoff = (safe_float(record.get("day_gain_pct"), 0) or 0) >= 4 and state != "REJECT"

    result = {
        "symbol": symbol,
        "event_date": event_date,
        "price_event_date": record.get("price_event_date"),
        "headline": record.get("headline") or record.get("title") or "",
        "summary": record.get("summary") or record.get("description") or record.get("notes") or "",
        "source_input": record.get("source_input"),
        "catalyst_type": catalyst_type,
        "ep_type": ep_type,
        "state": state,
        "state_reasons": sorted(set(state_reasons)),
        "rating": rating,
        "composite_score": composite,
        "component_scores": component_scores,
        "component_reasons": component_reasons,
        "catalyst_reasons": record.get("catalyst_reasons", []),
        "gap_pct": round_or_none(safe_float(record.get("gap_pct"))),
        "day_gain_pct": round_or_none(safe_float(record.get("day_gain_pct"))),
        "range_pct": round_or_none(safe_float(record.get("range_pct"))),
        "close_location_pct": round_or_none(safe_float(record.get("close_location_pct"))),
        "volume": round_or_none(safe_float(record.get("volume")), 0),
        "avg_volume_50": round_or_none(safe_float(record.get("avg_volume_50")), 0),
        "volume_ratio_50": round_or_none(safe_float(record.get("volume_ratio_50"))),
        "dollar_volume": round_or_none(safe_float(record.get("dollar_volume")), 0),
        "open": round_or_none(safe_float(record.get("open"))),
        "high": round_or_none(safe_float(record.get("high"))),
        "low": round_or_none(safe_float(record.get("low"))),
        "close": round_or_none(
            safe_float(record.get("close") or record.get("price") or record.get("current_price"))
        ),
        "prev_close": round_or_none(safe_float(record.get("prev_close"))),
        "risk_pct_to_low": round_or_none(safe_float(record.get("risk_pct_to_low"))),
        "prior_20d_return_pct": round_or_none(safe_float(record.get("prior_20d_return_pct"))),
        "source_grade": record.get("source_grade") or record.get("grade"),
        "source_score": round_or_none(
            safe_float(record.get("source_score") or record.get("score"))
        ),
        "market_cap": round_or_none(
            safe_float(record.get("market_cap") or record.get("mktCap")), 0
        ),
        "pead_handoff": pead_handoff,
        "momentum_handoff": momentum_handoff,
        "delayed_ep_watch": state == "DELAYED_EP_WATCH",
        "trade_plan_inputs": {
            "entry_reference": round_or_none(
                safe_float(
                    record.get("close") or record.get("price") or record.get("current_price")
                )
            ),
            "stop_reference": round_or_none(safe_float(record.get("low"))),
            "stop_basis": "ep_day_low",
            "risk_pct_to_stop": round_or_none(safe_float(record.get("risk_pct_to_low"))),
            "notes": "Candidate only; require manual catalyst and chart validation before trading.",
        },
        "raw_event": event,
    }
    return result


def dedupe_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    output = []
    for event in events:
        key = (
            normalize_symbol(event.get("symbol")),
            normalize_date(event.get("event_date")),
            normalize_catalyst_type(event.get("catalyst_type")),
            str(event.get("headline") or "")[:80],
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(event)
    return output


def sort_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {
        "ACTIONABLE_DAY1": 0,
        "DAY1_WATCH": 1,
        "DELAYED_EP_WATCH": 2,
        "CATALYST_WATCH": 3,
        "REJECT": 4,
    }
    return sorted(
        results,
        key=lambda r: (priority.get(r.get("state"), 9), -safe_float(r.get("composite_score"), 0)),
    )


def write_json_report(
    results: list[dict[str, Any]], metadata: dict[str, Any], output_file: str
) -> None:
    payload = {
        "schema_version": "1.0",
        "skill": "stockbee-episodic-pivot-analyzer",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "metadata": metadata,
        "results": results,
        "episodic_pivot_candidates": [r for r in results if r.get("state") != "REJECT"],
        "pead_handoff_candidates": [r for r in results if r.get("pead_handoff")],
        "delayed_ep_watchlist": [r for r in results if r.get("delayed_ep_watch")],
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=False)
        f.write("\n")


def format_num(value: Any, suffix: str = "") -> str:
    number = safe_float(value)
    if number is None:
        return "n/a"
    if abs(number) >= 1_000_000 and suffix == "":
        return f"{number / 1_000_000:.1f}M"
    return f"{number:.2f}{suffix}"


def write_markdown_report(
    results: list[dict[str, Any]], metadata: dict[str, Any], output_file: str
) -> None:
    state_counts: dict[str, int] = {}
    for result in results:
        state_counts[result.get("state", "UNKNOWN")] = (
            state_counts.get(result.get("state", "UNKNOWN"), 0) + 1
        )

    lines = [
        "# Stockbee Episodic Pivot Analyzer Report",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Input events: {metadata.get('event_count', 0)}",
        f"Max Day 1 risk: {metadata.get('max_risk_pct')}%",
        "",
        "## State Distribution",
        "",
        "| State | Count |",
        "|---|---:|",
    ]
    for state in ["ACTIONABLE_DAY1", "DAY1_WATCH", "DELAYED_EP_WATCH", "CATALYST_WATCH", "REJECT"]:
        lines.append(f"| {state} | {state_counts.get(state, 0)} |")

    lines.extend(
        [
            "",
            "## Top Candidates",
            "",
            "| Symbol | State | EP Type | Score | Rating | Move | Vol x50 | Risk | Catalyst |",
            "|---|---|---|---:|---|---:|---:|---:|---|",
        ]
    )
    for r in results[: metadata.get("top", 30)]:
        lines.append(
            "| {symbol} | {state} | {ep_type} | {score:.1f} | {rating} | {move} | {vol} | {risk} | {cat} |".format(
                symbol=r.get("symbol"),
                state=r.get("state"),
                ep_type=r.get("ep_type"),
                score=safe_float(r.get("composite_score"), 0) or 0,
                rating=r.get("rating"),
                move=format_num(r.get("day_gain_pct"), "%"),
                vol=format_num(r.get("volume_ratio_50"), "x"),
                risk=format_num(r.get("risk_pct_to_low"), "%"),
                cat=r.get("catalyst_type"),
            )
        )

    for r in results[: min(10, metadata.get("top", 30))]:
        if r.get("state") == "REJECT":
            continue
        lines.extend(
            [
                "",
                f"### {r.get('symbol')} — {r.get('state')} / {r.get('rating')} / {r.get('composite_score')}",
                "",
                f"- EP type: `{r.get('ep_type')}`",
                f"- Catalyst: `{r.get('catalyst_type')}` — {r.get('headline') or 'n/a'}",
                f"- Move: {format_num(r.get('day_gain_pct'), '%')} | Gap: {format_num(r.get('gap_pct'), '%')} | Volume: {format_num(r.get('volume_ratio_50'), 'x')} x50",
                f"- Close location: {format_num(r.get('close_location_pct'), '%')} | Risk to EP low: {format_num(r.get('risk_pct_to_low'), '%')}",
                f"- Handoffs: PEAD={r.get('pead_handoff')} Momentum={r.get('momentum_handoff')} DelayedEP={r.get('delayed_ep_watch')}",
                f"- State reasons: {', '.join(r.get('state_reasons') or []) or 'none'}",
            ]
        )

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        f.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stockbee Episodic Pivot Analyzer")
    parser.add_argument(
        "--events-json",
        help="Catalyst/event JSON file for earnings, guidance, M&A, FDA, theme, etc.",
    )
    parser.add_argument(
        "--earnings-json", help="earnings-trade-analyzer JSON output to convert into EP events"
    )
    parser.add_argument(
        "--momentum-json",
        help="stockbee-momentum-burst-screener JSON output for price/volume enrichment",
    )
    parser.add_argument("--prices-json", help="Offline OHLCV JSON by symbol; avoids FMP calls")
    parser.add_argument("--api-key", help="FMP API key for optional OHLCV enrichment")
    parser.add_argument(
        "--max-api-calls", type=int, default=200, help="FMP API call budget (default: 200)"
    )
    parser.add_argument(
        "--max-risk-pct",
        type=float,
        default=10.0,
        help="Max Day 1 risk to EP low before delayed watch (default: 10)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=30,
        help="Number of top rows to display in markdown (default: 30)",
    )
    parser.add_argument(
        "--output-dir", default="reports/", help="Output directory (default: reports/)"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    events: list[dict[str, Any]] = []
    if args.events_json:
        events.extend(events_from_events_json(load_json(args.events_json), source="events_json"))
    if args.earnings_json:
        events.extend(events_from_earnings_json(load_json(args.earnings_json)))
    events = dedupe_events(events)

    if not events:
        print(
            "ERROR: Provide at least one valid event via --events-json or --earnings-json",
            file=sys.stderr,
        )
        sys.exit(1)

    prices = load_prices_json(args.prices_json)
    momentum = load_momentum_enrichment(args.momentum_json)
    fmp = None
    if args.api_key or os.getenv("FMP_API_KEY"):
        try:
            fmp = FMPClient(args.api_key, max_api_calls=args.max_api_calls)
        except MissingDependencyError as exc:
            # FMP enrichment is optional. An explicit --api-key is a request for it,
            # so fail with exit 2; an ambient FMP_API_KEY only degrades with a warning.
            if args.api_key:
                print(f"ERROR: {exc}", file=sys.stderr)
                sys.exit(2)
            print(f"WARNING: FMP enrichment disabled: {exc}", file=sys.stderr)
        except Exception as exc:  # pragma: no cover - defensive for CLI users
            print(f"WARNING: FMP enrichment disabled: {exc}", file=sys.stderr)

    print("=" * 72)
    print("Stockbee Episodic Pivot Analyzer")
    print("=" * 72)
    print(f"Events loaded: {len(events)}")
    print(f"Offline price symbols: {len(prices)}")
    print(f"Momentum enrichments: {len(momentum)}")
    print()

    results = []
    for event in events:
        result = analyze_candidate(
            event,
            prices=prices,
            momentum_enrichment=momentum,
            fmp=fmp,
            max_risk_pct=args.max_risk_pct,
        )
        results.append(result)
        print(
            f"  {result['symbol']:6} {result['state']:18} "
            f"Score: {result['composite_score']:5.1f} ({result['rating']}) "
            f"{result['ep_type']}"
        )

    results = sort_results(results)
    os.makedirs(args.output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_file = os.path.join(args.output_dir, f"stockbee_episodic_pivot_{timestamp}.json")
    md_file = os.path.join(args.output_dir, f"stockbee_episodic_pivot_{timestamp}.md")
    metadata = {
        "event_count": len(events),
        "events_json": args.events_json,
        "earnings_json": args.earnings_json,
        "momentum_json": args.momentum_json,
        "prices_json": args.prices_json,
        "max_risk_pct": args.max_risk_pct,
        "top": args.top,
        "api_stats": fmp.stats() if fmp else None,
    }
    write_json_report(results, metadata, json_file)
    write_markdown_report(results, metadata, md_file)

    print()
    print("Reports:")
    print(f"  JSON:     {json_file}")
    print(f"  Markdown: {md_file}")


if __name__ == "__main__":
    main()
