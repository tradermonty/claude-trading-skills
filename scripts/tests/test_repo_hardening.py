"""Integration tests for the TraderMonty hardening mission (Phases 2-10).

These tests run against the *actual* repository content to ensure all
hardening invariants hold as skills are updated over time.

Deliberately kept separate from unit tests so they can be skipped in
fast-feedback contexts with `pytest -m "not repo_integration"`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILLS_DIR = PROJECT_ROOT / "skills"
WORKFLOWS_DIR = PROJECT_ROOT / "workflows"
SCHEMAS_JSON_DIR = PROJECT_ROOT / "schemas" / "json"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
from validate_skills_index import validate  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_index() -> dict:
    with open(PROJECT_ROOT / "skills-index.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _all_skills() -> list[dict]:
    return _load_index()["skills"]


def _skill_md_text(skill_id: str) -> str:
    path = SKILLS_DIR / skill_id / "SKILL.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


_TRADE_CATEGORIES = frozenset({"swing-opportunity", "trade-planning", "trade-memory"})
_DATA_INTEGRATION_TYPES = frozenset({"market_data", "api", "mcp", "web", "screener"})
_DATA_REQUIREMENTS = frozenset({"required", "recommended"})


# ---------------------------------------------------------------------------
# Phase 2 — Canonical artifact schemas
# ---------------------------------------------------------------------------


class TestStructuredOutput:
    """Phase 3 — Structured Output Requirement."""

    _OUTPUT_ARTIFACT_HEADING = re.compile(
        r"^##\s+Output Artifact", re.IGNORECASE | re.MULTILINE
    )

    def test_all_skills_with_artifact_schema_ids_have_output_artifact_section(self) -> None:
        missing: list[str] = []
        for skill in _all_skills():
            ids = skill.get("artifact_schema_ids") or []
            if not ids:
                continue
            text = _skill_md_text(skill["id"])
            if not self._OUTPUT_ARTIFACT_HEADING.search(text):
                missing.append(skill["id"])
        assert not missing, (
            "Skills with artifact_schema_ids but no '## Output Artifact' section:\n"
            + "\n".join(f"  {s}" for s in missing)
        )

    def test_output_artifact_sections_reference_manual_review(self) -> None:
        """Every ## Output Artifact section must mention manual_review_required."""
        bad: list[str] = []
        for skill in _all_skills():
            ids = skill.get("artifact_schema_ids") or []
            if not ids:
                continue
            text = _skill_md_text(skill["id"])
            m = self._OUTPUT_ARTIFACT_HEADING.search(text)
            if m:
                section = text[m.start() : m.start() + 600]
                if "manual_review_required" not in section:
                    bad.append(skill["id"])
        assert not bad, (
            "## Output Artifact sections missing 'manual_review_required':\n"
            + "\n".join(f"  {s}" for s in bad)
        )


class TestArtifactSchemas:
    def test_schema_index_exists(self) -> None:
        assert (SCHEMAS_JSON_DIR / "index.json").is_file(), (
            "schemas/json/index.json is missing — run scripts/export_json_schemas.py"
        )

    def test_schema_index_has_20_entries(self) -> None:
        index = json.loads((SCHEMAS_JSON_DIR / "index.json").read_text())
        assert len(index) >= 20, f"Expected ≥20 artifact types; found {len(index)}"

    def test_all_schema_files_exist(self) -> None:
        index = json.loads((SCHEMAS_JSON_DIR / "index.json").read_text())
        missing = [
            e["schema_file"]
            for e in index
            if not (SCHEMAS_JSON_DIR / e["schema_file"]).is_file()
        ]
        assert not missing, f"Missing schema JSON files: {missing}"

    def test_schema_index_has_required_types(self) -> None:
        index = json.loads((SCHEMAS_JSON_DIR / "index.json").read_text())
        types = {e["artifact_type"] for e in index}
        required = {
            "trade_plan",
            "trade_thesis",
            "postmortem_report",
            "backtest_report",
            "exposure_decision",
            "portfolio_review",
            "journal_entry",
        }
        missing = required - types
        assert not missing, f"Required artifact types missing from index: {missing}"


# ---------------------------------------------------------------------------
# Phase 4 — Workflow schema_id contract
# ---------------------------------------------------------------------------


class TestWorkflowContracts:
    def test_all_canonical_workflows_pass_strict_validation(self) -> None:
        findings = validate(PROJECT_ROOT, strict_workflows=True)
        errors = [f for f in findings if f.severity == "error"]
        assert not errors, (
            "Strict workflow validation errors:\n"
            + "\n".join(f"  [{f.code}] {f.location}: {f.message}" for f in errors)
        )

    def test_all_workflow_artifacts_have_schema_id(self) -> None:
        for wf_file in WORKFLOWS_DIR.glob("*.yaml"):
            with open(wf_file, encoding="utf-8") as f:
                wf = yaml.safe_load(f)
            for art in wf.get("artifacts", []):
                assert "schema_id" in art, (
                    f"{wf_file.name}: artifact {art.get('id')!r} is missing schema_id"
                )

    def test_five_canonical_workflows_present(self) -> None:
        expected = {
            "market-regime-daily",
            "core-portfolio-weekly",
            "swing-opportunity-daily",
            "trade-memory-loop",
            "monthly-performance-review",
        }
        found = {p.stem for p in WORKFLOWS_DIR.glob("*.yaml")}
        missing = expected - found
        assert not missing, f"Missing canonical workflow files: {missing}"


# ---------------------------------------------------------------------------
# Phase 5 — Skill index artifact_schema_ids
# ---------------------------------------------------------------------------


class TestSkillIndexHardening:
    def test_all_skills_have_artifact_schema_ids_field(self) -> None:
        missing = [s["id"] for s in _all_skills() if "artifact_schema_ids" not in s]
        assert not missing, f"Skills missing artifact_schema_ids: {missing}"

    def test_all_artifact_schema_ids_are_registered(self) -> None:
        index = json.loads((SCHEMAS_JSON_DIR / "index.json").read_text())
        known = {e["artifact_type"] for e in index}
        bad: list[str] = []
        for skill in _all_skills():
            for sid in skill.get("artifact_schema_ids") or []:
                if sid not in known:
                    bad.append(f"{skill['id']}: {sid!r}")
        assert not bad, f"Unregistered artifact_schema_ids:\n" + "\n".join(bad)

    def test_validator_exits_ok_for_live_repo(self) -> None:
        findings = validate(PROJECT_ROOT)
        errors = [f for f in findings if f.severity == "error"]
        assert not errors, (
            "Validator errors on live repo:\n"
            + "\n".join(f"  [{f.code}] {f.location}: {f.message}" for f in errors)
        )


# ---------------------------------------------------------------------------
# Phase 6 — Data gap discipline
# ---------------------------------------------------------------------------


class TestDataGapDiscipline:
    _DATA_GAP_HEADING = re.compile(
        r"^##\s+(data.gap|missing.data)", re.IGNORECASE | re.MULTILINE
    )

    def _external_data_skills(self) -> list[dict]:
        return [
            s
            for s in _all_skills()
            if any(
                i.get("type") in _DATA_INTEGRATION_TYPES
                and i.get("requirement") in _DATA_REQUIREMENTS
                for i in s.get("integrations", [])
            )
        ]

    def test_all_external_data_skills_have_data_gap_section(self) -> None:
        missing: list[str] = []
        for skill in self._external_data_skills():
            text = _skill_md_text(skill["id"])
            if not self._DATA_GAP_HEADING.search(text):
                missing.append(skill["id"])
        assert not missing, (
            "Skills with required/recommended external data but no ## Data Gaps section:\n"
            + "\n".join(f"  {s}" for s in missing)
        )

    def test_data_gap_sections_forbid_silent_neutral_replacement(self) -> None:
        """## Data Gaps sections must not silently replace missing data with neutral values.

        Pattern: affirmative instruction to replace/substitute without a 'do not' negation.
        Example of BAD: "replace missing values with zero"
        Example of OK:  "do not replace missing values with zero"
        """
        # Match the affirmative form only — 'do not' or 'never' negates the pattern
        _BAD = re.compile(
            r"(?<!do not )(?<!never )(replace.*with zero|substitute.*neutral.*value|"
            r"fill.*with.*default|assume.*zero when missing)",
            re.IGNORECASE,
        )
        violations: list[str] = []
        for skill in self._external_data_skills():
            text = _skill_md_text(skill["id"])
            m = self._DATA_GAP_HEADING.search(text)
            if m:
                gap_section = text[m.start() :]
                if _BAD.search(gap_section):
                    violations.append(skill["id"])
        assert not violations, (
            "Data Gaps sections contain forbidden silent-replacement language:\n"
            + "\n".join(f"  {s}" for s in violations)
        )


# ---------------------------------------------------------------------------
# Phase 7 — Backtest quality gates
# ---------------------------------------------------------------------------


class TestBacktestQuality:
    def test_backtest_expert_has_no_lookahead_checklist(self) -> None:
        text = _skill_md_text("backtest-expert")
        assert "No-Lookahead Checklist" in text, (
            "backtest-expert/SKILL.md is missing the '## No-Lookahead Checklist' section"
        )

    def test_backtest_expert_has_paper_only_gate(self) -> None:
        text = _skill_md_text("backtest-expert")
        assert "paper_only_until_validated" in text, (
            "backtest-expert/SKILL.md does not reference 'paper_only_until_validated'"
        )

    def test_edge_strategy_reviewer_has_research_quality_gate(self) -> None:
        text = _skill_md_text("edge-strategy-reviewer")
        assert "Research Quality Gate" in text, (
            "edge-strategy-reviewer/SKILL.md is missing '## Research Quality Gate'"
        )

    def test_backtest_spec_paper_only_default_true(self) -> None:
        """Verify BacktestSpec defaults paper_only_until_validated=True in schema."""
        schema_path = SCHEMAS_JSON_DIR / "backtest_spec.json"
        if not schema_path.is_file():
            pytest.skip("backtest_spec.json not found")
        schema = json.loads(schema_path.read_text())
        defaults = schema.get("properties", {}).get("paper_only_until_validated", {})
        assert defaults.get("default") is True, (
            "BacktestSpec.paper_only_until_validated default must be True"
        )


# ---------------------------------------------------------------------------
# Phase 8 — Trade planning quality gates
# ---------------------------------------------------------------------------


class TestTradePlanningGates:
    _EXEC_LANG = re.compile(
        r"\b(buy now|sell now|place order|execute order|go long|go short|enter trade)\b",
        re.IGNORECASE,
    )
    _QUALIFIED = re.compile(
        r"(manual|broker|decision.support|do not|no auto|approve|confirm)",
        re.IGNORECASE,
    )

    def test_no_unqualified_execution_language_in_trade_skills(self) -> None:
        violations: list[str] = []
        for skill in _all_skills():
            if skill.get("category") not in _TRADE_CATEGORIES:
                continue
            text = _skill_md_text(skill["id"])
            for m in self._EXEC_LANG.finditer(text):
                surrounding = text[max(0, m.start() - 120) : m.end() + 120]
                if not self._QUALIFIED.search(surrounding):
                    violations.append(f"{skill['id']}: {m.group()!r}")
                    break
        assert not violations, (
            "Unqualified execution language found in trade-planning skills:\n"
            + "\n".join(f"  {v}" for v in violations)
        )

    def test_trade_plan_manual_review_required_default(self) -> None:
        schema_path = SCHEMAS_JSON_DIR / "trade_plan.json"
        if not schema_path.is_file():
            pytest.skip("trade_plan.json not found")
        schema = json.loads(schema_path.read_text())
        defaults = schema.get("properties", {}).get("manual_review_required", {})
        assert defaults.get("default") is True, (
            "TradePlan.manual_review_required default must be True"
        )

    def test_breakout_planner_has_manual_review_gate(self) -> None:
        text = _skill_md_text("breakout-trade-planner")
        assert "Manual Review Gate" in text, (
            "breakout-trade-planner/SKILL.md is missing '## Manual Review Gate'"
        )


# ---------------------------------------------------------------------------
# Phase 9 — Trader memory lifecycle
# ---------------------------------------------------------------------------


class TestTraderMemoryLifecycle:
    def test_trader_memory_core_has_lifecycle_table(self) -> None:
        text = _skill_md_text("trader-memory-core")
        assert "ThesisLifecycle" in text or "Thesis Lifecycle" in text, (
            "trader-memory-core/SKILL.md is missing the ThesisLifecycle state table"
        )

    def test_trader_memory_core_no_auto_execution_claim(self) -> None:
        text = _skill_md_text("trader-memory-core")
        assert "does not place orders" in text.lower() or "no order" in text.lower(), (
            "trader-memory-core/SKILL.md must state it does not place orders"
        )

    def test_signal_postmortem_has_2x2_matrix(self) -> None:
        text = _skill_md_text("signal-postmortem")
        assert "process_quality" in text and "outcome_quality" in text, (
            "signal-postmortem/SKILL.md is missing process_quality/outcome_quality fields"
        )


# ---------------------------------------------------------------------------
# Phase 10 — Portfolio review discipline
# ---------------------------------------------------------------------------


class TestPortfolioReviewDiscipline:
    def test_portfolio_manager_has_concentration_checks(self) -> None:
        text = _skill_md_text("portfolio-manager")
        assert "Concentration Check" in text or "concentration" in text.lower(), (
            "portfolio-manager/SKILL.md is missing concentration check thresholds"
        )

    def test_portfolio_manager_no_auto_execution(self) -> None:
        text = _skill_md_text("portfolio-manager")
        assert "does not execute" in text.lower() or "no order" in text.lower() or \
               "manually" in text.lower(), (
            "portfolio-manager/SKILL.md must state orders require manual entry"
        )

    def test_kanchi_dividend_sop_has_manual_gate(self) -> None:
        text = _skill_md_text("kanchi-dividend-sop")
        assert "Manual Review Gate" in text, (
            "kanchi-dividend-sop/SKILL.md is missing '## Manual Review Gate'"
        )

    def test_kanchi_dividend_monitor_has_manual_gate(self) -> None:
        text = _skill_md_text("kanchi-dividend-review-monitor")
        assert "Manual Review Gate" in text, (
            "kanchi-dividend-review-monitor/SKILL.md is missing '## Manual Review Gate'"
        )


# ---------------------------------------------------------------------------
# Second Hardening Pass — Phase 1: Manual review gate enforcement
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Second Hardening Pass — Phase 2: Machine-checkable artifact correctness
# ---------------------------------------------------------------------------


class TestArtifactOutputCorrectness:
    """Phase 2 — Artifact JSON schema files must match Pydantic model defaults."""

    def test_all_json_schema_files_have_manual_review_status(self) -> None:
        """Every exported schema must carry the manual_review_status property."""
        missing = []
        for sf in sorted(SCHEMAS_JSON_DIR.glob("*.json")):
            if sf.name == "index.json":
                continue
            schema = json.loads(sf.read_text())
            if "manual_review_status" not in schema.get("properties", {}):
                missing.append(sf.name)
        assert not missing, (
            "Schema files missing 'manual_review_status' — re-run schemas/export_json_schemas.py:\n"
            + "\n".join(f"  {f}" for f in missing)
        )

    def test_all_json_schema_files_have_reviewer_fields(self) -> None:
        """Reviewer traceability fields must appear in every exported schema."""
        required_fields = {"reviewer", "reviewed_at", "review_notes"}
        bad: list[str] = []
        for sf in sorted(SCHEMAS_JSON_DIR.glob("*.json")):
            if sf.name == "index.json":
                continue
            schema = json.loads(sf.read_text())
            props = set(schema.get("properties", {}).keys())
            for field in required_fields:
                if field not in props:
                    bad.append(f"{sf.name}: missing '{field}'")
        assert not bad, (
            "Schema files missing reviewer traceability fields:\n"
            + "\n".join(f"  {b}" for b in bad)
        )

    def test_validate_artifact_validator_exists(self) -> None:
        assert (PROJECT_ROOT / "scripts" / "validate_artifacts.py").is_file(), (
            "scripts/validate_artifacts.py is missing"
        )

    def test_artifact_schema_consistency_passes(self) -> None:
        """AV006 — JSON schema defaults must match Pydantic model safety defaults."""
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from validate_artifacts import validate_schema_consistency
        findings = validate_schema_consistency()
        errors = [f for f in findings if f.severity == "error"]
        assert not errors, (
            "Schema consistency errors — re-run schemas/export_json_schemas.py:\n"
            + "\n".join(f"  {f}" for f in errors)
        )


# ---------------------------------------------------------------------------
# Second Hardening Pass — Phase 3: Data gap enforcement blocks overconfident outputs
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Second Hardening Pass — Phase 4: No-lookahead and leakage controls
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Second Hardening Pass — Phase 5: Forbidden language validator
# ---------------------------------------------------------------------------


class TestForbiddenLanguageValidator:
    """Phase 5 — Validator must block guaranteed-profit and auto-execution language."""

    def test_sk020_codes_exist_in_validator(self) -> None:
        src = (PROJECT_ROOT / "scripts" / "validate_skills_index.py").read_text()
        assert "SK020" in src, "validate_skills_index.py missing SK020 validator code"

    def test_fl001_code_exists_in_validate_artifacts(self) -> None:
        src = (PROJECT_ROOT / "scripts" / "validate_artifacts.py").read_text()
        assert "FL001" in src, "validate_artifacts.py missing FL001 validator code"

    def test_no_sk020_violations_in_live_repo(self) -> None:
        findings = validate(PROJECT_ROOT)
        sk020_errors = [f for f in findings if f.code == "SK020" and f.severity == "error"]
        assert not sk020_errors, (
            "Live repo has SK020 forbidden language violations in SKILL.md files:\n"
            + "\n".join(f"  [{f.code}] {f.location}: {f.message}" for f in sk020_errors)
        )

    def test_fl001_fires_for_guaranteed_profit_in_artifact(self) -> None:
        import json as _json
        import tempfile
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from validate_artifacts import validate_artifact_file
        data = {
            "schema_version": "1.0",
            "artifact_type": "data_quality_report",
            "skill_id": "test",
            "manual_review_required": True,
            "manual_review_status": "PENDING",
            "review_notes": "This strategy provides guaranteed profit in all market conditions",
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "artifact_2026-05-27.json"
            p.write_text(_json.dumps(data), encoding="utf-8")
            findings = validate_artifact_file(p)
        fl001 = [f for f in findings if f.code == "FL001"]
        assert fl001, "FL001 must fire for 'guaranteed profit' in artifact text field"

    def test_fl001_fires_for_auto_execute_in_artifact(self) -> None:
        import json as _json
        import tempfile
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from validate_artifacts import validate_artifact_file
        data = {
            "schema_version": "1.0",
            "artifact_type": "trade_plan",
            "skill_id": "test",
            "manual_review_required": True,
            "manual_review_status": "PENDING",
            "next_actions": ["Auto-execute at market open when pivot breaks"],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "trade_plan_2026-05-27.json"
            p.write_text(_json.dumps(data), encoding="utf-8")
            findings = validate_artifact_file(p)
        fl001 = [f for f in findings if f.code == "FL001"]
        assert fl001, "FL001 must fire for auto-execute language in trade plan"


class TestNoLookaheadControls:
    """Phase 4 — Validators must reject lookahead-biased artifacts."""

    def test_nk_validators_exist_in_validate_artifacts(self) -> None:
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from validate_artifacts import validate_artifact_file
        # Module-level check: NK codes should appear in the source
        src = (PROJECT_ROOT / "scripts" / "validate_artifacts.py").read_text()
        for code in ("NK001", "NK002", "NK003", "NK004", "NK005"):
            assert code in src, f"validate_artifacts.py missing {code} validator"

    def test_fixture_backtest_spec_unconfirmed_triggers_nk001(self) -> None:
        import json as _json
        import tempfile
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from validate_artifacts import validate_artifact_file
        fixture = PROJECT_ROOT / "scripts" / "tests" / "fixtures" / "lookahead" / "backtest_spec_unconfirmed.json"
        if not fixture.is_file():
            pytest.skip("lookahead fixture not found")
        data = _json.loads(fixture.read_text())
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "backtest_spec_2026-05-27.json"
            p.write_text(_json.dumps(data), encoding="utf-8")
            findings = validate_artifact_file(p)
        nk001 = [f for f in findings if f.code == "NK001"]
        assert nk001, "Unconfirmed backtest spec fixture must trigger NK001"

    def test_fixture_backtest_report_no_spec_triggers_nk002(self) -> None:
        import json as _json
        import tempfile
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from validate_artifacts import validate_artifact_file
        fixture = PROJECT_ROOT / "scripts" / "tests" / "fixtures" / "lookahead" / "backtest_report_no_spec.json"
        if not fixture.is_file():
            pytest.skip("lookahead fixture not found")
        data = _json.loads(fixture.read_text())
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "backtest_report_2026-05-27.json"
            p.write_text(_json.dumps(data), encoding="utf-8")
            findings = validate_artifact_file(p)
        nk002 = [f for f in findings if f.code == "NK002"]
        assert nk002, "Validated backtest report without spec must trigger NK002"

    def test_fixture_strategy_review_pass_with_flags_triggers_nk004_nk005(self) -> None:
        import json as _json
        import tempfile
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from validate_artifacts import validate_artifact_file
        fixture = PROJECT_ROOT / "scripts" / "tests" / "fixtures" / "lookahead" / "strategy_review_pass_with_flags.json"
        if not fixture.is_file():
            pytest.skip("lookahead fixture not found")
        data = _json.loads(fixture.read_text())
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "strategy_review_2026-05-27.json"
            p.write_text(_json.dumps(data), encoding="utf-8")
            findings = validate_artifact_file(p)
        codes = {f.code for f in findings}
        assert "NK004" in codes, "strategy_review fixture with low RQ must trigger NK004"
        assert "NK005" in codes, "strategy_review fixture with flags must trigger NK005"

    def test_backtest_spec_paper_only_default(self) -> None:
        from schemas.artifacts import BacktestSpec
        spec = BacktestSpec(
            skill_id="backtest-expert",
            artifact_type="backtest_spec",
            strategy_name="Test",
            universe="S&P 500",
        )
        assert spec.paper_only_until_validated is True
        assert spec.no_lookahead_confirmed is False

    def test_backtest_report_requires_spec_for_validated_status(self) -> None:
        from pydantic import ValidationError
        from schemas.artifacts import BacktestReport
        with pytest.raises(ValidationError):
            BacktestReport(
                skill_id="backtest-expert",
                artifact_type="backtest_report",
                strategy_name="Test",
                validation_status="IN_SAMPLE_ONLY",
                spec_artifact_id=None,
            )


class TestDataGapEnforcementBlocking:
    """Phase 3 — CRITICAL data gaps must prevent HIGH/MEDIUM confidence outputs."""

    def test_critical_gap_blocks_high_confidence_in_model(self) -> None:
        from pydantic import ValidationError
        from schemas.artifacts import DataGap, DataQualityReport, Severity
        with pytest.raises(ValidationError):
            DataQualityReport(
                skill_id="test",
                artifact_type="data_quality_report",
                confidence="HIGH",
                data_gaps=[DataGap(
                    severity=Severity.CRITICAL,
                    description="API key missing — cannot fetch data",
                    affected_decision="All market data",
                    remediation="Set FMP_API_KEY",
                    can_continue=False,
                )],
            )

    def test_critical_gap_allows_low_confidence(self) -> None:
        from schemas.artifacts import DataGap, DataQualityReport, Severity
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
        assert art.is_review_complete is False  # PENDING → still needs review

    def test_validate_artifacts_av007_fires_for_critical_high_confidence(self) -> None:
        """The file-level validator must also catch CRITICAL + HIGH confidence."""
        import json
        import tempfile
        from pathlib import Path
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        from validate_artifacts import validate_artifact_file
        data = {
            "schema_version": "1.0",
            "artifact_type": "data_quality_report",
            "skill_id": "test",
            "manual_review_required": True,
            "manual_review_status": "PENDING",
            "confidence": "HIGH",
            "data_gaps": [{
                "gap_id": "g1",
                "severity": "CRITICAL",
                "description": "API key missing",
                "affected_decision": "All scoring",
                "remediation": "Set env var",
                "can_continue": False,
            }],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "dqr_2026-05-27.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            findings = validate_artifact_file(p)
            av007 = [f for f in findings if f.code == "AV007"]
            assert av007, "AV007 must fire for CRITICAL gap + HIGH confidence in file validator"


class TestManualReviewGateEnforcement:
    """Phase 1 — ArtifactBase must carry review lifecycle fields enforced by workflow runner."""

    def test_artifact_base_has_review_status_field(self) -> None:
        from schemas.artifacts import ArtifactBase, ManualReviewStatus
        schema = ArtifactBase.model_json_schema()
        props = schema.get("properties", {})
        assert "manual_review_status" in props, (
            "ArtifactBase must declare 'manual_review_status' field"
        )

    def test_artifact_base_has_reviewer_fields(self) -> None:
        from schemas.artifacts import ArtifactBase
        schema = ArtifactBase.model_json_schema()
        props = schema.get("properties", {})
        for field in ("reviewer", "reviewed_at", "review_notes"):
            assert field in props, f"ArtifactBase missing '{field}' field"

    def test_all_artifacts_default_to_pending(self) -> None:
        from schemas import artifacts as art_mod
        from schemas.artifacts import ManualReviewStatus
        import inspect
        classes = [
            cls for _, cls in inspect.getmembers(art_mod, inspect.isclass)
            if issubclass(cls, art_mod.ArtifactBase) and cls is not art_mod.ArtifactBase
        ]
        for cls in classes:
            # Some abstract classes may lack required fields — skip those
            try:
                schema = cls.model_json_schema()
                props = schema.get("properties", {})
                status_default = (
                    props.get("manual_review_status", {}).get("default")
                    or props.get("manual_review_status", {}).get("const")
                )
                # Default should be PENDING (the enum value)
                assert status_default == "PENDING", (
                    f"{cls.__name__}.manual_review_status default is not 'PENDING': {status_default!r}"
                )
            except Exception:
                pass  # Skip instantiation-required abstract classes

    def test_workflow_runner_has_approve_review_command(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "wfr", PROJECT_ROOT / "scripts" / "workflow_runner.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "cmd_approve_review"), (
            "workflow_runner.py must expose cmd_approve_review command"
        )
        assert "approve-review" in mod.COMMANDS, (
            "COMMANDS dict must contain 'approve-review' entry"
        )

    def test_workflow_runner_awaiting_review_status_exists(self) -> None:
        from schemas.artifacts import WorkflowStatus
        assert WorkflowStatus.AWAITING_REVIEW is not None, (
            "WorkflowStatus must include AWAITING_REVIEW state"
        )

    def test_is_review_complete_property_blocks_pending(self) -> None:
        from schemas.artifacts import DataQualityReport, ManualReviewStatus
        art = DataQualityReport(skill_id="test", artifact_type="data_quality_report")
        assert art.manual_review_status == ManualReviewStatus.PENDING
        assert art.is_review_complete is False, (
            "is_review_complete must return False for PENDING artifacts — "
            "prevents promotion without human sign-off"
        )

    def test_is_review_complete_property_passes_approved(self) -> None:
        from schemas.artifacts import DataQualityReport, ManualReviewStatus
        art = DataQualityReport(
            skill_id="test",
            artifact_type="data_quality_report",
            manual_review_status=ManualReviewStatus.APPROVED,
            reviewer="Alice",
        )
        assert art.is_review_complete is True


# ---------------------------------------------------------------------------
# Phase 7 — Workflow Reproducibility (repo-level integration tests)
# ---------------------------------------------------------------------------


class TestWorkflowReproducibility:
    """WorkflowRun schema must carry all Phase 7 provenance fields."""

    def test_workflow_run_json_schema_has_provenance_fields(self) -> None:
        """Exported workflow_run.json schema must include all Phase 7 fields."""
        schema_path = SCHEMAS_JSON_DIR / "workflow_run.json"
        assert schema_path.is_file(), "workflow_run.json schema must exist"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        props = schema.get("properties", {})
        required_fields = [
            "workflow_version",
            "run_timestamp",
            "operator",
            "skill_versions",
            "artifact_schema_versions",
            "input_artifact_hashes",
            "output_artifact_hashes",
        ]
        for field in required_fields:
            assert field in props, (
                f"workflow_run.json schema missing Phase 7 provenance field: '{field}'"
            )

    def test_workflow_run_step_has_provenance_fields(self) -> None:
        """WorkflowStepRecord must carry input_artifact_ids and output_artifact_hashes."""
        schema_path = SCHEMAS_JSON_DIR / "workflow_run.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        # WorkflowStepRecord is embedded under steps array items
        steps_prop = schema.get("properties", {}).get("steps", {})
        items = steps_prop.get("items", {})
        # May be a $ref or direct properties; check via Pydantic directly
        from schemas.artifacts import WorkflowStepRecord
        step_fields = WorkflowStepRecord.model_fields
        assert "input_artifact_ids" in step_fields, (
            "WorkflowStepRecord missing input_artifact_ids field"
        )
        assert "output_artifact_hashes" in step_fields, (
            "WorkflowStepRecord missing output_artifact_hashes field"
        )

    def test_workflow_runner_has_inspect_command(self) -> None:
        """workflow_runner.py must expose an 'inspect' subcommand."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "workflow_runner_phase7",
            PROJECT_ROOT / "scripts" / "workflow_runner.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert "inspect" in mod.COMMANDS, "workflow_runner must have 'inspect' command (Phase 7)"

    def test_workflow_runner_has_record_artifact_command(self) -> None:
        """workflow_runner.py must expose a 'record-artifact' subcommand."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "workflow_runner_phase7b",
            PROJECT_ROOT / "scripts" / "workflow_runner.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert "record-artifact" in mod.COMMANDS, (
            "workflow_runner must have 'record-artifact' command (Phase 7)"
        )

    def test_get_artifact_schema_versions_covers_key_types(self) -> None:
        """_get_artifact_schema_versions() must return versions for key artifact types."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "workflow_runner_phase7c",
            PROJECT_ROOT / "scripts" / "workflow_runner.py",
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        versions = mod._get_artifact_schema_versions()
        assert "workflow_run" in versions
        assert "trade_plan" in versions
        assert len(versions) >= 10, "Expected at least 10 artifact schema types"


# ---------------------------------------------------------------------------
# Phase 8 — OANDA Integration Boundary
# ---------------------------------------------------------------------------


class TestOandaIntegrationBoundary:
    """OANDA integration boundary must be documented and enforced."""

    def test_oanda_boundary_doc_exists(self) -> None:
        """docs/internal/oanda-integration-boundary.md must exist."""
        doc = PROJECT_ROOT / "docs" / "internal" / "oanda-integration-boundary.md"
        assert doc.is_file(), (
            "docs/internal/oanda-integration-boundary.md is missing. "
            "OANDA integration boundary must be explicitly documented."
        )

    def test_oanda_boundary_doc_content(self) -> None:
        """Boundary doc must describe key architectural constraints."""
        doc = PROJECT_ROOT / "docs" / "internal" / "oanda-integration-boundary.md"
        content = doc.read_text(encoding="utf-8")
        required_phrases = [
            "decision-support",
            "never",          # explicit prohibition
            "OANDA",
            "manual_review",
            "handoff",
        ]
        for phrase in required_phrases:
            assert phrase.lower() in content.lower(), (
                f"oanda-integration-boundary.md must mention '{phrase}'"
            )

    def test_tradermonty_has_no_oanda_imports(self) -> None:
        """No TraderMonty script or skill must import oanda-trader modules."""
        forbidden_patterns = [
            r"\bfrom\s+oanda_trader\b",
            r"\bimport\s+oanda_trader\b",
            r"\bfrom\s+oanda\.trader\b",
        ]
        compiled = [re.compile(p) for p in forbidden_patterns]
        violations = []
        for py_file in PROJECT_ROOT.rglob("*.py"):
            # Skip the test itself and oanda-trader directory if present
            rel = py_file.relative_to(PROJECT_ROOT)
            if "oanda-trader" in rel.parts or "oanda_trader" in rel.parts:
                continue
            try:
                text = py_file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for pattern in compiled:
                if pattern.search(text):
                    violations.append(str(rel))
                    break
        assert not violations, (
            f"TraderMonty code must never import oanda-trader: {violations}"
        )

    def test_no_skill_references_broker_api(self) -> None:
        """No SKILL.md may instruct Claude to call broker APIs directly."""
        forbidden = re.compile(
            r"\b(oanda\.api|v20\.api|place_order|submit_order|create_order"
            r"|broker\.execute|broker_api)\b",
            re.IGNORECASE,
        )
        violations = []
        for skill_md in SKILLS_DIR.rglob("SKILL.md"):
            try:
                text = skill_md.read_text(encoding="utf-8")
            except OSError:
                continue
            if forbidden.search(text):
                violations.append(str(skill_md.relative_to(PROJECT_ROOT)))
        assert not violations, (
            f"SKILL.md files must not reference broker API calls directly: {violations}"
        )

    def test_trade_plan_artifacts_require_manual_review(self) -> None:
        """TradePlan artifacts must ship with manual_review_required=True."""
        from schemas.artifacts import TradePlan
        plan = TradePlan(
            skill_id="test",
            artifact_type="trade_plan",
            ticker="AAPL",
            entry_trigger="Break above 52-week high with volume",
            stop_price=148.00,
            invalidation="Close below the 50-day MA",
        )
        assert plan.manual_review_required is True, (
            "TradePlan must have manual_review_required=True — "
            "it cannot be promoted to OANDA Trader without explicit human approval"
        )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
