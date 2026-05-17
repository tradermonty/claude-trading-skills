"""Validator tests — one per error code, plus happy path.

Each test builds a minimal repository layout in tmp_path and asserts the
validator emits the specific error code.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from validate_skills_index import Finding, validate  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_skill(project_root: Path, skill_id: str, frontmatter_name: str | None = None) -> None:
    """Create skills/<id>/SKILL.md with frontmatter."""
    if frontmatter_name is None:
        frontmatter_name = skill_id
    skill_dir = project_root / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"""---
name: {frontmatter_name}
description: Test skill {skill_id}.
---

# {skill_id}
""",
        encoding="utf-8",
    )


def write_index(project_root: Path, skills: list[dict]) -> None:
    import yaml as _yaml

    payload = {
        "schema_version": 1,
        "categories": [
            "market-regime",
            "core-portfolio",
            "swing-opportunity",
            "trade-planning",
            "trade-memory",
            "strategy-research",
            "advanced-satellite",
            "meta",
        ],
        "skills": skills,
    }
    (project_root / "skills-index.yaml").write_text(
        _yaml.safe_dump(payload, sort_keys=False), encoding="utf-8"
    )


def write_workflow(project_root: Path, workflow_id: str, content: dict) -> Path:
    import yaml as _yaml

    workflows_dir = project_root / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)
    path = workflows_dir / f"{workflow_id}.yaml"
    path.write_text(_yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    return path


def codes(findings: list[Finding]) -> list[str]:
    return [f.code for f in findings if f.severity == "error"]


def warning_codes(findings: list[Finding]) -> list[str]:
    return [f.code for f in findings if f.severity == "warning"]


def minimal_skill(skill_id: str, **overrides) -> dict:
    base = {
        "id": skill_id,
        "display_name": skill_id.replace("-", " ").title(),
        "category": "core-portfolio",
        "status": "production",
        "summary": f"Summary for {skill_id}.",
        "timeframe": "weekly",
        "difficulty": "intermediate",
        "integrations": [
            {
                "id": "local_calculation",
                "type": "calculation",
                "requirement": "not_required",
                "note": "Pure local calculation.",
            }
        ],
        "inputs": ["test_input"],
        "outputs": ["test_output"],
        "workflows": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_default_mode(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_skill(tmp_path, "beta")
    write_index(tmp_path, [minimal_skill("alpha"), minimal_skill("beta")])

    findings = validate(tmp_path)
    assert codes(findings) == [], findings


def test_happy_path_strict_workflows_no_workflows(tmp_path: Path) -> None:
    """No workflows[] references and no workflows/ directory → still passes strict-workflows."""
    write_skill(tmp_path, "alpha")
    write_index(tmp_path, [minimal_skill("alpha")])

    findings = validate(tmp_path, strict_workflows=True)
    assert codes(findings) == [], findings


def test_warns_when_workflows_reference_missing_in_default(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(tmp_path, [minimal_skill("alpha", workflows=["nonexistent"])])

    findings = validate(tmp_path)  # default mode
    assert codes(findings) == [], findings
    assert "WF001" in warning_codes(findings)


# ---------------------------------------------------------------------------
# Index-level error codes
# ---------------------------------------------------------------------------


def test_idx001_duplicate_skill_id(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(tmp_path, [minimal_skill("alpha"), minimal_skill("alpha")])
    findings = validate(tmp_path)
    assert "IDX001" in codes(findings)


def test_idx002_index_entry_without_folder(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(tmp_path, [minimal_skill("alpha"), minimal_skill("ghost")])
    findings = validate(tmp_path)
    assert "IDX002" in codes(findings)


def test_idx003_folder_without_index_entry(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_skill(tmp_path, "orphan")
    write_index(tmp_path, [minimal_skill("alpha")])
    findings = validate(tmp_path)
    assert "IDX003" in codes(findings)


def test_idx004_frontmatter_name_mismatch(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha", frontmatter_name="wrong-name")
    write_index(tmp_path, [minimal_skill("alpha")])
    findings = validate(tmp_path)
    assert "IDX004" in codes(findings)


def test_idx005_invalid_category(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(tmp_path, [minimal_skill("alpha", category="bogus")])
    findings = validate(tmp_path)
    assert "IDX005" in codes(findings)


def test_idx006_invalid_status(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(tmp_path, [minimal_skill("alpha", status="bogus")])
    findings = validate(tmp_path)
    assert "IDX006" in codes(findings)


def test_idx007_invalid_integration_type(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(
        tmp_path,
        [
            minimal_skill(
                "alpha",
                integrations=[{"id": "x", "type": "bogus", "requirement": "required"}],
            )
        ],
    )
    findings = validate(tmp_path)
    assert "IDX007" in codes(findings)


def test_idx008_invalid_requirement(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(
        tmp_path,
        [
            minimal_skill(
                "alpha",
                integrations=[{"id": "x", "type": "broker", "requirement": "bogus"}],
            )
        ],
    )
    findings = validate(tmp_path)
    assert "IDX008" in codes(findings)


def test_idx009_empty_summary(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(tmp_path, [minimal_skill("alpha", summary="   ")])
    findings = validate(tmp_path)
    assert "IDX009" in codes(findings)


def test_idx010_missing_schema_version(tmp_path: Path) -> None:
    """schema_version absent or not equal to supported version → hard error."""
    import yaml as _yaml

    write_skill(tmp_path, "alpha")
    payload = {
        # schema_version intentionally missing
        "categories": [
            "market-regime",
            "core-portfolio",
            "swing-opportunity",
            "trade-planning",
            "trade-memory",
            "strategy-research",
            "advanced-satellite",
            "meta",
        ],
        "skills": [minimal_skill("alpha")],
    }
    (tmp_path / "skills-index.yaml").write_text(_yaml.safe_dump(payload), encoding="utf-8")
    findings = validate(tmp_path)
    assert "IDX010" in codes(findings)


def test_idx010_wrong_schema_version(tmp_path: Path) -> None:
    import yaml as _yaml

    write_skill(tmp_path, "alpha")
    payload = {
        "schema_version": 999,
        "categories": [
            "market-regime",
            "core-portfolio",
            "swing-opportunity",
            "trade-planning",
            "trade-memory",
            "strategy-research",
            "advanced-satellite",
            "meta",
        ],
        "skills": [minimal_skill("alpha")],
    }
    (tmp_path / "skills-index.yaml").write_text(_yaml.safe_dump(payload), encoding="utf-8")
    findings = validate(tmp_path)
    assert "IDX010" in codes(findings)


def test_idx011_missing_categories_block(tmp_path: Path) -> None:
    """categories block absent → hard error."""
    import yaml as _yaml

    write_skill(tmp_path, "alpha")
    payload = {
        "schema_version": 1,
        # categories intentionally missing
        "skills": [minimal_skill("alpha")],
    }
    (tmp_path / "skills-index.yaml").write_text(_yaml.safe_dump(payload), encoding="utf-8")
    findings = validate(tmp_path)
    assert "IDX011" in codes(findings)


def test_idx011_categories_not_canonical(tmp_path: Path) -> None:
    """categories block present but not the canonical 8 → hard error."""
    import yaml as _yaml

    write_skill(tmp_path, "alpha")
    payload = {
        "schema_version": 1,
        "categories": ["market-regime", "extra-bogus"],  # subset/different
        "skills": [minimal_skill("alpha")],
    }
    (tmp_path / "skills-index.yaml").write_text(_yaml.safe_dump(payload), encoding="utf-8")
    findings = validate(tmp_path)
    assert "IDX011" in codes(findings)


def test_idx011_categories_with_duplicate(tmp_path: Path) -> None:
    """All 8 canonical categories present, but one is duplicated → hard error.

    set() comparison alone would miss this; length check catches it.
    """
    import yaml as _yaml

    write_skill(tmp_path, "alpha")
    payload = {
        "schema_version": 1,
        "categories": [
            "market-regime",
            "market-regime",  # duplicated — set() would still equal VALID_CATEGORIES
            "core-portfolio",
            "swing-opportunity",
            "trade-planning",
            "trade-memory",
            "strategy-research",
            "advanced-satellite",
            "meta",
        ],
        "skills": [minimal_skill("alpha")],
    }
    (tmp_path / "skills-index.yaml").write_text(_yaml.safe_dump(payload), encoding="utf-8")
    findings = validate(tmp_path)
    assert "IDX011" in codes(findings)


def test_idx012_unknown_integration_warns_in_default(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(
        tmp_path,
        [
            minimal_skill(
                "alpha",
                integrations=[
                    {
                        "id": "unknown",
                        "type": "unknown",
                        "requirement": "unknown",
                        "note": "TODO",
                    }
                ],
            )
        ],
    )
    findings = validate(tmp_path)
    assert "IDX012" in warning_codes(findings)
    assert codes(findings) == []  # default mode: no errors


def test_idx012_unknown_integration_errors_in_strict_metadata(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(
        tmp_path,
        [
            minimal_skill(
                "alpha",
                integrations=[
                    {
                        "id": "unknown",
                        "type": "unknown",
                        "requirement": "unknown",
                        "note": "TODO",
                    }
                ],
            )
        ],
    )
    findings = validate(tmp_path, strict_metadata=True)
    assert "IDX012" in codes(findings)


# ---------------------------------------------------------------------------
# Workflow-level error codes (require --strict-workflows)
# ---------------------------------------------------------------------------


def _setup_minimal_workflow_repo(tmp_path: Path, **wf_overrides) -> None:
    """Create one skill + one valid workflow that we then mutate."""
    write_skill(tmp_path, "alpha")
    write_skill(tmp_path, "beta")
    write_index(
        tmp_path,
        [
            minimal_skill("alpha", workflows=["sample"]),
            minimal_skill("beta"),
        ],
    )
    base_wf = {
        "schema_version": 1,
        "id": "sample",
        "display_name": "Sample",
        "cadence": "daily",
        "estimated_minutes": 15,
        "required_skills": ["alpha"],
        "optional_skills": [],
        "artifacts": [
            {"id": "art1", "produced_by_step": 1, "required": True},
        ],
        "steps": [
            {
                "step": 1,
                "name": "Run alpha",
                "skill": "alpha",
                "produces": ["art1"],
                "decision_gate": False,
            }
        ],
        "journal_destination": "beta",
    }
    base_wf.update(wf_overrides)
    write_workflow(tmp_path, "sample", base_wf)


def test_wf001_workflow_file_missing(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(tmp_path, [minimal_skill("alpha", workflows=["ghost"])])
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF001" in codes(findings)


def test_wf002_workflow_id_filename_mismatch(tmp_path: Path) -> None:
    _setup_minimal_workflow_repo(tmp_path, id="wrong-id")
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF002" in codes(findings)


def test_wf003_step_skill_missing(tmp_path: Path) -> None:
    _setup_minimal_workflow_repo(
        tmp_path,
        required_skills=["alpha"],
        steps=[
            {
                "step": 1,
                "name": "Use ghost",
                "skill": "ghost-skill",
                "decision_gate": False,
            }
        ],
        artifacts=[],
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF003" in codes(findings)


def test_wf004_depends_on_future_step(tmp_path: Path) -> None:
    _setup_minimal_workflow_repo(
        tmp_path,
        required_skills=["alpha"],
        artifacts=[],
        steps=[
            {
                "step": 1,
                "name": "First",
                "skill": "alpha",
                "depends_on": [2],
                "decision_gate": False,
            },
            {
                "step": 2,
                "name": "Second",
                "skill": "alpha",
                "decision_gate": False,
            },
        ],
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF004" in codes(findings)


def test_wf005_decision_gate_missing_question(tmp_path: Path) -> None:
    _setup_minimal_workflow_repo(
        tmp_path,
        required_skills=["alpha"],
        artifacts=[],
        steps=[
            {
                "step": 1,
                "name": "Decide",
                "skill": "alpha",
                "decision_gate": True,
                # decision_question intentionally missing
            }
        ],
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF005" in codes(findings)


def test_wf006_journal_destination_missing(tmp_path: Path) -> None:
    _setup_minimal_workflow_repo(tmp_path, journal_destination="ghost-skill")
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF006" in codes(findings)


def test_wf007_artifact_consumed_before_produced(tmp_path: Path) -> None:
    _setup_minimal_workflow_repo(
        tmp_path,
        required_skills=["alpha"],
        artifacts=[
            {"id": "late_artifact", "produced_by_step": 2, "required": True},
        ],
        steps=[
            {
                "step": 1,
                "name": "Try to consume early",
                "skill": "alpha",
                "consumes": ["late_artifact"],
                "decision_gate": False,
            },
            {
                "step": 2,
                "name": "Produce late",
                "skill": "alpha",
                "produces": ["late_artifact"],
                "decision_gate": False,
            },
        ],
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF007" in codes(findings)


def test_wf008_deprecated_skill_required(tmp_path: Path) -> None:
    write_skill(tmp_path, "old-skill")
    write_skill(tmp_path, "beta")
    write_index(
        tmp_path,
        [
            minimal_skill("old-skill", status="deprecated", workflows=["sample"]),
            minimal_skill("beta"),
        ],
    )
    write_workflow(
        tmp_path,
        "sample",
        {
            "schema_version": 1,
            "id": "sample",
            "required_skills": ["old-skill"],
            "artifacts": [],
            "steps": [
                {
                    "step": 1,
                    "name": "Use deprecated",
                    "skill": "old-skill",
                    "decision_gate": False,
                }
            ],
            "journal_destination": "beta",
        },
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF008" in codes(findings)


def test_wf009_required_skill_not_in_steps(tmp_path: Path) -> None:
    _setup_minimal_workflow_repo(
        tmp_path,
        required_skills=["alpha", "beta"],  # beta is required but never used in a step
        artifacts=[],
        steps=[
            {
                "step": 1,
                "name": "Use alpha only",
                "skill": "alpha",
                "decision_gate": False,
            }
        ],
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF009" in codes(findings)


def test_wf011_optional_skill_not_in_index(tmp_path: Path) -> None:
    """optional_skills entry that does not exist in skills-index.yaml → error."""
    write_skill(tmp_path, "alpha")
    write_skill(tmp_path, "beta")
    write_index(
        tmp_path,
        [
            minimal_skill("alpha", workflows=["sample"]),
            minimal_skill("beta"),
        ],
    )
    write_workflow(
        tmp_path,
        "sample",
        {
            "schema_version": 1,
            "id": "sample",
            "required_skills": ["alpha"],
            "optional_skills": ["ghost-skill"],  # does not exist
            "artifacts": [],
            "steps": [{"step": 1, "name": "Run", "skill": "alpha", "decision_gate": False}],
            "journal_destination": "beta",
        },
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF011" in codes(findings)


def test_wf012_artifact_produced_by_step_mismatch(tmp_path: Path) -> None:
    """artifact says produced_by_step=N but step N does not list it in produces."""
    write_skill(tmp_path, "alpha")
    write_skill(tmp_path, "beta")
    write_index(
        tmp_path,
        [
            minimal_skill("alpha", workflows=["sample"]),
            minimal_skill("beta"),
        ],
    )
    write_workflow(
        tmp_path,
        "sample",
        {
            "schema_version": 1,
            "id": "sample",
            "required_skills": ["alpha"],
            "artifacts": [
                {"id": "ghost_artifact", "produced_by_step": 1, "required": True},
            ],
            "steps": [
                # Step 1 declares NO produces → mismatch
                {"step": 1, "name": "Run", "skill": "alpha", "decision_gate": False}
            ],
            "journal_destination": "beta",
        },
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF012" in codes(findings)


def test_wf012_step_produces_undeclared_artifact(tmp_path: Path) -> None:
    """step produces an artifact id that is not in artifacts: → error."""
    write_skill(tmp_path, "alpha")
    write_skill(tmp_path, "beta")
    write_index(
        tmp_path,
        [
            minimal_skill("alpha", workflows=["sample"]),
            minimal_skill("beta"),
        ],
    )
    write_workflow(
        tmp_path,
        "sample",
        {
            "schema_version": 1,
            "id": "sample",
            "required_skills": ["alpha"],
            "artifacts": [],  # nothing declared
            "steps": [
                {
                    "step": 1,
                    "name": "Run",
                    "skill": "alpha",
                    "produces": ["mystery"],
                    "decision_gate": False,
                }
            ],
            "journal_destination": "beta",
        },
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF012" in codes(findings)


def test_wf010_step_skill_not_in_required_skills(tmp_path: Path) -> None:
    _setup_minimal_workflow_repo(
        tmp_path,
        required_skills=[],  # alpha used in step 1 (non-optional) but not in required_skills
        artifacts=[],
        steps=[
            {
                "step": 1,
                "name": "Use alpha non-optional",
                "skill": "alpha",
                "decision_gate": False,
            }
        ],
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert "WF010" in codes(findings)


# ---------------------------------------------------------------------------
# Cross-cutting: optional steps and optional artifacts
# ---------------------------------------------------------------------------


def test_optional_step_skill_in_optional_skills_passes(tmp_path: Path) -> None:
    """Optional step.skill in optional_skills (not required_skills) should pass."""
    write_skill(tmp_path, "alpha")
    write_skill(tmp_path, "extra")
    write_skill(tmp_path, "beta")
    write_index(
        tmp_path,
        [
            minimal_skill("alpha", workflows=["sample"]),
            minimal_skill("extra"),
            minimal_skill("beta"),
        ],
    )
    write_workflow(
        tmp_path,
        "sample",
        {
            "schema_version": 1,
            "id": "sample",
            "required_skills": ["alpha"],
            "optional_skills": ["extra"],
            "artifacts": [],
            "steps": [
                {"step": 1, "name": "Required", "skill": "alpha", "decision_gate": False},
                {
                    "step": 2,
                    "name": "Optional",
                    "skill": "extra",
                    "optional": True,
                    "decision_gate": False,
                },
            ],
            "journal_destination": "beta",
        },
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert codes(findings) == [], findings


def test_consume_optional_artifact_passes(tmp_path: Path) -> None:
    """Consuming required: false artifact produced by an earlier step is OK."""
    write_skill(tmp_path, "alpha")
    write_skill(tmp_path, "beta")
    write_index(
        tmp_path,
        [
            minimal_skill("alpha", workflows=["sample"]),
            minimal_skill("beta"),
        ],
    )
    write_workflow(
        tmp_path,
        "sample",
        {
            "schema_version": 1,
            "id": "sample",
            "required_skills": ["alpha"],
            "artifacts": [
                {"id": "opt", "produced_by_step": 1, "required": False},
            ],
            "steps": [
                {
                    "step": 1,
                    "name": "Produce optional",
                    "skill": "alpha",
                    "optional": True,
                    "produces": ["opt"],
                    "decision_gate": False,
                },
                {
                    "step": 2,
                    "name": "Consume optional",
                    "skill": "alpha",
                    "consumes": ["opt"],
                    "decision_gate": False,
                },
            ],
            "journal_destination": "beta",
        },
    )
    findings = validate(tmp_path, strict_workflows=True)
    assert codes(findings) == [], findings


# ---------------------------------------------------------------------------
# strict-metadata
# ---------------------------------------------------------------------------


def test_strict_metadata_rejects_unknown_timeframe(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(tmp_path, [minimal_skill("alpha", timeframe="unknown")])
    findings = validate(tmp_path, strict_metadata=True)
    assert any(f.code == "IDX-META" and f.severity == "error" for f in findings)


def test_default_mode_warns_on_unknown_timeframe(tmp_path: Path) -> None:
    write_skill(tmp_path, "alpha")
    write_index(tmp_path, [minimal_skill("alpha", timeframe="unknown")])
    findings = validate(tmp_path)
    assert "IDX-META" in warning_codes(findings)
    assert codes(findings) == []


# ---------------------------------------------------------------------------
# Sanity: missing index file
# ---------------------------------------------------------------------------


def test_missing_index_file(tmp_path: Path) -> None:
    findings = validate(tmp_path)
    assert any(f.code == "IDX-MISSING" for f in findings)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
