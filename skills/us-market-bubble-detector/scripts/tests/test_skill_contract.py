import importlib.util
import json
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


def test_bubble_scorer_covers_every_risk_band_and_minsky_boundary() -> None:
    module = _load_bubble_scorer_module()
    scorer = module.BubbleScorer()

    expectations = (
        (0, "Normal", "Displacement/Early Boom"),
        (5, "Caution", "Displacement/Early Boom"),
        (8, "Elevated Risk", "Late Boom/Elevated Risk"),
        (10, "Euphoria", "Late Boom/Early Euphoria"),
        (13, "Critical", "Peak Euphoria/Profit Taking"),
    )
    for total, phase, minsky_phase in expectations:
        quantitative = {key: 0 for key in scorer.quantitative_indicators}
        qualitative = {key: 0 for key in scorer.qualitative_adjustments}
        remaining = total
        for key in quantitative:
            assigned = min(2, remaining)
            quantitative[key] = assigned
            remaining -= assigned
        for key in qualitative:
            assigned = min(1, remaining)
            qualitative[key] = assigned
            remaining -= assigned

        result = scorer.calculate_score(quantitative, qualitative)

        assert result["total_score"] == total
        assert result["phase"] == phase
        assert result["minsky_phase"] == minsky_phase


def test_bubble_scorer_distinguishes_boom_and_euphoria_components() -> None:
    module = _load_bubble_scorer_module()
    scorer = module.BubbleScorer()
    quantitative = {key: 0 for key in scorer.quantitative_indicators}
    qualitative = {key: 0 for key in scorer.qualitative_adjustments}

    quantitative.update(price_acceleration=1, volatility_suppression=1, leverage=2, ipo_heat=1)
    assert scorer.calculate_score(quantitative, qualitative)["minsky_phase"] == "Boom"

    quantitative.update(
        put_call_ratio=1,
        price_acceleration=2,
        breadth_anomaly=2,
        leverage=2,
        ipo_heat=2,
    )
    result = scorer.calculate_score(quantitative, qualitative)
    assert result["total_score"] == 10
    assert result["minsky_phase"] == "Euphoria"


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (lambda scores: scores.pop("put_call_ratio"), "Missing score"),
        (lambda scores: scores.update(unknown=0), "Unknown score"),
        (lambda scores: scores.update(put_call_ratio=True), "must be an integer"),
        (lambda scores: scores.update(put_call_ratio=1.5), "must be an integer"),
    ),
)
def test_bubble_scorer_rejects_incomplete_or_ambiguous_scores(mutation, message) -> None:
    module = _load_bubble_scorer_module()
    scorer = module.BubbleScorer()
    scores = {key: 0 for key in scorer.indicators}
    mutation(scores)

    with pytest.raises(ValueError, match=message):
        scorer.calculate_score(scores)


def test_bubble_scorer_formats_low_medium_and_high_indicator_states() -> None:
    module = _load_bubble_scorer_module()
    scorer = module.BubbleScorer()
    quantitative = {key: 0 for key in scorer.quantitative_indicators}
    qualitative = {key: 0 for key in scorer.qualitative_adjustments}
    quantitative.update(put_call_ratio=2, volatility_suppression=1)

    result = scorer.calculate_score(quantitative, qualitative)
    output = scorer.format_output(result)
    statuses = {
        item["indicator"]: item["status"] for item in result["detailed_quantitative_indicators"]
    }

    assert statuses["Put/Call Ratio"] == "high"
    assert statuses["Volatility Suppression + New Highs"] == "medium"
    assert statuses["Leverage"] == "low"
    assert "Final score: 3/15" in output
    assert "Qualitative adjustments:" in output


def test_scores_json_supports_flat_and_nested_contracts() -> None:
    module = _load_bubble_scorer_module()
    scorer = module.BubbleScorer()
    quantitative = {key: 0 for key in scorer.quantitative_indicators}
    qualitative = {key: 0 for key in scorer.qualitative_adjustments}
    flat = {**quantitative, **qualitative}

    assert module._scores_from_json(json.dumps(flat)) == (flat, None)
    assert module._scores_from_json(
        json.dumps({"quantitative": quantitative, "qualitative": qualitative})
    ) == (quantitative, qualitative)
    with pytest.raises(ValueError, match="JSON object"):
        module._scores_from_json("[]")
    with pytest.raises(ValueError, match="nested scores"):
        module._scores_from_json('{"quantitative": []}')


def test_manual_assessment_reprompts_invalid_values(monkeypatch, capsys) -> None:
    module = _load_bubble_scorer_module()
    answers = iter(["not-a-number", "3", "2", *(["0"] * 8)])
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))

    scores = module.manual_assessment()

    assert scores["put_call_ratio"] == 2
    assert len(scores) == 9
    output = capsys.readouterr().out
    assert "Enter a numeric value" in output
    assert "Enter a value between 0 and 2" in output


def test_cli_emits_json_and_fails_closed_on_invalid_input(monkeypatch, capsys) -> None:
    module = _load_bubble_scorer_module()
    scorer = module.BubbleScorer()
    scores = {key: 0 for key in scorer.indicators}
    monkeypatch.setattr(
        "sys.argv",
        ["bubble_scorer.py", "--scores", json.dumps(scores), "--output", "json"],
    )

    assert module.main() == 0
    assert json.loads(capsys.readouterr().out)["total_score"] == 0

    monkeypatch.setattr("sys.argv", ["bubble_scorer.py", "--scores", "not-json"])
    assert module.main() == 1
    assert "Error:" in capsys.readouterr().out

    monkeypatch.setattr("sys.argv", ["bubble_scorer.py"])
    assert module.main() == 1
    assert "specify --manual or --scores" in capsys.readouterr().out


@pytest.mark.parametrize("path", QUICK_REFERENCES, ids=lambda path: path.name)
def test_emergency_questions_require_full_evaluation_before_verdict(path) -> None:
    text = path.read_text(encoding="utf-8")
    emergency = text.split("## Emergency Assessment: 3 Questions", 1)[1].split("\n---", 1)[0]

    assert "All 3 YES → Strong warning signal" in emergency
    assert "Phase 1 data collection" in emergency
    assert "Phase 2 quantitative scoring" in emergency
    assert "Phase 3 evidence-based adjustments" in emergency
    assert "Critical requires a final score of 13-15" in emergency
    assert "leave the assessment incomplete" in emergency
    assert "YES/NO answers alone establish neither a phase nor an action" in emergency
    for shortcut in ("Critical zone", "Euphoria stage", "Still early", "healthy state"):
        assert shortcut not in emergency
    assert "When taxi drivers talk stocks, exit" not in text


def test_framework_social_signal_requires_quantitative_assessment() -> None:
    text = (SKILL_DIR / "references" / "bubble_framework.md").read_text(encoding="utf-8")
    assert "When taxi drivers talk stocks, exit" not in text
    assert "When taxi drivers talk stocks, run the full quantitative assessment" in text
    assert "Social anecdotes alone establish neither a phase nor an exit decision" in text


def test_japanese_emergency_example_is_warning_only() -> None:
    guide = SKILL_DIR.parents[1] / "docs" / "ja" / "skills" / "us-market-bubble-detector.md"
    text = guide.read_text(encoding="utf-8")
    emergency = text.split("**緊急時の簡易チェック：**", 1)[1].split("\n---", 1)[0]
    assert "警戒シグナル" in emergency
    assert "Phase 1" in emergency and "Phase 2" in emergency and "Phase 3" in emergency
    assert "3質問だけでフェーズや売買アクションを決めません" in emergency
    assert "データが不足する場合は評価未完了" in emergency
