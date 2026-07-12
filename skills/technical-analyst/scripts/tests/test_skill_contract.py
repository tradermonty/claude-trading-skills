from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parents[2]
SKILL_MD = SKILL_DIR / "SKILL.md"
EXPECTED_RESOURCES = (
    "references/technical_analysis_framework.md",
    "assets/analysis_template.md",
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


def test_frontmatter_identifies_chart_only_technical_skill() -> None:
    metadata = _frontmatter()

    assert metadata["name"] == "technical-analyst"
    assert "weekly price charts" in metadata["description"]
    assert "without consideration of news or fundamental factors" in metadata["description"]


def test_required_framework_and_template_are_present_and_named() -> None:
    text = _skill_text()

    for rel_path in EXPECTED_RESOURCES:
        assert (SKILL_DIR / rel_path).is_file()
        assert rel_path in text


def test_prompt_contract_requires_chart_input_and_probabilistic_output() -> None:
    text = _skill_text()

    assert "Chart Images" in text
    assert "Pure Chart Analysis" in text
    assert "Probabilistic Scenarios" in text
    assert "[SYMBOL]_technical_analysis_[YYYY-MM-DD].md" in text
