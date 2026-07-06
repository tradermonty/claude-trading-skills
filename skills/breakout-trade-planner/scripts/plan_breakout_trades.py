#!/usr/bin/env python3
"""Breakout Trade Planner — generate Minervini-style trade plans from VCP screener output.

Reads VCP screener JSON, applies a strict Minervini Gate, calculates position
sizes using worst-case entry prices, and outputs actionable trade plans with
Alpaca order templates (pre_place and post_confirm modes).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add scripts dir to path for sibling imports
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from order_builder import (
    build_entry_condition,
    build_post_confirm_template,
    build_pre_place_template,
    build_revalidation_advisory,
)
from risk_calculator import (
    calculate_position_size,
    calculate_r_multiples,
    calculate_risks,
    derive_trade_prices,
    get_rating_band,
    get_sizing_multiplier,
    round_price,
)

ACCEPTED_INPUT_VERSIONS = {"1.0"}
MAX_RISK_PCT = 8.0


def load_input(path: str) -> dict:
    """Load and validate VCP screener JSON."""
    with open(path) as f:
        data = json.load(f)

    version = data.get("schema_version")
    if version is None:
        raise ValueError(
            f"Input JSON missing 'schema_version' (expected one of {ACCEPTED_INPUT_VERSIONS})"
        )
    if version not in ACCEPTED_INPUT_VERSIONS:
        raise ValueError(
            f"Unsupported schema_version '{version}' (expected {ACCEPTED_INPUT_VERSIONS})"
        )

    if "results" not in data or not isinstance(data["results"], list):
        raise ValueError("Input JSON missing or empty 'results' array")

    return data


def load_exposure(path: str | None) -> dict:
    """Load current portfolio exposure or return defaults."""
    if path and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"sector_exposure": {}, "open_risk_pct": 0.0}


REQUIRED_FIELDS = ["symbol", "sector", "price", "composite_score", "execution_state", "valid_vcp"]
BREAKOUT_EXTRA_FIELDS = [
    "volume_pattern.breakout_volume_detected",
    "pivot_proximity.distance_from_pivot_pct",
]


def _get_nested(d: dict, key: str):
    """Get a possibly nested field like 'vcp_pattern.pivot_price'."""
    parts = key.split(".")
    val = d
    for p in parts:
        if not isinstance(val, dict):
            return None
        val = val.get(p)
    return val


def validate_result(result: dict) -> tuple[bool, list[str]]:
    """Validate a single VCP result has required fields.

    Returns (is_valid, list_of_warnings).
    """
    warnings = []
    for field in REQUIRED_FIELDS:
        if _get_nested(result, field) is None:
            warnings.append(f"missing required field: {field}")

    pivot = _get_nested(result, "vcp_pattern.pivot_price")
    if pivot is None:
        warnings.append("missing vcp_pattern.pivot_price")

    contractions = _get_nested(result, "vcp_pattern.contractions")
    if not contractions or not isinstance(contractions, list) or len(contractions) == 0:
        warnings.append("missing or empty vcp_pattern.contractions")
    elif _get_nested(contractions[-1], "low_price") is None:
        warnings.append("missing contractions[-1].low_price")

    # Warn (not fail) for Breakout-specific fields missing
    state = _get_nested(result, "execution_state")
    if state == "Breakout":
        for field in BREAKOUT_EXTRA_FIELDS:
            if _get_nested(result, field) is None:
                warnings.append(f"missing Breakout field: {field}")

    return len(warnings) == 0, warnings


def process_candidate(
    result: dict,
    args: argparse.Namespace,
    cumulative_risk_pct: float,
    sector_tracker: dict[str, float],
    exposure: dict,
) -> dict:
    """Process a single VCP candidate through the Minervini Gate.

    Returns a classified result dict with plan_type, trade_plan, etc.
    """
    symbol = result["symbol"]
    current_price = result["price"]
    composite_score = result["composite_score"]
    execution_state = result["execution_state"]
    valid_vcp = result.get("valid_vcp", False)
    sector = result.get("sector", "Unknown")

    rating_band = get_rating_band(composite_score)

    # Derive trade prices
    pivot = result["vcp_pattern"]["pivot_price"]
    contractions = result["vcp_pattern"]["contractions"]
    last_low = contractions[-1]["low_price"]

    try:
        signal_entry, worst_entry, stop_loss = derive_trade_prices(
            pivot,
            last_low,
            pivot_buffer_pct=args.pivot_buffer_pct,
            max_chase_pct=args.max_chase_pct,
            stop_buffer_pct=args.stop_buffer_pct,
        )
    except ValueError as e:
        return _reject(symbol, f"Trade price derivation failed: {e}")

    risk_pct_signal, risk_pct_worst = calculate_risks(signal_entry, worst_entry, stop_loss)

    # Take profit (worst-entry based)
    tp_worst = round_price(worst_entry + args.target_r_multiple * (worst_entry - stop_loss))

    base_output = {
        "symbol": symbol,
        "company_name": result.get("company_name", ""),
        "sector": sector,
        "composite_score": composite_score,
        "rating_band": rating_band,
        "execution_state": execution_state,
    }

    # --- Pre-breakout path ---
    if execution_state == "Pre-breakout":
        plan_eligible = (
            valid_vcp
            and rating_band in ("textbook", "strong", "good")
            and risk_pct_worst <= MAX_RISK_PCT
        )

        if not plan_eligible:
            # Check watchlist eligibility
            if valid_vcp and 60 <= composite_score < 70:
                return _watchlist(base_output, pivot, stop_loss)
            reasons = []
            if not valid_vcp:
                reasons.append("valid_vcp=False")
            if rating_band not in ("textbook", "strong", "good"):
                reasons.append(f"rating_band={rating_band}")
            if risk_pct_worst > MAX_RISK_PCT:
                reasons.append(f"risk_pct_worst={risk_pct_worst}%>{MAX_RISK_PCT}%")
            return _reject(symbol, "; ".join(reasons))

        return _build_actionable(
            base_output,
            args,
            signal_entry,
            worst_entry,
            stop_loss,
            risk_pct_signal,
            risk_pct_worst,
            tp_worst,
            pivot,
            cumulative_risk_pct,
            sector_tracker,
            exposure,
        )

    # --- Breakout path ---
    if execution_state == "Breakout":
        breakout_volume = _get_nested(result, "volume_pattern.breakout_volume_detected") or False
        distance = _get_nested(result, "pivot_proximity.distance_from_pivot_pct")
        if distance is None:
            return _reject(symbol, "missing distance_from_pivot_pct for Breakout")

        plan_eligible = (
            valid_vcp
            and rating_band in ("textbook", "strong", "good")
            and risk_pct_worst <= MAX_RISK_PCT
            and breakout_volume
            and distance <= args.max_chase_pct
            and current_price <= worst_entry
        )

        if plan_eligible:
            advisory = build_revalidation_advisory(symbol, pivot, current_price, worst_entry)
            advisory.update(base_output)
            advisory["decision_code"] = "REVALIDATION_BREAKOUT"
            advisory["risk_pct_worst"] = risk_pct_worst
            return {"classification": "revalidation", "data": advisory}

        # Breakout candidates do not go to watchlist — they already crossed pivot
        reasons = []
        if not valid_vcp:
            reasons.append("valid_vcp=False")
        if not breakout_volume:
            reasons.append("no breakout volume")
        if distance is not None and distance > args.max_chase_pct:
            reasons.append(f"distance={distance}%>{args.max_chase_pct}%")
        if current_price > worst_entry:
            reasons.append(f"price={current_price}>worst_entry={worst_entry}")
        if risk_pct_worst > MAX_RISK_PCT:
            reasons.append(f"risk_pct_worst={risk_pct_worst}%>{MAX_RISK_PCT}%")
        return _reject(symbol, "; ".join(reasons) if reasons else "ineligible Breakout")

    # --- Watchlist path ---
    if (
        valid_vcp
        and execution_state in ("Pre-breakout", "Early-post-breakout")
        and 60 <= composite_score < 70
    ):
        return _watchlist(base_output, pivot, stop_loss)

    # --- Reject ---
    return _reject(symbol, f"state={execution_state}, score={composite_score}")


def _build_actionable(
    base: dict,
    args,
    signal_entry,
    worst_entry,
    stop_loss,
    risk_pct_signal,
    risk_pct_worst,
    tp_worst,
    pivot,
    cumulative_risk_pct,
    sector_tracker,
    exposure,
):
    """Build an actionable order with trade plan and order templates."""
    sector = base["sector"]
    rating_band = base["rating_band"]
    multiplier = get_sizing_multiplier(rating_band)

    current_sector_exp = exposure.get("sector_exposure", {}).get(sector, 0.0)
    current_sector_exp += sector_tracker.get(sector, 0.0)

    sizing = calculate_position_size(
        worst_entry=worst_entry,
        stop_loss=stop_loss,
        account_size=args.account_size,
        base_risk_pct=args.risk_pct,
        sizing_multiplier=multiplier,
        max_position_pct=args.max_position_pct,
        max_sector_pct=args.max_sector_pct,
        current_sector_exposure=current_sector_exp,
    )

    if sizing["shares"] == 0:
        constraint = sizing.get("binding_constraint", "unknown")
        return {
            "classification": "constrained",
            "data": {"symbol": base["symbol"], "reason": f"0 shares: {constraint}"},
        }

    risk_dollars = sizing["risk_dollars"]
    risk_pct_of_account = risk_dollars / args.account_size * 100
    new_cumulative = cumulative_risk_pct + risk_pct_of_account

    if new_cumulative > args.max_portfolio_heat_pct:
        return {
            "classification": "deferred",
            "data": {
                "symbol": base["symbol"],
                "reason": f"Portfolio heat ceiling: {new_cumulative:.2f}% > {args.max_portfolio_heat_pct}%",
            },
        }

    # Build entry condition and order templates
    entry_cond = build_entry_condition(
        pivot=pivot,
        max_chase_pct=args.max_chase_pct,
    )

    pre_place = build_pre_place_template(
        symbol=base["symbol"],
        qty=sizing["shares"],
        signal_entry=signal_entry,
        worst_entry=worst_entry,
        stop_loss=stop_loss,
        take_profit=tp_worst,
    )

    post_confirm = build_post_confirm_template(
        symbol=base["symbol"],
        qty=sizing["shares"],
        worst_entry=worst_entry,
        stop_loss=stop_loss,
        take_profit=tp_worst,
        entry_condition=entry_cond,
    )

    # Valid for today if market is open (weekday), otherwise next trading day
    today = datetime.now().date()
    if today.weekday() < 5:  # Monday-Friday: valid today
        valid_date = today
    else:  # Weekend: next Monday
        valid_date = today + timedelta(days=7 - today.weekday())

    result = {
        **base,
        "plan_type": "pending_breakout",
        "decision_code": "ACTIONABLE_PREBREAKOUT",
        "decision_reason": (
            f"valid_vcp && state=Pre-breakout && risk_worst={risk_pct_worst}% <= {MAX_RISK_PCT}%"
        ),
        "plan_valid_for_session": str(valid_date),
        "trade_plan": {
            "signal_entry": signal_entry,
            "worst_entry": worst_entry,
            "stop_loss_price": stop_loss,
            "risk_per_share": round(worst_entry - stop_loss, 2),
            "risk_pct_signal": risk_pct_signal,
            "risk_pct_worst": risk_pct_worst,
            "r_multiples_signal": calculate_r_multiples(signal_entry, stop_loss),
            "r_multiples_worst": calculate_r_multiples(worst_entry, stop_loss),
            "target_price": tp_worst,
            "reward_risk_ratio": args.target_r_multiple,
            "sizing_multiplier": multiplier,
            "effective_risk_pct": sizing["effective_risk_pct"],
            "shares": sizing["shares"],
            "position_value": sizing["position_value"],
            "risk_dollars": risk_dollars,
            "cumulative_risk_pct": round(new_cumulative, 2),
            "binding_constraint": sizing["binding_constraint"],
        },
        "order_templates": {
            "pre_place": pre_place,
            "post_confirm": post_confirm,
        },
    }

    return {"classification": "actionable", "data": result, "risk_pct": risk_pct_of_account}


def _watchlist(base: dict, pivot: float, stop_loss: float) -> dict:
    return {
        "classification": "watchlist",
        "data": {
            **base,
            "plan_type": "watchlist",
            "pivot_price": pivot,
            "stop_loss_price": stop_loss,
            "alert_trigger": f"Price crosses above ${pivot:.2f} on 1.5x RVOL",
        },
    }


def _reject(symbol: str, reason: str) -> dict:
    return {
        "classification": "rejected",
        "data": {"symbol": symbol, "reason": reason},
    }


def generate_plans(data: dict, args: argparse.Namespace) -> dict:
    """Main pipeline: filter, score, size, classify all candidates."""
    exposure = load_exposure(args.current_exposure_json)
    results = data["results"]

    # Sort by composite_score descending (highest priority first)
    results_sorted = sorted(results, key=lambda r: r.get("composite_score", 0), reverse=True)

    actionable = []
    revalidation = []
    watchlist = []
    rejected = []
    deferred = []
    constrained = []
    warnings = []

    cumulative_risk_pct = exposure.get("open_risk_pct", 0.0)
    sector_tracker: dict[str, float] = {}

    for result in results_sorted:
        is_valid, warns = validate_result(result)
        if not is_valid:
            symbol = result.get("symbol", "UNKNOWN")
            for w in warns:
                warnings.append({"symbol": symbol, "code": "MISSING_FIELD", "message": w})
            rejected.append({"symbol": symbol, "reason": f"validation: {'; '.join(warns)}"})
            continue

        classified = process_candidate(result, args, cumulative_risk_pct, sector_tracker, exposure)
        cls = classified["classification"]

        if cls == "actionable":
            actionable.append(classified["data"])
            cumulative_risk_pct += classified["risk_pct"]
            sector = classified["data"]["sector"]
            pos_pct = classified["data"]["trade_plan"]["position_value"] / args.account_size * 100
            sector_tracker[sector] = sector_tracker.get(sector, 0.0) + pos_pct
        elif cls == "revalidation":
            revalidation.append(classified["data"])
        elif cls == "watchlist":
            watchlist.append(classified["data"])
        elif cls == "deferred":
            deferred.append(classified["data"])
        elif cls == "constrained":
            constrained.append(classified["data"])
        else:
            rejected.append(classified["data"])

    total_risk_dollars = sum(a["trade_plan"]["risk_dollars"] for a in actionable)
    total_risk_pct = total_risk_dollars / args.account_size * 100 if args.account_size > 0 else 0
    total_position = sum(a["trade_plan"]["position_value"] for a in actionable)

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "parameters": {
            "account_size": args.account_size,
            "base_risk_pct": args.risk_pct,
            "max_position_pct": args.max_position_pct,
            "max_sector_pct": args.max_sector_pct,
            "max_portfolio_heat_pct": args.max_portfolio_heat_pct,
            "target_r_multiple": args.target_r_multiple,
            "stop_buffer_pct": args.stop_buffer_pct,
            "max_chase_pct": args.max_chase_pct,
            "pivot_buffer_pct": args.pivot_buffer_pct,
            "current_exposure": exposure,
        },
        "input_metadata": {
            "source_file": args.input,
            "screener_generated_at": _get_nested(data, "metadata.generated_at"),
            "candidates_in_file": len(data["results"]),
            "screener_total_candidates": _get_nested(data, "summary.total"),
            "input_scope": "top_n_only",
        },
        "summary": {
            "actionable_count": len(actionable),
            "revalidation_count": len(revalidation),
            "watchlist_count": len(watchlist),
            "rejected_count": len(rejected),
            "deferred_count": len(deferred),
            "constrained_count": len(constrained),
            "total_risk_dollars": round(total_risk_dollars, 2),
            "total_risk_pct": round(total_risk_pct, 2),
            "total_position_value": round(total_position, 2),
        },
        "actionable_orders": actionable,
        "revalidation": revalidation,
        "watchlist": watchlist,
        "rejected": rejected,
        "deferred": deferred,
        "constrained": constrained,
        "warnings": warnings,
    }


def generate_markdown(plans: dict) -> str:
    """Generate human-readable markdown from plans."""
    lines = [
        "# Breakout Trade Plan",
        f"**Generated:** {plans['generated_at']}",
        f"**Account Size:** ${plans['parameters']['account_size']:,.0f} | "
        f"**Base Risk:** {plans['parameters']['base_risk_pct']}%",
        "",
        "## Summary",
        f"- Actionable: {plans['summary']['actionable_count']}",
        f"- Revalidation: {plans['summary']['revalidation_count']}",
        f"- Watchlist: {plans['summary']['watchlist_count']}",
        f"- Rejected: {plans['summary']['rejected_count']}",
        f"- Total Risk: ${plans['summary']['total_risk_dollars']:,.2f} "
        f"({plans['summary']['total_risk_pct']:.2f}%)",
        "",
    ]

    if plans["actionable_orders"]:
        lines.append("## Actionable Orders\n")
        for i, order in enumerate(plans["actionable_orders"], 1):
            tp = order["trade_plan"]
            lines.extend(
                [
                    f"### {i}. {order['symbol']} — {order.get('company_name', '')}",
                    f"**Rating:** {order['rating_band']} ({order['composite_score']}) | "
                    f"**State:** {order['execution_state']}",
                    "",
                    "| Parameter | Value |",
                    "|-----------|-------|",
                    f"| Signal Entry | ${tp['signal_entry']:.2f} |",
                    f"| Worst Entry | ${tp['worst_entry']:.2f} |",
                    f"| Stop Loss | ${tp['stop_loss_price']:.2f} |",
                    f"| Risk (worst) | {tp['risk_pct_worst']:.1f}% |",
                    f"| Target ({tp['reward_risk_ratio']}R) | ${tp['target_price']:.2f} |",
                    f"| Shares | {tp['shares']} |",
                    f"| Position Value | ${tp['position_value']:,.2f} |",
                    f"| Risk $ | ${tp['risk_dollars']:,.2f} |",
                    "",
                ]
            )

    if plans["revalidation"]:
        lines.append("## Revalidation (Breakout — needs live confirmation)\n")
        for r in plans["revalidation"]:
            lines.append(
                f"- **{r['symbol']}** — pivot ${r['pivot']:.2f}, "
                f"current ${r['current_price']:.2f}\n"
            )

    if plans["watchlist"]:
        lines.append("## Watchlist\n")
        lines.append("| Symbol | Score | Alert |")
        lines.append("|--------|-------|-------|")
        for w in plans["watchlist"]:
            lines.append(
                f"| {w['symbol']} | {w['composite_score']} | {w.get('alert_trigger', '')} |"
            )
        lines.append("")

    lines.append("\n---\n*Disclaimer: Not investment advice.*\n")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate breakout trade plans from VCP screener output"
    )
    parser.add_argument("--input", required=True, help="VCP screener JSON path")
    parser.add_argument("--account-size", type=float, required=True, help="Account equity ($)")
    parser.add_argument("--risk-pct", type=float, default=0.5, help="Base risk %% per trade")
    parser.add_argument("--max-position-pct", type=float, default=10.0)
    parser.add_argument("--max-sector-pct", type=float, default=30.0)
    parser.add_argument("--max-portfolio-heat-pct", type=float, default=6.0)
    parser.add_argument("--target-r-multiple", type=float, default=2.0)
    parser.add_argument("--stop-buffer-pct", type=float, default=1.0)
    parser.add_argument("--max-chase-pct", type=float, default=2.0)
    parser.add_argument("--pivot-buffer-pct", type=float, default=0.1)
    parser.add_argument("--current-exposure-json", default=None)
    parser.add_argument("--output-dir", default="reports/")
    args = parser.parse_args()

    data = load_input(args.input)
    plans = generate_plans(data, args)

    os.makedirs(args.output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")

    json_file = os.path.join(args.output_dir, f"breakout_trade_plan_{ts}.json")
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(plans, f, indent=2, default=str)
    print(f"JSON plan saved to: {json_file}")

    md_file = os.path.join(args.output_dir, f"breakout_trade_plan_{ts}.md")
    with open(md_file, "w", encoding="utf-8") as f:
        f.write(generate_markdown(plans))
    print(f"Markdown plan saved to: {md_file}")

    print(
        f"\nActionable: {plans['summary']['actionable_count']} | "
        f"Revalidation: {plans['summary']['revalidation_count']} | "
        f"Watchlist: {plans['summary']['watchlist_count']}"
    )


if __name__ == "__main__":
    main()
