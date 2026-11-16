"""Review round 2 regression tests for the approved-rule ledger (issue #514)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import approved_rules as ar
import manage_approved_rules as cli
import pytest
from test_approved_rules import (
    R1,
    REVIEW,
    activate,
    ledger_path,
    mk_rule,
    read_ledger,
    seeded,
    write_replay,
)
from test_approved_rules_round1 import (
    REVIEW2,
    SUCC,
    _a_to_b_with_b_retired,
    _lifecycle,
)

REVIEW3 = "monthly_2026-07_fictional"


def _rerun_seed(tmp_path: Path) -> None:
    assert activate(tmp_path, tmp_path / "seed.yaml") == 0


# ---------------------------------------------------------------------------
# r2-1 and the mismatch-note gaps (N17-N19)
# ---------------------------------------------------------------------------


def test_old_file_rerun_after_later_renewal_prints_no_mismatch_note(tmp_path, capsys):
    seeded(tmp_path, rules=[R1])
    jul = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id=REVIEW2)
    assert activate(tmp_path, jul, effective="2026-07-01", review_after="2026-07-31") == 0
    capsys.readouterr()
    _rerun_seed(tmp_path)
    out = capsys.readouterr().out
    assert "already_applied" in out and "differ" not in out


def test_old_file_rerun_after_later_reactivation_prints_no_mismatch_note(tmp_path, capsys):
    seeded(tmp_path, rules=[R1])
    assert _lifecycle(tmp_path, "retire", ar.rule_id_for(R1)) == 0
    jul = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id=REVIEW2)
    assert activate(tmp_path, jul, effective="2026-07-01", review_after="2026-07-31") == 0
    capsys.readouterr()
    _rerun_seed(tmp_path)
    assert "differ" not in capsys.readouterr().out


def test_later_extend_suppresses_the_mismatch_note(tmp_path, capsys):
    seeded(tmp_path, rules=[R1])
    rc = cli.main(
        [
            "extend",
            "--ledger",
            str(ledger_path(tmp_path)),
            "--rule-id",
            ar.rule_id_for(R1),
            "--review-after",
            "2026-09-30",
            "--reason",
            "r",
        ]
    )
    assert rc == 0
    capsys.readouterr()
    _rerun_seed(tmp_path)
    assert "differ" not in capsys.readouterr().out


def test_rerun_of_a_renewing_review_prints_no_mismatch_note(tmp_path, capsys):
    seeded(tmp_path, rules=[R1])
    jul = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id=REVIEW2)
    assert activate(tmp_path, jul, effective="2026-07-01", review_after="2026-07-31") == 0
    capsys.readouterr()
    # Different dates than stored, but the matched event is a renewal: no note.
    assert activate(tmp_path, jul, effective="2026-08-01", review_after="2026-08-31") == 0
    assert "differ" not in capsys.readouterr().out


def test_mismatch_note_still_names_each_differing_field(tmp_path, capsys):
    seeded(tmp_path, rules=[R1])
    capsys.readouterr()
    rc = activate(
        tmp_path,
        tmp_path / "seed.yaml",
        "--expires-on",
        "2026-12-31",
        effective="2026-06-02",
        review_after="2026-09-30",
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "effective_date: stored 2026-06-01, command 2026-06-02" in out
    assert "review_after: stored 2026-06-30, command 2026-09-30" in out
    assert "expires_on: stored None, command 2026-12-31" in out


def test_renewal_note_reports_expiry_set_and_changed(tmp_path, capsys):
    f = write_replay(tmp_path / "r.yaml", rules=[R1])
    assert activate(tmp_path, f) == 0
    capsys.readouterr()
    jul = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id=REVIEW2)
    args = {"effective": "2026-07-01", "review_after": "2026-07-31"}
    assert activate(tmp_path, jul, "--expires-on", "2026-12-31", **args) == 0
    assert "expires_on set to 2026-12-31 (was None)" in capsys.readouterr().out
    aug = write_replay(tmp_path / "aug.yaml", rules=[R1], review_id=REVIEW3)
    assert activate(tmp_path, aug, "--expires-on", "2027-01-31", **args) == 0
    assert "expires_on set to 2027-01-31 (was 2026-12-31)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# r2-2: same-batch supersession pair
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("order", [[R1, SUCC], [SUCC, R1]])
def test_same_batch_pair_gets_one_clear_message_in_either_order(tmp_path, capsys, order):
    a, b = _a_to_b_with_b_retired(tmp_path)
    capsys.readouterr()
    before = ledger_path(tmp_path).read_bytes()
    f = write_replay(tmp_path / "jul.yaml", rules=order, review_id=REVIEW2)
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 1
    err = capsys.readouterr().err
    assert f"rules {a} and {b} are both in this review, but {b} superseded {a}" in err
    assert "approve only one of them" in err
    assert ledger_path(tmp_path).read_bytes() == before


# ---------------------------------------------------------------------------
# r2-3: OSError is reported cleanly
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() == 0, reason="permissions are not enforced for root"
)
def test_unwritable_ledger_directory_reports_error_and_exits_1(tmp_path, capsys):
    seeded(tmp_path, rules=[R1])
    capsys.readouterr()
    directory = ledger_path(tmp_path).parent
    before = ledger_path(tmp_path).read_bytes()
    os.chmod(directory, 0o500)
    try:
        rc = _lifecycle(tmp_path, "retire", ar.rule_id_for(R1))
    finally:
        os.chmod(directory, 0o700)
    assert rc == 1
    assert capsys.readouterr().err.startswith("Error:")
    assert ledger_path(tmp_path).read_bytes() == before


# ---------------------------------------------------------------------------
# r2-4: the supersession invariant is part of validation
# ---------------------------------------------------------------------------


def _revived_pair_ledger() -> dict:
    a, b = ar.rule_id_for(R1), ar.rule_id_for(SUCC)
    revived = mk_rule(
        history=[
            {"at": "2026-05-31T21:00:00+00:00", "event": "activated"},
            {
                "at": "2026-06-10T21:00:00+00:00",
                "event": "restored",
                "former_successors": [b],
            },
        ]
    )
    other = mk_rule(rule_id=b, text=SUCC)
    assert revived["rule_id"] == a
    return {"schema_version": 1, "rules": [revived, other]}


def test_validate_ledger_rejects_revived_rule_beside_active_former_successor():
    with pytest.raises(ar.LedgerError, match="violates the supersession invariant"):
        ar.validate_ledger(_revived_pair_ledger())


def test_hand_edited_revived_pair_makes_cli_list_fail(tmp_path):
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(_revived_pair_ledger()), encoding="utf-8")
    assert cli.main(["list", "--ledger", str(path)]) == 1


def test_revived_rule_with_retired_former_successor_still_loads():
    ledger = _revived_pair_ledger()
    ledger["rules"][1]["status"] = "retired"
    ar.validate_ledger(ledger)


# ---------------------------------------------------------------------------
# N6: an older former_successors entry still counts after later events
# ---------------------------------------------------------------------------


def test_older_former_successors_entry_counts_after_later_events(tmp_path):
    a, b = _a_to_b_with_b_retired(tmp_path)
    assert _lifecycle(tmp_path, "restore", a) == 0
    rc = cli.main(
        [
            "extend",
            "--ledger",
            str(ledger_path(tmp_path)),
            "--rule-id",
            a,
            "--review-after",
            "2026-09-30",
            "--reason",
            "r",
        ]
    )
    assert rc == 0
    events = [e["event"] for e in read_ledger(tmp_path)["rules"][0]["history"]]
    assert events[-1] == "extended" and "restored" in events
    assert _lifecycle(tmp_path, "restore", b) == 1
    assert REVIEW and ar  # keep helpers referenced
