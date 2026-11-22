#!/usr/bin/env python3
"""Monitor one or more Stocks-With-Josh leaderboard traders and report trades new since the
last run.

For each target it fetches
https://leaderboard.stockswithjosh.com/api/leaderboard/traders/<id>?period=<p>, diffs the
returned trades against a small per-target state file, and reports the new signals (plus any
positions that closed since last run). State keeps a monotonic max-seen id and the detail of
the currently-open positions, so it stays small but readable.

Targets: pass --target repeatedly. Each accepts a bare id (`13`), an `id:period`
(`13:all_time`), or a full leaderboard URL (web or /api/...) — the id and period are parsed
out. Default target is 29:this_week.

Auth: the endpoint returns 401 without a session cookie. Provide it via JOSH_COOKIE (or a
JOSH_COOKIE=... line in ./.env), or --cookie. Cookies expire; on 401 the script says so.
Never commit the cookie — it is a live credential.

Informational only, not investment advice. Mirrors the last completed fetch; open trades
carry UNKNOWN P&L until the trader closes them.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://leaderboard.stockswithjosh.com/api/leaderboard/traders/{tid}?period={period}"
UA = "Mozilla/5.0 (X11; Linux x86_64) claude-trading-skills/josh-trade-monitor"
DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "targets.txt"
_TRADER_RE = re.compile(r"/traders/(\d+)")
_PERIOD_RE = re.compile(r"[?&]period=([^&]+)")


def read_targets_file(path):
    """One target token per line (id / id:period / URL). Blank lines and #-comments ignored."""
    out = []
    for raw in Path(path).read_text().splitlines():
        s = raw.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def parse_target(tok, default_period):
    """'13' -> (13, default); '13:all_time' -> (13,'all_time'); a leaderboard URL -> both."""
    if tok.startswith("http"):
        m = _TRADER_RE.search(tok)
        if not m:
            raise ValueError(f"no trader id in URL: {tok}")
        pm = _PERIOD_RE.search(tok)
        return int(m.group(1)), (pm.group(1) if pm else default_period)
    if ":" in tok:
        tid, period = tok.split(":", 1)
        return int(tid), period
    return int(tok), default_period


def load_cookie(cli_cookie):
    """JOSH_COOKIE env > ./.env JOSH_COOKIE line > --cookie."""
    cookie = os.environ.get("JOSH_COOKIE") or ""
    if not cookie:
        env = Path(".env")
        if env.exists():
            for line in env.read_text().splitlines():
                if line.strip().startswith("JOSH_COOKIE="):
                    cookie = line.split("=", 1)[1].strip().strip("'\"")
                    break
    return cookie or (cli_cookie or "")


def fetch(url, cookie):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    if cookie:
        req.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            sys.exit(
                f"HTTP {e.code}: authentication failed. The session cookie is missing or "
                "expired. Refresh JOSH_COOKIE (copy the Cookie header from a logged-in "
                "browser request to the leaderboard)."
            )
        sys.exit(f"HTTP {e.code} fetching {url}: {e.reason}")
    except urllib.error.URLError as e:
        sys.exit(f"Network error fetching {url}: {e.reason}")


def instrument(t):
    """option (has a strike/expiration) vs equity (Josh's 'long' with strike '—')."""
    return "option" if (t.get("direction") or "").lower() in ("call", "put") else "equity"


def parse_strike(strike):
    """'205 CALL' -> 205.0, '242.5 PUT' -> 242.5, '—'/None -> None."""
    if not strike or strike == "—":
        return None
    try:
        return float(str(strike).split()[0])
    except (ValueError, IndexError):
        return None


def trade_detail(t):
    """Normalized, readable view of a raw trade — the shape stored in state and in events."""
    strike = t.get("strike")
    return {
        "trade_id": t.get("id"),
        "ticker": t.get("ticker"),
        "instrument": instrument(t),
        "direction": (t.get("direction") or "").lower(),
        "strike": None if strike in (None, "—", "") else strike,
        "strike_price": parse_strike(strike),
        "expiration": t.get("expiration"),
        "entry_price": t.get("entryPrice"),
        "exit_price": t.get("exitPrice"),
        "pnl_percent": t.get("pnlPercent"),
        "result": t.get("result"),
        "status": t.get("status"),
        "signal_time": t.get("createdAt"),
        "closed_at": t.get("closedAt"),
    }


def to_event(t, action):
    """Executor-facing event: a trade_detail tagged with 'open' or 'close'.

    The monitor emits each trade's 'open' exactly once and its 'close' at most once across
    its whole run history, so a chained executor never double-acts; a decoupled executor can
    dedup on (trade_id, action).
    """
    return {"action": action, **trade_detail(t)}


def diff_trades(trades, state):
    """Return (new_trades, closed_now, next_state).

    First run (no prior max_seen_id) records a baseline and reports nothing as new. New = id
    strictly greater than the highest id seen before. closed_now = trades that were open last
    run and are now closed. next_state stores max_seen_id and the *detail* of currently-open
    positions (readable, not just ids).
    """
    first_run = "max_seen_id" not in state
    max_seen = state.get("max_seen_id", 0)
    # prev open ids: from stored open_positions detail (new schema) or legacy open_ids
    prev_open = {p["trade_id"] for p in state.get("open_positions", [])} or set(
        state.get("open_ids", [])
    )

    all_ids = [t["id"] for t in trades]
    new = [] if first_run else [t for t in trades if t["id"] > max_seen]
    closed_now = [t for t in trades if t["id"] in prev_open and t.get("status") == "closed"]
    open_positions = [trade_detail(t) for t in trades if t.get("status") == "open"]

    next_state = {
        "max_seen_id": max(all_ids + [max_seen]) if all_ids else max_seen,
        "open_positions": open_positions,
    }
    return new, closed_now, next_state


def fmt_trade(t):
    """One-line human summary of a raw trade signal."""
    tid, tkr, direc = t.get("id"), t.get("ticker", "?"), (t.get("direction") or "").lower()
    strike = t.get("strike") or ""
    contract = f"{direc} {strike}".strip() if strike and strike != "—" else direc
    exp = f" exp {t['expiration']}" if t.get("expiration") else ""
    entry = t.get("entryPrice")
    when = (t.get("createdAt") or "")[:16].replace("T", " ")
    return f"  #{tid} {tkr} {contract}{exp} @ {entry}  (opened {when}Z)"


def fmt_closed(t):
    entry, exit_, pnl = t.get("entryPrice"), t.get("exitPrice"), t.get("pnlPercent")
    pnl_s = f"{pnl:+.1f}%" if isinstance(pnl, (int, float)) else "?"
    return f"  #{t.get('id')} {t.get('ticker', '?')}: {entry} → {exit_} = {pnl_s} {t.get('result', '')}"


def build_report(trader, new, closed_now, first_run, last_run, open_trades):
    who = trader.get("displayName") or trader.get("username") or "trader"
    lines = [f"# Josh trade monitor — {who}", ""]
    if first_run:
        lines.append("Baseline recorded. Tracking future signals from now on.")
        if open_trades:
            lines.append(f"Currently open (tracked, not acted on): {len(open_trades)}")
            lines += [fmt_trade(t) for t in sorted(open_trades, key=lambda x: x["id"])]
        return "\n".join(lines)
    lines.append(f"Last run: {last_run or 'unknown'}")
    lines.append("")
    if new:
        lines.append(f"## {len(new)} NEW trade(s)")
        lines += [fmt_trade(t) for t in sorted(new, key=lambda x: x["id"])]
    else:
        lines.append("No new trades since last run.")
    if closed_now:
        lines.append("")
        lines.append(f"## {len(closed_now)} position(s) closed since last run")
        lines += [fmt_closed(t) for t in sorted(closed_now, key=lambda x: x["id"])]
    return "\n".join(lines)


def run_one(trader_id, period, cookie, state_dir, output_dir, fixture, now):
    """Fetch + diff + persist one target. Returns (text_report, events_doc)."""
    data = (
        json.loads(Path(fixture).read_text())
        if fixture
        else fetch(API.format(tid=trader_id, period=period), cookie)
    )
    trades = data.get("trades", [])
    trader = data.get("trader", {})

    state_file = Path(state_dir) / f"trader_{trader_id}_{period}.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    first_run = "max_seen_id" not in state
    last_run = state.get("last_run")

    new, closed_now, next_state = diff_trades(trades, state)
    events = [to_event(t, "open") for t in sorted(new, key=lambda x: x["id"])]
    events += [to_event(t, "close") for t in sorted(closed_now, key=lambda x: x["id"])]
    events_doc = {
        "generated_at": now,
        "trader_id": trader_id,
        "period": period,
        "trader": trader.get("displayName") or trader.get("username"),
        "events": events,
    }

    open_trades = [t for t in trades if t.get("status") == "open"]
    text = build_report(trader, new, closed_now, first_run, last_run, open_trades)

    next_state["last_run"] = now
    next_state["trader_id"] = trader_id
    next_state["period"] = period
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(next_state, indent=2))
    state_file.with_name(state_file.stem + "_events.json").write_text(
        json.dumps(events_doc, indent=2)
    )

    if (new or closed_now) and output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
        fp = out / f"josh_trade_monitor_{trader_id}_{period}_{stamp}.md"
        fp.write_text(text + "\n")
        print(f"Report written to {fp}", file=sys.stderr)
    return text, events_doc


def main(argv=None):
    p = argparse.ArgumentParser(description="Report Stocks-With-Josh trades new since last run.")
    p.add_argument(
        "--target",
        action="append",
        default=None,
        help="id | id:period | leaderboard URL — repeatable; overrides the targets file",
    )
    p.add_argument(
        "--targets-file",
        default=None,
        help=f"file of targets, one per line (default {DEFAULT_CONFIG} if present)",
    )
    p.add_argument(
        "--period", default="this_week", help="default period for bare ids/URLs (default this_week)"
    )
    p.add_argument("--cookie", help="session cookie (prefer JOSH_COOKIE env or ./.env)")
    p.add_argument(
        "--state-dir", default="state/josh-trade-monitor", help="per-target state/events dir"
    )
    p.add_argument(
        "--output-dir", default="reports", help="write a markdown report here when there is news"
    )
    p.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="stdout: human text or JSON event contract",
    )
    p.add_argument(
        "--fixture",
        help="read one response from this JSON file instead of the network (single target)",
    )
    args = p.parse_args(argv)

    # target precedence: explicit --target > --targets-file > default config file > 29
    if args.target:
        tokens = args.target
    elif args.targets_file:
        tokens = read_targets_file(args.targets_file)
    elif DEFAULT_CONFIG.exists():
        tokens = read_targets_file(DEFAULT_CONFIG)
    else:
        tokens = ["29"]
    if not tokens:
        p.error("no targets found (targets file is empty)")
    targets = [parse_target(t, args.period) for t in tokens]
    if args.fixture and len(targets) != 1:
        p.error("--fixture requires exactly one target")

    cookie = None if args.fixture else load_cookie(args.cookie)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    texts, docs = [], []
    for tid, period in targets:
        text, doc = run_one(tid, period, cookie, args.state_dir, args.output_dir, args.fixture, now)
        texts.append(text)
        docs.append(doc)

    if args.format == "json":
        print(json.dumps(docs[0] if len(docs) == 1 else docs, indent=2))
    else:
        print("\n\n".join(texts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
