"""Gate integration tests for the approved-rule ledger (issue #514). Fictional data only."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import approved_rules as ar
import pytest
from check_pre_trade_discipline import (
    evaluate_pre_trade_gate,
    finalize_links,
    generate_markdown_report,
    main,
    parse_as_of,
    write_journal,
    write_reports,
)
from test_check_pre_trade_discipline import (
    allowed_artifacts,
    base_candidate,
    evaluate,
    load_thesis_store_module,
    write_json,
)

R1 = "require the confirmed pivot before any entry"
R2 = "keep portfolio heat at or below 4R"
NOW = datetime(2026, 5, 31, 21, 0, tzinfo=timezone.utc)
SCRIPT = Path(__file__).resolve().parents[1] / "check_pre_trade_discipline.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "flag_absent_baseline.json"


def rule(text: str, **overrides) -> dict:
    row = {
        "rule_id": ar.rule_id_for(text),
        "text": text,
        "status": "active",
        "effective_date": "2026-06-01",
        "review_after": "2026-07-31",
        "expires_on": None,
        "origin": "coach_accepted",
        "superseded_by": None,
        "evidence_ids": [],
        "history": [{"at": NOW.isoformat(), "event": "activated"}],
    }
    row.update(overrides)
    return row


def make_ledger(tmp_path: Path, *rules: dict) -> Path:
    path = tmp_path / "state" / "approved_rules.json"
    ar.save_ledger(path, {"schema_version": 1, "rules": list(rules)})
    return path


def ack(text: str, status: str = "followed", note: str = "") -> dict:
    return {"rule_id": ar.rule_id_for(text), "status": status, "note": note}


def run_gate(tmp_path: Path, candidates: list[dict], ledger: Path | None, **kwargs) -> dict:
    return evaluate(tmp_path, candidates, approved_rules_ledger=ledger, **kwargs)


# ---------------------------------------------------------------------------
# Flag absent: byte-identical output
# ---------------------------------------------------------------------------


def _normalize(text: str, tmp: Path, thesis_id: str) -> str:
    text = text.replace(str(tmp), "TMP").replace(thesis_id, "TID")
    text = re.sub(r"\d{4}-\d{2}-\d{2}_\d{6}", "TS", text)
    text = re.sub(
        r"pre_trade_discipline_\d{4}-\d{2}-\d{2}\.jsonl", "pre_trade_discipline_DATE.jsonl", text
    )
    return re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+\+00:00", "NOW", text)


def test_flag_absent_output_is_byte_identical_to_pre_change_baseline(tmp_path: Path):
    state = tmp_path / "theses"
    thesis_id = load_thesis_store_module().register(
        state,
        {
            "ticker": "LINK",
            "thesis_type": "growth_momentum",
            "thesis_statement": "Link report test thesis",
            "origin": {"skill": "pre-trade-test", "output_file": "fixture.json"},
            "_source_date": "2026-07-02",
        },
    )
    market = write_json(tmp_path / "m.json", {"recommendation": "NEW_ENTRY_ALLOWED"})
    circuit = write_json(tmp_path / "c.json", {"recommendation": "TRADING_ALLOWED"})
    candidates = [
        {
            "symbol": "AAPL",
            "order_intent": "ENTRY_READY",
            "thesis_id": thesis_id,
            "entry_in_written_plan": True,
            "stop_predefined": True,
            "size_within_plan": True,
            "planned_risk_dollars": 500,
            "actual_risk_dollars": 500,
            # Present in the answers file but ignored when the flag is absent.
            "approved_rule_checks": [{"rule_id": "rule_x", "status": "followed"}],
        },
        {"symbol": "MSFT", "order_intent": "WATCHLIST"},
    ]
    answers = write_json(tmp_path / "a.json", {"candidates": candidates})
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--answers-file",
            str(answers),
            "--state-dir",
            str(state),
            "--as-of",
            "2026-07-03T12:00:00-04:00",
            "--market-regime-decision",
            str(market),
            "--circuit-breaker-decision",
            str(circuit),
            "--output-dir",
            str(tmp_path / "r"),
            "--journal-dir",
            str(tmp_path / "j"),
        ],
        capture_output=True,
        text=True,
    )
    actual = {
        "rc": proc.returncode,
        "stdout": proc.stdout,
        "json": next((tmp_path / "r").glob("*.json")).read_text(),
        "md": next((tmp_path / "r").glob("*.md")).read_text(),
        "journal": next((tmp_path / "j").glob("*.jsonl")).read_text(),
    }
    expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert proc.stderr == ""
    for key in ("stdout", "json", "md", "journal"):
        assert _normalize(actual[key], tmp_path, thesis_id) == expected[key], key
    assert actual["rc"] == expected["rc"] == 0
    assert "approved_rule" not in actual["json"]
    assert "approved_rule" not in actual["journal"]


# ---------------------------------------------------------------------------
# Flag present: acknowledgement behaviour
# ---------------------------------------------------------------------------


def test_followed_and_not_applicable_pass(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1), rule(R2))
    cand = base_candidate(approved_rule_checks=[ack(R1, "followed"), ack(R2, "not_applicable")])
    result = run_gate(tmp_path, [cand], ledger)
    assert result["overall_decision"] == "GO"
    assert result["approved_rules"]["status"] == "loaded"
    assert [r["rule_id"] for r in result["approved_rules"]["applied"]] == [
        ar.rule_id_for(R1),
        ar.rule_id_for(R2),
    ]
    assert result["inputs"]["approved_rules_ledger"] == str(ledger)
    assert result["candidate_results"][0]["approved_rule_checks"] == [
        ack(R1, "followed"),
        ack(R2, "not_applicable"),
    ]


def test_missing_acknowledgement_requires_review(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1))
    result = run_gate(tmp_path, [base_candidate()], ledger)
    assert result["overall_decision"] == "REVIEW_REQUIRED"
    assert result["candidate_results"][0]["reasons"] == [
        f"approved rule {ar.rule_id_for(R1)} not acknowledged: {R1}"
    ]
    assert result["candidate_results"][0]["approved_rule_checks"] == []


def test_exception_with_note_requires_review_carrying_note(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1))
    cand = base_candidate(approved_rule_checks=[ack(R1, "exception", "  gap through pivot  ")])
    result = run_gate(tmp_path, [cand], ledger)
    assert result["overall_decision"] == "REVIEW_REQUIRED"
    assert result["candidate_results"][0]["reasons"] == [
        f"approved rule {ar.rule_id_for(R1)} exception: gap through pivot"
    ]
    assert result["candidate_results"][0]["approved_rule_checks"][0]["note"] == "gap through pivot"


@pytest.mark.parametrize("note", ["", "   ", None])
def test_exception_without_note_requires_review(tmp_path: Path, note):
    ledger = make_ledger(tmp_path, rule(R1))
    check = {"rule_id": ar.rule_id_for(R1), "status": "exception"}
    if note is not None:
        check["note"] = note
    result = run_gate(tmp_path, [base_candidate(approved_rule_checks=[check])], ledger)
    assert result["overall_decision"] == "REVIEW_REQUIRED"
    assert "not acknowledged" in result["candidate_results"][0]["reasons"][0]


@pytest.mark.parametrize("status", ["Followed", " followed", "ok", ""])
def test_status_is_matched_exactly(tmp_path: Path, status):
    ledger = make_ledger(tmp_path, rule(R1))
    result = run_gate(tmp_path, [base_candidate(approved_rule_checks=[ack(R1, status)])], ledger)
    assert result["overall_decision"] == "REVIEW_REQUIRED"
    assert "not acknowledged" in result["candidate_results"][0]["reasons"][0]


def test_rule_id_is_matched_exactly(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1))
    check = {"rule_id": ar.rule_id_for(R1).upper(), "status": "followed"}
    result = run_gate(tmp_path, [base_candidate(approved_rule_checks=[check])], ledger)
    assert result["overall_decision"] == "REVIEW_REQUIRED"


@pytest.mark.parametrize(
    "checks",
    [
        "followed",
        {"rule_id": "x"},
        ["followed"],
        [{"status": "followed"}],
        [{"rule_id": ""}],
    ],
)
def test_malformed_checks_require_review_and_are_not_trusted(tmp_path: Path, checks):
    ledger = make_ledger(tmp_path, rule(R1))
    result = run_gate(tmp_path, [base_candidate(approved_rule_checks=checks)], ledger)
    assert result["overall_decision"] == "REVIEW_REQUIRED"
    assert "approved_rule_checks" in result["candidate_results"][0]["reasons"][0]
    assert result["candidate_results"][0]["approved_rule_checks"] == []


def test_duplicate_rule_id_in_checks_is_malformed(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1))
    cand = base_candidate(approved_rule_checks=[ack(R1), ack(R1, "exception", "n")])
    result = run_gate(tmp_path, [cand], ledger)
    assert result["overall_decision"] == "REVIEW_REQUIRED"
    assert "more than once" in result["candidate_results"][0]["reasons"][0]
    assert result["candidate_results"][0]["approved_rule_checks"] == []


def test_entry_for_unapplied_rule_is_recorded_and_warned(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1))
    cand = base_candidate(approved_rule_checks=[ack(R1), ack("some other rule")])
    result = run_gate(tmp_path, [cand], ledger)
    assert result["overall_decision"] == "GO"
    assert len(result["candidate_results"][0]["approved_rule_checks"]) == 2
    assert any("does not match an applied rule" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Rule states
# ---------------------------------------------------------------------------


def test_review_due_rule_is_applied_and_warned(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1, review_after="2026-07-01"))
    result = run_gate(tmp_path, [base_candidate()], ledger)
    assert result["overall_decision"] == "REVIEW_REQUIRED"
    assert result["approved_rules"]["applied"][0]["state"] == "review_due"
    assert any("past its review date 2026-07-01" in w for w in result["warnings"])
    acked = run_gate(tmp_path, [base_candidate(approved_rule_checks=[ack(R1)])], ledger)
    assert acked["overall_decision"] == "GO"


def test_inactive_rules_are_not_required(tmp_path: Path):
    ledger = make_ledger(
        tmp_path,
        rule(R1, expires_on="2026-06-30"),
        rule("future rule", effective_date="2026-07-04", review_after="2026-07-31"),
        rule("retired rule", status="retired"),
        rule("old rule", status="superseded", superseded_by=ar.rule_id_for("retired rule")),
    )
    result = run_gate(tmp_path, [base_candidate()], ledger)
    assert result["overall_decision"] == "GO"
    states = {r["state"] for r in result["approved_rules"]["not_applied"]}
    assert states == {"expired", "not_yet_effective", "retired", "superseded"}
    assert any("expired on 2026-06-30" in w for w in result["warnings"])


def test_et_date_boundary_uses_new_york_calendar_date(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1, effective_date="2026-06-01"))
    early = run_gate(
        tmp_path,
        [base_candidate()],
        ledger,
        as_of=parse_as_of("2026-06-01T03:00:00+00:00"),
    )
    assert early["approved_rules"]["as_of_date"] == "2026-05-31"
    assert early["approved_rules"]["applied"] == []
    assert early["overall_decision"] == "GO"
    later = run_gate(
        tmp_path,
        [base_candidate()],
        ledger,
        as_of=parse_as_of("2026-06-01T05:00:00+00:00"),
    )
    assert [r["rule_id"] for r in later["approved_rules"]["applied"]] == [ar.rule_id_for(R1)]


def test_date_only_as_of_covers_the_named_et_day(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1, effective_date="2026-06-01"))
    result = run_gate(tmp_path, [base_candidate()], ledger, as_of=parse_as_of("2026-06-01"))
    assert result["approved_rules"]["as_of_date"] == "2026-06-01"
    assert len(result["approved_rules"]["applied"]) == 1


# ---------------------------------------------------------------------------
# Ledger unavailable
# ---------------------------------------------------------------------------


def _cli(tmp_path: Path, answers: dict, *extra: str) -> int:
    answers_file = write_json(tmp_path / "answers.json", answers)
    market, circuit = allowed_artifacts(tmp_path)
    return main(
        [
            "--answers-file",
            str(answers_file),
            "--market-regime-decision",
            str(market),
            "--circuit-breaker-decision",
            str(circuit),
            "--output-dir",
            str(tmp_path / "reports"),
            "--journal-dir",
            str(tmp_path / "journal"),
            "--as-of",
            "2026-07-03",
            *extra,
        ]
    )


@pytest.mark.parametrize("kind", ["missing", "invalid", "truncated"])
def test_unavailable_ledger_requires_review_and_still_writes_artifacts(
    tmp_path: Path, kind, capsys
):
    path = tmp_path / "bad" / "ledger.json"
    if kind != "missing":
        path.parent.mkdir()
        path.write_text(
            '{"schema_version": 1, "rules": [' if kind == "truncated" else '{"schema_version": 9}',
            encoding="utf-8",
        )
    answers = {"candidates": [base_candidate(approved_rule_checks=[ack(R1)])]}
    assert _cli(tmp_path, answers, "--approved-rules-ledger", str(path)) == 0
    assert list((tmp_path / "reports").glob("*.json"))
    assert list((tmp_path / "reports").glob("*.md"))
    row = json.loads(next((tmp_path / "journal").glob("*.jsonl")).read_text().splitlines()[0])
    assert row["overall_decision"] == "REVIEW_REQUIRED"
    assert row["approved_rules"]["status"] == "unavailable"
    reason = row["candidate_results"][0]["reasons"][0]
    assert reason.startswith(f"approved-rule ledger {path} could not be read:")
    assert row["candidate_results"][0]["approved_rule_checks"] == [ack(R1)]
    assert any("does not match an applied rule" in w for w in row["warnings"])
    out = capsys.readouterr().out
    assert "Approved rules: ledger unavailable" in out


def test_unavailable_ledger_exit_2_with_fail_on_non_go(tmp_path: Path):
    answers = {"candidates": [base_candidate()]}
    rc = _cli(
        tmp_path,
        answers,
        "--approved-rules-ledger",
        str(tmp_path / "missing.json"),
        "--fail-on-non-go",
    )
    assert rc == 2


def test_unavailable_ledger_records_unknown_status_for_unmatched_entry(tmp_path: Path):
    answers = {
        "candidates": [
            base_candidate(approved_rule_checks=[{"rule_id": "rule_zzz", "status": "weird"}])
        ]
    }
    assert _cli(tmp_path, answers, "--approved-rules-ledger", str(tmp_path / "none.json")) == 0
    row = json.loads(next((tmp_path / "journal").glob("*.jsonl")).read_text().splitlines()[0])
    assert row["candidate_results"][0]["approved_rule_checks"][0]["status"] == "weird"
    assert any("rule_zzz" in w for w in row["warnings"])


# ---------------------------------------------------------------------------
# Decision interplay
# ---------------------------------------------------------------------------


def test_no_actionable_candidates_stays_no_actionable_orders(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1))
    cand = {"symbol": "MSFT", "order_intent": "WATCHLIST"}
    result = run_gate(tmp_path, [cand], ledger)
    assert result["overall_decision"] == "NO_ACTIONABLE_ORDERS"


def test_no_applied_rules_is_go(tmp_path: Path):
    ledger = make_ledger(tmp_path)
    result = run_gate(tmp_path, [base_candidate()], ledger)
    assert result["overall_decision"] == "GO"
    assert result["approved_rules"]["applied"] == []


def test_no_go_outranks_missing_acknowledgement(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1))
    result = run_gate(tmp_path, [base_candidate(stop_predefined=False)], ledger)
    assert result["overall_decision"] == "NO_GO"
    reasons = result["candidate_results"][0]["reasons"]
    assert "stop is not predefined" in reasons
    assert any("not acknowledged" in r for r in reasons)


def test_non_actionable_candidate_checks_recorded_decision_unchanged(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1))
    watch = {
        "symbol": "MSFT",
        "order_intent": "WATCHLIST",
        "approved_rule_checks": [ack(R1, "followed")],
    }
    result = run_gate(tmp_path, [base_candidate(approved_rule_checks=[ack(R1)]), watch], ledger)
    watch_result = result["candidate_results"][1]
    assert watch_result["decision"] == "NO_ACTIONABLE_ORDERS"
    assert watch_result["approved_rule_checks"] == [ack(R1, "followed")]
    assert result["overall_decision"] == "GO"


def test_non_actionable_candidate_malformed_checks_warn_without_changing_decision(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1))
    watch = {"symbol": "MSFT", "order_intent": "WATCHLIST", "approved_rule_checks": "oops"}
    result = run_gate(tmp_path, [watch], ledger)
    assert result["candidate_results"][0]["decision"] == "NO_ACTIONABLE_ORDERS"
    assert result["candidate_results"][0]["approved_rule_checks"] == []
    assert any("MSFT" in w and "must be a list" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Links, journal, markdown, stdout
# ---------------------------------------------------------------------------


def test_links_still_work_and_checks_survive_finalize_links(tmp_path: Path):
    thesis_store = load_thesis_store_module()
    state_dir = tmp_path / "theses"
    thesis_id = thesis_store.register(
        state_dir,
        {
            "ticker": "LINK",
            "thesis_type": "growth_momentum",
            "thesis_statement": "Link report test thesis",
            "origin": {"skill": "pre-trade-test", "output_file": "fixture.json"},
            "_source_date": "2026-07-02",
        },
    )
    ledger = make_ledger(tmp_path, rule(R1))
    cand = base_candidate(
        symbol="LINK", thesis_id=thesis_id, approved_rule_checks=[ack(R1, "followed", "ok")]
    )
    result = run_gate(tmp_path, [cand], ledger, state_dir=state_dir)
    write_reports(result, tmp_path / "reports", json_only=False)
    assert result["overall_decision"] == "GO"
    assert result["candidate_results"][0]["link_status"] == "linked"
    assert result["candidate_results"][0]["approved_rule_checks"] == [ack(R1, "followed", "ok")]


def test_journal_and_markdown_contain_the_new_block(tmp_path: Path):
    ledger = make_ledger(tmp_path, rule(R1))
    result = run_gate(
        tmp_path, [base_candidate(approved_rule_checks=[ack(R1, "followed")])], ledger
    )
    journal_path = write_journal(result, tmp_path / "journal")
    row = json.loads(journal_path.read_text().splitlines()[0])
    assert row["approved_rules"]["applied"][0]["text"] == R1
    assert row["candidate_results"][0]["approved_rule_checks"][0]["status"] == "followed"
    _, md_path = write_reports(result, tmp_path / "reports", json_only=False)
    markdown = md_path.read_text()
    assert "## Approved operating rules" in markdown
    assert R1 in markdown and "### Acknowledgements" in markdown


def test_markdown_escapes_rule_text_and_notes(tmp_path: Path):
    tricky = "avoid chasing | wait for\nthe retest"
    ledger = make_ledger(tmp_path, rule(tricky))
    cand = base_candidate(approved_rule_checks=[ack(tricky, "exception", "gap | overnight\nnews")])
    result = run_gate(tmp_path, [cand], ledger)
    markdown = generate_markdown_report(result)
    assert "avoid chasing \\| wait for<br>the retest" in markdown
    assert "gap \\| overnight<br>news" in markdown
    for line in markdown.splitlines():
        unescaped = len(re.findall(r"(?<!\\)\|", line))
        if line.startswith("| AAPL | ENTRY_READY"):
            assert unescaped == 7  # 6 columns
        elif line.startswith("| AAPL | rule_"):
            assert unescaped == 5  # 4 columns
        elif line.startswith("| rule_"):
            assert unescaped == 6  # 5 columns


def test_markdown_section_absent_without_flag(tmp_path: Path):
    result = evaluate(tmp_path, [base_candidate()])
    assert "approved_rules" not in result
    assert "approved_rules_ledger" not in result["inputs"]
    assert "approved_rule_checks" not in result["candidate_results"][0]
    assert "Approved operating rules" not in generate_markdown_report(result)


def test_stdout_shows_summary_and_warnings_only_with_flag(tmp_path: Path, capsys):
    ledger = make_ledger(tmp_path, rule(R1, review_after="2026-07-01"))
    answers = {"candidates": [base_candidate(approved_rule_checks=[ack(R1)])]}
    assert _cli(tmp_path, answers, "--approved-rules-ledger", str(ledger)) == 0
    out = capsys.readouterr().out
    assert "Approved rules: 1 applied, 0 not applied (as of 2026-07-03)" in out
    assert "Warning: approved rule" in out and "past its review date" in out


def test_stdout_unchanged_without_flag(tmp_path: Path, capsys):
    assert _cli(tmp_path, {"candidates": [base_candidate()]}) == 0
    out = capsys.readouterr().out
    assert "Approved rules" not in out and "Warning:" not in out


def test_direct_api_without_ledger_keeps_old_signature(tmp_path: Path):
    market, circuit = allowed_artifacts(tmp_path)
    result = evaluate_pre_trade_gate(
        [base_candidate()],
        as_of=parse_as_of("2026-07-03"),
        state_dir=None,
        revenge_window_hours=24.0,
        market_regime_decision=market,
        circuit_breaker_decision=circuit,
        output_dir=tmp_path / "r",
        json_only=True,
    )
    finalize_links(result, state_dir=None, as_of=parse_as_of("2026-07-03"))
    assert "approved_rules" not in result
