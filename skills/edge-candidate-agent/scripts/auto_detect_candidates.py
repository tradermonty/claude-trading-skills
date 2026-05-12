#!/usr/bin/env python3
"""Auto-detect edge candidates from EOD OHLCV and optional human hints."""

from __future__ import annotations

import argparse
import json
import math
import re
import shlex
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REQUIRED_OHLCV_COLUMNS = {
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
}

ENTRY_FAMILY_TO_HYPOTHESIS = {
    "pivot_breakout": "breakout",
    "gap_up_continuation": "earnings_drift",
    "panic_reversal": "panic_reversal",
    "news_reaction": "news_reaction",
}

RESEARCH_ONLY_HYPOTHESES = {
    "regime_shift",
    "sector_x_stock",
    "calendar_anomaly",
    "futures_trigger",
}

FAMILY_NAME = {
    "pivot_breakout": "Pivot Breakout",
    "gap_up_continuation": "Gap-Up Continuation",
    "panic_reversal": "Panic Reversal",
    "news_reaction": "News Reaction",
}

DEFAULT_MECHANISM_TAG = {
    "pivot_breakout": "behavior",
    "gap_up_continuation": "structure",
    "panic_reversal": "behavior",
    "news_reaction": "behavior",
}

HINT_KEYWORDS = {
    "pivot_breakout": [
        "breakout",
        "pivot",
        "new high",
        "vcp",
        "contraction",
        "base",
        "momentum",
    ],
    "gap_up_continuation": [
        "gap",
        "earnings",
        "post-earnings",
        "follow-through",
        "drift",
    ],
    "panic_reversal": [
        "reversal",
        "capitulation",
        "panic",
        "washout",
        "selloff",
        "oversold",
    ],
    "news_reaction": [
        "news",
        "reaction",
        "event",
        "catalyst",
        "extreme gap",
        "binary",
    ],
}


class AutoDetectError(Exception):
    """Raised when auto-detection cannot proceed."""


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp value into the provided inclusive range."""
    if value < low:
        return low
    if value > high:
        return high
    return value


def sanitize_identifier(value: str) -> str:
    """Convert arbitrary text into safe lowercase identifier."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return re.sub(r"_+", "_", cleaned)


def parse_as_of_date(raw_as_of: str | None) -> date | None:
    """Parse YYYY-MM-DD date text."""
    if raw_as_of is None:
        return None
    try:
        return datetime.strptime(raw_as_of, "%Y-%m-%d").date()
    except ValueError as exc:
        raise AutoDetectError(f"invalid --as-of format (expected YYYY-MM-DD): {raw_as_of}") from exc


def infer_entry_family_from_text(text: str) -> str | None:
    """Infer entry family from free-form hint text."""
    lowered = text.lower()
    for family, keywords in HINT_KEYWORDS.items():
        for keyword in keywords:
            if keyword in lowered:
                return family
    return None


def normalize_hints(raw_hints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize raw hints into consistent structure."""
    normalized: list[dict[str, Any]] = []

    for idx, hint in enumerate(raw_hints):
        if not isinstance(hint, dict):
            continue

        title = str(hint.get("title") or hint.get("observation") or f"hint_{idx + 1}").strip()
        preferred = hint.get("preferred_entry_family")
        entry_family: str | None = None

        if isinstance(preferred, str) and preferred in ENTRY_FAMILY_TO_HYPOTHESIS:
            entry_family = preferred
        else:
            free_text = " ".join(
                [
                    str(hint.get("title", "")),
                    str(hint.get("observation", "")),
                    str(hint.get("hypothesis", "")),
                ]
            )
            entry_family = infer_entry_family_from_text(free_text)

        symbols_raw = hint.get("symbols", [])
        symbols: set[str] = set()
        if isinstance(symbols_raw, list):
            for symbol in symbols_raw:
                if isinstance(symbol, str) and symbol.strip():
                    symbols.add(symbol.strip().upper())

        normalized.append(
            {
                "title": title or f"hint_{idx + 1}",
                "entry_family": entry_family,
                "symbols": symbols,
                "regime_bias": str(hint.get("regime_bias", "")).strip(),
                "mechanism_tag": str(hint.get("mechanism_tag", "")).strip(),
            }
        )

    return normalized


def hint_match_boost(
    symbol: str, entry_family: str, hints: list[dict[str, Any]]
) -> tuple[float, list[str]]:
    """Return score boost and matching hint titles."""
    boost = 0.0
    matched_titles: list[str] = []
    normalized_symbol = symbol.upper()

    for hint in hints:
        if hint.get("entry_family") != entry_family:
            continue

        title = str(hint.get("title", "hint")).strip() or "hint"
        symbols = hint.get("symbols", set())
        if symbols and normalized_symbol in symbols:
            boost += 12.0
            matched_titles.append(title)
        elif not symbols:
            boost += 6.0
            matched_titles.append(title)

    return clamp(boost, 0.0, 20.0), matched_titles


def score_breakout_candidate(
    record: dict[str, Any], regime_label: str, hint_boost: float = 0.0
) -> float:
    """Score pivot breakout candidate."""
    rs_rank = float(record.get("rs_rank_pct", 0.0) or 0.0)
    rel_volume = float(record.get("rel_volume", 0.0) or 0.0)
    close_pos = float(record.get("close_pos", 0.0) or 0.0)
    atr_pct = float(record.get("atr_pct", 0.0) or 0.0)
    close = float(record.get("close", 0.0) or 0.0)
    high20_prev = float(record.get("high20_prev", 0.0) or 0.0)

    breakout_strength = 0.0
    if high20_prev > 0:
        breakout_strength = (close / high20_prev) - 1.0

    regime_component = {"RiskOn": 10.0, "Neutral": 5.0, "RiskOff": -5.0}.get(regime_label, 0.0)
    atr_penalty = clamp((atr_pct - 0.08) / 0.07, 0.0, 1.0) * 15.0

    score = (
        clamp(rs_rank, 0.0, 1.0) * 40.0
        + clamp(rel_volume / 3.0, 0.0, 1.0) * 20.0
        + clamp(breakout_strength / 0.08, 0.0, 1.0) * 20.0
        + clamp(close_pos, 0.0, 1.0) * 10.0
        + regime_component
        + hint_boost
        - atr_penalty
    )
    return round(clamp(score), 2)


def score_gap_candidate(
    record: dict[str, Any], regime_label: str, hint_boost: float = 0.0
) -> float:
    """Score gap-up continuation candidate."""
    gap = float(record.get("gap", 0.0) or 0.0)
    rel_volume = float(record.get("rel_volume", 0.0) or 0.0)
    close_pos = float(record.get("close_pos", 0.0) or 0.0)
    close = float(record.get("close", 0.0) or 0.0)
    ma50 = float(record.get("ma50", 0.0) or 0.0)
    ma200 = float(record.get("ma200", 0.0) or 0.0)
    atr_pct = float(record.get("atr_pct", 0.0) or 0.0)

    trend_score = 0.0
    if close > ma50 > 0:
        trend_score += 10.0
    if close > ma200 > 0:
        trend_score += 10.0

    regime_component = {"RiskOn": 8.0, "Neutral": 4.0, "RiskOff": -8.0}.get(regime_label, 0.0)
    atr_penalty = clamp((atr_pct - 0.10) / 0.08, 0.0, 1.0) * 10.0

    score = (
        clamp(gap / 0.12, 0.0, 1.0) * 35.0
        + clamp(rel_volume / 4.0, 0.0, 1.0) * 25.0
        + clamp(close_pos, 0.0, 1.0) * 20.0
        + trend_score
        + regime_component
        + hint_boost
        - atr_penalty
    )
    return round(clamp(score), 2)


def score_reversal_candidate(
    record: dict[str, Any], regime_label: str, hint_boost: float = 0.0
) -> float:
    """Score panic-reversal style candidate."""
    ret_1d = float(record.get("ret_1d", 0.0) or 0.0)
    rel_volume = float(record.get("rel_volume", 0.0) or 0.0)
    atr_pct = float(record.get("atr_pct", 0.0) or 0.0)
    close = float(record.get("close", 0.0) or 0.0)
    ma200 = float(record.get("ma200", 0.0) or 0.0)

    shock_component = clamp(abs(min(ret_1d, 0.0)) / 0.18, 0.0, 1.0) * 45.0
    volume_component = clamp(rel_volume / 4.0, 0.0, 1.0) * 20.0
    trend_component = 15.0 if close > ma200 > 0 else 5.0
    regime_component = {"RiskOff": 12.0, "Neutral": 7.0, "RiskOn": 2.0}.get(regime_label, 0.0)
    atr_penalty = clamp((atr_pct - 0.14) / 0.10, 0.0, 1.0) * 12.0

    score = (
        shock_component
        + volume_component
        + trend_component
        + regime_component
        + hint_boost
        - atr_penalty
    )
    return round(clamp(score), 2)


def build_ticket_payload(
    candidate: dict[str, Any],
    as_of_date: date,
    regime_label: str,
    rank: int,
    market_summary: dict[str, Any],
) -> dict[str, Any]:
    """Build research ticket payload from candidate row."""
    symbol = str(candidate["symbol"]).upper()
    entry_family_raw = candidate.get("entry_family")
    entry_family = str(entry_family_raw) if entry_family_raw is not None else None
    hypothesis_type = str(
        candidate.get("hypothesis_type")
        or (ENTRY_FAMILY_TO_HYPOTHESIS.get(entry_family) if entry_family else "regime_shift")
    )

    if entry_family in DEFAULT_MECHANISM_TAG:
        mechanism_default = DEFAULT_MECHANISM_TAG[entry_family]
    else:
        mechanism_default = "uncertain"
    mechanism_tag = str(candidate.get("mechanism_tag") or mechanism_default)

    date_text = as_of_date.strftime("%Y%m%d")
    if entry_family == "pivot_breakout":
        family_tag = "vcp"
    elif entry_family == "gap_up_continuation":
        family_tag = "gap"
    else:
        family_tag = sanitize_identifier(hypothesis_type)
    ticket_id = sanitize_identifier(f"edge_auto_{family_tag}_{symbol}_{date_text}")

    priority_score = float(candidate["priority_score"])
    rel_volume = float(candidate.get("rel_volume", 0.0) or 0.0)
    gap = float(candidate.get("gap", 0.0) or 0.0)
    close_pos = float(candidate.get("close_pos", 0.0) or 0.0)
    rs_rank_pct = float(candidate.get("rs_rank_pct", 0.0) or 0.0)

    observation = {
        "symbol": symbol,
        "priority_score": priority_score,
        "close": round(float(candidate.get("close", 0.0) or 0.0), 4),
        "rel_volume": round(rel_volume, 3),
        "gap_pct": round(gap * 100.0, 3),
        "close_pos": round(close_pos, 3),
        "rs_rank_pct": round(rs_rank_pct, 3),
        "matched_hints": candidate.get("matched_hints", []),
    }

    if hypothesis_type == "news_reaction":
        observation["abs_reaction_1d"] = round(abs(float(candidate.get("reaction_1d", 0))), 4)
        observation["reaction_direction"] = (
            "up" if float(candidate.get("reaction_1d", 0)) > 0 else "down"
        )

    if entry_family == "pivot_breakout":
        hypothesis_sentence = (
            "if breakout above prior 20-day high with elevated relative volume, "
            "then 5-20 day follow-through returns remain positive"
        )
    elif entry_family == "gap_up_continuation":
        hypothesis_sentence = (
            "if earnings-style gap-up with strong close and volume confirmation, "
            "then 10-40 day drift remains positive"
        )
    elif entry_family == "panic_reversal":
        hypothesis_sentence = (
            "if extreme downside move occurs with volume shock but long-term trend is not broken, "
            "then 3-10 day rebound probability increases"
        )
    elif entry_family == "news_reaction":
        hypothesis_sentence = (
            "if news reaction magnitude is extreme relative to baseline, "
            "then post-event drift or reversal edge may emerge"
        )
    else:
        hypothesis_sentence = str(
            candidate.get("hypothesis")
            or "if observed pattern repeats with sufficient breadth/flow confirmation, "
            "then near-term edge remains testable"
        )

    if entry_family in FAMILY_NAME:
        ticket_name = f"{FAMILY_NAME[entry_family]} {symbol} {date_text}"
        description = f"Auto-detected {FAMILY_NAME[entry_family]} candidate for {symbol}."
    else:
        hypothesis_tag = hypothesis_type.replace("_", " ").title()
        ticket_name = f"{hypothesis_tag} {symbol} {date_text}"
        description = str(
            candidate.get("description") or f"Auto-detected {hypothesis_tag} research candidate."
        )

    ticket = {
        "id": ticket_id,
        "date": as_of_date.isoformat(),
        "rank": rank,
        "name": ticket_name,
        "description": description,
        "regime": regime_label,
        "hypothesis_type": hypothesis_type,
        "mechanism_tag": mechanism_tag,
        "priority_score": priority_score,
        "holding_horizon": str(candidate.get("holding_horizon", "20D")),
        "observation": observation,
        "hypothesis": hypothesis_sentence,
        "rationale": list(
            candidate.get(
                "rationale",
                [
                    "Use regime-conditioned signal to avoid forcing long exposure in weak environments.",
                    "Prioritize candidates with liquidity and participation confirmation.",
                ],
            )
        ),
        "signal_definition": (
            {
                "entry_family": entry_family,
                "conditions": candidate.get("conditions", []),
                "trend_filter": candidate.get("trend_filter", []),
            }
            if entry_family
            else {
                "entry_family": "research_only",
                "conditions": candidate.get("conditions", []),
                "trend_filter": candidate.get("trend_filter", []),
            }
        ),
        "test_spec": {
            "period": "2016-01-01 to latest",
            "entry_timing": "next_open",
            "hold_days": [5, 20, 60],
            "validation_method": "full_sample",
            "cost_model": {"slippage_bps": 5, "commission_per_share": 0.0},
        },
        "rejection_criteria": [
            "Expected value negative after costs",
            "Phase I gate failure or unstable split behavior",
            "Regime-dependent performance concentrated in low-frequency environments",
        ],
        "market_context": {
            "regime": regime_label,
            "pct_above_ma50": market_summary.get("pct_above_ma50"),
            "avg_pair_corr_20": market_summary.get("avg_pair_corr_20"),
            "vol_trend": market_summary.get("vol_trend"),
        },
    }

    if entry_family is not None:
        ticket["entry_family"] = entry_family
        # Strategy export compatibility fields
        ticket["entry"] = {
            "conditions": list(candidate.get("conditions", [])),
            "trend_filter": list(candidate.get("trend_filter", [])),
        }
        ticket["validation"] = {"method": "full_sample"}
    else:
        ticket["research_only"] = True

    return ticket


def render_daily_report(
    as_of_date: date,
    regime_label: str,
    market_summary: dict[str, Any],
    anomalies: list[dict[str, Any]],
    exportable_tickets: list[dict[str, Any]],
    research_tickets: list[dict[str, Any]],
    watchlist_count: int,
    skipped_modules: list[str],
) -> str:
    """Render markdown daily report."""
    lines: list[str] = []
    lines.append(f"# Edge Candidate Daily Report ({as_of_date.isoformat()})")
    lines.append("")
    lines.append(f"- Regime: **{regime_label}**")
    lines.append(f"- Watchlist candidates: **{watchlist_count}**")
    lines.append(f"- Exportable tickets: **{len(exportable_tickets)}**")
    lines.append(f"- Research-only tickets: **{len(research_tickets)}**")
    if skipped_modules:
        lines.append("- Optional modules skipped: " + ", ".join(skipped_modules))
    lines.append("")
    lines.append("## Market Summary")
    lines.append("")
    lines.append(f"- pct_above_ma50: {market_summary.get('pct_above_ma50')}")
    lines.append(f"- pct_above_ma200: {market_summary.get('pct_above_ma200')}")
    lines.append(f"- avg_pair_corr_20: {market_summary.get('avg_pair_corr_20')}")
    lines.append(f"- vol_trend: {market_summary.get('vol_trend')}")
    lines.append(f"- risk_on_score: {market_summary.get('risk_on_score')}")
    lines.append(f"- risk_off_score: {market_summary.get('risk_off_score')}")
    lines.append("")
    lines.append("## Anomalies (Top)")
    lines.append("")
    if anomalies:
        for item in anomalies[:10]:
            symbol = item.get("symbol", "MARKET")
            metric = item.get("metric", "n/a")
            value = item.get("value", "n/a")
            z = item.get("z", "n/a")
            lines.append(f"- {symbol}: {metric}={value} (z={z})")
    else:
        lines.append("- No high-z anomalies detected.")
    lines.append("")
    lines.append("## Exportable Tickets")
    lines.append("")
    if exportable_tickets:
        for ticket in exportable_tickets:
            lines.append(
                "- "
                f"{ticket['id']} | {ticket.get('entry_family', 'n/a')} | "
                f"score={ticket['priority_score']} | regime={ticket['regime']}"
            )
    else:
        lines.append("- No exportable tickets generated.")
    lines.append("")

    lines.append("## Research-Only Tickets")
    lines.append("")
    if research_tickets:
        for ticket in research_tickets:
            lines.append(
                "- "
                f"{ticket['id']} | {ticket.get('hypothesis_type', 'n/a')} | "
                f"score={ticket['priority_score']} | symbol={ticket.get('observation', {}).get('symbol', 'n/a')}"
            )
    else:
        lines.append("- No research-only tickets generated.")
    lines.append("")
    return "\n".join(lines)


def read_hints(hints_path: Path | None) -> list[dict[str, Any]]:
    """Load hints YAML (optional)."""
    if hints_path is None:
        return []
    payload = yaml.safe_load(hints_path.read_text())
    if payload is None:
        return []
    if isinstance(payload, list):
        return normalize_hints(payload)
    if isinstance(payload, dict):
        raw_hints = payload.get("hints", [])
        if isinstance(raw_hints, list):
            return normalize_hints(raw_hints)
    raise AutoDetectError(f"invalid hints format: {hints_path}")


def generate_llm_hints(
    llm_command: str | None,
    as_of_date: date,
    market_summary: dict[str, Any],
    anomalies: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generate hints via external LLM CLI command.

    Command receives JSON payload on stdin and must print YAML/JSON:
    - list[hint]
    - or {"hints": [...]}
    """
    if not llm_command:
        return []

    payload = {
        "as_of": as_of_date.isoformat(),
        "market_summary": market_summary,
        "anomalies": anomalies[:20],
        "instruction": (
            "Generate concise edge hints with fields: title, observation, preferred_entry_family, "
            "symbols(optional), regime_bias(optional), mechanism_tag(optional)."
        ),
    }

    command_parts = shlex.split(llm_command)
    if not command_parts:
        raise AutoDetectError("--llm-ideas-cmd is empty")

    result = subprocess.run(
        command_parts,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise AutoDetectError(f"LLM ideas command failed: {detail}")

    stdout = result.stdout.strip()
    if not stdout:
        return []

    parsed = yaml.safe_load(stdout)
    if parsed is None:
        return []
    if isinstance(parsed, list):
        return normalize_hints(parsed)
    if isinstance(parsed, dict):
        hints = parsed.get("hints", [])
        if isinstance(hints, list):
            return normalize_hints(hints)
    raise AutoDetectError(
        "LLM ideas command returned invalid format (expected list or {hints: [...]})"
    )


def _require_pandas() -> tuple[Any, Any]:
    """Import pandas/numpy lazily to keep test/runtime environments flexible."""
    try:
        import numpy as np
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - depends on runtime environment
        raise AutoDetectError(
            "pandas and numpy are required for auto detection. "
            "Run with an environment that has them installed."
        ) from exc
    return pd, np


def _load_ohlcv_table(ohlcv_path: Path) -> Any:
    """Load OHLCV table, sniffing parquet/CSV by extension."""
    pd, _ = _require_pandas()
    suffix = ohlcv_path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(ohlcv_path)
    if suffix in {".parquet", ".pq"}:
        try:
            return pd.read_parquet(ohlcv_path)
        except ImportError as exc:  # pragma: no cover - depends on runtime environment
            raise AutoDetectError(
                f"reading parquet requires pyarrow or fastparquet; install one "
                f"(e.g. `uv add pyarrow`) or convert {ohlcv_path.name} to CSV."
            ) from exc
    raise AutoDetectError(
        f"unsupported OHLCV format: {suffix or '(none)'} for {ohlcv_path.name} "
        f"(expected .parquet, .pq, or .csv)"
    )


def compute_features(
    ohlcv_path: Path,
    as_of_date: date | None,
) -> tuple[Any, Any, date]:
    """Load OHLCV (parquet or CSV) and compute per-symbol features."""
    pd, np = _require_pandas()
    df = _load_ohlcv_table(ohlcv_path)
    df.columns = [str(col).lower() for col in df.columns]

    missing = sorted(REQUIRED_OHLCV_COLUMNS - set(df.columns))
    if missing:
        raise AutoDetectError(f"OHLCV file missing columns: {', '.join(missing)}")

    frame = df[["symbol", "timestamp", "open", "high", "low", "close", "volume"]].copy()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame = frame.dropna(subset=["symbol", "timestamp", "open", "high", "low", "close", "volume"])
    frame = frame.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    frame["date"] = frame["timestamp"].dt.date

    available_dates = sorted(frame["date"].dropna().unique())
    if not available_dates:
        raise AutoDetectError("no valid timestamps found in OHLCV")

    target_date = as_of_date or available_dates[-1]
    if target_date not in available_dates:
        prior_dates = [d for d in available_dates if d <= target_date]
        if not prior_dates:
            raise AutoDetectError(f"no OHLCV data at or before as_of={target_date.isoformat()}")
        target_date = prior_dates[-1]

    frame = frame[frame["date"] <= target_date].copy()
    group = frame.groupby("symbol", sort=False)

    frame["prev_close"] = group["close"].shift(1)
    frame["ret_1d"] = frame["close"] / frame["prev_close"] - 1.0

    frame["ma20"] = group["close"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    frame["ma50"] = group["close"].transform(lambda s: s.rolling(50, min_periods=50).mean())
    frame["ma200"] = group["close"].transform(lambda s: s.rolling(200, min_periods=200).mean())

    frame["vol_avg20"] = group["volume"].transform(lambda s: s.rolling(20, min_periods=20).mean())
    frame["rel_volume"] = frame["volume"] / frame["vol_avg20"]

    frame["high20_prev"] = group["high"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=20).max()
    )
    frame["low20_prev"] = group["low"].transform(
        lambda s: s.shift(1).rolling(20, min_periods=20).min()
    )
    frame["close_pos"] = (
        (frame["close"] - frame["low"]) / (frame["high"] - frame["low"]).replace(0, np.nan)
    ).clip(0, 1)
    frame["gap"] = frame["open"] / frame["prev_close"] - 1.0
    frame["rs_120"] = group["close"].transform(lambda s: s / s.shift(120) - 1.0)

    tr1 = frame["high"] - frame["low"]
    tr2 = (frame["high"] - frame["prev_close"]).abs()
    tr3 = (frame["low"] - frame["prev_close"]).abs()
    frame["tr"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    frame["atr14"] = group["tr"].transform(lambda s: s.rolling(14, min_periods=14).mean())
    frame["atr_pct"] = frame["atr14"] / frame["close"]

    for metric in ("ret_1d", "rel_volume", "gap", "atr_pct"):
        rolling_mean = group[metric].transform(lambda s: s.rolling(60, min_periods=30).mean())
        rolling_std = group[metric].transform(lambda s: s.rolling(60, min_periods=30).std(ddof=0))
        frame[f"{metric}_z"] = (frame[metric] - rolling_mean) / rolling_std.replace(0, np.nan)

    frame = frame.replace([np.inf, -np.inf], np.nan)

    latest = frame[frame["date"] == target_date].copy()
    if latest.empty:
        raise AutoDetectError(f"no rows found for target date {target_date.isoformat()}")

    return frame, latest, target_date


def compute_regime(
    full_frame: Any,
    latest: Any,
    target_date: date,
    min_price: float,
    min_avg_volume: float,
) -> tuple[str, dict[str, Any], Any]:
    """Compute market regime label and summary metrics."""
    _, np = _require_pandas()

    tradable = latest[
        (latest["close"] >= min_price)
        & (latest["vol_avg20"] >= min_avg_volume)
        & latest["ma50"].notna()
        & latest["ma200"].notna()
    ].copy()

    if tradable.empty:
        raise AutoDetectError("no tradable symbols remain after min price/volume filters")

    tradable["rs_rank_pct"] = tradable["rs_120"].rank(pct=True, method="average")

    pct_above_ma50 = float((tradable["close"] > tradable["ma50"]).mean())
    pct_above_ma200 = float((tradable["close"] > tradable["ma200"]).mean())

    dates = sorted(full_frame["date"].dropna().unique())
    target_index = dates.index(target_date)
    last_20_dates = dates[max(0, target_index - 19) : target_index + 1]
    last_60_dates = dates[max(0, target_index - 59) : target_index + 1]

    recent = full_frame[full_frame["date"].isin(last_20_dates)][["date", "symbol", "ret_1d"]].copy()
    pivot = recent.pivot(index="date", columns="symbol", values="ret_1d")
    avg_pair_corr = float("nan")
    if pivot.shape[1] >= 2:
        corr = pivot.corr(min_periods=5)
        if corr.shape[0] >= 2:
            mask = ~np.eye(corr.shape[0], dtype=bool)
            vals = corr.values[mask]
            if vals.size > 0:
                avg_pair_corr = float(np.nanmean(vals))

    spy_rows = full_frame[full_frame["symbol"] == "SPY"].copy()
    spy_today = spy_rows[spy_rows["date"] == target_date].tail(1)
    spy_above_ma200 = bool(pct_above_ma200 >= 0.5)
    spy_ret_1d = float("nan")
    rv20 = float("nan")
    rv60 = float("nan")

    if not spy_today.empty:
        spy_close = float(spy_today["close"].iloc[0])
        spy_ma200 = (
            float(spy_today["ma200"].iloc[0])
            if not math.isnan(spy_today["ma200"].iloc[0])
            else float("nan")
        )
        spy_above_ma200 = (
            bool(spy_close > spy_ma200) if not math.isnan(spy_ma200) else spy_above_ma200
        )
        spy_ret_1d = (
            float(spy_today["ret_1d"].iloc[0])
            if not math.isnan(spy_today["ret_1d"].iloc[0])
            else float("nan")
        )

        spy_ret_20 = spy_rows[spy_rows["date"].isin(last_20_dates)]["ret_1d"].dropna()
        spy_ret_60 = spy_rows[spy_rows["date"].isin(last_60_dates)]["ret_1d"].dropna()
        if len(spy_ret_20) >= 10:
            rv20 = float(spy_ret_20.std(ddof=0) * math.sqrt(252))
        if len(spy_ret_60) >= 20:
            rv60 = float(spy_ret_60.std(ddof=0) * math.sqrt(252))

    if math.isnan(rv20) or math.isnan(rv60) or rv60 == 0:
        market_daily = (
            full_frame[full_frame["date"].isin(last_60_dates)]
            .groupby("date")["ret_1d"]
            .mean()
            .dropna()
        )
        if len(market_daily) >= 20:
            rv20 = float(market_daily.tail(20).std(ddof=0) * math.sqrt(252))
            rv60 = float(market_daily.std(ddof=0) * math.sqrt(252))

    vol_trend = float("nan")
    if not math.isnan(rv20) and not math.isnan(rv60) and rv60 > 0:
        vol_trend = float(rv20 / rv60)

    corr_component = 0.5 if math.isnan(avg_pair_corr) else avg_pair_corr
    vol_component = 1.0 if math.isnan(vol_trend) else vol_trend

    risk_on_score = (
        (25.0 if spy_above_ma200 else 5.0)
        + clamp((pct_above_ma50 - 0.35) / 0.45, 0.0, 1.0) * 35.0
        + clamp((0.8 - corr_component) / 0.6, 0.0, 1.0) * 20.0
        + clamp((1.4 - vol_component) / 0.8, 0.0, 1.0) * 20.0
    )
    risk_off_score = (
        (20.0 if not spy_above_ma200 else 5.0)
        + clamp((corr_component - 0.35) / 0.45, 0.0, 1.0) * 30.0
        + clamp((vol_component - 0.95) / 0.8, 0.0, 1.0) * 30.0
        + clamp((0.55 - pct_above_ma50) / 0.45, 0.0, 1.0) * 20.0
    )

    if risk_off_score >= 65 and risk_off_score - risk_on_score >= 5:
        regime_label = "RiskOff"
    elif risk_on_score >= 65 and risk_on_score >= risk_off_score:
        regime_label = "RiskOn"
    else:
        regime_label = "Neutral"

    summary = {
        "as_of": target_date.isoformat(),
        "universe_count": int(tradable["symbol"].nunique()),
        "pct_above_ma50": round(pct_above_ma50, 4),
        "pct_above_ma200": round(pct_above_ma200, 4),
        "avg_pair_corr_20": None if math.isnan(avg_pair_corr) else round(avg_pair_corr, 4),
        "rv20": None if math.isnan(rv20) else round(rv20, 4),
        "rv60": None if math.isnan(rv60) else round(rv60, 4),
        "vol_trend": None if math.isnan(vol_trend) else round(vol_trend, 4),
        "spy_above_ma200": bool(spy_above_ma200),
        "spy_return_1d": None if math.isnan(spy_ret_1d) else round(spy_ret_1d, 4),
        "risk_on_score": round(risk_on_score, 2),
        "risk_off_score": round(risk_off_score, 2),
        "regime_label": regime_label,
    }

    return regime_label, summary, tradable


def detect_anomalies(
    tradable: Any,
    market_summary: dict[str, Any],
    top_k: int,
) -> list[dict[str, Any]]:
    """Detect market/stock anomalies from z-scored metrics."""
    _, np = _require_pandas()
    anomalies: list[dict[str, Any]] = []

    metric_map = {
        "ret_1d_z": "ret_1d",
        "rel_volume_z": "rel_volume",
        "gap_z": "gap",
        "atr_pct_z": "atr_pct",
    }
    threshold = 2.0

    for _, row in tradable.iterrows():
        symbol = str(row["symbol"])
        for z_col, value_col in metric_map.items():
            z_val = row.get(z_col)
            if z_val is None or (isinstance(z_val, float) and math.isnan(z_val)):
                continue
            abs_z = abs(float(z_val))
            if abs_z < threshold:
                continue
            value = row.get(value_col)
            anomalies.append(
                {
                    "scope": "stock",
                    "symbol": symbol,
                    "metric": value_col,
                    "value": round(float(value), 5)
                    if value is not None and not math.isnan(float(value))
                    else None,
                    "z": round(float(z_val), 3),
                    "abs_z": round(abs_z, 3),
                    "comment": f"{value_col} z-score exceeded {threshold}",
                }
            )

    anomalies.sort(key=lambda item: item.get("abs_z", 0.0), reverse=True)

    avg_pair_corr = market_summary.get("avg_pair_corr_20")
    vol_trend = market_summary.get("vol_trend")
    pct_above_ma50 = market_summary.get("pct_above_ma50")
    spy_ret = market_summary.get("spy_return_1d")

    if (
        avg_pair_corr is not None
        and vol_trend is not None
        and pct_above_ma50 is not None
        and avg_pair_corr >= 0.65
        and vol_trend >= 1.15
        and pct_above_ma50 <= 0.40
    ):
        anomalies.insert(
            0,
            {
                "scope": "market",
                "symbol": "MARKET",
                "metric": "riskoff_combo",
                "value": round(float(vol_trend), 4),
                "z": None,
                "abs_z": 99.0,
                "comment": "High correlation + rising vol + weak breadth (RiskOff combo)",
            },
        )

    if (
        pct_above_ma50 is not None
        and spy_ret is not None
        and pct_above_ma50 <= 0.35
        and spy_ret > 0.003
    ):
        anomalies.insert(
            0,
            {
                "scope": "market",
                "symbol": "MARKET",
                "metric": "breadth_divergence",
                "value": round(float(pct_above_ma50), 4),
                "z": None,
                "abs_z": 95.0,
                "comment": "Index up while breadth is weak (possible divergence)",
            },
        )

    return anomalies[:top_k]


def scan_candidates(
    tradable: Any,
    regime_label: str,
    hints: list[dict[str, Any]],
    top_n: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Run breakout/gap scanners and build ranked watchlist + ticket seeds."""
    _, np = _require_pandas()

    breakout_mask = (
        (tradable["close"] > tradable["ma50"])
        & (tradable["ma50"] > tradable["ma200"])
        & (tradable["close"] > tradable["high20_prev"])
        & (tradable["rel_volume"] >= 1.5)
        & (tradable["close_pos"] >= 0.55)
        & (tradable["rs_rank_pct"] >= 0.70)
    )

    gap_mask = (
        (tradable["gap"] >= 0.04)
        & (tradable["rel_volume"] >= 2.0)
        & (tradable["close_pos"] >= 0.50)
        & (tradable["close"] > tradable["ma50"])
    )

    watchlist: list[dict[str, Any]] = []

    for family, mask, condition_text in (
        (
            "pivot_breakout",
            breakout_mask,
            ["close > high20_prev", "rel_volume >= 1.5", "close > ma50 > ma200"],
        ),
        (
            "gap_up_continuation",
            gap_mask,
            ["gap >= 4%", "rel_volume >= 2.0", "close_pos >= 0.5", "close > ma50"],
        ),
    ):
        subset = tradable[mask].copy()
        if subset.empty:
            continue

        for _, row in subset.iterrows():
            symbol = str(row["symbol"]).upper()
            row_dict = row.to_dict()
            boost, matched_hints = hint_match_boost(symbol, family, hints)

            if family == "pivot_breakout":
                score = score_breakout_candidate(
                    row_dict, regime_label=regime_label, hint_boost=boost
                )
                hypothesis_type = "breakout"
            else:
                score = score_gap_candidate(row_dict, regime_label=regime_label, hint_boost=boost)
                hypothesis_type = "earnings_drift"

            record = {
                "symbol": symbol,
                "entry_family": family,
                "hypothesis_type": hypothesis_type,
                "priority_score": score,
                "close": float(row.get("close", np.nan)),
                "gap": float(row.get("gap", np.nan)),
                "rel_volume": float(row.get("rel_volume", np.nan)),
                "close_pos": float(row.get("close_pos", np.nan)),
                "rs_rank_pct": float(row.get("rs_rank_pct", np.nan)),
                "atr_pct": float(row.get("atr_pct", np.nan)),
                "high20_prev": float(row.get("high20_prev", np.nan)),
                "ma50": float(row.get("ma50", np.nan)),
                "ma200": float(row.get("ma200", np.nan)),
                "conditions": condition_text,
                "trend_filter": ["price > sma_200", "price > sma_50", "sma_50 > sma_200"],
                "mechanism_tag": DEFAULT_MECHANISM_TAG[family],
                "matched_hints": matched_hints,
            }
            watchlist.append(record)

    watchlist.sort(key=lambda item: float(item["priority_score"]), reverse=True)
    tickets = watchlist[: max(top_n, 0)]
    return watchlist, tickets


def scan_reversal_candidates(
    tradable: Any,
    regime_label: str,
    hints: list[dict[str, Any]],
    top_n: int = 4,
) -> list[dict[str, Any]]:
    """Detect panic-reversal research candidates."""
    _, np = _require_pandas()

    mask = (
        (tradable["ret_1d"] <= -0.07)
        & (tradable["rel_volume"] >= 1.8)
        & (tradable["close"] > tradable["ma200"] * 0.85)
    )
    subset = tradable[mask].copy()
    if subset.empty:
        return []

    candidates: list[dict[str, Any]] = []
    for _, row in subset.iterrows():
        symbol = str(row["symbol"]).upper()
        row_dict = row.to_dict()
        boost, matched_hints = hint_match_boost(symbol, "panic_reversal", hints)
        score = score_reversal_candidate(
            row_dict, regime_label=regime_label, hint_boost=boost * 0.6
        )
        candidates.append(
            {
                "symbol": symbol,
                "entry_family": "panic_reversal",
                "hypothesis_type": "panic_reversal",
                "priority_score": score,
                "holding_horizon": "5D",
                "ret_1d": float(row.get("ret_1d", np.nan)),
                "rel_volume": float(row.get("rel_volume", np.nan)),
                "atr_pct": float(row.get("atr_pct", np.nan)),
                "close": float(row.get("close", np.nan)),
                "ma200": float(row.get("ma200", np.nan)),
                "gap": float(row.get("gap", np.nan)),
                "close_pos": float(row.get("close_pos", np.nan)),
                "rs_rank_pct": float(row.get("rs_rank_pct", np.nan)),
                "mechanism_tag": "behavior",
                "matched_hints": matched_hints,
                "conditions": ["ret_1d <= -0.07", "rel_volume >= 1.8", "close > 0.85 * ma200"],
                "trend_filter": ["avoid fresh breakdown regimes unless reversal setup confirms"],
                "rationale": [
                    "Extreme down move with participation often leads to short-horizon snapback.",
                    "Use only as tactical candidate with strict validation.",
                ],
                "description": "Panic-style selloff candidate with potential mean reversion.",
                "hypothesis": (
                    "if extreme downside move occurs with volume shock but long-term trend is not broken, "
                    "then 3-10 day rebound probability increases"
                ),
            }
        )

    candidates.sort(key=lambda item: float(item["priority_score"]), reverse=True)
    return candidates[: max(top_n, 0)]


def scan_regime_shift_candidate(
    full_frame: Any,
    target_date: date,
    market_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    """Detect early regime shift candidate from breadth/vol trend inflection."""
    _, np = _require_pandas()

    valid = full_frame[full_frame["ma50"].notna() & full_frame["ma200"].notna()].copy()
    if valid.empty:
        return []

    daily = (
        valid.groupby("date")
        .agg(
            pct_above_ma50=("close", lambda s: float((s > valid.loc[s.index, "ma50"]).mean())),
            pct_above_ma200=("close", lambda s: float((s > valid.loc[s.index, "ma200"]).mean())),
            avg_ret=("ret_1d", "mean"),
        )
        .dropna()
    )
    if target_date not in daily.index or len(daily) < 12:
        return []

    tail = daily.loc[:target_date].tail(8)
    if len(tail) < 6:
        return []

    breadth_delta = float(tail["pct_above_ma50"].iloc[-1] - tail["pct_above_ma50"].iloc[0])
    ret_5d = float(tail["avg_ret"].tail(5).sum())
    vol_trend = market_summary.get("vol_trend")
    avg_pair_corr = market_summary.get("avg_pair_corr_20")

    if vol_trend is None or avg_pair_corr is None:
        return []

    score = 0.0
    description = ""
    direction = ""
    if breadth_delta >= 0.08 and ret_5d > 0 and float(vol_trend) <= 1.05:
        direction = "risk_on_transition"
        score = 55.0 + clamp((breadth_delta - 0.08) / 0.12, 0.0, 1.0) * 25.0
        description = "Breadth expanding with calmer volatility, possible early RiskOn transition."
    elif breadth_delta <= -0.08 and ret_5d < 0 and float(vol_trend) >= 1.10:
        direction = "risk_off_transition"
        score = 55.0 + clamp((abs(breadth_delta) - 0.08) / 0.12, 0.0, 1.0) * 25.0
        description = (
            "Breadth deterioration with rising volatility, possible early RiskOff transition."
        )
    else:
        return []

    candidate = {
        "symbol": "MARKET_BASKET",
        "entry_family": None,
        "hypothesis_type": "regime_shift",
        "priority_score": round(clamp(score), 2),
        "holding_horizon": "60D",
        "mechanism_tag": "structure",
        "description": description,
        "conditions": [
            f"breadth_delta_7d={round(breadth_delta, 4)}",
            f"ret_5d={round(ret_5d, 4)}",
            f"vol_trend={vol_trend}",
            f"avg_pair_corr_20={avg_pair_corr}",
        ],
        "trend_filter": [direction],
        "rationale": [
            "Regime changes often begin with breadth/volatility structure shifts before broad narratives catch up.",
        ],
        "hypothesis": (
            "if breadth and volatility structure continue in the detected direction, "
            "then relative performance of aligned factor baskets should persist"
        ),
    }
    return [candidate]


def scan_correlation_chain_candidates(
    full_frame: Any,
    tradable: Any,
    target_date: date,
    top_n: int = 4,
) -> list[dict[str, Any]]:
    """Detect leader-follower chain candidates from lagged co-movement."""
    _, np = _require_pandas()

    recent_dates = sorted(full_frame["date"].dropna().unique())
    if target_date not in recent_dates:
        return []
    target_index = recent_dates.index(target_date)
    lookback_dates = recent_dates[max(0, target_index - 89) : target_index + 1]

    recent = full_frame[full_frame["date"].isin(lookback_dates)].copy()
    if recent.empty:
        return []

    recent = recent.assign(dollar_volume=recent["close"] * recent["volume"])
    dv = recent.groupby("symbol")["dollar_volume"].apply(lambda s: float(s.tail(20).mean()))
    dv = dv.sort_values(ascending=False)
    top_symbols = dv.head(120).index.tolist()
    recent = recent[recent["symbol"].isin(top_symbols)]

    pivot = recent.pivot(index="date", columns="symbol", values="ret_1d")
    if pivot.shape[1] < 8:
        return []

    today = tradable[["symbol", "ret_1d", "close", "ma50", "rel_volume"]].copy()
    today = today.set_index("symbol")
    leaders = today[today["ret_1d"].abs() >= 0.045].sort_values(
        "ret_1d", key=lambda s: s.abs(), ascending=False
    )
    if leaders.empty:
        return []

    candidates: list[dict[str, Any]] = []
    for leader_symbol, leader_row in leaders.head(6).iterrows():
        if leader_symbol not in pivot.columns:
            continue
        leader_shift = pivot[leader_symbol].shift(1)
        corr = pivot.corrwith(leader_shift).dropna()
        if corr.empty:
            continue

        followers = (
            corr[(corr.index != leader_symbol) & (corr >= 0.25)]
            .sort_values(ascending=False)
            .head(5)
        )
        for follower_symbol, lag_corr in followers.items():
            if follower_symbol not in today.index:
                continue
            follower_today = today.loc[follower_symbol]
            if abs(float(follower_today["ret_1d"])) >= 0.015:
                continue

            score = (
                clamp(abs(float(leader_row["ret_1d"])) / 0.12, 0.0, 1.0) * 40.0
                + clamp(float(lag_corr) / 0.60, 0.0, 1.0) * 35.0
                + clamp(float(follower_today["rel_volume"]) / 3.0, 0.0, 1.0) * 15.0
                + (10.0 if float(follower_today["close"]) > float(follower_today["ma50"]) else 4.0)
            )
            candidates.append(
                {
                    "symbol": str(follower_symbol),
                    "entry_family": None,
                    "hypothesis_type": "sector_x_stock",
                    "priority_score": round(clamp(score), 2),
                    "holding_horizon": "20D",
                    "mechanism_tag": "behavior",
                    "description": (
                        f"Potential leader-follower propagation from {leader_symbol} to {follower_symbol}."
                    ),
                    "conditions": [
                        f"leader={leader_symbol}",
                        f"leader_ret_1d={round(float(leader_row['ret_1d']), 4)}",
                        f"lag_corr={round(float(lag_corr), 4)}",
                        f"follower_ret_1d={round(float(follower_today['ret_1d']), 4)}",
                    ],
                    "trend_filter": ["follower_ret_1d_abs < 1.5%"],
                    "rationale": [
                        "Cross-symbol propagation can occur when leadership shocks diffuse across related names.",
                    ],
                    "hypothesis": (
                        "if leader shock persists and lag-correlation structure remains stable, "
                        "then follower move may emerge in subsequent sessions"
                    ),
                }
            )

    deduped: dict[str, dict[str, Any]] = {}
    for candidate in sorted(candidates, key=lambda item: item["priority_score"], reverse=True):
        symbol = str(candidate["symbol"])
        if symbol not in deduped:
            deduped[symbol] = candidate
    return list(deduped.values())[: max(top_n, 0)]


def scan_calendar_anomaly_candidates(
    full_frame: Any,
    tradable: Any,
    target_date: date,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """Detect month-of-year seasonal anomaly candidates."""
    pd, _ = _require_pandas()

    season = full_frame[["symbol", "timestamp", "close"]].copy()
    season["month"] = season["timestamp"].dt.to_period("M")
    month_end = season.groupby(["symbol", "month"], as_index=False)["close"].last()
    month_end["monthly_ret"] = month_end.groupby("symbol")["close"].pct_change()
    month_end["month_num"] = month_end["month"].dt.month

    target_month = target_date.month
    stats = (
        month_end[month_end["month_num"] == target_month]
        .groupby("symbol")
        .agg(
            mean_ret=("monthly_ret", "mean"),
            sample_count=("monthly_ret", "count"),
            win_rate=("monthly_ret", lambda s: float((s > 0).mean())),
        )
        .dropna()
    )

    if stats.empty:
        return []

    stats = stats[
        (stats["sample_count"] >= 6) & (stats["mean_ret"] >= 0.025) & (stats["win_rate"] >= 0.6)
    ]
    if stats.empty:
        return []

    today = tradable.set_index("symbol")
    candidates: list[dict[str, Any]] = []
    for symbol, row in stats.sort_values("mean_ret", ascending=False).head(20).iterrows():
        if symbol not in today.index:
            continue
        today_row = today.loc[symbol]
        rs_rank = float(today_row.get("rs_rank_pct", 0.0) or 0.0)
        rel_volume = float(today_row.get("rel_volume", 0.0) or 0.0)
        score = (
            clamp(float(row["mean_ret"]) / 0.10, 0.0, 1.0) * 45.0
            + clamp(float(row["win_rate"]), 0.0, 1.0) * 30.0
            + clamp(rs_rank, 0.0, 1.0) * 15.0
            + clamp(rel_volume / 2.5, 0.0, 1.0) * 10.0
        )
        candidates.append(
            {
                "symbol": str(symbol),
                "entry_family": None,
                "hypothesis_type": "calendar_anomaly",
                "priority_score": round(clamp(score), 2),
                "holding_horizon": "20D",
                "mechanism_tag": "risk_premium",
                "description": f"Seasonal strength candidate for month={target_month}.",
                "conditions": [
                    f"month={target_month}",
                    f"mean_monthly_ret={round(float(row['mean_ret']), 4)}",
                    f"win_rate={round(float(row['win_rate']), 4)}",
                    f"sample_count={int(row['sample_count'])}",
                ],
                "trend_filter": ["prefer symbols with positive medium-term RS"],
                "rationale": [
                    "Recurring seasonal participation can create repeatable calendar edges in specific symbols.",
                ],
                "hypothesis": (
                    "if historical month-of-year strength repeats and current trend quality is acceptable, "
                    "then short-term relative performance may improve"
                ),
            }
        )

    return sorted(candidates, key=lambda item: item["priority_score"], reverse=True)[
        : max(top_n, 0)
    ]


def read_optional_table(path: Path | None) -> Any | None:
    """Read optional CSV/Parquet file with pandas."""
    if path is None:
        return None
    if not path.exists():
        raise AutoDetectError(f"optional data file not found: {path}")
    pd, _ = _require_pandas()
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise AutoDetectError(f"unsupported optional data format: {path}")


def scan_news_reaction_candidates(
    news_table: Any | None,
    target_date: date,
    tradable: Any | None = None,
    top_n: int = 4,
) -> tuple[list[dict[str, Any]], bool]:
    """Detect candidates from optional news-reaction table."""
    if news_table is None:
        return [], False

    pd, _ = _require_pandas()
    frame = news_table.copy()
    frame.columns = [str(col).lower() for col in frame.columns]
    required = {"symbol", "timestamp", "reaction_1d"}
    if not required.issubset(frame.columns):
        raise AutoDetectError("news reactions file must include symbol,timestamp,reaction_1d")

    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame["date"] = frame["timestamp"].dt.date
    day = frame[frame["date"] == target_date].copy()
    day = day.dropna(subset=["reaction_1d"])
    if day.empty:
        return [], True

    # Join with tradable to get rel_volume, close_pos, atr_pct
    if tradable is not None:
        tradable_cols = tradable[["symbol"]].copy()
        for col in ("rel_volume", "close_pos", "atr_pct"):
            if col in tradable.columns:
                tradable_cols[col] = tradable[col]
        day = day.merge(tradable_cols, on="symbol", how="left")

    day["abs_reaction"] = day["reaction_1d"].abs()
    out: list[dict[str, Any]] = []
    for _, row in day.sort_values("abs_reaction", ascending=False).head(max(top_n, 0)).iterrows():
        reaction = float(row["reaction_1d"])
        score = clamp(abs(reaction) / 0.12, 0.0, 1.0) * 70.0 + 20.0
        out.append(
            {
                "symbol": str(row["symbol"]),
                "entry_family": "news_reaction",
                "hypothesis_type": "news_reaction",
                "priority_score": round(clamp(score), 2),
                "holding_horizon": "10D",
                "mechanism_tag": "behavior",
                "description": "News reaction candidate from external event table.",
                "conditions": [
                    "abs_reaction_1d >= 0.06",
                    "rel_volume >= 2.0",
                    "close_pos >= 0.4",
                ],
                "trend_filter": ["validate_follow_through_d2", "volume_confirmation_present"],
                "rationale": [
                    "Event-driven over/under-reaction can form short-horizon continuation or mean-reversion edges.",
                ],
                "hypothesis": (
                    "if news reaction magnitude is extreme relative to baseline, "
                    "then post-event drift or reversal edge may emerge"
                ),
                "reaction_1d": reaction,
            }
        )
    return out, True


def scan_futures_trigger_candidates(
    futures_table: Any | None,
    futures_map: dict[str, list[str]] | None,
    target_date: date,
    top_n: int = 6,
) -> tuple[list[dict[str, Any]], bool]:
    """Detect candidates from optional futures trigger table and mapping."""
    if futures_table is None:
        return [], False

    pd, _ = _require_pandas()
    frame = futures_table.copy()
    frame.columns = [str(col).lower() for col in frame.columns]
    required = {"symbol", "timestamp", "close"}
    if not required.issubset(frame.columns):
        raise AutoDetectError("futures file must include symbol,timestamp,close")

    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
    frame["date"] = frame["timestamp"].dt.date
    frame = frame.sort_values(["symbol", "timestamp"])
    frame["ret_1d"] = frame.groupby("symbol")["close"].pct_change()
    frame["ret_z"] = frame.groupby("symbol")["ret_1d"].transform(
        lambda s: (
            (s - s.rolling(60, min_periods=30).mean()) / s.rolling(60, min_periods=30).std(ddof=0)
        )
    )

    day = frame[frame["date"] == target_date].copy()
    if day.empty:
        return [], True

    mapping = futures_map or {}
    candidates: list[dict[str, Any]] = []
    shocks = day[day["ret_z"].abs() >= 2.0].sort_values(
        "ret_z", key=lambda s: s.abs(), ascending=False
    )
    for _, shock in shocks.iterrows():
        fut_symbol = str(shock["symbol"])
        related = mapping.get(fut_symbol, [])
        if not related:
            continue
        shock_z = float(shock["ret_z"])
        for stock_symbol in related:
            score = clamp(abs(shock_z) / 4.0, 0.0, 1.0) * 60.0 + 20.0
            candidates.append(
                {
                    "symbol": str(stock_symbol).upper(),
                    "entry_family": None,
                    "hypothesis_type": "futures_trigger",
                    "priority_score": round(clamp(score), 2),
                    "holding_horizon": "20D",
                    "mechanism_tag": "structure",
                    "description": f"Futures trigger candidate from {fut_symbol} shock.",
                    "conditions": [f"future={fut_symbol}", f"future_ret_z={round(shock_z, 3)}"],
                    "trend_filter": ["validate cross-asset sensitivity before deployment"],
                    "rationale": [
                        "Cross-asset shocks in futures can propagate to related equities through flow and hedging.",
                    ],
                    "hypothesis": (
                        "if futures shock persists and mapping remains stable, "
                        "then related equities may show directional response"
                    ),
                }
            )

    candidates.sort(key=lambda item: item["priority_score"], reverse=True)
    return candidates[: max(top_n, 0)], True


def load_futures_map(path: Path | None) -> dict[str, list[str]] | None:
    """Load optional futures-to-symbol mapping from YAML."""
    if path is None:
        return None
    if not path.exists():
        raise AutoDetectError(f"futures map file not found: {path}")

    payload = yaml.safe_load(path.read_text())
    if payload is None:
        return {}
    if isinstance(payload, dict) and "mappings" in payload:
        mapping_payload = payload["mappings"]
    else:
        mapping_payload = payload

    if not isinstance(mapping_payload, dict):
        raise AutoDetectError("futures map must be a mapping or {mappings: ...}")

    mapping: dict[str, list[str]] = {}
    for key, value in mapping_payload.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, list):
            symbols = [
                str(item).upper() for item in value if isinstance(item, str) and item.strip()
            ]
            if symbols:
                mapping[key.upper()] = symbols
    return mapping


def write_outputs(
    output_dir: Path,
    as_of_date: date,
    regime_label: str,
    market_summary: dict[str, Any],
    anomalies: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    exportable_tickets: list[dict[str, Any]],
    research_tickets: list[dict[str, Any]],
    skipped_modules: list[str],
) -> tuple[list[Path], list[Path], Path]:
    """Persist detection outputs to disk."""
    pd, _ = _require_pandas()

    output_dir.mkdir(parents=True, exist_ok=True)
    tickets_dir = output_dir / "tickets"
    exportable_dir = tickets_dir / "exportable"
    research_dir = tickets_dir / "research_only"
    exportable_dir.mkdir(parents=True, exist_ok=True)
    research_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "market_summary.json").write_text(json.dumps(market_summary, indent=2) + "\n")
    (output_dir / "anomalies.json").write_text(json.dumps(anomalies, indent=2) + "\n")

    if watchlist:
        watchlist_df = pd.DataFrame(watchlist)
        watchlist_df.to_csv(output_dir / "watchlist.csv", index=False)
    else:
        pd.DataFrame(
            columns=["symbol", "entry_family", "hypothesis_type", "priority_score"]
        ).to_csv(output_dir / "watchlist.csv", index=False)

    exportable_paths: list[Path] = []
    research_paths: list[Path] = []

    for idx, ticket_seed in enumerate(exportable_tickets, start=1):
        payload = build_ticket_payload(
            candidate=ticket_seed,
            as_of_date=as_of_date,
            regime_label=regime_label,
            rank=idx,
            market_summary=market_summary,
        )
        ticket_path = exportable_dir / f"{payload['id']}.yaml"
        ticket_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False))
        exportable_paths.append(ticket_path)

    for idx, ticket_seed in enumerate(research_tickets, start=1):
        payload = build_ticket_payload(
            candidate=ticket_seed,
            as_of_date=as_of_date,
            regime_label=regime_label,
            rank=idx,
            market_summary=market_summary,
        )
        ticket_path = research_dir / f"{payload['id']}.yaml"
        ticket_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False))
        research_paths.append(ticket_path)

    report_markdown = render_daily_report(
        as_of_date=as_of_date,
        regime_label=regime_label,
        market_summary=market_summary,
        anomalies=anomalies,
        exportable_tickets=[yaml.safe_load(path.read_text()) for path in exportable_paths],
        research_tickets=[yaml.safe_load(path.read_text()) for path in research_paths],
        watchlist_count=len(watchlist),
        skipped_modules=skipped_modules,
    )
    report_path = output_dir / "daily_report.md"
    report_path.write_text(report_markdown)

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "as_of": as_of_date.isoformat(),
        "regime": regime_label,
        "watchlist_count": len(watchlist),
        "exportable_ticket_count": len(exportable_paths),
        "research_ticket_count": len(research_paths),
        "skipped_modules": skipped_modules,
        "output_dir": str(output_dir),
    }
    (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return exportable_paths, research_paths, report_path


def export_tickets(
    ticket_paths: list[Path],
    strategies_dir: Path,
    force_export: bool,
    pipeline_root: Path | None,
    pipeline_stage: str,
) -> tuple[list[Path], dict[str, list[str]]]:
    """Export tickets to strategy artifacts and optionally validate in pipeline context."""
    from export_candidate import export_candidate

    exported: list[Path] = []
    validation_errors: dict[str, list[str]] = {}

    for ticket_path in ticket_paths:
        spec, _, candidate_dir = export_candidate(
            ticket_path=ticket_path,
            strategies_dir=strategies_dir,
            force=force_export,
        )
        strategy_path = candidate_dir / "strategy.yaml"
        exported.append(strategy_path)

        if pipeline_root is not None:
            from validate_candidate import validate_with_pipeline_schema

            errors = validate_with_pipeline_schema(
                strategy_path=strategy_path,
                pipeline_root=pipeline_root,
                stage=pipeline_stage,
            )
            if errors:
                validation_errors[spec["id"]] = errors

    return exported, validation_errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-detect edge candidates from EOD OHLCV and generate research tickets.",
    )
    parser.add_argument("--ohlcv", required=True, help="Path to OHLCV parquet")
    parser.add_argument(
        "--output-dir",
        default="reports/edge_candidate_auto",
        help="Output directory for reports/tickets (default: reports/edge_candidate_auto)",
    )
    parser.add_argument(
        "--as-of", default=None, help="Target date YYYY-MM-DD (default: latest date)"
    )
    parser.add_argument("--top-n", type=int, default=10, help="Number of top tickets to generate")
    parser.add_argument("--anomaly-top-k", type=int, default=10, help="Number of anomalies to keep")
    parser.add_argument("--min-price", type=float, default=5.0, help="Minimum close price filter")
    parser.add_argument(
        "--min-avg-volume",
        type=float,
        default=1_000_000.0,
        help="Minimum 20-day average volume filter",
    )
    parser.add_argument("--hints", default=None, help="Optional hints YAML path")
    parser.add_argument(
        "--llm-ideas-cmd",
        default=None,
        help=(
            "Optional external command to generate hints from market summary/anomalies. "
            "Command receives JSON on stdin and returns YAML/JSON hints."
        ),
    )
    parser.add_argument(
        "--news-reactions",
        default=None,
        help="Optional CSV/Parquet with symbol,timestamp,reaction_1d for event-reaction candidates",
    )
    parser.add_argument(
        "--futures-ohlcv",
        default=None,
        help="Optional CSV/Parquet with symbol,timestamp,close for futures-trigger candidates",
    )
    parser.add_argument(
        "--futures-map",
        default=None,
        help="Optional YAML map from futures symbol to related equities",
    )
    parser.add_argument(
        "--top-research-n",
        type=int,
        default=8,
        help="Maximum research-only tickets to keep",
    )
    parser.add_argument(
        "--export-strategies-dir",
        default=None,
        help="Optional strategies output directory for export_candidate integration",
    )
    parser.add_argument(
        "--force-export", action="store_true", help="Overwrite exported strategy artifacts"
    )
    parser.add_argument(
        "--pipeline-root",
        default=None,
        help="Optional trade-strategy-pipeline root for post-export validation",
    )
    parser.add_argument(
        "--pipeline-stage",
        default="phase1",
        choices=["phase1", "phase1_statistical", "phase2"],
        help="Validation stage when --pipeline-root is provided",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ohlcv_path = Path(args.ohlcv).resolve()
    output_dir = Path(args.output_dir).resolve()
    hints_path = Path(args.hints).resolve() if args.hints else None
    news_path = Path(args.news_reactions).resolve() if args.news_reactions else None
    futures_path = Path(args.futures_ohlcv).resolve() if args.futures_ohlcv else None
    futures_map_path = Path(args.futures_map).resolve() if args.futures_map else None
    as_of_date = parse_as_of_date(args.as_of)

    if not ohlcv_path.exists():
        print(f"[ERROR] OHLCV file not found: {ohlcv_path}")
        return 1
    if hints_path is not None and not hints_path.exists():
        print(f"[ERROR] hints file not found: {hints_path}")
        return 1
    if news_path is not None and not news_path.exists():
        print(f"[ERROR] news reactions file not found: {news_path}")
        return 1
    if futures_path is not None and not futures_path.exists():
        print(f"[ERROR] futures OHLCV file not found: {futures_path}")
        return 1
    if futures_map_path is not None and not futures_map_path.exists():
        print(f"[ERROR] futures map file not found: {futures_map_path}")
        return 1

    try:
        base_hints = read_hints(hints_path)
        full_frame, latest, resolved_date = compute_features(
            ohlcv_path=ohlcv_path, as_of_date=as_of_date
        )
        regime_label, market_summary, tradable = compute_regime(
            full_frame=full_frame,
            latest=latest,
            target_date=resolved_date,
            min_price=args.min_price,
            min_avg_volume=args.min_avg_volume,
        )
        anomalies = detect_anomalies(
            tradable=tradable,
            market_summary=market_summary,
            top_k=max(args.anomaly_top_k, 0),
        )

        llm_hints = generate_llm_hints(
            llm_command=args.llm_ideas_cmd,
            as_of_date=resolved_date,
            market_summary=market_summary,
            anomalies=anomalies,
        )
        all_hints = base_hints + llm_hints

        watchlist, exportable_ticket_seeds = scan_candidates(
            tradable=tradable,
            regime_label=regime_label,
            hints=all_hints,
            top_n=max(args.top_n, 0),
        )

        skipped_modules: list[str] = []
        research_ticket_seeds: list[dict[str, Any]] = []

        exportable_ticket_seeds.extend(
            scan_reversal_candidates(
                tradable=tradable,
                regime_label=regime_label,
                hints=all_hints,
                top_n=max(args.top_research_n, 0),
            )
        )
        research_ticket_seeds.extend(
            scan_regime_shift_candidate(
                full_frame=full_frame,
                target_date=resolved_date,
                market_summary=market_summary,
            )
        )
        research_ticket_seeds.extend(
            scan_correlation_chain_candidates(
                full_frame=full_frame,
                tradable=tradable,
                target_date=resolved_date,
                top_n=max(args.top_research_n, 0),
            )
        )
        research_ticket_seeds.extend(
            scan_calendar_anomaly_candidates(
                full_frame=full_frame,
                tradable=tradable,
                target_date=resolved_date,
                top_n=max(args.top_research_n, 0),
            )
        )

        news_table = read_optional_table(news_path)
        news_candidates, news_available = scan_news_reaction_candidates(
            news_table=news_table,
            target_date=resolved_date,
            tradable=tradable,
            top_n=max(args.top_research_n, 0),
        )
        exportable_ticket_seeds.extend(news_candidates)
        if not news_available:
            skipped_modules.append("news_reaction(no_input)")

        futures_table = read_optional_table(futures_path)
        futures_map = load_futures_map(futures_map_path)
        futures_candidates, futures_available = scan_futures_trigger_candidates(
            futures_table=futures_table,
            futures_map=futures_map,
            target_date=resolved_date,
            top_n=max(args.top_research_n, 0),
        )
        research_ticket_seeds.extend(futures_candidates)
        if not futures_available:
            skipped_modules.append("futures_trigger(no_input)")

        research_ticket_seeds = sorted(
            research_ticket_seeds,
            key=lambda item: float(item.get("priority_score", 0.0)),
            reverse=True,
        )[: max(args.top_research_n, 0)]

        exportable_paths, research_paths, report_path = write_outputs(
            output_dir=output_dir,
            as_of_date=resolved_date,
            regime_label=regime_label,
            market_summary=market_summary,
            anomalies=anomalies,
            watchlist=watchlist,
            exportable_tickets=exportable_ticket_seeds,
            research_tickets=research_ticket_seeds,
            skipped_modules=skipped_modules,
        )
    except AutoDetectError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"[OK] as_of={resolved_date.isoformat()} regime={regime_label}")
    print(
        "[OK] "
        f"watchlist={len(watchlist)} exportable_tickets={len(exportable_paths)} "
        f"research_tickets={len(research_paths)}"
    )
    print(f"[OK] output_dir={output_dir}")
    print(f"[OK] report={report_path}")
    if llm_hints:
        print(f"[OK] llm_hints_used={len(llm_hints)}")

    if args.export_strategies_dir:
        strategies_dir = Path(args.export_strategies_dir).resolve()
        pipeline_root = Path(args.pipeline_root).resolve() if args.pipeline_root else None
        try:
            exported, validation_errors = export_tickets(
                ticket_paths=exportable_paths,
                strategies_dir=strategies_dir,
                force_export=args.force_export,
                pipeline_root=pipeline_root,
                pipeline_stage=args.pipeline_stage,
            )
        except Exception as exc:  # pragma: no cover - integration error path
            print(f"[ERROR] export/validation integration failed: {exc}")
            return 1

        print(f"[OK] exported_strategies={len(exported)} dir={strategies_dir}")
        if validation_errors:
            print("[ERROR] exported strategies failed pipeline validation:")
            for strategy_id, errors in validation_errors.items():
                for error in errors:
                    print(f"  - {strategy_id}: {error}")
            return 1
        if pipeline_root is not None:
            print(
                f"[OK] pipeline validation passed for exported strategies (stage={args.pipeline_stage})"
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
