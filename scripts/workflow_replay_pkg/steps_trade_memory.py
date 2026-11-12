"""Step adapters for the trade-memory-loop workflow."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from .artifacts import _artifact_paths, _latest_report
from .common import (
    ReplayError,
    _load_json,
    _repo_module,
    _require_finite_number,
    _require_mapping_keys,
    _require_non_empty_string,
    _run_cli,
    _trader_memory_modules,
    _write_json,
    _write_yaml,
    load_yaml,
)
from .normalize import _canonicalize, _exact_payload_sha256, _file_sha256, _payload_sha256


def _trade_memory_close(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    _consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    active = load_yaml(inputs["active_thesis"])
    instruction = load_yaml(inputs["close_instruction"])
    instruction = _require_mapping_keys(
        instruction,
        label="close instruction",
        required={"thesis_id", "exit_reason", "actual_price", "actual_date", "event_date"},
    )
    thesis_store, _review = _trader_memory_modules(repo_root)
    try:
        thesis_store.validate_thesis(active)
    except Exception as exc:
        raise ReplayError(f"invalid active thesis: {exc}") from exc
    if active.get("status") != "ACTIVE":
        raise ReplayError("trade-memory close input must have status ACTIVE")
    if instruction["thesis_id"] != active.get("thesis_id"):
        raise ReplayError("close instruction thesis_id does not match active thesis")

    state_dir = work / "trade-memory-state"
    state_dir.mkdir(parents=True)
    source = state_dir / f"{active['thesis_id']}.yaml"
    _write_yaml(source, active)
    script = repo_root / "skills" / "trader-memory-core" / "scripts" / "thesis_store.py"
    _run_cli(
        [
            sys.executable,
            str(script),
            "--state-dir",
            str(state_dir),
            "close",
            str(instruction["thesis_id"]),
            "--exit-reason",
            str(instruction["exit_reason"]),
            "--actual-price",
            str(instruction["actual_price"]),
            "--actual-date",
            str(instruction["actual_date"]),
            "--event-date",
            str(instruction["event_date"]),
        ],
        repo_root,
    )
    closed = load_yaml(source)
    try:
        thesis_store.validate_thesis(closed)
    except Exception as exc:
        raise ReplayError(f"native close produced invalid thesis: {exc}") from exc
    if closed.get("status") != "CLOSED":
        raise ReplayError("native close did not produce CLOSED thesis")

    artifacts = _artifact_paths(stage, step["output_files"])
    output = Path(artifacts["closed_thesis_record"]["files"]["canonical"])
    canonical = _canonicalize(closed, spec["fixed_timestamp"], {str(state_dir): "$STATE"})
    canonical["created_at"] = closed["created_at"]
    try:
        thesis_store.validate_thesis(canonical)
    except Exception as exc:
        raise ReplayError(f"normalized close artifact is invalid: {exc}") from exc
    _write_yaml(output, canonical)
    return artifacts


def _trade_memory_postmortem(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    _work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"closed_thesis_record"}:
        raise ReplayError("trade-memory postmortem requires closed_thesis_record")
    closed_path = Path(consumed["closed_thesis_record"]["files"]["canonical"])
    closed = load_yaml(closed_path)
    realized = _load_json(inputs["realized_returns"], "realized returns")
    realized = _require_mapping_keys(
        realized,
        label="realized returns",
        required={"schema_version", "trade_direction", "returns", "regime_at_exit"},
    )
    if realized["schema_version"] != 1 or realized["trade_direction"] not in {"LONG", "SHORT"}:
        raise ReplayError("invalid realized returns contract")
    returns = realized["returns"]
    if not isinstance(returns, dict) or set(returns) != {"5d", "20d"}:
        raise ReplayError("realized returns must contain exactly 5d and 20d")
    for horizon, value in returns.items():
        _require_finite_number(value, f"realized returns {horizon}")
    _require_non_empty_string(realized["regime_at_exit"], "realized returns regime_at_exit")

    position = closed.get("position") or {}
    expected_direction = (
        position.get("direction") if position.get("asset_type") == "futures" else "LONG"
    )
    if realized["trade_direction"] != expected_direction:
        raise ReplayError("realized returns trade_direction does not match thesis position")
    if closed.get("status") != "CLOSED":
        raise ReplayError("postmortem input thesis must be CLOSED")
    entry = closed.get("entry") or {}
    exit_data = closed.get("exit") or {}
    signal = {
        "signal_id": closed["thesis_id"],
        "ticker": closed["ticker"],
        "signal_date": str(entry["actual_date"])[:10],
        "predicted_direction": realized["trade_direction"],
        "source_skill": closed["origin"]["skill"],
        "entry_price": entry["actual_price"],
        "regime": (closed.get("market_context") or {}).get("regime") or "UNKNOWN",
    }
    recorder = _repo_module(
        repo_root,
        "postmortem_recorder",
        repo_root / "skills" / "signal-postmortem" / "scripts",
    )
    native = recorder.create_postmortem_record(
        signal,
        returns,
        exit_data["actual_price"],
        str(exit_data["actual_date"])[:10],
        regime_at_exit=str(realized["regime_at_exit"]),
    )
    native = _canonicalize(native, spec["fixed_timestamp"], {})

    root_decision = load_yaml(inputs["root_cause_decision"])
    root_decision = _require_mapping_keys(
        root_decision,
        label="root cause decision",
        required={
            "human_approved",
            "thesis_id",
            "expected_native_classification",
            "expected_source_sha256",
            "classification",
            "summary",
        },
    )
    if root_decision["human_approved"] is not True:
        raise ReplayError("root cause decision requires human_approved: true")
    if root_decision["thesis_id"] != closed["thesis_id"]:
        raise ReplayError("root cause decision thesis_id mismatch")
    if root_decision["expected_native_classification"] != native["outcome_category"]:
        raise ReplayError("root cause decision native classification mismatch")
    if root_decision["classification"] not in {
        "thesis_quality",
        "execution",
        "market_environment",
        "randomness",
    }:
        raise ReplayError("root cause decision classification is invalid")
    _require_non_empty_string(root_decision["summary"], "root cause decision summary")
    expected_hashes = root_decision["expected_source_sha256"]
    actual_hashes = {
        "closed_thesis_record": _file_sha256(closed_path),
        "realized_returns": _payload_sha256(realized, spec["fixed_timestamp"]),
        "native_postmortem_record": _payload_sha256(native, spec["fixed_timestamp"]),
    }
    if expected_hashes != actual_hashes:
        raise ReplayError(
            f"root cause decision source_sha256 mismatch: expected {expected_hashes}, "
            f"actual {actual_hashes}"
        )

    payload = {
        "schema_version": 1,
        "source_snapshot": {"closed_thesis_record": closed},
        "native_postmortem": native,
        "manual_root_cause": {
            "human_approved": True,
            "classification": root_decision["classification"],
            "summary": root_decision["summary"],
        },
        "provenance": {
            "execution_mode": "composite",
            "components": ["native_api", "manual_contract"],
            "native_component": "signal-postmortem.create_postmortem_record",
            "native_classification_basis": "fixture_supplied_realized_returns",
            "source_sha256": actual_hashes,
            "source_snapshot_sha256": {"closed_thesis_record": _exact_payload_sha256(closed)},
            "limitation": "Root cause is a human-approved fixture decision, not native inference.",
        },
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["postmortem_findings"]["files"]["canonical"]), payload)
    return artifacts


def _trade_memory_coach(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"closed_thesis_record", "postmortem_findings"}:
        raise ReplayError("trade-memory coach requires closed thesis and postmortem")
    closed = load_yaml(Path(consumed["closed_thesis_record"]["files"]["canonical"]))
    postmortem = _load_json(
        Path(consumed["postmortem_findings"]["files"]["canonical"]), "postmortem findings"
    )
    created_at = datetime.fromisoformat(str(closed["created_at"]).replace("Z", "+00:00"))
    entered_at = datetime.fromisoformat(str(closed["entry"]["actual_date"]).replace("Z", "+00:00"))
    coach_input = {
        "review_id": "trade-memory-loop-fictional-exmpl",
        "review_type": "single_trade",
        "trade_id": closed["thesis_id"],
        "outcome": postmortem["native_postmortem"]["outcome_category"],
        "planned": {
            "thesis": closed["thesis_statement"],
            "thesis_recorded_before_entry": created_at <= entered_at,
            "entry_price": closed["entry"]["actual_price"],
            "stop_price": closed["exit"]["stop_loss"],
            "market_regime": closed["market_context"]["regime"],
        },
        "actual": {
            "entry_price": closed["entry"]["actual_price"],
            "exit_price": closed["exit"]["actual_price"],
        },
        "postmortem": {
            "root_cause": postmortem["manual_root_cause"]["classification"],
            "root_cause_notes": postmortem["manual_root_cause"]["summary"],
        },
    }
    input_path = work / "coach-input.json"
    _write_json(input_path, coach_input)
    reports = work / "reports"
    script = (
        repo_root / "skills" / "trade-performance-coach" / "scripts" / "review_trade_performance.py"
    )
    _run_cli(
        [
            sys.executable,
            str(script),
            "--input",
            str(input_path),
            "--output-dir",
            str(reports),
            "--json-name",
            "coach.json",
        ],
        repo_root,
    )
    coach = _load_json(reports / "coach.json", "coach report")
    coach = _canonicalize(
        coach,
        spec["fixed_timestamp"],
        # The coach records source paths with forward slashes on every platform.
        {input_path.as_posix(): "$INPUT/coach-input.json"},
    )

    decision = load_yaml(inputs["coach_decision"])
    decision = _require_mapping_keys(
        decision,
        label="coach decision",
        required={"human_approved", "action", "expected_source_sha256", "accepted_rules"},
    )
    coach_sha = _payload_sha256(coach, spec["fixed_timestamp"])
    if decision["human_approved"] is not True:
        raise ReplayError("coach decision requires human_approved: true")
    if decision["expected_source_sha256"] != {"coach_report": coach_sha}:
        raise ReplayError(
            f"coach decision source_sha256 mismatch: expected "
            f"{decision['expected_source_sha256']}, actual {{'coach_report': {coach_sha!r}}}"
        )
    if decision["action"] not in coach["human_decision_gate"]["allowed_actions"]:
        raise ReplayError("coach decision action is not allowed by native report")
    accepted_rules = decision["accepted_rules"]
    if not isinstance(accepted_rules, list) or not all(
        isinstance(rule, str) and rule.strip() for rule in accepted_rules
    ):
        raise ReplayError("coach decision accepted_rules must be a list of non-empty strings")
    native_rules = {
        item["rule"]
        for item in coach["next_session_operating_rules"]
        if isinstance(item, Mapping) and isinstance(item.get("rule"), str)
    }
    action = decision["action"]
    if action == "accept_rules" and (
        not accepted_rules or not set(accepted_rules).issubset(native_rules)
    ):
        raise ReplayError(
            "coach decision accepted_rules must come from the native coach report; "
            f"available={sorted(native_rules)}"
        )
    if action in {"defer", "journal_only"} and accepted_rules:
        raise ReplayError(f"coach decision action {action!r} cannot accept rules")
    if action == "modify_rules" and not accepted_rules:
        raise ReplayError("coach decision action 'modify_rules' requires modified rules")

    artifacts = _artifact_paths(stage, step["output_files"])
    coach_out = Path(artifacts["performance_coach_report"]["files"]["canonical"])
    _write_json(coach_out, coach)
    rules = {
        "human_approved": True,
        "action": decision["action"],
        "accepted_rules": accepted_rules,
        "provenance": {
            "execution_mode": "manual_contract",
            "coach_report_sha256": _file_sha256(coach_out),
            "native_coach_default_action": coach["human_decision_gate"]["default_action"],
        },
    }
    _write_yaml(
        Path(artifacts["next_session_operating_rules"]["files"]["canonical"]),
        rules,
        digest_allowlist=True,
    )
    return artifacts


def _trade_memory_backtest(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"postmortem_findings"}:
        raise ReplayError("trade-memory backtest evaluation requires postmortem_findings")
    metrics = _load_json(inputs["backtest_metrics"], "backtest metrics")
    required = {
        "total_trades",
        "win_rate",
        "avg_win_pct",
        "avg_loss_pct",
        "max_drawdown_pct",
        "years_tested",
        "num_parameters",
        "slippage_tested",
    }
    metrics = _require_mapping_keys(metrics, label="backtest metrics", required=required)
    _require_finite_number(
        metrics["total_trades"], "backtest total_trades", minimum=0, integer=True
    )
    _require_finite_number(metrics["win_rate"], "backtest win_rate", minimum=0, maximum=100)
    _require_finite_number(metrics["avg_win_pct"], "backtest avg_win_pct", minimum=0)
    _require_finite_number(metrics["avg_loss_pct"], "backtest avg_loss_pct", minimum=0)
    _require_finite_number(
        metrics["max_drawdown_pct"], "backtest max_drawdown_pct", minimum=0, maximum=100
    )
    _require_finite_number(
        metrics["years_tested"], "backtest years_tested", minimum=0, integer=True
    )
    _require_finite_number(
        metrics["num_parameters"], "backtest num_parameters", minimum=0, integer=True
    )
    reports = work / "reports"
    script = repo_root / "skills" / "backtest-expert" / "scripts" / "evaluate_backtest.py"
    command = [
        sys.executable,
        str(script),
        "--total-trades",
        str(metrics["total_trades"]),
        "--win-rate",
        str(metrics["win_rate"]),
        "--avg-win-pct",
        str(metrics["avg_win_pct"]),
        "--avg-loss-pct",
        str(metrics["avg_loss_pct"]),
        "--max-drawdown-pct",
        str(metrics["max_drawdown_pct"]),
        "--years-tested",
        str(metrics["years_tested"]),
        "--num-parameters",
        str(metrics["num_parameters"]),
        "--output-dir",
        str(reports),
    ]
    if metrics["slippage_tested"] is True:
        command.append("--slippage-tested")
    elif metrics["slippage_tested"] is not False:
        raise ReplayError("backtest metrics slippage_tested must be boolean")
    _run_cli(command, repo_root)
    result_path = _latest_report(reports, "backtest_eval_*.json")
    result = _load_json(result_path, "backtest evaluation")
    postmortem_path = Path(consumed["postmortem_findings"]["files"]["canonical"])
    result["provenance"] = {
        "execution": "native_cli_evaluated_fixture_metrics",
        "metrics_source": "bundled fictional aggregate metrics",
        "adapter_bound_source_sha256": {"postmortem_source_sha256": _file_sha256(postmortem_path)},
        "limitation": (
            "The native CLI evaluated supplied aggregate metrics; it did not run a strategy "
            "backtest or consume the postmortem."
        ),
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["backtest_validation"]["files"]["canonical"]), result)
    return artifacts


def _without_lesson_side_effects(thesis: Mapping[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(thesis))
    clone.pop("updated_at", None)
    outcome = clone.get("outcome") or {}
    for key in ("lessons_learned", "mae_pct", "mfe_pct", "mae_mfe_source"):
        outcome.pop(key, None)
    return clone


def _trade_memory_lessons(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if "postmortem_findings" not in consumed:
        raise ReplayError("trade-memory lessons requires postmortem_findings")
    unexpected = set(consumed) - {"postmortem_findings", "backtest_validation"}
    if unexpected:
        raise ReplayError(
            f"trade-memory lessons received unexpected artifacts: {sorted(unexpected)}"
        )
    variant = "full-path" if "backtest_validation" in consumed else "required-only"
    decision_key = "lessons_full" if variant == "full-path" else "lessons_required"
    decision = load_yaml(inputs[decision_key])
    decision = _require_mapping_keys(
        decision,
        label="lessons decision",
        required={
            "human_approved",
            "variant",
            "source_artifacts",
            "source_sha256",
            "decision",
            "lesson_text",
        },
    )
    if decision["human_approved"] is not True:
        raise ReplayError("lessons decision requires human_approved: true")
    if decision["variant"] != variant:
        raise ReplayError(
            f"lessons decision variant {decision['variant']!r} does not match {variant!r}"
        )
    expected_artifacts = ["postmortem_findings"]
    if variant == "full-path":
        expected_artifacts.append("backtest_validation")
    if decision["source_artifacts"] != expected_artifacts:
        raise ReplayError("lessons decision source_artifacts do not match executed variant")
    source_hashes = {
        artifact_id: _file_sha256(Path(consumed[artifact_id]["files"]["canonical"]))
        for artifact_id in expected_artifacts
    }
    if decision["source_sha256"] != source_hashes:
        raise ReplayError(
            f"lessons decision source_sha256 mismatch: expected "
            f"{decision['source_sha256']}, actual {source_hashes}"
        )
    if decision["decision"] not in {"journal_only", "research_rule"}:
        raise ReplayError("unsupported lessons decision")
    lesson_text = decision["lesson_text"]
    if not isinstance(lesson_text, str) or not lesson_text.strip():
        raise ReplayError("lessons decision lesson_text is required")

    thesis_store, thesis_review = _trader_memory_modules(repo_root)
    postmortem = _load_json(
        Path(consumed["postmortem_findings"]["files"]["canonical"]), "postmortem findings"
    )
    snapshot = _require_mapping_keys(
        postmortem.get("source_snapshot"),
        label="postmortem source_snapshot",
        required={"closed_thesis_record"},
    )
    closed = snapshot["closed_thesis_record"]
    if not isinstance(closed, dict):
        raise ReplayError("postmortem closed thesis snapshot must be a mapping")
    try:
        thesis_store.validate_thesis(closed)
    except Exception as exc:
        raise ReplayError(f"postmortem closed thesis snapshot is invalid: {exc}") from exc
    expected_closed_sha = (
        (postmortem.get("provenance") or {})
        .get("source_snapshot_sha256", {})
        .get("closed_thesis_record")
    )
    if _exact_payload_sha256(closed) != expected_closed_sha:
        raise ReplayError("postmortem closed thesis snapshot SHA-256 mismatch")
    thesis_id = postmortem["native_postmortem"]["signal_id"]
    if closed.get("thesis_id") != thesis_id:
        raise ReplayError("postmortem closed thesis snapshot thesis_id mismatch")
    state_dir = work / "trade-memory-state"
    state_dir.mkdir(parents=True)
    state_path = state_dir / f"{thesis_id}.yaml"
    _write_yaml(state_path, closed)
    try:
        thesis_store.update(
            state_dir,
            closed["thesis_id"],
            {"outcome": {"lessons_learned": lesson_text}},
        )
        journal_dir = work / "journal"
        journal_path = Path(
            thesis_review.generate_postmortem(
                closed["thesis_id"],
                str(state_dir),
                price_adapter=None,
                journal_dir=str(journal_dir),
            )
        )
        updated = load_yaml(state_path)
    except Exception as exc:
        raise ReplayError(f"trade-memory lessons native API failed: {exc}") from exc
    if _without_lesson_side_effects(updated) != _without_lesson_side_effects(closed):
        raise ReplayError("trade-memory lessons changed non-target thesis state")
    if updated["outcome"]["lessons_learned"] != lesson_text:
        raise ReplayError("trade-memory lessons did not persist approved text")

    artifacts = _artifact_paths(stage, step["output_files"])
    canonical = Path(artifacts["lessons_log_entry"]["files"]["canonical"])
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_bytes(journal_path.read_bytes())
    normalized = _canonicalize(updated, spec["fixed_timestamp"], {str(state_dir): "$STATE"})
    normalized["created_at"] = closed["created_at"]
    try:
        thesis_store.validate_thesis(normalized)
    except Exception as exc:
        raise ReplayError(f"normalized lessons state is invalid: {exc}") from exc
    _write_yaml(Path(artifacts["lessons_log_entry"]["files"]["state"]), normalized)
    provenance = {
        "human_approved": True,
        "variant": variant,
        "decision": decision["decision"],
        "source_sha256": source_hashes,
        "execution_mode": "composite",
        "components": ["native_api", "manual_contract"],
        "atomicity_scope": {
            "individual_state_files": "atomic replace by trader-memory-core",
            "temporary_state": "discarded on replay failure",
            "published_tree": "transactional replacement by workflow replay harness",
        },
    }
    _write_yaml(
        Path(artifacts["lessons_log_entry"]["files"]["provenance"]),
        provenance,
        digest_allowlist=True,
    )
    return artifacts
