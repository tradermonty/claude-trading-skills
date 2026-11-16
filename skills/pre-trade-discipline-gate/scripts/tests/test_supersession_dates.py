"""Immediate supersession must never silently schedule a gap in rule enforcement."""

from __future__ import annotations

import copy
from datetime import date, datetime

import approved_rules as ar
import manage_approved_rules as cli
import pytest
from check_pre_trade_discipline import parse_as_of
from test_check_pre_trade_discipline import base_candidate
from test_gate_approved_rules import R1, R2, ack, make_ledger, rule, run_gate


def replace(ledger, now, effective_date="2026-12-01"):
    return ar.supersede_rule(
        ledger,
        rule_id=ar.rule_id_for(R1),
        text=R2,
        effective_date=effective_date,
        review_after="2027-01-31",
        expires_on=None,
        reason="Fictional monthly rule update",
        now=datetime.fromisoformat(now),
    )


def active_ledger():
    return {
        "schema_version": 1,
        "rules": [rule(R1, effective_date="2026-11-01", review_after="2027-01-31")],
    }


@pytest.mark.parametrize(
    "now,effective_date",
    [
        ("2026-11-14T17:00:00+00:00", "2026-12-01"),
        ("2026-12-01T04:59:59+00:00", "2026-12-01"),
        ("2026-07-01T03:59:59+00:00", "2026-07-01"),
        ("2026-12-01T00:00:00+09:00", "2026-12-01"),
    ],
)
def test_future_supersession_is_refused_without_mutating_ledger(now, effective_date):
    ledger = active_ledger()
    before = copy.deepcopy(ledger)
    with pytest.raises(ar.LedgerError, match="future.*America/New_York"):
        replace(ledger, now, effective_date)
    assert ledger == before


@pytest.mark.parametrize(
    "now,effective_date",
    [
        ("2026-12-01T05:00:00+00:00", "2026-12-01"),
        ("2026-07-01T04:00:00+00:00", "2026-07-01"),
        ("2026-12-02T05:00:00+00:00", "2026-12-01"),
    ],
)
def test_current_or_past_et_date_supersedes_immediately(now, effective_date):
    ledger, successor = replace(active_ledger(), now, effective_date)
    view = ar.build_view(ledger, date.fromisoformat(effective_date))
    assert [row["rule_id"] for row in view["applied"]] == [successor]
    assert view["not_applied"] == [{"rule_id": ar.rule_id_for(R1), "state": "superseded"}]


def test_naive_supersession_clock_is_refused():
    with pytest.raises(ar.LedgerError, match="timezone-aware"):
        replace(active_ledger(), "2026-12-01T17:00:00")


def test_cli_future_supersession_keeps_file_byte_identical(tmp_path, monkeypatch, capsys):
    ledger = make_ledger(tmp_path, *active_ledger()["rules"])
    before = ledger.read_bytes()
    monkeypatch.setattr(cli, "_now", lambda: datetime.fromisoformat("2026-11-14T17:00:00+00:00"))
    rc = cli.main(
        [
            "supersede",
            "--ledger",
            str(ledger),
            "--rule-id",
            ar.rule_id_for(R1),
            "--text",
            R2,
            "--effective-date",
            "2026-12-01",
            "--review-after",
            "2027-01-31",
            "--reason",
            "Fictional monthly rule update",
            "--confirm",
        ]
    )
    assert rc == 1
    assert "future" in capsys.readouterr().err
    assert ledger.read_bytes() == before


@pytest.mark.parametrize("as_of", ["2026-11-30", "2026-12-01", "2026-12-02"])
def test_refused_schedule_keeps_gate_acknowledgement_required(tmp_path, as_of):
    path = make_ledger(tmp_path, *active_ledger()["rules"])
    with pytest.raises(ar.LedgerError):
        replace(ar.load_ledger(path), "2026-11-14T17:00:00+00:00")
    result = run_gate(tmp_path, [base_candidate()], path, as_of=parse_as_of(as_of))
    assert result["overall_decision"] == "REVIEW_REQUIRED"
    assert [row["rule_id"] for row in result["approved_rules"]["applied"]] == [ar.rule_id_for(R1)]
    acknowledged = run_gate(
        tmp_path,
        [base_candidate(approved_rule_checks=[ack(R1)])],
        path,
        as_of=parse_as_of(as_of),
    )
    assert acknowledged["overall_decision"] == "GO"


@pytest.mark.parametrize("as_of", ["2026-12-01", "2026-12-02"])
def test_successful_replacement_requires_successor_acknowledgement(tmp_path, as_of):
    ledger, successor = replace(active_ledger(), "2026-12-01T05:00:00+00:00")
    path = make_ledger(tmp_path, *ledger["rules"])
    old_ack = run_gate(
        tmp_path,
        [base_candidate(approved_rule_checks=[ack(R1)])],
        path,
        as_of=parse_as_of(as_of),
    )
    assert old_ack["overall_decision"] == "REVIEW_REQUIRED"
    assert [row["rule_id"] for row in old_ack["approved_rules"]["applied"]] == [successor]
    new_ack = run_gate(
        tmp_path,
        [base_candidate(approved_rule_checks=[ack(R2)])],
        path,
        as_of=parse_as_of(as_of),
    )
    assert new_ack["overall_decision"] == "GO"


def test_past_as_of_uses_current_ledger_status_without_replaying_history():
    ledger, _ = replace(active_ledger(), "2026-12-01T05:00:00+00:00")
    view = ar.build_view(ledger, date(2026, 11, 30))
    assert view["applied"] == []
    assert view["not_applied"] == [
        {"rule_id": ar.rule_id_for(R1), "state": "superseded"},
        {"rule_id": ar.rule_id_for(R2), "state": "not_yet_effective"},
    ]
