"""Exercise the approved-rule experiment through its command entry point."""

import json
from datetime import date, timedelta
from pathlib import Path

import approved_rules as ar
import pytest
import review_rule_experiment as experiment


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    start = date(2026, 6, 1)
    rule = {
        "rule_id": ar.rule_id_for("Skip a fictional breakout outside the written entry range"),
        "text": "Skip a fictional breakout outside the written entry range",
        "status": "active",
        "effective_date": start.isoformat(),
        "review_after": "2026-06-30",
        "expires_on": None,
        "origin": "coach_accepted",
        "superseded_by": None,
        "evidence_ids": [],
        "history": [{"event": "activated", "at": "2026-06-01T12:00:00+00:00"}],
    }
    path = tmp_path / "rules.json"
    ar.save_ledger(path, {"schema_version": 1, "rules": [rule]})
    monkeypatch.setattr(experiment, "today_et", lambda: start)
    return path, rule, start


def start_args(ledger, rule_id=None):
    path, rule, _ = ledger
    return [
        "--ledger",
        str(path),
        "start",
        "--rule-id",
        rule_id or rule["rule_id"],
        "--applicable-when",
        "A candidate is reviewed outside the written entry range.",
    ]


def write_json(path: Path, data):
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def plan(ledger, tmp_path, capsys, monkeypatch):
    assert experiment.main(start_args(ledger)) == 0
    monkeypatch.setattr(experiment, "today_et", lambda: date(2026, 6, 16))
    return write_json(tmp_path / "plan.json", json.loads(capsys.readouterr().out))


def observation(n, *, date="2026-06-02", decision="pass", assessment="followed", session="open"):
    return {
        "occasion_id": f"case-{n}",
        "date": date,
        "decision": decision,
        "assessment": assessment,
        "session": session,
        "evidence_ref": f"fictional-{n}",
    }


def review(ledger, plan, rows, capsys, *, as_of="2026-06-15"):
    observations = write_json(plan.with_name("observations.json"), rows)
    inputs = {p: p.read_bytes() for p in (ledger[0], plan, observations)}
    code = experiment.main(
        [
            "--ledger",
            str(ledger[0]),
            "review",
            "--plan",
            str(plan),
            "--observations",
            str(observations),
            "--as-of",
            as_of,
        ]
    )
    assert all(p.read_bytes() == data for p, data in inputs.items())
    return code, capsys.readouterr()


def test_counts_correct_passes_and_groups_exceptions(ledger, plan, capsys):
    code, output = review(
        ledger,
        plan,
        [
            observation(1, date="2026-06-01"),
            observation(2, date="2026-06-14", decision="enter", assessment="exception"),
            observation(3, decision="enter", assessment="not_applicable"),
        ],
        capsys,
    )
    assert code == 0
    report = json.loads(output.out)
    assert report["window_status"] == "ended"
    assert report["counts"] == {
        "recorded": 3,
        "applicable": 2,
        "followed": 1,
        "exceptions": 1,
        "not_applicable": 1,
        "unassessed": 0,
        "followed_passes": 1,
    }
    assert report["exceptions_by_session"] == {"open": 1}
    assert report["adherence_rate_pct"] is None
    assert report["rate_suppressed_reason"] == "small_sample"
    assert report["rule_review_after"] == "2026-06-30"
    assert "fictional-1" not in output.out


@pytest.mark.parametrize(
    ("as_of", "extra", "rate", "reason"),
    [
        ("2026-06-15", [], 90.0, None),
        ("2026-06-15", [observation(10, assessment="unassessed")], None, "unassessed_occasions"),
        ("2026-06-14", [], None, "window_open"),
    ],
)
def test_rate_requires_ended_window_and_assessed_sample(
    ledger, plan, capsys, as_of, extra, rate, reason
):
    rows = [observation(n) for n in range(9)]
    rows.append(observation(9, assessment="exception", decision="enter"))
    code, output = review(ledger, plan, rows + extra, capsys, as_of=as_of)
    assert code == 0
    report = json.loads(output.out)
    assert report["counts"]["applicable"] == 10
    assert report["counts"]["unassessed"] == len(extra)
    assert report["adherence_rate_pct"] == rate
    assert report["rate_suppressed_reason"] == reason


@pytest.mark.parametrize(
    "state", ["unknown", "retired", "superseded", "expired", "expires_during", "future"]
)
def test_start_requires_rule_to_cover_the_window(ledger, capsys, state):
    path, rule, start = ledger
    rules = [rule]
    if state == "retired":
        rule["status"] = "retired"
    elif state == "superseded":
        successor = {**rule, "text": "A different fictional rule"}
        successor["rule_id"] = ar.rule_id_for(successor["text"])
        rule.update(status="superseded", superseded_by=successor["rule_id"])
        rules.append(successor)
    elif state == "expired":
        rule.update(effective_date="2026-05-01", expires_on="2026-05-30")
    elif state == "expires_during":
        rule["expires_on"] = (start + timedelta(days=5)).isoformat()
    elif state == "future":
        rule["effective_date"] = (start + timedelta(days=1)).isoformat()
    ar.save_ledger(path, {"schema_version": 1, "rules": rules})
    initial = path.read_bytes()
    assert experiment.main(start_args(ledger, "deferred-rule" if state == "unknown" else None)) == 1
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err.startswith("Error:")
    assert path.read_bytes() == initial


@pytest.mark.parametrize(
    ("rows", "as_of", "message"),
    [
        ([observation(1), observation(1)], "2026-06-15", "duplicate occasion_id"),
        ([observation(1, date="2026-05-31")], "2026-06-15", "outside the experiment window"),
        ([observation(1, date="2026-06-15")], "2026-06-16", "outside the experiment window"),
        ([observation(1, date="2026-06-13")], "2026-06-12", "after the review date"),
        ([observation(1, assessment="maybe")], "2026-06-15", "invalid assessment"),
        ([{**observation(1), "outcome": "rally"}], "2026-06-15", "unexpected fields"),
    ],
)
def test_bad_observations_do_not_produce_a_partial_report(
    ledger, plan, capsys, rows, as_of, message
):
    code, output = review(ledger, plan, rows, capsys, as_of=as_of)
    assert code == 1
    assert output.out == ""
    assert message in output.err


def test_changed_rule_is_not_attributed_to_original_experiment(ledger, plan, capsys):
    path, rule, _ = ledger
    rule["review_after"] = "2026-07-31"
    ar.save_ledger(path, {"schema_version": 1, "rules": [rule]})
    code, output = review(ledger, plan, [observation(1)], capsys)
    assert code == 1
    assert output.out == ""
    assert "ledger rule changed since the experiment started" in output.err


def test_empty_log_is_zero_recorded_occasions(ledger, plan, capsys):
    code, output = review(ledger, plan, [], capsys)
    assert code == 0
    report = json.loads(output.out)
    assert report["counts"]["recorded"] == report["counts"]["applicable"] == 0
    assert report["adherence_rate_pct"] is None


def test_future_review_cannot_close_window(ledger, plan, capsys):
    code, output = review(ledger, plan, [], capsys, as_of="2026-06-17")
    assert code == 1
    assert output.out == ""
    assert "review date cannot be in the future" in output.err
