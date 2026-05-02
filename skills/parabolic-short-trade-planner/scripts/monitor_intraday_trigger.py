#!/usr/bin/env python3
"""Phase 3 CLI: one-shot intraday trigger evaluator.

Reads a Phase 2 plan JSON, fetches 5-min bars (Alpaca live or
fixture), walks each plan's FSM forward by one step, persists per-plan
state, and writes an ``intraday_monitor`` JSON describing the current
state of every monitored plan.

Run via ``watch -n 60 python3 monitor_intraday_trigger.py ...`` or
5-min cron during US market hours. The runtime is deliberately
one-shot — no internal sleep loop — so the trader controls cadence
and crash-recovery is "just run it again".

Idempotency contract: the FSM is a pure left-fold over the bar list
from session open. ``prior_state`` is read by this CLI for diff /
notification purposes only; it is never an input to the FSM. Two
runs with the same fixture and same ``--now-et`` produce
byte-identical output (after normalising ``evaluated_at``).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (
    str(SCRIPTS_DIR / "intraday_evaluators"),
    str(SCRIPTS_DIR / "adapters"),
    str(SCRIPTS_DIR),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from intraday_size_resolver import resolve_size_recipe  # noqa: E402
from intraday_state_machine import step_one_plan  # noqa: E402
from intraday_state_store import load_state, save_state  # noqa: E402
from market_clock import is_regular_session, now_et, session_date_for  # noqa: E402

logger = logging.getLogger("parabolic_short.intraday")

SCHEMA_VERSION = "1.0"
SKILL_NAME = "parabolic-short-trade-planner"
PHASE = "intraday_monitor"

ALPACA_DATA_SOURCE = "alpaca_v2_stocks_bars"
FIXTURE_DATA_SOURCE = "fixture"


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Parabolic Short — Phase 3 intraday trigger monitor (one-shot)",
    )
    p.add_argument("--plans-json", required=True, help="Phase 2 plans JSON path")
    p.add_argument(
        "--bars-source",
        choices=["alpaca", "fixture"],
        required=True,
    )
    p.add_argument(
        "--bars-fixture",
        help="Path to fixture JSON ({ticker: [bars]}). Required when --bars-source=fixture.",
    )
    p.add_argument("--state-dir", default="state/parabolic_short/")
    p.add_argument("--output-dir", default="reports/")
    p.add_argument("--output-prefix", default="parabolic_short_intraday")
    p.add_argument(
        "--as-of",
        default=None,
        help="YYYY-MM-DD; default = ET session date for --now-et (or now if omitted).",
    )
    p.add_argument(
        "--now-et",
        default=None,
        help=(
            "ISO 8601 datetime (with offset) overriding 'right now'. Used by tests "
            "and replay walks; production usage omits this and reads market_clock.now_et()."
        ),
    )
    p.add_argument(
        "--stop-buffer-atr",
        type=float,
        default=0.25,
        help="ORL stop cushion as a multiple of daily ATR(14).",
    )
    p.add_argument(
        "--include-watch-only",
        action="store_true",
        help="Also evaluate plans whose plan_status=watch_only (default skips them).",
    )
    p.add_argument("--alpaca-api-key")
    p.add_argument("--alpaca-secret")
    p.add_argument("--alpaca-paper", default="true")
    p.add_argument("--alpaca-feed", default="iex", choices=["iex", "sip"])
    p.add_argument("--verbose", action="store_true")
    return p


def _resolve_now_et(args: argparse.Namespace) -> datetime:
    if args.now_et:
        ts = datetime.fromisoformat(args.now_et)
        if ts.tzinfo is None:
            raise SystemExit("--now-et must include a timezone offset")
        return ts
    return now_et()


def _market_status(ts_now_et: datetime) -> str:
    if is_regular_session(ts_now_et):
        return "regular_session"
    return "closed"


def _resolve_adapter(args: argparse.Namespace):
    if args.bars_source == "fixture":
        if not args.bars_fixture:
            raise SystemExit("--bars-source fixture requires --bars-fixture <path>")
        from fixture_market_data_adapter import FixtureBarsAdapter

        return FixtureBarsAdapter(args.bars_fixture), FIXTURE_DATA_SOURCE

    from alpaca_market_data_adapter import AlpacaMarketDataAdapter

    adapter = AlpacaMarketDataAdapter(
        api_key=args.alpaca_api_key,
        secret_key=args.alpaca_secret,
        paper=args.alpaca_paper.lower() == "true",
        feed=args.alpaca_feed,
    )
    return adapter, ALPACA_DATA_SOURCE


def _flatten_plans(phase2_report: dict, *, include_watch_only: bool) -> list[dict]:
    """Pull every entry_plan out of the Phase 2 report and tag it with
    its parent's ticker / key_levels / plan_status so the FSM can
    consume it standalone."""
    out: list[dict] = []
    for parent in phase2_report.get("plans", []):
        if parent.get("plan_status") != "actionable" and not include_watch_only:
            continue
        for ep in parent.get("entry_plans", []):
            out.append(
                {
                    "plan_id": ep["plan_id"],
                    "ticker": parent["ticker"],
                    "trigger_type": ep["trigger_type"],
                    "size_recipe": ep["size_recipe"],
                    "atr_14": parent.get("key_levels", {}).get("atr_14"),
                }
            )
    return out


def _no_bars_state(plan: dict, prior_state: dict | None) -> dict:
    """Display-only carry-forward when the adapter returns []. The FSM
    is NOT advanced; we just preserve the prior FSM state for UI
    continuity (per v0.5c contract — the single exception to the
    prior-state-free FSM rule).

    Schema parity (v0.5d): emits ``shares_actual`` and
    ``size_recipe_resolved`` keys (both null) so downstream consumers
    can rely on every ``monitored_plans[*]`` entry having the same
    key set, regardless of whether bars were available.
    """
    base = {
        "plan_id": plan["plan_id"],
        "ticker": plan["ticker"],
        "trigger_type": plan["trigger_type"],
        "state": "armed",
        "evaluation_status": "no_bars",
        "skip_reason": None,
        "armed_at": None,
        "triggered_at": None,
        "invalidated_at": None,
        "invalidation_reason": None,
        "entry_actual": None,
        "stop_actual": None,
        "shares_actual": None,
        "size_recipe_resolved": None,
        "session_high": None,
        "session_low": None,
        "last_bar_ts": None,
    }
    if prior_state:
        # Carry forward FSM-shaped fields only; never advance.
        for k in (
            "state",
            "armed_at",
            "triggered_at",
            "invalidated_at",
            "invalidation_reason",
            "entry_actual",
            "stop_actual",
            "shares_actual",
            "size_recipe_resolved",
            "session_high",
            "session_low",
            "last_bar_ts",
        ):
            if k in prior_state and prior_state[k] is not None:
                base[k] = prior_state[k]
    return base


def _attach_size_resolved(monitored: dict, size_recipe: dict) -> dict:
    """If the plan triggered, fill size_recipe_resolved using the
    code-implemented formula (NEVER eval the formula string)."""
    if monitored["state"] != "triggered" or monitored.get("entry_actual") is None:
        monitored["size_recipe_resolved"] = None
        monitored["shares_actual"] = None
        return monitored
    resolved = resolve_size_recipe(
        size_recipe,
        entry_actual=monitored["entry_actual"],
        stop_actual=monitored["stop_actual"],
    )
    monitored["size_recipe_resolved"] = resolved
    monitored["shares_actual"] = resolved["shares_actual"]
    return monitored


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    with open(args.plans_json, encoding="utf-8") as fh:
        phase2 = json.load(fh)

    flat_plans = _flatten_plans(phase2, include_watch_only=args.include_watch_only)
    if not flat_plans:
        logger.warning("No actionable plans found in %s", args.plans_json)

    ts_now_et = _resolve_now_et(args)
    as_of = args.as_of or session_date_for(ts_now_et)
    market_status = _market_status(ts_now_et)

    adapter, data_source = _resolve_adapter(args)

    # Group plans by ticker so we fetch each ticker's bars exactly once.
    plans_by_ticker: dict[str, list[dict]] = defaultdict(list)
    for p in flat_plans:
        plans_by_ticker[p["ticker"]].append(p)

    monitored_plans: list[dict] = []
    for ticker, plans in plans_by_ticker.items():
        bars = adapter.get_bars_5min(ticker, session_date=as_of, until_et=ts_now_et)
        for plan in plans:
            prior = load_state(args.state_dir, plan["plan_id"], as_of)

            if not bars:
                state = _no_bars_state(plan, prior)
            else:
                state = step_one_plan(
                    plan,
                    bars,
                    atr_14=plan["atr_14"],
                    stop_buffer_atr=args.stop_buffer_atr,
                )
                _attach_size_resolved(state, plan["size_recipe"])

            state["last_evaluated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            save_state(args.state_dir, plan["plan_id"], as_of, state)
            monitored_plans.append(state)

    report = {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "phase": PHASE,
        "as_of": as_of,
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "now_et": ts_now_et.isoformat(),
        "market_status": market_status,
        "data_source": data_source,
        "monitored_plans": monitored_plans,
    }

    odir = Path(args.output_dir)
    odir.mkdir(parents=True, exist_ok=True)
    out_path = odir / f"{args.output_prefix}_{as_of}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
