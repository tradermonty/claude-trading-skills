#!/usr/bin/env python3
"""Orchestrate the full edge research pipeline from detection to export."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

EXPORTABLE_FAMILIES = {"pivot_breakout", "gap_up_continuation"}

SCRIPT_PATHS = {
    "auto_detect": "skills/edge-candidate-agent/scripts/auto_detect_candidates.py",
    "hints": "skills/edge-hint-extractor/scripts/build_hints.py",
    "concepts": "skills/edge-concept-synthesizer/scripts/synthesize_edge_concepts.py",
    "drafts": "skills/edge-strategy-designer/scripts/design_strategy_drafts.py",
    "review": "skills/edge-strategy-reviewer/scripts/review_strategy_drafts.py",
    "export": "skills/edge-candidate-agent/scripts/export_candidate.py",
}

MAX_REVIEW_ITERATIONS = 2


class EdgePipelineError(Exception):
    """Raised when the pipeline cannot proceed."""


@dataclass
class TrackedDraft:
    """Track a draft through the review-revision loop."""

    draft_id: str
    file_path: Path
    verdict: str
    export_eligible: bool
    confidence_score: int


@dataclass
class ReviewLoopResult:
    """Accumulated results from the review-revision loop."""

    passed: list[TrackedDraft] = field(default_factory=list)
    rejected: list[TrackedDraft] = field(default_factory=list)
    downgraded: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------


def run_stage(stage: str, args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run an upstream skill script via subprocess."""
    if stage not in SCRIPT_PATHS:
        raise EdgePipelineError(f"unknown stage: {stage}")

    script_path = SCRIPT_PATHS[stage]
    cmd = [sys.executable, script_path] + args

    result = subprocess.run(
        cmd,
        text=True,
        capture_output=True,
        cwd=cwd,
    )

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise EdgePipelineError(f"stage '{stage}' failed (exit {result.returncode}): {detail}")

    return result


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


def load_drafts_from_dir(drafts_dir: Path) -> list[dict[str, Any]]:
    """Load all draft YAML files from a directory."""
    drafts: list[dict[str, Any]] = []
    for path in sorted(drafts_dir.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text())
        if isinstance(payload, dict) and payload.get("id"):
            drafts.append(payload)
    return drafts


def load_reviews_from_dir(reviews_dir: Path) -> list[dict[str, Any]]:
    """Load review results from a directory.

    Supports two formats:
    1. Consolidated: review.yaml / review.json with a top-level ``reviews`` list
       (output of edge-strategy-reviewer).
    2. Per-draft: individual {draft_id}_review.yaml files.
    """
    reviews: list[dict[str, Any]] = []

    # Format 1: consolidated review.yaml / review.json
    for name in ("review.yaml", "review.json"):
        consolidated = reviews_dir / name
        if consolidated.exists():
            payload = yaml.safe_load(consolidated.read_text())
            if isinstance(payload, dict) and isinstance(payload.get("reviews"), list):
                for r in payload["reviews"]:
                    if isinstance(r, dict) and r.get("draft_id"):
                        reviews.append(r)
                return reviews

    # Format 2: per-draft *_review.yaml files
    for path in sorted(reviews_dir.glob("*_review.yaml")):
        payload = yaml.safe_load(path.read_text())
        if isinstance(payload, dict) and payload.get("draft_id"):
            reviews.append(payload)
    return reviews


# ---------------------------------------------------------------------------
# Export logic
# ---------------------------------------------------------------------------


def should_export(draft: dict[str, Any]) -> bool:
    """Check if a draft is eligible for export."""
    return (
        bool(draft.get("export_ready_v1")) and draft.get("entry_family", "") in EXPORTABLE_FAMILIES
    )


def build_export_ticket(draft: dict[str, Any]) -> dict[str, Any]:
    """Build exportable ticket from strategy draft."""
    ticket_id = draft["id"].replace("draft_", "edge_")
    return {
        "id": ticket_id,
        "name": draft["name"],
        "description": f"Draft-derived ticket from concept {draft['concept_id']} ({draft['variant']}).",
        "hypothesis_type": draft.get("hypothesis_type", "unknown"),
        "entry_family": draft["entry_family"],
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


def export_draft(
    draft: dict[str, Any],
    draft_path: Path,
    strategies_dir: Path,
    exportable_tickets_dir: Path | None,
    dry_run: bool,
) -> str | None:
    """Export a single draft via the export_candidate script. Returns ticket_id or None."""
    ticket_id = draft["id"].replace("draft_", "edge_")

    # Try pre-generated ticket first
    ticket_path: Path | None = None
    if exportable_tickets_dir is not None:
        candidate_path = exportable_tickets_dir / f"{ticket_id}.yaml"
        if candidate_path.exists():
            ticket_path = candidate_path

    # Fall back to generating ticket from draft
    if ticket_path is None:
        ticket = build_export_ticket(draft)
        generated_path = draft_path.parent / f"{ticket_id}_export_ticket.yaml"
        generated_path.write_text(yaml.safe_dump(ticket, sort_keys=False))
        ticket_path = generated_path

    if dry_run:
        return ticket_id

    export_args = [
        "--ticket",
        str(ticket_path),
        "--strategies-dir",
        str(strategies_dir),
        "--force",
    ]
    run_stage("export", export_args)
    return ticket_id


# ---------------------------------------------------------------------------
# Revision logic
# ---------------------------------------------------------------------------


def apply_revisions(draft: dict[str, Any], instructions: list[str]) -> dict[str, Any]:
    """Apply heuristic revisions based on reviewer instructions."""
    revised = deepcopy(draft)
    entry = revised.get("entry", {})
    conditions = list(entry.get("conditions", []))

    for instruction in instructions:
        lower = instruction.lower()

        if "reduce entry conditions" in lower:
            conditions = conditions[:5]

        elif "add volume filter" in lower:
            if "avg_volume > 500000" not in conditions:
                conditions.append("avg_volume > 500000")

        elif "round precise thresholds" in lower:
            rounded: list[str] = []
            for cond in conditions:
                rounded.append(
                    re.sub(
                        r"(\d+)\.(\d+)",
                        lambda m: str(round(float(m.group(0)))),
                        cond,
                    )
                )
            conditions = rounded

    entry["conditions"] = conditions
    revised["entry"] = entry
    # variant and export_ready_v1 remain unchanged
    return revised


def downgrade_to_research_probe(draft: dict[str, Any]) -> dict[str, Any]:
    """Downgrade a draft to research_probe variant."""
    downgraded = deepcopy(draft)
    downgraded["variant"] = "research_probe"
    downgraded["export_ready_v1"] = False
    return downgraded


# ---------------------------------------------------------------------------
# Review-revision feedback loop
# ---------------------------------------------------------------------------


def run_review_loop(
    drafts_dir: Path,
    review_output_base: Path,
    max_iterations: int = MAX_REVIEW_ITERATIONS,
    strict_export: bool = False,
) -> ReviewLoopResult:
    """Run the review-revision feedback loop."""
    result = ReviewLoopResult()

    # Build initial draft map: draft_id → (draft_data, file_path)
    current_drafts: dict[str, tuple[dict[str, Any], Path]] = {}
    for path in sorted(drafts_dir.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text())
        if isinstance(payload, dict) and payload.get("id"):
            current_drafts[payload["id"]] = (payload, path)

    for iteration in range(max_iterations):
        if not current_drafts:
            break

        # Prepare drafts dir for this iteration's review
        iter_drafts_dir = review_output_base / f"review_input_iter_{iteration}"
        iter_drafts_dir.mkdir(parents=True, exist_ok=True)
        for draft_id, (draft_data, orig_path) in current_drafts.items():
            iter_draft_path = iter_drafts_dir / f"{draft_id}.yaml"
            iter_draft_path.write_text(yaml.safe_dump(draft_data, sort_keys=False))

        # Run review stage
        review_dir = review_output_base / f"reviews_iter_{iteration}"
        review_args = [
            "--drafts-dir",
            str(iter_drafts_dir),
            "--output-dir",
            str(review_dir),
        ]
        if strict_export:
            review_args.append("--strict-export")
        run_stage("review", review_args)

        # Load reviews
        reviews = load_reviews_from_dir(review_dir)
        review_map = {r["draft_id"]: r for r in reviews}

        next_drafts: dict[str, tuple[dict[str, Any], Path]] = {}

        for draft_id, (draft_data, file_path) in current_drafts.items():
            review = review_map.get(draft_id)
            if review is None:
                # No review found, treat as REVISE to retry
                next_drafts[draft_id] = (draft_data, file_path)
                continue

            verdict = review.get("verdict", "REJECT")
            confidence = int(review.get("confidence_score", 0))

            if verdict == "PASS":
                result.passed.append(
                    TrackedDraft(
                        draft_id=draft_id,
                        file_path=file_path,
                        verdict="PASS",
                        export_eligible=should_export(draft_data),
                        confidence_score=confidence,
                    )
                )
            elif verdict == "REJECT":
                result.rejected.append(
                    TrackedDraft(
                        draft_id=draft_id,
                        file_path=file_path,
                        verdict="REJECT",
                        export_eligible=False,
                        confidence_score=confidence,
                    )
                )
            elif verdict == "REVISE":
                instructions = review.get("revision_instructions", [])
                revised = apply_revisions(draft_data, instructions)
                # Write revised draft back to file
                file_path.write_text(yaml.safe_dump(revised, sort_keys=False))
                next_drafts[draft_id] = (revised, file_path)

        current_drafts = next_drafts

    # Downgrade remaining REVISE drafts
    for draft_id, (draft_data, file_path) in current_drafts.items():
        downgraded = downgrade_to_research_probe(draft_data)
        file_path.write_text(yaml.safe_dump(downgraded, sort_keys=False))
        result.downgraded.append(draft_id)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Orchestrate the full edge research pipeline.",
    )
    parser.add_argument(
        "--tickets-dir",
        default=None,
        help="Directory containing edge ticket YAML files",
    )
    parser.add_argument(
        "--market-summary",
        default=None,
        help="Path to market_summary.json",
    )
    parser.add_argument(
        "--anomalies",
        default=None,
        help="Path to anomalies.json",
    )
    parser.add_argument(
        "--from-ohlcv",
        default=None,
        help="Path to OHLCV CSV for auto_detect stage",
    )
    parser.add_argument(
        "--resume-from",
        default=None,
        choices=["drafts"],
        help="Resume pipeline from a specific stage",
    )
    parser.add_argument(
        "--review-only",
        action="store_true",
        help="Only run review loop on existing drafts",
    )
    parser.add_argument(
        "--drafts-dir",
        default=None,
        help="Path to existing drafts directory (for --resume-from or --review-only)",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/edge_pipeline",
        help="Output directory for pipeline artifacts",
    )
    parser.add_argument(
        "--risk-profile",
        default="balanced",
        choices=["conservative", "balanced", "aggressive"],
        help="Risk profile for strategy design",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without export stage",
    )
    parser.add_argument(
        "--max-review-iterations",
        type=int,
        default=MAX_REVIEW_ITERATIONS,
        help="Maximum review-revision iterations",
    )
    parser.add_argument(
        "--llm-ideas-file",
        default=None,
        metavar="PATH",
        help="YAML file of LLM hints, forwarded to hints stage",
    )
    parser.add_argument(
        "--promote-hints",
        action="store_true",
        default=False,
        help="Forward --promote-hints to concepts stage (full pipeline only)",
    )
    parser.add_argument(
        "--as-of",
        default=None,
        help="Target date YYYY-MM-DD forwarded to hints stage",
    )
    parser.add_argument(
        "--strict-export",
        action="store_true",
        default=False,
        help="Forward --strict-export to review stage (warn on export-eligible → REVISE)",
    )
    parser.add_argument(
        "--max-synthetic-ratio",
        type=float,
        default=None,
        help="Forward --max-synthetic-ratio to concepts stage (cap synthetic tickets)",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entrypoint."""
    args = parse_args()

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = f"edge_pipeline_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    started_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_at_utc": started_at,
        "status": "running",
        "input": {
            "tickets_dir": str(args.tickets_dir) if args.tickets_dir else None,
            "from_ohlcv": str(args.from_ohlcv) if args.from_ohlcv else None,
            "resume_from": args.resume_from,
            "review_only": args.review_only,
            "risk_profile": args.risk_profile,
            "dry_run": args.dry_run,
            "llm_ideas_file": str(args.llm_ideas_file) if args.llm_ideas_file else None,
            "promote_hints": args.promote_hints,
        },
        "stages": {},
    }

    try:
        tickets_dir = Path(args.tickets_dir).resolve() if args.tickets_dir else None
        drafts_dir: Path | None = Path(args.drafts_dir).resolve() if args.drafts_dir else None
        auto_detect_output: Path | None = None

        # --- auto_detect stage ---
        if args.from_ohlcv and not args.resume_from and not args.review_only:
            ohlcv_path = Path(args.from_ohlcv).resolve()
            auto_detect_output = output_dir / "tickets"
            auto_detect_args = [
                "--ohlcv",
                str(ohlcv_path),
                "--output-dir",
                str(auto_detect_output),
            ]
            run_stage("auto_detect", auto_detect_args)
            tickets_dir = auto_detect_output
            manifest["stages"]["auto_detect"] = {
                "status": "completed",
                "output": str(auto_detect_output),
            }

        # --- hints stage ---
        hints_output: Path | None = None
        if not args.resume_from and not args.review_only:
            hints_args: list[str] = []
            # Resolve market_summary / anomalies paths:
            # 1. Explicit CLI args take priority
            # 2. Fall back to auto_detect output when --from-ohlcv was used
            market_summary_path = (
                Path(args.market_summary).resolve()
                if args.market_summary
                else (auto_detect_output / "market_summary.json" if auto_detect_output else None)
            )
            anomalies_path = (
                Path(args.anomalies).resolve()
                if args.anomalies
                else (auto_detect_output / "anomalies.json" if auto_detect_output else None)
            )
            if market_summary_path and market_summary_path.exists():
                hints_args += ["--market-summary", str(market_summary_path)]
            if anomalies_path and anomalies_path.exists():
                hints_args += ["--anomalies", str(anomalies_path)]
            if args.llm_ideas_file:
                hints_args += ["--llm-ideas-file", str(Path(args.llm_ideas_file).resolve())]
            if args.as_of:
                hints_args += ["--as-of", args.as_of]
            hints_output_path = output_dir / "hints" / "hints.yaml"
            hints_args += ["--output", str(hints_output_path)]
            run_stage("hints", hints_args)
            hints_output = hints_output_path
            manifest["stages"]["hints"] = {"status": "completed", "output": str(hints_output_path)}

        # --- concepts stage ---
        concepts_output: Path | None = None
        if not args.resume_from and not args.review_only:
            if tickets_dir is None:
                raise EdgePipelineError("--tickets-dir or --from-ohlcv required for concepts stage")
            concepts_output_path = output_dir / "concepts" / "edge_concepts.yaml"
            concepts_args = [
                "--tickets-dir",
                str(tickets_dir),
                "--output",
                str(concepts_output_path),
            ]
            if hints_output and hints_output.exists():
                concepts_args += ["--hints", str(hints_output)]
            if args.promote_hints:
                concepts_args += ["--promote-hints"]
            if args.max_synthetic_ratio is not None:
                concepts_args += ["--max-synthetic-ratio", str(args.max_synthetic_ratio)]
            run_stage("concepts", concepts_args)
            concepts_output = concepts_output_path
            manifest["stages"]["concepts"] = {
                "status": "completed",
                "output": str(concepts_output_path),
            }

        # --- drafts stage ---
        exportable_tickets_dir: Path | None = None
        if not args.resume_from and not args.review_only:
            if concepts_output is None:
                raise EdgePipelineError("concepts output required for drafts stage")
            drafts_output = output_dir / "drafts"
            exportable_tickets_dir = output_dir / "exportable_tickets"
            drafts_args = [
                "--concepts",
                str(concepts_output),
                "--output-dir",
                str(drafts_output),
                "--risk-profile",
                args.risk_profile,
                "--exportable-tickets-dir",
                str(exportable_tickets_dir),
            ]
            run_stage("drafts", drafts_args)
            drafts_dir = drafts_output
            manifest["stages"]["drafts"] = {"status": "completed", "output": str(drafts_output)}

        # --- review-revision loop ---
        if drafts_dir is None:
            raise EdgePipelineError(
                "--drafts-dir required when using --resume-from or --review-only"
            )

        review_result = run_review_loop(
            drafts_dir=drafts_dir,
            review_output_base=output_dir,
            max_iterations=args.max_review_iterations,
            strict_export=args.strict_export,
        )

        manifest["stages"]["review_loop"] = {
            "status": "completed",
            "passed_count": len(review_result.passed),
            "rejected_count": len(review_result.rejected),
            "downgraded_count": len(review_result.downgraded),
            "passed_ids": [td.draft_id for td in review_result.passed],
            "rejected_ids": [td.draft_id for td in review_result.rejected],
            "downgraded_ids": review_result.downgraded,
        }

        # --- export stage ---
        exported: list[str] = []
        skipped: list[str] = []

        if not args.dry_run:
            strategies_dir = output_dir / "strategies"
            strategies_dir.mkdir(parents=True, exist_ok=True)

            for td in review_result.passed:
                draft_data = yaml.safe_load(td.file_path.read_text())
                if not isinstance(draft_data, dict):
                    skipped.append(td.draft_id)
                    continue

                if should_export(draft_data):
                    ticket_id = export_draft(
                        draft=draft_data,
                        draft_path=td.file_path,
                        strategies_dir=strategies_dir,
                        exportable_tickets_dir=exportable_tickets_dir,
                        dry_run=False,
                    )
                    if ticket_id:
                        exported.append(ticket_id)
                else:
                    skipped.append(td.draft_id)
        else:
            for td in review_result.passed:
                draft_data = (
                    yaml.safe_load(td.file_path.read_text()) if td.file_path.exists() else {}
                )
                if isinstance(draft_data, dict) and should_export(draft_data):
                    exported.append(td.draft_id)
                else:
                    skipped.append(td.draft_id)

        manifest["stages"]["export"] = {
            "status": "completed" if not args.dry_run else "skipped_dry_run",
            "exported": exported,
            "skipped_not_eligible": skipped,
        }

        manifest["status"] = "completed"

    except EdgePipelineError as exc:
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        print(f"[ERROR] {exc}", file=sys.stderr)
        manifest_path = output_dir / "pipeline_run_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        return 1

    manifest_path = output_dir / "pipeline_run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(
        f"[OK] pipeline={run_id} "
        f"passed={len(review_result.passed)} "
        f"rejected={len(review_result.rejected)} "
        f"downgraded={len(review_result.downgraded)} "
        f"exported={len(exported)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
