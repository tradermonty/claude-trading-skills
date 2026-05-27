"""Tests for scripts/workflow_runner.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

# Load workflow_runner as a module
_script_path = Path(__file__).resolve().parents[1] / "workflow_runner.py"
_spec = importlib.util.spec_from_file_location("workflow_runner", _script_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

_validate_manifest = _mod._validate_manifest
_load_workflows = _mod._load_workflows
WorkflowRun = _mod.WorkflowRun
WorkflowStatus = _mod.WorkflowStatus


# ---------------------------------------------------------------------------
# Test _validate_manifest
# ---------------------------------------------------------------------------

def _base_manifest() -> dict:
    return {
        "schema_version": 1,
        "id": "test-workflow",
        "display_name": "Test Workflow",
        "cadence": "daily",
        "required_skills": ["market-breadth-analyzer", "uptrend-analyzer"],
        "optional_skills": [],
        "steps": [
            {"step": 1, "name": "Step 1", "skill": "market-breadth-analyzer", "produces": ["breadth_report"]},
            {
                "step": 2,
                "name": "Step 2",
                "skill": "uptrend-analyzer",
                "decision_gate": True,
                "decision_question": "Is breadth healthy?",
                "produces": ["uptrend_report"],
            },
        ],
        "artifacts": [
            {"id": "breadth_report", "produced_by_step": 1, "required": True},
            {"id": "uptrend_report", "produced_by_step": 2, "required": True},
        ],
        "manual_review": ["Confirm output before acting."],
        "when_to_run": "Before market open.",
        "when_not_to_run": "Do not use as standalone signal.",
    }


class TestValidateManifest:
    def test_valid_manifest(self):
        errors = _validate_manifest(_base_manifest(), known_skills=set())
        assert errors == []

    def test_missing_skill_in_index(self):
        m = _base_manifest()
        errors = _validate_manifest(m, known_skills={"market-breadth-analyzer"})
        # uptrend-analyzer is not in the known set → should produce an error
        assert any("uptrend-analyzer" in e for e in errors)

    def test_decision_gate_missing_question(self):
        m = _base_manifest()
        m["steps"][1]["decision_question"] = None
        errors = _validate_manifest(m, known_skills=set())
        assert any("decision_question" in e for e in errors)

    def test_artifact_references_nonexistent_step(self):
        m = _base_manifest()
        m["artifacts"].append({"id": "ghost", "produced_by_step": 99, "required": False})
        errors = _validate_manifest(m, known_skills=set())
        assert any("99" in e for e in errors)

    def test_execution_language_forbidden(self):
        m = _base_manifest()
        m["when_to_run"] = "Place order when breadth is above 70."
        errors = _validate_manifest(m, known_skills=set())
        assert any("execution language" in e.lower() for e in errors)

    def test_missing_manual_review(self):
        m = _base_manifest()
        m["manual_review"] = []
        errors = _validate_manifest(m, known_skills=set())
        assert any("manual_review" in e.lower() for e in errors)

    def test_optional_skill_not_in_index(self):
        m = _base_manifest()
        m["optional_skills"] = ["nonexistent-skill"]
        errors = _validate_manifest(m, known_skills={"market-breadth-analyzer", "uptrend-analyzer"})
        assert any("nonexistent-skill" in e for e in errors)


# ---------------------------------------------------------------------------
# Test load_workflows
# ---------------------------------------------------------------------------

class TestLoadWorkflows:
    def test_loads_all_real_workflows(self):
        workflows = _load_workflows()
        assert len(workflows) >= 5
        assert "market-regime-daily" in workflows
        assert "swing-opportunity-daily" in workflows
        assert "core-portfolio-weekly" in workflows
        assert "trade-memory-loop" in workflows
        assert "monthly-performance-review" in workflows

    def test_all_workflows_have_required_fields(self):
        workflows = _load_workflows()
        for wf_id, manifest in workflows.items():
            assert "id" in manifest, f"{wf_id} missing 'id'"
            assert "steps" in manifest, f"{wf_id} missing 'steps'"
            assert "manual_review" in manifest, f"{wf_id} missing 'manual_review'"

    def test_all_real_workflows_validate_clean(self):
        """All 5 shipped workflow manifests must pass validation."""
        workflows = _load_workflows()
        from schemas import artifacts  # noqa: F401 — ensure importable

        for wf_id, manifest in workflows.items():
            errors = _validate_manifest(manifest, known_skills=set())
            assert errors == [], f"Workflow '{wf_id}' has validation errors:\n" + "\n".join(errors)


# ---------------------------------------------------------------------------
# Test WorkflowRun creation (integration with schema)
# ---------------------------------------------------------------------------

class TestWorkflowRunCreation:
    def test_create_run(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="market-regime-daily",
            workflow_display_name="Market Regime Daily",
        )
        assert run.status == WorkflowStatus.STARTED
        assert run.run_id.startswith("run_")
        assert run.manual_review_required is True

    def test_run_serializes(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="market-regime-daily",
        )
        d = json.loads(run.model_dump_json())
        assert d["workflow_id"] == "market-regime-daily"
        assert d["status"] == "STARTED"

    def test_no_execution_fields(self):
        """WorkflowRun schema must not have any order/execution fields."""
        from schemas.artifacts import WorkflowRun as WR
        schema = WR.model_json_schema()
        props = schema.get("properties", {})
        forbidden_fields = {
            "order_id", "broker_id", "execute", "auto_execute",
            "buy_order", "sell_order", "place_order"
        }
        for f in forbidden_fields:
            assert f not in props, f"WorkflowRun schema has forbidden field: {f}"


# ---------------------------------------------------------------------------
# Phase 1 — Manual review gate enforcement
# ---------------------------------------------------------------------------

def _make_run_with_decision_gate(tmp_path: Path) -> WorkflowRun:
    """Create a WorkflowRun with one plain step and one decision-gate step."""
    import importlib.util
    import sys
    _script_path = Path(__file__).resolve().parents[1] / "workflow_runner.py"
    _spec = importlib.util.spec_from_file_location("workflow_runner_fresh", _script_path)
    mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(mod)

    WSR = mod.WorkflowStepRecord
    WR = mod.WorkflowRun
    WS = mod.WorkflowStatus

    run = WR(
        skill_id="workflow-runner",
        artifact_type="workflow_run",
        workflow_id="test-workflow",
        workflow_display_name="Test Workflow",
        status=WS.IN_PROGRESS,
        steps=[
            WSR(step_number=1, name="Market Breadth", skill_id="market-breadth-analyzer"),
            WSR(
                step_number=2,
                name="Exposure Decision Gate",
                skill_id="exposure-coach",
                decision_gate_question="Is current breadth score above 60?",
            ),
        ],
    )
    return run


class TestDecisionGateEnforcement:
    """Decision gate steps must require an answer before being completed."""

    def test_decision_gate_step_blocked_without_answer(self, tmp_path, monkeypatch):
        """complete-step on a decision gate step returns exit 1 without --answer."""
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)

        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            steps=[
                _mod.WorkflowStepRecord(
                    step_number=1,
                    name="Gate Step",
                    skill_id="exposure-coach",
                    decision_gate_question="Is market breadth healthy?",
                ),
            ],
        )
        # Save the run
        path = tmp_path / f"{run.run_id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

        # Build args with no --answer
        args = _make_args(run_id=run.run_id, step_number="1", answer=None)
        result = _mod.cmd_complete_step(args)
        assert result == 1, "Should block decision gate step without answer"

        # Run should still be in PENDING / unchanged state
        reloaded = _mod._load_run(run.run_id)
        assert reloaded.steps[0].status == "PENDING"

    def test_decision_gate_step_allowed_with_answer(self, tmp_path, monkeypatch):
        """complete-step on a decision gate step succeeds when --answer is provided."""
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)

        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            steps=[
                _mod.WorkflowStepRecord(
                    step_number=1,
                    name="Gate Step",
                    skill_id="exposure-coach",
                    decision_gate_question="Is market breadth healthy?",
                ),
            ],
        )
        path = tmp_path / f"{run.run_id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

        args = _make_args(run_id=run.run_id, step_number="1", answer="Yes — breadth score 72, proceed")
        result = _mod.cmd_complete_step(args)
        assert result == 0

        reloaded = _mod._load_run(run.run_id)
        assert reloaded.steps[0].status == "DONE"
        assert reloaded.steps[0].decision_gate_answer == "Yes — breadth score 72, proceed"

    def test_non_gate_step_allowed_without_answer(self, tmp_path, monkeypatch):
        """Plain steps (no decision_gate_question) succeed without --answer."""
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)

        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            steps=[
                _mod.WorkflowStepRecord(
                    step_number=1,
                    name="Plain Step",
                    skill_id="market-breadth-analyzer",
                    decision_gate_question=None,
                ),
            ],
        )
        path = tmp_path / f"{run.run_id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

        args = _make_args(run_id=run.run_id, step_number="1", answer=None)
        result = _mod.cmd_complete_step(args)
        assert result == 0


class TestManualReviewGate:
    """Completing all steps with manual_review_required=True → AWAITING_REVIEW, not COMPLETED."""

    def test_all_steps_done_transitions_to_awaiting_review(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)

        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            manual_review_required=True,
            steps=[
                _mod.WorkflowStepRecord(
                    step_number=1, name="Only Step", skill_id="market-breadth-analyzer"
                )
            ],
        )
        path = tmp_path / f"{run.run_id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

        args = _make_args(run_id=run.run_id, step_number="1", answer=None)
        result = _mod.cmd_complete_step(args)
        assert result == 0

        reloaded = _mod._load_run(run.run_id)
        assert reloaded.status == WorkflowStatus.AWAITING_REVIEW, (
            "Workflow with manual_review_required=True must enter AWAITING_REVIEW, not COMPLETED"
        )
        # completed_at must NOT be set yet — run is not done until reviewed
        assert reloaded.completed_at is None

    def test_no_review_required_transitions_to_completed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)

        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            manual_review_required=False,
            steps=[
                _mod.WorkflowStepRecord(
                    step_number=1, name="Only Step", skill_id="market-breadth-analyzer"
                )
            ],
        )
        path = tmp_path / f"{run.run_id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

        args = _make_args(run_id=run.run_id, step_number="1", answer=None)
        result = _mod.cmd_complete_step(args)
        assert result == 0

        reloaded = _mod._load_run(run.run_id)
        assert reloaded.status == WorkflowStatus.COMPLETED

    def test_approve_review_transitions_to_completed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)
        from schemas.artifacts import ManualReviewStatus

        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            manual_review_required=True,
            status=WorkflowStatus.AWAITING_REVIEW,
        )
        path = tmp_path / f"{run.run_id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

        args = _make_args(run_id=run.run_id, reviewer="Alice", notes="Looks good")
        result = _mod.cmd_approve_review(args)
        assert result == 0

        reloaded = _mod._load_run(run.run_id)
        assert reloaded.status == WorkflowStatus.COMPLETED
        assert reloaded.manual_review_status == ManualReviewStatus.APPROVED
        assert reloaded.reviewer == "Alice"
        assert reloaded.review_notes == "Looks good"
        assert reloaded.reviewed_at is not None
        assert reloaded.completed_at is not None

    def test_approve_review_blocked_when_not_awaiting(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)

        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            status=WorkflowStatus.IN_PROGRESS,
        )
        path = tmp_path / f"{run.run_id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

        args = _make_args(run_id=run.run_id, reviewer="Bob")
        result = _mod.cmd_approve_review(args)
        assert result == 1, "approve-review must fail when run is not in AWAITING_REVIEW"

    def test_approve_review_blocked_with_unanswered_gates(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)

        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            status=WorkflowStatus.AWAITING_REVIEW,
            steps=[
                _mod.WorkflowStepRecord(
                    step_number=1,
                    name="Decision Gate",
                    skill_id="exposure-coach",
                    status="DONE",
                    decision_gate_question="Breadth > 60?",
                    decision_gate_answer=None,  # Not answered!
                )
            ],
        )
        path = tmp_path / f"{run.run_id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

        args = _make_args(run_id=run.run_id, reviewer="Carol")
        result = _mod.cmd_approve_review(args)
        assert result == 1, "approve-review must fail when decision gate has no answer"

    def test_approve_already_completed_is_idempotent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)

        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            status=WorkflowStatus.COMPLETED,
        )
        path = tmp_path / f"{run.run_id}.json"
        path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

        args = _make_args(run_id=run.run_id, reviewer="Dave")
        result = _mod.cmd_approve_review(args)
        assert result == 0, "approve-review on already-COMPLETED run should be idempotent"


# ---------------------------------------------------------------------------
# Phase 7 — Workflow Reproducibility
# ---------------------------------------------------------------------------


class TestWorkflowRunProvenanceFields:
    """WorkflowRun must carry full provenance metadata for reproducibility."""

    def test_run_has_run_timestamp(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
        )
        assert run.run_timestamp, "run_timestamp must be non-empty"
        # Must be a valid ISO timestamp
        assert "T" in run.run_timestamp, "run_timestamp must be ISO-8601"

    def test_run_has_operator_field(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            operator="Alice",
        )
        assert run.operator == "Alice"

    def test_operator_defaults_to_none(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
        )
        assert run.operator is None

    def test_run_has_workflow_version_field(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            workflow_version="1.2",
        )
        assert run.workflow_version == "1.2"

    def test_run_has_skill_versions_dict(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            skill_versions={"market-breadth-analyzer": "1.0", "uptrend-analyzer": "2.1"},
        )
        assert run.skill_versions["market-breadth-analyzer"] == "1.0"
        assert run.skill_versions["uptrend-analyzer"] == "2.1"

    def test_skill_versions_defaults_to_empty_dict(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
        )
        assert run.skill_versions == {}

    def test_run_has_artifact_schema_versions_dict(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            artifact_schema_versions={"market_breadth_report": "1.0", "workflow_run": "1.0"},
        )
        assert run.artifact_schema_versions["workflow_run"] == "1.0"

    def test_artifact_schema_versions_defaults_to_empty_dict(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
        )
        assert run.artifact_schema_versions == {}

    def test_run_has_input_artifact_hashes(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            input_artifact_hashes={"art-abc123": "deadbeef" * 8},
        )
        assert "art-abc123" in run.input_artifact_hashes

    def test_run_has_output_artifact_hashes(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            output_artifact_hashes={"art-def456": "cafebabe" * 8},
        )
        assert "art-def456" in run.output_artifact_hashes

    def test_provenance_fields_serialise_to_json(self):
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            workflow_version="3.0",
            operator="CI-pipeline",
            skill_versions={"vcp-screener": "1.5"},
            artifact_schema_versions={"trade_plan": "1.0"},
            input_artifact_hashes={"art-in": "a" * 64},
            output_artifact_hashes={"art-out": "b" * 64},
        )
        import json as _json
        d = _json.loads(run.model_dump_json())
        assert d["workflow_version"] == "3.0"
        assert d["operator"] == "CI-pipeline"
        assert d["skill_versions"]["vcp-screener"] == "1.5"
        assert d["artifact_schema_versions"]["trade_plan"] == "1.0"
        assert d["input_artifact_hashes"]["art-in"] == "a" * 64
        assert d["output_artifact_hashes"]["art-out"] == "b" * 64


class TestCmdStartProvenanceCapture:
    """cmd_start must populate provenance fields when creating a new run."""

    def _make_workflow_yaml(self, tmp_path: Path, skill_ids: list[str]) -> dict:
        """Write a minimal workflow YAML and return the manifest dict."""
        manifest = {
            "schema_version": 1,
            "id": "test-workflow",
            "display_name": "Test Workflow",
            "version": "2.0",
            "cadence": "daily",
            "estimated_minutes": 30,
            "required_skills": skill_ids,
            "optional_skills": [],
            "steps": [
                {
                    "step": i + 1,
                    "name": f"Step {i + 1}",
                    "skill": sid,
                    "produces": [f"report_{i}"],
                }
                for i, sid in enumerate(skill_ids)
            ],
            "artifacts": [],
            "manual_review": ["Confirm output before acting."],
            "when_to_run": "Before market open.",
            "when_not_to_run": "Do not use as standalone signal.",
        }
        wf_dir = tmp_path / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "test-workflow.yaml").write_text(
            yaml.dump(manifest), encoding="utf-8"
        )
        return manifest

    def test_start_captures_workflow_version(self, tmp_path, monkeypatch):
        """cmd_start populates workflow_version from the manifest 'version' field."""
        self._make_workflow_yaml(tmp_path, ["market-breadth-analyzer"])
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path / "runs")
        monkeypatch.setattr(_mod, "WORKFLOWS_DIR", tmp_path / "workflows")
        monkeypatch.setattr(_mod, "SKILLS_INDEX", tmp_path / "skills-index.yaml")
        (tmp_path / "skills-index.yaml").write_text(
            yaml.dump({"skills": [{"id": "market-breadth-analyzer", "version": "1.3"}]}),
            encoding="utf-8",
        )

        args = _make_args(workflow_id="test-workflow", include_optional=False, operator=None)
        result = _mod.cmd_start(args)
        assert result == 0

        run_files = list((tmp_path / "runs").glob("*.json"))
        assert run_files, "No run file created"
        run = _mod._load_run(run_files[0].stem)
        assert run.workflow_version == "2.0", "workflow_version should be captured from manifest"

    def test_start_captures_skill_versions(self, tmp_path, monkeypatch):
        """cmd_start populates skill_versions from skills-index.yaml."""
        self._make_workflow_yaml(tmp_path, ["market-breadth-analyzer", "uptrend-analyzer"])
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path / "runs")
        monkeypatch.setattr(_mod, "WORKFLOWS_DIR", tmp_path / "workflows")
        monkeypatch.setattr(_mod, "SKILLS_INDEX", tmp_path / "skills-index.yaml")
        (tmp_path / "skills-index.yaml").write_text(
            yaml.dump({"skills": [
                {"id": "market-breadth-analyzer", "version": "1.3"},
                {"id": "uptrend-analyzer", "version": "2.0"},
            ]}),
            encoding="utf-8",
        )

        args = _make_args(workflow_id="test-workflow", include_optional=False, operator=None)
        _mod.cmd_start(args)

        run = _mod._load_run(list((tmp_path / "runs").glob("*.json"))[0].stem)
        assert "market-breadth-analyzer" in run.skill_versions
        assert run.skill_versions["market-breadth-analyzer"] == "1.3"
        assert run.skill_versions["uptrend-analyzer"] == "2.0"

    def test_start_captures_operator(self, tmp_path, monkeypatch):
        """cmd_start records the --operator value in the run."""
        self._make_workflow_yaml(tmp_path, ["market-breadth-analyzer"])
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path / "runs")
        monkeypatch.setattr(_mod, "WORKFLOWS_DIR", tmp_path / "workflows")
        monkeypatch.setattr(_mod, "SKILLS_INDEX", tmp_path / "skills-index.yaml")
        (tmp_path / "skills-index.yaml").write_text(
            yaml.dump({"skills": [{"id": "market-breadth-analyzer", "version": "1.0"}]}),
            encoding="utf-8",
        )

        args = _make_args(workflow_id="test-workflow", include_optional=False, operator="Alice")
        _mod.cmd_start(args)

        run = _mod._load_run(list((tmp_path / "runs").glob("*.json"))[0].stem)
        assert run.operator == "Alice"

    def test_start_populates_artifact_schema_versions(self, tmp_path, monkeypatch):
        """cmd_start captures artifact schema versions (non-empty dict)."""
        self._make_workflow_yaml(tmp_path, ["market-breadth-analyzer"])
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path / "runs")
        monkeypatch.setattr(_mod, "WORKFLOWS_DIR", tmp_path / "workflows")
        monkeypatch.setattr(_mod, "SKILLS_INDEX", tmp_path / "skills-index.yaml")
        (tmp_path / "skills-index.yaml").write_text(
            yaml.dump({"skills": [{"id": "market-breadth-analyzer", "version": "1.0"}]}),
            encoding="utf-8",
        )

        args = _make_args(workflow_id="test-workflow", include_optional=False, operator=None)
        _mod.cmd_start(args)

        run = _mod._load_run(list((tmp_path / "runs").glob("*.json"))[0].stem)
        assert isinstance(run.artifact_schema_versions, dict), "artifact_schema_versions must be a dict"
        assert len(run.artifact_schema_versions) > 0, "artifact_schema_versions must not be empty"
        assert "workflow_run" in run.artifact_schema_versions, (
            "workflow_run artifact type should be present in schema versions"
        )


class TestCmdRecordArtifact:
    """record-artifact command must persist artifact hashes in the run."""

    def test_record_output_artifact_by_hash(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
        )
        (tmp_path / f"{run.run_id}.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")

        sha = "a" * 64
        args = _make_args(run_id=run.run_id, artifact_id="art-out-1", hash=sha, file=None, kind="output", step_number=None)
        result = _mod.cmd_record_artifact(args)
        assert result == 0

        reloaded = _mod._load_run(run.run_id)
        assert reloaded.output_artifact_hashes["art-out-1"] == sha
        assert "art-out-1" in reloaded.artifact_ids

    def test_record_input_artifact_by_hash(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
        )
        (tmp_path / f"{run.run_id}.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")

        sha = "b" * 64
        args = _make_args(run_id=run.run_id, artifact_id="art-in-1", hash=sha, file=None, kind="input", step_number=None)
        result = _mod.cmd_record_artifact(args)
        assert result == 0

        reloaded = _mod._load_run(run.run_id)
        assert reloaded.input_artifact_hashes["art-in-1"] == sha
        # Input artifacts do NOT go into artifact_ids
        assert "art-in-1" not in reloaded.artifact_ids

    def test_record_artifact_by_file(self, tmp_path, monkeypatch):
        import hashlib
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
        )
        (tmp_path / f"{run.run_id}.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")

        content = b'{"artifact_type": "test", "data": 42}'
        art_file = tmp_path / "test_artifact.json"
        art_file.write_bytes(content)
        expected_sha = hashlib.sha256(content).hexdigest()

        args = _make_args(run_id=run.run_id, artifact_id="art-file-1", hash=None, file=str(art_file), kind="output", step_number=None)
        result = _mod.cmd_record_artifact(args)
        assert result == 0

        reloaded = _mod._load_run(run.run_id)
        assert reloaded.output_artifact_hashes["art-file-1"] == expected_sha

    def test_record_artifact_requires_hash_or_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
        )
        (tmp_path / f"{run.run_id}.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")

        args = _make_args(run_id=run.run_id, artifact_id="art-x", hash=None, file=None, kind="output", step_number=None)
        result = _mod.cmd_record_artifact(args)
        assert result == 1, "Must return error when neither --hash nor --file provided"

    def test_record_artifact_on_step(self, tmp_path, monkeypatch):
        """record-artifact --step associates the hash with the step's output_artifact_hashes."""
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            steps=[
                _mod.WorkflowStepRecord(step_number=2, name="Analysis", skill_id="vcp-screener"),
            ],
        )
        (tmp_path / f"{run.run_id}.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")

        sha = "c" * 64
        args = _make_args(run_id=run.run_id, artifact_id="art-step-out", hash=sha, file=None, kind="output", step_number=2)
        result = _mod.cmd_record_artifact(args)
        assert result == 0

        reloaded = _mod._load_run(run.run_id)
        assert reloaded.steps[0].output_artifact_hashes["art-step-out"] == sha


class TestCmdInspect:
    """inspect command must print provenance without error."""

    def test_inspect_known_run(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)
        run = WorkflowRun(
            skill_id="workflow-runner",
            artifact_type="workflow_run",
            workflow_id="test-wf",
            workflow_version="1.0",
            operator="Bob",
            skill_versions={"market-breadth-analyzer": "1.0"},
            artifact_schema_versions={"workflow_run": "1.0"},
            input_artifact_hashes={"art-in": "a" * 64},
            output_artifact_hashes={"art-out": "b" * 64},
        )
        (tmp_path / f"{run.run_id}.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")

        args = _make_args(run_id=run.run_id)
        result = _mod.cmd_inspect(args)
        assert result == 0

        out = capsys.readouterr().out
        assert "WORKFLOW RUN PROVENANCE REPORT" in out
        assert run.run_id in out
        assert "Bob" in out
        assert "market-breadth-analyzer" in out
        assert "art-in" in out
        assert "art-out" in out

    def test_inspect_unknown_run_returns_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_mod, "RUNS_DIR", tmp_path)
        args = _make_args(run_id="run_doesnotexist")
        result = _mod.cmd_inspect(args)
        assert result == 1


class TestWorkflowStepRecordProvenance:
    """WorkflowStepRecord must carry input_artifact_ids and output_artifact_hashes."""

    def test_step_has_input_artifact_ids(self):
        step = _mod.WorkflowStepRecord(
            step_number=1,
            name="Analysis",
            skill_id="market-breadth-analyzer",
            input_artifact_ids=["art-upstream-1"],
        )
        assert "art-upstream-1" in step.input_artifact_ids

    def test_step_input_artifact_ids_default_empty(self):
        step = _mod.WorkflowStepRecord(
            step_number=1, name="Analysis", skill_id="market-breadth-analyzer"
        )
        assert step.input_artifact_ids == []

    def test_step_has_output_artifact_hashes(self):
        step = _mod.WorkflowStepRecord(
            step_number=1,
            name="Analysis",
            skill_id="market-breadth-analyzer",
            output_artifact_hashes={"art-out-1": "d" * 64},
        )
        assert step.output_artifact_hashes["art-out-1"] == "d" * 64

    def test_step_output_artifact_hashes_default_empty(self):
        step = _mod.WorkflowStepRecord(
            step_number=1, name="Analysis", skill_id="market-breadth-analyzer"
        )
        assert step.output_artifact_hashes == {}


class TestGetArtifactSchemaVersions:
    """_get_artifact_schema_versions must return a non-empty dict of known types."""

    def test_returns_workflow_run_version(self):
        versions = _mod._get_artifact_schema_versions()
        assert "workflow_run" in versions, "workflow_run must be in schema versions"

    def test_returns_non_empty_dict(self):
        versions = _mod._get_artifact_schema_versions()
        assert len(versions) >= 5, "At least 5 artifact schema types expected"

    def test_versions_are_strings(self):
        versions = _mod._get_artifact_schema_versions()
        for art_type, ver in versions.items():
            assert isinstance(ver, str), f"{art_type} version must be a string"


# ---------------------------------------------------------------------------
# Helpers for building args namespaces
# ---------------------------------------------------------------------------

def _make_args(**kwargs):
    """Build a minimal argparse.Namespace with sensible defaults."""
    import argparse
    defaults = dict(
        run_id=None,
        step_number=None,
        answer=None,
        reviewer=None,
        notes=None,
        reason=None,
        workflow_id=None,
        include_optional=False,
        operator=None,
        hash=None,
        file=None,
        kind="output",
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)
