#!/usr/bin/env python3
"""Phase 2 entry point: pre-market trade plan generator.

Reads a Phase 1 ``parabolic_short_<as_of>.json`` watchlist, then for each
candidate:

1. Filter by ``--tradable-min-grade`` (default ``B``).
2. Look up Alpaca's short inventory (or ``ManualBrokerAdapter`` when
   ``--broker none`` is passed / Alpaca env vars are missing).
3. Inherit the previous regular-session close from
   ``key_levels.prior_close`` and evaluate Rule 201 SSR state.
4. Build the size recipe (risk_usd, max_position_value_usd,
   shares_formula).
5. Render the three trigger plans (5min ORL break, first red 5-min,
   VWAP fail) — entry / stop are *hints*, not concrete prices, so the
   final share count is computed at trigger time, not here.
6. Emit ``parabolic_short_plan_<as_of>.json``.

Pure I/O glue. All math sits in dedicated modules with their own tests.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (
    str(SCRIPTS_DIR / "calculators"),
    str(SCRIPTS_DIR / "adapters"),
    str(SCRIPTS_DIR / "plan_builders"),
    str(SCRIPTS_DIR),
):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from broker_short_inventory_adapter import (  # noqa: E402
    BrokerNotConfiguredError,
    ManualBrokerAdapter,
)
from first_red_plan_builder import build_first_red_plan  # noqa: E402
from manual_reasons import (  # noqa: E402
    build_manual_reasons,
    requires_manual_confirmation,
    trade_allowed_without_manual,
)
from orl_plan_builder import build_orl_plan  # noqa: E402
from parabolic_scorer import grade_at_or_above  # noqa: E402
from size_recipe_builder import build_size_recipe  # noqa: E402
from ssr_state_tracker import evaluate_ssr, load_prior_day_state, save_state  # noqa: E402
from vwap_fail_plan_builder import build_vwap_fail_plan  # noqa: E402

logger = logging.getLogger("parabolic_short.plan")

SCHEMA_VERSION = "1.0"
SKILL_NAME = "parabolic-short-trade-planner"
PHASE = "pre_market_plan"


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Parabolic Short — pre-market plan generator (Phase 2)")
    p.add_argument("--candidates-json", required=True, help="Phase 1 output JSON path")
    p.add_argument("--tradable-min-grade", choices=["A", "B", "C", "D"], default="B")
    p.add_argument("--account-size", type=float, default=100_000)
    p.add_argument("--risk-bps", type=int, default=50)
    p.add_argument("--max-position-pct", type=float, default=5.0)
    p.add_argument("--max-short-exposure-pct", type=float, default=20.0)
    p.add_argument("--current-short-exposure", type=float, default=0.0)
    p.add_argument("--stop-buffer-atr", type=float, default=0.25)
    p.add_argument("--reference-r-multiples", default="1.0,2.0,3.0")
    p.add_argument("--broker", choices=["alpaca", "none"], default="alpaca")
    p.add_argument("--alpaca-api-key")
    p.add_argument("--alpaca-secret")
    p.add_argument("--alpaca-paper", default="true")
    p.add_argument("--ssr-state-dir", default="state/parabolic_short/")
    p.add_argument("--output-dir", default="reports/")
    p.add_argument("--output-prefix", default="parabolic_short_plan")
    p.add_argument("--verbose", action="store_true")
    return p


def _resolve_broker(args: argparse.Namespace):
    if args.broker == "none":
        return ManualBrokerAdapter()
    try:
        from alpaca_inventory_adapter import AlpacaInventoryAdapter

        return AlpacaInventoryAdapter(
            api_key=args.alpaca_api_key,
            secret_key=args.alpaca_secret,
            paper=args.alpaca_paper.lower() == "true",
        )
    except BrokerNotConfiguredError as e:
        logger.warning("Alpaca not configured (%s); falling back to manual", e)
        return ManualBrokerAdapter()


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_r_multiples(s: str) -> tuple[float, ...]:
    return tuple(float(x) for x in s.split(",") if x.strip())


def _premarket_levels_from_phase1(candidate: dict) -> dict:
    """Phase 1 doesn't fetch aftermarket data, so the schema fields stay
    ``None`` until a future revision wires get_aftermarket_quote into
    Phase 2. Keeping the keys present (with null values) preserves the
    schema contract for downstream consumers."""
    return {
        "premarket_price": None,
        "premarket_bid": None,
        "premarket_ask": None,
        "premarket_volume": None,
        "premarket_high": None,
        "premarket_low": None,
        "premarket_high_low_source": "manual_check_required",
        "premarket_source": "not_fetched_in_mvp",
        "premarket_timestamp": None,
    }


def build_plan_for_candidate(
    candidate: dict,
    *,
    broker_adapter,
    args: argparse.Namespace,
    ssr_state_dir: str,
    as_of: str,
) -> dict:
    ticker = candidate["ticker"]
    rank = candidate["rank"]
    score = candidate["score"]
    state_caps = candidate.get("state_caps", [])
    warnings = candidate.get("warnings", [])
    key_levels = candidate.get("key_levels", {})
    prior_close = key_levels.get("prior_close")

    broker_inventory = broker_adapter.get_inventory_status(ticker)

    ssr_state = {
        "ssr_triggered_today": False,
        "ssr_carryover_from_prior_day": False,
        "prior_regular_close": prior_close,
        "prior_regular_close_source": "phase1_inherit",
        "uptick_rule_active": False,
    }
    if prior_close:
        # Treat the screener's close as both prior_close and "current" — the
        # MVP doesn't pull premarket prints, so SSR can only tell us about
        # carryover, not "today triggered" until aftermarket is wired up.
        prior_state = load_prior_day_state(ssr_state_dir, ticker, as_of)
        ssr_state = evaluate_ssr(
            prior_regular_close=prior_close,
            current_price=prior_close,
            prior_day_state=prior_state,
        )
        save_state(ssr_state_dir, ticker, as_of, ssr_state)

    premarket = _premarket_levels_from_phase1(candidate)

    reasons = build_manual_reasons(
        broker_inventory=broker_inventory,
        ssr_state=ssr_state,
        state_caps=state_caps,
        warnings=warnings,
        premarket_levels=premarket,
    )

    size_recipe = build_size_recipe(
        account_size=args.account_size,
        risk_bps=args.risk_bps,
        max_position_pct=args.max_position_pct,
        max_short_exposure_pct=args.max_short_exposure_pct,
        current_short_exposure=args.current_short_exposure,
    )

    r_multiples = _parse_r_multiples(args.reference_r_multiples)
    today = as_of.replace("-", "")
    base_id = f"{ticker}-{today}"
    entry_plans = [
        build_orl_plan(
            plan_id=f"{base_id}-ORL5",
            size_recipe=size_recipe,
            reference_r_multiples=r_multiples,
            stop_buffer_atr=args.stop_buffer_atr,
        ),
        build_first_red_plan(
            plan_id=f"{base_id}-FR5",
            size_recipe=size_recipe,
            reference_r_multiples=r_multiples,
        ),
        build_vwap_fail_plan(
            plan_id=f"{base_id}-VWF",
            size_recipe=size_recipe,
            reference_r_multiples=r_multiples,
        ),
    ]

    plan_status = _classify_plan_status(reasons["blocking"])

    return {
        "ticker": ticker,
        "rank": rank,
        "score": score,
        "plan_status": plan_status,
        "requires_manual_confirmation": requires_manual_confirmation(reasons),
        "trade_allowed_without_manual": trade_allowed_without_manual(reasons),
        "blocking_manual_reasons": reasons["blocking"],
        "advisory_manual_reasons": reasons["advisory"],
        "broker_inventory": broker_inventory,
        "ssr_state": ssr_state,
        "premarket_levels": premarket,
        "key_levels": {
            "dma_10": key_levels.get("dma_10"),
            "dma_20": key_levels.get("dma_20"),
            "atr_14": candidate.get("metrics", {}).get("atr_14"),
        },
        "entry_plans": entry_plans,
    }


# Reasons that prevent trading entirely vs. reasons the trader can clear by
# confirming at the broker. ``borrow_inventory_unavailable`` and active SSR
# fall in the "no path forward today" bucket → watch_only. Premarket high/low
# missing or HTB borrow fee unknown can be cleared by manual checks → still
# rendered as actionable plans, just gated.
_HARD_BLOCKERS = frozenset(
    {
        "borrow_inventory_unavailable",
        "ssr_active_today",
        "ssr_carryover",
    }
)


def _classify_plan_status(blocking_reasons: list[str]) -> str:
    """Classify the plan into ``actionable`` / ``watch_only``.

    - ``actionable``: no blocking reasons OR only "manual gate" blockers
      (HTB fee, premarket high/low unavailable, state caps) that the
      trader can clear by checking with the broker.
    - ``watch_only``: at least one hard blocker (borrow unavailable, SSR
      active/carryover) means today is off-limits regardless of manual
      confirmation. The plan is still emitted so the trader has a target
      list, but trade_allowed_without_manual stays False.
    """
    if any(r in _HARD_BLOCKERS for r in blocking_reasons):
        return "watch_only"
    return "actionable"


def build_plan_report(
    *,
    plans: list[dict],
    as_of: str,
    account_size: float,
    risk_bps: int,
    data_source: str,
) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "skill": SKILL_NAME,
        "phase": PHASE,
        "generated_at": _now_iso(),
        "as_of": as_of,
        "data_source": data_source,
        "data_latency_sec": 0,
        "account_size": account_size,
        "risk_bps": risk_bps,
        "plans": plans,
    }


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    with open(args.candidates_json, encoding="utf-8") as fh:
        phase1 = json.load(fh)
    as_of = phase1.get("as_of") or datetime.now().date().isoformat()
    candidates = phase1.get("candidates", [])

    broker = _resolve_broker(args)
    data_source = "FMP+Alpaca" if isinstance(broker, ManualBrokerAdapter) is False else "FMP+manual"

    plans = []
    for c in candidates:
        if not grade_at_or_above(c["rank"], args.tradable_min_grade):
            continue
        plans.append(
            build_plan_for_candidate(
                c,
                broker_adapter=broker,
                args=args,
                ssr_state_dir=args.ssr_state_dir,
                as_of=as_of,
            )
        )

    report = build_plan_report(
        plans=plans,
        as_of=as_of,
        account_size=args.account_size,
        risk_bps=args.risk_bps,
        data_source=data_source,
    )

    odir = Path(args.output_dir)
    odir.mkdir(parents=True, exist_ok=True)
    out_path = odir / f"{args.output_prefix}_{as_of}.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
