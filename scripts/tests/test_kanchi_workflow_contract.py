"""Cross-skill contract tests for the Kanchi weekly workflow."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / "workflows" / "kanchi-dividend-weekly.yaml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_kanchi_workflow_uses_canonical_tmc_output_artifact() -> None:
    workflow = _workflow()
    artifacts = {item["id"] for item in workflow["artifacts"]}
    final_step = max(workflow["steps"], key=lambda item: item["step"])

    assert "thesis_record" in artifacts
    assert "kanchi_thesis_entry" not in artifacts
    assert final_step["skill"] == "trader-memory-core"
    assert final_step["produces"] == ["thesis_record"]


def test_kanchi_workflow_declares_distinct_optional_holdings_inputs() -> None:
    workflow = _workflow()
    manual_inputs = {item["id"]: item for item in workflow["manual_inputs"]}
    steps = {item["step"]: item for item in workflow["steps"]}

    tax_input = manual_inputs["tax_holdings_input"]
    assert tax_input["required"] is False
    assert tax_input["used_by_steps"] == [4]
    assert steps[4]["optional"] is True
    assert (ROOT / tax_input["schema_ref"]).is_file()
    assert tax_input["schema_ref"].endswith(
        "kanchi-dividend-us-tax-accounting/references/input-schema.md"
    )

    monitor_input = manual_inputs["review_monitor_input"]
    assert monitor_input["required"] is False
    assert monitor_input["used_by_steps"] == [5]
    assert steps[5]["optional"] is True
    assert (ROOT / monitor_input["schema_ref"]).is_file()
    assert monitor_input["schema_ref"].endswith(
        "kanchi-dividend-review-monitor/references/input-schema.md"
    )
