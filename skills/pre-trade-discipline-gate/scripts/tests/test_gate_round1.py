"""Review round 1 gate regression tests (issue #514)."""

from __future__ import annotations

from pathlib import Path

from test_check_pre_trade_discipline import base_candidate
from test_gate_approved_rules import R1, _cli, ack, make_ledger, rule


def test_stdout_prints_only_approved_rule_warnings(tmp_path: Path, capsys):
    state = tmp_path / "theses"
    state.mkdir()
    (state / "th_broken.yaml").write_text("- not\n- an object\n", encoding="utf-8")
    ledger = make_ledger(tmp_path, rule(R1, review_after="2026-07-01"))
    answers = {"candidates": [base_candidate(approved_rule_checks=[ack(R1), ack("other rule")])]}
    rc = _cli(
        tmp_path,
        answers,
        "--approved-rules-ledger",
        str(ledger),
        "--state-dir",
        str(state),
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "Warning: approved rule" in out and "past its review date" in out
    assert "does not match an applied rule" in out
    assert "Skipped" not in out and "th_broken" not in out
