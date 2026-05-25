from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPT_DIR))

import review_trade_performance as rpc  # noqa: E402


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_clean_process_loss_is_ok_or_warn_without_behavior_tag():
    report = rpc.build_review(load("single_trade_clean_loss.json"), ["fixture"])
    assert report["overall_verdict"] == "OK"
    assert report["summary"]["primary_root_cause"] == "randomness"
    assert report["scores"]["risk_score"] == 100
    tags = {t["tag"] for t in report["behavioral_pattern_tags"]}
    assert tags == {"no_pattern_detected"}
    assert "financial advice" in report["disclaimer"].lower()


def test_rule_violation_loss_detects_fomo_size_creep_and_stop_moved():
    report = rpc.build_review(load("single_trade_rule_violation_loss.json"), ["fixture"])
    assert report["overall_verdict"] == "COOL_DOWN"
    tags = {t["tag"] for t in report["behavioral_pattern_tags"]}
    assert {"fomo_entry", "size_creep", "stop_moved"}.issubset(tags)
    process_rules = {f["rule"]: f for f in report["process_adherence_findings"]}
    assert process_rules["setup_confirmation"]["severity"] == "critical"
    assert process_rules["market_regime_gate"]["severity"] == "critical"
    assert any(
        n["topic"] == "position_size" and n["severity"] == "critical"
        for n in report["risk_manager_notes"]
    )
    assert any("0.5R" in r["rule"] for r in report["next_session_operating_rules"])


def test_partial_close_stop_moved_detects_stop_pattern():
    report = rpc.build_review(load("partial_close_stop_moved.json"), ["fixture"])
    assert report["review_type"] == "partial_close"
    # Note (2026-05-24 PR-F Blocker 1 fix): execution_quality_assessment now contributes
    # to determine_verdict. An unplanned stop move surfaces as critical in both the
    # process_adherence (stop_change_rule) and execution_quality (stop phase) axes,
    # so critical_count reaches 2 and the verdict escalates to COOL_DOWN. This is
    # conservative-side correct — stop_moved without a pre-defined rule is materially
    # serious — so COOL_DOWN is included alongside RULE_VIOLATION / REVIEW_REQUIRED here.
    assert report["overall_verdict"] in {"RULE_VIOLATION", "REVIEW_REQUIRED", "COOL_DOWN"}
    tags = {t["tag"] for t in report["behavioral_pattern_tags"]}
    assert "stop_moved" in tags
    assert any(e["phase"] == "stop" for e in report["execution_quality_assessment"])


def test_monthly_aggregate_revenge_pattern_cool_down():
    report = rpc.build_review(load("monthly_aggregate_revenge_pattern.json"), ["fixture"])
    assert report["review_type"] == "monthly_aggregate"
    assert report["overall_verdict"] == "COOL_DOWN"
    tags = {t["tag"] for t in report["behavioral_pattern_tags"]}
    assert "revenge_trade" in tags
    assert any("review-only" in r["rule"].lower() for r in report["next_session_operating_rules"])


def test_incomplete_record_degrades_without_crashing():
    report = rpc.build_review(load("incomplete_record.json"), ["fixture"])
    assert report["overall_verdict"] in {"REVIEW_REQUIRED", "WARN"}
    assert report["scores"]["review_quality_score"] < 80
    assert any(f["status"] == "unclear" for f in report["process_adherence_findings"])
    assert report["human_decision_gate"]["default_action"] == "journal_only"


def test_premature_exit_is_not_verdict_ok():
    """Blocker 1 regression (2026-05-24 PR-F review):
    actual.premature_exit=true must escalate the verdict beyond OK
    (execution warnings now contribute to determine_verdict).
    """
    report = rpc.build_review(load("single_trade_premature_exit.json"), ["fixture"])
    assert report["overall_verdict"] != "OK"
    assert report["overall_verdict"] in {"REVIEW_REQUIRED", "WARN", "RULE_VIOLATION", "COOL_DOWN"}
    assert any(
        e["phase"] == "exit" and e["severity"] == "warning"
        for e in report["execution_quality_assessment"]
    )
    tags = {t["tag"] for t in report["behavioral_pattern_tags"]}
    assert "premature_exit" in tags


def test_missing_risk_data_does_not_tag_size_creep():
    """Blocker 2 regression (2026-05-24 PR-F review):
    size_creep must require explicit evidence that actual.risk_r > reference_r.
    A missing-risk-data position_size warning must NOT be tagged as size_creep;
    instead it should surface as unknown_size_discipline.
    """
    report = rpc.build_review(load("risk_data_missing_no_size_creep.json"), ["fixture"])
    tags = {t["tag"] for t in report["behavioral_pattern_tags"]}
    assert "size_creep" not in tags
    assert "unknown_size_discipline" in tags
    assert any(
        n["topic"] == "position_size" and n["severity"] == "warning"
        for n in report["risk_manager_notes"]
    )


def test_cli_writes_json_and_markdown(tmp_path):
    fixture = FIXTURES / "single_trade_rule_violation_loss.json"
    rc = rpc.main(
        [
            "--input",
            str(fixture),
            "--output-dir",
            str(tmp_path),
            "--json-name",
            "report.json",
            "--markdown",
        ]
    )
    assert rc == 0
    report_json = tmp_path / "report.json"
    report_md = tmp_path / "report.md"
    assert report_json.exists()
    assert report_md.exists()
    data = json.loads(report_json.read_text(encoding="utf-8"))
    assert data["overall_verdict"] == "COOL_DOWN"
    assert "Human Decision Gate" in report_md.read_text(encoding="utf-8")
