from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parents[2]
SKILL_MD = SKILL_DIR / "SKILL.md"
EXPECTED_REFERENCES = (
    "references/headline_event_patterns.md",
    "references/sector_sensitivity_matrix.md",
    "references/scenario_playbooks.md",
)


def _skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


def _frontmatter() -> dict:
    text = _skill_text()
    assert text.startswith("---\n")
    _prefix, raw_yaml, _body = text.split("---", 2)
    metadata = yaml.safe_load(raw_yaml)
    assert isinstance(metadata, dict)
    return metadata


def test_frontmatter_identifies_scenario_analyzer_skill() -> None:
    metadata = _frontmatter()

    assert metadata["name"] == "scenario-analyzer"
    assert "18-month scenarios" in metadata["description"]
    assert "strategy-reviewer" in metadata["description"]


def test_required_references_are_present_and_named() -> None:
    text = _skill_text()

    for rel_path in EXPECTED_REFERENCES:
        assert (SKILL_DIR / rel_path).is_file()
        assert rel_path in text


def test_orchestration_contract_keeps_primary_and_review_agents() -> None:
    text = _skill_text()

    assert 'subagent_type: "scenario-analyst"' in text
    assert 'subagent_type: "strategy-reviewer"' in text
    assert "probabilities sum to 100%" in text
    assert "reports/scenario_analysis_<topic>_YYYYMMDD.md" in text
    assert "1st/2nd/3rd-order impacts" in text
