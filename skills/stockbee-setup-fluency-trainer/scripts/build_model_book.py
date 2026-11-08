#!/usr/bin/env python3
"""
Stockbee Setup Fluency Trainer

Build and maintain a Stockbee-style setup model book from momentum-burst
screener outputs. The trainer records every candidate as a study example, then
updates 3/5-day forward outcomes with MFE/MAE and outcome tags so the trader can
learn which setup variants are working.

Input modes:
  1. ingest    - add candidates from stockbee-momentum-burst-screener JSON
  2. update    - attach 3/5-day forward outcomes from offline JSON or FMP
  3. summarize - aggregate model-book evidence by rating, trigger, and tags

The script is intentionally signal/research oriented. It does not place orders,
generate broker instructions, or treat screener candidates as automatic trades.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import statistics
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover - optional FMP path
    requests = None

SCHEMA_VERSION = "1.0"
SKILL_NAME = "stockbee-setup-fluency-trainer"
DEFAULT_HORIZONS = (3, 5)
DEFAULT_MODEL_BOOK = "state/stockbee/model_book.jsonl"


@dataclass(frozen=True)
class Bar:
    """Normalized OHLCV bar sorted oldest -> newest."""

    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


class ApiCallBudgetExceeded(Exception):
    """Raised when max_api_calls is exhausted."""


_SHARED_FMP_MODULE = "_stockbee_setup_fluency_trainer_fmp_client"


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

    def __init__(self, api_key: str | None = None, max_api_calls: int = 200):
        if requests is None:
            raise RuntimeError("requests is not installed; use --prices-json or install requests")
        self.api_key = api_key or os.getenv("FMP_API_KEY")
        if not self.api_key:
            raise ValueError("FMP API key required. Set FMP_API_KEY or pass --api-key.")
        shared = _load_shared_fmp()
        self._budget_error = shared.ApiCallBudgetExceeded
        self._client = shared.FMPClient(api_key=self.api_key, max_api_calls=max_api_calls)
        self.cache: dict[str, Any] = {}
        self.failed_requests = 0

    session = _delegated("session")
    api_calls_made = _delegated("api_calls_made")
    max_api_calls = _delegated("max_api_calls")
    last_call_time = _delegated("last_call_time")
    rate_limit_reached = _delegated("rate_limit_reached")

    def get_historical_prices(self, symbol: str, days: int = 80) -> list[dict[str, Any]]:
        symbol = normalize_symbol(symbol)
        cache_key = f"history:{symbol}:{days}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        try:
            data = self._client.fetch_eod_rows(symbol, days, pad_days=10, quiet=False)
        except self._budget_error as exc:
            raise ApiCallBudgetExceeded(str(exc)) from exc
        if data is None:
            self.failed_requests += 1
            return []
        bars = normalize_price_bars(data, symbol=symbol)
        result = [bar_to_dict(b) for b in bars[-days:]]
        self.cache[cache_key] = result
        return result

    def stats(self) -> dict[str, Any]:
        return {
            "api_calls_made": self.api_calls_made,
            "max_api_calls": self.max_api_calls,
            "budget_remaining": max(0, self.max_api_calls - self.api_calls_made),
            "rate_limit_reached": self.rate_limit_reached,
            "failed_requests": self.failed_requests,
        }


def normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper().replace(".", "-")


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def bar_to_dict(bar: Bar) -> dict[str, Any]:
    return {
        "date": bar.date,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


def parse_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def normalize_price_bars(payload: Any, symbol: str | None = None) -> list[Bar]:
    """Normalize several common OHLCV JSON shapes into oldest -> newest bars.

    Supported shapes:
    - [{date, open, high, low, close, volume}, ...]
    - {"historical": [...]}
    - {"prices": {"AAPL": [...]}} handled by load_prices_json, not here
    - FMP stable flat list that may include a per-row symbol field
    """
    rows: Any
    if isinstance(payload, dict) and "historical" in payload:
        rows = payload.get("historical") or []
    elif isinstance(payload, dict) and "bars" in payload:
        rows = payload.get("bars") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        return []

    bars = []
    target = normalize_symbol(symbol) if symbol else None
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_symbol = normalize_symbol(row.get("symbol")) if row.get("symbol") else None
        if target and row_symbol and row_symbol != target:
            continue
        dt = str(row.get("date") or row.get("datetime") or "")[:10]
        if len(dt) != 10:
            continue
        open_ = to_float(row.get("open"), default=to_float(row.get("close")))
        high = to_float(row.get("high"), default=max(open_, to_float(row.get("close"))))
        low = to_float(row.get("low"), default=min(open_, to_float(row.get("close"))))
        close = to_float(row.get("close"), default=to_float(row.get("adjClose")))
        volume = to_int(row.get("volume"))
        if close <= 0:
            continue
        # If high/low are absent in a close-only feed, keep them equal to close so
        # forward return still works but MFE/MAE is conservative.
        high = high if high > 0 else close
        low = low if low > 0 else close
        bars.append(Bar(date=dt, open=open_, high=high, low=low, close=close, volume=volume))

    dedup: dict[str, Bar] = {b.date: b for b in bars}
    return [dedup[k] for k in sorted(dedup.keys())]


def load_prices_json(path: str | Path) -> dict[str, list[Bar]]:
    """Load offline prices by symbol for no-API outcome updates."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "prices" in data and isinstance(data["prices"], dict):
        data = data["prices"]

    result: dict[str, list[Bar]] = {}
    if isinstance(data, dict):
        for symbol, payload in data.items():
            norm = normalize_symbol(symbol)
            bars = normalize_price_bars(payload, symbol=norm)
            if bars:
                result[norm] = bars
    elif isinstance(data, list):
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in data:
            if not isinstance(row, dict):
                continue
            symbol = normalize_symbol(row.get("symbol") or row.get("ticker"))
            if not symbol:
                continue
            grouped.setdefault(symbol, []).append(row)
        for symbol, rows in grouped.items():
            bars = normalize_price_bars(rows, symbol=symbol)
            if bars:
                result[symbol] = bars
    return result


def load_model_book(path: str | Path) -> list[dict[str, Any]]:
    path = Path(path)
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
            if isinstance(record, dict):
                records.append(record)
    return records


def save_model_book(path: str | Path, records: list[dict[str, Any]]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    records = sorted(
        records,
        key=lambda r: (r.get("setup_date", ""), r.get("symbol", ""), r.get("record_id", "")),
    )
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")


def upsert_records(
    existing: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_id = {r.get("record_id"): dict(r) for r in existing if r.get("record_id")}
    inserted = 0
    updated = 0
    for record in new_records:
        record_id = record["record_id"]
        if record_id in by_id:
            previous = by_id[record_id]
            merged = dict(previous)
            # Refresh deterministic setup fields while preserving human annotations
            # and previously calculated outcomes. Fresh ingest records carry empty
            # PENDING outcome placeholders, so they should not erase evidence that
            # has already matured.
            preserved = {
                key: previous[key]
                for key in ("human_label", "human_decision", "human_notes")
                if key in previous
            }
            previous_has_outcome = bool(previous.get("outcomes")) or previous.get("matured")
            if previous_has_outcome and not record.get("outcomes"):
                for key in ("outcomes", "overall_outcome", "matured", "last_outcome_update_at"):
                    if key in previous:
                        preserved[key] = previous[key]
            merged.update(record)
            merged.update(preserved)
            by_id[record_id] = merged
            updated += 1
        else:
            by_id[record_id] = record
            inserted += 1
    return list(by_id.values()), {"inserted": inserted, "updated": updated, "total": len(by_id)}


_PER_SYMBOL_METADATA_KEYS = frozenset({"latest_bar_dates"})


def load_screener_candidates(
    paths: Iterable[str | Path], include_rejects: bool = False
) -> list[dict[str, Any]]:
    candidates = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        report_candidates = data.get("candidates") if isinstance(data, dict) else None
        if not isinstance(report_candidates, list):
            raise ValueError(f"{path} does not look like a stockbee momentum burst JSON report")
        metadata = data.get("metadata", {}) if isinstance(data.get("metadata", {}), dict) else {}
        # Per-symbol maps (one entry per screened symbol) would be copied into
        # every persisted model-book row; candidates carry their own values.
        metadata = {k: v for k, v in metadata.items() if k not in _PER_SYMBOL_METADATA_KEYS}
        for c in report_candidates:
            if not isinstance(c, dict):
                continue
            if not include_rejects:
                state = str(c.get("state", "")).upper()
                if state in {"REJECT", "REJECTED", "INVALID"}:
                    continue
            item = dict(c)
            item["_source_report"] = str(path)
            item["_source_metadata"] = metadata
            candidates.append(item)
    return candidates


def derive_setup_tags(candidate: dict[str, Any]) -> list[str]:
    tags: set[str] = set()
    for tag in candidate.get("trigger_tags", []) or []:
        if tag:
            tags.add(str(tag))
    for tag in candidate.get("soft_failure_tags", []) or []:
        if tag:
            tags.add(f"soft_{tag}")
    for tag in candidate.get("reject_reasons", []) or []:
        if tag:
            tags.add(f"reject_{tag}")

    rating = str(candidate.get("rating") or "")
    if rating:
        tags.add(f"rating_{rating.replace('+', 'plus').replace('-', 'minus')}")

    close_location = to_float(candidate.get("close_location_pct"))
    if close_location >= 85:
        tags.add("close_near_high")
    elif close_location < 50:
        tags.add("weak_close_location")

    volume_ratio = to_float(candidate.get("volume_ratio_1d"))
    if volume_ratio >= 3:
        tags.add("high_volume_expansion")
    elif 0 < volume_ratio < 1.2:
        tags.add("thin_volume_confirmation")

    base_width = to_float(candidate.get("base_width_pct"))
    if 0 < base_width <= 8:
        tags.add("tight_base")
    elif base_width >= 15:
        tags.add("wide_base")

    prior_base_days = to_int(candidate.get("prior_base_days"))
    if 3 <= prior_base_days <= 20:
        tags.add("controlled_3_to_20_day_base")
    elif prior_base_days > 30:
        tags.add("long_base")

    risk = to_float(candidate.get("risk_pct_to_stop"))
    if 0 < risk <= 3:
        tags.add("compact_risk")
    elif risk >= 6:
        tags.add("wide_risk")

    if candidate.get("volume_dry_up"):
        tags.add("volume_dry_up")
    if candidate.get("recent_4pct_breakdown"):
        tags.add("recent_4pct_breakdown")
    if to_int(candidate.get("prior_up_streak")) >= 3:
        tags.add("three_days_up_before_trigger")

    return sorted(tags)


def make_record(
    candidate: dict[str, Any], source_skill: str = "stockbee-momentum-burst-screener"
) -> dict[str, Any]:
    symbol = normalize_symbol(candidate.get("symbol"))
    setup_date = str(candidate.get("date") or candidate.get("setup_date") or "")[:10]
    if not symbol or len(setup_date) != 10:
        raise ValueError(f"candidate missing symbol or setup date: {candidate}")
    primary_trigger = str(candidate.get("primary_trigger") or "unknown")
    record_id = f"stockbee_mb:{symbol}:{setup_date}:{primary_trigger}"

    entry = to_float(candidate.get("entry_reference"), default=to_float(candidate.get("close")))
    stop = to_float(candidate.get("stop_reference"), default=to_float(candidate.get("low")))

    return {
        "schema_version": SCHEMA_VERSION,
        "record_id": record_id,
        "source_skill": source_skill,
        "source_report": candidate.get("_source_report"),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "symbol": symbol,
        "setup_date": setup_date,
        "setup_type": "stockbee_momentum_burst",
        "primary_trigger": primary_trigger,
        "trigger_tags": candidate.get("trigger_tags", []) or [],
        "setup_tags": derive_setup_tags(candidate),
        "rating": candidate.get("rating"),
        "setup_score": to_float(candidate.get("setup_score")),
        "state_at_ingest": candidate.get("state"),
        "entry_reference": entry,
        "stop_reference": stop,
        "risk_pct_to_stop": to_float(candidate.get("risk_pct_to_stop")),
        "day_gain_pct": to_float(candidate.get("day_gain_pct")),
        "volume_ratio_1d": to_float(candidate.get("volume_ratio_1d")),
        "volume_ratio_20d": to_float(candidate.get("volume_ratio_20d")),
        "close_location_pct": to_float(candidate.get("close_location_pct")),
        "prior_base_days": to_int(candidate.get("prior_base_days")),
        "base_width_pct": to_float(candidate.get("base_width_pct")),
        "human_label": None,
        "human_decision": "unknown",
        "human_notes": "",
        "outcomes": {},
        "overall_outcome": "PENDING",
        "matured": False,
        "raw_candidate": candidate,
    }


def is_studyable_candidate(candidate: dict[str, Any]) -> tuple[bool, str | None]:
    symbol = normalize_symbol(candidate.get("symbol"))
    setup_date = str(candidate.get("date") or candidate.get("setup_date") or "")[:10]
    if not symbol:
        return False, "missing_symbol"
    if len(setup_date) != 10:
        return False, "missing_setup_date"
    return True, None


def make_studyable_records(
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    records = []
    stats = {"candidates_loaded": len(candidates), "studyable": 0, "skipped": 0}
    for candidate in candidates:
        studyable, reason = is_studyable_candidate(candidate)
        if not studyable:
            stats["skipped"] += 1
            key = f"skipped_{reason or 'unknown'}"
            stats[key] = stats.get(key, 0) + 1
            continue
        records.append(make_record(candidate))
        stats["studyable"] += 1
    return records, stats


def future_bars_after_setup(bars: list[Bar], setup_date: str) -> list[Bar]:
    setup_dt = parse_date(setup_date)
    return [bar for bar in bars if parse_date(bar.date) > setup_dt]


def calculate_window_outcome(
    record: dict[str, Any],
    bars: list[Bar],
    horizon: int,
) -> dict[str, Any]:
    """Calculate forward close return plus MFE/MAE for N future trading days."""
    entry = to_float(record.get("entry_reference"))
    stop = to_float(record.get("stop_reference"))
    if entry <= 0:
        return {"horizon_days": horizon, "matured": False, "reason": "missing_entry"}

    future = future_bars_after_setup(bars, str(record.get("setup_date")))
    if len(future) < horizon:
        return {
            "horizon_days": horizon,
            "matured": False,
            "available_future_bars": len(future),
            "reason": "not_enough_future_bars",
        }

    window = future[:horizon]
    close_bar = window[-1]
    max_high = max(bar.high for bar in window)
    min_low = min(bar.low for bar in window)
    fwd = ((close_bar.close / entry) - 1.0) * 100.0
    mfe = ((max_high / entry) - 1.0) * 100.0
    mae = ((min_low / entry) - 1.0) * 100.0

    stop_hit = False
    stop_hit_date = None
    if stop > 0:
        for bar in window:
            if bar.low <= stop:
                stop_hit = True
                stop_hit_date = bar.date
                break

    tag = classify_outcome(fwd_return_pct=fwd, mfe_pct=mfe, mae_pct=mae, stop_hit=stop_hit)
    return {
        "horizon_days": horizon,
        "matured": True,
        "close_date": close_bar.date,
        "close": round(close_bar.close, 4),
        "forward_return_pct": round(fwd, 2),
        "mfe_pct": round(mfe, 2),
        "mae_pct": round(mae, 2),
        "max_high": round(max_high, 4),
        "min_low": round(min_low, 4),
        "stop_hit": stop_hit,
        "stop_hit_date": stop_hit_date,
        "outcome_tag": tag,
    }


def classify_outcome(fwd_return_pct: float, mfe_pct: float, mae_pct: float, stop_hit: bool) -> str:
    if stop_hit:
        return "FAILED_STOP"
    if mfe_pct >= 12 or fwd_return_pct >= 8:
        return "STRONG_WINNER"
    if mfe_pct >= 6 or fwd_return_pct >= 4:
        return "WORKED"
    if fwd_return_pct <= -2:
        return "FAILED_FADE"
    if mae_pct <= -5 and fwd_return_pct < 2:
        return "CHOPPY_FAILURE"
    return "NEUTRAL"


def derive_overall_outcome(outcomes: dict[str, dict[str, Any]], primary_horizon: int = 5) -> str:
    preferred = outcomes.get(f"{primary_horizon}d")
    if not preferred or not preferred.get("matured"):
        return "PENDING"
    return str(preferred.get("outcome_tag", "UNKNOWN"))


def update_record_outcomes(
    records: list[dict[str, Any]],
    prices_by_symbol: dict[str, list[Bar]],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    only_pending: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    updated = 0
    skipped_no_prices = 0
    still_pending = 0
    matured = 0

    for record in records:
        if only_pending and record.get("matured"):
            continue
        symbol = normalize_symbol(record.get("symbol"))
        bars = prices_by_symbol.get(symbol)
        if not bars:
            record["update_error"] = "missing_prices"
            skipped_no_prices += 1
            continue
        outcomes = dict(record.get("outcomes") or {})
        for horizon in horizons:
            outcomes[f"{horizon}d"] = calculate_window_outcome(record, bars, horizon)
        record["outcomes"] = outcomes
        record["overall_outcome"] = derive_overall_outcome(outcomes, primary_horizon=max(horizons))
        record["matured"] = record["overall_outcome"] != "PENDING"
        record["updated_at"] = datetime.now().isoformat(timespec="seconds")
        record["last_outcome_update_at"] = record["updated_at"]
        if record["matured"]:
            matured += 1
        else:
            still_pending += 1
        updated += 1

    return records, {
        "updated": updated,
        "matured": matured,
        "still_pending": still_pending,
        "skipped_no_prices": skipped_no_prices,
    }


def values_for_metric(records: list[dict[str, Any]], metric_path: str) -> list[float]:
    parts = metric_path.split(".")
    values = []
    for record in records:
        node: Any = record
        for part in parts:
            if not isinstance(node, dict):
                node = None
                break
            node = node.get(part)
        value = to_float(node, default=float("nan"))
        if not math.isnan(value):
            values.append(value)
    return values


def group_records(records: list[dict[str, Any]], group_by: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        if group_by == "setup_tags":
            tags = record.get("setup_tags") or ["untagged"]
            for tag in tags:
                groups.setdefault(str(tag), []).append(record)
        else:
            key = record.get(group_by) or "unknown"
            groups.setdefault(str(key), []).append(record)
    return groups


def summarize_group(records: list[dict[str, Any]]) -> dict[str, Any]:
    matured = [r for r in records if r.get("matured")]
    sample = len(matured)
    if sample == 0:
        return {"sample_size": 0, "pending": len(records), "win_rate_pct": None}

    winners = [r for r in matured if r.get("overall_outcome") in {"WORKED", "STRONG_WINNER"}]
    failures = [
        r
        for r in matured
        if str(r.get("overall_outcome", "")).startswith("FAILED")
        or r.get("overall_outcome") == "CHOPPY_FAILURE"
    ]
    strong = [r for r in matured if r.get("overall_outcome") == "STRONG_WINNER"]
    stop = [r for r in matured if r.get("outcomes", {}).get("5d", {}).get("stop_hit")]

    ret3 = values_for_metric(matured, "outcomes.3d.forward_return_pct")
    ret5 = values_for_metric(matured, "outcomes.5d.forward_return_pct")
    mfe5 = values_for_metric(matured, "outcomes.5d.mfe_pct")
    mae5 = values_for_metric(matured, "outcomes.5d.mae_pct")

    return {
        "sample_size": sample,
        "pending": len(records) - sample,
        "win_rate_pct": round((len(winners) / sample) * 100, 1),
        "failure_rate_pct": round((len(failures) / sample) * 100, 1),
        "strong_winner_rate_pct": round((len(strong) / sample) * 100, 1),
        "stop_hit_rate_pct": round((len(stop) / sample) * 100, 1),
        "avg_3d_return_pct": round(statistics.fmean(ret3), 2) if ret3 else None,
        "avg_5d_return_pct": round(statistics.fmean(ret5), 2) if ret5 else None,
        "median_5d_return_pct": round(statistics.median(ret5), 2) if ret5 else None,
        "avg_5d_mfe_pct": round(statistics.fmean(mfe5), 2) if mfe5 else None,
        "avg_5d_mae_pct": round(statistics.fmean(mae5), 2) if mae5 else None,
    }


def summarize_model_book(
    records: list[dict[str, Any]],
    group_by_fields: list[str],
    min_sample: int = 3,
) -> dict[str, Any]:
    matured = [r for r in records if r.get("matured")]
    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_records": len(records),
        "matured_records": len(matured),
        "pending_records": len(records) - len(matured),
        "overall": summarize_group(records),
        "groups": {},
        "rule_candidates": [],
    }
    for group_by in group_by_fields:
        groups = group_records(records, group_by)
        rows = []
        for key, group in groups.items():
            stats = summarize_group(group)
            if stats.get("sample_size", 0) < min_sample:
                continue
            row = {"group": key, **stats}
            rows.append(row)
            if is_promote_candidate(row):
                summary["rule_candidates"].append(
                    {
                        "action": "promote",
                        "group_by": group_by,
                        "group": key,
                        "reason": "High win rate with positive 5d expectancy and acceptable drawdown.",
                        "evidence": row,
                    }
                )
            elif is_downgrade_candidate(row):
                summary["rule_candidates"].append(
                    {
                        "action": "downgrade_or_filter",
                        "group_by": group_by,
                        "group": key,
                        "reason": "Weak 5d expectancy or high failure rate. Review examples before changing rules.",
                        "evidence": row,
                    }
                )
        rows.sort(
            key=lambda r: (
                r.get("avg_5d_return_pct") if r.get("avg_5d_return_pct") is not None else -999,
                r.get("win_rate_pct") if r.get("win_rate_pct") is not None else -999,
            ),
            reverse=True,
        )
        summary["groups"][group_by] = rows
    return summary


def is_promote_candidate(row: dict[str, Any]) -> bool:
    sample = row.get("sample_size") or 0
    win_rate = row.get("win_rate_pct") or 0
    avg5 = row.get("avg_5d_return_pct") or 0
    mae = row.get("avg_5d_mae_pct") or 0
    return sample >= 5 and win_rate >= 60 and avg5 >= 2 and mae > -5


def is_downgrade_candidate(row: dict[str, Any]) -> bool:
    sample = row.get("sample_size") or 0
    fail_rate = row.get("failure_rate_pct") or 0
    avg5 = row.get("avg_5d_return_pct") or 0
    return sample >= 5 and (fail_rate >= 50 or avg5 <= -1)


def write_json_report(payload: dict[str, Any], output_dir: str | Path, prefix: str) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = output_dir / f"{prefix}_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def write_markdown_report(payload: dict[str, Any], output_dir: str | Path, prefix: str) -> Path:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    path = output_dir / f"{prefix}_{ts}.md"
    lines = []
    title = payload.get("title") or "Stockbee Setup Fluency Report"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(
        f"Generated: {payload.get('generated_at') or datetime.now().isoformat(timespec='seconds')}"
    )
    lines.append("")

    if "ingest" in payload:
        stats = payload["ingest"]
        lines.append("## Ingest")
        lines.append("")
        lines.append(f"- Candidates loaded: {stats.get('candidates_loaded', 0)}")
        lines.append(f"- Studyable records: {stats.get('studyable', 0)}")
        lines.append(f"- Skipped: {stats.get('skipped', 0)}")
        if stats.get("skipped_missing_setup_date"):
            lines.append(
                f"- Skipped missing setup date: {stats.get('skipped_missing_setup_date', 0)}"
            )
        if stats.get("skipped_missing_symbol"):
            lines.append(f"- Skipped missing symbol: {stats.get('skipped_missing_symbol', 0)}")
        lines.append(f"- Inserted: {stats.get('inserted', 0)}")
        lines.append(f"- Updated: {stats.get('updated', 0)}")
        lines.append(f"- Total model-book records: {stats.get('total', 0)}")
        lines.append("")

    if "update" in payload:
        stats = payload["update"]
        lines.append("## Outcome Update")
        lines.append("")
        lines.append(f"- Updated: {stats.get('updated', 0)}")
        lines.append(f"- Matured: {stats.get('matured', 0)}")
        lines.append(f"- Still pending: {stats.get('still_pending', 0)}")
        lines.append(f"- Missing prices: {stats.get('skipped_no_prices', 0)}")
        lines.append("")

    if "overall" in payload:
        overall = payload.get("overall") or {}
        lines.append("## Overall")
        lines.append("")
        lines.append(f"- Total records: {payload.get('total_records', 0)}")
        lines.append(f"- Matured records: {payload.get('matured_records', 0)}")
        lines.append(f"- Pending records: {payload.get('pending_records', 0)}")
        if overall.get("sample_size"):
            lines.append(f"- Win rate: {overall.get('win_rate_pct')}%")
            lines.append(f"- Avg 5d return: {overall.get('avg_5d_return_pct')}%")
            lines.append(
                f"- Avg 5d MFE / MAE: {overall.get('avg_5d_mfe_pct')}% / {overall.get('avg_5d_mae_pct')}%"
            )
        lines.append("")

    groups = payload.get("groups") or {}
    for group_by, rows in groups.items():
        lines.append(f"## Cohorts by {group_by}")
        lines.append("")
        if not rows:
            lines.append("No cohorts met the sample threshold.")
            lines.append("")
            continue
        lines.append("| Group | N | Win% | Fail% | Avg 5d | Avg MFE | Avg MAE |")
        lines.append("|---|---:|---:|---:|---:|---:|---:|")
        for row in rows[:20]:
            lines.append(
                f"| {row.get('group')} | {row.get('sample_size')} | {row.get('win_rate_pct')} | "
                f"{row.get('failure_rate_pct')} | {row.get('avg_5d_return_pct')} | "
                f"{row.get('avg_5d_mfe_pct')} | {row.get('avg_5d_mae_pct')} |"
            )
        lines.append("")

    rules = payload.get("rule_candidates") or []
    if rules:
        lines.append("## Rule Candidates")
        lines.append("")
        for rule in rules[:20]:
            evidence = rule.get("evidence", {})
            lines.append(
                f"- **{rule.get('action')}** `{rule.get('group_by')}={rule.get('group')}`: "
                f"{rule.get('reason')} N={evidence.get('sample_size')}, "
                f"Win={evidence.get('win_rate_pct')}%, Avg5d={evidence.get('avg_5d_return_pct')}%."
            )
        lines.append("")

    lines.append("## Reminder")
    lines.append("")
    lines.append(
        "This model book is a learning dataset, not an execution engine. Promote or downgrade rules only after manual chart review of representative examples."
    )
    lines.append("")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


def parse_horizons(value: str) -> tuple[int, ...]:
    horizons = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        n = int(part)
        if n <= 0:
            raise ValueError("horizons must be positive integers")
        horizons.append(n)
    if not horizons:
        raise ValueError("at least one horizon is required")
    return tuple(sorted(set(horizons)))


def command_ingest(args: argparse.Namespace) -> int:
    candidates = load_screener_candidates(args.screener_json, include_rejects=args.include_rejects)
    new_records, ingest_stats = make_studyable_records(candidates)
    existing = load_model_book(args.model_book)
    records, upsert_stats = upsert_records(existing, new_records)
    stats = {**ingest_stats, **upsert_stats}
    save_model_book(args.model_book, records)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "title": "Stockbee Setup Fluency Ingest Report",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model_book": args.model_book,
        "source_reports": args.screener_json,
        "candidates_loaded": len(candidates),
        "ingest": stats,
    }
    json_path = write_json_report(payload, args.output_dir, "stockbee_setup_fluency_ingest")
    md_path = write_markdown_report(payload, args.output_dir, "stockbee_setup_fluency_ingest")
    print(
        f"Ingested {stats.get('studyable', 0)} studyable candidates into {args.model_book} "
        f"({stats.get('skipped', 0)} skipped)"
    )
    print(f"JSON Report: {json_path}")
    print(f"Markdown Report: {md_path}")
    return 0


def requested_symbols(records: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {normalize_symbol(r.get("symbol")) for r in records if normalize_symbol(r.get("symbol"))}
    )


def build_prices_for_update(
    args: argparse.Namespace, records: list[dict[str, Any]]
) -> tuple[dict[str, list[Bar]], dict[str, Any] | None]:
    if args.prices_json:
        return load_prices_json(args.prices_json), None

    client = FMPClient(api_key=args.api_key, max_api_calls=args.max_api_calls)
    prices: dict[str, list[Bar]] = {}
    symbols = requested_symbols(records)
    for symbol in symbols:
        raw = client.get_historical_prices(symbol, days=args.history_days)
        bars = normalize_price_bars(raw, symbol=symbol)
        if bars:
            prices[symbol] = bars
    return prices, client.stats()


def command_update(args: argparse.Namespace) -> int:
    records = load_model_book(args.model_book)
    if not records:
        print(f"No records found in {args.model_book}")
        return 0
    prices, api_stats = build_prices_for_update(args, records)
    if api_stats is not None:
        symbol_count = len(requested_symbols(records))
        if symbol_count > 0 and api_stats["failed_requests"] == symbol_count:
            print(
                f"ERROR: FMP price fetch failed for all {symbol_count} symbols; "
                "model book not updated",
                file=sys.stderr,
            )
            return 1
    horizons = parse_horizons(args.horizons)
    records, stats = update_record_outcomes(
        records, prices, horizons=horizons, only_pending=args.only_pending
    )
    save_model_book(args.model_book, records)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "title": "Stockbee Setup Fluency Outcome Update",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model_book": args.model_book,
        "horizons": list(horizons),
        "prices_source": args.prices_json or "fmp",
        "update": stats,
        "api_stats": api_stats,
    }
    json_path = write_json_report(payload, args.output_dir, "stockbee_setup_fluency_update")
    md_path = write_markdown_report(payload, args.output_dir, "stockbee_setup_fluency_update")
    print(f"Updated outcomes in {args.model_book}")
    print(f"JSON Report: {json_path}")
    print(f"Markdown Report: {md_path}")
    return 0


def command_summarize(args: argparse.Namespace) -> int:
    records = load_model_book(args.model_book)
    group_by = [part.strip() for part in args.group_by.split(",") if part.strip()]
    summary = summarize_model_book(records, group_by_fields=group_by, min_sample=args.min_sample)
    summary["model_book"] = args.model_book
    json_path = write_json_report(summary, args.output_dir, "stockbee_setup_fluency_summary")
    md_path = write_markdown_report(summary, args.output_dir, "stockbee_setup_fluency_summary")
    print(f"Summarized {len(records)} records from {args.model_book}")
    print(f"JSON Report: {json_path}")
    print(f"Markdown Report: {md_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stockbee setup fluency model-book trainer")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Ingest Stockbee momentum-burst screener reports")
    ingest.add_argument(
        "--screener-json", nargs="+", required=True, help="Momentum burst JSON report(s)"
    )
    ingest.add_argument("--model-book", default=DEFAULT_MODEL_BOOK, help="JSONL model-book path")
    ingest.add_argument("--output-dir", default="reports/", help="Report output directory")
    ingest.add_argument(
        "--include-rejects",
        action="store_true",
        help="Also ingest rejected candidates as negative examples",
    )
    ingest.set_defaults(func=command_ingest)

    update = sub.add_parser(
        "update", help="Update pending model-book records with forward outcomes"
    )
    update.add_argument("--model-book", default=DEFAULT_MODEL_BOOK, help="JSONL model-book path")
    update.add_argument("--prices-json", help="Offline OHLCV JSON by symbol; avoids FMP")
    update.add_argument("--api-key", help="FMP API key; defaults to FMP_API_KEY")
    update.add_argument("--max-api-calls", type=int, default=200, help="FMP call budget")
    update.add_argument(
        "--history-days", type=int, default=80, help="Daily bars per symbol when using FMP"
    )
    update.add_argument(
        "--horizons", default="3,5", help="Comma-separated forward horizons in trading days"
    )
    update.add_argument("--output-dir", default="reports/", help="Report output directory")
    update.add_argument(
        "--only-pending",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Only update records not yet matured",
    )
    update.set_defaults(func=command_update)

    summarize = sub.add_parser("summarize", help="Aggregate model-book evidence into cohort stats")
    summarize.add_argument("--model-book", default=DEFAULT_MODEL_BOOK, help="JSONL model-book path")
    summarize.add_argument(
        "--group-by",
        default="rating,primary_trigger,setup_tags",
        help="Comma-separated fields or setup_tags",
    )
    summarize.add_argument(
        "--min-sample", type=int, default=3, help="Minimum matured records per cohort"
    )
    summarize.add_argument("--output-dir", default="reports/", help="Report output directory")
    summarize.set_defaults(func=command_summarize)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
