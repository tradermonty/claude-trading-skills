#!/usr/bin/env python3
"""Export research tickets to trade-strategy-pipeline candidate artifacts."""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from candidate_contract import (
    INTERFACE_VERSION,
    read_yaml,
    validate_interface_contract,
    validate_ticket_payload,
    write_yaml,
)

DEFAULT_UNIVERSE = {
    "type": "us_equities",
    "index": "sp500",
    "filters": ["avg_volume > 500_000", "price > 10"],
}

DEFAULT_DATA = {
    "timeframe": "daily",
    "lookback_years": 8,
}

DEFAULT_RISK = {
    "position_sizing": "fixed_risk",
    "risk_per_trade": 0.01,
    "max_positions": 5,
    "max_sector_exposure": 0.30,
}

DEFAULT_COST_MODEL = {
    "commission_per_share": 0.00,
    "slippage_bps": 5,
}

DEFAULT_PROMOTION_GATES = {
    "min_trades": 200,
    "max_drawdown": 0.15,
    "sharpe": 1.0,
    "profit_factor": 1.2,
}

DEFAULT_EXIT = {
    "stop_loss": "7% below entry",
    "trailing_stop": "below 21-day EMA or 10-day low",
    "take_profit": "risk_reward_3x",
    "stop_loss_pct": 0.07,
    "take_profit_rr": 3.0,
    "breakeven_at_rr": 1.0,
    "trailing_start_bars": 0,
}

DEFAULT_ENTRY_BY_FAMILY = {
    "pivot_breakout": {
        "conditions": [
            "vcp_pattern_detected",
            "breakout_above_pivot_point",
            "volume > 1.5 * avg_volume_50",
        ],
        "trend_filter": ["price > sma_200", "price > sma_50", "sma_50 > sma_200"],
    },
    "gap_up_continuation": {
        "conditions": [
            "gap_up_detected",
            "close_above_gap_day_high",
            "volume > 2.0 * avg_volume_50",
        ],
        "trend_filter": ["price > sma_200", "price > sma_50", "sma_50 > sma_200"],
    },
}

DEFAULT_VCP_DETECTION = {
    "min_contractions": 2,
    "contraction_ratio": 0.75,
    "lookback_window": 120,
    "swing_threshold": 0.05,
    "volume_decline": True,
    "breakout_volume_ratio": 1.5,
    "rolling_window_size": 300,
    "rolling_step_size": 15,
    "rolling_cooldown": 30,
    "atr_multiplier": 1.5,
    "atr_period": 14,
    "min_contraction_days": 5,
    "t1_depth_min": 0.10,
    "t1_depth_max": 0.35,
    "right_shoulder_pct": 0.05,
    "min_pattern_days": 15,
    "max_pattern_days": 325,
    "trend_min_criteria": 6,
}

DEFAULT_GAP_DETECTION = {
    "min_gap_pct": 0.06,
    "volume_ratio": 2.0,
    "avg_volume_window": 50,
    "max_entry_days": 5,
    "breakout_volume_ratio": 1.0,
    "max_stop_pct": 0.10,
    "breakout_close_pos_min": 0.5,
}


class ExportError(Exception):
    """Raised when export cannot proceed safely."""


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge two dictionaries."""
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def build_strategy_spec(ticket: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    """Build a Phase I-compatible strategy.yaml payload."""
    entry_family = ticket["entry_family"]

    entry_defaults = DEFAULT_ENTRY_BY_FAMILY[entry_family]
    entry_overrides = ticket.get("entry", {})
    exit_overrides = ticket.get("exit", {})

    if "validation" in ticket:
        validation = ticket["validation"]
        if validation.get("method", "full_sample") != "full_sample":
            raise ExportError("ticket.validation.method must be 'full_sample' for Phase I export")
        if validation.get("oos_ratio") is not None:
            raise ExportError(
                "ticket.validation.oos_ratio must be omitted or null for Phase I export"
            )

    spec: dict[str, Any] = {
        "id": candidate_id,
        "name": ticket.get("name", candidate_id.replace("_", " ").replace("-", " ").title()),
        "description": ticket.get(
            "description",
            f"Auto-generated from ticket {ticket['id']} ({ticket['hypothesis_type']})",
        ),
        "universe": deep_merge(DEFAULT_UNIVERSE, ticket.get("universe", {})),
        "data": deep_merge(DEFAULT_DATA, ticket.get("data", {})),
        "signals": {
            "entry": {
                "type": entry_family,
                "conditions": entry_overrides.get("conditions", entry_defaults["conditions"]),
                "trend_filter": entry_overrides.get("trend_filter", entry_defaults["trend_filter"]),
            },
            "exit": deep_merge(DEFAULT_EXIT, exit_overrides),
        },
        "risk": deep_merge(DEFAULT_RISK, ticket.get("risk", {})),
        "cost_model": deep_merge(DEFAULT_COST_MODEL, ticket.get("cost_model", {})),
        "validation": {"method": "full_sample"},
        "promotion_gates": deep_merge(DEFAULT_PROMOTION_GATES, ticket.get("promotion_gates", {})),
    }

    detection = ticket.get("detection", {})
    if entry_family == "pivot_breakout":
        spec["vcp_detection"] = deep_merge(
            DEFAULT_VCP_DETECTION,
            detection.get("vcp_detection", ticket.get("vcp_detection", {})),
        )
    if entry_family == "gap_up_continuation":
        spec["gap_up_detection"] = deep_merge(
            DEFAULT_GAP_DETECTION,
            detection.get("gap_up_detection", ticket.get("gap_up_detection", {})),
        )

    strategy_overrides = ticket.get("strategy_overrides", {})
    if strategy_overrides:
        if not isinstance(strategy_overrides, dict):
            raise ExportError("ticket.strategy_overrides must be a mapping when provided")
        spec = deep_merge(spec, strategy_overrides)

    return spec


def build_metadata(
    ticket: dict[str, Any],
    candidate_id: str,
    ticket_path: Path,
    generator_version: str,
) -> dict[str, Any]:
    """Build metadata.json payload."""
    return {
        "interface_version": INTERFACE_VERSION,
        "candidate_id": candidate_id,
        "generated_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "generator": {
            "name": "edge-candidate-agent",
            "version": generator_version,
            "source_ticket_path": str(ticket_path),
        },
        "research_context": {
            "ticket_id": ticket["id"],
            "hypothesis_type": ticket["hypothesis_type"],
            "mechanism_tag": ticket.get("mechanism_tag", "uncertain"),
            "holding_horizon": ticket.get("holding_horizon", "20D"),
            "entry_family": ticket["entry_family"],
            "regime": ticket.get("regime", "Neutral"),
        },
    }


def export_candidate(
    ticket_path: Path,
    strategies_dir: Path,
    candidate_id: str | None = None,
    force: bool = False,
    dry_run: bool = False,
    generator_version: str = "0.1.0",
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Export candidate artifacts and return in-memory payloads."""
    ticket = read_yaml(ticket_path)
    ticket_errors = validate_ticket_payload(ticket)
    if ticket_errors:
        raise ExportError("Ticket validation failed:\n- " + "\n- ".join(ticket_errors))

    resolved_candidate_id = (candidate_id or ticket["id"]).strip()
    if not resolved_candidate_id:
        raise ExportError("candidate_id must not be empty")

    spec = build_strategy_spec(ticket, resolved_candidate_id)
    contract_errors = validate_interface_contract(
        spec,
        candidate_id=resolved_candidate_id,
        stage="phase1",
    )
    if contract_errors:
        raise ExportError(
            "Generated strategy does not satisfy contract:\n- " + "\n- ".join(contract_errors)
        )

    metadata = build_metadata(
        ticket=ticket,
        candidate_id=resolved_candidate_id,
        ticket_path=ticket_path,
        generator_version=generator_version,
    )

    candidate_dir = strategies_dir / resolved_candidate_id
    strategy_path = candidate_dir / "strategy.yaml"
    metadata_path = candidate_dir / "metadata.json"

    if (strategy_path.exists() or metadata_path.exists()) and not force:
        raise ExportError(
            f"candidate artifacts already exist: {candidate_dir} (use --force to overwrite)"
        )

    if not dry_run:
        candidate_dir.mkdir(parents=True, exist_ok=True)
        write_yaml(strategy_path, spec)
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=True) + "\n")

    return spec, metadata, candidate_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export edge research ticket to trade-strategy-pipeline candidate artifacts.",
    )
    parser.add_argument("--ticket", required=True, help="Path to ticket YAML file")
    parser.add_argument(
        "--strategies-dir",
        default="strategies",
        help="Output strategies root directory (default: strategies)",
    )
    parser.add_argument(
        "--candidate-id",
        default=None,
        help="Override candidate id (defaults to ticket.id)",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing artifacts")
    parser.add_argument(
        "--dry-run", action="store_true", help="Build and validate without writing files"
    )
    parser.add_argument(
        "--generator-version",
        default="0.1.0",
        help="Version string to write in metadata.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ticket_path = Path(args.ticket).resolve()
    strategies_dir = Path(args.strategies_dir).resolve()

    try:
        spec, metadata, candidate_dir = export_candidate(
            ticket_path=ticket_path,
            strategies_dir=strategies_dir,
            candidate_id=args.candidate_id,
            force=args.force,
            dry_run=args.dry_run,
            generator_version=args.generator_version,
        )
    except (ExportError, ValueError) as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"[OK] Candidate id: {spec['id']}")
    print(f"[OK] Entry family: {spec['signals']['entry']['type']}")
    print(f"[OK] Interface version: {metadata['interface_version']}")
    if args.dry_run:
        print("[OK] Dry-run completed. No files were written.")
    else:
        print(f"[OK] Wrote strategy.yaml: {candidate_dir / 'strategy.yaml'}")
        print(f"[OK] Wrote metadata.json: {candidate_dir / 'metadata.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
