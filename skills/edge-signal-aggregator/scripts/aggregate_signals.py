#!/usr/bin/env python3
"""
Edge Signal Aggregator

Combine outputs from multiple upstream edge-finding skills into a single
weighted conviction dashboard with deduplication and contradiction detection.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False


# Default weights if no config provided
DEFAULT_WEIGHTS = {
    "edge_candidate_agent": 0.25,
    "edge_concept_synthesizer": 0.20,
    "theme_detector": 0.15,
    "sector_analyst": 0.15,
    "institutional_flow_tracker": 0.15,
    "edge_hint_extractor": 0.10,
}

DEFAULT_CONFIG = {
    "weights": DEFAULT_WEIGHTS,
    "deduplication": {
        "similarity_threshold": 0.60,
        "ticker_overlap_threshold": 0.30,
        "merge_bonus_per_duplicate": 0.05,  # deprecated (Issue #510): ignored, kept for YAML compat
    },
    "agreement": {
        "two_skills_bonus": 0.10,
        "three_plus_skills_bonus": 0.20,
        "max_score": 1.00,
    },
    "recency": {
        "within_24h": 1.00,
        "days_1_to_3": 0.95,
        "days_3_to_7": 0.90,
        "days_7_plus": 0.85,
    },
    "contradictions": {
        "low_penalty": 0.00,
        "medium_penalty": 0.10,
        "high_action": "exclude",
    },
    "confidence_factors": {
        "multi_skill_agreement": 0.35,
        "signal_strength": 0.40,
        "recency": 0.25,
    },
    "min_conviction": 0.50,
}


def load_config(config_path: str | None) -> dict[str, Any]:
    """Load weights configuration from YAML file or use defaults."""
    if config_path is None:
        return deepcopy(DEFAULT_CONFIG)

    path = Path(config_path)
    if not path.exists():
        print(f"Warning: Config file not found: {config_path}, using defaults", file=sys.stderr)
        return deepcopy(DEFAULT_CONFIG)

    if not YAML_AVAILABLE:
        print("Warning: PyYAML not installed, using default config", file=sys.stderr)
        return deepcopy(DEFAULT_CONFIG)

    with open(path) as f:
        config = yaml.safe_load(f)

    # Merge with defaults for any missing keys
    merged = deepcopy(DEFAULT_CONFIG)
    if config:
        for key, value in config.items():
            if isinstance(value, dict) and key in merged:
                merged[key] = {**merged.get(key, {}), **value}
            else:
                merged[key] = value
    _reject_non_finite_config_values(merged)
    return merged


def _reject_non_finite_config_values(config: dict[str, Any]) -> None:
    """Issue #510: NaN/inf in a custom YAML (e.g. weights) must not leak into output JSON."""

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)
        else:
            yield node

    for value in walk(config):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("Config contains non-finite numeric values (NaN/infinity)")


def load_json_files(pattern: str | None) -> list[dict[str, Any]]:
    """Load all JSON files matching the glob pattern."""
    if not pattern:
        return []
    files = glob.glob(pattern)
    results = []
    for f in files:
        try:
            with open(f) as fp:
                data = json.load(fp)
                if isinstance(data, dict):
                    data["_source_file"] = f
                    results.append(data)
                elif isinstance(data, list):
                    results.append({"_source_file": f, "items": data})
                else:
                    print(
                        f"Warning: Unsupported JSON root in {f}: {type(data).__name__}",
                        file=sys.stderr,
                    )
        except (json.JSONDecodeError, OSError) as e:
            print(f"Warning: Failed to load {f}: {e}", file=sys.stderr)
    return results


def load_yaml_files(pattern: str | None) -> list[dict[str, Any]]:
    """Load all YAML files matching the glob pattern."""
    if not pattern:
        return []
    if not YAML_AVAILABLE:
        print("Warning: PyYAML not installed, cannot load YAML files", file=sys.stderr)
        return []
    files = glob.glob(pattern)
    results = []
    for f in files:
        try:
            with open(f) as fp:
                data = yaml.safe_load(fp)
                if isinstance(data, dict):
                    data["_source_file"] = f
                    results.append(data)
                elif isinstance(data, list):
                    results.append({"_source_file": f, "items": data})
        except (OSError, yaml.YAMLError) as e:
            print(f"Warning: Failed to load {f}: {e}", file=sys.stderr)
    return results


def normalize_direction(value: str | None, default: str = "NEUTRAL") -> str:
    """Normalize various direction labels into LONG/SHORT/NEUTRAL."""
    if not value:
        return default
    direction = str(value).strip().lower()
    if direction in {"long", "bull", "bullish", "buy", "accumulation", "increase", "up"}:
        return "LONG"
    if direction in {"short", "bear", "bearish", "sell", "distribution", "decrease", "down"}:
        return "SHORT"
    return default


def as_ticker_list(value: Any) -> list[str]:
    """Normalize ticker payload into uppercase string list."""
    tickers: list[str] = []
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                tickers.append(item.strip().upper())
            elif isinstance(item, dict):
                symbol = item.get("symbol") or item.get("ticker")
                if isinstance(symbol, str) and symbol.strip():
                    tickers.append(symbol.strip().upper())
    elif isinstance(value, str):
        for token in value.split(","):
            if token.strip():
                tickers.append(token.strip().upper())
    return sorted(set(tickers))


GRADE_SCALE_MAP = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.2}


def parse_raw_score(score, declared_scale=None):
    """Parse a raw score into (score, status, reason).

    Status is one of "valid", "invalid", "assumed_scale". Reason is None or one of
    "non_finite", "negative", "out_of_range", "missing_scale", "unparsable".
    Invalid inputs never produce a numeric score (Issue #510: NaN/inf must never
    surface as maximum confidence). When no scale is declared, values in (1, 100]
    are assumed to be on a 0-100 scale and flagged as "assumed_scale".
    """
    if score is None:
        return 0.0, "valid", None
    if isinstance(score, str):
        text = score.strip()
        if text.upper() in GRADE_SCALE_MAP:
            return GRADE_SCALE_MAP[text.upper()], "valid", None
        try:
            return _parse_numeric_score(float(text), declared_scale)
        except (TypeError, ValueError):
            return None, "invalid", "unparsable"
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None, "invalid", "unparsable"
    return _parse_numeric_score(value, declared_scale)


def _parse_numeric_score(value: float, declared_scale):
    if not math.isfinite(value):
        return None, "invalid", "non_finite"
    if value < 0:
        return None, "invalid", "negative"
    if declared_scale is not None:
        scale = str(declared_scale).strip().lower()
        if scale == "0-1":
            if value <= 1.0:
                return value, "valid", None
            return None, "invalid", "out_of_range"
        if scale == "0-100":
            if value <= 100.0:
                return value / 100.0, "valid", None
            return None, "invalid", "out_of_range"
        # Producer attempted a scale declaration it failed to express.
        return None, "invalid", "missing_scale"
    # Undeclared scale: best-effort assumption with an explicit flag upstream.
    if value <= 1.0:
        return value, "valid", None
    if value > 100.0:
        return None, "invalid", "out_of_range"
    return value / 100.0, "assumed_scale", None


def _is_finite_score(value) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)


def _stable_title(title) -> str:
    return " ".join(str(title or "").strip().split()).lower()


def _ticker_token(tickers) -> str:
    return ",".join(sorted({str(t).strip().upper() for t in (tickers or []) if t}))


def _default_evidence_id(
    skill: str,
    signal_ref,
    title,
    tickers,
    direction: str,
    provided=None,
) -> str:
    """Deterministic fallback identity per producer item; timestamp excluded."""
    if provided:
        return str(provided)
    raw = f"{skill}|{signal_ref}|{_stable_title(title)}|{_ticker_token(tickers)}|{direction}"
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def _default_event_fingerprint(title, tickers) -> str:
    raw = f"{_stable_title(title)}|{_ticker_token(tickers)}"
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def _invalid_signal_entry(
    skill: str,
    signal_ref,
    title,
    reason: str,
    declared_scale,
    raw_value,
    source_file,
) -> dict:
    return {
        "skill": skill,
        "signal_ref": signal_ref,
        "title": title,
        "reason": reason,
        "declared_scale": declared_scale,
        "raw_value_repr": repr(raw_value),
        "source_file": source_file,
    }


def _resolve_item_score(raw_score, item, doc, skill, signal_ref, title, source_file):
    """Apply Issue #510 scoring contract to one producer item.

    Returns (signal_payload|None, invalid_entry|None). signal_payload carries the
    parsed score plus scale/identity bookkeeping, or None when invalid.
    """
    declared_scale = None
    if isinstance(item, dict) and "score_scale" in item:
        declared_scale = item.get("score_scale")
    elif isinstance(doc, dict) and "score_scale" in doc:
        declared_scale = doc.get("score_scale")
    raw_value, status, reason = parse_raw_score(raw_score, declared_scale)
    if status == "invalid":
        return None, _invalid_signal_entry(
            skill, signal_ref, title, reason, declared_scale, raw_score, source_file
        )
    payload = {
        "raw_score": raw_value,
        "input_value": raw_score,
        "score_scale_assumed": status == "assumed_scale",
        "declared_scale": declared_scale,
    }
    return payload, None


def horizon_bucket(horizon: str | None) -> str:
    """Map free-text horizon to short/medium/long/unknown buckets."""
    if not horizon:
        return "unknown"
    text = str(horizon).lower().strip()
    # Handle compact numeric+unit patterns like "20D", "4W", "3M", "1Y"
    import re

    m = re.match(r"(\d+)\s*([dwmy])$", text)
    if m:
        num, unit = int(m.group(1)), m.group(2)
        if unit == "d" or (unit == "w" and num <= 12):
            return "short"
        if unit == "w":
            return "medium"
        if unit == "m" and num <= 3:
            return "short"
        if unit == "m" and num <= 6:
            return "medium"
        if unit in ("m", "y"):
            return "long"
    if any(k in text for k in ("day", "week", "1-3 months", "1-2 months", "short")):
        return "short"
    if any(k in text for k in ("3-6 months", "6 months", "3 months", "medium")):
        return "medium"
    if any(k in text for k in ("6-12 months", "12 months", "year", "long")):
        return "long"
    return "unknown"


def horizons_overlap(horizon_a: str | None, horizon_b: str | None) -> bool:
    """Return True when two horizons are likely in the same decision window."""
    bucket_a = horizon_bucket(horizon_a)
    bucket_b = horizon_bucket(horizon_b)
    if "unknown" in {bucket_a, bucket_b}:
        return True
    return bucket_a == bucket_b


def normalize_score(score: float | str | None, min_val: float = 0.0, max_val: float = 1.0) -> float:
    """Normalize a score to [0, 1] range.

    Legacy helper, no longer used by the Issue #510 extraction pipeline (which uses
    parse_raw_score). Kept only for backward compatibility with external callers;
    note it silently clamps instead of rejecting invalid values.
    """
    if score is None:
        return 0.0
    if isinstance(score, str):
        # Handle letter grades
        grade_map = {"A": 1.0, "B": 0.8, "C": 0.6, "D": 0.4, "F": 0.2}
        return grade_map.get(score.upper(), 0.0)
    try:
        val = float(score)
        if max_val == min_val:
            return 1.0 if val >= max_val else 0.0
        return max(0.0, min(1.0, (val - min_val) / (max_val - min_val)))
    except (TypeError, ValueError):
        return 0.0


def calculate_recency_factor(timestamp_str: str | None, recency_config: dict[str, float]) -> float:
    """Calculate recency adjustment factor based on signal age."""
    if not timestamp_str:
        return recency_config.get("days_7_plus", 0.85)

    ts = _parse_timestamp(timestamp_str)
    if ts is None:
        return recency_config.get("days_7_plus", 0.85)

    age_days = (datetime.now(timezone.utc) - ts).days
    if age_days < 1:
        return recency_config.get("within_24h", 1.0)
    elif age_days <= 3:
        return recency_config.get("days_1_to_3", 0.95)
    elif age_days <= 7:
        return recency_config.get("days_3_to_7", 0.90)
    return recency_config.get("days_7_plus", 0.85)


def extract_signals_from_edge_candidates(data: list[dict]) -> tuple[list[dict], list[dict]]:
    """Extract signals from edge-candidate-agent output."""
    signals = []
    invalids = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        tickets = doc.get("tickets", [])
        if not tickets and "anomalies" in doc:
            tickets = doc.get("anomalies", [])
        if not tickets and "items" in doc:
            tickets = doc.get("items", [])

        # Handle individual ticket YAML files (top-level dict IS the ticket)
        if not tickets and "priority_score" in doc:
            tickets = [doc]
        elif not tickets and isinstance(doc.get("observation"), dict):
            tickets = [doc]

        for ticket in tickets:
            if not isinstance(ticket, dict):
                continue
            score = ticket.get("priority_score")
            if score is None:
                score = ticket.get("score", ticket.get("confidence"))
            tickers = as_ticker_list(ticket.get("tickers", ticket.get("symbols", [])))
            if not tickers:
                symbol = ticket.get("symbol")
                if not symbol and isinstance(ticket.get("observation"), dict):
                    symbol = ticket["observation"].get("symbol")
                tickers = as_ticker_list([symbol] if symbol else [])
            signal_ref = ticket.get("ticket_id", ticket.get("id", "unknown"))
            title = ticket.get("title", ticket.get("description", "Unnamed signal"))
            payload, invalid_entry = _resolve_item_score(
                score, ticket, doc, "edge_candidate_agent", signal_ref, title, source_file
            )
            if invalid_entry is not None:
                invalids.append(invalid_entry)
                continue
            signal = {
                "skill": "edge_candidate_agent",
                "signal_ref": signal_ref,
                "title": title,
                "raw_score": payload["raw_score"],
                "score_scale_assumed": payload["score_scale_assumed"],
                "input_value": payload["input_value"],
                "evidence_id": _default_evidence_id(
                    "edge_candidate_agent",
                    signal_ref,
                    title,
                    tickers,
                    normalize_direction(ticket.get("direction"), default="NEUTRAL"),
                    ticket.get("evidence_id"),
                ),
                "event_fingerprint": _default_event_fingerprint(title, tickers),
                "tickers": tickers,
                "direction": normalize_direction(ticket.get("direction"), default="NEUTRAL"),
                "time_horizon": ticket.get(
                    "time_horizon", ticket.get("holding_horizon", "unknown")
                ),
                "timestamp": ticket.get(
                    "timestamp",
                    ticket.get("date", ticket.get("as_of")),
                ),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals, invalids


def extract_signals_from_concepts(data: list[dict]) -> tuple[list[dict], list[dict]]:
    """Extract signals from edge-concept-synthesizer output."""
    signals = []
    invalids = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        concepts = doc.get("concepts", doc.get("edge_concepts", []))
        if not concepts and "items" in doc:
            concepts = doc.get("items", [])

        for concept in concepts:
            if not isinstance(concept, dict):
                continue
            support = concept.get("support", {}) if isinstance(concept.get("support"), dict) else {}
            score = concept.get("confidence", concept.get("score"))
            if score is None:
                score = support.get("avg_priority_score")
            tickers = as_ticker_list(concept.get("tickers", concept.get("symbols", [])))
            if not tickers:
                tickers = as_ticker_list(support.get("symbols", []))
            signal_ref = concept.get("concept_id", concept.get("id", "unknown"))
            title = concept.get("title", concept.get("name", "Unnamed concept"))
            payload, invalid_entry = _resolve_item_score(
                score, concept, doc, "edge_concept_synthesizer", signal_ref, title, source_file
            )
            if invalid_entry is not None:
                invalids.append(invalid_entry)
                continue
            signal = {
                "skill": "edge_concept_synthesizer",
                "signal_ref": signal_ref,
                "title": title,
                "raw_score": payload["raw_score"],
                "score_scale_assumed": payload["score_scale_assumed"],
                "input_value": payload["input_value"],
                "evidence_id": _default_evidence_id(
                    "edge_concept_synthesizer",
                    signal_ref,
                    title,
                    tickers,
                    normalize_direction(concept.get("direction"), default="NEUTRAL"),
                    concept.get("evidence_id"),
                ),
                "event_fingerprint": _default_event_fingerprint(title, tickers),
                "tickers": tickers,
                "direction": normalize_direction(concept.get("direction"), default="NEUTRAL"),
                "time_horizon": concept.get(
                    "time_horizon",
                    concept.get("holding_horizon", "medium-term"),
                ),
                "timestamp": concept.get(
                    "timestamp",
                    doc.get("as_of", doc.get("generated_at")),
                ),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals, invalids


def extract_signals_from_themes(data: list[dict]) -> tuple[list[dict], list[dict]]:
    """Extract signals from theme-detector output."""
    signals = []
    invalids = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        theme_payload = doc.get("themes", doc.get("detected_themes", []))
        if not theme_payload and "items" in doc:
            theme_payload = doc.get("items", [])
        if isinstance(theme_payload, dict):
            themes = theme_payload.get("all", [])
        else:
            themes = theme_payload

        for theme in themes:
            if not isinstance(theme, dict):
                continue
            score = theme.get("strength", theme.get("score"))
            if score is None:
                score = theme.get("theme_heat", theme.get("heat"))
            tickers = as_ticker_list(theme.get("tickers", theme.get("related_symbols", [])))
            if not tickers:
                tickers = as_ticker_list(
                    theme.get("representative_stocks", theme.get("static_stocks", []))
                )
            signal_ref = theme.get("theme_id", theme.get("id", "unknown"))
            title = theme.get("theme_name", theme.get("name", "Unnamed theme"))
            payload, invalid_entry = _resolve_item_score(
                score, theme, doc, "theme_detector", signal_ref, title, source_file
            )
            if invalid_entry is not None:
                invalids.append(invalid_entry)
                continue
            signal = {
                "skill": "theme_detector",
                "signal_ref": signal_ref,
                "title": title,
                "raw_score": payload["raw_score"],
                "score_scale_assumed": payload["score_scale_assumed"],
                "input_value": payload["input_value"],
                "evidence_id": _default_evidence_id(
                    "theme_detector",
                    signal_ref,
                    title,
                    tickers,
                    normalize_direction(theme.get("direction"), default="NEUTRAL"),
                    theme.get("evidence_id"),
                ),
                "event_fingerprint": _default_event_fingerprint(title, tickers),
                "tickers": tickers,
                "direction": normalize_direction(theme.get("direction"), default="NEUTRAL"),
                "time_horizon": theme.get("horizon", theme.get("time_horizon", "3-6 months")),
                "timestamp": doc.get("generated_at", doc.get("timestamp")),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals, invalids


def extract_signals_from_sectors(data: list[dict]) -> tuple[list[dict], list[dict]]:
    """Extract signals from sector-analyst output."""
    signals = []
    invalids = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        sectors = doc.get("sectors", doc.get("sector_analysis", []))
        if not sectors:
            sectors = doc.get("ranking", [])
        if not sectors and "items" in doc:
            sectors = doc.get("items", [])

        for sector in sectors:
            if not isinstance(sector, dict):
                continue
            direction = "NEUTRAL"
            explicit = normalize_direction(sector.get("direction"), default="NEUTRAL")
            if explicit != "NEUTRAL":
                direction = explicit
            elif sector.get("rotation_phase") in ["accumulation", "markup"]:
                direction = "LONG"
            elif sector.get("rotation_phase") in ["distribution", "markdown"]:
                direction = "SHORT"
            elif str(sector.get("trend", "")).lower() == "up":
                direction = "LONG"
            elif str(sector.get("trend", "")).lower() == "down":
                direction = "SHORT"

            score = sector.get("strength", sector.get("score"))
            if score is None:
                score = sector.get("ratio_pct", sector.get("ratio"))
            signal_ref = sector.get("sector_name", sector.get("sector", "unknown"))
            title = f"{sector.get('sector_name', sector.get('sector', 'Unknown'))} Sector"
            payload, invalid_entry = _resolve_item_score(
                score, sector, doc, "sector_analyst", signal_ref, title, source_file
            )
            if invalid_entry is not None:
                invalids.append(invalid_entry)
                continue
            signal = {
                "skill": "sector_analyst",
                "signal_ref": signal_ref,
                "title": title,
                "raw_score": payload["raw_score"],
                "score_scale_assumed": payload["score_scale_assumed"],
                "input_value": payload["input_value"],
                "evidence_id": _default_evidence_id(
                    "sector_analyst",
                    signal_ref,
                    title,
                    as_ticker_list(sector.get("top_stocks", sector.get("tickers", []))),
                    direction,
                    sector.get("evidence_id"),
                ),
                "event_fingerprint": _default_event_fingerprint(
                    title, as_ticker_list(sector.get("top_stocks", sector.get("tickers", [])))
                ),
                "tickers": as_ticker_list(sector.get("top_stocks", sector.get("tickers", []))),
                "direction": direction,
                "time_horizon": "1-3 months",
                "timestamp": doc.get("generated_at", doc.get("timestamp", doc.get("as_of"))),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals, invalids


def extract_signals_from_institutional(data: list[dict]) -> tuple[list[dict], list[dict]]:
    """Extract signals from institutional-flow-tracker output."""
    signals = []
    invalids = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        flows = doc.get("flows", doc.get("institutional_flows", []))
        if not flows and "items" in doc:
            flows = doc.get("items", [])

        for flow in flows:
            if not isinstance(flow, dict):
                continue
            direction = "NEUTRAL"
            action = str(flow.get("action", "")).upper()
            if action in ["BUY", "INCREASE", "ACCUMULATION"]:
                direction = "LONG"
            elif action in ["SELL", "DECREASE", "DISTRIBUTION"]:
                direction = "SHORT"
            elif flow.get("percent_change") is not None:
                try:
                    change = float(flow.get("percent_change"))
                    if change > 0:
                        direction = "LONG"
                    elif change < 0:
                        direction = "SHORT"
                except (TypeError, ValueError):
                    direction = "NEUTRAL"

            score = flow.get("confidence", flow.get("magnitude"))
            if score is None:
                try:
                    score = abs(float(flow.get("percent_change", 0.0)))
                except (TypeError, ValueError):
                    score = None

            signal_ref = flow.get(
                "flow_id",
                f"{flow.get('institution', 'unknown')}_{flow.get('ticker', flow.get('symbol', 'unknown'))}",
            )
            title = flow.get(
                "title",
                f"{flow.get('institution', flow.get('company_name', 'Unknown'))} - {flow.get('ticker', flow.get('symbol', 'Unknown'))}",
            )
            flow_tickers = as_ticker_list(
                flow.get("tickers", [flow.get("ticker", flow.get("symbol"))]),
            )
            payload, invalid_entry = _resolve_item_score(
                score, flow, doc, "institutional_flow_tracker", signal_ref, title, source_file
            )
            if invalid_entry is not None:
                invalids.append(invalid_entry)
                continue
            signal = {
                "skill": "institutional_flow_tracker",
                "signal_ref": signal_ref,
                "title": title,
                "raw_score": payload["raw_score"],
                "score_scale_assumed": payload["score_scale_assumed"],
                "input_value": payload["input_value"],
                "evidence_id": _default_evidence_id(
                    "institutional_flow_tracker",
                    signal_ref,
                    title,
                    flow_tickers,
                    direction,
                    flow.get("evidence_id"),
                ),
                "event_fingerprint": _default_event_fingerprint(title, flow_tickers),
                "tickers": as_ticker_list(
                    flow.get("tickers", [flow.get("ticker", flow.get("symbol"))]),
                ),
                "direction": direction,
                "time_horizon": "3-12 months",
                "timestamp": flow.get("filing_date", doc.get("generated_at")),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals, invalids


def extract_signals_from_hints(data: list[dict]) -> tuple[list[dict], list[dict]]:
    """Extract signals from edge-hint-extractor output."""
    signals = []
    invalids = []
    for doc in data:
        source_file = doc.get("_source_file", "unknown")
        hints = doc.get("hints", doc.get("edge_hints", []))
        if not hints and "items" in doc:
            hints = doc.get("items", [])

        for hint in hints:
            if not isinstance(hint, dict):
                continue
            signal_ref = hint.get("hint_id", hint.get("id", "unknown"))
            title = hint.get("title", hint.get("hint", hint.get("description", "Unnamed hint")))
            hint_tickers = as_ticker_list(hint.get("tickers", hint.get("symbols", [])))
            payload, invalid_entry = _resolve_item_score(
                hint.get("relevance", hint.get("score", 0.3)),
                hint,
                doc,
                "edge_hint_extractor",
                signal_ref,
                title,
                source_file,
            )
            if invalid_entry is not None:
                invalids.append(invalid_entry)
                continue
            signal = {
                "skill": "edge_hint_extractor",
                "signal_ref": signal_ref,
                "title": title,
                "raw_score": payload["raw_score"],
                "score_scale_assumed": payload["score_scale_assumed"],
                "input_value": payload["input_value"],
                "evidence_id": _default_evidence_id(
                    "edge_hint_extractor",
                    signal_ref,
                    title,
                    hint_tickers,
                    normalize_direction(hint.get("direction"), default="NEUTRAL"),
                    hint.get("evidence_id"),
                ),
                "event_fingerprint": _default_event_fingerprint(title, hint_tickers),
                "tickers": as_ticker_list(hint.get("tickers", hint.get("symbols", []))),
                "direction": normalize_direction(hint.get("direction"), default="NEUTRAL"),
                "time_horizon": hint.get("horizon", "unknown"),
                "timestamp": doc.get("generated_at", doc.get("timestamp")),
                "source_file": source_file,
            }
            signals.append(signal)
    return signals, invalids


def calculate_ticker_overlap(tickers_a: list[str], tickers_b: list[str]) -> float:
    """Calculate Jaccard similarity between two ticker lists."""
    if not tickers_a or not tickers_b:
        return 0.0
    set_a = set(t.upper() for t in tickers_a)
    set_b = set(t.upper() for t in tickers_b)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def calculate_text_similarity(text_a: str, text_b: str) -> float:
    """Calculate simple word-based Jaccard similarity."""
    if not text_a or not text_b:
        return 0.0
    words_a = set(text_a.lower().split())
    words_b = set(text_b.lower().split())
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union if union > 0 else 0.0


def are_signals_similar(sig_a: dict, sig_b: dict, config: dict) -> bool:
    """Determine if two signals should be considered duplicates."""
    dedup_config = config.get("deduplication", {})
    similarity_threshold = dedup_config.get("similarity_threshold", 0.80)
    ticker_threshold = dedup_config.get("ticker_overlap_threshold", 0.50)

    # Different directions are not duplicates
    if sig_a.get("direction") != sig_b.get("direction"):
        return False

    ticker_sim = calculate_ticker_overlap(sig_a.get("tickers", []), sig_b.get("tickers", []))
    text_sim = calculate_text_similarity(sig_a.get("title", ""), sig_b.get("title", ""))

    # Either high ticker overlap or high text similarity
    return ticker_sim >= ticker_threshold or text_sim >= similarity_threshold


def _contributor_entry(sig: dict) -> dict:
    """Contributing-skill entry with identity fields for agreement tiering."""
    title = sig.get("title")
    tickers = sig.get("tickers")
    fingerprint = sig.get("event_fingerprint")
    if not fingerprint and (title is not None or tickers is not None):
        fingerprint = _default_event_fingerprint(title, tickers)
    entry = {
        "skill": sig["skill"],
        "signal_ref": sig["signal_ref"],
        "raw_score": sig["raw_score"],
        "evidence_id": sig.get("evidence_id"),
        "event_fingerprint": fingerprint,
    }
    if title is not None:
        entry["title"] = title
    if tickers is not None:
        entry["tickers"] = sorted({str(x).strip().upper() for x in tickers if x})
    return entry


EXACT_MERGE_RULE = (
    "newest timestamp wins; ties, missing, or unparsable timestamps keep the "
    "highest raw_score, then a stable key"
)


_TS_OFFSET_RE = re.compile(r"([+-])(\d{2})(?::?(\d{2}))?$")
_TS_FRACTION_RE = re.compile(r"(\.\d+)")


def _parse_timestamp(value) -> datetime | None:
    """Parse an ISO-8601 timestamp or YYYY-MM-DD date to an aware datetime.

    Only ISO-8601 strings are ordered; epoch numbers and compact forms such as
    ``20261010`` return None. Naive values are read as UTC. The text is normalized
    (``Z``/``+HHMM``/``+HH`` offsets, fractions truncated to 6 digits) so behavior is
    identical on Python 3.10 through 3.14.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if "T" in text or " " in text:
            text = text.replace(" ", "T", 1)
            if text.endswith(("Z", "z")):
                text = text[:-1] + "+00:00"
            head, sep, tail = text.partition("T")
            match = _TS_OFFSET_RE.search(tail)
            if match:
                hh, mm = match.group(2), match.group(3) or "00"
                tail = tail[: match.start()] + f"{match.group(1)}{hh}:{mm}"
            tail = _TS_FRACTION_RE.sub(lambda m: m.group(1)[:7], tail, count=1)
            parsed = datetime.fromisoformat(head + sep + tail)
        else:
            parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _score_or_zero(value) -> float:
    return float(value) if _is_finite_score(value) else 0.0


def _exact_copy_sort_key(sig: dict) -> tuple:
    """Total order, ascending: index 0 is the copy to retain."""
    parsed = _parse_timestamp(sig.get("timestamp"))
    ts_rank = parsed.timestamp() if parsed is not None else float("-inf")
    return (
        -ts_rank,
        -_score_or_zero(sig.get("raw_score")),
        str(sig.get("signal_ref", "")),
        str(sig.get("source_file", "")),
        str(sig.get("title", "")),
        str(sig.get("direction", "")),
        _ticker_token(sig.get("tickers")),
        json.dumps(sig, sort_keys=True, default=str),
    )


def _copy_summary(sig: dict) -> dict:
    return {
        "signal_ref": sig.get("signal_ref"),
        "source_file": sig.get("source_file"),
        "raw_score": sig.get("raw_score"),
        "timestamp": sig.get("timestamp"),
    }


def deduplicate_signals(signals: list[dict], config: dict) -> tuple[list[dict], list[dict]]:
    """
    Deduplicate signals, merging similar ones.
    Returns (deduplicated_signals, dedup_log).

    Issue #510: identical evidence (same skill + evidence_id) merges silently with no
    bonus; near-duplicate merges keep the old merge path but carry identity fields so
    agreement tiering can distinguish same-skill copies from independent evidence.
    """
    if not signals:
        return [], []

    # Pass 1: merge exact-evidence re-ingestions (same skill + evidence_id).
    # Newest observation wins: the copy with the latest parsed (timezone-aware)
    # timestamp is the primary. Equal, missing, or unparsable timestamps fall back to
    # the highest raw_score, then a stable key, so ingestion order cannot change the
    # result (Issue #510). A copy that declared no score_scale still toggles the
    # assumed-scale flag on the primary.
    groups: dict[tuple[str, Any], list[dict]] = {}
    for sig in signals:
        identity = (sig.get("skill", "unknown"), sig.get("evidence_id"))
        groups.setdefault(identity, []).append(sig)

    exact_signals: list[dict] = []
    exact_logs: dict[tuple[str, Any], dict] = {}
    for identity, group in groups.items():
        ordered = sorted(group, key=_exact_copy_sort_key)
        primary = dict(ordered[0])
        discarded = ordered[1:]
        if discarded:
            primary["_duplicate_copies"] = len(discarded)
            if any(c.get("score_scale_assumed") for c in discarded):
                primary["score_scale_assumed"] = True
            exact_logs[identity] = {
                "merged_into": f"{primary['skill']}:{primary['signal_ref']}",
                "duplicates_removed": [
                    f"{c['skill']}:{c['signal_ref']}@{c.get('source_file')}" for c in discarded
                ],
                "similarity_score": 1.0,
                "reason": "same evidence re-ingested",
                "selection_rule": EXACT_MERGE_RULE,
                "retained_copy": _copy_summary(primary),
                "discarded_copies": [_copy_summary(c) for c in discarded],
            }
        exact_signals.append(primary)

    # Deterministic order for the near-duplicate pass (independent of ingestion order).
    exact_signals.sort(
        key=lambda s: (
            -_score_or_zero(s.get("raw_score")),
            str(s.get("skill", "")),
            str(s.get("signal_ref", "")),
            str(s.get("evidence_id", "")),
        )
    )

    merged = []
    dedup_log = []
    used_indices = set()

    # Exact-copy merges are logged BEFORE pass 2 so they surface regardless of the
    # primary's own fate in the near-duplicate merge (Issue #510 review finding).
    for sig in exact_signals:
        identity = (sig.get("skill", "unknown"), sig.get("evidence_id"))
        if identity in exact_logs:
            dedup_log.append(exact_logs[identity])

    # Pass 2: near-duplicate similarity merge (existing behaviour).
    for i, sig in enumerate(exact_signals):
        if i in used_indices:
            continue

        duplicates = []
        for j, other in enumerate(exact_signals):
            if j != i and j not in used_indices:
                if are_signals_similar(sig, other, config):
                    duplicates.append((j, other))
                    used_indices.add(j)

        merged_signal = sig.copy()
        merged_signal["contributing_skills"] = [_contributor_entry(sig)]
        merged_signal["merged_from"] = []

        for _dup_idx, dup in duplicates:
            merged_signal["contributing_skills"].append(_contributor_entry(dup))
            merged_signal["merged_from"].append(f"{dup['skill']}:{dup['signal_ref']}")
            if dup.get("score_scale_assumed"):
                merged_signal["score_scale_assumed"] = True

            # Merge tickers
            existing_tickers = set(t.upper() for t in merged_signal.get("tickers", []))
            new_tickers = set(t.upper() for t in dup.get("tickers", []))
            merged_signal["tickers"] = sorted(existing_tickers | new_tickers)

        if duplicates:
            dedup_log.append(
                {
                    "merged_into": f"{sig['skill']}:{sig['signal_ref']}",
                    "duplicates_removed": merged_signal["merged_from"],
                    "similarity_score": 0.90,  # Simplified
                }
            )

        merged.append(merged_signal)
        used_indices.add(i)

    return merged, dedup_log


def detect_contradictions(signals: list[dict]) -> list[dict]:
    """Detect contradictions between signals."""
    contradictions = []

    # Group signals by ticker
    ticker_signals: dict[str, list[dict]] = defaultdict(list)
    for sig in signals:
        for ticker in sig.get("tickers", []):
            ticker_signals[ticker.upper()].append(sig)

    seen_pairs: set[tuple[str, str]] = set()

    # Check for opposing directions
    for ticker, sigs in ticker_signals.items():
        long_sigs = [s for s in sigs if s.get("direction") == "LONG"]
        short_sigs = [s for s in sigs if s.get("direction") == "SHORT"]

        for long_sig in long_sigs:
            for short_sig in short_sigs:
                long_ref = (
                    f"{long_sig.get('skill', 'unknown')}:{long_sig.get('signal_ref', 'unknown')}"
                )
                short_ref = (
                    f"{short_sig.get('skill', 'unknown')}:{short_sig.get('signal_ref', 'unknown')}"
                )
                pair_key = tuple(sorted((long_ref, short_ref)))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                same_skill = long_sig.get("skill") == short_sig.get("skill")
                overlap = horizons_overlap(
                    long_sig.get("time_horizon"),
                    short_sig.get("time_horizon"),
                )

                if same_skill:
                    severity = "HIGH"
                    resolution = "Same skill opposite signals - exclude both"
                elif not overlap:
                    severity = "LOW"
                    resolution = "Different time horizons - log only"
                else:
                    severity = "MEDIUM"
                    resolution = "Check timeframe mismatch (short-term vs long-term)"

                contradictions.append(
                    {
                        "contradiction_id": f"contra_{ticker}_{len(contradictions)}",
                        "ticker": ticker,
                        "description": f"Conflicting direction on {ticker}",
                        "severity": severity,
                        "time_horizon_overlap": overlap,
                        "signal_a_ref": long_ref,
                        "signal_b_ref": short_ref,
                        "skill_a": {
                            "skill": long_sig.get("skill", "unknown"),
                            "signal": long_sig.get("title", "unknown"),
                            "direction": "LONG",
                            "time_horizon": long_sig.get("time_horizon", "unknown"),
                        },
                        "skill_b": {
                            "skill": short_sig.get("skill", "unknown"),
                            "signal": short_sig.get("title", "unknown"),
                            "direction": "SHORT",
                            "time_horizon": short_sig.get("time_horizon", "unknown"),
                        },
                        "resolution_hint": resolution,
                    }
                )

    return contradictions


def apply_contradiction_adjustments(
    scored_signals: list[dict],
    contradictions: list[dict],
    config: dict,
) -> tuple[list[dict], list[dict]]:
    """Apply contradiction penalties or exclusion rules to scored signals."""
    contradiction_config = config.get("contradictions", {})
    low_penalty = float(contradiction_config.get("low_penalty", 0.0))
    medium_penalty = float(contradiction_config.get("medium_penalty", 0.10))
    high_action = str(contradiction_config.get("high_action", "exclude")).lower()

    by_ref = {signal["_source_ref"]: signal for signal in scored_signals}
    adjustment_log: list[dict] = []

    def apply_penalty(signal_ref: str, penalty: float, contradiction_id: str) -> None:
        signal = by_ref.get(signal_ref)
        if signal is None or signal.get("_excluded", False):
            return
        old_score = signal.get("composite_score", 0.0)
        new_score = max(0.0, old_score * (1.0 - penalty))
        signal["composite_score"] = round(new_score, 4)
        adjustment_log.append(
            {
                "signal_ref": signal_ref,
                "action": "penalty",
                "penalty": round(penalty, 4),
                "score_before": round(old_score, 4),
                "score_after": round(new_score, 4),
                "contradiction_id": contradiction_id,
            }
        )

    def apply_exclusion(signal_ref: str, contradiction_id: str) -> None:
        signal = by_ref.get(signal_ref)
        if signal is None or signal.get("_excluded", False):
            return
        signal["_excluded"] = True
        adjustment_log.append(
            {
                "signal_ref": signal_ref,
                "action": "exclude",
                "contradiction_id": contradiction_id,
            }
        )

    for contradiction in contradictions:
        signal_refs = [contradiction.get("signal_a_ref"), contradiction.get("signal_b_ref")]
        signal_refs = [ref for ref in signal_refs if isinstance(ref, str) and ref]
        if len(signal_refs) != 2:
            continue

        severity = contradiction.get("severity")
        contradiction_id = contradiction.get("contradiction_id", "unknown")

        if severity == "LOW":
            if low_penalty > 0:
                for signal_ref in signal_refs:
                    apply_penalty(signal_ref, low_penalty, contradiction_id)
            continue

        if severity == "MEDIUM":
            for signal_ref in signal_refs:
                apply_penalty(signal_ref, medium_penalty, contradiction_id)
            continue

        if severity == "HIGH" and high_action == "exclude":
            for signal_ref in signal_refs:
                apply_exclusion(signal_ref, contradiction_id)
            continue

        if severity == "HIGH":
            for signal_ref in signal_refs:
                apply_penalty(signal_ref, medium_penalty, contradiction_id)

    return scored_signals, adjustment_log


def calculate_composite_score(signal: dict, config: dict) -> dict:
    """Calculate composite conviction score for a signal."""
    weights = config.get("weights", DEFAULT_WEIGHTS)
    agreement_config = config.get("agreement", {})
    recency_config = config.get("recency", {})
    confidence_factors = config.get("confidence_factors", {})

    contributing = signal.get(
        "contributing_skills",
        [
            {
                "skill": signal["skill"],
                "signal_ref": signal["signal_ref"],
                "raw_score": signal["raw_score"],
                "evidence_id": signal.get("evidence_id"),
                "event_fingerprint": signal.get("event_fingerprint"),
            }
        ],
    )

    # Identity fallbacks for externally supplied contributor dicts (Issue #510).
    for contrib in contributing:
        if not _is_finite_score(contrib.get("raw_score")):
            # A non-finite/None raw score must never reach serialized output.
            contrib["raw_score"] = None
        if not contrib.get("evidence_id"):
            contrib["evidence_id"] = hashlib.sha1(
                f"{contrib.get('skill', 'unknown')}|{contrib.get('signal_ref', 'unknown')}".encode(),
                usedforsecurity=False,
            ).hexdigest()
        if not contrib.get("event_fingerprint"):
            if contrib.get("title") is not None or contrib.get("tickers") is not None:
                contrib["event_fingerprint"] = _default_event_fingerprint(
                    contrib.get("title"), contrib.get("tickers")
                )
            else:
                contrib["event_fingerprint"] = hashlib.sha1(
                    f"{contrib.get('skill', 'unknown')}|{contrib.get('signal_ref', 'unknown')}".encode(),
                    usedforsecurity=False,
                ).hexdigest()

    # Calculate weighted score from contributing skills
    weighted_sum = 0.0
    total_weight = 0.0
    for contrib in contributing:
        raw = contrib["raw_score"]
        if not _is_finite_score(raw):
            # Belt-and-suspenders guard: non-finite contributions are ignored.
            continue
        skill = contrib["skill"]
        weight = weights.get(skill, 0.10)
        weighted_sum += raw * weight
        total_weight += weight
        contrib["weighted_contribution"] = round(raw * weight, 4)

    base_score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Agreement bonus (Issue #510): credit requires distinct evidence AND distinct
    # events AND distinct skills; agreement_tier_n = min of the three distinct counts.
    distinct_evidence = len({c.get("evidence_id") for c in contributing})
    distinct_events = len({c.get("event_fingerprint") for c in contributing})
    distinct_skills = len({c.get("skill") for c in contributing})
    agreement_tier = min(distinct_evidence, distinct_events, distinct_skills)
    if agreement_tier >= 3:
        agreement_bonus = agreement_config.get("three_plus_skills_bonus", 0.20)
    elif agreement_tier == 2:
        agreement_bonus = agreement_config.get("two_skills_bonus", 0.10)
    else:
        agreement_bonus = 0.0

    # Merge bonus REMOVED (Issue #510): re-ingested duplicates must not inflate scores.

    # Recency factor
    recency_factor = calculate_recency_factor(signal.get("timestamp"), recency_config)

    # Composite score with cap; final non-finite guard.
    max_score = agreement_config.get("max_score", 1.0)
    composite = (base_score + agreement_bonus) * recency_factor
    if not math.isfinite(composite):
        composite = 0.0
    composite = max(0.0, min(max_score, composite))

    # Confidence breakdown
    agreement_weight = confidence_factors.get("multi_skill_agreement", 0.35)
    strength_weight = confidence_factors.get("signal_strength", 0.40)
    recency_weight = confidence_factors.get("recency", 0.25)

    finite_scores = [c["raw_score"] for c in contributing if _is_finite_score(c["raw_score"])]
    avg_raw_score = sum(finite_scores) / len(finite_scores) if finite_scores else 0.0

    confidence_breakdown = {
        "multi_skill_agreement": round(
            agreement_bonus
            / max(agreement_config.get("three_plus_skills_bonus", 0.20), 1e-9)
            * agreement_weight,
            2,
        ),
        "signal_strength": round(avg_raw_score * strength_weight, 2),
        "recency": round(recency_factor * recency_weight, 2),
    }

    return {
        "composite_score": round(composite, 4),
        "contributing_skills": contributing,
        "confidence_breakdown": confidence_breakdown,
    }


def aggregate_signals(
    edge_candidates: list[dict],
    edge_concepts: list[dict],
    themes: list[dict],
    sectors: list[dict],
    institutional: list[dict],
    hints: list[dict],
    config: dict,
) -> dict:
    """Main aggregation function."""
    # Extract signals from all sources (Issue #510: extraction returns valid + invalid)
    all_signals = []
    invalid_signals = []
    scale_assumptions_report = []

    def extract(source_name, extractor, data):
        nonlocal invalid_signals
        src_signals, src_invalids = extractor(data or [])
        all_signals.extend(src_signals)
        invalid_signals.extend(src_invalids)

    extract("edge_candidates", extract_signals_from_edge_candidates, edge_candidates)
    extract("edge_concepts", extract_signals_from_concepts, edge_concepts)
    extract("themes", extract_signals_from_themes, themes)
    extract("sectors", extract_signals_from_sectors, sectors)
    extract("institutional", extract_signals_from_institutional, institutional)
    extract("hints", extract_signals_from_hints, hints)

    total_input = len(all_signals)

    idempotency_check = {
        "total_input_signals": total_input,
        "unique_evidence_ids": len({s.get("evidence_id") for s in all_signals}),
        "duplicate_copies_merged": 0,
        "independent_units_total": len(
            {(s.get("skill"), s.get("evidence_id")) for s in all_signals}
        ),
    }

    # Deduplicate
    deduped_signals, dedup_log = deduplicate_signals(all_signals, config)
    exact_copy_count = sum(
        len(entry["duplicates_removed"])
        for entry in dedup_log
        if entry.get("reason") == "same evidence re-ingested"
    )
    idempotency_check["duplicate_copies_merged"] = exact_copy_count

    assumed_by_key: dict[tuple, dict] = {}
    for sig in all_signals:
        if sig.get("score_scale_assumed"):
            key = (sig.get("skill"), sig.get("signal_ref"), sig.get("evidence_id"))
            best = assumed_by_key.get(key)
            if best is None or _exact_copy_sort_key(sig) < _exact_copy_sort_key(best):
                assumed_by_key[key] = sig
    for sig in sorted(
        assumed_by_key.values(),
        key=lambda x: (str(x.get("skill")), str(x.get("signal_ref")), str(x.get("evidence_id"))),
    ):
        scale_assumptions_report.append(
            {
                "skill": sig.get("skill"),
                "signal_ref": sig.get("signal_ref"),
                "value": sig.get("input_value", sig.get("raw_score")),
                "normalized_value": round(sig["raw_score"], 6)
                if _is_finite_score(sig.get("raw_score"))
                else None,
                "assumed_scale": "0-100",
                "source_file": sig.get("source_file"),
            }
        )

    # Detect contradictions
    contradictions = detect_contradictions(deduped_signals)

    # Calculate composite scores
    scored_signals = []
    for sig in deduped_signals:
        score_data = calculate_composite_score(sig, config)
        scored_signal = {
            "_source_ref": f"{sig.get('skill', 'unknown')}:{sig.get('signal_ref', 'unknown')}",
            "signal_id": f"sig_{len(scored_signals):03d}",
            "title": sig["title"],
            "composite_score": score_data["composite_score"],
            "evidence_id": sig.get("evidence_id"),
            "score_scale_assumed": bool(sig.get("score_scale_assumed")),
            "contributing_skills": score_data["contributing_skills"],
            "tickers": sig.get("tickers", []),
            "direction": sig.get("direction", "NEUTRAL"),
            "time_horizon": sig.get("time_horizon", "unknown"),
            "confidence_breakdown": score_data["confidence_breakdown"],
        }
        scored_signals.append(scored_signal)

    # Apply contradiction penalties / exclusion
    adjusted_signals, contradiction_adjustments = apply_contradiction_adjustments(
        scored_signals,
        contradictions,
        config,
    )

    # Exclude signals removed by contradiction rules
    ranked_signals = [s for s in adjusted_signals if not s.get("_excluded", False)]

    # Sort by composite score
    ranked_signals.sort(key=lambda s: s["composite_score"], reverse=True)

    # Assign ranks
    for i, sig in enumerate(ranked_signals):
        sig["rank"] = i + 1
        sig.pop("_source_ref", None)
        sig.pop("_excluded", None)

    # Filter by minimum conviction
    min_conviction = config.get("min_conviction", 0.50)
    signals_above_threshold = [s for s in ranked_signals if s["composite_score"] >= min_conviction]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "config": {
            "weights": config.get("weights", DEFAULT_WEIGHTS),
            "min_conviction": min_conviction,
            "dedup_similarity_threshold": config.get("deduplication", {}).get(
                "similarity_threshold", 0.60
            ),
        },
        "summary": {
            "total_input_signals": total_input,
            "unique_signals_after_dedup": len(deduped_signals),
            "contradictions_found": len(contradictions),
            "contradiction_adjustments_applied": len(contradiction_adjustments),
            "signals_above_threshold": len(signals_above_threshold),
            "invalid_signals_dropped": len(invalid_signals),
            "idempotency_check": idempotency_check,
        },
        "schema_version": "1.1",
        "ranked_signals": ranked_signals,
        "contradictions": contradictions,
        "contradiction_adjustments": contradiction_adjustments,
        "deduplication_log": dedup_log,
        "invalid_signals": invalid_signals,
        "scale_assumptions_report": scale_assumptions_report,
    }


def generate_markdown_report(result: dict) -> str:
    """Generate markdown dashboard from aggregation result."""
    lines = [
        "# Edge Signal Aggregator Dashboard",
        f"**Generated:** {result['generated_at']}",
        "",
        "## Summary",
        f"- Total Input Signals: {result['summary']['total_input_signals']}",
        f"- Unique After Dedup: {result['summary']['unique_signals_after_dedup']}",
        f"- Contradictions: {result['summary']['contradictions_found']}",
        f"- High Conviction (>={result['config']['min_conviction']}): {result['summary']['signals_above_threshold']}",
        "",
    ]

    # Top signals
    min_conv = result["config"]["min_conviction"]
    top_signals = [s for s in result["ranked_signals"] if s["composite_score"] >= min_conv][:10]

    if top_signals:
        lines.append("## Top Edge Ideas by Conviction")
        lines.append("")

        for sig in top_signals:
            lines.append(f"### {sig['rank']}. {sig['title']} (Score: {sig['composite_score']:.2f})")
            tickers = ", ".join(sig["tickers"]) if sig["tickers"] else "N/A"
            lines.append(f"- **Tickers:** {tickers}")
            lines.append(
                f"- **Direction:** {sig['direction']} | **Horizon:** {sig['time_horizon']}"
            )
            lines.append("- **Contributing Skills:**")
            for contrib in sig["contributing_skills"]:
                contrib_score = contrib.get("raw_score")
                score_text = f"{contrib_score:.2f}" if _is_finite_score(contrib_score) else "n/a"
                lines.append(f"  - {contrib['skill']}: {score_text} ({contrib['signal_ref']})")
            cb = sig["confidence_breakdown"]
            lines.append(
                f"- **Confidence:** Agreement {cb['multi_skill_agreement']:.2f} | Strength {cb['signal_strength']:.2f} | Recency {cb['recency']:.2f}"
            )
            lines.append("")

    # Contradictions
    if result["contradictions"]:
        lines.append("## Contradictions Requiring Review")
        lines.append("")
        for contra in result["contradictions"]:
            lines.append(f"### {contra['description']} ({contra['severity']})")
            lines.append(
                f"- **{contra['skill_a']['skill']}:** {contra['skill_a']['signal']} ({contra['skill_a']['direction']})"
            )
            lines.append(
                f"- **{contra['skill_b']['skill']}:** {contra['skill_b']['signal']} ({contra['skill_b']['direction']})"
            )
            lines.append(f"- **Hint:** {contra['resolution_hint']}")
            lines.append("")

    # Dropped by score validation (Issue #510)
    if result.get("invalid_signals"):
        lines.append("## Dropped by Score Validation")
        lines.append("")
        for item in result["invalid_signals"]:
            lines.append(
                f"- {item['skill']}:{item['signal_ref']} - {item['reason']} "
                f"(declared_scale: {item.get('declared_scale')}, raw: {item.get('raw_value_repr')})"
            )
        lines.append("")

    # Deduplication summary
    if result["deduplication_log"]:
        lines.append("## Deduplication Summary")
        total_merged = sum(len(d["duplicates_removed"]) for d in result["deduplication_log"])
        lines.append(
            f"- {total_merged} signals merged into {len(result['deduplication_log'])} unique themes"
        )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Aggregate signals from multiple edge-finding skills"
    )
    parser.add_argument(
        "--edge-candidates",
        help="Glob pattern for edge-candidate-agent JSON files",
    )
    parser.add_argument(
        "--edge-concepts",
        help="Glob pattern for edge-concept-synthesizer YAML files",
    )
    parser.add_argument(
        "--themes",
        help="Glob pattern for theme-detector JSON files",
    )
    parser.add_argument(
        "--sectors",
        help="Glob pattern for sector-analyst JSON files",
    )
    parser.add_argument(
        "--institutional",
        help="Glob pattern for institutional-flow-tracker JSON files",
    )
    parser.add_argument(
        "--hints",
        help="Glob pattern for edge-hint-extractor YAML files",
    )
    parser.add_argument(
        "--weights-config",
        help="Path to custom weights YAML configuration",
    )
    parser.add_argument(
        "--min-conviction",
        type=float,
        help="Minimum conviction score for output filtering (overrides config)",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/",
        help="Output directory for reports (default: reports/)",
    )
    parser.add_argument(
        "--output-prefix",
        default="edge_signal_aggregator",
        help="Prefix for output filenames",
    )

    args = parser.parse_args()

    # Check if at least one input is provided
    if not any(
        [
            args.edge_candidates,
            args.edge_concepts,
            args.themes,
            args.sectors,
            args.institutional,
            args.hints,
        ]
    ):
        print("Error: At least one input source must be provided", file=sys.stderr)
        parser.print_help(sys.stderr)
        return 1

    # Load configuration
    try:
        config = load_config(args.weights_config)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if args.min_conviction is not None:
        config["min_conviction"] = args.min_conviction

    # Load input files
    edge_candidates = load_json_files(args.edge_candidates)
    edge_concepts = load_yaml_files(args.edge_concepts)
    themes = load_json_files(args.themes)
    sectors = load_json_files(args.sectors)
    institutional = load_json_files(args.institutional)
    hints = load_yaml_files(args.hints)

    # Run aggregation
    result = aggregate_signals(
        edge_candidates=edge_candidates,
        edge_concepts=edge_concepts,
        themes=themes,
        sectors=sectors,
        institutional=institutional,
        hints=hints,
        config=config,
    )

    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp for filenames
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    # Write JSON report
    json_path = output_dir / f"{args.output_prefix}_{timestamp}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"JSON report written to: {json_path}")

    # Write Markdown report
    md_content = generate_markdown_report(result)
    md_path = output_dir / f"{args.output_prefix}_{timestamp}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Markdown report written to: {md_path}")

    # Print summary to stdout
    print("\n--- Aggregation Summary ---")
    print(f"Total input signals: {result['summary']['total_input_signals']}")
    print(f"Unique after dedup: {result['summary']['unique_signals_after_dedup']}")
    print(f"Contradictions found: {result['summary']['contradictions_found']}")
    print(
        f"Above threshold ({config['min_conviction']}): {result['summary']['signals_above_threshold']}"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
