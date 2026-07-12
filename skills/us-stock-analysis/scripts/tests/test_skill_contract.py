from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parents[2]
SKILL_MD = SKILL_DIR / "SKILL.md"
EXPECTED_REFERENCES = (
    "references/fundamental-analysis.md",
    "references/financial-metrics.md",
    "references/report-template.md",
    "references/technical-analysis.md",
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


def test_frontmatter_identifies_us_stock_analysis_skill() -> None:
    metadata = _frontmatter()

    assert metadata["name"] == "us-stock-analysis"
    assert "Comprehensive US stock analysis" in metadata["description"]
    assert "investment recommendations" in metadata["description"]


def test_required_references_are_present_and_named() -> None:
    text = _skill_text()

    for rel_path in EXPECTED_REFERENCES:
        assert (SKILL_DIR / rel_path).is_file()
        assert rel_path in text


def test_prompt_contract_requires_data_sources_and_analysis_modes() -> None:
    text = _skill_text()

    assert "Always use web search tools to gather current market data" in text
    assert "Basic Stock Info" in text
    assert "Fundamental Analysis" in text
    assert "Technical Analysis" in text
    assert "Comprehensive Investment Report" in text
