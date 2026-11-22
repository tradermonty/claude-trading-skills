"""Contract tests: workflows declare the approved-rule inputs of the adherence loop (#514)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / "workflows"
GATE_SKILL = "pre-trade-discipline-gate"
SCHEMA_REF = "skills/pre-trade-discipline-gate/references/rule_adherence.md"
PACKAGE = ROOT / "skill-packages" / "pre-trade-discipline-gate.skill"


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / f"{name}.yaml").read_text(encoding="utf-8"))


def _inputs(workflow: dict) -> dict:
    return {item["id"]: item for item in workflow.get("manual_inputs", [])}


def _gate_workflows() -> dict:
    found = {}
    for path in sorted(WORKFLOWS.glob("*.yaml")):
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        steps = [s["step"] for s in workflow.get("steps", []) if s.get("skill") == GATE_SKILL]
        if steps:
            found[workflow["id"]] = (workflow, steps)
    return found


def test_the_known_gate_workflows_are_covered() -> None:
    assert {"swing-opportunity-daily", "earnings-weekly", "stockbee-ep-daily"} <= set(
        _gate_workflows()
    )


@pytest.mark.parametrize("workflow_id", sorted(_gate_workflows()))
def test_gate_workflows_declare_the_optional_approved_rule_ledger(workflow_id: str) -> None:
    workflow, gate_steps = _gate_workflows()[workflow_id]
    entry = _inputs(workflow)["approved_rules_ledger"]
    assert entry["required"] is False
    assert entry["used_by_steps"] == gate_steps
    assert entry["schema_ref"] == SCHEMA_REF
    assert (ROOT / entry["schema_ref"]).is_file()
    assert entry["description"].strip() and entry["description_ja"].strip()


def test_monthly_review_declares_the_prior_rule_adherence_report() -> None:
    workflow = _load("monthly-performance-review")
    entry = _inputs(workflow)["prior_rule_adherence"]
    assert entry["required"] is False
    assert entry["used_by_steps"] == [6]
    assert entry["schema_ref"] == SCHEMA_REF
    assert (ROOT / entry["schema_ref"]).is_file()
    assert entry["description"].strip() and entry["description_ja"].strip()
    for key in ("manual_review", "manual_review_ja"):
        assert any("review_rule_adherence.py" in item for item in workflow[key]), key


def test_package_ships_the_adherence_script_and_reference() -> None:
    with zipfile.ZipFile(PACKAGE) as archive:
        names = archive.namelist()
    assert f"{GATE_SKILL}/scripts/review_rule_adherence.py" in names
    assert f"{GATE_SKILL}/references/rule_adherence.md" in names
