#!/usr/bin/env python3
"""Submit a single bracket order to Alpaca with all safety checks.

Usage:
    python3 execute_trade.py \
      --ticker AAPL --side buy --quantity 50 \
      --entry-type market --stop-loss 145.00 --target 165.00 \
      --signal-id vcp-2026-04-21-aapl \
      --output reports/orders/aapl_2026-04-21.json

Exit codes:
    0 - submitted (or dry-run-acknowledged) successfully
    1 - refused (safety violation)
    2 - Alpaca API error
    3 - config / environment error
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    import requests
    import yaml
except ImportError as e:
    print(f"error: {e}. Run: pip3 install --break-system-packages requests pyyaml", file=sys.stderr)
    sys.exit(3)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = REPO_ROOT / "config" / "trading_params.yaml"
DEFAULT_CHECKLIST = REPO_ROOT / "LIVE_TRADING_CHECKLIST.md"

ALPACA_PAPER_BASE = "https://paper-api.alpaca.markets"
ALPACA_LIVE_BASE = "https://api.alpaca.markets"


def _err(msg: str) -> None:
    print(f"REFUSED: {msg}", file=sys.stderr)


def load_config(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f)


def get_active_profile(cfg: dict[str, Any]) -> dict[str, Any]:
    name = cfg["active_profile"]
    return cfg["profiles"][name]


def checklist_signed(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text().lower()
    return "signed: true" in text


def compute_client_order_id(ticker: str, signal_id: str, day: str) -> str:
    raw = f"{ticker}|{signal_id}|{day}".encode()
    return "ace_" + hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:24]


def validate_order(
    ticker: str,
    side: str,
    quantity: int,
    entry_price: float,
    stop_loss: float,
    target: float,
    cfg: dict[str, Any],
) -> tuple[bool, str]:
    """Return (ok, reason). reason is empty on success."""
    g = cfg.get("global", {})
    p = get_active_profile(cfg)

    if side not in ("buy", "sell"):
        return False, f"side must be buy or sell, got {side}"
    if quantity <= 0:
        return False, f"quantity must be positive, got {quantity}"
    if entry_price <= 0:
        return False, "entry_price must be positive"
    if stop_loss <= 0 or target <= 0:
        return False, "stop_loss and target are mandatory and must be positive"

    # Direction sanity
    if side == "buy":
        if stop_loss >= entry_price:
            return False, f"buy: stop_loss {stop_loss} must be < entry_price {entry_price}"
        if target <= entry_price:
            return False, f"buy: target {target} must be > entry_price {entry_price}"
    else:  # sell short
        if stop_loss <= entry_price:
            return False, f"sell: stop_loss {stop_loss} must be > entry_price {entry_price}"
        if target >= entry_price:
            return False, f"sell: target {target} must be < entry_price {entry_price}"

    # Stop too close (Alpaca min)
    stop_pct = abs(entry_price - stop_loss) / entry_price
    if stop_pct < 0.01:
        return False, f"stop_loss too close (<1%): {stop_pct:.3%}"

    # Risk per trade check
    risk_per_share = abs(entry_price - stop_loss)
    notional_risk = risk_per_share * quantity
    max_risk = p["account_size_usd"] * p["risk_per_trade_pct"] / 100
    if notional_risk > max_risk * 1.001:  # tiny epsilon
        return False, (
            f"risk ${notional_risk:.0f} exceeds max ${max_risk:.0f} "
            f"(account ${p['account_size_usd']} * {p['risk_per_trade_pct']}%)"
        )

    # Position size check
    notional = quantity * entry_price
    max_notional = p["account_size_usd"] * p["max_position_size_pct"] / 100
    if notional > max_notional * 1.001:
        return False, (
            f"notional ${notional:.0f} exceeds max ${max_notional:.0f} "
            f"({p['max_position_size_pct']}% of account)"
        )

    # Min position size
    if notional < p.get("min_position_size_usd", 0):
        return False, f"notional ${notional:.0f} below min ${p['min_position_size_usd']}"

    # R/R check
    reward = abs(target - entry_price)
    if risk_per_share > 0:
        rr = reward / risk_per_share
        min_rr = g.get("min_rr_ratio", 1.5)
        if rr < min_rr:
            return False, f"R/R {rr:.2f} below minimum {min_rr}"

    return True, ""


def safety_gate(cfg: dict[str, Any]) -> tuple[bool, str]:
    """System-level guards before any order can fly."""
    g = cfg.get("global", {})
    mode = g.get("mode", "paper")
    paper_env = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

    if mode == "live" and paper_env:
        return False, "config mode=live but ALPACA_PAPER=true (env). Refusing."
    if mode == "paper" and not paper_env:
        return False, "config mode=paper but ALPACA_PAPER=false (env). Refusing."

    if mode == "live":
        cl_path = Path(os.environ.get("LIVE_TRADING_CHECKLIST_PATH", str(DEFAULT_CHECKLIST)))
        if not cl_path.is_absolute():
            cl_path = REPO_ROOT / cl_path
        if not checklist_signed(cl_path):
            return False, f"live mode requires signed checklist at {cl_path}"

    return True, ""


def submit_alpaca_order(
    ticker: str,
    side: str,
    quantity: int,
    entry_type: str,
    stop_loss: float,
    target: float,
    client_order_id: str,
    paper: bool,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    """POST a bracket order to Alpaca. Returns the response JSON."""
    api_key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret:
        raise RuntimeError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set")

    base = ALPACA_PAPER_BASE if paper else ALPACA_LIVE_BASE
    url = f"{base}/v2/orders"

    body = {
        "symbol": ticker.upper(),
        "qty": quantity,
        "side": side,
        "type": entry_type,
        "time_in_force": "day",
        "client_order_id": client_order_id,
        "order_class": "bracket",
        "stop_loss": {"stop_price": stop_loss},
        "take_profit": {"limit_price": target},
    }

    headers = {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }

    for attempt in range(3):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=timeout_seconds)
            if r.status_code in (200, 201):
                return r.json()
            if r.status_code in (409, 422):  # idempotent dup or validation
                return {
                    "status": "duplicate_or_invalid",
                    "http_status": r.status_code,
                    "body": r.text[:500],
                }
            if r.status_code >= 500:
                time.sleep(1 + attempt)
                continue
            raise RuntimeError(f"Alpaca {r.status_code}: {r.text[:500]}")
        except requests.RequestException as e:
            if attempt == 2:
                raise RuntimeError(f"Network error: {e}") from e
            time.sleep(1 + attempt)
    raise RuntimeError("Exhausted retries")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--side", required=True, choices=["buy", "sell"])
    ap.add_argument("--quantity", type=int, required=True)
    ap.add_argument("--entry-type", default="market", choices=["market", "limit"])
    ap.add_argument(
        "--entry-price",
        type=float,
        default=0.0,
        help="Required for limit orders. For market orders, validation uses this as estimate.",
    )
    ap.add_argument("--stop-loss", type=float, required=True)
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--signal-id", required=True, help="Stable id for idempotency")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument(
        "--force", action="store_true", help="Skip safety gate (use ONLY for paper-replay-harness)"
    )
    args = ap.parse_args()

    cfg = load_config(args.config)

    # Estimate entry price for validation if not provided. Pull from Alpaca's last quote.
    entry_price = args.entry_price
    if entry_price <= 0 and args.entry_type == "market":
        # Best-effort: use stop and target to back-estimate (or fall back to midpoint)
        entry_price = (args.stop_loss + args.target) / 2

    # Validate the trade structure
    ok, reason = validate_order(
        args.ticker, args.side, args.quantity, entry_price, args.stop_loss, args.target, cfg
    )
    if not ok:
        _err(reason)
        out = {
            "submitted_at": dt.datetime.utcnow().isoformat() + "Z",
            "ticker": args.ticker,
            "status": "refused",
            "reason": reason,
            "would_have_sent": vars(args),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, indent=2, default=str))
        return 1

    # Safety gate (env + checklist)
    if not args.force:
        ok, reason = safety_gate(cfg)
        if not ok:
            _err(reason)
            out = {
                "submitted_at": dt.datetime.utcnow().isoformat() + "Z",
                "ticker": args.ticker,
                "status": "refused",
                "reason": reason,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(out, indent=2, default=str))
            return 1

    today = dt.date.today().isoformat()
    coid = compute_client_order_id(args.ticker, args.signal_id, today)

    dry_run = os.environ.get("TRADE_LOOP_DRY_RUN", "true").lower() == "true"
    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"

    if dry_run:
        out = {
            "submitted_at": dt.datetime.utcnow().isoformat() + "Z",
            "ticker": args.ticker,
            "side": args.side,
            "quantity": args.quantity,
            "client_order_id": coid,
            "alpaca_order_id": None,
            "status": "dry_run_acknowledged",
            "entry_type": args.entry_type,
            "stop_loss": args.stop_loss,
            "target": args.target,
            "dry_run": True,
            "paper": paper,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, indent=2))
        print(
            f"DRY_RUN ack: {args.ticker} {args.side} {args.quantity} (coid={coid})", file=sys.stderr
        )
        return 0

    # Live submission
    try:
        resp = submit_alpaca_order(
            args.ticker,
            args.side,
            args.quantity,
            args.entry_type,
            args.stop_loss,
            args.target,
            coid,
            paper,
        )
    except Exception as e:
        out = {
            "submitted_at": dt.datetime.utcnow().isoformat() + "Z",
            "ticker": args.ticker,
            "status": "api_error",
            "reason": str(e),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, indent=2))
        print(f"API ERROR: {e}", file=sys.stderr)
        return 2

    out = {
        "submitted_at": dt.datetime.utcnow().isoformat() + "Z",
        "ticker": args.ticker,
        "side": args.side,
        "quantity": args.quantity,
        "client_order_id": coid,
        "alpaca_order_id": resp.get("id"),
        "status": resp.get("status", "unknown"),
        "entry_type": args.entry_type,
        "stop_loss": args.stop_loss,
        "target": args.target,
        "dry_run": False,
        "paper": paper,
        "alpaca_response": resp,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, indent=2))
    print(
        f"Submitted: {args.ticker} {args.side} {args.quantity} alpaca_id={resp.get('id')}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
