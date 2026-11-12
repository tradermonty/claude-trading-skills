"""Step adapters for the strategy-research-pipeline workflow."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .artifacts import _artifact_paths
from .common import (
    ReplayError,
    _load_json,
    _require_mapping_keys,
    _require_non_empty_string,
    _run_cli,
    _write_json,
    _write_yaml,
    load_yaml,
)
from .normalize import _file_sha256


def _strategy_research_tickets(report_dir: Path) -> list[dict[str, Any]]:
    paths = sorted((report_dir / "tickets").glob("*/*.yaml"))
    tickets = [load_yaml(path) for path in paths]
    if len({ticket.get("id") for ticket in tickets}) != len(tickets):
        raise ReplayError("strategy research generated duplicate ticket IDs")
    return tickets


def _strategy_research_detect(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
    *,
    final: bool,
) -> dict[str, dict[str, Any]]:
    expected = {"edge_hints"} if final else set()
    if set(consumed) != expected:
        raise ReplayError(f"strategy research detection requires {sorted(expected)}")
    as_of = spec["fixed_timestamp"][:10]
    report_dir = work / "reports"
    command = [
        sys.executable,
        str(repo_root / "skills/edge-candidate-agent/scripts/auto_detect_candidates.py"),
        "--ohlcv",
        str(inputs["ohlcv"]),
        "--as-of",
        as_of,
        "--output-dir",
        str(report_dir),
    ]
    if final:
        command.extend(["--hints", consumed["edge_hints"]["files"]["canonical"]])
    _run_cli(command, repo_root)
    tickets = _strategy_research_tickets(report_dir)
    artifacts = _artifact_paths(stage, step["output_files"])
    if final:
        if not tickets:
            raise ReplayError("strategy research replay needs a final ticket for evaluation")
        payload = {
            "as_of": as_of,
            "ohlcv_sha256": _file_sha256(inputs["ohlcv"]),
            "hints_sha256": _file_sha256(Path(consumed["edge_hints"]["files"]["canonical"])),
            "tickets": tickets,
        }
        _write_json(Path(artifacts["final_research_tickets"]["files"]["canonical"]), payload)
    else:
        summary = _load_json(report_dir / "market_summary.json", "initial market summary")
        anomalies = _load_json(report_dir / "anomalies.json", "initial anomalies")
        _write_json(Path(artifacts["initial_market_summary"]["files"]["canonical"]), summary)
        _write_json(Path(artifacts["initial_anomalies"]["files"]["canonical"]), anomalies)
        _write_json(Path(artifacts["initial_tickets"]["files"]["canonical"]), tickets)
    return artifacts


def _strategy_research_detect_initial(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    return _strategy_research_detect(
        repo_root, spec, step, inputs, consumed, work, stage, final=False
    )


def _strategy_research_hints(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    del inputs
    if set(consumed) != {"initial_market_summary", "initial_anomalies"}:
        raise ReplayError("strategy research hints require initial summary and anomalies")
    output = work / "hints.yaml"
    _run_cli(
        [
            sys.executable,
            str(repo_root / "skills/edge-hint-extractor/scripts/build_hints.py"),
            "--market-summary",
            consumed["initial_market_summary"]["files"]["canonical"],
            "--anomalies",
            consumed["initial_anomalies"]["files"]["canonical"],
            "--as-of",
            spec["fixed_timestamp"][:10],
            "--output",
            str(output),
        ],
        repo_root,
    )
    hints = load_yaml(output)
    if hints.get("as_of") != spec["fixed_timestamp"][:10]:
        raise ReplayError("strategy research hints as_of differs from detector as_of")
    hints.pop("generated_at_utc", None)
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_yaml(Path(artifacts["edge_hints"]["files"]["canonical"]), hints)
    return artifacts


def _strategy_research_detect_final(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    return _strategy_research_detect(
        repo_root, spec, step, inputs, consumed, work, stage, final=True
    )


def _strategy_research_hold(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"final_research_tickets"}:
        raise ReplayError("strategy research evaluation requires final tickets")
    tickets_path = Path(consumed["final_research_tickets"]["files"]["canonical"])
    final = _load_json(tickets_path, "final research tickets")
    metrics = _require_mapping_keys(
        _load_json(inputs["backtest_metrics"], "strategy research backtest metrics"),
        label="strategy research backtest metrics",
        required={
            "ticket_id",
            "as_of",
            "universe",
            "period",
            "cost_assumptions",
            "source",
            "total_trades",
            "win_rate",
            "avg_win_pct",
            "avg_loss_pct",
            "max_drawdown_pct",
            "years_tested",
            "num_parameters",
            "slippage_tested",
        },
    )
    tickets = {ticket["id"]: ticket for ticket in final["tickets"]}
    ticket_id = _require_non_empty_string(metrics["ticket_id"], "backtest ticket_id")
    for field in ("universe", "period", "source"):
        _require_non_empty_string(metrics[field], f"backtest {field}")
    if not isinstance(metrics["cost_assumptions"], dict):
        raise ReplayError("backtest cost_assumptions must be a mapping")
    if metrics["slippage_tested"] is not True and metrics["slippage_tested"] is not False:
        raise ReplayError("backtest slippage_tested must be boolean")
    reasons = []
    ticket = tickets.get(ticket_id)
    if ticket is None:
        reasons.append("ticket ID is absent from final research tickets")
    if metrics["as_of"] != final["as_of"]:
        reasons.append("metrics as-of date differs from final detection")
    if ticket is not None:
        if ticket.get("observation", {}).get("symbol") not in metrics["universe"]:
            reasons.append("metrics universe does not identify the selected ticket symbol")
        test_spec = ticket.get("test_spec") or {}
        if metrics["period"] != test_spec.get("period"):
            reasons.append("metrics period differs from selected ticket test period")
        if metrics["cost_assumptions"] != test_spec.get("cost_model"):
            reasons.append("metrics costs differ from selected ticket cost model")
    if not metrics["slippage_tested"]:
        reasons.append("slippage was not separately tested")
    reasons.append("independent look-ahead, survivorship, and out-of-sample reviews are absent")
    reasons.append("fictional aggregate metrics are not separate backtest provenance")
    result = {
        "status": "HOLD",
        "evaluation_invoked": False,
        "reasons": reasons,
        "provenance": {
            "execution": "manual_contract_only",
            "ticket_id": ticket_id,
            "as_of": final["as_of"],
            "universe": metrics["universe"],
            "period": metrics["period"],
            "cost_assumptions": metrics["cost_assumptions"],
            "source": metrics["source"],
            "final_tickets_sha256": _file_sha256(tickets_path),
            "limitation": "No backtest or scoring CLI was executed; human review is required.",
        },
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["backtest_quality_assessment"]["files"]["canonical"]), result)
    return artifacts
