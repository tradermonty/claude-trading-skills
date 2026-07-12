import importlib.util
from pathlib import Path

import pytest
import yaml

SKILL_DIR = Path(__file__).resolve().parents[2]
SKILL_MD = SKILL_DIR / "SKILL.md"
IMPLEMENTATION_GUIDE = SKILL_DIR / "references" / "implementation_guide.md"
BUBBLE_SCORER = SKILL_DIR / "scripts" / "bubble_scorer.py"
HISTORICAL_CASES = SKILL_DIR / "references" / "historical_cases.md"
EXPECTED_FILES = (
    "scripts/bubble_scorer.py",
    "references/quick_reference.md",
    "references/quick_reference_en.md",
    "references/implementation_guide.md",
    "references/historical_cases.md",
    "references/bubble_framework.md",
)
QUICK_REFERENCES = (
    SKILL_DIR / "references" / "quick_reference.md",
    SKILL_DIR / "references" / "quick_reference_en.md",
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


def _load_bubble_scorer_module():
    spec = importlib.util.spec_from_file_location("bubble_scorer", BUBBLE_SCORER)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frontmatter_identifies_bubble_detector_skill() -> None:
    metadata = _frontmatter()

    assert metadata["name"] == "us-market-bubble-detector"
    assert "Minsky/Kindleberger framework v2.1" in metadata["description"]
    assert "mandatory data collection" in metadata["description"]


def test_required_script_and_references_are_present() -> None:
    for rel_path in EXPECTED_FILES:
        assert (SKILL_DIR / rel_path).is_file()


def test_prompt_contract_requires_quantitative_first_scoring() -> None:
    text = _skill_text()

    assert "Mandatory Quantitative Data Collection" in text
    assert "Do NOT proceed with evaluation without Phase 1 data collection" in text
    assert "Score mechanically based on collected data" in text
    assert "Final Score = Phase 2 Total (0-12 points) + Phase 3 Adjustment (0 to +3 points)" in text


def test_v21_qualitative_cap_is_consistent_in_checklists() -> None:
    combined = _skill_text() + "\n" + IMPLEMENTATION_GUIDE.read_text(encoding="utf-8")

    assert "within +3 point limit" in combined
    assert "total limit of +3 points" in combined
    assert "Total <= 3 points?" in combined
    assert "within +5 point limit" not in combined
    assert "total limit of +5 points" not in combined
    assert "Total <= 5 points?" not in combined
    assert "Total \u2264 5 points?" not in combined


def test_bubble_scorer_helper_uses_v21_score_model() -> None:
    module = _load_bubble_scorer_module()
    scorer = module.BubbleScorer()

    assert len(scorer.quantitative_indicators) == 6
    assert len(scorer.qualitative_adjustments) == 3

    quantitative_scores = {key: 2 for key in scorer.quantitative_indicators}
    qualitative_scores = {key: 1 for key in scorer.qualitative_adjustments}
    result = scorer.calculate_score(quantitative_scores, qualitative_scores)

    assert result["quantitative_score"] == 12
    assert result["qualitative_adjustment"] == 3
    assert result["total_score"] == 15
    assert result["max_score"] == 15
    assert result["phase"] == "Critical"
    assert result["risk_budget"] == "20-30%"

    bad_quantitative_scores = dict(quantitative_scores)
    bad_quantitative_scores["put_call_ratio"] = 3
    with pytest.raises(ValueError, match="put_call_ratio must be between 0 and 2"):
        scorer.calculate_score(bad_quantitative_scores, qualitative_scores)


def test_quick_references_use_v21_score_model() -> None:
    for path in QUICK_REFERENCES:
        text = path.read_text(encoding="utf-8")

        assert "6 quantitative indicators" in text
        assert "3 qualitative adjustments" in text
        assert "13-15" in text
        assert "Score 8 indicators" not in text
        assert "8 Indicators" not in text
        assert "13-16" not in text
        assert "5-8" not in text
        assert "9-12" not in text


def test_historical_cases_use_v21_score_model() -> None:
    text = HISTORICAL_CASES.read_text(encoding="utf-8")

    assert "Bubble-O-Meter v2.1 Score Estimate" in text
    assert "15/15 points" in text
    assert "13/15 points" in text
    assert "15/16 points" not in text
    assert "16/16 points" not in text
    assert "14/16 points" not in text
