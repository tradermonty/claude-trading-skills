#!/usr/bin/env python3
"""Flatten all positions and cancel all open orders. Called by kill-switch.

Usage:
    python3 flatten_all.py --reason "kill_switch_triggered" --confirm
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

try:
    import requests
    import yaml
except ImportError as e:
    print(f"error: {e}", file=sys.stderr)
    sys.exit(3)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO_ROOT / "config" / "trading_params.yaml"
ALPACA_PAPER_BASE = "https://paper-api.alpaca.markets"
ALPACA_LIVE_BASE = "https://api.alpaca.markets"


def _call(method: str, url: str, headers: dict) -> dict:
    r = requests.request(method, url, headers=headers, timeout=15)
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:500]}
    return {"status": r.status_code, "body": body}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reason", default="manual")
    ap.add_argument(
        "--confirm", action="store_true", help="Required unless kill_switch_active=true in config"
    )
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    with args.config.open() as f:
        cfg = yaml.safe_load(f)

    kill_switch_active = cfg.get("global", {}).get("kill_switch_active", False)
    if not args.confirm and not kill_switch_active:
        print("REFUSED: pass --confirm or set global.kill_switch_active=true", file=sys.stderr)
        return 1

    dry_run = os.environ.get("TRADE_LOOP_DRY_RUN", "true").lower() == "true"
    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    base = ALPACA_PAPER_BASE if paper else ALPACA_LIVE_BASE

    api_key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")

    out = {
        "triggered_at": dt.datetime.utcnow().isoformat() + "Z",
        "reason": args.reason,
        "paper": paper,
        "dry_run": dry_run,
        "actions": [],
    }

    if dry_run:
        out["status"] = "dry_run_acknowledged"
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, indent=2))
        print("DRY_RUN: flatten_all acknowledged, no API calls.", file=sys.stderr)
        return 0

    if not api_key or not secret:
        print("ERROR: ALPACA_API_KEY/ALPACA_SECRET_KEY not set", file=sys.stderr)
        return 3

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret,
    }

    # Cancel all open orders
    cancel_resp = _call("DELETE", f"{base}/v2/orders", headers)
    out["actions"].append({"action": "cancel_all_orders", "response": cancel_resp})

    # Close all positions
    close_resp = _call("DELETE", f"{base}/v2/positions?cancel_orders=true", headers)
    out["actions"].append({"action": "close_all_positions", "response": close_resp})

    out["status"] = "submitted"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2, default=str))
    print(f"Flatten all submitted. Reason: {args.reason}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
