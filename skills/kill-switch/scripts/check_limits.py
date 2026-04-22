#!/usr/bin/env python3
"""Kill-switch watchdog. Compares Alpaca account state against trading_params.yaml limits.

Exit codes:
    0 - OK, within limits
    1 - TRIPPED, flatten_all invoked (or would be, in dry_run)
    2 - WARN, soft limit (position count / sector) breached, blocking new entries
    3 - UNKNOWN, Alpaca unreachable - orchestrator must treat as TRIPPED

Usage:
    # Continuous watchdog (runs flatten on hard breach):
    python3 check_limits.py \
      --sod state/sod_2026-04-21.json \
      --output state/kill_switch_status.json

    # Pre-loop check (orchestrator only - never flattens):
    python3 check_limits.py --pre-loop --output state/kill_switch_status.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    import requests
    import yaml
except ImportError as e:
    print(f"error: {e}", file=sys.stderr)
    sys.exit(3)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO_ROOT / "config" / "trading_params.yaml"
DEFAULT_SECTOR_MAP = REPO_ROOT / "config" / "sector_map.yaml"
FLATTEN_SCRIPT = REPO_ROOT / "skills" / "alpaca-executor" / "scripts" / "flatten_all.py"
ALPACA_PAPER_BASE = "https://paper-api.alpaca.markets"
ALPACA_LIVE_BASE = "https://api.alpaca.markets"


# ---------- Alpaca helpers ----------


def _headers() -> dict[str, str]:
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("ALPACA_API_KEY / ALPACA_SECRET_KEY not set")
    return {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}


def _base() -> str:
    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    return ALPACA_PAPER_BASE if paper else ALPACA_LIVE_BASE


def fetch_account(timeout: int = 10) -> dict[str, Any]:
    r = requests.get(f"{_base()}/v2/account", headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_positions(timeout: int = 10) -> list[dict[str, Any]]:
    r = requests.get(f"{_base()}/v2/positions", headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


# ---------- Check logic (pure functions, testable) ----------


def check_daily_loss(
    current_equity: float,
    sod_equity: float,
    max_daily_loss_pct: float,
) -> dict[str, Any]:
    """Return status dict; breach is HARD (triggers flatten)."""
    if sod_equity <= 0:
        return {"type": "daily_loss", "status": "skipped", "message": "sod_equity missing or zero"}
    pnl_pct = (current_equity - sod_equity) / sod_equity * 100
    limit = -abs(max_daily_loss_pct)
    breached = pnl_pct <= limit
    return {
        "type": "daily_loss",
        "status": "BREACH" if breached else "ok",
        "severity": "hard" if breached else None,
        "value_pct": round(pnl_pct, 3),
        "limit_pct": limit,
        "message": (
            f"Daily loss {pnl_pct:.2f}% breaches {limit:.2f}% limit"
            if breached
            else f"Daily P&L {pnl_pct:.2f}%"
        ),
    }


def check_position_count(
    positions: list[dict[str, Any]],
    max_positions: int,
) -> dict[str, Any]:
    """Soft limit - blocks new entries but does not flatten."""
    count = len(positions)
    breached = count >= max_positions
    return {
        "type": "position_count",
        "status": "BREACH" if breached else "ok",
        "severity": "soft" if breached else None,
        "value": count,
        "limit": max_positions,
        "message": (
            f"At cap: {count}/{max_positions} positions open"
            if breached
            else f"{count}/{max_positions} positions"
        ),
    }


def check_single_position_size(
    positions: list[dict[str, Any]],
    account_equity: float,
    max_position_size_pct: float,
) -> dict[str, Any]:
    """Per-position cap. Soft breach - trim suggested, not flatten."""
    if account_equity <= 0:
        return {"type": "single_position_size", "status": "skipped"}
    max_notional = account_equity * max_position_size_pct / 100
    offenders = []
    for p in positions:
        mkt_val = abs(float(p.get("market_value", 0)))
        if mkt_val > max_notional * 1.001:
            offenders.append(
                {
                    "symbol": p.get("symbol"),
                    "market_value": round(mkt_val, 2),
                    "pct_of_account": round(mkt_val / account_equity * 100, 2),
                }
            )
    return {
        "type": "single_position_size",
        "status": "BREACH" if offenders else "ok",
        "severity": "soft" if offenders else None,
        "limit_pct": max_position_size_pct,
        "offenders": offenders,
        "message": (
            f"{len(offenders)} position(s) exceed {max_position_size_pct}% cap"
            if offenders
            else "All positions within single-position cap"
        ),
    }


def load_sector_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    # support both {symbol: sector} flat map and {sectors: {sector: [symbols]}}
    if "sectors" in data and isinstance(data["sectors"], dict):
        out: dict[str, str] = {}
        for sector, tickers in data["sectors"].items():
            for t in tickers or []:
                out[str(t).upper()] = sector
        return out
    return {str(k).upper(): v for k, v in data.items()}


def check_sector_exposure(
    positions: list[dict[str, Any]],
    account_equity: float,
    max_sector_exposure_pct: float,
    sector_map: dict[str, str],
) -> dict[str, Any]:
    """Sum long+short notional by GICS sector. Soft breach."""
    if account_equity <= 0:
        return {"type": "sector_exposure", "status": "skipped"}
    by_sector: dict[str, float] = defaultdict(float)
    for p in positions:
        sym = str(p.get("symbol", "")).upper()
        sector = sector_map.get(sym, "Unclassified")
        by_sector[sector] += abs(float(p.get("market_value", 0)))
    breaches = []
    exposures_pct = {}
    for sector, notional in by_sector.items():
        pct = notional / account_equity * 100
        exposures_pct[sector] = round(pct, 2)
        if pct > max_sector_exposure_pct:
            breaches.append({"sector": sector, "exposure_pct": round(pct, 2)})
    return {
        "type": "sector_exposure",
        "status": "BREACH" if breaches else "ok",
        "severity": "soft" if breaches else None,
        "limit_pct": max_sector_exposure_pct,
        "exposures_pct": exposures_pct,
        "breaches": breaches,
        "message": (
            f"Sector cap breached: {[b['sector'] for b in breaches]}"
            if breaches
            else "All sectors within exposure cap"
        ),
    }


def check_distribution_days(distribution_state_path: Path, limit: int = 6) -> dict[str, Any]:
    """Reads market-top-detector output if present. Soft breach - force trim."""
    if not distribution_state_path.exists():
        return {
            "type": "distribution_days",
            "status": "skipped",
            "message": f"no state file at {distribution_state_path}",
        }
    try:
        state = json.loads(distribution_state_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return {"type": "distribution_days", "status": "skipped", "message": f"read error: {e}"}
    count = int(state.get("distribution_day_count", 0))
    breached = count >= limit
    return {
        "type": "distribution_days",
        "status": "BREACH" if breached else "ok",
        "severity": "soft" if breached else None,
        "value": count,
        "limit": limit,
        "message": (
            f"Distribution days {count} >= {limit}: market-top warning"
            if breached
            else f"Distribution days: {count}/{limit}"
        ),
    }


# ---------- Orchestration ----------


def build_status(
    account: dict[str, Any],
    positions: list[dict[str, Any]],
    sod: dict[str, Any],
    profile: dict[str, Any],
    sector_map: dict[str, str],
    distribution_state_path: Path,
) -> dict[str, Any]:
    """Run every check and build the status payload."""
    current_equity = float(account.get("equity", 0))
    sod_equity = float(sod.get("equity", 0)) if sod else 0.0

    checks = [
        check_daily_loss(current_equity, sod_equity, profile["max_daily_loss_pct"]),
        check_position_count(positions, profile["max_positions"]),
        check_single_position_size(positions, current_equity, profile["max_position_size_pct"]),
        check_sector_exposure(
            positions, current_equity, profile["max_sector_exposure_pct"], sector_map
        ),
        check_distribution_days(distribution_state_path, limit=6),
    ]

    breaches = [c for c in checks if c.get("status") == "BREACH"]
    hard_breaches = [c for c in breaches if c.get("severity") == "hard"]
    soft_breaches = [c for c in breaches if c.get("severity") == "soft"]

    if hard_breaches:
        status = "TRIPPED"
    elif soft_breaches:
        status = "WARN"
    else:
        status = "OK"

    pnl_pct = ((current_equity - sod_equity) / sod_equity * 100) if sod_equity > 0 else None

    return {
        "checked_at": dt.datetime.utcnow().isoformat() + "Z",
        "status": status,
        "account": {
            "equity": round(current_equity, 2),
            "sod_equity": round(sod_equity, 2),
            "pnl_pct": round(pnl_pct, 3) if pnl_pct is not None else None,
            "cash": round(float(account.get("cash", 0)), 2),
            "buying_power": round(float(account.get("buying_power", 0)), 2),
        },
        "positions": {
            "count": len(positions),
            "symbols": sorted({str(p.get("symbol", "")).upper() for p in positions}),
        },
        "checks": checks,
        "hard_breaches": hard_breaches,
        "soft_breaches": soft_breaches,
        "reason": hard_breaches[0]["message"] if hard_breaches else None,
    }


def invoke_flatten_all(reason: str, flatten_output: Path) -> dict[str, Any]:
    """Shell out to alpaca-executor/flatten_all.py."""
    flatten_output.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(FLATTEN_SCRIPT),
        "--reason",
        f"kill_switch: {reason}",
        "--confirm",
        "--output",
        str(flatten_output),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return {
            "invoked_at": dt.datetime.utcnow().isoformat() + "Z",
            "returncode": r.returncode,
            "stdout": r.stdout[-500:],
            "stderr": r.stderr[-500:],
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "error": "flatten_all timed out after 60s"}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--sod", type=Path, help="Path to start-of-day equity snapshot")
    ap.add_argument("--sector-map", type=Path, default=DEFAULT_SECTOR_MAP)
    ap.add_argument(
        "--distribution-state", type=Path, default=REPO_ROOT / "state" / "distribution_days.json"
    )
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument(
        "--flatten-output", type=Path, default=REPO_ROOT / "state" / "flatten_all_last.json"
    )
    ap.add_argument(
        "--pre-loop", action="store_true", help="Read-only mode: never triggers flatten_all"
    )
    args = ap.parse_args()

    # Load config + profile
    with args.config.open() as f:
        cfg = yaml.safe_load(f)
    profile_name = cfg["active_profile"]
    profile = cfg["profiles"][profile_name]

    # Load SOD snapshot (default to today if not provided)
    sod: dict[str, Any] = {}
    sod_path = args.sod
    if sod_path is None:
        sod_path = REPO_ROOT / "state" / f"sod_{dt.date.today().isoformat()}.json"
    if sod_path.exists():
        try:
            sod = json.loads(sod_path.read_text())
        except (json.JSONDecodeError, OSError):
            sod = {}

    sector_map = load_sector_map(args.sector_map)

    # Fetch account + positions; on any failure, emit UNKNOWN.
    try:
        account = fetch_account()
        positions = fetch_positions()
    except (requests.RequestException, RuntimeError) as e:
        payload = {
            "checked_at": dt.datetime.utcnow().isoformat() + "Z",
            "status": "UNKNOWN",
            "error": str(e),
            "reason": f"Alpaca unreachable: {e}",
        }
        _write(args.output, payload)
        print(f"UNKNOWN: {e}", file=sys.stderr)
        return 3

    status = build_status(account, positions, sod, profile, sector_map, args.distribution_state)

    # On hard breach, shell out to flatten_all (unless pre-loop mode)
    if status["status"] == "TRIPPED" and not args.pre_loop:
        flat = invoke_flatten_all(status["reason"], args.flatten_output)
        status["flatten_all_invoked"] = True
        status["flatten_all"] = flat

    _write(args.output, status)

    if status["status"] == "TRIPPED":
        print(f"TRIPPED: {status['reason']}", file=sys.stderr)
        return 1
    if status["status"] == "WARN":
        print(f"WARN: {len(status['soft_breaches'])} soft breach(es)", file=sys.stderr)
        return 2
    print(
        f"OK: equity=${status['account']['equity']:,.2f} "
        f"pnl={status['account']['pnl_pct']}% "
        f"positions={status['positions']['count']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
