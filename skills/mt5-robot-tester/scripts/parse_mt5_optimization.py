#!/usr/bin/env python3
"""Parse a MetaTrader 5 Strategy Tester **optimization** report.

Handles both the SpreadsheetML (``.xml``) form MT5 writes for optimization runs
and, as a fallback, an HTML ``<table>`` export. Reports may be in English or
Spanish; headers are normalized via ``mt5_common.canonical_header``.

Each data row (a "pass") becomes a dict:

    {
      "pass": 33, "symbol": "TSLA", "profit": 18308.98, "result": 1.39,
      "trades": 686, "profit_factor": 1.39, "sharpe": 5.24,
      "recovery_factor": 6.98, "drawdown_pct": 15.22, "expected_payoff": 26.69,
      "inputs": {"GannHiLoPeriod1": 86.0, ...}
    }

Round-1 gate helpers (``count_positive_profit``, ``best_pass``) and the Round-3
helper ``best_param_value`` build on this.

CLI:
    python3 parse_mt5_optimization.py report.xml --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from mt5_common import canonical_header, table_records, to_float
except ImportError:  # pragma: no cover - import shim for loose script execution
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from mt5_common import canonical_header, table_records, to_float

# Metric columns whose values are numeric.
_NUMERIC_METRICS = {
    "pass",
    "result",
    "profit",
    "trades",
    "profit_factor",
    "expected_payoff",
    "recovery_factor",
    "sharpe",
    "drawdown_pct",
}


def parse_passes(path: str | Path) -> list[dict]:
    """Parse an optimization report into a list of pass dicts."""
    rows = table_records(path)
    if not rows:
        return []

    # Find the header row (first row that maps at least two known headers).
    header_idx = None
    for i, cells in enumerate(rows):
        mapped = sum(1 for c in cells if canonical_header(c) is not None)
        if mapped >= 2:
            header_idx = i
            break
    if header_idx is None:
        return []

    headers = rows[header_idx]
    # Column plan: canonical metric key, or ("input", name) for EA parameters.
    plan: list[tuple[str, str]] = []
    for raw in headers:
        canon = canonical_header(raw)
        if canon:
            plan.append(("metric", canon))
        elif raw.strip():
            plan.append(("input", raw.strip()))
        else:
            plan.append(("skip", ""))

    passes: list[dict] = []
    for cells in rows[header_idx + 1 :]:
        if not any(c.strip() for c in cells):
            continue
        record: dict = {"inputs": {}}
        for col, value in enumerate(cells):
            if col >= len(plan):
                break
            kind, key = plan[col]
            if kind == "metric":
                record[key] = to_float(value) if key in _NUMERIC_METRICS else value
            elif kind == "input":
                num = to_float(value)
                record["inputs"][key] = num if num is not None else value
        # A valid data row must have a numeric profit.
        if record.get("profit") is not None:
            if record.get("pass") is not None:
                record["pass"] = int(record["pass"])
            if record.get("trades") is not None:
                record["trades"] = int(record["trades"])
            passes.append(record)
    return passes


def count_positive_profit(passes: list[dict]) -> int:
    """Number of passes with profit strictly greater than zero."""
    return sum(1 for p in passes if (p.get("profit") or 0) > 0)


def best_pass(passes: list[dict], by: str = "profit") -> dict | None:
    """Pass with the maximum value of ``by`` (default profit)."""
    scored = [p for p in passes if isinstance(p.get(by), (int, float))]
    return max(scored, key=lambda p: p[by]) if scored else None


def best_param_value(passes: list[dict], param_name: str, by: str = "profit"):
    """Value of ``param_name`` in the pass that maximizes ``by``."""
    best = None
    best_score = float("-inf")
    for p in passes:
        score = p.get(by)
        if isinstance(score, (int, float)) and score > best_score:
            val = p.get("inputs", {}).get(param_name)
            if val is not None:
                best, best_score = val, score
    return best


def gate_round1(
    passes: list[dict], deposit: float, min_positive: int = 5, min_profit_multiple: float = 3.0
) -> dict:
    """Evaluate the Round-1 gate.

    Passes if ``>= min_positive`` symbols are profitable AND the best symbol's
    profit is at least ``min_profit_multiple * deposit``.
    """
    positive = count_positive_profit(passes)
    top = best_pass(passes, by="profit")
    best_profit = top.get("profit") if top else None
    threshold = min_profit_multiple * deposit
    passed = positive >= min_positive and best_profit is not None and best_profit >= threshold
    return {
        "passed": passed,
        "positive_symbols": positive,
        "min_positive": min_positive,
        "best_symbol": top.get("symbol") if top else None,
        "best_profit": best_profit,
        "profit_threshold": threshold,
        "reason": _gate_reason(passed, positive, min_positive, best_profit, threshold),
    }


def _gate_reason(passed, positive, min_positive, best_profit, threshold) -> str:
    if passed:
        return "ok"
    parts = []
    if positive < min_positive:
        parts.append(f"only {positive}/{min_positive} profitable symbols")
    if best_profit is None or best_profit < threshold:
        parts.append(f"best profit {best_profit} < threshold {threshold:.0f}")
    return "; ".join(parts) or "gate not met"


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse an MT5 optimization report.")
    parser.add_argument("report", help="Path to the .xml/.htm optimization report.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--deposit", type=float, default=10000.0, help="Deposit for the Round-1 gate summary."
    )
    args = parser.parse_args(argv)

    path = Path(args.report)
    if not path.exists():
        print(f"error: report not found: {path}", file=sys.stderr)
        return 1

    passes = parse_passes(path)
    gate = gate_round1(passes, args.deposit)
    if args.json:
        print(json.dumps({"passes": passes, "gate": gate}, indent=2))
    else:
        print(
            f"passes: {len(passes)} | profitable: {gate['positive_symbols']} "
            f"| best: {gate['best_symbol']} ({gate['best_profit']}) "
            f"| gate: {'PASS' if gate['passed'] else 'FAIL'} ({gate['reason']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
