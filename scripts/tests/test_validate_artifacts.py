"""Tests for scripts/validate_artifacts.py (Phase 2 — Machine-checkable artifact correctness)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Import the module under test
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.validate_artifacts import (
    ArtifactFinding,
    validate_artifact_file,
    validate_schema_consistency,
    validate_all_reports,
    _TRADE_ARTIFACT_TYPES,
    _FILENAME_RE,
    _VALID_REVIEW_STATUSES,
    _BACKTEST_STATUSES_REQUIRING_SPEC,
    _STRATEGY_PASS_MIN_RESEARCH_QUALITY,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMAS_JSON_DIR = PROJECT_ROOT / "schemas" / "json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_artifact(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _known_ids() -> frozenset[str]:
    index = json.loads((SCHEMAS_JSON_DIR / "index.json").read_text())
    return frozenset(e["artifact_type"] for e in index)


def _base_artifact(artifact_type: str = "data_quality_report") -> dict:
    return {
        "schema_version": "1.0",
        "artifact_id": "abc-123",
        "artifact_type": artifact_type,
        "skill_id": "data-quality-checker",
        "manual_review_required": True,
        "manual_review_status": "PENDING",
        "disclaimer": {"text": "Decision-support only", "decision_support_only": True},
    }


# ---------------------------------------------------------------------------
# AV001 — artifact_type must be registered
# ---------------------------------------------------------------------------

class TestAV001ArtifactType:
    def test_registered_type_passes(self, tmp_path):
        path = _write_artifact(tmp_path, "dqr_2026-05-27.json", _base_artifact("data_quality_report"))
        findings = validate_artifact_file(path, _known_ids())
        av001 = [f for f in findings if f.code == "AV001"]
        assert not av001, f"Unexpected AV001: {av001}"

    def test_unregistered_type_fails(self, tmp_path):
        data = _base_artifact("invented_artifact_type_xyz")
        path = _write_artifact(tmp_path, "inv_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av001 = [f for f in findings if f.code == "AV001"]
        assert av001, "Expected AV001 for unregistered artifact_type"
        assert all(f.severity == "error" for f in av001)

    def test_missing_artifact_type_field_fails(self, tmp_path):
        data = {"schema_version": "1.0", "skill_id": "test"}
        path = _write_artifact(tmp_path, "no_type_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av001 = [f for f in findings if f.code == "AV001"]
        assert av001, "Expected AV001 for missing artifact_type field"

    def test_all_registered_types_pass(self, tmp_path):
        """Every artifact type in index.json should pass AV001 validation."""
        known = _known_ids()
        for artifact_type in sorted(known):
            data = _base_artifact(artifact_type)
            path = _write_artifact(tmp_path, f"{artifact_type}_2026-05-27.json", data)
            findings = validate_artifact_file(path, known)
            av001 = [f for f in findings if f.code == "AV001"]
            assert not av001, f"AV001 fired for registered type '{artifact_type}': {av001}"


# ---------------------------------------------------------------------------
# AV002 — manual_review_required must be True for trade artifacts
# ---------------------------------------------------------------------------

class TestAV002ManualReviewRequired:
    def test_trade_plan_with_true_passes(self, tmp_path):
        data = _base_artifact("trade_plan")
        data["manual_review_required"] = True
        data["ticker"] = "NVDA"
        path = _write_artifact(tmp_path, "trade_plan_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av002 = [f for f in findings if f.code == "AV002"]
        assert not av002

    def test_trade_plan_with_false_fails(self, tmp_path):
        data = _base_artifact("trade_plan")
        data["manual_review_required"] = False
        path = _write_artifact(tmp_path, "trade_plan_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av002 = [f for f in findings if f.code == "AV002"]
        assert av002, "Expected AV002 for trade_plan with manual_review_required=False"
        assert av002[0].severity == "error"

    def test_trade_plan_with_null_fails(self, tmp_path):
        data = _base_artifact("trade_plan")
        data["manual_review_required"] = None
        path = _write_artifact(tmp_path, "trade_plan_null_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av002 = [f for f in findings if f.code == "AV002"]
        assert av002, "Expected AV002 for trade_plan with manual_review_required=null"

    def test_all_trade_artifact_types_require_true(self, tmp_path):
        """Every trade-planning artifact type must enforce manual_review_required=True."""
        known = _known_ids()
        for artifact_type in sorted(_TRADE_ARTIFACT_TYPES):
            data = _base_artifact(artifact_type)
            data["manual_review_required"] = False
            path = _write_artifact(tmp_path, f"{artifact_type}_false_2026-05-27.json", data)
            findings = validate_artifact_file(path, known)
            av002 = [f for f in findings if f.code == "AV002"]
            assert av002, (
                f"Expected AV002 for trade-planning type '{artifact_type}' "
                f"with manual_review_required=False"
            )

    def test_non_trade_artifact_with_false_does_not_raise_av002(self, tmp_path):
        """Non-trade artifact types are not required to have manual_review_required=True."""
        # data_quality_report is not in _TRADE_ARTIFACT_TYPES
        data = _base_artifact("data_quality_report")
        data["manual_review_required"] = False
        path = _write_artifact(tmp_path, "dqr_false_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av002 = [f for f in findings if f.code == "AV002"]
        assert not av002, "data_quality_report should not trigger AV002"


# ---------------------------------------------------------------------------
# AV003 — filename naming convention
# ---------------------------------------------------------------------------

class TestAV003FilenameConvention:
    @pytest.mark.parametrize("filename", [
        "trade_plan_2026-05-27.json",
        "vcp-screener_screen_candidate_2026-05-27.json",
        "backtest_report_2026-05-27_143022.json",
        "exposure_decision_2026-01-01_abc.json",
    ])
    def test_valid_filenames_pass(self, tmp_path, filename):
        data = _base_artifact()
        path = _write_artifact(tmp_path, filename, data)
        findings = validate_artifact_file(path, _known_ids())
        av003 = [f for f in findings if f.code == "AV003"]
        assert not av003, f"AV003 should not fire for valid filename '{filename}'"

    @pytest.mark.parametrize("filename", [
        "output.json",
        "report.json",
        "artifact.json",
        "2026_05_27.json",       # underscores instead of dashes in date
        "tradeplan20260527.json",  # no separators
    ])
    def test_invalid_filenames_warn(self, tmp_path, filename):
        data = _base_artifact()
        path = _write_artifact(tmp_path, filename, data)
        findings = validate_artifact_file(path, _known_ids())
        av003 = [f for f in findings if f.code == "AV003"]
        assert av003, f"Expected AV003 warning for non-conventional filename '{filename}'"
        assert av003[0].severity == "warning"


# ---------------------------------------------------------------------------
# AV004 — schema_version must be present
# ---------------------------------------------------------------------------

class TestAV004SchemaVersion:
    def test_present_passes(self, tmp_path):
        data = _base_artifact()
        assert "schema_version" in data
        path = _write_artifact(tmp_path, "dqr_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av004 = [f for f in findings if f.code == "AV004"]
        assert not av004

    def test_missing_warns(self, tmp_path):
        data = _base_artifact()
        del data["schema_version"]
        path = _write_artifact(tmp_path, "dqr_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av004 = [f for f in findings if f.code == "AV004"]
        assert av004, "Expected AV004 warning when schema_version is absent"
        assert av004[0].severity == "warning"


# ---------------------------------------------------------------------------
# AV005 — manual_review_status must be valid
# ---------------------------------------------------------------------------

class TestAV005ReviewStatus:
    @pytest.mark.parametrize("status", sorted(_VALID_REVIEW_STATUSES))
    def test_valid_status_passes(self, tmp_path, status):
        data = _base_artifact()
        data["manual_review_status"] = status
        path = _write_artifact(tmp_path, f"dqr_{status.lower()}_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av005 = [f for f in findings if f.code == "AV005"]
        assert not av005, f"AV005 should not fire for valid status '{status}'"

    @pytest.mark.parametrize("status", ["DONE", "YES", "complete", "approved", "1", ""])
    def test_invalid_status_fails(self, tmp_path, status):
        data = _base_artifact()
        data["manual_review_status"] = status
        path = _write_artifact(tmp_path, f"dqr_bad_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av005 = [f for f in findings if f.code == "AV005"]
        assert av005, f"Expected AV005 for invalid status '{status}'"
        assert av005[0].severity == "error"

    def test_absent_status_does_not_raise_av005(self, tmp_path):
        """manual_review_status is optional at validation time (old artifacts may lack it)."""
        data = _base_artifact()
        del data["manual_review_status"]
        path = _write_artifact(tmp_path, "dqr_nostatus_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av005 = [f for f in findings if f.code == "AV005"]
        assert not av005


# ---------------------------------------------------------------------------
# AV006 — JSON schema files match Pydantic model defaults
# ---------------------------------------------------------------------------

class TestAV006SchemaConsistency:
    def test_schema_consistency_passes_on_live_repo(self):
        """All safety-critical defaults in schemas/json/ must match Pydantic models."""
        findings = validate_schema_consistency()
        errors = [f for f in findings if f.severity == "error"]
        assert not errors, (
            "Schema consistency errors found — re-run scripts/export_json_schemas.py:\n"
            + "\n".join(str(f) for f in errors)
        )

    def test_trade_plan_schema_manual_review_default_true(self):
        schema = json.loads((SCHEMAS_JSON_DIR / "trade_plan.json").read_text())
        props = schema.get("properties", {})
        assert props.get("manual_review_required", {}).get("default") is True

    def test_backtest_spec_paper_only_default_true(self):
        schema = json.loads((SCHEMAS_JSON_DIR / "backtest_spec.json").read_text())
        props = schema.get("properties", {})
        assert props.get("paper_only_until_validated", {}).get("default") is True

    def test_backtest_spec_no_lookahead_default_false(self):
        schema = json.loads((SCHEMAS_JSON_DIR / "backtest_spec.json").read_text())
        props = schema.get("properties", {})
        assert props.get("no_lookahead_confirmed", {}).get("default") is False

    def test_schema_index_has_all_required_types(self):
        index = json.loads((SCHEMAS_JSON_DIR / "index.json").read_text())
        types = {e["artifact_type"] for e in index}
        required = {
            "trade_plan", "trade_thesis", "postmortem_report", "backtest_report",
            "exposure_decision", "portfolio_review", "journal_entry",
            "workflow_run", "screen_candidate", "backtest_spec",
        }
        missing = required - types
        assert not missing, f"Required artifact types missing from index.json: {missing}"

    def test_all_json_schema_files_parseable(self):
        """Every .json file in schemas/json/ must be valid JSON with a 'properties' key."""
        schema_files = list(SCHEMAS_JSON_DIR.glob("*.json"))
        assert schema_files, "No schema JSON files found"
        for sf in schema_files:
            if sf.name == "index.json":
                continue
            try:
                schema = json.loads(sf.read_text())
            except json.JSONDecodeError as exc:
                pytest.fail(f"{sf.name} is not valid JSON: {exc}")
            assert "properties" in schema, f"{sf.name} has no 'properties' key"

    def test_all_json_schemas_have_manual_review_status(self):
        """Every artifact schema file must include the manual_review_status property."""
        schema_files = list(SCHEMAS_JSON_DIR.glob("*.json"))
        missing = []
        for sf in schema_files:
            if sf.name == "index.json":
                continue
            schema = json.loads(sf.read_text())
            if "manual_review_status" not in schema.get("properties", {}):
                missing.append(sf.name)
        assert not missing, (
            "These schema files are missing 'manual_review_status' — "
            "re-run scripts/export_json_schemas.py:\n" + "\n".join(missing)
        )


# ---------------------------------------------------------------------------
# validate_all_reports (directory scan)
# ---------------------------------------------------------------------------

class TestValidateAllReports:
    def test_empty_reports_dir_returns_no_findings(self, tmp_path):
        findings = validate_all_reports(tmp_path, _known_ids())
        assert findings == []

    def test_skips_non_artifact_json_files(self, tmp_path):
        # A JSON file without artifact_type should be skipped silently
        p = tmp_path / "config_2026-05-27.json"
        p.write_text(json.dumps({"version": "1.0", "settings": {}}), encoding="utf-8")
        findings = validate_all_reports(tmp_path, _known_ids())
        assert findings == []

    def test_finds_artifact_files_recursively(self, tmp_path):
        subdir = tmp_path / "swing-opportunity-daily"
        subdir.mkdir()
        data = _base_artifact("trade_plan")
        data["manual_review_required"] = True
        p = subdir / "trade_plan_2026-05-27.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        findings = validate_all_reports(tmp_path, _known_ids())
        errors = [f for f in findings if f.severity == "error"]
        assert not errors, f"Unexpected errors in clean artifact: {errors}"

    def test_detects_bad_artifact_in_reports(self, tmp_path):
        data = _base_artifact("trade_plan")
        data["manual_review_required"] = False  # AV002
        p = tmp_path / "trade_plan_2026-05-27.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        findings = validate_all_reports(tmp_path, _known_ids())
        errors = [f for f in findings if f.severity == "error"]
        assert errors, "Expected AV002 error for trade_plan with manual_review_required=False"


# ---------------------------------------------------------------------------
# AV007 — CRITICAL blocking gaps must not be paired with HIGH/MEDIUM confidence
# ---------------------------------------------------------------------------

def _critical_gap() -> dict:
    return {
        "gap_id": "gap001",
        "severity": "CRITICAL",
        "description": "FMP_API_KEY environment variable is missing",
        "affected_decision": "All market data scoring",
        "remediation": "Set FMP_API_KEY and retry",
        "can_continue": False,
    }


def _high_gap() -> dict:
    return {
        "gap_id": "gap002",
        "severity": "HIGH",
        "description": "FMP returned empty response for 3 tickers",
        "affected_decision": "Breadth scoring",
        "remediation": "Retry or use fewer tickers",
        "can_continue": True,  # HIGH gaps do NOT block by default
    }


class TestAV007CriticalGapConfidence:
    def test_critical_gap_with_low_confidence_passes(self, tmp_path):
        data = _base_artifact()
        data["data_gaps"] = [_critical_gap()]
        data["confidence"] = "LOW"
        path = _write_artifact(tmp_path, "dqr_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av007 = [f for f in findings if f.code == "AV007"]
        assert not av007, "AV007 should not fire when confidence=LOW with CRITICAL gap"

    def test_critical_gap_with_none_confidence_passes(self, tmp_path):
        data = _base_artifact()
        data["data_gaps"] = [_critical_gap()]
        data["confidence"] = None
        path = _write_artifact(tmp_path, "dqr_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av007 = [f for f in findings if f.code == "AV007"]
        assert not av007, "AV007 should not fire when confidence=None with CRITICAL gap"

    def test_critical_gap_with_high_confidence_fails(self, tmp_path):
        data = _base_artifact()
        data["data_gaps"] = [_critical_gap()]
        data["confidence"] = "HIGH"
        path = _write_artifact(tmp_path, "dqr_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av007 = [f for f in findings if f.code == "AV007"]
        assert av007, "Expected AV007 error for CRITICAL gap with HIGH confidence"
        assert av007[0].severity == "error"

    def test_critical_gap_with_medium_confidence_fails(self, tmp_path):
        data = _base_artifact()
        data["data_gaps"] = [_critical_gap()]
        data["confidence"] = "MEDIUM"
        path = _write_artifact(tmp_path, "dqr_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av007 = [f for f in findings if f.code == "AV007"]
        assert av007, "Expected AV007 error for CRITICAL gap with MEDIUM confidence"

    def test_high_gap_with_high_confidence_passes(self, tmp_path):
        """HIGH gaps with can_continue=True do NOT trigger AV007."""
        data = _base_artifact()
        data["data_gaps"] = [_high_gap()]
        data["confidence"] = "HIGH"
        path = _write_artifact(tmp_path, "dqr_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av007 = [f for f in findings if f.code == "AV007"]
        assert not av007, "HIGH gaps with can_continue=True should not trigger AV007"

    def test_no_gaps_with_high_confidence_passes(self, tmp_path):
        data = _base_artifact()
        data["data_gaps"] = []
        data["confidence"] = "HIGH"
        path = _write_artifact(tmp_path, "dqr_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        av007 = [f for f in findings if f.code == "AV007"]
        assert not av007


class TestCriticalGapPydanticEnforcement:
    """The Pydantic model itself must enforce the CRITICAL gap → LOW confidence rule."""

    def test_critical_gap_with_low_confidence_instantiates(self):
        from schemas.artifacts import DataQualityReport, DataGap, Severity
        art = DataQualityReport(
            skill_id="test",
            artifact_type="data_quality_report",
            confidence="LOW",
            data_gaps=[DataGap(
                severity=Severity.CRITICAL,
                description="API key missing",
                affected_decision="All scoring",
                remediation="Set env var",
                can_continue=False,
            )],
        )
        assert art.confidence == "LOW"

    def test_critical_gap_with_high_confidence_raises(self):
        from pydantic import ValidationError
        from schemas.artifacts import DataQualityReport, DataGap, Severity
        with pytest.raises(ValidationError, match="CRITICAL"):
            DataQualityReport(
                skill_id="test",
                artifact_type="data_quality_report",
                confidence="HIGH",
                data_gaps=[DataGap(
                    severity=Severity.CRITICAL,
                    description="API key missing",
                    affected_decision="All scoring",
                    remediation="Set env var",
                    can_continue=False,
                )],
            )

    def test_critical_gap_with_medium_confidence_raises(self):
        from pydantic import ValidationError
        from schemas.artifacts import BreadthAssessment, DataGap, Severity
        with pytest.raises(ValidationError, match="CRITICAL"):
            BreadthAssessment(
                skill_id="market-breadth-analyzer",
                artifact_type="breadth_assessment",
                confidence="MEDIUM",
                data_gaps=[DataGap(
                    severity=Severity.CRITICAL,
                    description="CSV file not found",
                    affected_decision="Breadth scoring",
                    remediation="Regenerate CSV",
                    can_continue=False,
                )],
            )

    def test_critical_gap_with_can_continue_true_does_not_block(self):
        """CRITICAL gaps that declare can_continue=True don't force LOW confidence.
        (Unusual but valid: the skill judges output is still useful despite a CRITICAL label.)
        """
        from schemas.artifacts import DataQualityReport, DataGap, Severity
        art = DataQualityReport(
            skill_id="test",
            artifact_type="data_quality_report",
            confidence="MEDIUM",
            data_gaps=[DataGap(
                severity=Severity.CRITICAL,
                description="Data stale by 7 days",
                affected_decision="Timeliness",
                remediation="Wait for refresh",
                can_continue=True,  # Explicitly allowed to continue
            )],
        )
        assert art.confidence == "MEDIUM"


# ---------------------------------------------------------------------------
# Phase 4 — No-lookahead and leakage controls (NK series)
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "lookahead"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


class TestNK001BacktestSpecNoLookahead:
    """NK001 — BacktestSpec must have no_lookahead_confirmed before use."""

    def test_spec_unconfirmed_warns(self, tmp_path):
        data = _load_fixture("backtest_spec_unconfirmed.json")
        assert data["no_lookahead_confirmed"] is False
        path = _write_artifact(tmp_path, "backtest_spec_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk001 = [f for f in findings if f.code == "NK001"]
        assert nk001, "Expected NK001 warning for unconfirmed no-lookahead"
        assert nk001[0].severity == "warning"

    def test_spec_confirmed_no_nk001(self, tmp_path):
        data = _load_fixture("backtest_spec_unconfirmed.json")
        data["no_lookahead_confirmed"] = True
        path = _write_artifact(tmp_path, "backtest_spec_confirmed_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk001 = [f for f in findings if f.code == "NK001"]
        assert not nk001


class TestNK002BacktestReportSpecLinkage:
    """NK002 — Validated BacktestReport must reference its BacktestSpec."""

    def test_report_validated_without_spec_fails(self, tmp_path):
        data = _load_fixture("backtest_report_no_spec.json")
        assert data["validation_status"] == "OUT_OF_SAMPLE_PASSED"
        assert data["spec_artifact_id"] is None
        path = _write_artifact(tmp_path, "backtest_report_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk002 = [f for f in findings if f.code == "NK002"]
        assert nk002, "Expected NK002 error for validated report without spec"
        assert nk002[0].severity == "error"

    @pytest.mark.parametrize("status", sorted(_BACKTEST_STATUSES_REQUIRING_SPEC))
    def test_all_validated_statuses_require_spec(self, tmp_path, status):
        data = _load_fixture("backtest_report_no_spec.json")
        data["validation_status"] = status
        data["spec_artifact_id"] = None
        path = _write_artifact(tmp_path, f"backtest_report_{status.lower()}_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk002 = [f for f in findings if f.code == "NK002"]
        assert nk002, f"Expected NK002 for status='{status}' without spec"

    def test_unvalidated_report_without_spec_passes_nk002(self, tmp_path):
        data = _load_fixture("backtest_report_no_spec.json")
        data["validation_status"] = "UNVALIDATED"
        data["spec_artifact_id"] = None
        path = _write_artifact(tmp_path, "backtest_report_unval_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk002 = [f for f in findings if f.code == "NK002"]
        assert not nk002, "UNVALIDATED report without spec should not trigger NK002"

    def test_validated_report_with_spec_passes(self, tmp_path):
        data = _load_fixture("backtest_report_no_spec.json")
        data["validation_status"] = "OUT_OF_SAMPLE_PASSED"
        data["spec_artifact_id"] = "spec-abc-123"
        path = _write_artifact(tmp_path, "backtest_report_linked_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk002 = [f for f in findings if f.code == "NK002"]
        assert not nk002


class TestNK003OOSMetricsWithoutSpec:
    """NK003 — OOS metrics without a spec may be post-hoc period selection."""

    def test_oos_metrics_without_spec_warns(self, tmp_path):
        data = _load_fixture("backtest_report_oos_without_spec.json")
        assert data["spec_artifact_id"] is None
        assert data["out_of_sample_metrics"]
        path = _write_artifact(tmp_path, "backtest_report_oos_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk003 = [f for f in findings if f.code == "NK003"]
        assert nk003, "Expected NK003 warning for OOS metrics without spec"
        assert nk003[0].severity == "warning"

    def test_oos_metrics_with_spec_no_nk003(self, tmp_path):
        data = _load_fixture("backtest_report_oos_without_spec.json")
        data["spec_artifact_id"] = "spec-xyz"
        path = _write_artifact(tmp_path, "backtest_report_oos_spec_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk003 = [f for f in findings if f.code == "NK003"]
        assert not nk003

    def test_empty_oos_metrics_no_nk003(self, tmp_path):
        data = _load_fixture("backtest_report_oos_without_spec.json")
        data["out_of_sample_metrics"] = {}
        data["spec_artifact_id"] = None
        path = _write_artifact(tmp_path, "backtest_report_empty_oos_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk003 = [f for f in findings if f.code == "NK003"]
        assert not nk003, "Empty OOS metrics should not trigger NK003"


class TestNK004StrategyReviewResearchQuality:
    """NK004 — PASS verdict requires adequate research_quality_score."""

    def test_pass_with_low_research_quality_fails(self, tmp_path):
        data = _load_fixture("strategy_review_pass_with_flags.json")
        assert data["verdict"] == "PASS"
        assert data["research_quality_score"] < _STRATEGY_PASS_MIN_RESEARCH_QUALITY
        path = _write_artifact(tmp_path, "strategy_review_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk004 = [f for f in findings if f.code == "NK004"]
        assert nk004, "Expected NK004 for PASS with low research quality"
        assert nk004[0].severity == "error"

    def test_pass_with_adequate_research_quality_no_nk004(self, tmp_path):
        data = _load_fixture("strategy_review_pass_with_flags.json")
        data["research_quality_score"] = 75.0
        data["overfitting_flags"] = []  # Clear flags too
        path = _write_artifact(tmp_path, "strategy_review_good_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk004 = [f for f in findings if f.code == "NK004"]
        assert not nk004

    def test_revise_verdict_with_low_rq_no_nk004(self, tmp_path):
        data = _load_fixture("strategy_review_pass_with_flags.json")
        data["verdict"] = "REVISE"
        data["research_quality_score"] = 30.0  # Low RQ is fine for REVISE/REJECT
        path = _write_artifact(tmp_path, "strategy_review_revise_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk004 = [f for f in findings if f.code == "NK004"]
        assert not nk004, "NK004 only applies to PASS verdicts"

    def test_pass_with_none_rq_no_nk004(self, tmp_path):
        """research_quality_score=None means reviewer didn't score it — no penalty."""
        data = _load_fixture("strategy_review_pass_with_flags.json")
        data["research_quality_score"] = None
        data["overfitting_flags"] = []
        path = _write_artifact(tmp_path, "strategy_review_none_rq_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk004 = [f for f in findings if f.code == "NK004"]
        assert not nk004


class TestNK005StrategyReviewOverfittingFlags:
    """NK005 — PASS verdict with open overfitting flags is contradictory."""

    def test_pass_with_flags_fails(self, tmp_path):
        data = _load_fixture("strategy_review_pass_with_flags.json")
        assert data["overfitting_flags"]
        data["research_quality_score"] = 70.0  # Fix RQ to isolate NK005
        path = _write_artifact(tmp_path, "strategy_review_flags_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk005 = [f for f in findings if f.code == "NK005"]
        assert nk005, "Expected NK005 for PASS with overfitting flags"
        assert nk005[0].severity == "error"

    def test_pass_without_flags_no_nk005(self, tmp_path):
        data = _load_fixture("strategy_review_pass_with_flags.json")
        data["overfitting_flags"] = []
        data["research_quality_score"] = 75.0
        path = _write_artifact(tmp_path, "strategy_review_clean_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk005 = [f for f in findings if f.code == "NK005"]
        assert not nk005

    def test_reject_with_flags_no_nk005(self, tmp_path):
        data = _load_fixture("strategy_review_pass_with_flags.json")
        data["verdict"] = "REJECT"
        path = _write_artifact(tmp_path, "strategy_review_reject_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        nk005 = [f for f in findings if f.code == "NK005"]
        assert not nk005, "NK005 only applies to PASS verdicts"


class TestNoLookaheadPydanticEnforcement:
    """BacktestReport model must enforce spec linkage at instantiation time."""

    def test_validated_report_without_spec_raises(self):
        from pydantic import ValidationError
        from schemas.artifacts import BacktestReport
        with pytest.raises(ValidationError, match="spec_artifact_id"):
            BacktestReport(
                skill_id="backtest-expert",
                artifact_type="backtest_report",
                strategy_name="Test Strategy",
                validation_status="OUT_OF_SAMPLE_PASSED",
                spec_artifact_id=None,
            )

    def test_validated_report_with_spec_passes(self):
        from schemas.artifacts import BacktestReport
        report = BacktestReport(
            skill_id="backtest-expert",
            artifact_type="backtest_report",
            strategy_name="Test Strategy",
            validation_status="OUT_OF_SAMPLE_PASSED",
            spec_artifact_id="spec-abc-123",
        )
        assert report.spec_artifact_id == "spec-abc-123"

    def test_unvalidated_report_without_spec_passes(self):
        from schemas.artifacts import BacktestReport
        report = BacktestReport(
            skill_id="backtest-expert",
            artifact_type="backtest_report",
            strategy_name="Test Strategy",
            validation_status="UNVALIDATED",
            spec_artifact_id=None,
        )
        assert report.validation_status == "UNVALIDATED"

    def test_fixture_backtest_spec_default_no_lookahead_false(self):
        """BacktestSpec.no_lookahead_confirmed defaults to False — must be set explicitly."""
        from schemas.artifacts import BacktestSpec
        spec = BacktestSpec(
            skill_id="backtest-expert",
            artifact_type="backtest_spec",
            strategy_name="New Strategy",
            universe="S&P 500",
        )
        assert spec.no_lookahead_confirmed is False, (
            "no_lookahead_confirmed must default to False — the user must explicitly confirm it"
        )
        assert spec.paper_only_until_validated is True


# ---------------------------------------------------------------------------
# Phase 5 — Forbidden language validator (FL series)
# ---------------------------------------------------------------------------

class TestFL001ForbiddenLanguage:
    """FL001 — Artifact text fields must not contain forbidden profit/execution claims."""

    @pytest.mark.parametrize("phrase,field", [
        ("This strategy offers guaranteed profit every month", "next_actions[0]"),
        ("Guaranteed returns of 20% annually", "review_notes"),
        ("This is a sure win setup — buy immediately", "thesis_summary"),
        ("The position cannot lose given the setup quality", "rationale"),
        ("This is a risk-free trade with defined downside", "description"),
        ("Place this trade automatically at market open", "entry_trigger"),
        ("Auto-execute the order when price crosses pivot", "next_actions[0]"),
        ("The strategy is 100% accurate in backtests", "notes"),
        ("Always profitable in trending markets", "review_notes"),
    ])
    def test_forbidden_phrase_detected(self, tmp_path, phrase, field):
        data = _base_artifact()
        data["review_notes"] = phrase
        path = _write_artifact(tmp_path, "artifact_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        fl001 = [f for f in findings if f.code == "FL001"]
        assert fl001, f"Expected FL001 for forbidden phrase: {phrase!r}"
        assert fl001[0].severity == "error"

    @pytest.mark.parametrize("safe_text", [
        "Review the candidate before making any decision",
        "Entry requires manual confirmation at the broker",
        "This is decision-support only — no automatic execution",
        "Stop-loss is at $45.20; adjust based on market conditions",
        "The setup looks promising but requires chart confirmation",
        "Exposure limit: do not exceed 2% risk per trade",
        "risk-free disclosure: this is not financial advice",  # 'risk-free disclosure' is exempt
    ])
    def test_safe_text_passes(self, tmp_path, safe_text):
        data = _base_artifact()
        data["review_notes"] = safe_text
        path = _write_artifact(tmp_path, "artifact_safe_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        fl001 = [f for f in findings if f.code == "FL001"]
        assert not fl001, f"FL001 should not fire for safe text: {safe_text!r}\nFindings: {fl001}"

    def test_forbidden_phrase_in_nested_field(self, tmp_path):
        """FL001 must scan nested structures like next_actions lists."""
        data = _base_artifact()
        data["next_actions"] = [
            "Review the chart pattern",
            "This is a guaranteed profit setup — enter now",
        ]
        path = _write_artifact(tmp_path, "nested_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        fl001 = [f for f in findings if f.code == "FL001"]
        assert fl001, "FL001 must detect forbidden phrase in nested list field"

    def test_clean_artifact_no_fl001(self, tmp_path):
        data = _base_artifact()
        data["next_actions"] = ["Review the chart", "Confirm stop-loss level manually"]
        data["review_notes"] = "Candidate looks promising; chart review pending"
        path = _write_artifact(tmp_path, "clean_2026-05-27.json", data)
        findings = validate_artifact_file(path, _known_ids())
        fl001 = [f for f in findings if f.code == "FL001"]
        assert not fl001
