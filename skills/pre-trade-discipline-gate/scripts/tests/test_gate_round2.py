"""Review round 2 gate regression tests (issue #514)."""

from __future__ import annotations

import json
from pathlib import Path

import approved_rules as ar
from test_check_pre_trade_discipline import base_candidate
from test_gate_approved_rules import R1, R2, _cli


def test_ledger_with_revived_rule_beside_its_former_successor_is_unavailable(
    tmp_path: Path, capsys
):
    revived = {
        "rule_id": ar.rule_id_for(R1),
        "text": R1,
        "status": "active",
        "effective_date": "2026-06-01",
        "review_after": "2026-07-31",
        "expires_on": None,
        "origin": "coach_accepted",
        "superseded_by": None,
        "evidence_ids": [],
        "history": [
            {"at": "2026-05-31T21:00:00+00:00", "event": "activated"},
            {
                "at": "2026-06-10T21:00:00+00:00",
                "event": "restored",
                "former_successors": [ar.rule_id_for(R2)],
            },
        ],
    }
    other = dict(revived, rule_id=ar.rule_id_for(R2), text=R2, history=revived["history"][:1])
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"schema_version": 1, "rules": [revived, other]}), encoding="utf-8")
    assert (
        _cli(tmp_path, {"candidates": [base_candidate()]}, "--approved-rules-ledger", str(path))
        == 0
    )
    out = capsys.readouterr().out
    assert "Approved rules: ledger unavailable" in out
    row = json.loads(next((tmp_path / "journal").glob("*.jsonl")).read_text().splitlines()[0])
    assert row["approved_rules"]["status"] == "unavailable"
    assert row["overall_decision"] == "REVIEW_REQUIRED"
