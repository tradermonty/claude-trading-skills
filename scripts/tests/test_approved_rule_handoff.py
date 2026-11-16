"""Contract test for the monthly-rule -> approved-rule ledger -> pre-trade gate handoff (#514).

Activates rules from the committed monthly example artifacts into a temporary ledger and runs
the gate CLI against it. Fails if either committed artifact shape drifts from what
``manage_approved_rules.py activate`` accepts. Fictional data only.
"""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "pre-trade-discipline-gate"
MANAGE = SKILL / "scripts" / "manage_approved_rules.py"
GATE = SKILL / "scripts" / "check_pre_trade_discipline.py"
MONTHLY = ROOT / "examples" / "workflows" / "monthly-performance-review"
REPLAY_FULL = MONTHLY / "replay-run-full-path" / "06_rule_changes_for_next_month.yaml"
REPLAY_REQUIRED_ONLY = MONTHLY / "replay-run" / "06_rule_changes_for_next_month.yaml"
SAMPLE_FULL = MONTHLY / "sample-run-full-path" / "06_rule_changes_for_next_month.yaml"
PACKAGE = ROOT / "skill-packages" / "pre-trade-discipline-gate.skill"


def _run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *argv], capture_output=True, text=True)


def _activate(ledger: Path, rule_file: Path, *extra: str) -> subprocess.CompletedProcess:
    return _run(
        str(MANAGE),
        "activate",
        "--ledger",
        str(ledger),
        "--rule-changes",
        str(rule_file),
        "--effective-date",
        "2026-06-01",
        "--confirm-activation",
        *extra,
    )


def _gate(tmp_path: Path, ledger: Path, checks: list[dict] | None) -> dict:
    market = tmp_path / "exposure.json"
    circuit = tmp_path / "circuit.json"
    market.write_text(json.dumps({"recommendation": "NEW_ENTRY_ALLOWED"}), encoding="utf-8")
    circuit.write_text(json.dumps({"recommendation": "TRADING_ALLOWED"}), encoding="utf-8")
    candidate = {
        "symbol": "TEST",
        "order_intent": "ENTRY_READY",
        "entry_in_written_plan": True,
        "stop_predefined": True,
        "size_within_plan": True,
        "planned_risk_dollars": 500,
        "actual_risk_dollars": 500,
    }
    if checks is not None:
        candidate["approved_rule_checks"] = checks
    answers = tmp_path / "answers.json"
    answers.write_text(json.dumps({"candidates": [candidate]}), encoding="utf-8")
    out_dir = tmp_path / "reports"
    proc = _run(
        str(GATE),
        "--answers-file",
        str(answers),
        "--approved-rules-ledger",
        str(ledger),
        "--market-regime-decision",
        str(market),
        "--circuit-breaker-decision",
        str(circuit),
        "--output-dir",
        str(out_dir),
        "--journal-dir",
        str(tmp_path / "journal"),
        "--as-of",
        "2026-06-10",
        "--json-only",
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(next(out_dir.glob("*.json")).read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("rule_file", "extra", "expected_origin", "expected_count"),
    [
        (REPLAY_FULL, ("--review-after", "2026-06-30"), "coach_modified", 3),
        (
            SAMPLE_FULL,
            ("--source-review-id", "monthly_sample_fictional"),
            "sample_accepted",
            2,
        ),
    ],
    ids=["replay-shape", "sample-shape"],
)
def test_committed_monthly_artifact_activates_and_drives_the_gate(
    tmp_path, rule_file, extra, expected_origin, expected_count
):
    ledger = tmp_path / "state" / "approved_rules.json"
    proc = _activate(ledger, rule_file, *extra)
    assert proc.returncode == 0, proc.stderr
    rules = json.loads(ledger.read_text(encoding="utf-8"))["rules"]
    assert len(rules) == expected_count
    assert {r["origin"] for r in rules} == {expected_origin}

    # Without acknowledgements every applied rule blocks the order for review.
    blocked_dir = tmp_path / "blocked"
    blocked_dir.mkdir()
    blocked = _gate(blocked_dir, ledger, checks=None)
    assert blocked["overall_decision"] == "REVIEW_REQUIRED"
    assert blocked["approved_rules"]["status"] == "loaded"
    assert len(blocked["approved_rules"]["applied"]) == expected_count
    reasons = blocked["candidate_results"][0]["reasons"]
    assert len(reasons) == expected_count
    assert all("not acknowledged" in reason for reason in reasons)

    # Acknowledging each applied rule clears the gate.
    acked_dir = tmp_path / "acked"
    acked_dir.mkdir()
    checks = [{"rule_id": rule["rule_id"], "status": "followed", "note": ""} for rule in rules]
    acked = _gate(acked_dir, ledger, checks=checks)
    assert acked["overall_decision"] == "GO"


def test_required_only_replay_golden_has_nothing_to_activate_without_the_flag(tmp_path):
    ledger = tmp_path / "state" / "approved_rules.json"
    proc = _activate(ledger, REPLAY_REQUIRED_ONLY, "--review-after", "2026-06-30")
    assert proc.returncode == 1
    assert "nothing to activate" in proc.stderr
    assert not ledger.exists()


def test_required_only_replay_golden_activates_trade_rule_changes_with_the_flag(tmp_path):
    ledger = tmp_path / "state" / "approved_rules.json"
    proc = _activate(
        ledger,
        REPLAY_REQUIRED_ONLY,
        "--review-after",
        "2026-06-30",
        "--include-trade-rule-changes",
        "--source-review-id",
        "monthly_2026-05_fictional",
    )
    assert proc.returncode == 0, proc.stderr
    rules = json.loads(ledger.read_text(encoding="utf-8"))["rules"]
    assert len(rules) == 3
    assert {r["origin"] for r in rules} == {"trade_rule_change"}


def test_packaged_skill_ships_the_ledger_scripts_and_no_tests():
    with zipfile.ZipFile(PACKAGE) as archive:
        names = archive.namelist()
    prefix = "pre-trade-discipline-gate/scripts/"
    assert f"{prefix}approved_rules.py" in names
    assert f"{prefix}manage_approved_rules.py" in names
    assert not [n for n in names if "/tests/" in n or Path(n).name.startswith("test_")]
