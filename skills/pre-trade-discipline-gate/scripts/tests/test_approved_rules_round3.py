"""Review round 3 regression tests for the approved-rule ledger (issue #514)."""

from __future__ import annotations

from pathlib import Path

import approved_rules as ar
import pytest
from test_approved_rules import R1, activate, ledger_path, seeded, write_replay
from test_approved_rules_round1 import REVIEW2, SUCC, _a_to_b_with_b_retired, _supersede
from test_approved_rules_round2 import REVIEW3, _revived_pair_ledger

CALM = "rule c"


def _revive_a_by_activate(tmp_path: Path) -> tuple[str, str]:
    a, b = _a_to_b_with_b_retired(tmp_path)
    f = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id=REVIEW2)
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 0
    return a, b


def _expected_refusal(a: str, b: str) -> str:
    return (
        f"rule {b} cannot be active while rule {a}, which it superseded, is active; "
        "retire one of them first"
    )


def test_activating_former_successor_after_activate_revival_is_refused(tmp_path, capsys):
    a, b = _revive_a_by_activate(tmp_path)
    capsys.readouterr()
    before = ledger_path(tmp_path).read_bytes()
    f = write_replay(tmp_path / "aug.yaml", rules=[SUCC], review_id=REVIEW3)
    assert activate(tmp_path, f, effective="2026-08-01", review_after="2026-08-31") == 1
    assert _expected_refusal(a, b) in capsys.readouterr().err
    assert ledger_path(tmp_path).read_bytes() == before


def test_dry_run_of_a_refused_activation_fails_with_the_error(tmp_path, capsys):
    a, b = _revive_a_by_activate(tmp_path)
    capsys.readouterr()
    before = ledger_path(tmp_path).read_bytes()
    f = write_replay(tmp_path / "aug.yaml", rules=[SUCC], review_id=REVIEW3)
    rc = activate(tmp_path, f, effective="2026-08-01", review_after="2026-08-31", confirm=False)
    captured = capsys.readouterr()
    assert rc == 1
    assert _expected_refusal(a, b) in captured.err
    assert "Nothing was written" not in captured.err
    assert ledger_path(tmp_path).read_bytes() == before


@pytest.mark.parametrize("order", [[R1, CALM], [CALM, R1]])
def test_same_batch_pair_message_names_the_chain_end_not_only_the_next_hop(tmp_path, capsys, order):
    seeded(tmp_path, rules=[R1])
    a, b, c = ar.rule_id_for(R1), ar.rule_id_for("rule b"), ar.rule_id_for(CALM)
    assert _supersede(tmp_path, a, "rule b") == 0
    assert _supersede(tmp_path, b, CALM) == 0
    from test_approved_rules_round1 import _lifecycle

    assert _lifecycle(tmp_path, "retire", c) == 0
    capsys.readouterr()
    f = write_replay(tmp_path / "jul.yaml", rules=order, review_id=REVIEW2)
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 1
    err = capsys.readouterr().err
    assert f"rules {a} and {c} are both in this review, but {c} superseded {a}" in err


def test_load_time_violation_message_says_to_edit_the_file_and_names_both_rules():
    ledger = _revived_pair_ledger()
    revived, other = ledger["rules"][0]["rule_id"], ledger["rules"][1]["rule_id"]
    with pytest.raises(ar.LedgerError) as info:
        ar.validate_ledger(ledger)
    message = str(info.value)
    assert "violates the supersession invariant" in message
    assert "by hand" in message
    assert revived in message and other in message
    assert "retire one of them first" not in message
