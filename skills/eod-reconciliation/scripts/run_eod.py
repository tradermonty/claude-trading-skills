#!/usr/bin/env python3
"""End-of-day reconciliation: loop decisions -> Alpaca fills -> attribution.

Runs at 16:30 ET via launchd. Produces both a JSON state file and a human
markdown report under `reports/eod/`. Closes matched theses and shells out to
trader-memory-core for postmortems.

Usage:
    python3 run_eod.py --output-dir reports/eod/
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
from zoneinfo import ZoneInfo

try:
    import requests
except ImportError:
    print(
        "error: requests not installed. Run: pip3 install --break-system-packages requests",
        file=sys.stderr,
    )
    sys.exit(3)


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_STATE_LOOP = REPO_ROOT / "state" / "loop"
DEFAULT_STATE_DIR = REPO_ROOT / "state"
DEFAULT_THESES_DIR = REPO_ROOT / "state" / "theses"
DEFAULT_OUTPUT = REPO_ROOT / "reports" / "eod"
THESIS_REVIEW = REPO_ROOT / "skills" / "trader-memory-core" / "scripts" / "thesis_review.py"

ALPACA_PAPER_BASE = "https://paper-api.alpaca.markets"
ALPACA_LIVE_BASE = "https://api.alpaca.markets"

ET = ZoneInfo("America/New_York")


# ---------- Alpaca helpers ----------


def _headers() -> dict[str, str]:
    return {
        "APCA-API-KEY-ID": os.environ.get("ALPACA_API_KEY", ""),
        "APCA-API-SECRET-KEY": os.environ.get("ALPACA_SECRET_KEY", ""),
    }


def _base() -> str:
    paper = os.environ.get("ALPACA_PAPER", "true").lower() == "true"
    return ALPACA_PAPER_BASE if paper else ALPACA_LIVE_BASE


def fetch_alpaca_orders(after_iso: str, timeout: int = 30) -> list[dict[str, Any]]:
    """Fetch ALL orders (status=all) placed after `after_iso`.

    after_iso should be ISO8601 (e.g. "2026-04-21T13:30:00Z"). Alpaca returns
    up to 500 by default; we paginate with the `until` parameter if needed.
    """
    url = f"{_base()}/v2/orders"
    params = {
        "status": "all",
        "after": after_iso,
        "limit": 500,
        "direction": "asc",
        "nested": "true",
    }
    r = requests.get(url, headers=_headers(), params=params, timeout=timeout)
    r.raise_for_status()
    return r.json() or []


def fetch_alpaca_account(timeout: int = 15) -> dict[str, Any]:
    r = requests.get(f"{_base()}/v2/account", headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_alpaca_positions(timeout: int = 15) -> list[dict[str, Any]]:
    r = requests.get(f"{_base()}/v2/positions", headers=_headers(), timeout=timeout)
    r.raise_for_status()
    return r.json() or []


# ---------- Iteration loading ----------


def list_iteration_audits(state_loop_dir: Path, target_date: dt.date) -> list[Path]:
    """Return paths of iter_*.json files whose iteration_id falls on target_date."""
    if not state_loop_dir.exists():
        return []
    prefix = f"iter_loop_{target_date.isoformat()}"
    return sorted(state_loop_dir.glob(f"{prefix}*.json"))


def load_iteration_decisions(paths: list[Path]) -> list[dict[str, Any]]:
    """Read each iteration JSON and flatten all decision dicts with iteration metadata."""
    flat: list[dict[str, Any]] = []
    for p in paths:
        try:
            data = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        iter_meta = {
            "iteration_id": data.get("iteration_id"),
            "started_at": data.get("started_at"),
        }
        for d in data.get("decisions") or []:
            rec = {**iter_meta, **d}
            flat.append(rec)
    return flat


def extract_submit_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only decisions that actually hit the executor (submit or submit_failed)."""
    actions = {"submit", "submit_failed"}
    return [d for d in decisions if d.get("action") in actions]


# ---------- Matching + classification ----------


def classify_order(order: dict[str, Any]) -> str:
    """Map Alpaca order status to EOD bucket."""
    status = (order.get("status") or "").lower()
    filled_qty = float(order.get("filled_qty") or 0)
    qty = float(order.get("qty") or 0)

    if status == "filled":
        return "filled"
    if status == "partially_filled":
        return "partial"
    if filled_qty > 0 and qty > filled_qty and status in ("canceled", "expired"):
        return "partial"
    if status == "canceled":
        return "canceled"
    if status == "expired":
        return "expired"
    if status == "rejected":
        return "rejected"
    if status in ("new", "accepted", "pending_new", "pending_cancel"):
        return "pending"
    return status or "unknown"


def compute_slippage(intended_entry: float, fill_price: float | None, side: str) -> float | None:
    """Signed slippage in dollars per share.

    Positive = price moved against us at entry (worse fill):
      - buy:  fill > intended -> positive (paid more)
      - sell: intended > fill -> positive (received less)
    """
    if fill_price is None or intended_entry is None:
        return None
    try:
        fp = float(fill_price)
        ie = float(intended_entry)
    except (TypeError, ValueError):
        return None
    if side == "sell":
        return round(ie - fp, 4)
    return round(fp - ie, 4)


def match_decisions_to_orders(
    decisions: list[dict[str, Any]],
    orders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Join submit decisions with Alpaca orders by client_order_id.

    Returns a list of match dicts with keys:
      decision, order, classification, slippage_per_share, filled_avg_price,
      filled_qty, unmatched (bool if no Alpaca order found).
    """
    by_coid: dict[str, dict[str, Any]] = {}
    for o in orders:
        coid = o.get("client_order_id")
        if coid:
            by_coid[coid] = o

    matches: list[dict[str, Any]] = []
    for d in decisions:
        coid = d.get("client_order_id")
        order = by_coid.get(coid) if coid else None
        if order is None:
            matches.append(
                {
                    "decision": d,
                    "order": None,
                    "classification": "unmatched",
                    "unmatched": True,
                    "filled_avg_price": None,
                    "filled_qty": 0,
                    "slippage_per_share": None,
                }
            )
            continue

        classification = classify_order(order)
        avg = order.get("filled_avg_price")
        filled_qty = float(order.get("filled_qty") or 0)
        fill_px = float(avg) if avg not in (None, "") else None
        slip = compute_slippage(
            intended_entry=float(d.get("entry_price") or 0) or None,
            fill_price=fill_px,
            side=d.get("side") or order.get("side") or "buy",
        )
        matches.append(
            {
                "decision": d,
                "order": {
                    "id": order.get("id"),
                    "client_order_id": coid,
                    "status": order.get("status"),
                    "side": order.get("side"),
                    "qty": order.get("qty"),
                    "filled_qty": order.get("filled_qty"),
                    "filled_avg_price": avg,
                    "submitted_at": order.get("submitted_at"),
                    "filled_at": order.get("filled_at"),
                    "canceled_at": order.get("canceled_at"),
                },
                "classification": classification,
                "unmatched": False,
                "filled_avg_price": fill_px,
                "filled_qty": filled_qty,
                "slippage_per_share": slip,
            }
        )
    return matches


def classification_counts(matches: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for m in matches:
        counts[m["classification"]] += 1
    return dict(counts)


# ---------- Attribution ----------


def compute_attribution(
    matches: list[dict[str, Any]],
    closed_theses: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Group by primary_screener: submits, fills, realized P&L, open positions."""
    by: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "submits": 0,
            "fills": 0,
            "partials": 0,
            "rejects": 0,
            "realized_pnl_usd": 0.0,
            "open_positions": 0,
        }
    )
    for m in matches:
        d = m["decision"]
        screener = d.get("primary_screener") or "unknown"
        bucket = by[screener]
        bucket["submits"] += 1
        cls = m["classification"]
        if cls == "filled":
            bucket["fills"] += 1
            bucket["open_positions"] += 1
        elif cls == "partial":
            bucket["partials"] += 1
            bucket["open_positions"] += 1
        elif cls in ("rejected", "canceled", "expired"):
            bucket["rejects"] += 1

    for c in closed_theses:
        screener = c.get("primary_screener") or "unknown"
        bucket = by[screener]
        # Realized from the exit we booked today
        bucket["realized_pnl_usd"] += float(c.get("realized_pnl_usd") or 0.0)
        # Any still-open positions for this screener
        bucket["open_positions"] = max(bucket["open_positions"] - 1, 0)
    # round
    for v in by.values():
        v["realized_pnl_usd"] = round(v["realized_pnl_usd"], 2)
    return dict(by)


# ---------- Closed-position detection via theses ----------


def detect_closed_positions(
    theses_dir: Path,
    sod_tickers: set[str],
    current_positions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find ACTIVE theses whose ticker we no longer hold -> close candidates.

    Returns placeholders with ticker/thesis_id. Full close happens later via
    close_thesis_and_postmortem(), which needs the exit price/reason.
    """
    if not theses_dir.exists():
        return []

    # Import thesis_store lazily so tests can run without PyYAML-backed theses
    sys.path.insert(0, str(THESIS_REVIEW.parent))
    try:
        import thesis_store  # type: ignore
    except Exception:
        return []

    held_now = {p.get("symbol", "").upper() for p in current_positions}
    active = thesis_store.list_active(theses_dir)

    closed: list[dict[str, Any]] = []
    for idx_entry in active:
        tkr = idx_entry.get("ticker", "").upper()
        if tkr and tkr not in held_now:
            closed.append(
                {
                    "ticker": tkr,
                    "thesis_id": idx_entry.get("thesis_id"),
                    "thesis_type": idx_entry.get("thesis_type"),
                    "primary_screener": idx_entry.get("source_screener"),
                }
            )
    return closed


def close_thesis_and_postmortem(
    thesis_id: str,
    ticker: str,
    exit_price: float,
    exit_date_iso: str,
    exit_reason: str,
    theses_dir: Path,
    journal_dir: Path | None = None,
) -> dict[str, Any]:
    """Close a thesis in-place, then generate a postmortem via subprocess.

    Returns a dict with thesis_id, realized_pnl_usd, postmortem_path, errors.
    """
    result: dict[str, Any] = {
        "thesis_id": thesis_id,
        "ticker": ticker,
        "realized_pnl_usd": None,
        "r_multiple": None,
        "postmortem_path": None,
        "errors": [],
    }

    sys.path.insert(0, str(THESIS_REVIEW.parent))
    try:
        import thesis_store  # type: ignore
    except Exception as e:
        result["errors"].append(f"import thesis_store: {e}")
        return result

    try:
        closed = thesis_store.close(
            state_dir=theses_dir,
            thesis_id=thesis_id,
            exit_reason=exit_reason,
            actual_price=exit_price,
            actual_date=exit_date_iso,
        )
        result["realized_pnl_usd"] = closed.get("outcome", {}).get("pnl_dollars")
        # r_multiple = pnl_per_share / initial_risk_per_share
        pos = closed.get("position") or {}
        risk_dollars = pos.get("risk_dollars")
        pnl = closed.get("outcome", {}).get("pnl_dollars")
        if risk_dollars and pnl is not None and risk_dollars > 0:
            result["r_multiple"] = round(pnl / risk_dollars, 2)
    except Exception as e:
        result["errors"].append(f"close: {e}")
        return result

    # Postmortem via subprocess (fresh interpreter so optional deps load clean)
    cmd = [
        sys.executable,
        str(THESIS_REVIEW),
        "--state-dir",
        str(theses_dir),
        "postmortem",
        thesis_id,
    ]
    if journal_dir:
        cmd.extend(["--journal-dir", str(journal_dir)])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            # Path is in stdout: "Postmortem generated: <path>"
            for line in r.stdout.splitlines():
                if "generated:" in line:
                    result["postmortem_path"] = line.split("generated:", 1)[1].strip()
                    break
        else:
            result["errors"].append(f"postmortem rc={r.returncode}: {r.stderr.strip()[:200]}")
    except subprocess.TimeoutExpired:
        result["errors"].append("postmortem timeout")
    return result


# ---------- SOD snapshot ----------


def load_sod_snapshot(state_dir: Path, target_date: dt.date) -> dict[str, Any] | None:
    path = state_dir / f"sod_{target_date.isoformat()}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


# ---------- Report rendering ----------


def render_markdown(payload: dict[str, Any]) -> str:
    date = payload["date"]
    pnl = payload.get("day_pnl_usd", 0.0)
    pnl_pct = payload.get("day_pnl_pct", 0.0)
    fills = payload.get("fills", {})
    by_strat = payload.get("by_strategy", {})
    closed = payload.get("closed_positions", [])
    warnings = payload.get("warnings", [])

    lines = [
        f"# End-of-Day Reconciliation — {date}",
        "",
        f"**Start-of-day equity:** ${payload.get('sod_equity', 0):,.2f}",
        f"**End-of-day equity:** ${payload.get('eod_equity', 0):,.2f}",
        f"**Day P&L:** ${pnl:,.2f} ({pnl_pct:+.2f}%)",
        "",
        "## Loop Activity",
        "",
        f"- Iterations run: {payload.get('iterations_count', 0)}",
        f"- Submits attempted: {payload.get('submits_attempted', 0)}",
        f"- Open positions EOD: {payload.get('open_positions', 0)}",
        "",
        "## Fills",
        "",
        "| Classification | Count |",
        "|---|---|",
    ]
    for k in ("filled", "partial", "canceled", "expired", "rejected", "pending", "unmatched"):
        if k in fills:
            lines.append(f"| {k} | {fills[k]} |")
    lines += [
        "",
        "## Strategy Attribution",
        "",
        "| Screener | Submits | Fills | Realized P&L | Open |",
        "|---|---|---|---|---|",
    ]
    for screener, stats in sorted(by_strat.items()):
        lines.append(
            f"| {screener} | {stats['submits']} | {stats['fills']} | "
            f"${stats['realized_pnl_usd']:,.2f} | {stats['open_positions']} |"
        )
    if closed:
        lines += [
            "",
            "## Closed Positions",
            "",
            "| Ticker | Thesis | Realized P&L | R | Postmortem |",
            "|---|---|---|---|---|",
        ]
        for c in closed:
            pnl_s = (
                f"${c['realized_pnl_usd']:,.2f}" if c.get("realized_pnl_usd") is not None else "—"
            )
            r_s = f"{c['r_multiple']}R" if c.get("r_multiple") is not None else "—"
            pm = c.get("postmortem_path") or "—"
            lines.append(
                f"| {c.get('ticker', '—')} | {c.get('thesis_id', '—')} | {pnl_s} | {r_s} | {pm} |"
            )
    if warnings:
        lines += ["", "## Warnings", ""]
        for w in warnings:
            lines.append(f"- {w}")
    return "\n".join(lines) + "\n"


# ---------- Orchestration ----------


def run_reconciliation(args: argparse.Namespace) -> dict[str, Any]:
    today = args.date or dt.datetime.now(ET).date()
    warnings: list[str] = []

    # 1. Iteration audits
    iter_paths = list_iteration_audits(args.state_loop, today)
    decisions_all = load_iteration_decisions(iter_paths)
    submit_decisions = extract_submit_decisions(decisions_all)

    # 2. Alpaca state
    try:
        account = fetch_alpaca_account()
    except Exception as e:
        account = {}
        warnings.append(f"account fetch failed: {e}")
    try:
        positions = fetch_alpaca_positions()
    except Exception as e:
        positions = []
        warnings.append(f"positions fetch failed: {e}")

    # 3. Orders since SOD
    sod_iso = f"{today.isoformat()}T00:00:00Z"
    try:
        orders = fetch_alpaca_orders(sod_iso)
    except Exception as e:
        orders = []
        warnings.append(f"orders fetch failed: {e}")

    # 4. SOD snapshot
    sod = load_sod_snapshot(args.state_dir, today)
    sod_equity = float((sod or {}).get("equity", 0)) or None
    eod_equity = float(account.get("equity") or 0)

    # 5. Match decisions to fills
    matches = match_decisions_to_orders(submit_decisions, orders)

    # 6. Detect closed positions via thesis store
    sod_tickers: set[str] = set()  # (not required for current simple logic)
    closed_candidates = detect_closed_positions(args.theses_dir, sod_tickers, positions)

    # 7. Close each thesis and run postmortem (exit price = last trade if we can)
    # Find exit fills (sell orders that filled today for that ticker)
    sell_fills_by_ticker: dict[str, dict[str, Any]] = {}
    for o in orders:
        if (o.get("side") or "").lower() == "sell" and classify_order(o) in ("filled", "partial"):
            sym = (o.get("symbol") or "").upper()
            sell_fills_by_ticker.setdefault(sym, o)  # first match wins (chronological order)

    closed_positions: list[dict[str, Any]] = []
    if not args.skip_postmortems:
        for c in closed_candidates:
            sell = sell_fills_by_ticker.get(c["ticker"])
            if sell is None:
                warnings.append(
                    f"{c['ticker']}: active thesis {c['thesis_id']} has no "
                    "holding but no sell fill found today — skipping close"
                )
                continue
            exit_price = float(sell.get("filled_avg_price") or 0)
            exit_date = sell.get("filled_at") or f"{today.isoformat()}T20:00:00+00:00"
            result = close_thesis_and_postmortem(
                thesis_id=c["thesis_id"],
                ticker=c["ticker"],
                exit_price=exit_price,
                exit_date_iso=exit_date,
                exit_reason="manual",
                theses_dir=args.theses_dir,
            )
            result["primary_screener"] = c.get("primary_screener")
            closed_positions.append(result)

    # 8. Attribution
    attribution = compute_attribution(matches, closed_positions)

    day_pnl_usd = None
    day_pnl_pct = None
    if sod_equity:
        day_pnl_usd = round(eod_equity - sod_equity, 2)
        day_pnl_pct = round((day_pnl_usd / sod_equity) * 100, 3)
    else:
        warnings.append("no SOD snapshot — P&L incomplete")

    payload: dict[str, Any] = {
        "date": today.isoformat(),
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "sod_equity": sod_equity,
        "eod_equity": eod_equity,
        "day_pnl_usd": day_pnl_usd,
        "day_pnl_pct": day_pnl_pct,
        "iterations_count": len(iter_paths),
        "submits_attempted": len(submit_decisions),
        "fills": classification_counts(matches),
        "matches": matches,
        "by_strategy": attribution,
        "closed_positions": closed_positions,
        "open_positions": len(positions),
        "warnings": warnings,
    }
    return payload


def write_reports(payload: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    date = payload["date"]
    md_path = output_dir / f"eod_{date}.md"
    json_path = output_dir / f"eod_{date}.json"
    # Strip heavy "matches" list from markdown-friendly payload? Keep it in JSON.
    md_path.write_text(render_markdown(payload))
    json_path.write_text(json.dumps(payload, indent=2, default=str))
    return md_path, json_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--state-loop",
        type=Path,
        default=DEFAULT_STATE_LOOP,
        help="Directory containing iter_*.json iteration audits",
    )
    ap.add_argument(
        "--state-dir", type=Path, default=DEFAULT_STATE_DIR, help="State root containing sod_*.json"
    )
    ap.add_argument("--theses-dir", type=Path, default=DEFAULT_THESES_DIR)
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument(
        "--date",
        type=lambda s: dt.date.fromisoformat(s),
        default=None,
        help="YYYY-MM-DD override (default: today ET)",
    )
    ap.add_argument("--skip-postmortems", action="store_true")
    args = ap.parse_args()

    payload = run_reconciliation(args)
    md_path, json_path = write_reports(payload, args.output_dir)

    pnl = payload.get("day_pnl_usd")
    pnl_s = f"${pnl:,.2f}" if pnl is not None else "unknown"
    print(
        f"EOD done: date={payload['date']} pnl={pnl_s} fills={payload.get('fills')} md={md_path}",
        file=sys.stderr,
    )

    return 1 if payload.get("warnings") else 0


if __name__ == "__main__":
    sys.exit(main())
