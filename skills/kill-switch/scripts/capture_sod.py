#!/usr/bin/env python3
"""Capture start-of-day Alpaca account equity. Run at 09:30 ET.

Usage:
    python3 capture_sod.py --output state/sod_$(date +%Y-%m-%d).json
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
except ImportError:
    print("error: requests not installed", file=sys.stderr)
    sys.exit(3)


ALPACA_PAPER_BASE = "https://paper-api.alpaca.markets"
ALPACA_LIVE_BASE = "https://api.alpaca.markets"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    base = ALPACA_PAPER_BASE if paper else ALPACA_LIVE_BASE
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")

    if not key or not secret:
        print("error: ALPACA_API_KEY/ALPACA_SECRET_KEY not set", file=sys.stderr)
        return 3

    headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}

    try:
        r = requests.get(f"{base}/v2/account", headers=headers, timeout=10)
        r.raise_for_status()
        acct = r.json()
    except requests.RequestException as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    out = {
        "captured_at": dt.datetime.utcnow().isoformat() + "Z",
        "date": dt.date.today().isoformat(),
        "paper": paper,
        "equity": float(acct.get("equity", 0)),
        "cash": float(acct.get("cash", 0)),
        "buying_power": float(acct.get("buying_power", 0)),
        "portfolio_value": float(acct.get("portfolio_value", 0)),
        "last_equity": float(acct.get("last_equity", 0)),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2))
    print(f"SOD captured: equity=${out['equity']:,.2f}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
