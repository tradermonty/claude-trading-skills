"""Adapter layer: load each screener's report and normalize to Candidate dicts.

Each adapter is forgiving: missing report -> empty list, malformed entries
are skipped with a warning. The orchestrator never crashes on bad screener
output.
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any, Callable


def _warn(msg: str) -> None:
    print(f"[adapter-warn] {msg}", file=sys.stderr)


def _safe_load(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        _warn(f"failed to load {path}: {e}")
        return None


def _today() -> str:
    return dt.date.today().isoformat()


# ---------- Individual adapters ----------


def adapt_vcp_screener(reports_dir: Path) -> list[dict[str, Any]]:
    """VCP (Volatility Contraction Pattern) screener output.

    Expected fields per row: ticker, pivot_price, stop_price, target_price,
    base_count, score (0-100), atr, sector.
    """
    out: list[dict[str, Any]] = []
    candidates_files = sorted(reports_dir.glob(f"vcp_screener_{_today()}*.json"))
    if not candidates_files:
        candidates_files = sorted(reports_dir.glob("vcp_screener_*.json"))[-1:]
    for f in candidates_files:
        data = _safe_load(f)
        if not data:
            continue
        rows = data.get("candidates") or data.get("results") or data
        if not isinstance(rows, list):
            continue
        for row in rows:
            try:
                out.append(
                    {
                        "ticker": str(row["ticker"]).upper(),
                        "side": "buy",
                        "entry_type": "limit",
                        "entry_price": float(row["pivot_price"]),
                        "stop_loss": float(row["stop_price"]),
                        "target": float(row["target_price"]),
                        "primary_screener": "vcp-screener",
                        "supporting_screeners": [],
                        "strategy_score": float(row.get("score", 60)),
                        "confidence": float(row.get("confidence", 0.7)),
                        "sector": row.get("sector"),
                        "atr": row.get("atr"),
                        "source_report": str(f),
                        "as_of": data.get("as_of") or row.get("as_of"),
                        "notes": row.get("notes", "VCP pivot"),
                    }
                )
            except (KeyError, ValueError, TypeError) as e:
                _warn(f"vcp row skipped: {e}")
    return out


def adapt_canslim_screener(reports_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    files = sorted(reports_dir.glob(f"canslim_*{_today()}*.json"))
    if not files:
        files = sorted(reports_dir.glob("canslim_*.json"))[-1:]
    for f in files:
        data = _safe_load(f)
        if not data:
            continue
        rows = data.get("candidates") or data.get("results") or data
        if not isinstance(rows, list):
            continue
        for row in rows:
            try:
                entry = float(row.get("entry_price", row.get("close", 0)))
                stop = float(row.get("stop_price", entry * 0.93))
                target = float(row.get("target_price", entry * 1.15))
                out.append(
                    {
                        "ticker": str(row["ticker"]).upper(),
                        "side": "buy",
                        "entry_type": "limit",
                        "entry_price": entry,
                        "stop_loss": stop,
                        "target": target,
                        "primary_screener": "canslim-screener",
                        "supporting_screeners": [],
                        "strategy_score": float(row.get("score", 60)),
                        "confidence": float(row.get("confidence", 0.65)),
                        "sector": row.get("sector"),
                        "atr": row.get("atr"),
                        "source_report": str(f),
                        "as_of": data.get("as_of"),
                        "notes": "CANSLIM",
                    }
                )
            except (KeyError, ValueError, TypeError) as e:
                _warn(f"canslim row skipped: {e}")
    return out


def adapt_pead_screener(reports_dir: Path) -> list[dict[str, Any]]:
    """PEAD outputs SIGNAL_READY/BREAKOUT candidates."""
    out: list[dict[str, Any]] = []
    files = sorted(reports_dir.glob(f"pead_*{_today()}*.json"))
    if not files:
        files = sorted(reports_dir.glob("pead_*.json"))[-1:]
    for f in files:
        data = _safe_load(f)
        if not data:
            continue
        rows = data.get("candidates") or data.get("results") or data
        if not isinstance(rows, list):
            continue
        for row in rows:
            try:
                state = str(row.get("state", "")).upper()
                if state not in ("BREAKOUT", "SIGNAL_READY"):
                    continue
                entry = float(row.get("breakout_price", row.get("close")))
                stop = float(row.get("red_candle_low", row.get("stop_price", entry * 0.94)))
                target = float(row.get("target_price", entry + 2 * (entry - stop)))
                out.append(
                    {
                        "ticker": str(row["ticker"]).upper(),
                        "side": "buy",
                        "entry_type": "limit" if state == "SIGNAL_READY" else "market",
                        "entry_price": entry,
                        "stop_loss": stop,
                        "target": target,
                        "primary_screener": "pead-screener",
                        "supporting_screeners": [],
                        "strategy_score": float(row.get("score", 65)),
                        "confidence": 0.75 if state == "BREAKOUT" else 0.6,
                        "sector": row.get("sector"),
                        "source_report": str(f),
                        "notes": f"PEAD {state}",
                    }
                )
            except (KeyError, ValueError, TypeError) as e:
                _warn(f"pead row skipped: {e}")
    return out


def adapt_earnings_trade_analyzer(reports_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    files = sorted(reports_dir.glob(f"earnings_trade_*{_today()}*.json"))
    if not files:
        files = sorted(reports_dir.glob("earnings_trade_*.json"))[-1:]
    for f in files:
        data = _safe_load(f)
        if not data:
            continue
        rows = data.get("candidates") or data.get("results") or data
        if not isinstance(rows, list):
            continue
        for row in rows:
            try:
                grade = str(row.get("grade", "C")).upper()
                if grade not in ("A", "B"):
                    continue
                entry = float(row.get("entry_price", row.get("close")))
                stop = float(row.get("stop_price", entry * 0.94))
                target = float(row.get("target_price", entry * 1.10))
                out.append(
                    {
                        "ticker": str(row["ticker"]).upper(),
                        "side": "buy",
                        "entry_type": "market",
                        "entry_price": entry,
                        "stop_loss": stop,
                        "target": target,
                        "primary_screener": "earnings-trade-analyzer",
                        "supporting_screeners": [],
                        "strategy_score": 80 if grade == "A" else 65,
                        "confidence": 0.75 if grade == "A" else 0.6,
                        "sector": row.get("sector"),
                        "source_report": str(f),
                        "notes": f"Earnings reaction grade {grade}",
                    }
                )
            except (KeyError, ValueError, TypeError) as e:
                _warn(f"earnings row skipped: {e}")
    return out


def adapt_kanchi_dividend(reports_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    files = sorted(reports_dir.glob(f"kanchi_entry_signals_{_today()}*.json"))
    if not files:
        files = sorted(reports_dir.glob("kanchi_entry_signals_*.json"))[-1:]
    for f in files:
        data = _safe_load(f)
        if not data:
            continue
        rows = data.get("entries") or data.get("candidates") or data
        if not isinstance(rows, list):
            continue
        for row in rows:
            try:
                entry = float(row["entry_price"])
                stop = float(row["stop_price"])
                target = float(row.get("target_price", entry + 2 * (entry - stop)))
                out.append(
                    {
                        "ticker": str(row["ticker"]).upper(),
                        "side": "buy",
                        "entry_type": "limit",
                        "entry_price": entry,
                        "stop_loss": stop,
                        "target": target,
                        "primary_screener": "kanchi-dividend-sop",
                        "supporting_screeners": [],
                        "strategy_score": float(row.get("score", 70)),
                        "confidence": 0.75,
                        "sector": row.get("sector"),
                        "source_report": str(f),
                        "notes": "Kanchi pullback entry",
                    }
                )
            except (KeyError, ValueError, TypeError) as e:
                _warn(f"kanchi row skipped: {e}")
    return out


def adapt_edge_pipeline(reports_dir: Path) -> list[dict[str, Any]]:
    """edge-pipeline-orchestrator export shape: strategy.yaml -> candidates."""
    out: list[dict[str, Any]] = []
    files = sorted(reports_dir.glob("edge_pipeline/*/strategy_*.json"))
    files += sorted(reports_dir.glob(f"edge_pipeline_{_today()}*.json"))
    for f in files[-3:]:
        data = _safe_load(f)
        if not data:
            continue
        rows = data.get("entries") or data.get("candidates") or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            try:
                entry = float(row["entry_price"])
                stop = float(row["stop_price"])
                target = float(row.get("target_price", entry + 2 * (entry - stop)))
                out.append(
                    {
                        "ticker": str(row["ticker"]).upper(),
                        "side": str(row.get("side", "buy")).lower(),
                        "entry_type": str(row.get("entry_type", "limit")),
                        "entry_price": entry,
                        "stop_loss": stop,
                        "target": target,
                        "primary_screener": "edge-pipeline",
                        "supporting_screeners": [],
                        "strategy_score": float(row.get("score", 65)),
                        "confidence": float(row.get("confidence", 0.6)),
                        "sector": row.get("sector"),
                        "source_report": str(f),
                        "notes": "edge-pipeline strategy",
                    }
                )
            except (KeyError, ValueError, TypeError) as e:
                _warn(f"edge row skipped: {e}")
    return out


def adapt_rsm_scanner(reports_dir: Path) -> list[dict[str, Any]]:
    """relative-strength-momentum-scanner output: rsm_scanner_<date>.json.

    The scanner already emits records in the Candidate schema with
    primary_screener='rsm-scanner'. Only `entry_ready` rows are forwarded;
    watchlist rows stay filtered out of the trade loop (monitoring only).
    """
    out: list[dict[str, Any]] = []
    files = sorted(reports_dir.glob(f"rsm_scanner_{_today()}*.json"))
    if not files:
        files = sorted(reports_dir.glob("rsm_scanner_*.json"))[-1:]
    for f in files:
        data = _safe_load(f)
        if not data:
            continue
        rows = data.get("candidates") or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if row.get("status") != "entry_ready":
                continue
            try:
                out.append(
                    {
                        "ticker": str(row["ticker"]).upper(),
                        "side": str(row.get("side", "buy")).lower(),
                        "entry_type": str(row.get("entry_type", "market")),
                        "entry_price": float(row["entry_price"]),
                        "stop_loss": float(row["stop_loss"]),
                        "target": float(row["target"]),
                        "primary_screener": "rsm-scanner",
                        "supporting_screeners": list(row.get("supporting_screeners") or []),
                        "strategy_score": float(row.get("strategy_score", row.get("rs_score", 60))),
                        "confidence": float(row.get("confidence", 0.7)),
                        "sector": row.get("sector"),
                        "source_report": str(f),
                        "as_of": data.get("as_of") or row.get("as_of"),
                        "notes": row.get("notes", "RS momentum leader"),
                    }
                )
            except (KeyError, ValueError, TypeError) as e:
                _warn(f"rsm row skipped: {e}")
    return out


# Registry: map screener key (matches screener_weights.yaml) -> loader fn
ADAPTERS: dict[str, Callable[[Path], list[dict[str, Any]]]] = {
    "vcp-screener": adapt_vcp_screener,
    "canslim-screener": adapt_canslim_screener,
    "pead-screener": adapt_pead_screener,
    "earnings-trade-analyzer": adapt_earnings_trade_analyzer,
    "kanchi-dividend-sop": adapt_kanchi_dividend,
    "edge-pipeline": adapt_edge_pipeline,
    "rsm-scanner": adapt_rsm_scanner,
}


def load_all_candidates(
    reports_dir: Path, enabled_screeners: list[str] | None = None
) -> list[dict[str, Any]]:
    """Run every enabled adapter and return concatenated candidate list."""
    enabled = set(enabled_screeners) if enabled_screeners else set(ADAPTERS.keys())
    all_cands: list[dict[str, Any]] = []
    for key, fn in ADAPTERS.items():
        if key not in enabled:
            continue
        try:
            cands = fn(reports_dir)
            all_cands.extend(cands)
        except Exception as e:
            _warn(f"adapter {key} crashed: {e}")
    return all_cands
