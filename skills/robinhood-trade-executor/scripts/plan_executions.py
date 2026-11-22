#!/usr/bin/env python3
"""Downstream Robinhood execution planner — the money-spending selection, kept deterministic
and testable. Actual orders are placed by the skill via the Robinhood MCP connector; this
script never touches a broker.

`plan`   reads one or more upstream recommendation files, adapts each to a canonical order
         intent, diffs against an idempotency ledger, and emits the orders to place
         (equity + single-leg option, buy + sell) plus a skipped list with reasons. A single
         feed may mix equity and options.
`record` appends a confirmed execution to the ledger AFTER the skill places the order, so a
         re-run never double-executes.

Upstream sources (auto-detected by top-level key, or forced with --source):
  - canonical : {"intents": [ ... ]}                       (any skill that speaks the contract)
  - josh      : josh-trade-monitor <state>_events.json     ({"events": [...]}) — equity + options, open/close
  - social    : social-signal-ingestor signals/index.json  ({"signals": [...]}) — long stock, buy only

Real money, no human gate: idempotency is on intent_id and is not optional; a close sells only
what its matching open filled.
"""

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    return json.loads(p.read_text())


# --- adapters: upstream shape -> canonical intents ---------------------------------------
# canonical intent: {match_key, action(open|close), instrument(equity|option), ticker,
#   direction(long|call|put), strike, expiration, reference_price, notional, source}
# match_key is the position identity shared by an open and its close; intent_id = match_key:action.


def adapt_canonical(doc):
    return list(doc.get("intents", []))


def adapt_josh(doc):
    tid = doc.get("trader_id")
    out = []
    for e in doc.get("events", []):
        out.append(
            {
                "match_key": f"josh:{tid}:{e.get('trade_id')}",
                "action": e.get("action"),
                "instrument": e.get("instrument"),
                "ticker": e.get("ticker"),
                "direction": e.get("direction"),
                "strike": e.get("strike_price"),
                "expiration": e.get("expiration"),
                "reference_price": e.get("entry_price"),
                "notional": None,
                "source": "josh",
            }
        )
    return out


def adapt_social(doc):
    """social-signal-ingestor: long-stock buys only (options are multi-leg / carry no premium,
    so they can't be notional-sized here — deferred, exactly as the old skill skipped them)."""
    out, skipped = [], []
    for s in doc.get("signals", []):
        tkr = s.get("ticker")
        if s.get("direction") != "long":
            skipped.append(
                {
                    "match_key": f"social:{tkr}",
                    "reason": f"direction {s.get('direction')!r} — buy long only",
                }
            )
            continue
        if s.get("watch"):
            skipped.append(
                {"match_key": f"social:{tkr}", "reason": "conditional/watch long — not triggered"}
            )
            continue
        if s.get("instrument") == "option":
            skipped.append(
                {
                    "match_key": f"social:{tkr}",
                    "reason": "social options are multi-leg / no premium — deferred",
                }
            )
            continue
        out.append(
            {
                "match_key": f"social:{tkr}",
                "action": "open",
                "instrument": "equity",
                "ticker": tkr,
                "direction": "long",
                "strike": None,
                "expiration": None,
                "reference_price": None,
                "notional": None,
                "source": "social",
            }
        )
    return out, skipped


_ADAPTERS = {"canonical": adapt_canonical, "josh": adapt_josh, "social": adapt_social}


def detect_source(doc):
    if "intents" in doc:
        return "canonical"
    if "events" in doc:
        return "josh"
    if "signals" in doc:
        return "social"
    raise ValueError("cannot detect source: expected an 'intents', 'events', or 'signals' key")


def load_intents(paths, forced_source=None):
    """Read + adapt + merge intents from several upstream files. Returns (intents, pre_skipped)."""
    intents, pre_skipped = [], []
    for path in paths:
        doc = _load(path)
        if doc is None:
            raise SystemExit(f"input not found: {path}")
        src = forced_source or detect_source(doc)
        result = _ADAPTERS[src](doc)
        if isinstance(result, tuple):  # adapters may return (intents, skipped)
            got, sk = result
            intents += got
            pre_skipped += sk
        else:
            intents += result
    return intents, pre_skipped


# --- planning: canonical intents -> orders ------------------------------------------------


def build_plan(intents, ledger, buy_amount, as_of=None, pre_skipped=None):
    """(intents, ledger, buy_amount, as_of, pre_skipped) -> plan dict. Pure; the tested core.

    Orders carry `kind` in {equity_buy, equity_sell, option_buy, option_sell} mapping to the
    two Robinhood MCP tools. Options are sized to whole contracts against the notional using
    the signal's reference premium (an estimate — the live fill differs). A close sells exactly
    what its matching open filled; expired options and unaffordable/incomplete ones are skipped.
    """
    acted = {r.get("intent_id") for r in ledger}
    opens = {
        r["match_key"]: r
        for r in ledger
        if r.get("action") == "open" and r.get("status") in ("filled", "pending")
    }
    orders, skipped = [], list(pre_skipped or [])

    def skip(mk, reason, action=None, ticker=None):
        skipped.append({"match_key": mk, "action": action, "ticker": ticker, "reason": reason})

    for it in intents:
        mk, action, ticker = it.get("match_key"), it.get("action"), it.get("ticker")
        inst = it.get("instrument")
        intent_id = f"{mk}:{action}"
        notional = it.get("notional") or buy_amount
        base = {"intent_id": intent_id, "match_key": mk, "ticker": ticker}

        if intent_id in acted:
            skip(mk, "already executed (in ledger)", action, ticker)
            continue

        if action == "open":
            if inst == "equity":
                if it.get("direction") != "long":
                    skip(
                        mk,
                        f"non-long equity open ({it.get('direction')}) — not supported",
                        action,
                        ticker,
                    )
                    continue
                orders.append({"kind": "equity_buy", **base, "dollar_amount": notional})
            elif inst == "option":
                exp, strike = it.get("expiration"), it.get("strike")
                otype, prem = it.get("direction"), it.get("reference_price")
                if not exp or strike is None or otype not in ("call", "put"):
                    skip(mk, "incomplete option spec (expiration/strike/type)", action, ticker)
                    continue
                if as_of and exp < as_of:
                    skip(mk, f"contract expired ({exp} < {as_of})", action, ticker)
                    continue
                if not prem or prem <= 0:
                    skip(mk, "no reference premium — cannot size contracts", action, ticker)
                    continue
                cost_per = prem * 100.0
                contracts = math.floor(notional / cost_per)
                if contracts < 1:
                    skip(
                        mk, f"notional ${notional:g} < 1 contract (~${cost_per:g})", action, ticker
                    )
                    continue
                orders.append(
                    {
                        "kind": "option_buy",
                        **base,
                        "option_type": otype,
                        "strike": strike,
                        "expiration": exp,
                        "contracts": contracts,
                        "est_premium": prem,
                        "est_cost": round(contracts * cost_per, 2),
                    }
                )
            else:
                skip(mk, f"unknown instrument {inst!r}", action, ticker)

        elif action == "close":
            o = opens.get(mk)
            if not o:
                skip(mk, "no tracked open position — nothing to close", action, ticker)
                continue
            if o.get("instrument") == "option":
                orders.append(
                    {
                        "kind": "option_sell",
                        **base,
                        "option_type": o.get("option_type"),
                        "strike": o.get("strike"),
                        "expiration": o.get("expiration"),
                        "contracts": o.get("quantity"),
                    }
                )
            else:
                orders.append({"kind": "equity_sell", **base, "quantity": o.get("quantity")})
        else:
            skip(mk, f"unknown action {action!r}", action, ticker)

    return {"buy_amount": buy_amount, "as_of": as_of, "orders": orders, "skipped": skipped}


def cmd_plan(args):
    intents, pre_skipped = load_intents(args.input, args.source)
    ledger = _load(args.ledger, [])
    as_of = args.as_of or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    plan = build_plan(intents, ledger, args.buy_amount, as_of, pre_skipped)
    print(json.dumps(plan, indent=2))
    return 0


def cmd_record(args):
    ledger_path = Path(args.ledger)
    ledger = _load(ledger_path, [])
    ledger.append(
        {
            "intent_id": args.intent_id,
            "match_key": args.match_key,
            "action": args.action,
            "instrument": args.instrument,
            "ticker": args.ticker,
            "status": args.status,
            "order_id": args.order_id,
            "quantity": args.quantity,
            "dollar_amount": args.dollar_amount,
            "option_type": args.option_type,
            "strike": args.strike,
            "expiration": args.expiration,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2))
    print(
        f"recorded {args.action} {args.ticker} [{args.intent_id}] ({args.status})", file=sys.stderr
    )
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Plan/record Robinhood executions from upstream recommendations."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("plan", help="emit orders from one or more upstream files + ledger")
    pl.add_argument(
        "--input",
        action="append",
        required=True,
        help="upstream file (repeatable — feeds are merged)",
    )
    pl.add_argument(
        "--source",
        choices=list(_ADAPTERS),
        default=None,
        help="force source (default: auto-detect per file)",
    )
    pl.add_argument("--ledger", required=True, help="idempotency ledger JSON (created if absent)")
    pl.add_argument(
        "--buy-amount",
        type=float,
        required=True,
        help="fixed $ notional per open (no default — caller decides)",
    )
    pl.add_argument(
        "--as-of", default=None, help="date YYYY-MM-DD for the expiration check (default today)"
    )
    pl.set_defaults(func=cmd_plan)

    rc = sub.add_parser("record", help="append a confirmed execution to the ledger")
    rc.add_argument("--ledger", required=True)
    rc.add_argument("--intent-id", required=True)
    rc.add_argument("--match-key", required=True)
    rc.add_argument("--action", choices=["open", "close"], required=True)
    rc.add_argument("--instrument", choices=["equity", "option"], required=True)
    rc.add_argument("--ticker", required=True)
    rc.add_argument("--status", required=True, help="filled | pending | rejected")
    rc.add_argument("--order-id", default=None)
    rc.add_argument(
        "--quantity", type=float, default=None, help="filled shares (equity) or contracts (option)"
    )
    rc.add_argument("--dollar-amount", type=float, default=None)
    rc.add_argument("--option-type", choices=["call", "put"], default=None)
    rc.add_argument("--strike", type=float, default=None)
    rc.add_argument("--expiration", default=None)
    rc.set_defaults(func=cmd_record)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
