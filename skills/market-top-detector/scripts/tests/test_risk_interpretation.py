"""Risk interpretation must survive JSON and Markdown report rendering."""

import json

from historical_comparator import COMPONENT_KEYS, compare_to_historical
from report_generator import generate_json_report, generate_markdown_report
from scorer import calculate_composite_score


def test_report_no_match_and_uncalibrated_score(tmp_path):
    analysis = {
        "composite": calculate_composite_score({key: 70 for key in COMPONENT_KEYS}),
        "historical_comparison": compare_to_historical({key: 0 for key in COMPONENT_KEYS}),
    }
    json_path = tmp_path / "report.json"
    md_path = tmp_path / "report.md"
    generate_json_report(analysis, str(json_path))
    generate_markdown_report(analysis, str(md_path))
    saved = json.loads(json_path.read_text())
    assert saved["composite"]["calibrated_probability"] is False
    assert saved["composite"]["score_kind"] == "heuristic_risk_score"
    assert saved["composite"]["zone"] == "Red (High Risk)"
    assert saved["historical_comparison"]["closest_match"] is None
    text = md_path.read_text()
    assert "Heuristic Risk Score" in text
    assert "not an estimated event probability" in text
    assert "No comparable episode" in text
    assert "Closest Pattern:** None" not in text
