"""Tests for review_rule_adherence.py (issue #514): monthly approved-rule adherence report.

Fictional data only. Journal rows are either produced by the real gate CLI (chain tests) or
built with ``make_row`` in the exact shape the gate writes, so edge cases such as reruns,
unavailable ledgers and malformed rows can be set up precisely.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import approved_rules as ar
import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = ROOT / "skills" / "pre-trade-discipline-gate" / "scripts"
GATE = SCRIPTS / "check_pre_trade_discipline.py"
MANAGE = SCRIPTS / "manage_approved_rules.py"
REPORT = SCRIPTS / "review_rule_adherence.py"
REPLAY_FULL = (
    ROOT
    / "examples"
    / "workflows"
    / "monthly-performance-review"
    / "replay-run-full-path"
    / "06_rule_changes_for_next_month.yaml"
)

RULE_A = "Wait for the confirmed pivot close before any entry."
RULE_B = "Cap planned risk at half a percent of the account per idea."
RULE_C = "Skip new entries during the first ten minutes of the session."
RULE_D = "Wait for the confirmed pivot close and a volume check before any entry."
MONTH = "2026-06"
AS_OF = "2026-07-05"
ID_A = ar.rule_id_for(RULE_A)
ID_B = ar.rule_id_for(RULE_B)
ID_C = ar.rule_id_for(RULE_C)


@pytest.fixture
def rra():
    return importlib.import_module("review_rule_adherence")


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


class Env:
    """Temporary journal directory and ledger path."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.journal = root / "journal"
        self.ledger = root / "state" / "approved_rules.json"
        self.out = root / "out"


@pytest.fixture
def env(tmp_path):
    e = Env(tmp_path)
    e.journal.mkdir()
    return e


def rule_dict(text, *, effective="2026-06-01", review_after="2026-06-30", expires=None, **extra):
    history = [{"at": "2026-06-01T09:00:00-04:00", "event": "activated"}]
    history.extend(extra.pop("history", []))
    rule = {
        "rule_id": ar.rule_id_for(text),
        "text": text,
        "status": extra.pop("status", "active"),
        "effective_date": effective,
        "review_after": review_after,
        "expires_on": expires,
        "origin": "coach_accepted",
        "superseded_by": None,
        "evidence_ids": [],
        "history": history,
    }
    rule.update(extra)
    return rule


def write_ledger(path: Path, *rules: dict) -> None:
    ar.save_ledger(path, {"schema_version": 1, "rules": list(rules)})


def applied_entry(text: str, state: str = "effective") -> dict:
    return {
        "rule_id": ar.rule_id_for(text),
        "text": text,
        "state": state,
        "effective_date": "2026-06-01",
        "review_after": "2026-06-30",
        "expires_on": None,
        "origin": "coach_accepted",
    }


def check(rule_id: str, status: str, note: str = "") -> dict:
    return {"rule_id": rule_id, "status": status, "note": note}


def cand(symbol="TEST", *, thesis_id=None, intent="ENTRY_READY", actionable=True, checks=None):
    row = {
        "symbol": symbol,
        "thesis_id": thesis_id,
        "order_intent": intent,
        "actionable": actionable,
        "decision": "GO",
        "reasons": [],
        "checklist_answers": {},
        "link_status": "not_requested",
    }
    if checks is not None:
        row["approved_rule_checks"] = checks
    return row


def make_row(
    day: str,
    candidates: list,
    applied: list | None = None,
    *,
    status: str = "loaded",
    generated_at: str | None = None,
    ledger: str | None = None,
    no_block: bool = False,
) -> dict:
    """A journal row in the shape the gate writes (as_of is end of the ET day, EDT in June)."""
    row = {
        "schema_version": "1.0",
        "generated_at": generated_at or f"{day}T21:00:00+00:00",
        "as_of": f"{day}T23:59:59.999999-04:00",
        "overall_decision": "GO",
        "candidate_results": candidates,
        "inputs": {},
        "warnings": [],
    }
    if no_block:
        return row
    row["inputs"]["approved_rules_ledger"] = ledger or "state/rules/approved_rules.json"
    if status == "loaded":
        row["approved_rules"] = {
            "status": "loaded",
            "as_of_date": day,
            "applied": applied or [],
            "not_applied": [],
        }
    else:
        row["approved_rules"] = {"status": "unavailable", "error": "ledger could not be read"}
    return row


def write_journal(env: Env, rows: list, name: str = "pre_trade_discipline_2026-06-30.jsonl"):
    """Write rows (dicts or raw strings) as JSONL lines into one journal file."""
    lines = [r if isinstance(r, str) else json.dumps(r) for r in rows]
    (env.journal / name).write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(rra, capsys, env, *extra, month=MONTH, as_of=AS_OF, stdout=True, ledger=True):
    argv = ["--journal-dir", str(env.journal), "--month", month, "--as-of", as_of]
    if ledger:
        argv += ["--ledger", str(env.ledger)]
    argv += list(extra)
    if stdout:
        argv.append("--stdout")
    capsys.readouterr()
    rc = rra.main(argv)
    cap = capsys.readouterr()
    data = json.loads(cap.out) if rc == 0 and stdout else None
    return rc, data, cap


def rules_by_id(data: dict) -> dict:
    return {r["rule_id"]: r for r in data["rules"]}


def one_rule_env(env, rows, *, rules=None):
    write_ledger(env.ledger, *(rules or [rule_dict(RULE_A)]))
    write_journal(env, rows)


def counts(rule: dict) -> tuple:
    return (rule["followed"], rule["exception"], rule["not_applicable"], rule["unacknowledged"])


# ---------------------------------------------------------------------------
# 1-2. Chain with the real gate and the rate threshold
# ---------------------------------------------------------------------------


def _cli(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *argv], capture_output=True, text=True)


def today_et_iso() -> str:
    """Real gate rows are generated now, so a review of them must be dated today or later."""
    return datetime.now(ZoneInfo("America/New_York")).date().isoformat()


def run_gate(env: Env, as_of: str, checks: list, symbol: str = "TEST") -> None:
    market = env.root / "exposure.json"
    circuit = env.root / "circuit.json"
    market.write_text(json.dumps({"recommendation": "NEW_ENTRY_ALLOWED"}), encoding="utf-8")
    circuit.write_text(json.dumps({"recommendation": "TRADING_ALLOWED"}), encoding="utf-8")
    candidate = {
        "symbol": symbol,
        "order_intent": "ENTRY_READY",
        "entry_in_written_plan": True,
        "stop_predefined": True,
        "size_within_plan": True,
        "planned_risk_dollars": 500,
        "actual_risk_dollars": 500,
        "approved_rule_checks": checks,
    }
    answers = env.root / f"answers_{as_of}.json"
    answers.write_text(json.dumps({"candidates": [candidate]}), encoding="utf-8")
    proc = _cli(
        str(GATE),
        "--answers-file",
        str(answers),
        "--approved-rules-ledger",
        str(env.ledger),
        "--market-regime-decision",
        str(market),
        "--circuit-breaker-decision",
        str(circuit),
        "--output-dir",
        str(env.root / f"gate_out_{as_of}"),
        "--journal-dir",
        str(env.journal),
        "--as-of",
        as_of,
        "--json-only",
    )
    assert proc.returncode == 0, proc.stderr


def test_chain_activate_gate_report_lists_every_activated_rule(env, rra, capsys):
    proc = _cli(
        str(MANAGE),
        "activate",
        "--ledger",
        str(env.ledger),
        "--rule-changes",
        str(REPLAY_FULL),
        "--effective-date",
        "2026-06-01",
        "--review-after",
        "2026-06-30",
        "--confirm-activation",
    )
    assert proc.returncode == 0, proc.stderr
    rule_ids = [r["rule_id"] for r in json.loads(env.ledger.read_text(encoding="utf-8"))["rules"]]
    assert len(rule_ids) == 3

    run_gate(env, "2026-06-03", [check(r, "followed") for r in rule_ids])
    run_gate(
        env,
        "2026-06-04",
        [check(rule_ids[0], "exception", "fictional gap entry")]
        + [check(r, "followed") for r in rule_ids[1:]],
    )
    run_gate(env, "2026-06-05", [check(r, "not_applicable") for r in rule_ids])

    rc, data, cap = run(rra, capsys, env, as_of=today_et_iso())
    assert rc == 0, cap.err
    by_id = rules_by_id(data)
    assert set(by_id) == set(rule_ids)
    assert counts(by_id[rule_ids[0]]) == (1, 1, 1, 0)
    for other in rule_ids[1:]:
        assert counts(by_id[other]) == (2, 0, 1, 0)
    assert all(r["occasions"] == 3 for r in data["rules"])
    assert all(r["acknowledged_followed_pct"] is None for r in data["rules"])
    assert all(r["rate_suppressed_reason"] == "small_sample" for r in data["rules"])
    assert "exceptions_present" in by_id[rule_ids[0]]["reconsider_reasons"]
    assert data["window"]["status"] == "ended"
    assert not any(w.startswith("different_ledger_path") for w in data["warnings"])


@pytest.mark.parametrize(
    ("followed", "expected_rate", "expected_reason"),
    [(8, None, "small_sample"), (9, 90.0, None)],
)
def test_rate_needs_ten_applicable_occasions(
    env, rra, capsys, followed, expected_rate, expected_reason
):
    rows = [
        make_row(
            f"2026-06-{day:02d}",
            [cand(checks=[check(ID_A, "followed")])],
            [applied_entry(RULE_A)],
        )
        for day in range(1, followed + 1)
    ]
    rows.append(
        make_row(
            "2026-06-20",
            [cand(checks=[check(ID_A, "exception", "fictional reason")])],
            [applied_entry(RULE_A)],
        )
    )
    one_rule_env(env, rows)
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    rule = rules_by_id(data)[ID_A]
    assert rule["followed"] + rule["exception"] == followed + 1
    assert rule["acknowledged_followed_pct"] == expected_rate
    assert rule["rate_suppressed_reason"] == expected_reason


# ---------------------------------------------------------------------------
# 3. Rerun dedupe
# ---------------------------------------------------------------------------


def _dedupe_env(env, earlier_rows, later_rows):
    write_ledger(env.ledger, rule_dict(RULE_A))
    write_journal(env, earlier_rows + later_rows)


def test_later_loaded_rerun_replaces_the_earlier_occasion(env, rra, capsys):
    early = make_row(
        "2026-06-10",
        [cand(checks=[check(ID_A, "followed")])],
        [applied_entry(RULE_A)],
        generated_at="2026-06-10T14:00:00+00:00",
    )
    late = make_row(
        "2026-06-10",
        [cand(checks=[check(ID_A, "exception", "fictional reason")])],
        [applied_entry(RULE_A)],
        generated_at="2026-06-10T15:00:00+00:00",
    )
    _dedupe_env(env, [late], [early])  # file order must not decide: generated_at does
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert counts(rules_by_id(data)[ID_A]) == (0, 1, 0, 0)
    assert data["input_quality"]["superseded_reruns"] == 1


def test_thesis_key_collapses_different_intents_on_the_same_day(env, rra, capsys):
    early = make_row(
        "2026-06-10",
        [cand(thesis_id="th_fict_1", intent="ENTRY_READY", checks=[check(ID_A, "followed")])],
        [applied_entry(RULE_A)],
        generated_at="2026-06-10T14:00:00+00:00",
    )
    late = make_row(
        "2026-06-10",
        [cand(thesis_id="th_fict_1", intent="MANUAL_ORDER", checks=[check(ID_A, "followed")])],
        [applied_entry(RULE_A)],
        generated_at="2026-06-10T15:00:00+00:00",
    )
    _dedupe_env(env, [early], [late])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert rules_by_id(data)[ID_A]["occasions"] == 1
    assert rules_by_id(data)[ID_A]["distinct_candidates"] == 1


@pytest.mark.parametrize(
    ("late_kwargs", "quality_key"),
    [
        ({"status": "unavailable"}, "ledger_unavailable_runs"),
        ({"no_block": True}, "runs_without_ledger"),
    ],
    ids=["unavailable", "no-ledger"],
)
def test_later_row_without_a_loaded_ledger_suppresses_the_earlier_occasion(
    env, rra, capsys, late_kwargs, quality_key
):
    early = make_row(
        "2026-06-10",
        [cand(checks=[check(ID_A, "followed")])],
        [applied_entry(RULE_A)],
        generated_at="2026-06-10T14:00:00+00:00",
    )
    late = make_row(
        "2026-06-10",
        [cand()],
        generated_at="2026-06-10T15:00:00+00:00",
        **late_kwargs,
    )
    _dedupe_env(env, [early], [late])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    rule = rules_by_id(data)[ID_A]
    assert counts(rule) == (0, 0, 0, 0)
    assert "no_applicable_occasions" in rule["reconsider_reasons"]
    assert data["input_quality"]["superseded_reruns"] == 1
    assert data["input_quality"][quality_key] == 1


def test_later_non_actionable_rerun_suppresses_the_earlier_occasion(env, rra, capsys):
    early = make_row(
        "2026-06-10",
        [cand(thesis_id="th_fict_2", checks=[check(ID_A, "followed")])],
        [applied_entry(RULE_A)],
        generated_at="2026-06-10T14:00:00+00:00",
    )
    late = make_row(
        "2026-06-10",
        [cand(thesis_id="th_fict_2", intent="WATCHLIST", actionable=False)],
        [applied_entry(RULE_A)],
        generated_at="2026-06-10T15:00:00+00:00",
    )
    _dedupe_env(env, [early], [late])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert rules_by_id(data)[ID_A]["occasions"] == 0


def test_two_unthesised_candidates_with_one_key_in_the_winning_row_are_both_kept(env, rra, capsys):
    early = make_row(
        "2026-06-10",
        [cand(checks=[check(ID_A, "followed")])],
        [applied_entry(RULE_A)],
        generated_at="2026-06-10T14:00:00+00:00",
    )
    late = make_row(
        "2026-06-10",
        [cand(checks=[check(ID_A, "followed")]), cand(checks=[check(ID_A, "not_applicable")])],
        [applied_entry(RULE_A)],
        generated_at="2026-06-10T15:00:00+00:00",
    )
    _dedupe_env(env, [early], [late])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    rule = rules_by_id(data)[ID_A]
    assert counts(rule) == (1, 0, 1, 0)
    assert rule["occasions"] == 2
    assert rule["distinct_candidates"] == 1


def test_tie_on_generated_at_goes_to_the_later_scan_position(env, rra, capsys):
    stamp = "2026-06-10T15:00:00+00:00"
    first = make_row(
        "2026-06-10",
        [cand(checks=[check(ID_A, "followed")])],
        [applied_entry(RULE_A)],
        generated_at=stamp,
    )
    second = make_row(
        "2026-06-10",
        [cand(checks=[check(ID_A, "exception", "fictional reason")])],
        [applied_entry(RULE_A)],
        generated_at=stamp,
    )
    write_ledger(env.ledger, rule_dict(RULE_A))
    write_journal(env, [first], "pre_trade_discipline_2026-06-10.jsonl")
    write_journal(env, [second], "pre_trade_discipline_2026-06-11.jsonl")
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert counts(rules_by_id(data)[ID_A]) == (0, 1, 0, 0)


# ---------------------------------------------------------------------------
# 4. Window, boundaries, partial application
# ---------------------------------------------------------------------------


def test_new_york_month_window_uses_the_row_date_not_the_journal_file_date(env, rra, capsys):
    write_ledger(env.ledger, rule_dict(RULE_A))
    # Both rows land in today's UTC-named journal file, whatever their as_of dates.
    run_gate(env, "2026-06-30", [check(ID_A, "followed")])
    run_gate(env, "2026-07-01", [check(ID_A, "followed")])
    rc, data, cap = run(rra, capsys, env, as_of=today_et_iso())
    assert rc == 0, cap.err
    assert rules_by_id(data)[ID_A]["occasions"] == 1
    assert data["input_quality"]["rows_outside_window"] == 1


def test_fallback_row_date_converts_as_of_to_new_york(env, rra, capsys):
    # 01:00 UTC on 2026-07-01 is still 2026-06-30 in New York.
    row = make_row("2026-06-30", [cand()], no_block=True)
    row["as_of"] = "2026-07-01T01:00:00+00:00"
    one_rule_env(env, [row])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert data["input_quality"]["runs_without_ledger"] == 1
    rc, data, _ = run(rra, capsys, env, month="2026-07")
    assert rc == 0
    assert data["input_quality"]["runs_without_ledger"] == 0


@pytest.mark.parametrize(
    ("as_of", "status", "reason"),
    [("2026-06-30", "open", "window_open"), ("2026-07-01", "ended", None)],
)
def test_window_status_boundary(env, rra, capsys, as_of, status, reason):
    rows = [
        make_row(
            f"2026-06-{day:02d}",
            [cand(checks=[check(ID_A, "followed")])],
            [applied_entry(RULE_A)],
        )
        for day in range(1, 12)
    ]
    one_rule_env(env, rows)
    rc, data, _ = run(rra, capsys, env, as_of=as_of)
    assert rc == 0
    assert data["window"] == {"start": "2026-06-01", "end": "2026-06-30", "status": status}
    rule = rules_by_id(data)[ID_A]
    assert rule["rate_suppressed_reason"] == reason
    assert (rule["acknowledged_followed_pct"] is None) == (reason is not None)


def test_month_that_starts_after_as_of_is_refused(env, rra, capsys):
    one_rule_env(env, [])
    rc, _, cap = run(rra, capsys, env, month="2026-07", as_of="2026-06-30")
    assert rc == 1
    assert "month" in cap.err.lower()


def test_partial_application_and_noise_are_handled(env, rra, capsys):
    ghost = "rule_ffffffffffff"
    rows = [
        make_row(
            "2026-06-10",
            [
                cand(checks=[check(ID_A, "followed"), check(ghost, "followed")]),
                cand(
                    "SKIP", intent="WATCHLIST", actionable=False, checks=[check(ID_A, "followed")]
                ),
            ],
            [applied_entry(RULE_A)],
        ),
        make_row(
            "2026-06-11",
            [cand(checks=[check(ID_A, "followed")])],
            [applied_entry(RULE_A, "review_due")],
        ),
        make_row(
            "2026-06-12",
            [cand(checks=[check(ID_A, "followed"), check(ID_B, "not_applicable")])],
            [applied_entry(RULE_A), applied_entry(RULE_B)],
        ),
    ]
    write_ledger(env.ledger, rule_dict(RULE_A), rule_dict(RULE_B, effective="2026-06-12"))
    write_journal(env, rows)
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    by_id = rules_by_id(data)
    assert set(by_id) == {ID_A, ID_B}
    assert counts(by_id[ID_A]) == (3, 0, 0, 0)
    assert by_id[ID_A]["days_in_applied"] == 3
    assert counts(by_id[ID_B]) == (0, 0, 1, 0)
    assert by_id[ID_B]["days_in_applied"] == 1


def test_missing_timezone_data_exits_2(env, rra, capsys, monkeypatch):
    def broken():
        raise ZoneInfoNotFoundError("America/New_York")

    monkeypatch.setattr(rra, "get_et_zone", broken)
    one_rule_env(env, [])
    rc, _, cap = run(rra, capsys, env)
    assert rc == 2
    assert "tzdata" in cap.err


def test_rows_after_the_review_date_are_excluded_and_counted(env, rra, capsys):
    kept = make_row("2026-06-10", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)])
    rerun_after = make_row(
        "2026-06-10",
        [cand(checks=[check(ID_A, "exception", "fictional reason")])],
        [applied_entry(RULE_A)],
        generated_at="2026-07-06T15:00:00+00:00",
    )
    future_day = make_row("2026-07-10", [cand()], [applied_entry(RULE_A)])
    one_rule_env(env, [kept, rerun_after, future_day])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert counts(rules_by_id(data)[ID_A]) == (1, 0, 0, 0)
    assert data["input_quality"]["rows_after_as_of"] == 2


# ---------------------------------------------------------------------------
# 5-6. Ledger quality and acknowledgement quality
# ---------------------------------------------------------------------------


def test_unavailable_and_unflagged_rows_only_affect_input_quality(env, rra, capsys):
    rows = [
        make_row("2026-06-10", [cand()], status="unavailable"),
        make_row("2026-06-11", [cand()], no_block=True),
    ]
    one_rule_env(env, rows)
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert data["input_quality"]["ledger_unavailable_runs"] == 1
    assert data["input_quality"]["runs_without_ledger"] == 1
    assert rules_by_id(data)[ID_A]["occasions"] == 0


def test_different_ledger_paths_are_counted_and_warned(env, rra, capsys):
    rows = [
        make_row("2026-06-10", [cand()], [applied_entry(RULE_A)], ledger=str(env.ledger)),
        make_row("2026-06-11", [cand()], [applied_entry(RULE_A)], ledger="other/ledger.json"),
    ]
    one_rule_env(env, rows)
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert data["input_quality"]["ledger_paths"] == {str(env.ledger): 1, "other/ledger.json": 1}
    assert any(w.startswith("different_ledger_path") for w in data["warnings"])


def test_unacknowledged_occasions_suppress_the_rate_and_flag_the_rule(env, rra, capsys):
    rows = [
        make_row("2026-06-01", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)]),
        make_row(
            "2026-06-02",
            [cand(checks=[check(ID_A, "exception", "")])],  # noteless exception
            [applied_entry(RULE_A)],
        ),
        make_row("2026-06-03", [cand(checks=[])], [applied_entry(RULE_A)]),  # malformed -> []
        make_row("2026-06-04", [cand()], [applied_entry(RULE_A)]),  # no checks at all
        make_row(
            "2026-06-05",
            [cand(checks=[check(ID_A, "maybe")])],  # unknown status
            [applied_entry(RULE_A)],
        ),
    ]
    one_rule_env(env, rows)
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    rule = rules_by_id(data)[ID_A]
    assert counts(rule) == (1, 0, 0, 4)
    assert rule["acknowledged_followed_pct"] is None
    assert rule["rate_suppressed_reason"] == "unacknowledged_occasions"
    assert "unacknowledged_occasions" in rule["reconsider_reasons"]


# ---------------------------------------------------------------------------
# 7-8. Ledger state at review and never-seen rules
# ---------------------------------------------------------------------------


def test_states_at_review_and_reconsider_reasons(env, rra, capsys):
    now = datetime(2026, 6, 15, 16, 0, tzinfo=timezone.utc)
    ledger = {
        "schema_version": 1,
        "rules": [
            rule_dict(RULE_A),
            rule_dict(RULE_B),
            rule_dict(RULE_C, expires="2026-06-20"),
        ],
    }
    ledger, successor = ar.supersede_rule(
        ledger,
        rule_id=ID_A,
        text=RULE_D,
        effective_date="2026-06-15",
        review_after="2026-08-31",
        expires_on=None,
        reason="sharper wording",
        now=now,
    )
    ledger = ar.retire_rule(ledger, rule_id=ID_B, reason="not useful", now=now)
    ar.save_ledger(env.ledger, ledger)
    all_applied = [applied_entry(r) for r in (RULE_A, RULE_B, RULE_C)]
    rows = [
        make_row(
            "2026-06-10",
            [cand(checks=[check(r, "followed") for r in (ID_A, ID_B, ID_C)])],
            all_applied,
        ),
        make_row(
            "2026-06-16",
            [cand(checks=[check(successor, "followed")])],
            [applied_entry(RULE_D)],
        ),
    ]
    write_journal(env, rows)
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    by_id = rules_by_id(data)
    assert by_id[ID_A]["ledger_state_at_review"] == "superseded"
    assert by_id[ID_A]["superseded_by"] == successor
    assert by_id[ID_B]["ledger_state_at_review"] == "retired"
    assert by_id[ID_C]["ledger_state_at_review"] == "expired"
    assert by_id[ID_C]["expires_on"] == "2026-06-20"
    assert by_id[successor]["ledger_state_at_review"] == "effective"
    for stale in (ID_A, ID_B, ID_C):
        assert "not_applied_at_review" in by_id[stale]["reconsider_reasons"]
    assert "not_applied_at_review" not in by_id[successor]["reconsider_reasons"]
    assert [r["rule_id"] for r in data["rules"]] == sorted(by_id)


def test_review_due_rule_is_reported_for_reconsideration(env, rra, capsys):
    rows = [
        make_row("2026-06-10", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)])
    ]
    one_rule_env(env, rows)  # review_after 2026-06-30 < as_of 2026-07-05
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    rule = rules_by_id(data)[ID_A]
    assert rule["ledger_state_at_review"] == "review_due"
    assert rule["review_after"] == "2026-06-30"
    assert rule["reconsider_reasons"][0] == "review_due"


def test_never_seen_rules_listed_only_when_their_interval_overlaps_the_window(env, rra, capsys):
    seen = rule_dict(RULE_A)
    expired_at_window_end = rule_dict(RULE_B, effective="2026-06-02", expires="2026-06-30")
    after_window = rule_dict(
        "Review the watchlist before the open.",
        effective="2026-07-01",
        review_after="2026-07-31",
    )
    before_window = rule_dict(
        "Avoid earnings week entries.",
        effective="2026-04-01",
        review_after="2026-04-30",
        expires="2026-05-31",
    )
    retired_before = rule_dict(
        "Trim a third at the first target.",
        effective="2026-03-01",
        status="retired",
        history=[{"at": "2026-05-15T10:00:00-04:00", "event": "retired"}],
    )
    retired_inside = rule_dict(
        "Do not average down.",
        effective="2026-03-01",
        status="retired",
        history=[{"at": "2026-06-20T10:00:00-04:00", "event": "retired"}],
    )
    write_ledger(
        env.ledger,
        seen,
        expired_at_window_end,
        after_window,
        before_window,
        retired_before,
        retired_inside,
    )
    write_journal(
        env,
        [make_row("2026-06-10", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)])],
    )
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    by_id = rules_by_id(data)
    listed = {ID_A, ID_B, ar.rule_id_for("Do not average down.")}
    assert set(by_id) == listed
    never_seen = by_id[ID_B]
    assert counts(never_seen) == (0, 0, 0, 0)
    assert never_seen["occasions"] == 0 and never_seen["days_in_applied"] == 0
    assert never_seen["ledger_state_at_review"] == "expired"
    assert "not_applied_at_review" in never_seen["reconsider_reasons"]
    assert "no_applicable_occasions" in never_seen["reconsider_reasons"]
    retired = by_id[ar.rule_id_for("Do not average down.")]
    assert retired["ledger_state_at_review"] == "retired"


def test_ledger_state_missing_from_ledger_for_unknown_row_rule(env, rra, capsys):
    rows = [
        make_row("2026-06-10", [cand(checks=[check(ID_C, "followed")])], [applied_entry(RULE_C)])
    ]
    one_rule_env(env, rows)  # the ledger only holds RULE_A
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    rule = rules_by_id(data)[ID_C]
    assert rule["ledger_state_at_review"] == "missing_from_ledger"
    assert "not_applied_at_review" in rule["reconsider_reasons"]
    assert rule["text"] == RULE_C


# ---------------------------------------------------------------------------
# 10-11. Input hygiene, outputs, privacy
# ---------------------------------------------------------------------------


def test_malformed_rows_are_counted_with_locations(env, rra, capsys):
    good = make_row("2026-06-10", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)])
    no_generated = make_row("2026-06-11", [cand()], [applied_entry(RULE_A)])
    del no_generated["generated_at"]
    bad_actionable = make_row("2026-06-12", [cand()], [applied_entry(RULE_A)])
    bad_actionable["candidate_results"][0]["actionable"] = "yes"
    bad_applied = make_row("2026-06-13", [cand()], [applied_entry(RULE_A)])
    bad_applied["approved_rules"]["applied"] = ["not-an-object"]
    no_candidates = make_row("2026-06-14", [cand()], [applied_entry(RULE_A)])
    del no_candidates["candidate_results"]
    rows = [
        good,
        "{not json",
        json.dumps([1, 2]),
        no_generated,
        bad_actionable,
        bad_applied,
        no_candidates,
    ]
    one_rule_env(env, rows)
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    malformed = data["input_quality"]["malformed_rows"]
    assert malformed["count"] == 6
    assert malformed["locations"][0] == "pre_trade_discipline_2026-06-30.jsonl:2"
    assert counts(rules_by_id(data)[ID_A]) == (1, 0, 0, 0)


def test_empty_window_exits_zero_with_a_warning(env, rra, capsys):
    one_rule_env(env, [])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert data["warnings"]
    assert data["input_quality"]["malformed_rows"]["count"] == 0


def test_stdout_writes_no_files_and_default_writes_json_and_markdown(env, rra, capsys):
    rows = [
        make_row("2026-06-10", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)])
    ]
    one_rule_env(env, rows)
    rc, data, _ = run(rra, capsys, env, "--output-dir", str(env.out))
    assert rc == 0 and data["schema_version"] == 1
    assert not env.out.exists()

    rc, _, _ = run(rra, capsys, env, "--output-dir", str(env.out), stdout=False)
    assert rc == 0
    report_json = env.out / "rule_adherence_2026-06_as-of_2026-07-05.json"
    report_md = env.out / "rule_adherence_2026-06_as-of_2026-07-05.md"
    assert json.loads(report_json.read_text(encoding="utf-8"))["month"] == MONTH
    assert ID_A in report_md.read_text(encoding="utf-8")


def test_report_envelope_fields(env, rra, capsys):
    one_rule_env(env, [])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert data["source"] == "pre_trade_gate_acknowledgements"
    assert data["month"] == MONTH and data["as_of"] == AS_OF
    assert set(data["inputs"]) == {"journal_dir", "ledger"}
    assert "not proof of behavior" in data["human_decision_note"]
    assert "manage_approved_rules.py" in data["human_decision_note"]


def test_report_never_copies_notes_symbols_or_thesis_ids(env, rra, capsys):
    note_text = "FICTIONALNOTETEXT"
    rows = [
        make_row(
            "2026-06-10",
            [
                cand(
                    "ZZZQ",
                    thesis_id="th_zzzq_1",
                    checks=[check(ID_A, "exception", note_text)],
                )
            ],
            [applied_entry(RULE_A)],
        )
    ]
    one_rule_env(env, rows)
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    rc, _, _ = run(rra, capsys, env, "--output-dir", str(env.out), stdout=False)
    assert rc == 0
    blobs = [json.dumps(data)] + [p.read_text(encoding="utf-8") for p in env.out.iterdir()]
    for blob in blobs:
        for forbidden in (note_text, "ZZZQ", "th_zzzq_1"):
            assert forbidden not in blob


# ---------------------------------------------------------------------------
# 12. CLI errors and a real subprocess run
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("month", ["2026-13", "June", "2026-6", ""])
def test_bad_month_exits_1(env, rra, capsys, month):
    one_rule_env(env, [])
    rc, _, cap = run(rra, capsys, env, month=month)
    assert rc == 1
    assert "month" in cap.err.lower()


def test_future_as_of_exits_1(env, rra, capsys):
    one_rule_env(env, [])
    tomorrow = datetime.now(ZoneInfo("America/New_York")).date() + timedelta(days=1)
    rc, _, cap = run(rra, capsys, env, month=tomorrow.strftime("%Y-%m"), as_of=tomorrow.isoformat())
    assert rc == 1
    assert "future" in cap.err.lower()


def test_missing_journal_dir_exits_1(env, rra, capsys):
    write_ledger(env.ledger, rule_dict(RULE_A))
    env.journal.rmdir()
    rc, _, cap = run(rra, capsys, env)
    assert rc == 1
    assert "journal" in cap.err.lower()


@pytest.mark.parametrize("content", [None, "{not json", '{"schema_version": 1, "rules": 5}'])
def test_unreadable_or_invalid_ledger_exits_1(env, rra, capsys, content):
    write_journal(env, [])
    if content is not None:
        env.ledger.parent.mkdir(parents=True, exist_ok=True)
        env.ledger.write_text(content, encoding="utf-8")
    rc, _, cap = run(rra, capsys, env)
    assert rc == 1
    assert "manage_approved_rules.py list" in cap.err


def test_script_runs_as_a_command(env):
    write_ledger(env.ledger, rule_dict(RULE_A))
    write_journal(
        env,
        [make_row("2026-06-10", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)])],
    )
    proc = _cli(
        str(REPORT),
        "--journal-dir",
        str(env.journal),
        "--ledger",
        str(env.ledger),
        "--month",
        MONTH,
        "--as-of",
        AS_OF,
        "--stdout",
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["rules"][0]["rule_id"] == ID_A
    assert date.fromisoformat(json.loads(proc.stdout)["as_of"]) == date(2026, 7, 5)


# ---------------------------------------------------------------------------
# Code review round 1 regressions
# ---------------------------------------------------------------------------


def test_out_of_range_dates_and_deep_nesting_are_malformed_not_fatal(env, rra, capsys):
    good = make_row("2026-06-10", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)])
    year_one = make_row("2026-06-11", [cand()], no_block=True)
    year_one["as_of"] = "0001-01-01T00:00:00+00:00"
    deep = "[" * 100000 + "]" * 100000
    one_rule_env(env, [good, year_one, deep])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert data["input_quality"]["malformed_rows"]["count"] == 2
    assert counts(rules_by_id(data)[ID_A]) == (1, 0, 0, 0)


def test_row_dated_after_as_of_is_excluded_even_when_generated_earlier(env, rra, capsys):
    forward = make_row(
        "2026-06-20",
        [cand(checks=[check(ID_A, "followed")])],
        [applied_entry(RULE_A)],
        generated_at="2026-06-10T15:00:00+00:00",
    )
    one_rule_env(env, [forward])
    rc, data, _ = run(rra, capsys, env, as_of="2026-06-15")
    assert rc == 0
    assert data["input_quality"]["rows_after_as_of"] == 1
    assert counts(rules_by_id(data)[ID_A]) == (0, 0, 0, 0)


def test_never_seen_rule_expiring_on_the_first_day_of_the_window_is_listed(env, rra, capsys):
    expiring = rule_dict(
        RULE_B, effective="2026-05-01", review_after="2026-05-31", expires="2026-06-01"
    )
    write_ledger(env.ledger, rule_dict(RULE_A), expiring)
    write_journal(env, [make_row("2026-06-10", [cand()], [applied_entry(RULE_A)])])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert ID_B in rules_by_id(data)


def test_unwritable_output_dir_exits_1_with_a_message(env, rra, capsys):
    one_rule_env(env, [make_row("2026-06-10", [cand()], [applied_entry(RULE_A)])])
    blocker = env.journal.parent / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    rc, _, cap = run(rra, capsys, env, "--output-dir", str(blocker / "out"), stdout=False)
    assert rc == 1
    assert "Error: cannot write the report" in cap.err
    assert "Traceback" not in cap.err


def test_duplicate_applied_rule_in_one_row_is_counted_once(env, rra, capsys):
    row = make_row(
        "2026-06-10",
        [cand(checks=[check(ID_A, "followed")])],
        [applied_entry(RULE_A), applied_entry(RULE_A)],
    )
    one_rule_env(env, [row])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert counts(rules_by_id(data)[ID_A]) == (1, 0, 0, 0)


# ---------------------------------------------------------------------------
# Code review round 2 regressions
# ---------------------------------------------------------------------------


def _markdown(rra, capsys, env, *extra):
    rc, _, _ = run(rra, capsys, env, "--output-dir", str(env.out), *extra, stdout=False)
    assert rc == 0
    [md_path] = sorted(env.out.glob("*.md"))
    return md_path.read_text(encoding="utf-8")


def test_markdown_flattens_and_escapes_rule_text(env, rra, capsys):
    hostile = "Never chase | no exceptions\n# Heading injected\n<script>x</script>"
    hid = ar.rule_id_for(hostile)
    write_ledger(env.ledger, rule_dict(hostile))
    write_journal(
        env,
        [make_row("2026-06-10", [cand(checks=[check(hid, "followed")])], [applied_entry(hostile)])],
    )
    md = _markdown(rra, capsys, env)
    assert "\n# Heading injected" not in md
    assert "<script>" not in md
    assert "Never chase \\| no exceptions # Heading injected &lt;script&gt;x&lt;/script&gt;" in md


def test_markdown_shows_unavailable_text_details_and_locations(env, rra, capsys):
    entry = applied_entry(RULE_C)
    del entry["text"]
    rows = [
        make_row("2026-06-10", [cand(checks=[check(ID_C, "exception", "x")])], [entry]),
        "{not json",
    ]
    one_rule_env(env, rows)
    md = _markdown(rra, capsys, env)
    assert f"{ID_C}: (text unavailable)" in md
    assert ": None" not in md
    assert "pre_trade_discipline_2026-06-30.jsonl:2" in md
    assert "review_after" in md and "days_in_applied" in md


def test_markdown_shows_a_zero_rate(env, rra, capsys):
    rows = [
        make_row(
            f"2026-06-{day:02d}",
            [cand(checks=[check(ID_A, "exception", "fictional reason")])],
            [applied_entry(RULE_A)],
        )
        for day in range(1, 11)
    ]
    one_rule_env(env, rows)
    md = _markdown(rra, capsys, env)
    assert "| 0.0 |" in md


def test_empty_ledger_reports_no_rules(env, rra, capsys):
    write_ledger(env.ledger)
    write_journal(env, [])
    rc, data, _ = run(rra, capsys, env)
    assert rc == 0
    assert data["rules"] == []
    assert any(w.startswith("no_rules_in_window") for w in data["warnings"])
    md = _markdown(rra, capsys, env)
    assert "No approved rules in the window." in md
    assert "| Rule |" not in md and "|---|" not in md
    assert "## Input quality" in md and "## Warnings" in md


def test_report_file_name_carries_the_review_date(env, rra, capsys):
    one_rule_env(env, [make_row("2026-06-10", [cand()], [applied_entry(RULE_A)])])
    run(rra, capsys, env, "--output-dir", str(env.out), stdout=False, as_of="2026-06-15")
    run(rra, capsys, env, "--output-dir", str(env.out), stdout=False, as_of="2026-07-05")
    names = sorted(p.name for p in env.out.glob("*.json"))
    assert names == [
        "rule_adherence_2026-06_as-of_2026-06-15.json",
        "rule_adherence_2026-06_as-of_2026-07-05.json",
    ]


def test_whitespace_only_exception_note_is_unacknowledged(env, rra, capsys):
    rows = [
        make_row(
            "2026-06-10", [cand(checks=[check(ID_A, "exception", "   ")])], [applied_entry(RULE_A)]
        )
    ]
    one_rule_env(env, rows)
    rc, data, _ = run(rra, capsys, env)
    assert counts(rules_by_id(data)[ID_A]) == (0, 0, 0, 1)


def test_rate_is_rounded_to_one_decimal(env, rra, capsys):
    rows = [
        make_row(
            f"2026-06-{day:02d}", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)]
        )
        for day in range(1, 11)
    ] + [
        make_row(
            f"2026-06-{day:02d}",
            [cand(checks=[check(ID_A, "exception", "fictional reason")])],
            [applied_entry(RULE_A)],
        )
        for day in range(11, 14)
    ]
    one_rule_env(env, rows)
    rc, data, _ = run(rra, capsys, env)
    assert rules_by_id(data)[ID_A]["acknowledged_followed_pct"] == 76.9


def test_rule_text_comes_from_the_latest_row(env, rra, capsys):
    old = applied_entry(RULE_A)
    old["text"] = "An older wording of the rule."
    rows = [
        make_row("2026-06-10", [cand()], [applied_entry(RULE_A)]),
        make_row("2026-06-05", [cand()], [old]),
    ]
    one_rule_env(env, rows)
    rc, data, _ = run(rra, capsys, env)
    assert rules_by_id(data)[ID_A]["text"] == RULE_A


def test_never_seen_boundaries_on_effective_and_end_event_days(env, rra, capsys):
    starts_last_day = rule_dict(RULE_B, effective="2026-06-30", review_after="2026-07-31")
    retired_first_day = rule_dict(
        RULE_C,
        effective="2026-03-01",
        status="retired",
        history=[{"at": "2026-06-01T10:00:00-04:00", "event": "retired"}],
    )
    write_ledger(env.ledger, rule_dict(RULE_A), starts_last_day, retired_first_day)
    write_journal(env, [make_row("2026-06-10", [cand()], [applied_entry(RULE_A)])])
    rc, data, _ = run(rra, capsys, env)
    assert {ID_B, ID_C} <= set(rules_by_id(data))


def test_undecodable_line_only_drops_that_line(env, rra, capsys):
    one_rule_env(env, [])
    good = make_row("2026-06-10", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)])
    path = env.journal / "pre_trade_discipline_2026-06-30.jsonl"
    path.write_bytes(json.dumps(good).encode("utf-8") + b"\n\xff\xfe broken\n")
    rc, data, _ = run(rra, capsys, env)
    assert counts(rules_by_id(data)[ID_A]) == (1, 0, 0, 0)
    assert data["input_quality"]["malformed_rows"]["locations"] == [
        "pre_trade_discipline_2026-06-30.jsonl:2"
    ]


# ---------------------------------------------------------------------------
# Code review round 3 regressions
# ---------------------------------------------------------------------------


def test_lone_surrogate_in_a_row_renders_cleanly(env, rra, capsys):
    entry = applied_entry(RULE_C)
    entry["text"] = "\ud800 broken"
    one_rule_env(env, [make_row("2026-06-10", [cand(checks=[check(ID_C, "followed")])], [entry])])
    md = _markdown(rra, capsys, env)
    assert ID_C in md
    assert sorted(p.suffix for p in env.out.iterdir()) == [".json", ".md"]


def test_rule_id_is_escaped_in_markdown(env, rra, capsys):
    entry = applied_entry(RULE_C)
    entry["rule_id"] = "r|1<b>"
    one_rule_env(
        env, [make_row("2026-06-10", [cand(checks=[check("r|1<b>", "followed")])], [entry])]
    )
    md = _markdown(rra, capsys, env)
    assert "r|1<b>" not in md
    assert "r\\|1&lt;b&gt;" in md


def test_bom_and_crlf_journal_lines_are_read(env, rra, capsys):
    one_rule_env(env, [])
    first = make_row(
        "2026-06-10", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)]
    )
    second = make_row(
        "2026-06-11", [cand(checks=[check(ID_A, "followed")])], [applied_entry(RULE_A)]
    )
    path = env.journal / "pre_trade_discipline_2026-06-30.jsonl"
    body = json.dumps(first) + "\r\n" + json.dumps(second) + "\r\n"
    path.write_bytes(b"\xef\xbb\xbf" + body.encode("utf-8"))
    rc, data, _ = run(rra, capsys, env)
    assert data["input_quality"]["malformed_rows"]["count"] == 0
    assert counts(rules_by_id(data)[ID_A]) == (2, 0, 0, 0)
