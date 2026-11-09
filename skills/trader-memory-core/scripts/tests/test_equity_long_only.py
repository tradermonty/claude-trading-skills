"""Unsupported equity shorts must not silently enter long-only accounting."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
import thesis_ingest as ingest
import thesis_review as review
import thesis_store as store
import yaml

DATE = "2026-01-01T00:00:00+00:00"
END = "2026-01-02T00:00:00+00:00"


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def data(**overrides):
    result = {
        "ticker": "TEST",
        "thesis_type": "pivot_breakout",
        "thesis_statement": "Synthetic long-only boundary",
        "origin": {"skill": "test", "output_file": "fixture.json"},
    }
    result.update(overrides)
    return result


def ready(state, stop=90):
    tid = store.register(
        state,
        data(_source_date="2026-01-01", entry={"target_price": 100}, exit={"stop_loss": stop}),
    )
    store.transition(state, tid, "ENTRY_READY", "synthetic ready", event_date=DATE)
    return tid


def active(state):
    tid = ready(state)
    store.open_position(state, tid, 100, DATE, shares=10, event_date=DATE)
    return tid


def manual(**overrides):
    record = {
        "ticker": "TEST",
        "thesis_type": "pivot_breakout",
        "thesis_statement": "Synthetic manual equity",
        "entry_price": 100,
        "stop_price": 90,
        "shares": 10,
    }
    record.update(overrides)
    return record


@pytest.mark.parametrize(
    "fields",
    [
        {"direction": "SHORT"},
        {"direction": " short "},
        {"position": {"direction": "SHORT"}},
        {"position": {"asset_type": "futures", "direction": "SHORT"}},
    ],
)
def test_raw_registration_short_direction_is_not_dropped(tmp_path, fields):
    state = tmp_path / "theses"
    with pytest.raises(ValueError, match="long-only"):
        store.register(state, data(**fields))
    assert not state.exists()


@pytest.mark.parametrize(
    "fields",
    [{"direction": "SHORT"}, {"direction": "short"}, {"stop_price": 110}, {"stop_loss": 110}],
)
def test_manual_short_input_rejects_before_registration(tmp_path, fields):
    record = manual(**fields)
    before = json.dumps(record, sort_keys=True)
    with pytest.raises(ValueError, match="long-only"):
        ingest.ingest_manual(record, "synthetic.json")
    assert json.dumps(record, sort_keys=True) == before
    source = tmp_path / "manual.json"
    source.write_text(json.dumps(record))
    state = tmp_path / "theses"
    assert ingest.ingest("manual", str(source), str(state)) == []
    assert not state.exists()


def test_manual_long_normalization_preserves_provenance_and_aliases():
    record = manual(direction=" long ", side="SELL", stop_loss=95, stop_price=110)
    result = ingest.ingest_manual(record, "synthetic.json")
    assert result["entry"] == {}
    assert result["exit"]["stop_loss"] == 95
    assert result["origin"]["raw_provenance"] == record


def test_manual_short_cli_rejects_without_state(tmp_path):
    source = tmp_path / "manual.json"
    source.write_text(json.dumps(manual(direction="SHORT", stop_price=110)))
    state = tmp_path / "theses"
    script = Path(ingest.__file__)
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--source",
            "manual",
            "--input",
            str(source),
            "--state-dir",
            str(state),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "long-only" in result.stderr
    assert not state.exists()


def test_manual_bulk_csv_short_row_rolls_back_all(tmp_path):
    state = tmp_path / "theses"
    ready(state)
    before = snapshot(state)
    source = tmp_path / "records.csv"
    source.write_text(
        "ticker,thesis_type,thesis_statement,entry_price,stop_price\nLONG,pivot_breakout,Long record,100,90\nSHORT,pivot_breakout,Short record,100,110\n"
    )
    with pytest.raises(ValueError, match="row 3.*long-only"):
        ingest.ingest_bulk_csv("manual", str(source), str(state))
    assert snapshot(state) == before


@pytest.mark.parametrize("direction", ["SHORT", " short ", True, ["SHORT"]])
def test_equity_open_cannot_ignore_short_direction(tmp_path, direction):
    tid = ready(tmp_path)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="long-only"):
        store.open_position(tmp_path, tid, 100, DATE, shares=10, direction=direction)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("stop,fill", [(110, 100), (95, 90)])
def test_initial_equity_stop_above_actual_fill_rejects(tmp_path, stop, fill):
    tid = ready(tmp_path, stop=stop)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="long-only"):
        store.open_position(tmp_path, tid, fill, DATE, shares=10)
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("exit_price,pnl", [(90, -100), (120, 200)])
def test_long_equity_roundtrip_retains_sign_and_amount(tmp_path, exit_price, pnl):
    tid = ready(tmp_path)
    store.open_position(tmp_path, tid, 100, DATE, shares=10, direction=" long ")
    result = store.close(tmp_path, tid, "manual", exit_price, END)
    assert result["outcome"]["pnl_dollars"] == pnl


def test_active_long_profit_stop_and_partial_exit_remain_valid(tmp_path):
    tid = active(tmp_path)
    store.update(tmp_path, tid, {"exit": {"stop_loss": 110}})
    store.trim(tmp_path, tid, 5, 115, END, "synthetic trim")
    result = store.close(tmp_path, tid, "manual", 120, "2026-01-03T00:00:00+00:00")
    assert result["exit"]["stop_loss"] == 110
    assert result["outcome"]["pnl_dollars"] == 175


def report(**overrides):
    result = {
        "mode": "shares",
        "parameters": {"entry_price": 100, "stop_price": 90},
        "calculations": {"fixed_fractional": {"method": "fixed_fractional"}},
        "final_recommended_shares": 10,
        "final_position_value": 1000,
        "final_risk_dollars": 100,
        "final_risk_pct": 1,
    }
    result.update(overrides)
    return result


@pytest.mark.parametrize(
    "payload",
    [
        report(direction="SHORT"),
        report(parameters={"entry_price": 100, "stop_price": 90, "direction": "SHORT"}),
        report(parameters={"entry_price": 100, "stop_price": 110}),
    ],
)
def test_equity_attach_rejects_short_report_before_mutation(tmp_path, payload):
    state = tmp_path / "theses"
    tid = ready(state)
    source = tmp_path / "position.json"
    source.write_text(json.dumps(payload))
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="long-only"):
        store.attach_position(state, tid, str(source))
    assert snapshot(tmp_path) == before


def corrupt_short(state, tid, manual_provenance=False):
    thesis = store.get(state, tid)
    if manual_provenance:
        thesis["origin"]["skill"] = "manual"
        thesis["origin"]["raw_provenance"] = {
            "direction": "SHORT",
            "entry_price": 100,
            "stop_price": 110,
        }
    else:
        thesis["position"]["direction"] = "SHORT"
    (state / f"{tid}.yaml").write_text(yaml.safe_dump(thesis, sort_keys=False))
    return thesis


@pytest.mark.parametrize("operation", ["close", "trim", "terminate", "update"])
@pytest.mark.parametrize("manual_provenance", [False, True])
def test_legacy_explicit_equity_short_cannot_write_wrong_accounting(
    tmp_path, operation, manual_provenance
):
    tid = active(tmp_path)
    corrupt_short(tmp_path, tid, manual_provenance)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="long-only"):
        if operation == "close":
            store.close(tmp_path, tid, "manual", 90, END)
        elif operation == "trim":
            store.trim(tmp_path, tid, 5, 90, END, "synthetic")
        elif operation == "terminate":
            store.terminate(tmp_path, tid, "INVALIDATED", "manual", 90, END)
        else:
            store.update(tmp_path, tid, {"thesis_statement": "cannot mask invalid side"})
    assert snapshot(tmp_path) == before
    # Read APIs stay available for inspecting and repairing unsupported legacy data.
    assert store.get(tmp_path, tid)["status"] == "ACTIVE"


@pytest.mark.parametrize("manual_provenance", [False, True])
def test_mae_mfe_rejects_unsupported_equity_short_before_network(tmp_path, manual_provenance):
    state = tmp_path / "theses"
    tid = active(state)
    store.close(state, tid, "manual", 120, END)
    thesis = corrupt_short(state, tid, manual_provenance)
    adapter = Mock()
    adapter.get_daily_closes.side_effect = AssertionError("provider forbidden")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="long-only"):
        review.compute_mae_mfe(thesis, adapter)
    adapter.get_daily_closes.assert_not_called()
    assert snapshot(tmp_path) == before
    assert not (tmp_path / "journal").exists()


def test_futures_short_plan_can_be_registered_then_opened_and_closed(tmp_path):
    # Generic IDEA has no asset type until a validated futures attachment/direct open.
    tid = ready(tmp_path, stop=110)
    store.open_position(
        tmp_path,
        tid,
        100,
        DATE,
        contracts=1,
        multiplier=10,
        direction="SHORT",
        contract_symbol="ES",
        contract_currency="USD",
    )
    result = store.close(tmp_path, tid, "manual", 90, END)
    assert result["position"]["asset_type"] == "futures"
    assert result["position"]["direction"] == "SHORT"
    assert result["outcome"]["pnl_dollars"] == 100
    content = Path(
        review.generate_postmortem(tid, str(tmp_path), journal_dir=str(tmp_path / "journal"))
    ).read_text(encoding="utf-8")
    assert "Historical record only" not in content
    assert "| Contracts | 1 |" in content
    assert f"| P&L ($) | {result['outcome']['pnl_dollars']} |" in content


def test_persisted_lowercase_equity_direction_does_not_relax_schema(tmp_path):
    tid = active(tmp_path)
    thesis = store.get(tmp_path, tid)
    thesis["position"]["direction"] = "long"
    with pytest.raises(ValueError):
        store.validate_thesis(thesis)


@pytest.mark.parametrize(
    "entry,stop",
    [(True, 110), (100, False), ("100", 110), (100, float("nan")), (float("inf"), 110)],
)
def test_supplied_manual_initial_pair_is_finite_numeric(entry, stop):
    with pytest.raises(ValueError, match="long-only"):
        ingest.ingest_manual(manual(entry_price=entry, stop_price=stop), "synthetic.json")


@pytest.mark.parametrize("entry,stop", [(None, 110), (100, None), (100, 100), (0, 110), (-10, 5)])
def test_optional_equal_and_legacy_nonpositive_pairs_remain_compatible(entry, stop):
    result = ingest.ingest_manual(manual(entry_price=entry, stop_price=stop), "synthetic.json")
    assert result["entry"] == {}


def test_manual_invalid_side_is_checked_before_idempotency(tmp_path):
    source = tmp_path / "manual.json"
    source.write_text(json.dumps(manual()))
    state = tmp_path / "theses"
    ids = ingest.ingest("manual", str(source), str(state))
    assert len(ids) == 1
    before = snapshot(state)
    source.write_text(json.dumps(manual(direction="SHORT")))
    assert ingest.ingest("manual", str(source), str(state)) == []
    assert snapshot(state) == before


def test_unsupported_parabolic_source_is_not_documented_or_accepted(tmp_path):
    root = Path(__file__).resolve().parents[4]
    assert "--source parabolic-short-trade-planner" not in (root / "CLAUDE.md").read_text(
        encoding="utf-8"
    )
    state = tmp_path / "theses"
    with pytest.raises(ValueError, match="Unknown source"):
        ingest.ingest("parabolic-short-trade-planner", str(tmp_path / "plan.json"), str(state))
    assert not state.exists()


def test_cli_equity_open_does_not_ignore_short_flag(tmp_path):
    state = tmp_path / "theses"
    tid = ready(state)
    before = snapshot(state)
    result = subprocess.run(
        [
            sys.executable,
            str(Path(store.__file__)),
            "--state-dir",
            str(state),
            "open-position",
            tid,
            "--actual-price",
            "100",
            "--actual-date",
            DATE,
            "--shares",
            "10",
            "--direction",
            "SHORT",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "long-only" in result.stderr
    assert snapshot(state) == before


@pytest.mark.parametrize("manual_provenance", [False, True])
def test_attach_cannot_erase_legacy_short_marker(tmp_path, manual_provenance):
    state = tmp_path / "theses"
    tid = ready(state)
    source = tmp_path / "position.json"
    source.write_text(json.dumps(report()))
    store.attach_position(state, tid, str(source))
    corrupt_short(state, tid, manual_provenance)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="long-only"):
        store.attach_position(state, tid, str(source))
    assert snapshot(tmp_path) == before


def test_generic_origin_update_cannot_erase_legacy_short_intent(tmp_path):
    tid = active(tmp_path)
    corrupt_short(tmp_path, tid, manual_provenance=True)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="long-only"):
        store.update(tmp_path, tid, {"origin": {"skill": "test", "raw_provenance": {}}})
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "status,manual_provenance", [("IDEA", True), ("ACTIVE", False), ("ACTIVE", True)]
)
def test_legacy_short_can_be_invalidated_without_accounting(tmp_path, manual_provenance, status):
    tid = active(tmp_path) if status == "ACTIVE" else store.register(tmp_path, data())
    prior = corrupt_short(tmp_path, tid, manual_provenance)
    result = store.terminate(tmp_path, tid, "INVALIDATED", "unsupported legacy equity short")
    assert result["status"] == "INVALIDATED"
    assert result["outcome"] == prior["outcome"]
    assert result.get("position") == prior.get("position")
    assert result["origin"] == prior["origin"]
    assert store.list_review_due(tmp_path, "2099-01-01") == []


@pytest.mark.parametrize("manual_provenance", [False, True])
def test_legacy_short_can_be_marked_reviewed_without_changing_money(tmp_path, manual_provenance):
    tid = active(tmp_path)
    prior = corrupt_short(tmp_path, tid, manual_provenance)
    result = store.mark_reviewed(tmp_path, tid, review_date="2026-01-03", outcome="WARN")
    assert result["monitoring"]["last_review_date"] == "2026-01-03"
    assert result["outcome"] == prior["outcome"]
    assert result["position"] == prior["position"]


@pytest.mark.parametrize(
    "direction",
    [
        "BUY",
        "Long position",
        "buy",
        "",
        "unclassified",
        "Sell to close",
        "Long (sell calls)",
        "Buy, sell at target",
    ],
)
def test_legacy_manual_nonshort_provenance_keeps_long_accounting(tmp_path, direction):
    state = tmp_path / "theses"
    tid = active(state)
    thesis = store.get(state, tid)
    thesis["origin"].update({"skill": "manual", "raw_provenance": {"direction": direction}})
    (state / f"{tid}.yaml").write_text(yaml.safe_dump(thesis), encoding="utf-8")
    result = store.close(state, tid, "manual", 120, END, event_date=END)
    assert result["outcome"]["pnl_dollars"] == 200
    assert result["origin"]["raw_provenance"]["direction"] == direction
    assert review.summary_stats(str(state))["count"] == 1
    report = Path(review.monthly_report(str(state), "2026-01")).read_text(encoding="utf-8")
    assert "20.0" in report


@pytest.mark.parametrize(
    "direction",
    [
        "SHORT",
        "SELL_SHORT",
        "sell short",
        "sell-short",
        "SELL",
        "Short position",
        "short sale",
        "SHORT SELL",
        "short-sell",
        "Short.",
        "Shorted",
        "sell short, 100 sh",
    ],
)
def test_legacy_explicit_short_aliases_are_excluded_without_poisoning_valid_trades(
    tmp_path, direction
):
    state = tmp_path / "theses"
    bad_id = active(state)
    store.close(state, bad_id, "manual", 90, END, event_date=END)
    bad = store.get(state, bad_id)
    bad["origin"].update({"skill": "manual", "raw_provenance": {"direction": direction}})
    (state / f"{bad_id}.yaml").write_text(yaml.safe_dump(bad), encoding="utf-8")
    good_id = store.register(
        state,
        data(
            ticker="GOOD",
            _source_date="2026-01-01",
            entry={"target_price": 100},
            exit={"stop_loss": 90},
        ),
    )
    store.transition(state, good_id, "ENTRY_READY", "ready", event_date=DATE)
    store.open_position(state, good_id, 100, DATE, shares=10, event_date=DATE)
    store.close(state, good_id, "manual", 120, END, event_date=END)
    before = snapshot(state)
    summary = review.summary_stats(str(state))
    assert summary["count"] == 1 and summary["avg_pnl_pct"] == 20
    assert summary["excluded_unsupported_equity_shorts"] == 1
    report = Path(review.monthly_report(str(state), "2026-01")).read_text(encoding="utf-8")
    assert "Excluded unsupported equity shorts: 1" in report
    assert "GOOD" in report and "TEST" not in report
    assert snapshot(state) == before


@pytest.mark.parametrize("direction,expected_count", [("BUY", 1), ("SHORT", 0), ("SELL_SHORT", 0)])
def test_review_summary_cli_handles_legacy_labels(tmp_path, direction, expected_count):
    tid = active(tmp_path)
    store.close(tmp_path, tid, "manual", 120, END, event_date=END)
    thesis = store.get(tmp_path, tid)
    thesis["origin"].update({"skill": "manual", "raw_provenance": {"direction": direction}})
    (tmp_path / f"{tid}.yaml").write_text(yaml.safe_dump(thesis), encoding="utf-8")
    before = snapshot(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            str(Path(store.__file__).with_name("trader_memory_cli.py")),
            "review",
            "--state-dir",
            str(tmp_path),
            "summary",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["count"] == expected_count
    assert summary.get("excluded_unsupported_equity_shorts", 0) == 1 - expected_count
    assert snapshot(tmp_path) == before


def test_partially_closed_legacy_short_can_be_retired_without_rewriting_ledger(tmp_path):
    tid = active(tmp_path)
    store.trim(tmp_path, tid, 5, 110, END, "trim", event_date=END)
    prior = corrupt_short(tmp_path, tid)
    result = store.terminate(tmp_path, tid, "INVALIDATED", "unsupported")
    assert result["status"] == "INVALIDATED"
    assert result["outcome"] == prior["outcome"]
    assert result["position"] == prior["position"]


@pytest.mark.parametrize("futures", [False, True])
def test_reports_exclude_equity_position_short_but_keep_futures_short(tmp_path, futures):
    state = tmp_path / "theses"
    if futures:
        tid = ready(state, stop=110)
        store.open_position(
            state,
            tid,
            100,
            DATE,
            contracts=1,
            multiplier=10,
            direction="SHORT",
            contract_symbol="ES",
            contract_currency="USD",
            event_date=DATE,
        )
        store.close(state, tid, "manual", 90, END, event_date=END)
    else:
        tid = active(state)
        store.close(state, tid, "manual", 90, END, event_date=END)
        corrupt_short(state, tid)
    before = snapshot(state)
    summary = review.summary_stats(str(state))
    assert summary["count"] == int(futures)
    assert summary.get("excluded_unsupported_equity_shorts", 0) == int(not futures)
    content = Path(review.monthly_report(str(state), "2026-01")).read_text(encoding="utf-8")
    assert ("TEST" in content) == futures
    assert snapshot(state) == before


@pytest.mark.parametrize("status", ["CLOSED", "INVALIDATED"])
@pytest.mark.parametrize("manual_provenance", [False, True])
@pytest.mark.parametrize("direction", ["SHORT", "SELL"])
@pytest.mark.parametrize("with_adapter", [False, True])
def test_legacy_short_postmortem_is_historical_and_preserves_state(
    tmp_path, status, manual_provenance, direction, with_adapter
):
    state = tmp_path / "theses"
    tid = active(state)
    if status == "CLOSED":
        store.close(state, tid, "manual", 120, END)
    else:
        store.terminate(state, tid, "INVALIDATED", "retired legacy record")
    thesis = corrupt_short(state, tid, manual_provenance)
    if manual_provenance:
        thesis["origin"]["raw_provenance"]["direction"] = direction
    else:
        thesis["position"]["direction"] = direction
    thesis["outcome"].update(
        pnl_dollars=777.0,
        pnl_pct=888.0,
        mae_pct=-999.0,
        mfe_pct=999.0,
        mae_mfe_source="old_untrusted",
    )
    thesis["outcome"]["lessons_learned"] = "Preserve original thesis evidence"
    (state / f"{tid}.yaml").write_text(yaml.safe_dump(thesis), encoding="utf-8")
    adapter = Mock()
    adapter.get_daily_closes.side_effect = AssertionError("provider forbidden")
    before = snapshot(state)
    path = review.generate_postmortem(tid, str(state), adapter if with_adapter else None)
    content = Path(path).read_text(encoding="utf-8")
    assert Path(path) == tmp_path / "journal" / f"pm_{tid}.md"
    assert "Historical record only" in content
    assert "unsupported legacy equity short" in content
    assert "stored values were not changed or validated" in content
    assert "Preserve original thesis evidence" in content
    assert status in content
    for metric in ("P&L ($)", "P&L (%)", "MAE (%)", "MFE (%)", "Position Value", "Risk ($)"):
        assert f"| {metric} | — |" in content
    assert "777.0" not in content
    assert "888.0" not in content
    assert "999.0" not in content
    assert snapshot(state) == before
    adapter.get_daily_closes.assert_not_called()


@pytest.mark.parametrize("status", ["CLOSED", "INVALIDATED"])
def test_legacy_short_postmortem_public_cli(tmp_path, status):
    state = tmp_path / "theses"
    tid = active(state)
    if status == "CLOSED":
        store.close(state, tid, "manual", 120, END)
    corrupt_short(state, tid)
    if status == "INVALIDATED":
        store.terminate(state, tid, "INVALIDATED", "legacy short")
    before = snapshot(state)
    journal = tmp_path / "custom-journal"
    completed = subprocess.run(
        [
            sys.executable,
            review.__file__,
            "--state-dir",
            str(state),
            "postmortem",
            tid,
            "--journal-dir",
            str(journal),
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "Postmortem generated:" in completed.stdout
    assert "Historical record only" in (journal / f"pm_{tid}.md").read_text(encoding="utf-8")
    assert snapshot(state) == before


@pytest.mark.parametrize("status", ["ACTIVE", "PARTIALLY_CLOSED"])
def test_nonterminal_short_cannot_generate_historical_postmortem(tmp_path, status):
    state = tmp_path / "theses"
    tid = active(state)
    if status == "PARTIALLY_CLOSED":
        store.trim(state, tid, 5, 120, END, "synthetic trim")
    corrupt_short(state, tid)
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="CLOSED or INVALIDATED"):
        review.generate_postmortem(tid, str(state))
    assert snapshot(tmp_path) == before


@pytest.mark.parametrize("direction", ["BUY", "Long position"])
def test_legacy_nonshort_postmortem_retains_accounting(tmp_path, direction):
    state = tmp_path / "theses"
    tid = active(state)
    store.close(state, tid, "manual", 120, END)
    thesis = store.get(state, tid)
    thesis["origin"].update(skill="manual", raw_provenance={"direction": direction})
    (state / f"{tid}.yaml").write_text(yaml.safe_dump(thesis), encoding="utf-8")
    content = Path(review.generate_postmortem(tid, str(state))).read_text(encoding="utf-8")
    assert "Historical record only" not in content
    assert f"| P&L ($) | {thesis['outcome']['pnl_dollars']} |" in content
