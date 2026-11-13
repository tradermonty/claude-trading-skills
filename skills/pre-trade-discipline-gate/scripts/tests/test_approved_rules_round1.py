"""Review round 1 regression tests for the approved-rule ledger (issue #514)."""

from __future__ import annotations

import copy
import json
import os
import stat
from pathlib import Path

import approved_rules as ar
import manage_approved_rules as cli
import pytest
import yaml
from test_approved_rules import (
    NOW,
    R1,
    activate,
    ledger_path,
    mk_rule,
    read_ledger,
    seeded,
    write_replay,
)

SUCC = "successor rule text"
REVIEW2 = "monthly_2026-06_fictional"


def _supersede(tmp_path: Path, rid: str, text: str) -> int:
    return cli.main(
        [
            "supersede",
            "--ledger",
            str(ledger_path(tmp_path)),
            "--rule-id",
            rid,
            "--text",
            text,
            "--effective-date",
            "2026-06-15",
            "--review-after",
            "2026-07-15",
            "--reason",
            "replace",
            "--confirm",
        ]
    )


def _lifecycle(tmp_path: Path, verb: str, rid: str) -> int:
    return cli.main(
        [verb, "--ledger", str(ledger_path(tmp_path)), "--rule-id", rid, "--reason", "r"]
    )


def _a_to_b_with_b_retired(tmp_path: Path) -> tuple[str, str]:
    seeded(tmp_path, rules=[R1])
    a, b = ar.rule_id_for(R1), ar.rule_id_for(SUCC)
    assert _supersede(tmp_path, a, SUCC) == 0
    assert _lifecycle(tmp_path, "retire", b) == 0
    return a, b


# ---------------------------------------------------------------------------
# M-1: order independence and the supersession invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("order", [[R1, SUCC], [SUCC, R1]])
def test_activate_batch_refused_in_either_order_when_it_would_revive_a_chain(tmp_path, order):
    _a_to_b_with_b_retired(tmp_path)
    before = ledger_path(tmp_path).read_bytes()
    f = write_replay(tmp_path / "jul.yaml", rules=order, review_id=REVIEW2)
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 1
    assert ledger_path(tmp_path).read_bytes() == before


def test_restore_of_former_successor_refused_while_revived_rule_is_active(tmp_path, capsys):
    a, b = _a_to_b_with_b_retired(tmp_path)
    assert _lifecycle(tmp_path, "restore", a) == 0  # allowed: B is retired
    capsys.readouterr()
    before = ledger_path(tmp_path).read_bytes()
    assert _lifecycle(tmp_path, "restore", b) == 1
    assert a in capsys.readouterr().err
    assert ledger_path(tmp_path).read_bytes() == before
    # Once A is retired again, B may come back.
    assert _lifecycle(tmp_path, "retire", a) == 0
    assert _lifecycle(tmp_path, "restore", b) == 0


def test_activate_of_former_successor_refused_while_revived_rule_is_active(tmp_path):
    a, b = _a_to_b_with_b_retired(tmp_path)
    assert _lifecycle(tmp_path, "restore", a) == 0
    before = ledger_path(tmp_path).read_bytes()
    f = write_replay(tmp_path / "jul.yaml", rules=[SUCC], review_id=REVIEW2)
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 1
    assert ledger_path(tmp_path).read_bytes() == before


def test_middle_link_of_a_chain_cannot_be_restored_beside_revived_rule(tmp_path):
    seeded(tmp_path, rules=[R1])
    a, b, c = ar.rule_id_for(R1), ar.rule_id_for("rule b"), ar.rule_id_for("rule c")
    assert _supersede(tmp_path, a, "rule b") == 0
    assert _supersede(tmp_path, b, "rule c") == 0
    assert _lifecycle(tmp_path, "retire", c) == 0
    assert _lifecycle(tmp_path, "restore", a) == 0
    assert _lifecycle(tmp_path, "restore", b) == 1
    assert _lifecycle(tmp_path, "restore", c) == 1


# ---------------------------------------------------------------------------
# M-2: renewal that clears an expiry says so
# ---------------------------------------------------------------------------


def test_renewal_reports_cleared_expiry(tmp_path, capsys):
    f = write_replay(tmp_path / "r.yaml", rules=[R1])
    assert activate(tmp_path, f, "--expires-on", "2026-12-31") == 0
    capsys.readouterr()
    jul = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id=REVIEW2)
    assert activate(tmp_path, jul, effective="2026-07-01", review_after="2026-07-31") == 0
    assert "expires_on cleared (was 2026-12-31)" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# m-1: dates are normalized or rejected cleanly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [" 2026-06-01", "2026-06-01 ", "2026-06-01\n", "2026-6-1"])
def test_padded_or_newline_dates_rejected_cleanly(tmp_path, bad):
    f = write_replay(tmp_path / "r.yaml", rules=[R1])
    assert activate(tmp_path, f, effective=bad) == 1
    assert activate(tmp_path, f, review_after=bad) == 1
    assert not ledger_path(tmp_path).exists()
    with pytest.raises(ar.LedgerError):
        ar.parse_date(bad, "date")


def test_extend_rejects_padded_date_and_leaves_ledger_untouched(tmp_path):
    seeded(tmp_path, rules=[R1])
    before = ledger_path(tmp_path).read_bytes()
    rc = cli.main(
        [
            "extend",
            "--ledger",
            str(ledger_path(tmp_path)),
            "--rule-id",
            ar.rule_id_for(R1),
            "--review-after",
            "2026-09-30 ",
            "--reason",
            "r",
        ]
    )
    assert rc == 1
    assert ledger_path(tmp_path).read_bytes() == before
    assert cli.main(["list", "--ledger", str(ledger_path(tmp_path))]) == 0


def test_stored_dates_are_canonical_strings_even_from_yaml_dates(tmp_path):
    f = tmp_path / "s.yaml"
    f.write_text(
        "schema_version: '1.0'\neffective_month: '2026-06'\nreview_after: 2026-06-30\n"
        "rules:\n  - {rule_id: RULE-001, rule: Rule one, status: ACCEPTED}\n",
        encoding="utf-8",
    )
    assert activate(tmp_path, f, "--source-review-id", "x", review_after=None) == 0
    rule = read_ledger(tmp_path)["rules"][0]
    assert rule["review_after"] == "2026-06-30" and isinstance(rule["review_after"], str)


# ---------------------------------------------------------------------------
# m-2: hand-edited ledgers fail validation cleanly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "superseded", "superseded_by": []},
        {"status": "superseded", "superseded_by": 5},
        {"superseded_by": {"a": 1}},
        {"status": ["active"]},
        {"origin": ["coach_accepted"]},
        {"effective_date": 20260601},
        {"review_after": None},
        {"expires_on": 5},
        {"expires_on": "2026-06-01\n"},
        {"text": 5},
        {"rule_id": ["x"]},
        {"evidence_ids": "TRADE-1"},
        {"history": "activated"},
        {"history": [None]},
    ],
)
def test_wrong_field_types_give_validation_error_not_traceback(tmp_path, overrides):
    ledger = {"schema_version": 1, "rules": [mk_rule(**overrides)]}
    with pytest.raises(ar.LedgerError):
        ar.validate_ledger(ledger)
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(ledger), encoding="utf-8")
    assert cli.main(["list", "--ledger", str(path)]) == 1


# ---------------------------------------------------------------------------
# m-3 / m-4: output warnings
# ---------------------------------------------------------------------------


def test_already_applied_with_different_dates_warns_and_points_to_extend(tmp_path, capsys):
    seeded(tmp_path, rules=[R1])
    capsys.readouterr()
    f = tmp_path / "seed.yaml"
    assert activate(tmp_path, f, review_after="2026-09-30") == 0
    out = capsys.readouterr().out
    assert "already_applied" in out and "review_after" in out and "extend" in out
    assert "differ" in out


def test_already_applied_with_same_dates_does_not_warn(tmp_path, capsys):
    seeded(tmp_path, rules=[R1])
    capsys.readouterr()
    assert activate(tmp_path, tmp_path / "seed.yaml") == 0
    assert "differ" not in capsys.readouterr().out


def test_sample_rows_with_other_status_are_listed_as_skipped(tmp_path, capsys):
    f = tmp_path / "s.yaml"
    payload = {
        "schema_version": "1.0",
        "effective_month": "2026-06",
        "review_after": "2026-06-30",
        "rules": [
            {"rule_id": "RULE-001", "rule": "Good rule", "status": "ACCEPTED"},
            {"rule_id": "RULE-002", "rule": "Typo status rule", "status": "accepted"},
            {"rule_id": "RULE-003", "rule": "Deferred rule", "status": "DEFERRED"},
        ],
    }
    f.write_text(yaml.safe_dump(payload), encoding="utf-8")
    assert activate(tmp_path, f, "--source-review-id", "x", review_after=None) == 0
    out = capsys.readouterr().out
    assert "skipped: status 'accepted'" in out and "Typo status rule" in out
    assert "skipped: status 'DEFERRED'" in out
    assert len(read_ledger(tmp_path)["rules"]) == 1


# ---------------------------------------------------------------------------
# m-7: permissions and symlinks
# ---------------------------------------------------------------------------


def test_save_preserves_existing_file_mode(tmp_path):
    seeded(tmp_path, rules=[R1])
    path = ledger_path(tmp_path)
    os.chmod(path, 0o640)
    assert _lifecycle(tmp_path, "retire", ar.rule_id_for(R1)) == 0
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_save_writes_through_symlink(tmp_path):
    seeded(tmp_path, rules=[R1])
    real = tmp_path / "elsewhere.json"
    real.write_bytes(ledger_path(tmp_path).read_bytes())
    link = tmp_path / "link.json"
    link.symlink_to(real)
    rc = cli.main(
        ["retire", "--ledger", str(link), "--rule-id", ar.rule_id_for(R1), "--reason", "r"]
    )
    assert rc == 0
    assert link.is_symlink()
    assert json.loads(real.read_text())["rules"][0]["status"] == "retired"


# ---------------------------------------------------------------------------
# Surviving mutations: no input mutation, atomic write
# ---------------------------------------------------------------------------


def test_apply_activation_does_not_mutate_input_when_a_later_candidate_raises(tmp_path):
    seeded(tmp_path, rules=[R1])
    a = ar.rule_id_for(R1)
    assert _supersede(tmp_path, a, SUCC) == 0
    ledger = ar.load_ledger(ledger_path(tmp_path))
    snapshot = copy.deepcopy(ledger)
    activation = ar.ActivationInput(
        "replay",
        [ar.Candidate("brand new rule", "coach_accepted"), ar.Candidate(R1, "coach_accepted")],
        REVIEW2,
        "2026-07-31",
        None,
    )
    with pytest.raises(ar.LedgerError):
        ar.apply_activation(
            ledger,
            activation,
            effective_date="2026-07-01",
            review_after="2026-07-31",
            expires_on=None,
            source_sha256="0" * 64,
            now=NOW,
        )
    assert ledger == snapshot


def test_failed_write_keeps_original_and_leaves_no_temp_file(tmp_path, monkeypatch):
    seeded(tmp_path, rules=[R1])
    path = ledger_path(tmp_path)
    before = path.read_bytes()
    ledger = ar.load_ledger(path)
    ledger["rules"][0]["review_after"] = "2026-12-31"

    def boom(*_args, **_kwargs):
        raise OSError("simulated failure")

    monkeypatch.setattr(ar.os, "replace", boom)
    with pytest.raises(OSError):
        ar.save_ledger(path, ledger)
    assert path.read_bytes() == before
    assert not list(path.parent.glob("*.tmp"))
    assert sorted(p.name for p in path.parent.iterdir()) == ["ledger.json"]
