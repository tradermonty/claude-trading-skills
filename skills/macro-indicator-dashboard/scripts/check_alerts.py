#!/usr/bin/env python3
"""Detect regime-change alerts vs the previous run.

Compares two macro_regime JSON files and emits an alerts JSON the orchestrator
can read.

Usage:
    python3 check_alerts.py --current macro_regime_today.json \
        --previous macro_regime_yesterday.json --output macro_alerts.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def detect_alerts(current: dict[str, Any], previous: dict[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    # Regime change
    cur_regime = current.get("regime")
    prev_regime = previous.get("regime")
    if cur_regime and prev_regime and cur_regime != prev_regime:
        alerts.append({
            "level": "high",
            "type": "regime_change",
            "from": prev_regime,
            "to": cur_regime,
            "message": f"Regime changed: {prev_regime} -> {cur_regime}",
        })

    # Risk-on score swing
    cur_score = current.get("risk_on_score", 50)
    prev_score = previous.get("risk_on_score", 50)
    delta = cur_score - prev_score
    if abs(delta) >= 15:
        alerts.append({
            "level": "high" if abs(delta) >= 25 else "medium",
            "type": "risk_on_swing",
            "from": prev_score,
            "to": cur_score,
            "delta": delta,
            "message": f"Risk-on score moved {delta:+d} ({prev_score} -> {cur_score})",
        })

    # NFCI sign flip
    cur_nfci = current.get("indicators", {}).get("financial_conditions", {}).get("nfci")
    prev_nfci = previous.get("indicators", {}).get("financial_conditions", {}).get("nfci")
    if cur_nfci is not None and prev_nfci is not None:
        if (cur_nfci >= 0) != (prev_nfci >= 0):
            alerts.append({
                "level": "high",
                "type": "nfci_sign_flip",
                "from": prev_nfci,
                "to": cur_nfci,
                "message": f"NFCI crossed zero: {prev_nfci:+.2f} -> {cur_nfci:+.2f} ("
                           f"{'tightening' if cur_nfci > 0 else 'loosening'})",
            })

    # Yield curve sign flip
    cur_curve = current.get("indicators", {}).get("yield_curve", {}).get("t10y3m")
    prev_curve = previous.get("indicators", {}).get("yield_curve", {}).get("t10y3m")
    if cur_curve is not None and prev_curve is not None:
        if (cur_curve >= 0) != (prev_curve >= 0):
            alerts.append({
                "level": "high",
                "type": "yield_curve_sign_flip",
                "from": prev_curve,
                "to": cur_curve,
                "message": f"Yield curve T10Y3M crossed zero: {prev_curve:+.2f} -> {cur_curve:+.2f} ("
                           f"{'inverted' if cur_curve < 0 else 'un-inverted'})",
            })

    # Sahm Rule trigger
    cur_sahm = current.get("indicators", {}).get("growth", {}).get("sahm_proxy_pp")
    prev_sahm = previous.get("indicators", {}).get("growth", {}).get("sahm_proxy_pp")
    if cur_sahm is not None and prev_sahm is not None:
        if prev_sahm < 0.5 and cur_sahm >= 0.5:
            alerts.append({
                "level": "critical",
                "type": "sahm_trigger",
                "from": prev_sahm,
                "to": cur_sahm,
                "message": f"SAHM RULE TRIGGERED: {prev_sahm:+.2f} -> {cur_sahm:+.2f}pp. "
                           "Recession likely underway.",
            })

    return alerts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--current", type=Path, required=True)
    ap.add_argument("--previous", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    if not args.previous.exists():
        # First run, no previous to compare to
        out = {"as_of": "n/a", "alerts": [], "note": "no previous run for comparison"}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("w") as f:
            json.dump(out, f, indent=2)
        print("No previous run; wrote empty alerts file.", file=sys.stderr)
        return 0

    with args.current.open() as f:
        cur = json.load(f)
    with args.previous.open() as f:
        prev = json.load(f)

    alerts = detect_alerts(cur, prev)
    out = {
        "as_of": cur.get("as_of"),
        "compared_to": prev.get("as_of"),
        "alerts": alerts,
        "alert_count": len(alerts),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w") as f:
        json.dump(out, f, indent=2)

    print(f"Detected {len(alerts)} alert(s).", file=sys.stderr)
    for a in alerts:
        print(f"  [{a['level'].upper()}] {a['message']}", file=sys.stderr)
    print(f"Wrote {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
