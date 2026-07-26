"""Contract tests for the strict workflow samples added for Issue #208."""

from __future__ import annotations

import importlib.util
import json
import math
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml
from jsonschema import Draft7Validator, FormatChecker, validators

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples" / "workflows"
STRICT_WORKFLOWS = (
    "core-portfolio-weekly",
    "swing-opportunity-daily",
    "monthly-performance-review",
)
VARIANTS = ("sample-run", "sample-run-full-path")


def _load(path: Path) -> Any:
    if path.suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if path.suffix in {".yaml", ".yml"}:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    return path.read_text(encoding="utf-8")


def _module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _sample_dir(workflow_id: str, variant: str) -> Path:
    return EXAMPLES / workflow_id / variant


def _manifest(workflow_id: str, variant: str) -> dict[str, Any]:
    return _load(_sample_dir(workflow_id, variant) / "manifest.yaml")


@pytest.mark.parametrize("workflow_id", STRICT_WORKFLOWS)
@pytest.mark.parametrize("variant", VARIANTS)
def test_manifest_matches_workflow_and_directory_is_complete(
    workflow_id: str,
    variant: str,
) -> None:
    sample_dir = _sample_dir(workflow_id, variant)
    manifest = _manifest(workflow_id, variant)
    workflow = _load(ROOT / "workflows" / f"{workflow_id}.yaml")

    assert manifest["workflow_id"] == workflow_id
    assert manifest["sample_type"] == ("required-only" if variant == "sample-run" else "full-path")
    assert manifest["illustrative"] is True

    prompt = sample_dir / manifest["prompt"]
    prompt_text = " ".join(prompt.read_text(encoding="utf-8").lower().split())
    assert "fictional" in prompt_text
    assert "not investment advice" in prompt_text

    artifact_contract = {item["id"]: item for item in workflow["artifacts"]}
    step_contract = {item["step"]: item for item in workflow["steps"]}
    optional_steps = {step["step"]: step for step in workflow["steps"] if step.get("optional")}
    expected_artifacts = {
        artifact_id
        for artifact_id, artifact in artifact_contract.items()
        if variant == "sample-run-full-path" or artifact["required"]
    }

    artifact_entries = manifest["artifacts"]
    actual_artifacts = [item["artifact_id"] for item in artifact_entries]
    assert len(actual_artifacts) == len(set(actual_artifacts))
    assert set(actual_artifacts) == expected_artifacts

    for entry in artifact_entries:
        artifact = artifact_contract[entry["artifact_id"]]
        assert entry["step"] == artifact["produced_by_step"]
        step = step_contract[entry["step"]]
        assert entry["skill"] == step["skill"]
        assert entry["artifact_id"] in step["produces"]

    skipped = {item["step"]: item for item in manifest["optional_steps_skipped"]}
    if variant == "sample-run":
        assert set(skipped) == set(optional_steps)
        for step_number, item in skipped.items():
            assert item["skill"] == optional_steps[step_number]["skill"]
    else:
        assert skipped == {}

    prerequisite_contract = {
        (item["id"], item["artifact"])
        for item in (workflow.get("prerequisite_workflows", []) or [])
    }
    prerequisite_inputs = manifest.get("prerequisite_inputs", []) or []
    prerequisite_pairs = {
        (item["workflow_id"], item["artifact_id"]) for item in prerequisite_inputs
    }
    assert len(prerequisite_inputs) == len(prerequisite_pairs)
    assert prerequisite_pairs == prerequisite_contract
    for item in prerequisite_inputs:
        prerequisite = _load(sample_dir / item["file"])
        assert prerequisite["recommendation"] == item["required_state"]
        generated_date = datetime.fromisoformat(prerequisite["generated_at"]).date().isoformat()
        assert generated_date == item["data_date"] == manifest["verification"]["data_date"]

    declared_files = {"manifest.yaml", manifest["prompt"]}
    for entry in artifact_entries:
        declared_files.update(entry["files"].values())
    for item in prerequisite_inputs:
        declared_files.add(item["file"])
    for item in manifest.get("verification_inputs", []):
        declared_files.add(item["file"])

    for name in declared_files:
        relative = Path(name)
        assert not relative.is_absolute()
        assert ".." not in relative.parts
        resolved = (sample_dir / relative).resolve()
        assert resolved.parent == sample_dir.resolve()
        assert resolved.is_file()
        if resolved.suffix in {".json", ".yaml", ".yml"}:
            assert _load(resolved) is not None

    actual_files = {path.name for path in sample_dir.iterdir() if path.is_file()}
    assert actual_files == declared_files


def test_readme_starting_paths_link_the_three_required_samples() -> None:
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    japanese = (ROOT / "README.ja.md").read_text(encoding="utf-8")
    examples_readme = (EXAMPLES / "README.md").read_text(encoding="utf-8")

    for workflow_id in STRICT_WORKFLOWS:
        sample_path = f"examples/workflows/{workflow_id}/sample-run/"
        assert f"([sample]({sample_path}))" in english
        assert f"（[実行例]({sample_path})）" in japanese
        assert f"[`{workflow_id}/sample-run/`]({workflow_id}/sample-run/)" in examples_readme
        assert (
            f"[`{workflow_id}/sample-run-full-path/`]({workflow_id}/sample-run-full-path/)"
        ) in examples_readme


@pytest.mark.parametrize("variant", VARIANTS)
def test_core_portfolio_values_flow_to_rebalance_and_journal(variant: str) -> None:
    sample_dir = _sample_dir("core-portfolio-weekly", variant)
    holdings = _load(sample_dir / "01_holdings_snapshot.json")
    allocation = _load(sample_dir / "02_allocation_report.json")
    rebalance = _load(sample_dir / "04_rebalance_actions.yaml")
    journal = _load(sample_dir / "05_weekly_journal_entry.yaml")

    account = holdings["account"]
    positions_value = sum(item["market_value"] for item in holdings["positions"])
    assert positions_value == account["long_market_value"] == 90000.0
    assert positions_value + account["cash"] == account["equity"] == 100000.0
    for position in holdings["positions"]:
        expected_weight = position["market_value"] / account["equity"] * 100
        assert position["portfolio_weight_pct"] == expected_weight

    assert sum(item["current_pct"] for item in allocation["allocation"]) == 100.0
    assert allocation["allocation_total_pct"] == 100.0

    action = rebalance["actions"][0]
    assert action["estimated_value"] == action["shares"] * action["reference_price"]
    projected_cash = (account["cash"] + action["estimated_value"]) / account["equity"] * 100
    assert rebalance["projected_allocation"]["cash_pct"] == projected_cash == 15.0
    assert rebalance["manual_execution_required"] is True
    assert action["status"] == "PROPOSED_NOT_SUBMITTED"

    journal_action = journal["proposed_actions"][0]
    for field in ("action_id", "symbol", "action", "shares", "estimated_value"):
        assert journal_action[field] == action[field]
    assert journal_action["broker_status"] == "NOT_SUBMITTED"
    assert journal["projected_cash_pct"] == projected_cash
    assert journal["human_confirmation"]["execution_authorized"] is False

    companion = (sample_dir / "02_allocation_report.md").read_text(encoding="utf-8")
    for value in ("$100,000.00", "100.0%", "FICTA at 30.0%", "50 FICTA shares"):
        assert value in companion


def test_full_core_dividend_report_is_reproduced_by_rule_engine() -> None:
    sample_dir = _sample_dir("core-portfolio-weekly", "sample-run-full-path")
    payload = _load(sample_dir / "03_dividend_monitor_input.json")
    expected = _load(sample_dir / "03_dividend_review_findings.json")
    module = _module(
        "issue208_dividend_review",
        ROOT / "skills" / "kanchi-dividend-review-monitor" / "scripts" / "build_review_queue.py",
    )

    actual = module.build_report(payload)
    actual["generated_at"] = expected["generated_at"]
    assert actual == expected

    rebalance = _load(sample_dir / "04_rebalance_actions.yaml")
    journal = _load(sample_dir / "05_weekly_journal_entry.yaml")
    finding = expected["results"][0]["findings"][0]
    assert expected["results"][0]["status"] == "WARN"
    assert rebalance["dividend_review"]["trigger"] == finding["trigger"] == "T2"
    assert journal["dividend_review"]["trigger"] == finding["trigger"]
    assert rebalance["dividend_review"]["response"].startswith("PAUSE_OPTIONAL_ADDS")


@pytest.mark.parametrize("variant", VARIANTS)
def test_swing_sample_recomputes_risk_and_stops_before_broker(
    variant: str,
    tmp_path: Path,
) -> None:
    sample_dir = _sample_dir("swing-opportunity-daily", variant)
    exposure = _load(sample_dir / "00_exposure_decision.json")
    circuit = _load(sample_dir / "01_circuit_breaker_decision.json")
    setups = _load(sample_dir / "07_validated_setups.json")
    sizing = _load(sample_dir / "08_position_sizing.json")
    thesis = _load(sample_dir / "10_candidate_journal_entry.yaml")
    discipline = _load(sample_dir / "11_pre_trade_discipline_decision.json")

    assert exposure["recommendation"] == "NEW_ENTRY_ALLOWED"
    assert circuit["recommendation"] == "TRADING_ALLOWED"
    setup = setups["setups"][0]
    parameters = sizing["parameters"]
    assert setup["entry_price"] == parameters["entry_price"]
    assert setup["stop_price"] == parameters["stop_price"]

    risk_budget = parameters["account_size"] * parameters["risk_pct"] / 100
    risk_per_share = parameters["entry_price"] - parameters["stop_price"]
    shares = math.floor(risk_budget / risk_per_share)
    assert sizing["final_recommended_shares"] == shares == 200
    assert sizing["final_risk_dollars"] == shares * risk_per_share == 500.0
    assert sizing["final_position_value"] == shares * parameters["entry_price"]

    output_dir = tmp_path / f"position-{variant}"
    subprocess.run(
        [
            sys.executable,
            "skills/position-sizer/scripts/position_sizer.py",
            "--account-size",
            str(parameters["account_size"]),
            "--entry",
            str(parameters["entry_price"]),
            "--stop",
            str(parameters["stop_price"]),
            "--risk-pct",
            str(parameters["risk_pct"]),
            "--output-dir",
            str(output_dir),
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    generated = _load(next(output_dir.glob("position_sizer_*.json")))
    assert generated == sizing

    schema = _load(ROOT / "skills" / "trader-memory-core" / "schemas" / "thesis.schema.json")
    Draft7Validator(schema, format_checker=FormatChecker()).validate(thesis)
    thesis_store = _module(
        f"issue208_thesis_store_{variant.replace('-', '_')}",
        ROOT / "skills" / "trader-memory-core" / "scripts" / "thesis_store.py",
    )
    thesis_store._validate_thesis(thesis)
    assert thesis["ticker"] == setup["symbol"] == "EXMPL"
    assert thesis["entry"]["target_price"] == parameters["entry_price"]
    assert thesis["exit"]["stop_loss"] == parameters["stop_price"]
    assert thesis["position"]["shares"] == shares
    assert thesis["position"]["risk_dollars"] == sizing["final_risk_dollars"]
    assert thesis["status"] == "ENTRY_READY"

    result = discipline["candidate_results"][0]
    assert discipline["overall_decision"] == result["decision"] == "GO"
    assert result["symbol"] == thesis["ticker"]
    assert result["thesis_id"] == thesis["thesis_id"]
    assert result["checklist_answers"]["planned_risk_dollars"] == sizing["final_risk_dollars"]
    assert result["checklist_answers"]["actual_risk_dollars"] == sizing["final_risk_dollars"]
    assert "no order submitted" in result["checklist_answers"]["notes"].lower()

    companion = (sample_dir / "11_pre_trade_discipline_decision.md").read_text(encoding="utf-8")
    for value in ("200 shares", "$50.00", "$47.50", "$500.00", "NOT_SUBMITTED"):
        assert value in companion


@pytest.mark.parametrize("variant", VARIANTS)
def test_swing_decision_engines_reproduce_allowed_gates(
    variant: str,
    tmp_path: Path,
) -> None:
    sample_dir = _sample_dir("swing-opportunity-daily", variant)
    exposure_path = sample_dir / "00_exposure_decision.json"
    circuit_path = sample_dir / "01_circuit_breaker_decision.json"
    expected_exposure = _load(exposure_path)
    expected_circuit = _load(circuit_path)
    thesis = _load(sample_dir / "10_candidate_journal_entry.yaml")
    expected_gate = _load(sample_dir / "11_pre_trade_discipline_decision.json")

    exposure = _module(
        f"issue208_exposure_{variant.replace('-', '_')}",
        ROOT / "skills" / "exposure-coach" / "scripts" / "calculate_exposure.py",
    )
    scores = {
        "regime": None,
        "top_risk": 65,
        "breadth": 70,
        "uptrend": 74,
        "institutional": None,
        "sector": None,
        "theme": None,
        "ftd": None,
    }
    composite, provided, missing = exposure.calculate_composite_score(scores)
    recommendation = exposure.determine_recommendation(
        composite,
        scores["top_risk"],
        len(set(missing) & exposure.CRITICAL_INPUTS),
    )
    participation = exposure.determine_participation(
        scores["uptrend"],
        scores["breadth"],
        None,
    )
    bias = exposure.determine_bias("unknown", None, None, None)
    actual_exposure = {
        "schema_version": "1.0",
        "generated_at": expected_exposure["generated_at"],
        "exposure_ceiling_pct": exposure.determine_exposure_ceiling(composite),
        "bias": bias,
        "participation": participation,
        "recommendation": recommendation,
        "confidence": exposure.determine_confidence(provided, missing),
        "composite_score": round(composite, 1),
        "component_scores": {
            "breadth_score": scores["breadth"],
            "uptrend_score": scores["uptrend"],
            "top_risk_score": scores["top_risk"],
        },
        "inputs_provided": provided,
        "inputs_missing": missing,
        "rationale": exposure.generate_rationale(
            composite,
            recommendation,
            participation,
            bias,
            scores,
            missing,
        ),
    }
    assert actual_exposure == expected_exposure

    breaker = _module(
        f"issue208_breaker_{variant.replace('-', '_')}",
        ROOT / "skills" / "drawdown-circuit-breaker" / "scripts" / "check_circuit_breaker.py",
    )
    actual_circuit = breaker.evaluate_circuit_breaker(
        [],
        account_size=100000.0,
        as_of=datetime.fromisoformat("2026-06-29T08:05:00-04:00"),
        config=breaker.CircuitConfig(),
    )
    actual_circuit["generated_at"] = expected_circuit["generated_at"]
    assert actual_circuit == expected_circuit

    gate = _module(
        f"issue208_gate_{variant.replace('-', '_')}",
        ROOT / "skills" / "pre-trade-discipline-gate" / "scripts" / "check_pre_trade_discipline.py",
    )
    candidate = {
        "symbol": thesis["ticker"],
        "thesis_id": thesis["thesis_id"],
        "order_intent": "MANUAL_ORDER",
        "entry_in_written_plan": True,
        "stop_predefined": True,
        "size_within_plan": True,
        "planned_risk_dollars": 500.0,
        "actual_risk_dollars": 500.0,
        "notes": "Fictional 200-share plan; no order submitted.",
    }
    actual_gate = gate.evaluate_pre_trade_gate(
        [candidate],
        as_of=datetime.fromisoformat("2026-06-29T08:30:00-04:00"),
        state_dir=None,
        revenge_window_hours=24.0,
        market_regime_decision=exposure_path,
        circuit_breaker_decision=circuit_path,
        output_dir=tmp_path / f"gate-{variant}",
        json_only=False,
    )
    gate.finalize_links(
        actual_gate,
        state_dir=None,
        as_of=datetime.fromisoformat("2026-06-29T08:30:00-04:00"),
    )
    actual_gate["generated_at"] = expected_gate["generated_at"]
    actual_gate["inputs"]["market_regime_decision"] = Path(
        actual_gate["inputs"]["market_regime_decision"]
    ).name
    actual_gate["inputs"]["circuit_breaker_decision"] = Path(
        actual_gate["inputs"]["circuit_breaker_decision"]
    ).name
    actual_gate["artifact_paths"] = expected_gate["artifact_paths"]
    assert actual_gate == expected_gate


def test_full_swing_optional_handoffs_are_complete_and_consistent() -> None:
    sample_dir = _sample_dir("swing-opportunity-daily", "sample-run-full-path")
    setups = _load(sample_dir / "07_validated_setups.json")
    sizing = _load(sample_dir / "08_position_sizing.json")
    plans = _load(sample_dir / "09_trade_plans.json")
    thesis = _load(sample_dir / "10_candidate_journal_entry.yaml")

    assert len(setups["inputs_provided"]) == 5
    assert setups["inputs_missing"] == []
    assert _load(sample_dir / "04_exhaustion_hammer_candidates.json")["candidates"] == []

    plan = plans["plans"][0]
    assert plan["symbol"] == thesis["ticker"]
    assert plan["shares"] == sizing["final_recommended_shares"]
    assert plan["planned_risk_dollars"] == sizing["final_risk_dollars"]
    assert plan["entry_price"] == thesis["entry"]["target_price"]
    assert plan["stop_price"] == thesis["exit"]["stop_loss"]
    assert plan["order_status"] == "PROPOSED_NOT_SUBMITTED"
    assert plans["manual_execution_required"] is True


@pytest.mark.parametrize("variant", VARIANTS)
def test_monthly_aggregate_and_evidence_graph_are_consistent(variant: str) -> None:
    sample_dir = _sample_dir("monthly-performance-review", variant)
    aggregate = _load(sample_dir / "01_monthly_aggregate.json")
    postmortem = _load(sample_dir / "02_aggregate_postmortem.json")
    decisions = _load(sample_dir / "06_monthly_decision_log.json")
    rules = _load(sample_dir / "06_rule_changes_for_next_month.yaml")

    trades = aggregate["trades"]
    summary = aggregate["summary"]
    assert summary["closed_trades"] == len(trades) == 3
    assert summary["winners"] == sum(item["realized_pnl"] > 0 for item in trades) == 2
    assert summary["losers"] == sum(item["realized_pnl"] < 0 for item in trades) == 1
    assert summary["realized_pnl"] == sum(item["realized_pnl"] for item in trades) == 300.0
    assert summary["win_rate_pct"] == round(summary["winners"] / len(trades) * 100, 2)

    category_counts = Counter(item["root_cause"] for item in trades)
    assert sum(postmortem["category_counts"].values()) == len(trades)
    for category, count in postmortem["category_counts"].items():
        assert count == category_counts.get(category, 0)

    trade_ids = {item["trade_id"] for item in trades}
    postmortem_ids = {item["evidence_id"] for item in postmortem["findings"]}
    assert set(postmortem["source_trade_ids"]) == trade_ids
    for finding in postmortem["findings"]:
        assert set(finding["trade_ids"]) <= trade_ids

    behavior_ids: set[str] = set()
    operating_rule_ids: set[str] = set()
    if variant == "sample-run-full-path":
        coach = _load(sample_dir / "03_monthly_performance_coach_report.json")
        behavior = _load(sample_dir / "03_monthly_behavior_patterns.json")
        operating_rules = _load(sample_dir / "03_next_month_operating_rules.yaml")
        skill_review = _load(sample_dir / "05_skill_review_findings.json")
        assert behavior["source_review_id"] == coach["review_id"]
        assert operating_rules["source_review_id"] == coach["review_id"]
        for pattern in behavior["patterns"]:
            for source_field in pattern["source_fields"]:
                source_value: Any = aggregate
                for field_part in source_field.split("."):
                    assert isinstance(source_value, dict)
                    assert field_part in source_value
                    source_value = source_value[field_part]
        behavior_ids = {item["evidence_id"] for item in behavior["patterns"]}
        operating_rule_ids = {item["rule_id"] for item in operating_rules["rules"]}
        source_evidence_ids = trade_ids | postmortem_ids | behavior_ids
        for operating_rule in operating_rules["rules"]:
            assert set(operating_rule["evidence_ids"]) <= source_evidence_ids
        for review in skill_review["reviews"]:
            assert set(review["trade_ids"]) <= trade_ids

    source_evidence_ids = trade_ids | postmortem_ids | behavior_ids
    decision_evidence_ids = source_evidence_ids | operating_rule_ids
    for decision in decisions["decisions"]:
        assert set(decision["evidence_ids"]) <= decision_evidence_ids

    for rule in rules["rules"]:
        assert set(rule["evidence_ids"]) <= source_evidence_ids
        if variant == "sample-run-full-path":
            assert rule["source_rule_id"] in operating_rule_ids


def test_full_monthly_optional_outputs_are_reproducible_and_schema_valid() -> None:
    sample_dir = _sample_dir("monthly-performance-review", "sample-run-full-path")
    aggregate_path = sample_dir / "01_monthly_aggregate.json"
    coach = _load(sample_dir / "03_monthly_performance_coach_report.json")
    behavior = _load(sample_dir / "03_monthly_behavior_patterns.json")
    operating_rules = _load(sample_dir / "03_next_month_operating_rules.yaml")
    hypothesis = _load(sample_dir / "04_hypothesis_revalidation.json")
    skill_review = _load(sample_dir / "05_skill_review_findings.json")
    decisions = _load(sample_dir / "06_monthly_decision_log.json")
    backlog = _load(sample_dir / "06_skill_improvement_backlog.yaml")

    schema = _load(
        ROOT
        / "skills"
        / "trade-performance-coach"
        / "assets"
        / "performance_coach_report.schema.json"
    )
    validator_class = validators.validator_for(schema)
    validator_class.check_schema(schema)
    validator_class(schema).validate(coach)

    completed = subprocess.run(
        [
            sys.executable,
            "skills/trade-performance-coach/scripts/review_trade_performance.py",
            "--input",
            str(aggregate_path.relative_to(ROOT)),
            "--stdout",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    generated = json.loads(completed.stdout)
    for field in (
        "schema_version",
        "review_type",
        "review_id",
        "source_records",
        "overall_verdict",
        "summary",
        "scores",
        "process_adherence_findings",
        "risk_manager_notes",
        "execution_quality_assessment",
        "behavioral_pattern_tags",
        "next_session_operating_rules",
        "coach_questions",
        "human_decision_gate",
        "disclaimer",
    ):
        assert generated[field] == coach[field]

    coach_patterns = {
        (item["tag"], item["confidence"]) for item in coach["behavioral_pattern_tags"]
    }
    artifact_patterns = {(item["tag"], item["confidence"]) for item in behavior["patterns"]}
    assert artifact_patterns == coach_patterns
    assert len(operating_rules["rules"]) == len(coach["next_session_operating_rules"])

    returns = hypothesis["sample_returns_r"]
    metrics = hypothesis["metrics"]
    assert metrics["trade_count"] == len(returns) == 10
    assert metrics["wins"] == sum(value > 0 for value in returns) == 6
    assert metrics["losses"] == sum(value < 0 for value in returns) == 4
    assert metrics["total_return_r"] == sum(returns) == 2.0
    assert metrics["average_return_r"] == sum(returns) / len(returns) == 0.2
    assert metrics["win_rate_pct"] == metrics["wins"] / len(returns) * 100 == 60.0
    assert hypothesis["hypothesis_id"] == decisions["hypothesis_decision"]["hypothesis_id"]
    assert hypothesis["verdict"] == decisions["hypothesis_decision"]["verdict"]
    assert decisions["hypothesis_decision"]["action"] == "NO_STRATEGY_CLAIM"

    review_ids = {item["evidence_id"] for item in skill_review["reviews"]}
    backlog_by_id = {item["backlog_id"]: item for item in backlog["items"]}
    assert set(backlog_by_id) == {"IMP-001"}
    for item in backlog["items"]:
        assert set(item["evidence_ids"]) <= review_ids
    assert backlog["trade_rules_included"] is False
    repo_improvements = {item["backlog_id"]: item for item in decisions["repo_improvements"]}
    assert set(repo_improvements) == set(backlog_by_id)
    for backlog_id, improvement in repo_improvements.items():
        assert set(improvement["evidence_ids"]) == set(backlog_by_id[backlog_id]["evidence_ids"])
        assert set(improvement["evidence_ids"]) <= review_ids
