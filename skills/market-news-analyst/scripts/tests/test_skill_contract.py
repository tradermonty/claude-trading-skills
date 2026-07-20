from pathlib import Path

import yaml

SKILL_DIR = Path(__file__).resolve().parents[2]
SKILL_MD = SKILL_DIR / "SKILL.md"
EXPECTED_REFERENCES = (
    "references/market_event_patterns.md",
    "references/trusted_news_sources.md",
    "references/geopolitical_commodity_correlations.md",
    "references/corporate_news_impact.md",
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


def test_frontmatter_identifies_market_news_skill() -> None:
    metadata = _frontmatter()

    assert metadata["name"] == "market-news-analyst"
    assert "market-moving news" in metadata["description"]
    assert "past 10 days" in metadata["description"]


def test_reference_knowledge_base_is_present_and_named() -> None:
    text = _skill_text()

    for rel_path in EXPECTED_REFERENCES:
        assert (SKILL_DIR / rel_path).is_file()
        assert rel_path in text


def test_prompt_contract_requires_recency_sources_and_impact_ranking() -> None:
    text = _skill_text()

    assert "past 10 days" in text
    assert "Recommended News Sources" in text
    assert "publication dates" in text
    assert "Impact Magnitude Assessment" in text
    assert "ranked by market impact significance" in text
