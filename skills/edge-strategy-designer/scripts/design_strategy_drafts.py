#!/usr/bin/env python3
"""Design strategy drafts from abstract edge concepts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

EXPORTABLE_FAMILIES = {"pivot_breakout", "gap_up_continuation"}

ENTRY_TEMPLATE = {
    "pivot_breakout": {
        "conditions": [
            "close > high20_prev",
            "rel_volume >= 1.5",
            "close > ma50 > ma200",
        ],
        "trend_filter": [
            "price > sma_200",
            "price > sma_50",
            "sma_50 > sma_200",
        ],
    },
    "gap_up_continuation": {
        "conditions": [
            "gap_up_detected",
            "close_above_gap_day_high",
            "volume > 2.0 * avg_volume_50",
        ],
        "trend_filter": [
            "price > sma_200",
            "price > sma_50",
            "sma_50 > sma_200",
        ],
    },
}

RISK_PROFILES = {
    "conservative": {
        "risk_per_trade": 0.005,
        "max_positions": 3,
        "stop_loss_pct": 0.05,
        "take_profit_rr": 2.2,
    },
    "balanced": {
        "risk_per_trade": 0.01,
        "max_positions": 5,
        "stop_loss_pct": 0.07,
        "take_profit_rr": 3.0,
    },
    "aggressive": {
        "risk_per_trade": 0.015,
        "max_positions": 7,
        "stop_loss_pct": 0.09,
        "take_profit_rr": 3.5,
    },
}

VARIANT_OVERRIDES = {
    "core": {
        "entry_filter_note": "Use baseline confirmation and trend filter.",
        "risk_multiplier": 1.0,
    },
    "conservative": {
        "entry_filter_note": "Require stricter confirmation before entry.",
        "risk_multiplier": 0.75,
    },
    "research_probe": {
        "entry_filter_note": "Probe setup with small size for hypothesis validation.",
        "risk_multiplier": 0.5,
    },
}


class StrategyDesignError(Exception):
    """Raised when strategy design cannot proceed."""


def sanitize_identifier(value: str) -> str:
    """Convert free text into a safe identifier."""
    lowered = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    compact = "_".join(part for part in lowered.split("_") if part)
    return compact or "draft"


def safe_float(value: Any, default: float = 0.0) -> float:
    """Best-effort float conversion."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_concepts(path: Path) -> list[dict[str, Any]]:
    """Load concept YAML payload."""
    payload = yaml.safe_load(path.read_text())
    if not isinstance(payload, dict):
        raise StrategyDesignError("concept file must be a mapping")
    concepts = payload.get("concepts", [])
    if not isinstance(concepts, list):
        raise StrategyDesignError("concept file must contain concepts list")
    out: list[dict[str, Any]] = []
    for concept in concepts:
        if isinstance(concept, dict) and concept.get("id"):
            out.append(concept)
    return out


def resolve_variants(concept: dict[str, Any], variants_per_concept: int) -> list[str]:
    """Choose draft variants for a concept."""
    strategy_design = concept.get("strategy_design", {})
    export_ready = bool(strategy_design.get("export_ready_v1"))

    if export_ready:
        variants = ["core", "conservative"]
    else:
        variants = ["research_probe"]

    return variants[: max(variants_per_concept, 1)]


def resolve_entry_settings(concept: dict[str, Any]) -> tuple[str, dict[str, Any], bool]:
    """Resolve entry family and default conditions."""
    strategy_design = concept.get("strategy_design", {})
    family = strategy_design.get("recommended_entry_family")
    if isinstance(family, str) and family in ENTRY_TEMPLATE:
        return family, ENTRY_TEMPLATE[family], True

    return "research_only", {"conditions": [], "trend_filter": []}, False


def build_draft(
    concept: dict[str, Any],
    variant: str,
    risk_profile: str,
    as_of: str | None,
) -> dict[str, Any]:
    """Build one strategy draft from concept + variant."""
    concept_id = str(concept.get("id"))
    hypothesis_type = str(concept.get("hypothesis_type", "unknown"))
    mechanism_tag = str(concept.get("mechanism_tag", "uncertain"))
    regime = str(concept.get("regime", "Unknown"))
    support = concept.get("support", {}) if isinstance(concept.get("support"), dict) else {}
    abstraction = (
        concept.get("abstraction", {}) if isinstance(concept.get("abstraction"), dict) else {}
    )

    entry_family, entry_template, export_ready = resolve_entry_settings(concept)

    representative_conditions = support.get("representative_conditions", [])
    if isinstance(representative_conditions, list):
        merged_conditions = [
            c for c in representative_conditions if isinstance(c, str) and c.strip()
        ]
    else:
        merged_conditions = []
    if not merged_conditions:
        merged_conditions = list(entry_template.get("conditions", []))

    trend_filter = entry_template.get("trend_filter", [])
    if not isinstance(trend_filter, list):
        trend_filter = []

    risk_base = RISK_PROFILES[risk_profile]
    variant_override = VARIANT_OVERRIDES[variant]
    multiplier = safe_float(variant_override.get("risk_multiplier"), 1.0)

    risk_per_trade = round(risk_base["risk_per_trade"] * multiplier, 4)
    max_positions = max(int(round(risk_base["max_positions"] * multiplier)), 1)
    stop_loss_pct = risk_base["stop_loss_pct"]
    take_profit_rr = risk_base["take_profit_rr"]

    draft_id = sanitize_identifier(f"draft_{concept_id}_{variant}")

    return {
        "id": draft_id,
        "as_of": as_of,
        "concept_id": concept_id,
        "variant": variant,
        "name": f"{concept.get('title', concept_id)} ({variant})",
        "hypothesis_type": hypothesis_type,
        "mechanism_tag": mechanism_tag,
        "regime": regime,
        "export_ready_v1": bool(export_ready and entry_family in EXPORTABLE_FAMILIES),
        "entry_family": entry_family,
        "entry": {
            "conditions": merged_conditions,
            "trend_filter": trend_filter,
            "note": variant_override["entry_filter_note"],
        },
        "exit": {
            "stop_loss_pct": stop_loss_pct,
            "take_profit_rr": take_profit_rr,
            "time_stop_days": 20 if hypothesis_type in {"breakout", "futures_trigger"} else 10,
        },
        "risk": {
            "position_sizing": "fixed_risk",
            "risk_per_trade": risk_per_trade,
            "max_positions": max_positions,
            "max_sector_exposure": 0.3,
        },
        "validation_plan": {
            "period": "2016-01-01 to latest",
            "entry_timing": "next_open",
            "hold_days": [5, 20, 60],
            "success_criteria": [
                "expected_value_after_costs > 0",
                "stable across regimes and subperiods",
                "passes pipeline phase1 gates",
            ],
        },
        "thesis": str(abstraction.get("thesis", "")),
        "invalidation_signals": abstraction.get("invalidation_signals", []),
    }


def build_export_ticket(draft: dict[str, Any]) -> dict[str, Any]:
    """Build exportable ticket from strategy draft."""
    ticket_id = sanitize_identifier(draft["id"].replace("draft_", "edge_"))
    entry_family = draft["entry_family"]
    hypothesis_type = str(draft.get("hypothesis_type", "unknown"))

    if entry_family == "pivot_breakout" and hypothesis_type == "unknown":
        hypothesis_type = "breakout"
    if entry_family == "gap_up_continuation" and hypothesis_type == "unknown":
        hypothesis_type = "earnings_drift"

    return {
        "id": ticket_id,
        "name": draft["name"],
        "description": f"Draft-derived ticket from concept {draft['concept_id']} ({draft['variant']}).",
        "hypothesis_type": hypothesis_type,
        "entry_family": entry_family,
        "mechanism_tag": draft.get("mechanism_tag", "uncertain"),
        "regime": draft.get("regime", "Neutral"),
        "holding_horizon": "20D",
        "entry": {
            "conditions": draft.get("entry", {}).get("conditions", []),
            "trend_filter": draft.get("entry", {}).get("trend_filter", []),
        },
        "risk": draft.get("risk", {}),
        "exit": {
            "stop_loss_pct": draft.get("exit", {}).get("stop_loss_pct", 0.07),
            "take_profit_rr": draft.get("exit", {}).get("take_profit_rr", 3.0),
        },
        "cost_model": {
            "commission_per_share": 0.0,
            "slippage_bps": 5,
        },
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(
        description="Design strategy drafts from edge concepts.",
    )
    parser.add_argument("--concepts", required=True, help="Path to edge_concepts.yaml")
    parser.add_argument(
        "--output-dir",
        default="reports/edge_strategy_drafts",
        help="Output directory for strategy draft YAML files",
    )
    parser.add_argument(
        "--risk-profile",
        default="balanced",
        choices=sorted(RISK_PROFILES.keys()),
        help="Risk profile applied to generated drafts",
    )
    parser.add_argument(
        "--variants-per-concept",
        type=int,
        default=2,
        help="Maximum variants to generate per concept",
    )
    parser.add_argument(
        "--exportable-tickets-dir",
        default=None,
        help="Optional directory to write exportable ticket YAML files",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()
    concepts_path = Path(args.concepts).resolve()
    output_dir = Path(args.output_dir).resolve()
    exportable_tickets_dir = (
        Path(args.exportable_tickets_dir).resolve() if args.exportable_tickets_dir else None
    )

    if not concepts_path.exists():
        print(f"[ERROR] concepts file not found: {concepts_path}")
        return 1

    try:
        concepts = load_concepts(concepts_path)
        if not concepts:
            raise StrategyDesignError("no concepts available in file")

        source_payload = yaml.safe_load(concepts_path.read_text())
        as_of = source_payload.get("as_of") if isinstance(source_payload, dict) else None

        output_dir.mkdir(parents=True, exist_ok=True)
        if exportable_tickets_dir is not None:
            exportable_tickets_dir.mkdir(parents=True, exist_ok=True)

        draft_count = 0
        exportable_ticket_count = 0

        for concept in concepts:
            variants = resolve_variants(
                concept=concept, variants_per_concept=args.variants_per_concept
            )
            for variant in variants:
                draft = build_draft(
                    concept=concept,
                    variant=variant,
                    risk_profile=args.risk_profile,
                    as_of=as_of,
                )
                draft_path = output_dir / f"{draft['id']}.yaml"
                draft_path.write_text(yaml.safe_dump(draft, sort_keys=False))
                draft_count += 1

                if draft.get("export_ready_v1") and exportable_tickets_dir is not None:
                    ticket = build_export_ticket(draft)
                    ticket_path = exportable_tickets_dir / f"{ticket['id']}.yaml"
                    ticket_path.write_text(yaml.safe_dump(ticket, sort_keys=False))
                    exportable_ticket_count += 1

        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "concepts_file": str(concepts_path),
            "risk_profile": args.risk_profile,
            "draft_count": draft_count,
            "exportable_ticket_count": exportable_ticket_count,
            "output_dir": str(output_dir),
            "exportable_tickets_dir": str(exportable_tickets_dir)
            if exportable_tickets_dir
            else None,
        }
        (output_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    except StrategyDesignError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(
        "[OK] "
        f"drafts={draft_count} exportable_tickets={exportable_ticket_count} "
        f"output_dir={output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
