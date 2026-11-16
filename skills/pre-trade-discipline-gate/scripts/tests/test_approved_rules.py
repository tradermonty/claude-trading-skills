"""Tests for approved_rules.py and manage_approved_rules.py (issue #514). Fictional data only."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import approved_rules as ar
import manage_approved_rules as cli
import pytest
import yaml

REVIEW = "monthly_2026-05_fictional"
NOW = datetime(2026, 5, 31, 21, 0, tzinfo=timezone.utc)
R1 = "require the confirmed pivot before any entry"
R2 = "move the stop loss only after the thesis is invalidated"
R3 = "keep portfolio heat at or below 4R"


def write_replay(
    path: Path,
    *,
    action: str = "modify_rules",
    rules: list[str] | None = None,
    review_id: str = REVIEW,
    trade_changes: list[str] | None = None,
    null_decision: bool = False,
    rule_activation: str = "not_performed",
) -> Path:
    if rules is None:
        rules = [R1, R2] if action in ("accept_rules", "modify_rules") else []
    decision = (
        None
        if null_decision
        else {
            "schema_version": 1,
            "source_review_id": review_id,
            "action": action,
            "accepted_rules": rules,
            "human_notes": "Fictional approval notes.",
        }
    )
    payload = {
        "schema_version": 1,
        "coach_rule_decision": decision,
        "rule_activation": rule_activation,
        "trade_rule_changes": trade_changes if trade_changes is not None else ["Trade change A."],
        "repo_improvements": [],
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def write_sample(
    path: Path,
    *,
    entries: list[dict] | None = None,
    month: str = "2026-06",
    review_after: str | None = "2026-06-30",
) -> Path:
    if entries is None:
        entries = [
            {
                "rule_id": "RULE-001",
                "rule": "Require the written confirmation condition before entry.",
                "source_rule_id": "COACH-RULE-001",
                "evidence_ids": ["TRADE-002", "PM-EXEC-001"],
                "status": "ACCEPTED",
            },
            {
                "rule_id": "RULE-002",
                "rule": "Journal the review before adding risk.",
                "source_rule_id": "COACH-RULE-002",
                "evidence_ids": ["BEHAVIOR-002"],
                "status": "ACCEPTED",
            },
            {
                "rule_id": "RULE-003",
                "rule": "A rule that was not accepted.",
                "source_rule_id": "COACH-RULE-003",
                "evidence_ids": [],
                "status": "DEFERRED",
            },
        ]
    payload: dict = {"schema_version": "1.0", "effective_month": month, "rules": entries}
    if review_after is not None:
        payload["review_after"] = review_after
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def activate(
    tmp_path: Path,
    rule_file: Path,
    *extra: str,
    effective: str = "2026-06-01",
    review_after: str | None = "2026-06-30",
    confirm: bool = True,
    ledger: Path | None = None,
) -> int:
    argv = [
        "activate",
        "--ledger",
        str(ledger or tmp_path / "rules" / "ledger.json"),
        "--rule-changes",
        str(rule_file),
        "--effective-date",
        effective,
    ]
    if review_after is not None:
        argv += ["--review-after", review_after]
    argv += list(extra)
    if confirm:
        argv.append("--confirm-activation")
    return cli.main(argv)


def ledger_path(tmp_path: Path) -> Path:
    return tmp_path / "rules" / "ledger.json"


def read_ledger(tmp_path: Path) -> dict:
    return json.loads(ledger_path(tmp_path).read_text(encoding="utf-8"))


def rule_by_text(ledger: dict, text: str) -> dict:
    rid = ar.rule_id_for(text)
    return next(r for r in ledger["rules"] if r["rule_id"] == rid)


def seeded(tmp_path: Path, rules: list[str] | None = None, **kw) -> Path:
    """Activate rules from a fictional replay file; return the ledger path."""
    f = write_replay(tmp_path / "seed.yaml", rules=rules or [R1, R2], **kw)
    assert activate(tmp_path, f) == 0
    return ledger_path(tmp_path)


def mk_rule(**overrides) -> dict:
    rule = {
        "rule_id": ar.rule_id_for(R1),
        "text": R1,
        "status": "active",
        "effective_date": "2026-06-01",
        "review_after": "2026-06-30",
        "expires_on": None,
        "origin": "coach_accepted",
        "superseded_by": None,
        "evidence_ids": [],
        "history": [{"at": NOW.isoformat(), "event": "activated"}],
    }
    rule.update(overrides)
    return rule


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_rule_id_is_stable_under_case_width_and_whitespace():
    assert ar.rule_id_for("Keep  heat\tbelow 4R") == ar.rule_id_for("keep heat below 4r ")
    assert ar.rule_id_for("ＡＢＣ rule") == ar.rule_id_for("abc rule")
    assert ar.rule_id_for(R1).startswith("rule_") and len(ar.rule_id_for(R1)) == 17


# ---------------------------------------------------------------------------
# activate: replay shape
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("action", "origin"), [("accept_rules", "coach_accepted"), ("modify_rules", "coach_modified")]
)
def test_replay_accept_and_modify_activate(tmp_path, action, origin):
    f = write_replay(tmp_path / "r.yaml", action=action)
    assert activate(tmp_path, f) == 0
    ledger = read_ledger(tmp_path)
    assert [r["text"] for r in ledger["rules"]] == [R1, R2]
    rule = ledger["rules"][0]
    assert rule["status"] == "active" and rule["origin"] == origin
    assert rule["effective_date"] == "2026-06-01" and rule["review_after"] == "2026-06-30"
    event = rule["history"][0]
    assert event["event"] == "activated" and event["source_review_id"] == REVIEW
    assert len(event["source_artifact_sha256"]) == 64
    assert event["human_notes"] == "Fictional approval notes."


@pytest.mark.parametrize("action", ["defer", "journal_only"])
def test_replay_defer_and_journal_only_contribute_nothing(tmp_path, capsys, action):
    f = write_replay(tmp_path / "r.yaml", action=action)
    assert activate(tmp_path, f) == 1
    assert "nothing to activate" in capsys.readouterr().err
    assert not ledger_path(tmp_path).exists()


def test_replay_null_decision_contributes_nothing(tmp_path, capsys):
    f = write_replay(tmp_path / "r.yaml", null_decision=True)
    assert activate(tmp_path, f, "--source-review-id", REVIEW) == 1
    assert "nothing to activate" in capsys.readouterr().err


def test_trade_rule_changes_with_null_decision_need_source_review_id(tmp_path, capsys):
    f = write_replay(tmp_path / "r.yaml", null_decision=True, trade_changes=["Trade change A."])
    assert activate(tmp_path, f, "--include-trade-rule-changes") == 1
    assert "--source-review-id is required" in capsys.readouterr().err
    assert activate(tmp_path, f, "--include-trade-rule-changes", "--source-review-id", REVIEW) == 0
    rule = read_ledger(tmp_path)["rules"][0]
    assert rule["origin"] == "trade_rule_change" and rule["text"] == "Trade change A."
    assert rule["history"][0]["human_notes"] is None


def test_trade_rule_changes_ignored_without_flag(tmp_path):
    f = write_replay(tmp_path / "r.yaml", action="accept_rules", rules=[R1])
    assert activate(tmp_path, f) == 0
    assert [r["text"] for r in read_ledger(tmp_path)["rules"]] == [R1]


def test_replay_rule_activation_other_than_not_performed_rejected(tmp_path, capsys):
    f = write_replay(tmp_path / "r.yaml", rule_activation="performed")
    assert activate(tmp_path, f) == 1
    assert "not_performed" in capsys.readouterr().err


def test_replay_review_after_is_required(tmp_path, capsys):
    f = write_replay(tmp_path / "r.yaml")
    assert activate(tmp_path, f, review_after=None) == 1
    assert "--review-after is required" in capsys.readouterr().err


def test_source_review_id_disagreeing_with_decision_rejected(tmp_path, capsys):
    f = write_replay(tmp_path / "r.yaml")
    assert activate(tmp_path, f, "--source-review-id", "monthly_other") == 1
    assert "disagrees" in capsys.readouterr().err
    assert not ledger_path(tmp_path).exists()


def test_matching_source_review_id_is_accepted(tmp_path):
    f = write_replay(tmp_path / "r.yaml")
    assert activate(tmp_path, f, "--source-review-id", REVIEW) == 0


def test_replay_validation_errors(tmp_path, capsys):
    f = write_replay(tmp_path / "a.yaml", action="modify_rules", rules=[R1, ""])
    assert activate(tmp_path, f) == 1
    f = write_replay(tmp_path / "b.yaml", action="accept_rules", rules=[])
    assert activate(tmp_path, f) == 1
    f = write_replay(tmp_path / "c.yaml", action="defer", rules=[R1])
    assert activate(tmp_path, f) == 1
    f = write_replay(tmp_path / "d.yaml", action="bogus", rules=[R1])
    assert activate(tmp_path, f) == 1
    f = write_replay(tmp_path / "e.yaml", action="modify_rules", rules=[R1, R1.upper()])
    assert activate(tmp_path, f) == 1
    err = capsys.readouterr().err
    assert "non-empty strings" in err and "non-empty accepted_rules" in err
    assert "defer/journal_only" in err and "action must be one of" in err and "unique" in err
    assert not ledger_path(tmp_path).exists()


# ---------------------------------------------------------------------------
# activate: sample shape
# ---------------------------------------------------------------------------


def test_sample_shape_only_accepted_rules_with_refs_and_default_review_after(tmp_path):
    f = write_sample(tmp_path / "s.yaml")
    assert activate(tmp_path, f, "--source-review-id", "sample_review", review_after=None) == 0
    ledger = read_ledger(tmp_path)
    assert len(ledger["rules"]) == 2
    rule = ledger["rules"][0]
    assert rule["origin"] == "sample_accepted" and rule["review_after"] == "2026-06-30"
    assert rule["evidence_ids"] == ["TRADE-002", "PM-EXEC-001"]
    event = rule["history"][0]
    assert event["source_rule_ref"] == "COACH-RULE-001"
    assert event["source_rule_local_id"] == "RULE-001"
    assert event["evidence_ids"] == ["TRADE-002", "PM-EXEC-001"]
    assert event["source_review_id"] == "sample_review"


def test_sample_effective_date_must_fall_in_effective_month(tmp_path, capsys):
    f = write_sample(tmp_path / "s.yaml")
    assert activate(tmp_path, f, "--source-review-id", "x", effective="2026-07-01") == 1
    assert "effective_month" in capsys.readouterr().err


def test_sample_requires_source_review_id(tmp_path, capsys):
    f = write_sample(tmp_path / "s.yaml")
    assert activate(tmp_path, f) == 1
    assert "--source-review-id is required" in capsys.readouterr().err


def test_sample_without_review_after_anywhere_rejected(tmp_path, capsys):
    f = write_sample(tmp_path / "s.yaml", review_after=None)
    assert activate(tmp_path, f, "--source-review-id", "x", review_after=None) == 1
    assert "--review-after is required" in capsys.readouterr().err


def test_sample_with_no_accepted_rules_is_nothing_to_activate(tmp_path, capsys):
    entries = [{"rule_id": "RULE-001", "rule": "x", "status": "DEFERRED"}]
    f = write_sample(tmp_path / "s.yaml", entries=entries)
    assert activate(tmp_path, f, "--source-review-id", "x") == 1
    assert "nothing to activate" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# activate: general input handling
# ---------------------------------------------------------------------------


def test_unknown_shape_rejected_naming_both_shapes(tmp_path, capsys):
    f = tmp_path / "x.yaml"
    f.write_text(yaml.safe_dump({"schema_version": 2, "rules": []}), encoding="utf-8")
    assert activate(tmp_path, f) == 1
    err = capsys.readouterr().err
    assert "replay shape" in err and "sample shape" in err


def test_non_mapping_file_rejected(tmp_path):
    f = tmp_path / "x.yaml"
    f.write_text("- just\n- a list\n", encoding="utf-8")
    assert activate(tmp_path, f) == 1


def test_duplicate_text_in_one_file_rejected(tmp_path, capsys):
    entries = [
        {"rule_id": "RULE-001", "rule": "Same Rule", "status": "ACCEPTED"},
        {"rule_id": "RULE-002", "rule": "same   rule", "status": "ACCEPTED"},
    ]
    f = write_sample(tmp_path / "s.yaml", entries=entries)
    assert activate(tmp_path, f, "--source-review-id", "x") == 1
    assert "duplicate rule text" in capsys.readouterr().err


def test_missing_confirm_writes_nothing(tmp_path, capsys):
    f = write_replay(tmp_path / "r.yaml")
    assert activate(tmp_path, f, confirm=False) == 1
    captured = capsys.readouterr()
    assert "--confirm-activation" in captured.err
    assert R1 in captured.out
    assert not ledger_path(tmp_path).exists()


def test_first_activate_creates_missing_directory(tmp_path):
    f = write_replay(tmp_path / "r.yaml")
    target = tmp_path / "a" / "b" / "ledger.json"
    assert activate(tmp_path, f, ledger=target) == 0
    assert target.exists()
    assert not list(target.parent.glob("*.tmp"))


def test_missing_pyyaml_exits_2_with_requirements_hint(tmp_path, monkeypatch, capsys):
    f = write_replay(tmp_path / "r.yaml")
    monkeypatch.setitem(sys.modules, "yaml", None)
    assert activate(tmp_path, f) == 2
    err = capsys.readouterr().err
    assert "PyYAML" in err and "pip install -r" in err and "requirements.txt" in err
    assert not ledger_path(tmp_path).exists()


# ---------------------------------------------------------------------------
# activate: renewal, idempotency, reactivation
# ---------------------------------------------------------------------------


def test_renewal_keeps_id_and_effective_date_and_moves_review_later(tmp_path):
    seeded(tmp_path)
    before = read_ledger(tmp_path)
    f = write_replay(tmp_path / "jul.yaml", review_id="monthly_2026-06_fictional")
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 0
    after = read_ledger(tmp_path)
    old, new = rule_by_text(before, R1), rule_by_text(after, R1)
    assert new["rule_id"] == old["rule_id"]
    assert new["effective_date"] == "2026-06-01"
    assert new["review_after"] == "2026-07-31"
    assert [e["event"] for e in new["history"]] == ["activated", "renewed"]
    assert new["history"][0] == old["history"][0]


def test_renewal_with_earlier_review_after_keeps_existing_and_says_so(tmp_path, capsys):
    seeded(tmp_path)
    capsys.readouterr()
    f = write_replay(tmp_path / "jul.yaml", review_id="monthly_2026-06_fictional")
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-06-10") == 0
    assert "review_after kept at 2026-06-30" in capsys.readouterr().out
    assert rule_by_text(read_ledger(tmp_path), R1)["review_after"] == "2026-06-30"


def test_rerun_same_file_is_noop(tmp_path):
    seeded(tmp_path)
    before = ledger_path(tmp_path).read_bytes()
    f = tmp_path / "seed.yaml"
    assert activate(tmp_path, f) == 0
    assert ledger_path(tmp_path).read_bytes() == before


def test_rerun_after_retire_leaves_retired_and_exits_1(tmp_path, capsys):
    seeded(tmp_path)
    for text in (R1, R2):
        assert (
            cli.main(
                [
                    "retire",
                    "--ledger",
                    str(ledger_path(tmp_path)),
                    "--rule-id",
                    ar.rule_id_for(text),
                    "--reason",
                    "stop applying",
                ]
            )
            == 0
        )
    capsys.readouterr()
    assert activate(tmp_path, tmp_path / "seed.yaml") == 1
    assert "restore" in capsys.readouterr().err
    assert rule_by_text(read_ledger(tmp_path), R1)["status"] == "retired"


def test_new_review_reactivates_retired_rule(tmp_path):
    seeded(tmp_path, rules=[R1])
    rid = ar.rule_id_for(R1)
    cli.main(["retire", "--ledger", str(ledger_path(tmp_path)), "--rule-id", rid, "--reason", "r"])
    f = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id="monthly_2026-06_fictional")
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 0
    rule = rule_by_text(read_ledger(tmp_path), R1)
    assert rule["status"] == "active"
    assert rule["effective_date"] == "2026-07-01" and rule["review_after"] == "2026-07-31"
    assert [e["event"] for e in rule["history"]] == ["activated", "retired", "reactivated"]


def test_edited_copy_of_same_review_does_not_resurrect_but_adds_new_rule(tmp_path):
    seeded(tmp_path, rules=[R1])
    cli.main(
        [
            "retire",
            "--ledger",
            str(ledger_path(tmp_path)),
            "--rule-id",
            ar.rule_id_for(R1),
            "--reason",
            "r",
        ]
    )
    edited = write_replay(tmp_path / "edited.yaml", rules=[R1, R3])
    assert activate(tmp_path, edited, effective="2026-07-01", review_after="2026-07-31") == 0
    ledger = read_ledger(tmp_path)
    assert rule_by_text(ledger, R1)["status"] == "retired"
    assert rule_by_text(ledger, R1)["effective_date"] == "2026-06-01"
    assert rule_by_text(ledger, R3)["status"] == "active"


def test_rerun_before_effective_date_exits_0(tmp_path):
    f = write_replay(tmp_path / "r.yaml")
    far = "2999-01-01"
    assert activate(tmp_path, f, effective=far, review_after="2999-01-31") == 0
    assert activate(tmp_path, f, effective=far, review_after="2999-01-31") == 0
    assert read_ledger(tmp_path)["rules"][0]["status"] == "active"


def test_renewal_after_extend_keeps_later_date(tmp_path):
    seeded(tmp_path, rules=[R1])
    rid = ar.rule_id_for(R1)
    assert (
        cli.main(
            [
                "extend",
                "--ledger",
                str(ledger_path(tmp_path)),
                "--rule-id",
                rid,
                "--review-after",
                "2026-09-30",
                "--reason",
                "longer cycle",
            ]
        )
        == 0
    )
    f = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id="monthly_2026-06_fictional")
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 0
    assert rule_by_text(read_ledger(tmp_path), R1)["review_after"] == "2026-09-30"


def test_renewal_clears_expiry_unless_given_and_reapplies_expired_rule(tmp_path):
    f = write_replay(tmp_path / "r.yaml", rules=[R1])
    assert activate(tmp_path, f, "--expires-on", "2026-06-20") == 0
    rule = rule_by_text(read_ledger(tmp_path), R1)
    assert ar.compute_state(rule, date(2026, 6, 21)) == "expired"
    jul = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id="monthly_2026-06_fictional")
    assert activate(tmp_path, jul, effective="2026-07-01", review_after="2026-07-31") == 0
    rule = rule_by_text(read_ledger(tmp_path), R1)
    assert rule["expires_on"] is None
    assert ar.compute_state(rule, date(2026, 7, 5)) == "effective"


def test_renewal_sets_expiry_when_given(tmp_path):
    seeded(tmp_path, rules=[R1])
    jul = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id="monthly_2026-06_fictional")
    assert (
        activate(
            tmp_path,
            jul,
            "--expires-on",
            "2026-07-15",
            effective="2026-07-01",
            review_after="2026-07-31",
        )
        == 0
    )
    assert rule_by_text(read_ledger(tmp_path), R1)["expires_on"] == "2026-07-15"


def test_history_keeps_sample_refs_and_evidence_is_unioned_on_renewal(tmp_path):
    f = write_sample(tmp_path / "s.yaml")
    assert activate(tmp_path, f, "--source-review-id", "sample_may") == 0
    again = write_sample(
        tmp_path / "s2.yaml",
        entries=[
            {
                "rule_id": "RULE-009",
                "rule": "Require the written confirmation condition before entry.",
                "source_rule_id": "COACH-RULE-009",
                "evidence_ids": ["PM-EXEC-001", "TRADE-099"],
                "status": "ACCEPTED",
            }
        ],
        month="2026-07",
        review_after="2026-07-31",
    )
    assert (
        activate(
            tmp_path,
            again,
            "--source-review-id",
            "sample_jun",
            effective="2026-07-01",
            review_after=None,
        )
        == 0
    )
    rule = rule_by_text(
        read_ledger(tmp_path), "Require the written confirmation condition before entry."
    )
    assert rule["evidence_ids"] == ["TRADE-002", "PM-EXEC-001", "TRADE-099"]
    renewed = rule["history"][1]
    assert renewed["event"] == "renewed"
    assert renewed["source_rule_ref"] == "COACH-RULE-009"
    assert renewed["source_rule_local_id"] == "RULE-009"
    assert rule["history"][0]["source_rule_local_id"] == "RULE-001"


# ---------------------------------------------------------------------------
# all-or-nothing, supersession chains
# ---------------------------------------------------------------------------


def _supersede(tmp_path, rid, text, **kw) -> int:
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
            kw.get("effective", "2026-06-15"),
            "--review-after",
            kw.get("review_after", "2026-07-15"),
            "--reason",
            "replace",
            "--confirm",
        ]
    )


def test_one_bad_candidate_leaves_ledger_byte_identical(tmp_path):
    seeded(tmp_path, rules=[R1])
    rid = ar.rule_id_for(R1)
    assert _supersede(tmp_path, rid, "successor rule text") == 0
    before = ledger_path(tmp_path).read_bytes()
    f = write_replay(
        tmp_path / "jul.yaml", rules=[R3, R1, R2], review_id="monthly_2026-06_fictional"
    )
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 1
    assert ledger_path(tmp_path).read_bytes() == before


def test_activate_superseded_rule_refused_while_successor_active_then_allowed(tmp_path, capsys):
    seeded(tmp_path, rules=[R1])
    rid = ar.rule_id_for(R1)
    succ = ar.rule_id_for("successor rule text")
    assert _supersede(tmp_path, rid, "successor rule text") == 0
    f = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id="monthly_2026-06_fictional")
    before = ledger_path(tmp_path).read_bytes()
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 1
    assert succ in capsys.readouterr().err
    assert ledger_path(tmp_path).read_bytes() == before
    cli.main(["retire", "--ledger", str(ledger_path(tmp_path)), "--rule-id", succ, "--reason", "r"])
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 0
    rule = rule_by_text(read_ledger(tmp_path), R1)
    assert rule["status"] == "active" and rule["superseded_by"] is None


def test_chain_end_blocks_restore_and_reactivation_of_earlier_links(tmp_path):
    seeded(tmp_path, rules=[R1])
    a, b, c = ar.rule_id_for(R1), ar.rule_id_for("rule b"), ar.rule_id_for("rule c")
    assert _supersede(tmp_path, a, "rule b") == 0
    assert _supersede(tmp_path, b, "rule c") == 0
    ledger = ar.load_ledger(ledger_path(tmp_path))
    for rid in (a, b):
        with pytest.raises(ar.LedgerError, match="successor"):
            ar.restore_rule(ledger, rule_id=rid, reason="r", now=NOW)
    f = write_replay(tmp_path / "jul.yaml", rules=[R1], review_id="monthly_2026-06_fictional")
    assert activate(tmp_path, f, effective="2026-07-01", review_after="2026-07-31") == 1
    cli.main(["retire", "--ledger", str(ledger_path(tmp_path)), "--rule-id", c, "--reason", "r"])
    restored = ar.restore_rule(
        ar.load_ledger(ledger_path(tmp_path)), rule_id=b, reason="r", now=NOW
    )
    assert next(r for r in restored["rules"] if r["rule_id"] == b)["status"] == "active"


# ---------------------------------------------------------------------------
# supersede / retire / extend / restore
# ---------------------------------------------------------------------------


def test_supersede_adds_manual_rule_and_marks_old(tmp_path):
    seeded(tmp_path, rules=[R1])
    rid = ar.rule_id_for(R1)
    assert _supersede(tmp_path, rid, "Only enter after the confirmed pivot closes.") == 0
    ledger = read_ledger(tmp_path)
    old = rule_by_text(ledger, R1)
    new = rule_by_text(ledger, "Only enter after the confirmed pivot closes.")
    assert old["status"] == "superseded" and old["superseded_by"] == new["rule_id"]
    assert new["origin"] == "manual_supersede" and new["status"] == "active"
    event = new["history"][0]
    assert event["superseded_id"] == rid and event["reason"] == "replace"
    assert event["source_review_id"] is None and event["source_artifact_sha256"] is None
    assert old["history"][-1]["event"] == "superseded"


def test_supersede_requires_confirm(tmp_path, capsys):
    seeded(tmp_path, rules=[R1])
    before = ledger_path(tmp_path).read_bytes()
    rc = cli.main(
        [
            "supersede",
            "--ledger",
            str(ledger_path(tmp_path)),
            "--rule-id",
            ar.rule_id_for(R1),
            "--text",
            "new text",
            "--effective-date",
            "2026-06-15",
            "--review-after",
            "2026-07-15",
            "--reason",
            "r",
        ]
    )
    assert rc == 1 and "--confirm" in capsys.readouterr().err
    assert ledger_path(tmp_path).read_bytes() == before


@pytest.mark.parametrize("existing_state", ["active", "retired", "superseded"])
def test_supersede_onto_existing_text_refused(tmp_path, existing_state, capsys):
    seeded(tmp_path, rules=[R1, R2])
    r1, r2 = ar.rule_id_for(R1), ar.rule_id_for(R2)
    if existing_state == "retired":
        cli.main(
            ["retire", "--ledger", str(ledger_path(tmp_path)), "--rule-id", r2, "--reason", "r"]
        )
    elif existing_state == "superseded":
        assert _supersede(tmp_path, r2, "some third rule") == 0
    before = ledger_path(tmp_path).read_bytes()
    assert _supersede(tmp_path, r1, R2) == 1
    assert "already exists" in capsys.readouterr().err
    assert ledger_path(tmp_path).read_bytes() == before


def test_supersede_with_same_text_as_old_refused(tmp_path):
    seeded(tmp_path, rules=[R1])
    assert _supersede(tmp_path, ar.rule_id_for(R1), R1.upper()) == 1


def test_supersede_non_active_refused(tmp_path):
    seeded(tmp_path, rules=[R1])
    rid = ar.rule_id_for(R1)
    cli.main(["retire", "--ledger", str(ledger_path(tmp_path)), "--rule-id", rid, "--reason", "r"])
    assert _supersede(tmp_path, rid, "something new") == 1


def test_retire_restore_roundtrip_and_refusals(tmp_path):
    seeded(tmp_path, rules=[R1])
    rid = ar.rule_id_for(R1)
    ledger = ar.load_ledger(ledger_path(tmp_path))
    with pytest.raises(ar.LedgerError, match="already active"):
        ar.restore_rule(ledger, rule_id=rid, reason="r", now=NOW)
    retired = ar.retire_rule(ledger, rule_id=rid, reason="done", now=NOW)
    with pytest.raises(ar.LedgerError, match="only an active"):
        ar.retire_rule(retired, rule_id=rid, reason="again", now=NOW)
    with pytest.raises(ar.LedgerError, match="not found"):
        ar.retire_rule(ledger, rule_id="rule_missing", reason="r", now=NOW)
    with pytest.raises(ar.LedgerError, match="reason"):
        ar.retire_rule(ledger, rule_id=rid, reason="  ", now=NOW)
    restored = ar.restore_rule(retired, rule_id=rid, reason="back", now=NOW)
    rule = restored["rules"][0]
    assert rule["status"] == "active"
    assert [e["event"] for e in rule["history"]] == ["activated", "retired", "restored"]


def test_restore_superseded_clears_pointer_after_successor_retired(tmp_path):
    seeded(tmp_path, rules=[R1])
    a = ar.rule_id_for(R1)
    b = ar.rule_id_for("successor text")
    assert _supersede(tmp_path, a, "successor text") == 0
    ledger = ar.load_ledger(ledger_path(tmp_path))
    with pytest.raises(ar.LedgerError, match=b):
        ar.restore_rule(ledger, rule_id=a, reason="r", now=NOW)
    ledger = ar.retire_rule(ledger, rule_id=b, reason="r", now=NOW)
    ledger = ar.restore_rule(ledger, rule_id=a, reason="r", now=NOW)
    restored = next(r for r in ledger["rules"] if r["rule_id"] == a)
    assert restored["status"] == "active" and restored["superseded_by"] is None


def test_extend_all_branches(tmp_path):
    seeded(tmp_path, rules=[R1])
    rid = ar.rule_id_for(R1)
    ledger = ar.load_ledger(ledger_path(tmp_path))

    def ext(led, **kw):
        base = dict(
            rule_id=rid, review_after=None, expires_on=None, clear_expiry=False, reason="r", now=NOW
        )
        base.update(kw)
        return ar.extend_rule(led, **base)

    with pytest.raises(ar.LedgerError, match="at least one"):
        ext(ledger)
    with pytest.raises(ar.LedgerError, match="later than"):
        ext(ledger, review_after="2026-06-30")
    with pytest.raises(ar.LedgerError, match="cannot be combined"):
        ext(ledger, expires_on="2026-08-01", clear_expiry=True)
    first = ext(ledger, expires_on="2026-07-10")  # null -> date
    assert first["rules"][0]["expires_on"] == "2026-07-10"
    second = ext(first, expires_on="2026-07-20")  # date -> later date
    assert second["rules"][0]["expires_on"] == "2026-07-20"
    with pytest.raises(ar.LedgerError, match="retire it"):
        ext(second, expires_on="2026-07-01")  # earlier date refused
    cleared = ext(second, clear_expiry=True)
    assert cleared["rules"][0]["expires_on"] is None
    both = ext(ledger, review_after="2026-08-31", expires_on="2026-09-30")
    assert both["rules"][0]["review_after"] == "2026-08-31"
    assert len(both["rules"][0]["history"]) == 2


def test_extend_works_on_expired_and_review_due_rules_only_when_active(tmp_path):
    f = write_replay(tmp_path / "r.yaml", rules=[R1])
    assert activate(tmp_path, f, "--expires-on", "2026-06-20") == 0
    rid = ar.rule_id_for(R1)
    ledger = ar.load_ledger(ledger_path(tmp_path))
    assert ar.compute_state(ledger["rules"][0], date(2026, 7, 5)) == "expired"
    extended = ar.extend_rule(
        ledger,
        rule_id=rid,
        review_after=None,
        expires_on=None,
        clear_expiry=True,
        reason="keep",
        now=NOW,
    )
    assert ar.compute_state(extended["rules"][0], date(2026, 7, 5)) == "review_due"
    retired = ar.retire_rule(extended, rule_id=rid, reason="r", now=NOW)
    with pytest.raises(ar.LedgerError, match="only an active"):
        ar.extend_rule(
            retired,
            rule_id=rid,
            review_after="2026-12-01",
            expires_on=None,
            clear_expiry=False,
            reason="r",
            now=NOW,
        )


def test_cli_extend_and_restore_and_history_only_grows(tmp_path):
    seeded(tmp_path, rules=[R1])
    led = str(ledger_path(tmp_path))
    rid = ar.rule_id_for(R1)
    counts = [len(read_ledger(tmp_path)["rules"][0]["history"])]
    steps = [
        [
            "extend",
            "--ledger",
            led,
            "--rule-id",
            rid,
            "--review-after",
            "2026-08-31",
            "--reason",
            "r",
        ],
        ["retire", "--ledger", led, "--rule-id", rid, "--reason", "r"],
        ["restore", "--ledger", led, "--rule-id", rid, "--reason", "r"],
        [
            "extend",
            "--ledger",
            led,
            "--rule-id",
            rid,
            "--expires-on",
            "2026-12-31",
            "--reason",
            "r",
        ],
        ["extend", "--ledger", led, "--rule-id", rid, "--clear-expiry", "--reason", "r"],
    ]
    for argv in steps:
        assert cli.main(argv) == 0
        counts.append(len(read_ledger(tmp_path)["rules"][0]["history"]))
    assert counts == sorted(counts) and counts[-1] == counts[0] + len(steps)


def test_cli_refusals_return_1(tmp_path):
    seeded(tmp_path, rules=[R1])
    led = str(ledger_path(tmp_path))
    rid = ar.rule_id_for(R1)
    assert cli.main(["restore", "--ledger", led, "--rule-id", rid, "--reason", "r"]) == 1
    assert cli.main(["retire", "--ledger", led, "--rule-id", "rule_nope", "--reason", "r"]) == 1
    assert cli.main(["extend", "--ledger", led, "--rule-id", rid, "--reason", "r"]) == 1


def test_cli_list_json_and_text(tmp_path, capsys):
    seeded(tmp_path)
    capsys.readouterr()
    led = str(ledger_path(tmp_path))
    assert cli.main(["list", "--ledger", led, "--as-of", "2026-06-15", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["as_of_date"] == "2026-06-15"
    assert {r["state"] for r in data["rules"]} == {"effective"}
    assert cli.main(["list", "--ledger", led, "--as-of", "2026-07-01"]) == 0
    assert "review_due" in capsys.readouterr().out
    assert cli.main(["list", "--ledger", str(tmp_path / "missing.json")]) == 1


# ---------------------------------------------------------------------------
# Computed state boundaries
# ---------------------------------------------------------------------------


def test_state_boundaries():
    rule = mk_rule(effective_date="2026-06-01", review_after="2026-06-30", expires_on="2026-07-10")
    state = lambda d: ar.compute_state(rule, date.fromisoformat(d))  # noqa: E731
    assert state("2026-05-31") == "not_yet_effective"
    assert state("2026-06-01") == "effective"
    assert state("2026-06-30") == "effective"
    assert state("2026-07-01") == "review_due"
    assert state("2026-07-10") == "review_due"
    assert state("2026-07-11") == "expired"


def test_expiry_before_review_after_is_expired_after_expiry():
    rule = mk_rule(review_after="2026-06-30", expires_on="2026-06-20")
    assert ar.compute_state(rule, date(2026, 6, 20)) == "effective"
    assert ar.compute_state(rule, date(2026, 6, 21)) == "expired"


def test_stored_status_wins_over_dates():
    assert ar.compute_state(mk_rule(status="retired"), date(2026, 6, 15)) == "retired"
    rule = mk_rule(status="superseded", superseded_by="rule_other")
    assert ar.compute_state(rule, date(2026, 6, 15)) == "superseded"


# ---------------------------------------------------------------------------
# Ledger validation
# ---------------------------------------------------------------------------


def ledger_of(*rules) -> dict:
    return {"schema_version": 1, "rules": list(rules)}


def test_valid_ledger_passes():
    ar.validate_ledger(ledger_of(mk_rule()))
    ar.validate_ledger(ar.empty_ledger())


@pytest.mark.parametrize(
    ("ledger", "message"),
    [
        (ledger_of(mk_rule(status="paused")), "unknown status"),
        (ledger_of(mk_rule(), mk_rule()), "duplicate rule_id"),
        (ledger_of(mk_rule(rule_id="rule_000000000000")), "does not match its text"),
        (ledger_of(mk_rule(status="superseded", superseded_by="rule_gone")), "does not exist"),
        (ledger_of(mk_rule(superseded_by=ar.rule_id_for(R1))), "if and only if"),
        (ledger_of(mk_rule(status="superseded")), "if and only if"),
        (ledger_of(mk_rule(review_after="2026-05-01")), "review_after is before"),
        (ledger_of(mk_rule(expires_on="2026-05-01")), "expires_on is before"),
        (ledger_of(mk_rule(origin="mystery")), "unknown origin"),
        (ledger_of(mk_rule(effective_date="06/01/2026")), "YYYY-MM-DD"),
        (ledger_of(mk_rule(history=[])), "history"),
        ({"schema_version": 2, "rules": []}, "schema_version"),
        ({"schema_version": 1}, "'rules' must be a list"),
        ([], "JSON object"),
    ],
)
def test_validation_rejects(ledger, message):
    with pytest.raises(ar.LedgerError, match=message):
        ar.validate_ledger(ledger)


def test_supersession_cycle_rejected():
    a, b = ar.rule_id_for(R1), ar.rule_id_for(R2)
    ledger = ledger_of(
        mk_rule(status="superseded", superseded_by=b),
        mk_rule(rule_id=b, text=R2, status="superseded", superseded_by=a),
    )
    with pytest.raises(ar.LedgerError, match="cycle"):
        ar.validate_ledger(ledger)


def test_truncated_json_is_an_error_not_an_empty_ledger(tmp_path, capsys):
    path = tmp_path / "ledger.json"
    path.write_text('{"schema_version": 1, "rules": [', encoding="utf-8")
    with pytest.raises(ar.LedgerError):
        ar.load_ledger(path, missing_ok=True)
    f = write_replay(tmp_path / "r.yaml")
    assert activate(tmp_path, f, ledger=path) == 1
    assert path.read_text(encoding="utf-8") == '{"schema_version": 1, "rules": ['


def test_save_refuses_invalid_ledger(tmp_path):
    path = tmp_path / "ledger.json"
    with pytest.raises(ar.LedgerError):
        ar.save_ledger(path, ledger_of(mk_rule(status="paused")))
    assert not path.exists()


def test_build_view_splits_applied_and_warns():
    ledger = ledger_of(
        mk_rule(),
        mk_rule(rule_id=ar.rule_id_for(R2), text=R2, expires_on="2026-06-10"),
        mk_rule(rule_id=ar.rule_id_for(R3), text=R3, status="retired"),
    )
    view = ar.build_view(ledger, date(2026, 7, 1))
    assert [r["state"] for r in view["applied"]] == ["review_due"]
    assert {r["state"] for r in view["not_applied"]} == {"expired", "retired"}
    assert len(view["warnings"]) == 2
