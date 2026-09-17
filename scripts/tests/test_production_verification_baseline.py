"""Audit-contract tests for the production verification baseline."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
AXES = {
    "instruction_contract",
    "unit_tests",
    "workflow_contract",
    "end_to_end_replay",
    "data_provenance",
    "financial_logic_review",
    "empirical_validation",
    "security_review",
}
VALUES = {"passed", "not_verified", "not_applicable"}


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _resolve_axis(profile_axis: dict, override: dict | None) -> dict:
    return override if override is not None else profile_axis


def _assert_evidence_entries(evidence: list) -> None:
    assert isinstance(evidence, list), "evidence must be a list"
    for entry in evidence:
        assert isinstance(entry, dict) and entry, "evidence entries must be nonempty mappings"
        for key, value in entry.items():
            assert isinstance(key, str) and key.strip(), "evidence keys must be nonblank strings"
            assert isinstance(value, str) and value.strip(), (
                "evidence values must be nonblank strings"
            )


@pytest.mark.parametrize(
    "evidence",
    [
        "command",
        ["t"],
        [{"command": "valid command"}, "i"],
        [{}],
        [{"command": " "}],
        [{"command": None}],
        [{"command": 18}],
        [{"": "valid command"}],
        [{1: "valid command"}],
    ],
)
def test_malformed_evidence_is_rejected(evidence: list) -> None:
    with pytest.raises(AssertionError):
        _assert_evidence_entries(evidence)


def test_structured_evidence_is_accepted() -> None:
    _assert_evidence_entries([])
    _assert_evidence_entries(
        [
            {"path": ".github/workflows/ci.yml", "job": "security"},
            {"spec + schema": "replay.yaml with replay-contract.schema.json"},
        ]
    )


def test_baseline_covers_exactly_current_production_skills() -> None:
    index = _load_yaml(ROOT / "skills-index.yaml")
    baseline = _load_yaml(ROOT / "docs/dev/production-verification-baseline.yaml")

    production = {
        skill["id"]: skill for skill in index["skills"] if skill["status"] == "production"
    }
    rows = baseline["skills"]
    row_ids = [row["id"] for row in rows]

    assert len(row_ids) == len(set(row_ids)), "duplicate skill IDs in baseline"
    assert set(row_ids) == set(production)
    assert set(baseline["profiles"])

    audit = baseline["audit"]
    assert len(audit["baseline_commit"]) == 40
    int(audit["baseline_commit"], 16)
    date.fromisoformat(str(audit["assessed_at"]))

    gate = baseline["external_release_gates"]["open_high_severity_issues"]
    assert gate["status"] in {"checked", "not_evaluated"}
    assert isinstance(gate["query"], str) and gate["query"].strip()
    assert "checked_at" in gate

    for row in rows:
        assert set(row) <= {"id", "profile", "overrides"}
        profile = baseline["profiles"][row["profile"]]
        profile_axes = profile["axes"]
        overrides = row.get("overrides") or {}
        assert set(profile_axes) == AXES
        assert set(overrides) <= AXES

        resolved_values = {}
        for axis in AXES:
            resolved = _resolve_axis(profile_axes[axis], overrides.get(axis))
            assert resolved["value"] in VALUES
            assert isinstance(resolved["rationale"], str) and resolved["rationale"].strip()
            _assert_evidence_entries(resolved["evidence"])
            if resolved["value"] == "passed":
                assert axis in overrides, "passed requires skill-specific evidence override"
                assert resolved["evidence"], "passed requires auditable evidence"
            resolved_values[axis] = resolved["value"]

        assert resolved_values == production[row["id"]]["verification"]

        skill = production[row["id"]]
        script_dir = ROOT / "skills" / row["id"] / "scripts"
        has_scripts = script_dir.is_dir() and any(script_dir.glob("*.py"))
        has_workflows = bool(skill.get("workflows"))
        assert (resolved_values["unit_tests"] == "not_applicable") is (not has_scripts)
        assert (resolved_values["workflow_contract"] == "not_applicable") is (not has_workflows)
        assert (resolved_values["end_to_end_replay"] == "not_applicable") is (not has_workflows)


def test_date_price_unit_skills_do_not_claim_financial_review_is_not_applicable() -> None:
    index = _load_yaml(ROOT / "skills-index.yaml")
    by_id = {skill["id"]: skill for skill in index["skills"]}

    for skill_id in (
        "data-quality-checker",
        "earnings-calendar",
        "economic-calendar-fetcher",
    ):
        assert by_id[skill_id]["verification"]["financial_logic_review"] == "not_verified"
