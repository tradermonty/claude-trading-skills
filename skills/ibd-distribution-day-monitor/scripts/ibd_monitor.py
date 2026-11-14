#!/usr/bin/env python3
"""IBD Distribution Day Monitor — CLI entrypoint.

Workflow:
  1. Resolve config (default.yaml under config/, optional --config override).
  2. Fetch OHLCV for each symbol via FMP.
  3. Rebase via prepare_effective_history (as_of normalization).
  4. Detect, enrich, count active DDs (d5/d15/d25).
  5. Compute MA filters (21EMA / 50SMA) -> market_below_ma flag.
  6. Classify per-index risk and combine to overall risk.
  7. Generate portfolio action for the configured instrument.
  8. Write JSON + Markdown reports to --output-dir.

API key resolution order: --api-key > config.data.api_key > $FMP_API_KEY.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# pyyaml may not be installed in all envs (pyproject does include it).
import yaml  # type: ignore

# Local imports — relative to scripts/ directory.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from data_loader import build_fmp_client, fetch_ohlcv  # noqa: E402
from distribution_day_tracker import (  # noqa: E402
    count_active_in_window,
    detect_distribution_days,
    enrich_records,
)
from exposure_policy import generate_portfolio_action  # noqa: E402
from history_utils import prepare_effective_history  # noqa: E402
from math_utils import calc_ema, calc_sma  # noqa: E402
from models import DDRecord, DistributionDayRule, IndexResult, RiskThresholds  # noqa: E402
from report_generator import write_json, write_markdown  # noqa: E402
from risk_classifier import classify_risk, combine_index_risks  # noqa: E402

SKILL_ID = "ibd-distribution-day-monitor"
REPORT_PREFIX = "ibd_distribution_day_monitor"
RULE_VERSION = "ibd_dd_v1.0"
DEFAULT_CONFIG_PATH = HERE.parent / "config" / "default.yaml"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbols", default=None, help="Comma-separated, e.g. QQQ,SPY")
    p.add_argument("--lookback-days", type=int, default=None)
    p.add_argument("--instrument", default=None, help="TQQQ or QQQ")
    p.add_argument("--current-exposure", type=int, default=None)
    p.add_argument("--base-trailing-stop", type=int, default=None)
    p.add_argument("--as-of", default=None, help="YYYY-MM-DD; default = latest session")
    p.add_argument("--config", default=None)
    p.add_argument("--api-key", default=None)
    p.add_argument("--output-dir", default="reports/")
    return p.parse_args(argv)


def load_config(path: str | None) -> dict:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise FileNotFoundError(f"config not found: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def resolve_api_key(cli_key: str | None, config: dict) -> str:
    """API key precedence: CLI > config.data.api_key > $FMP_API_KEY."""
    if cli_key:
        return cli_key
    cfg_key = ((config.get("data") or {}).get("api_key")) or None
    if cfg_key:
        return cfg_key
    env_key = os.getenv("FMP_API_KEY")
    if env_key:
        return env_key
    raise ValueError("FMP API key required. Pass --api-key or set FMP_API_KEY env var.")


def _build_rule(config: dict) -> DistributionDayRule:
    rule_cfg = config.get("distribution_day_rule") or {}
    return DistributionDayRule(
        min_decline_pct=rule_cfg.get("min_decline_pct", -0.002),
        expiration_sessions=rule_cfg.get("expiration_sessions", 25),
        invalidation_gain_pct=rule_cfg.get("invalidation_gain_pct", 0.05),
        invalidation_price_source=rule_cfg.get("invalidation_price_source", "high"),
    )


def _build_thresholds(config: dict) -> RiskThresholds:
    t_cfg = config.get("risk_thresholds") or {}
    high = t_cfg.get("high") or {}
    severe = t_cfg.get("severe") or {}
    return RiskThresholds(
        caution_d25=(t_cfg.get("caution") or {}).get("d25_count", 3),
        high_d25=high.get("d25_count", 5),
        high_d15=high.get("d15_count", 3),
        high_d5=high.get("d5_count", 2),
        severe_d25=severe.get("d25_count", 6),
        severe_d15=severe.get("d15_count", 4),
        severe_ma_d25=severe.get("severe_ma_d25", 5),
    )


def _required_min_sessions(config: dict, rule: DistributionDayRule) -> int:
    lookback = config.get("lookback_days", 80)
    ma_cfg = config.get("moving_average_filters") or {}
    sma_periods = ma_cfg.get("sma_periods") or []
    ema_periods = ma_cfg.get("ema_periods") or []
    return max(
        int(lookback),
        max(sma_periods, default=0),
        max(ema_periods, default=0),
        rule.expiration_sessions + 2,
    )


def _compute_ma_filters(effective_history: list[dict], ma_cfg: dict) -> tuple[dict, list[str]]:
    """Compute close_above_21ema, close_above_50sma, market_below_21ema_or_50ma."""
    audit_flags: list[str] = []
    if not ma_cfg.get("enabled", True) or not effective_history:
        return {
            "close_above_21ema": None,
            "close_above_50sma": None,
            "market_below_21ema_or_50ma": None,
        }, audit_flags

    closes = [row["close"] for row in effective_history]
    today_close = closes[0]

    ema_period = (ma_cfg.get("ema_periods") or [21])[0]
    sma_period = (ma_cfg.get("sma_periods") or [50])[0]

    def _ma_or_none(fn, period):
        if len(closes) < period:
            return None
        try:
            return fn(closes, period)
        except ValueError:
            return None

    ema_val = _ma_or_none(calc_ema, ema_period)
    sma_val = _ma_or_none(calc_sma, sma_period)

    close_above_ema = (today_close > ema_val) if ema_val is not None else None
    close_above_sma = (today_close > sma_val) if sma_val is not None else None

    if close_above_ema is None or close_above_sma is None:
        audit_flags.append("insufficient_data_for_moving_average")
        market_below = None
    else:
        # market_below = True only when close is below BOTH MAs
        market_below = (not close_above_ema) and (not close_above_sma)

    return {
        "close_above_21ema": close_above_ema,
        "close_above_50sma": close_above_sma,
        "market_below_21ema_or_50ma": market_below,
    }, audit_flags


def _record_to_dict(r: DDRecord) -> dict:
    return asdict(r)


def _today_dict(effective_history: list[dict], records: list[DDRecord]) -> dict:
    """Return summary fields for the evaluation session."""
    if not effective_history:
        return {}
    today = effective_history[0]
    yesterday = effective_history[1] if len(effective_history) > 1 else None
    pct_change = None
    volume_change_pct = None
    if yesterday and today.get("close") and yesterday.get("close"):
        pct_change = today["close"] / yesterday["close"] - 1
    if yesterday and today.get("volume") and yesterday.get("volume"):
        volume_change_pct = today["volume"] / yesterday["volume"] - 1
    return {
        "date": today.get("date"),
        "close": today.get("close"),
        "previous_close": yesterday.get("close") if yesterday else None,
        "pct_change": pct_change,
        "volume": today.get("volume"),
        "previous_volume": yesterday.get("volume") if yesterday else None,
        "volume_change_pct": volume_change_pct,
    }


def _build_explanation(symbol: str, d5: int, d15: int, d25: int, risk: str, today_dd: bool) -> str:
    parts = []
    parts.append(
        f"{symbol}は本日{'Distribution Day該当' if today_dd else 'Distribution Day非該当'}。"
    )
    parts.append(f"5/15/25セッション経過以内の有効Distribution Dayはそれぞれ {d5}/{d15}/{d25} 件。")
    parts.append(f"リスク判定: {risk}。")
    return " ".join(parts)


def _build_cluster_state(d5: int, d15: int, d25: int) -> dict:
    return {
        "has_d5_cluster": d5 >= 2,
        "has_d15_cluster": d15 >= 3,
        "has_d25_cluster": d25 >= 5,
        "cluster_description": (f"5/15/25セッション経過以内: {d5}/{d15}/{d25}"),
    }


def analyze_index(
    symbol: str,
    benchmark_name: str,
    history: list[dict],
    config: dict,
    rule: DistributionDayRule,
    thresholds: RiskThresholds,
    as_of: str | None,
) -> tuple[IndexResult, list[str]]:
    """Run the full per-index pipeline and return the IndexResult."""
    required_min = _required_min_sessions(config, rule)
    effective_history, hist_audit = prepare_effective_history(history, as_of, required_min)
    audit_flags = list(hist_audit.get("audit_flags", []))

    raw_records, skipped = detect_distribution_days(effective_history, rule)
    records = enrich_records(raw_records, effective_history, rule)

    active = [r for r in records if r.status == "active"]
    removed = [r for r in records if r.status != "active"]

    d5 = count_active_in_window(records, 5)
    d15 = count_active_in_window(records, 15)
    d25 = count_active_in_window(records, 25)

    ma_cfg = config.get("moving_average_filters") or {}
    trend_filters, ma_flags = _compute_ma_filters(effective_history, ma_cfg)
    audit_flags.extend(ma_flags)

    market_below = trend_filters.get("market_below_21ema_or_50ma")
    risk = classify_risk(d5, d15, d25, market_below, thresholds)

    today_is_dd = any(r.dd_index == 0 and r.status == "active" for r in records)
    explanation = _build_explanation(symbol, d5, d15, d25, risk, today_is_dd)

    result = IndexResult(
        symbol=symbol,
        benchmark_name=benchmark_name,
        is_distribution_day_today=today_is_dd,
        today=_today_dict(effective_history, records),
        d5_count=d5,
        d15_count=d15,
        d25_count=d25,
        active_distribution_days=[_record_to_dict(r) for r in active],
        removed_distribution_days=[_record_to_dict(r) for r in removed],
        risk_level=risk,
        cluster_state=_build_cluster_state(d5, d15, d25),
        trend_filters=trend_filters,
        explanation=explanation,
        skipped_sessions=skipped,
    )
    return result, audit_flags


def build_payload(
    config: dict,
    rule: DistributionDayRule,
    thresholds: RiskThresholds,
    index_results: list[IndexResult],
    overall_risk: str,
    portfolio_action: dict,
    aggregate_audit: dict,
) -> dict:
    """Assemble the final JSON payload."""
    primary = next((r.symbol for r in index_results if r.symbol == "QQQ"), None)
    if primary is None and index_results:
        primary = index_results[0].symbol

    return {
        "market_distribution_state": {
            "as_of": aggregate_audit.get("as_of_resolved"),
            "generated_at": aggregate_audit.get("generated_at"),
            "overall_risk_level": overall_risk,
            "primary_signal_symbol": primary,
            "index_results": [_index_result_to_dict(r) for r in index_results],
        },
        "portfolio_action": portfolio_action,
        "rule_evaluation": {
            "rule_version": RULE_VERSION,
            "distribution_day_rule": {
                "min_decline_pct": rule.min_decline_pct,
                "expiration_sessions": rule.expiration_sessions,
                "invalidation_gain_pct": rule.invalidation_gain_pct,
                "invalidation_price_source": rule.invalidation_price_source,
            },
            "thresholds_used": {
                "caution_d25": thresholds.caution_d25,
                "high_d25": thresholds.high_d25,
                "high_d15": thresholds.high_d15,
                "high_d5": thresholds.high_d5,
                "severe_d25": thresholds.severe_d25,
                "severe_d15": thresholds.severe_d15,
                "severe_ma_d25": thresholds.severe_ma_d25,
            },
        },
        "audit": aggregate_audit,
    }


def _index_result_to_dict(r: IndexResult) -> dict:
    return asdict(r)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config(args.config)

    # CLI overrides
    if args.symbols:
        config["symbols_override"] = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if args.lookback_days is not None:
        config["lookback_days"] = args.lookback_days
    if args.instrument:
        config.setdefault("strategy_context", {})["instrument"] = args.instrument
    if args.current_exposure is not None:
        config.setdefault("strategy_context", {})["current_exposure_pct"] = args.current_exposure
    if args.base_trailing_stop is not None:
        config.setdefault("strategy_context", {})["base_trailing_stop_pct"] = (
            args.base_trailing_stop
        )

    # Symbols / benchmark mapping
    indexes_cfg: list[dict] = config.get("indexes") or [
        {"symbol": "QQQ", "benchmark_name": "Nasdaq Proxy"},
        {"symbol": "SPY", "benchmark_name": "S&P500 Proxy"},
    ]
    if config.get("symbols_override"):
        wanted = {s.upper() for s in config["symbols_override"]}
        indexes_cfg = [i for i in indexes_cfg if i["symbol"].upper() in wanted] or [
            {"symbol": s, "benchmark_name": f"{s} proxy"} for s in config["symbols_override"]
        ]

    # FMP client
    try:
        api_key = resolve_api_key(args.api_key, config)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    client = build_fmp_client(api_key=api_key)

    rule = _build_rule(config)
    thresholds = _build_thresholds(config)
    lookback = int(config.get("lookback_days", 80))

    aggregate_audit_flags: list[str] = []
    symbols_loaded: list[str] = []
    skipped_sessions_all: list[dict] = []
    index_results: list[IndexResult] = []
    as_of_resolved: str | None = args.as_of

    for entry in indexes_cfg:
        symbol = entry["symbol"]
        benchmark = entry.get("benchmark_name") or f"{symbol} Proxy"
        history, fetch_audit = fetch_ohlcv(client, symbol, days=lookback + 5)
        aggregate_audit_flags.extend(fetch_audit.get("audit_flags", []))
        skipped_sessions_all.extend(fetch_audit.get("skipped_sessions", []))

        if not history:
            continue
        symbols_loaded.append(symbol)

        result, idx_flags = analyze_index(
            symbol=symbol,
            benchmark_name=benchmark,
            history=history,
            config=config,
            rule=rule,
            thresholds=thresholds,
            as_of=args.as_of,
        )
        aggregate_audit_flags.extend(idx_flags)
        skipped_sessions_all.extend(result.skipped_sessions)
        # Preserve as_of from the first successful index.
        if as_of_resolved is None and result.today.get("date"):
            as_of_resolved = result.today["date"]
        index_results.append(result)

    if not index_results:
        print("ERROR: no symbols loaded", file=sys.stderr)
        return 1

    overall_risk = combine_index_risks(index_results)

    strategy_ctx = config.get("strategy_context") or {}
    instrument = strategy_ctx.get("instrument", "TQQQ")
    current_exposure = int(strategy_ctx.get("current_exposure_pct", 100))
    base_trail = int(strategy_ctx.get("base_trailing_stop_pct", 10))
    portfolio_action_obj = generate_portfolio_action(
        risk_level=overall_risk,
        instrument=instrument,
        current_exposure_pct=current_exposure,
        base_trailing_stop_pct=base_trail,
    )

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    aggregate_audit = {
        "data_source": "fmp",
        "rule_version": RULE_VERSION,
        "as_of_resolved": as_of_resolved,
        "lookback_days": lookback,
        "symbols_requested": [i["symbol"] for i in indexes_cfg],
        "symbols_loaded": symbols_loaded,
        "skipped_sessions": skipped_sessions_all,
        "audit_flags": sorted(set(aggregate_audit_flags)),
        "generated_at": generated_at,
        "config_snapshot": {
            "data": config.get("data"),
            "lookback_days": lookback,
            "moving_average_filters": config.get("moving_average_filters"),
            "strategy_context": strategy_ctx,
        },
    }

    payload = build_payload(
        config=config,
        rule=rule,
        thresholds=thresholds,
        index_results=index_results,
        overall_risk=overall_risk,
        portfolio_action=asdict(portfolio_action_obj),
        aggregate_audit=aggregate_audit,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    json_path = output_dir / f"{REPORT_PREFIX}_{timestamp}.json"
    md_path = output_dir / f"{REPORT_PREFIX}_{timestamp}.md"
    write_json(payload, json_path)
    write_markdown(payload, md_path)
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
