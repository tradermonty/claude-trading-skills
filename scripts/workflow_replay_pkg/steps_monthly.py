"""Step adapters for the monthly-performance-review workflow."""

from __future__ import annotations

import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
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
    _write_json,
    _write_yaml,
    load_yaml,
)
from .normalize import (
    _canonicalize,
    _normalize_elapsed,
    _normalize_review_test_command,
    _normalize_review_test_output,
    _payload_sha256,
)


def _monthly_aggregate(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if consumed:
        raise ReplayError("monthly aggregate must not consume upstream artifacts")
    bundle = _require_mapping_keys(
        _load_json(inputs["closed_theses"], "closed theses"),
        label="closed theses",
        required={"schema_version", "period", "thesis_records"},
    )
    if bundle["schema_version"] != 1:
        raise ReplayError("closed theses schema_version must be 1")
    period = _require_mapping_keys(bundle["period"], label="period", required={"start", "end"})
    for key in ("start", "end"):
        _require_non_empty_string(period[key], f"period.{key}")
    records = bundle["thesis_records"]
    if not isinstance(records, list) or not records:
        raise ReplayError("closed theses thesis_records must be a non-empty list")

    trade_rows: list[dict[str, Any]] = []
    realized_total = 0.0
    winners = 0
    losers = 0
    max_consecutive = 0
    current_consecutive = 0
    violations = 0
    root_cause_counts: dict[str, int] = {}
    for row in records:
        row = _require_mapping_keys(
            row,
            label="thesis record",
            required={
                "trade_id",
                "symbol",
                "outcome",
                "realized_pnl",
                "root_cause",
                "process_followed",
            },
        )
        trade_id = _require_non_empty_string(row["trade_id"], "thesis record trade_id")
        outcome = row["outcome"]
        if outcome not in {"win", "loss"}:
            raise ReplayError(f"thesis record {trade_id} outcome must be win or loss")
        pnl = _require_finite_number(row["realized_pnl"], f"{trade_id} realized_pnl")
        root_cause = _require_non_empty_string(row["root_cause"], f"{trade_id} root_cause")
        if row["process_followed"] is not True:
            violations += 1
        realized_total += pnl
        if outcome == "win":
            winners += 1
            current_consecutive = 0
        else:
            losers += 1
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        root_cause_counts[root_cause] = root_cause_counts.get(root_cause, 0) + 1
        trade_rows.append(
            {
                "trade_id": trade_id,
                "symbol": _require_non_empty_string(row["symbol"], f"{trade_id} symbol"),
                "outcome": outcome,
                "realized_pnl": round(pnl, 2),
                "root_cause": root_cause,
            }
        )

    month = period["start"][:7]
    dominant_root = max(root_cause_counts, key=root_cause_counts.get)
    closed = len(records)
    aggregate = {
        "schema_version": 1,
        "review_type": "monthly_aggregate",
        "trade_id": f"monthly_{month}_fictional",
        "period": period,
        "outcome": "mixed",
        "planned": {
            "thesis_recorded_before_entry": True,
            "setup_confirmed": True,
            "market_regime": "allowed",
        },
        "actual": {
            "portfolio_heat_r": 3,
            "stop_moved": False,
            "entry_before_confirmation": False,
            "traded_against_regime": False,
        },
        "risk_plan": {"max_risk_per_trade_r": 1.0, "max_portfolio_heat_r": 4.0},
        "monthly": {
            "trades": [row["trade_id"] for row in trade_rows],
            "consecutive_losses": max_consecutive,
            "rule_violations": violations,
        },
        "postmortem": {
            "root_cause": dominant_root,
            "notes": [f"{v} trades traced to {k}" for k, v in sorted(root_cause_counts.items())],
        },
        "journal": {
            "reflection": "Monthly aggregate reconstructed from the closed-theses log.",
            "emotions": [],
        },
        "trades": trade_rows,
        "summary": {
            "closed_trades": closed,
            "winners": winners,
            "losers": losers,
            "realized_pnl": round(realized_total, 2),
            "win_rate_pct": round(winners / closed * 100, 2),
        },
        "provenance": {
            "execution_mode": "manual_contract",
            "deferred_evidence": (
                "Monthly aggregate is consolidated in-harness from the closed-theses log; "
                "trader-memory-core journal synthesis remains deferred (issue 294)."
            ),
        },
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["monthly_aggregate"]["files"]["canonical"]), aggregate)
    return artifacts


def _monthly_postmortem(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"monthly_aggregate"}:
        raise ReplayError("monthly postmortem requires exactly monthly_aggregate")
    decision = _require_mapping_keys(
        load_yaml(inputs["pattern_decision"]),
        label="pattern decision",
        required={
            "human_approved",
            "expected_native_classifications",
            "classifications",
            "summary",
        },
    )
    if decision["human_approved"] is not True:
        raise ReplayError("pattern decision requires human_approved: true")
    classifications = decision["classifications"]
    if not isinstance(classifications, list) or not classifications:
        raise ReplayError("pattern decision classifications must be a non-empty list")
    allowed_categories = {"thesis_quality", "execution", "market_environment", "randomness"}
    category_counts: dict[str, int] = {}
    for item in classifications:
        item = _require_mapping_keys(
            item,
            label="pattern classification",
            required={"category", "pattern", "count", "qualifier"},
        )
        category = item["category"]
        if category not in allowed_categories:
            raise ReplayError(f"unexpected pattern category {category!r}")
        category_counts[category] = category_counts.get(category, 0) + item["count"]
    _require_non_empty_string(decision["summary"], "pattern decision summary")

    expected_native = sorted(decision["expected_native_classifications"])
    if expected_native != sorted(allowed_categories):
        raise ReplayError(
            "expected_native_classifications must list the canonical postmortem category set; "
            f"got {expected_native}"
        )

    aggregate = _load_json(
        Path(consumed["monthly_aggregate"]["files"]["canonical"]), "monthly aggregate"
    )
    _require_mapping_keys(
        aggregate,
        label="monthly aggregate",
        required={"trades", "summary"},
        optional={
            "schema_version",
            "review_type",
            "trade_id",
            "period",
            "outcome",
            "planned",
            "actual",
            "risk_plan",
            "monthly",
            "postmortem",
            "journal",
            "provenance",
        },
    )
    trades = aggregate["trades"]
    if not isinstance(trades, list) or not trades:
        raise ReplayError("monthly aggregate trades must be a non-empty list")
    trade_ids: list[str] = []
    for row in trades:
        if not isinstance(row, dict) or "root_cause" not in row:
            raise ReplayError("monthly aggregate trade must be a mapping with a root_cause")
        if row["root_cause"] not in allowed_categories:
            raise ReplayError(
                f"monthly aggregate trade has unexpected root_cause {row['root_cause']!r}"
            )
        trade_ids.append(row.get("trade_id"))
    summary = _require_mapping_keys(
        aggregate["summary"],
        label="monthly aggregate summary",
        required={"closed_trades", "winners", "losers"},
        optional={"realized_pnl", "win_rate_pct"},
    )
    closed = _require_finite_number(
        summary["closed_trades"], "monthly aggregate closed_trades", integer=True, minimum=0
    )
    winners = _require_finite_number(
        summary["winners"], "monthly aggregate winners", integer=True, minimum=0
    )
    losers = _require_finite_number(
        summary["losers"], "monthly aggregate losers", integer=True, minimum=0
    )
    if closed != len(trades):
        raise ReplayError("monthly aggregate summary.closed_trades must equal the number of trades")
    if winners + losers != closed:
        raise ReplayError("monthly aggregate summary winners + losers must equal closed_trades")

    pm_records = _load_json(inputs["postmortems"], "postmortems")
    if isinstance(pm_records, dict):
        pm_records = pm_records.get("records") or []
    if not isinstance(pm_records, list) or not pm_records:
        raise ReplayError("postmortems must be a non-empty list")
    pm_dir = work / "postmortems"
    pm_dir.mkdir(parents=True, exist_ok=True)
    for index, pm in enumerate(pm_records, 1):
        _write_json(pm_dir / f"pm_{index:03d}.json", pm)

    analyzer = _repo_module(
        repo_root, "postmortem_analyzer", repo_root / "skills" / "signal-postmortem" / "scripts"
    )
    fixed_now = datetime.fromisoformat(spec["fixed_timestamp"].replace("Z", "+00:00"))
    loaded = analyzer.load_postmortems(str(pm_dir), days_back=2000, now=fixed_now)
    if not loaded:
        raise ReplayError("no postmortems loaded from fixture")
    metrics = analyzer.calculate_skill_metrics(loaded)

    aggregate_postmortem = {
        "schema_version": 1,
        "native_skill_metrics": metrics,
        "category_counts": {
            category: category_counts.get(category, 0) for category in sorted(allowed_categories)
        },
        "findings": classifications,
        "decision": "documented",
        "summary": decision["summary"],
        "warnings": [],
        "provenance": {
            "postmortem_records": len(pm_records),
            "source_skills": sorted(
                {pm.get("source_skill") for pm in pm_records if pm.get("source_skill")}
            ),
            "aggregate": {
                "postmortem_root_cause": aggregate.get("postmortem", {}).get("root_cause"),
                "closed_trades": aggregate.get("summary", {}).get("closed_trades"),
                "trade_ids": trade_ids,
                "sha256": _payload_sha256(aggregate, spec["fixed_timestamp"]),
            },
        },
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["aggregate_postmortem"]["files"]["canonical"]), aggregate_postmortem)
    return artifacts


def _canonical_source_record(record: Any) -> Any:
    """Keep relative source references; remove machine roots from absolute ones."""
    if isinstance(record, str):
        if PurePosixPath(record).is_absolute():
            return "./" + PurePosixPath(record).name
        windows_path = PureWindowsPath(record)
        if windows_path.is_absolute():
            return "./" + windows_path.name
    return record


_MONTHLY_COACH_ARTIFACTS = {
    "monthly_performance_coach_report",
    "monthly_behavior_patterns",
    "next_month_operating_rules",
}


def _validate_monthly_coach_decision(
    payload: Any, coach: Mapping[str, Any], *, published: bool = False
) -> dict[str, Any]:
    decision = _require_mapping_keys(
        payload,
        label="coach decision",
        required={"source_review_id", "action", "accepted_rules", "human_notes"}
        | ({"schema_version"} if published else set()),
    )
    review_id = _require_non_empty_string(coach.get("review_id"), "coach review_id")
    if decision["source_review_id"] != review_id:
        raise ReplayError("coach decision source_review_id must match the coach report")
    if published and decision["schema_version"] != 1:
        raise ReplayError("coach decision schema_version must be 1")
    action = decision["action"]
    allowed_actions = {"accept_rules", "modify_rules", "defer", "journal_only"}
    native_actions = (coach.get("human_decision_gate") or {}).get("allowed_actions") or []
    if not isinstance(action, str) or action not in allowed_actions or action not in native_actions:
        raise ReplayError("coach decision action not in coach allowed actions")
    rules = decision["accepted_rules"]
    if not isinstance(rules, list):
        raise ReplayError("coach decision accepted_rules must be a list")
    for rule in rules:
        _require_non_empty_string(rule, "coach decision accepted_rule")
    if len({rule.strip() for rule in rules}) != len(rules):
        raise ReplayError("coach decision accepted_rules must be unique")
    if action in {"accept_rules", "modify_rules"} and not rules:
        raise ReplayError("coach decision accept/modify requires non-empty accepted_rules")
    if action in {"defer", "journal_only"} and rules:
        raise ReplayError("coach decision defer/journal_only cannot contain accepted_rules")
    native_rules = {
        row["rule"]
        for row in coach.get("next_session_operating_rules", [])
        if isinstance(row, dict) and isinstance(row.get("rule"), str)
    }
    if action == "accept_rules" and not set(rules).issubset(native_rules):
        raise ReplayError("coach decision accept_rules must come from native coach proposals")
    _require_non_empty_string(decision["human_notes"], "coach decision human_notes")
    return dict(decision)


def _monthly_coach(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if set(consumed) != {"monthly_aggregate", "aggregate_postmortem"}:
        raise ReplayError("monthly coach requires monthly_aggregate and aggregate_postmortem")
    agg_path = Path(consumed["monthly_aggregate"]["files"]["canonical"])
    reports = work / "reports"
    script = (
        repo_root / "skills" / "trade-performance-coach" / "scripts" / "review_trade_performance.py"
    )
    _run_cli(
        [
            sys.executable,
            str(script),
            "--input",
            str(agg_path),
            "--output-dir",
            str(reports),
            "--json-name",
            "monthly-coach.json",
        ],
        repo_root,
    )
    coach = _canonicalize(
        _load_json(reports / "monthly-coach.json", "coach report"), spec["fixed_timestamp"], {}
    )
    source_records = coach.get("source_records")
    if isinstance(source_records, list):
        coach["source_records"] = [_canonical_source_record(rec) for rec in source_records]

    decision = _validate_monthly_coach_decision(load_yaml(inputs["coach_decision"]), coach)

    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["monthly_performance_coach_report"]["files"]["canonical"]), coach)
    behavioral = {
        "schema_version": 1,
        "behavioral_pattern_tags": coach.get("behavioral_pattern_tags") or [],
        "primary_root_cause": coach.get("summary", {}).get("primary_root_cause", "unknown"),
        "review_id": coach.get("review_id"),
    }
    _write_json(Path(artifacts["monthly_behavior_patterns"]["files"]["canonical"]), behavioral)
    _write_yaml(
        Path(artifacts["next_month_operating_rules"]["files"]["canonical"]),
        {
            "schema_version": 1,
            **decision,
        },
    )
    return artifacts


def _monthly_backtest(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if consumed and set(consumed) != {"aggregate_postmortem"}:
        raise ReplayError(f"monthly backtest received unexpected artifacts: {sorted(consumed)}")
    params = _require_mapping_keys(
        _load_json(inputs["backtest_params"], "backtest params"),
        label="backtest params",
        required={
            "hypothesis_id",
            "symbol",
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
    hypothesis_id = _require_non_empty_string(params["hypothesis_id"], "backtest hypothesis_id")
    slippage_tested = params["slippage_tested"]
    if not isinstance(slippage_tested, bool):
        raise ReplayError("backtest params slippage_tested must be a boolean")
    batch = work / "bt"
    script = repo_root / "skills" / "backtest-expert" / "scripts" / "evaluate_backtest.py"
    backtest_command = [
        sys.executable,
        str(script),
        "--total-trades",
        str(_require_finite_number(params["total_trades"], "total_trades")),
        "--win-rate",
        str(_require_finite_number(params["win_rate"], "win_rate")),
        "--avg-win-pct",
        str(_require_finite_number(params["avg_win_pct"], "avg_win_pct")),
        "--avg-loss-pct",
        str(_require_finite_number(params["avg_loss_pct"], "avg_loss_pct")),
        "--max-drawdown-pct",
        str(_require_finite_number(params["max_drawdown_pct"], "max_drawdown_pct")),
        "--years-tested",
        str(_require_finite_number(params["years_tested"], "years_tested")),
        "--num-parameters",
        str(_require_finite_number(params["num_parameters"], "num_parameters")),
    ]
    if slippage_tested:
        backtest_command.append("--slippage-tested")
    backtest_command.extend(["--output-dir", str(batch)])
    _run_cli(backtest_command, repo_root)
    evaluation = _canonicalize(
        _load_json(_latest_report(batch, "backtest_eval_*.json"), "backtest evaluation"),
        spec["fixed_timestamp"],
        {},
    )
    payload = {
        "schema_version": 1,
        "hypothesis_id": hypothesis_id,
        "symbol": _require_non_empty_string(params["symbol"], "backtest symbol"),
        "evaluation": evaluation,
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["hypothesis_revalidation"]["files"]["canonical"]), payload)
    return artifacts


def _monthly_skill_review(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    if consumed and set(consumed) != {"aggregate_postmortem"}:
        raise ReplayError(f"monthly skill review received unexpected artifacts: {sorted(consumed)}")
    target = _require_mapping_keys(
        load_yaml(inputs["skill_review_target"]),
        label="skill review target",
        required={"skill_name"},
    )
    skill_name = _require_non_empty_string(target["skill_name"], "skill review target skill_name")
    batch = work / "dual"
    script = (
        repo_root / "skills" / "dual-axis-skill-reviewer" / "scripts" / "run_dual_axis_review.py"
    )
    python_fallback_path = work / "python-fallback-path"
    python_fallback_path.mkdir(parents=True, exist_ok=True)
    _run_cli(
        [
            sys.executable,
            str(script),
            "--project-root",
            str(repo_root),
            "--skill",
            skill_name,
            "--output-dir",
            str(batch),
        ],
        repo_root,
        path_override=python_fallback_path,
        env_overrides={"NO_COLOR": "1", "PY_COLORS": "0"},
    )
    report = _load_json(_latest_report(batch, f"skill_review_{skill_name}_*.json"), "skill review")
    _normalize_review_test_command(report)
    _normalize_review_test_output(report)
    report = _canonicalize(
        report,
        spec["fixed_timestamp"],
        # The reviewer serializes paths with forward slashes on every platform, so
        # both the lexical and the resolved root are stripped in that spelling.
        {repo_root.as_posix() + "/": "", repo_root.resolve().as_posix() + "/": ""},
    )
    report = _normalize_elapsed(report)
    payload = {
        "schema_version": 1,
        "skill_name": report.get("skill_name", skill_name),
        "selection_mode": "manual",
        "grades": report.get("auto_review", {}).get("grades", {}),
        "final_score": report.get("final_review", {}).get("score"),
        "review": report,
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["skill_review_findings"]["files"]["canonical"]), payload)
    return artifacts


def _monthly_decision_log(
    repo_root: Path,
    spec: Mapping[str, Any],
    step: Mapping[str, Any],
    inputs: Mapping[str, Path],
    consumed: Mapping[str, dict[str, Any]],
    work: Path,
    stage: Path,
) -> dict[str, dict[str, Any]]:
    expected = {"aggregate_postmortem"}
    coach_artifacts = set(consumed) & _MONTHLY_COACH_ARTIFACTS
    if coach_artifacts and coach_artifacts != _MONTHLY_COACH_ARTIFACTS:
        raise ReplayError("monthly decision log requires the complete coach artifact group")
    expected.update(coach_artifacts)
    if "hypothesis_revalidation" in consumed:
        expected.add("hypothesis_revalidation")
    if "skill_review_findings" in consumed:
        expected.add("skill_review_findings")
    if set(consumed) != expected:
        raise ReplayError(f"monthly decision log received unexpected artifacts: {sorted(consumed)}")
    decision = _require_mapping_keys(
        load_yaml(inputs["rule_change_decision"]),
        label="rule change decision",
        required={
            "human_approved",
            "trade_rule_changes",
            "repo_improvements",
            "skill_improvement_backlog",
            "expected",
        },
    )
    if decision["human_approved"] is not True:
        raise ReplayError("rule change decision requires human_approved: true")
    for key in ("trade_rule_changes", "repo_improvements", "skill_improvement_backlog", "expected"):
        if not isinstance(decision[key], list):
            raise ReplayError(f"rule change decision {key} must be a list")
    coach_decision = None
    coach_hashes = dict.fromkeys(sorted(_MONTHLY_COACH_ARTIFACTS))
    if coach_artifacts:
        payloads = {}
        for artifact_id in sorted(coach_artifacts):
            path = Path(consumed[artifact_id]["files"]["canonical"])
            payloads[artifact_id] = load_yaml(path)
            coach_hashes[artifact_id] = _payload_sha256(
                payloads[artifact_id], spec["fixed_timestamp"]
            )
        coach = payloads["monthly_performance_coach_report"]
        if not isinstance(coach, dict):
            raise ReplayError("monthly coach report must be a mapping")
        coach_decision = _validate_monthly_coach_decision(
            payloads["next_month_operating_rules"], coach, published=True
        )
        behavior = payloads["monthly_behavior_patterns"]
        if not isinstance(behavior, dict) or behavior.get("review_id") != coach["review_id"]:
            raise ReplayError("monthly behavior review_id must match the coach report")

    postmortem_path = Path(consumed["aggregate_postmortem"]["files"]["canonical"])
    postmortem = _load_json(postmortem_path, "aggregate postmortem")

    log_entry = {
        "schema_version": 1,
        "coach_rule_decision": coach_decision,
        "rule_activation": "not_performed",
        "monthly_aggregate_root_cause": postmortem.get("summary", "unknown"),
        "rule_changes": decision["trade_rule_changes"],
        "repo_improvements": decision["repo_improvements"],
        "provenance": {
            **coach_hashes,
            "aggregate_postmortem": _payload_sha256(
                _load_json(postmortem_path, "aggregate postmortem"), spec["fixed_timestamp"]
            ),
            "hypothesis_revalidation": (
                _payload_sha256(
                    _load_json(
                        Path(consumed["hypothesis_revalidation"]["files"]["canonical"]),
                        "hypothesis revalidation",
                    ),
                    spec["fixed_timestamp"],
                )
                if "hypothesis_revalidation" in consumed
                else None
            ),
            "skill_review_findings": (
                _payload_sha256(
                    _load_json(
                        Path(consumed["skill_review_findings"]["files"]["canonical"]),
                        "skill review findings",
                    ),
                    spec["fixed_timestamp"],
                )
                if "skill_review_findings" in consumed
                else None
            ),
            "execution_mode": "manual_contract",
            "deferred_evidence": (
                "Decision log is transcribed from the human rule-change decision; native "
                "trader-memory-core decision/journal persistence remains deferred (issue 294)."
            ),
        },
    }
    artifacts = _artifact_paths(stage, step["output_files"])
    _write_json(Path(artifacts["monthly_decision_log"]["files"]["canonical"]), log_entry)
    _write_yaml(
        Path(artifacts["rule_changes_for_next_month"]["files"]["canonical"]),
        {
            "schema_version": 1,
            "coach_rule_decision": coach_decision,
            "rule_activation": "not_performed",
            "trade_rule_changes": decision["trade_rule_changes"],
            "repo_improvements": decision["repo_improvements"],
        },
    )
    _write_yaml(
        Path(artifacts["skill_improvement_backlog"]["files"]["canonical"]),
        {
            "schema_version": 1,
            "items": decision["skill_improvement_backlog"],
        },
    )
    return artifacts
