#!/usr/bin/env python3
"""Main automated trading loop driver.

Runs every 5 min via launchd during US market hours. Orchestrates:
  1. Pre-loop kill-switch check
  2. Macro regime snapshot
  3. Screener adapter fan-out
  4. Ranking + dedupe
  5. Per-candidate position sizing
  6. Bracket order submission via alpaca-executor
  7. Per-iteration audit log

Usage:
    # Plan-only smoke test (no orders):
    python3 run_loop.py --mode plan --output state/loop/

    # Live loop (still gated by TRADE_LOOP_DRY_RUN env):
    python3 run_loop.py --mode execute --output state/loop/
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

try:
    import yaml
except ImportError:
    print("error: pyyaml not installed", file=sys.stderr)
    sys.exit(1)


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).parent))

from rank_signals import rank_and_dedupe  # noqa: E402
from screener_adapters import load_all_candidates  # noqa: E402

DEFAULT_CONFIG = REPO_ROOT / "config" / "trading_params.yaml"
DEFAULT_WEIGHTS = REPO_ROOT / "config" / "screener_weights.yaml"
DEFAULT_SECTOR_MAP = REPO_ROOT / "config" / "sector_map.yaml"
KILL_SWITCH = REPO_ROOT / "skills" / "kill-switch" / "scripts" / "check_limits.py"
EXECUTE_TRADE = REPO_ROOT / "skills" / "alpaca-executor" / "scripts" / "execute_trade.py"
REPORTS_DIR = REPO_ROOT / "reports"
MACRO_DIR = REPO_ROOT / "state" / "macro"


# ---------- Utilities ----------


def _utcnow() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _now_et() -> dt.datetime:
    return dt.datetime.now(ZoneInfo("America/New_York"))


def _signal_id(ticker: str, date: str, screener: str) -> str:
    raw = f"{ticker}|{date}|{screener}".encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:16]


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f)


def load_sector_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    if "sectors" in data and isinstance(data["sectors"], dict):
        out: dict[str, str] = {}
        for sector, tickers in data["sectors"].items():
            for t in tickers or []:
                out[str(t).upper()] = sector
        return out
    return {str(k).upper(): v for k, v in data.items()}


# ---------- Pre-loop gates ----------


def in_trading_window(cfg: dict[str, Any]) -> tuple[bool, str]:
    g = cfg.get("global", {})
    hours = g.get("trading_hours", {})
    start_s = hours.get("start", "09:45")
    end_s = hours.get("end", "15:45")
    tz = ZoneInfo(hours.get("timezone", "America/New_York"))

    now = dt.datetime.now(tz)
    if now.weekday() >= 5:  # Sat/Sun
        return False, f"weekend ({now.strftime('%A')})"

    today_str = now.date().isoformat()
    blackouts = g.get("blackout_dates", []) or []
    if today_str in blackouts:
        return False, f"blackout date {today_str}"

    h1, m1 = (int(x) for x in start_s.split(":"))
    h2, m2 = (int(x) for x in end_s.split(":"))
    start = now.replace(hour=h1, minute=m1, second=0, microsecond=0)
    end = now.replace(hour=h2, minute=m2, second=0, microsecond=0)
    if now < start:
        return False, f"before open ({now.strftime('%H:%M')} < {start_s})"
    if now > end:
        return False, f"after close ({now.strftime('%H:%M')} > {end_s})"
    return True, "inside trading window"


def run_killswitch_check(output_path: Path) -> dict[str, Any]:
    """Shell out to kill-switch in --pre-loop mode."""
    cmd = [sys.executable, str(KILL_SWITCH), "--pre-loop", "--output", str(output_path)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    status_path = output_path
    payload: dict[str, Any] = {}
    if status_path.exists():
        try:
            payload = json.loads(status_path.read_text())
        except (json.JSONDecodeError, OSError):
            payload = {}
    payload["_returncode"] = r.returncode
    payload["_stderr"] = (r.stderr or "")[-200:]
    return payload


# ---------- Macro ----------


def latest_macro_snapshot(max_age_hours: float = 4.0) -> dict[str, Any]:
    """Find today's dashboard_*.json and return it; fall back to neutral."""
    today = dt.date.today().isoformat()
    paths = sorted(MACRO_DIR.glob(f"dashboard_{today}*.json"), reverse=True)
    if not paths:
        paths = sorted(MACRO_DIR.glob("dashboard_*.json"), reverse=True)
    if not paths:
        return {
            "_fallback": True,
            "regime": "UNKNOWN",
            "risk_on_score": 50,
            "exposure_scale": 0.5,
            "warning": "no macro snapshot found - using neutral",
        }
    latest = paths[0]
    try:
        payload = json.loads(latest.read_text())
    except (json.JSONDecodeError, OSError):
        return {
            "_fallback": True,
            "regime": "UNKNOWN",
            "risk_on_score": 50,
            "exposure_scale": 0.5,
            "warning": f"corrupt macro file {latest}",
        }

    # Age check
    mtime = dt.datetime.utcfromtimestamp(latest.stat().st_mtime)
    age_h = (dt.datetime.utcnow() - mtime).total_seconds() / 3600
    if age_h > max_age_hours:
        payload["_stale"] = True
        payload["_age_hours"] = round(age_h, 2)
        payload.setdefault("warning", f"stale by {age_h:.1f}h - caller should discount")

    payload["_source"] = str(latest)
    return payload


# ---------- Per-candidate gates ----------


def size_position(
    entry: float,
    stop: float,
    profile: dict[str, Any],
    exposure_scale: float,
) -> tuple[int, dict[str, Any]]:
    """Return (quantity, detail). Quantity=0 means skip."""
    if entry <= 0 or stop <= 0 or entry == stop:
        return 0, {"reason": "invalid prices"}

    account = profile["account_size_usd"]
    risk_pct = profile["risk_per_trade_pct"]
    max_risk = account * risk_pct / 100
    # Scale risk down (but not below 50%) when exposure_scale is reduced
    scaled_max_risk = max_risk * max(exposure_scale, 0.25)

    risk_per_share = abs(entry - stop)
    raw_qty = scaled_max_risk / risk_per_share
    qty = int(math.floor(raw_qty))

    max_notional = account * profile["max_position_size_pct"] / 100
    if qty * entry > max_notional:
        qty = int(math.floor(max_notional / entry))

    min_usd = profile.get("min_position_size_usd", 0)
    if qty * entry < min_usd:
        return 0, {"reason": f"below min position size ${min_usd}"}

    return qty, {
        "raw_qty": round(raw_qty, 3),
        "scaled_max_risk": round(scaled_max_risk, 2),
        "risk_per_share": round(risk_per_share, 4),
        "notional": round(qty * entry, 2),
    }


def sector_of(
    ticker: str,
    cand_sector: str | None,
    sector_map: dict[str, str],
) -> str:
    if cand_sector:
        return cand_sector
    return sector_map.get(ticker.upper(), "Unclassified")


def would_breach_sector_cap(
    new_ticker: str,
    new_sector: str,
    new_notional: float,
    current_exposures: dict[str, float],
    account_equity: float,
    cap_pct: float,
) -> bool:
    if account_equity <= 0:
        return True
    projected = current_exposures.get(new_sector, 0.0) + new_notional
    projected_pct = projected / account_equity * 100
    return projected_pct > cap_pct


# ---------- Execution ----------


def submit_via_executor(cand: dict[str, Any], qty: int, output_dir: Path) -> dict[str, Any]:
    today = dt.date.today().isoformat()
    signal_id = _signal_id(cand["ticker"], today, cand["primary_screener"])
    order_out = output_dir / "orders" / f"{cand['ticker']}_{today}_{signal_id}.json"
    order_out.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        str(EXECUTE_TRADE),
        "--ticker",
        cand["ticker"],
        "--side",
        cand["side"],
        "--quantity",
        str(qty),
        "--entry-type",
        cand.get("entry_type", "market"),
        "--entry-price",
        str(cand["entry_price"]),
        "--stop-loss",
        str(cand["stop_loss"]),
        "--target",
        str(cand["target"]),
        "--signal-id",
        signal_id,
        "--output",
        str(order_out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

    result: dict[str, Any] = {
        "returncode": r.returncode,
        "order_file": str(order_out),
    }
    if order_out.exists():
        try:
            result["order"] = json.loads(order_out.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return result


# ---------- Lock ----------


class FileLock:
    def __init__(self, path: Path):
        self.path = path

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                age = time.time() - self.path.stat().st_mtime
                if age < 600:  # 10 min stale threshold
                    raise RuntimeError(
                        f"lock held at {self.path} (age {age:.0f}s) - another loop running?"
                    )
            except FileNotFoundError:
                pass
        self.path.write_text(f"{os.getpid()}\n{_utcnow()}\n")
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


# ---------- Main ----------


def run_iteration(args: argparse.Namespace) -> dict[str, Any]:
    cfg = load_yaml(args.config)
    weights = load_yaml(args.weights) if args.weights.exists() else {"screeners": {}}
    profile = cfg["profiles"][cfg["active_profile"]]
    sector_map = load_sector_map(args.sector_map)
    output_dir = args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    iteration: dict[str, Any] = {
        "iteration_id": f"loop_{_utcnow()}",
        "mode": args.mode,
        "started_at": _utcnow(),
        "profile": cfg["active_profile"],
        "decisions": [],
    }
    t0 = time.time()

    # Gate 1: trading window
    in_window, win_reason = in_trading_window(cfg)
    iteration["trading_window"] = {"inside": in_window, "detail": win_reason}
    if not in_window:
        iteration["status"] = "blocked_window"
        iteration["reason"] = win_reason
        return iteration

    # Gate 2: kill-switch
    ks_status_path = REPO_ROOT / "state" / "kill_switch_status.json"
    ks = run_killswitch_check(ks_status_path)
    iteration["kill_switch"] = {
        "status": ks.get("status"),
        "reason": ks.get("reason"),
        "source": str(ks_status_path),
    }
    if ks.get("status") not in ("OK", "WARN"):
        iteration["status"] = "blocked_killswitch"
        iteration["reason"] = ks.get("reason", "kill switch not OK")
        return iteration

    # Gate 3: macro
    macro = latest_macro_snapshot()
    regime = macro.get("regime")
    risk_on = float(macro.get("risk_on_score", 50))
    exposure_scale = float(macro.get("exposure_scale", 0.5))
    macro_min = float(cfg.get("global", {}).get("macro_min_risk_on", 35))
    iteration["macro"] = {
        "regime": regime,
        "risk_on_score": risk_on,
        "exposure_scale": exposure_scale,
        "fallback": macro.get("_fallback", False),
        "stale": macro.get("_stale", False),
        "source": macro.get("_source"),
    }
    if risk_on < macro_min:
        iteration["status"] = "blocked_macro"
        iteration["reason"] = f"risk_on {risk_on} < min {macro_min}"
        return iteration

    # Current positions (from kill-switch snapshot - avoids a second API call)
    current_positions = ks.get("positions", {}).get("symbols", [])
    current_count = ks.get("positions", {}).get("count", 0)
    current_equity = float(ks.get("account", {}).get("equity", profile["account_size_usd"]))

    max_positions = int(profile["max_positions"])
    allowed_total = int(math.floor(max_positions * exposure_scale))
    entries_allowed = max(allowed_total - current_count, 0)
    iteration["entry_budget"] = {
        "max_positions": max_positions,
        "exposure_scale": exposure_scale,
        "allowed_total": allowed_total,
        "current_count": current_count,
        "entries_allowed_this_loop": entries_allowed,
    }

    # Gate 4: already at cap
    if entries_allowed == 0:
        iteration["status"] = "no_budget"
        iteration["reason"] = f"current {current_count} >= allowed {allowed_total}"
        return iteration

    # Screener adapter fan-out
    enabled = list((weights.get("screeners") or {}).keys()) or None
    candidates = load_all_candidates(args.reports_dir, enabled_screeners=enabled)
    iteration["candidates_loaded"] = len(candidates)

    # Drop candidates for tickers we already hold
    candidates = [c for c in candidates if c["ticker"] not in current_positions]
    iteration["candidates_after_holdings_filter"] = len(candidates)

    # Rank + dedupe + regime gate
    ranked = rank_and_dedupe(candidates, weights, regime=regime, risk_on_score=risk_on)
    iteration["candidates_after_rank"] = len(ranked)

    # Pre-compute current sector exposures (from kill-switch detailed checks
    # if available; else zero)
    sector_exposures: dict[str, float] = defaultdict(float)
    for check in ks.get("checks", []):
        if check.get("type") == "sector_exposure" and "exposures_pct" in check:
            for s, pct in check["exposures_pct"].items():
                sector_exposures[s] = pct / 100.0 * current_equity
            break

    # Evaluate each candidate top-down until budget exhausted
    submitted = 0
    for cand in ranked:
        if submitted >= entries_allowed:
            iteration["decisions"].append(
                {
                    "ticker": cand["ticker"],
                    "action": "skip_budget_exhausted",
                    "composite_score": cand.get("composite_score"),
                }
            )
            continue

        ticker = cand["ticker"]
        sector = sector_of(ticker, cand.get("sector"), sector_map)

        # Sector cap check
        qty_est, sz_detail = size_position(
            cand["entry_price"], cand["stop_loss"], profile, exposure_scale
        )
        if qty_est == 0:
            iteration["decisions"].append(
                {
                    "ticker": ticker,
                    "action": "skip_sizing",
                    **sz_detail,
                    "composite_score": cand.get("composite_score"),
                }
            )
            continue

        notional = qty_est * cand["entry_price"]
        if would_breach_sector_cap(
            ticker,
            sector,
            notional,
            sector_exposures,
            current_equity,
            profile["max_sector_exposure_pct"],
        ):
            iteration["decisions"].append(
                {
                    "ticker": ticker,
                    "action": "skip_sector_cap",
                    "sector": sector,
                    "composite_score": cand.get("composite_score"),
                }
            )
            continue

        # Submit
        if args.mode == "plan":
            iteration["decisions"].append(
                {
                    "ticker": ticker,
                    "action": "plan_submit",
                    "side": cand["side"],
                    "quantity": qty_est,
                    "entry_type": cand.get("entry_type"),
                    "entry_price": cand["entry_price"],
                    "stop_loss": cand["stop_loss"],
                    "target": cand["target"],
                    "sector": sector,
                    "primary_screener": cand["primary_screener"],
                    "supporting_screeners": cand.get("supporting_screeners", []),
                    "composite_score": cand.get("composite_score"),
                    "sizing": sz_detail,
                }
            )
        else:
            result = submit_via_executor(cand, qty_est, output_dir)
            order_body = result.get("order") or {}
            iteration["decisions"].append(
                {
                    "ticker": ticker,
                    "action": "submit" if result["returncode"] == 0 else "submit_failed",
                    "returncode": result["returncode"],
                    "order_status": order_body.get("status"),
                    "alpaca_order_id": order_body.get("alpaca_order_id"),
                    "client_order_id": order_body.get("client_order_id"),
                    "order_file": result.get("order_file"),
                    "composite_score": cand.get("composite_score"),
                    "quantity": qty_est,
                    "sector": sector,
                }
            )
            if result["returncode"] != 0:
                continue

        # Reserve budget + sector exposure (assume fill at estimate)
        submitted += 1
        sector_exposures[sector] += notional

    iteration["submitted_count"] = submitted
    iteration["status"] = "executed" if args.mode == "execute" else "planned"
    iteration["duration_ms"] = int((time.time() - t0) * 1000)
    return iteration


def write_iteration_audit(iteration: dict[str, Any], output_dir: Path) -> Path:
    safe_status = iteration.get("status", "unknown")
    fname = f"iter_{iteration['iteration_id']}_{safe_status}.json".replace(":", "-")
    path = output_dir / fname
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(iteration, indent=2, default=str))
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["plan", "execute"], default="plan")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    ap.add_argument("--sector-map", type=Path, default=DEFAULT_SECTOR_MAP)
    ap.add_argument("--reports-dir", type=Path, default=REPORTS_DIR)
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "state" / "loop")
    ap.add_argument("--lock", type=Path, default=REPO_ROOT / "state" / "loop" / ".lock")
    args = ap.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    try:
        with FileLock(args.lock):
            iteration = run_iteration(args)
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    audit_path = write_iteration_audit(iteration, args.output)
    status = iteration.get("status", "unknown")
    print(
        f"[{status}] submitted={iteration.get('submitted_count', 0)} audit={audit_path}",
        file=sys.stderr,
    )

    if status.startswith("blocked"):
        return 2
    fails = [d for d in iteration.get("decisions", []) if d.get("action") == "submit_failed"]
    if fails:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
