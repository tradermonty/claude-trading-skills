#!/usr/bin/env python3
"""Persistent, cross-run learning store for the mt5-robot-tester pipeline.

The point (per the user's request) is that the skill **improves its selection of
the best bots on every loop**. This is done deterministically — not with any
opaque magic — by accumulating aggregate statistics across runs and feeding them
back into the pipeline:

  * per-parameter average profit improvement from optimizing it → the sequential
    Round-3 optimization tries the historically most impactful parameters first
    (so improvements are found sooner and, under a step budget, at all);
  * per-symbol how often it was a bot's best pair and its mean profit → a prior
    surfaced in the report;
  * per-bot verdict/reason → institutional memory across loops.

State lives in ``learnings.json``; a human-readable ``learnings.md`` digest is
written beside it in the configured output directory.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path

SCHEMA_VERSION = "1.0"


def _empty() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated": None,
        "runs": 0,
        "symbols": {},  # symbol -> {best_pair_count, profit_sum, profit_count}
        "parameters": {},  # name   -> {opt_count, improvement_sum, improved_count}
        "bots": {},  # bot    -> {verdict, reason, last_seen}
    }


class Learnings:
    """Load/update/save the learning store and expose guidance to the pipeline."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                # Fill any missing top-level keys for forward-compat.
                base = _empty()
                base.update({k: data.get(k, base[k]) for k in base})
                return base
            except (json.JSONDecodeError, OSError):
                pass
        return _empty()

    # --- guidance (read) ---------------------------------------------------

    def param_avg_improvement(self, name: str) -> float:
        p = self.data["parameters"].get(name)
        if not p or not p.get("opt_count"):
            return 0.0
        return p["improvement_sum"] / p["opt_count"]

    def param_priority_order(self, names: list[str]) -> list[str]:
        """Order ``names`` by historical average improvement (desc), stable on
        ties and for parameters with no history (original order preserved)."""
        indexed = list(enumerate(names))
        indexed.sort(key=lambda t: (-self.param_avg_improvement(t[1]), t[0]))
        return [name for _, name in indexed]

    def symbol_prior(self, symbol: str) -> dict:
        s = self.data["symbols"].get(symbol)
        if not s or not s.get("profit_count"):
            return {"best_pair_count": 0, "avg_profit": None}
        return {
            "best_pair_count": s.get("best_pair_count", 0),
            "avg_profit": s["profit_sum"] / s["profit_count"],
        }

    # --- updates (write) ---------------------------------------------------

    def bump_run(self) -> None:
        self.data["runs"] = self.data.get("runs", 0) + 1

    def record_best_pair(self, symbol: str, profit: float | None) -> None:
        s = self.data["symbols"].setdefault(
            symbol, {"best_pair_count": 0, "profit_sum": 0.0, "profit_count": 0}
        )
        s["best_pair_count"] += 1
        if profit is not None:
            s["profit_sum"] += profit
            s["profit_count"] += 1

    def record_param_optimization(self, name: str, improvement: float) -> None:
        p = self.data["parameters"].setdefault(
            name, {"opt_count": 0, "improvement_sum": 0.0, "improved_count": 0}
        )
        p["opt_count"] += 1
        p["improvement_sum"] += improvement
        if improvement > 0:
            p["improved_count"] += 1

    def record_bot(self, bot: str, verdict: str, reason: str = "") -> None:
        self.data["bots"][bot] = {
            "verdict": verdict,
            "reason": reason,
            "last_seen": dt.date.today().isoformat(),
        }

    # --- persistence -------------------------------------------------------

    def save(self, markdown_path: str | Path | None = None) -> None:
        self.data["updated"] = dt.datetime.now().isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.path, json.dumps(self.data, indent=2, ensure_ascii=False))
        if markdown_path:
            self._atomic_write(Path(markdown_path), self.render_markdown())

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def render_markdown(self) -> str:
        d = self.data
        lines = [
            "# MT5 Robot Tester — Learnings",
            "",
            "Accumulated learning store across runs. The orchestrator uses it to",
            "**order parameter optimization by historical impact** and as a symbol",
            "prior. It is updated after every bot.",
            "",
            f"- Accumulated runs: **{d.get('runs', 0)}**",
            f"- Last updated: {d.get('updated')}",
            "",
            "## Parameters by average impact (profit delta after optimization)",
            "",
            "| Parameter | Optimized runs | Improved runs | Average delta |",
            "|-----------|---------------:|--------------:|--------------:|",
        ]
        params = sorted(
            d["parameters"].items(),
            key=lambda kv: -(kv[1]["improvement_sum"] / max(kv[1]["opt_count"], 1)),
        )
        for name, p in params:
            avg = p["improvement_sum"] / max(p["opt_count"], 1)
            lines.append(f"| {name} | {p['opt_count']} | {p['improved_count']} | {avg:,.2f} |")
        if not params:
            lines.append("| _(no data yet)_ | | | |")

        lines += [
            "",
            "## Symbols (best-symbol frequency / average profit)",
            "",
            "| Symbol | Best-symbol runs | Average profit |",
            "|--------|-----------------:|---------------:|",
        ]
        syms = sorted(d["symbols"].items(), key=lambda kv: -kv[1].get("best_pair_count", 0))
        for sym, s in syms:
            avg = s["profit_sum"] / s["profit_count"] if s.get("profit_count") else None
            avg_s = f"{avg:,.2f}" if avg is not None else "—"
            lines.append(f"| {sym} | {s.get('best_pair_count', 0)} | {avg_s} |")
        if not syms:
            lines.append("| _(no data yet)_ | | |")

        lines += [
            "",
            "## Verdicts by bot",
            "",
            "| Bot | Verdict | Reason | Last seen |",
            "|-----|---------|--------|-----------|",
        ]
        for bot, b in sorted(d["bots"].items()):
            lines.append(
                f"| {bot} | {b.get('verdict', '')} | {b.get('reason', '')} "
                f"| {b.get('last_seen', '')} |"
            )
        if not d["bots"]:
            lines.append("| _(no data yet)_ | | | |")
        lines.append("")
        return "\n".join(lines)


def load(path: str | Path) -> Learnings:
    return Learnings(path)
