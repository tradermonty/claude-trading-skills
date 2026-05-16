"""Tests for thesis_store.py — CRUD, transitions, and index management."""

import json
from pathlib import Path

import pytest
import thesis_store

# -- Helpers -------------------------------------------------------------------


def _make_thesis_data(**overrides):
    """Create minimal thesis data for registration."""
    data = {
        "ticker": "AAPL",
        "thesis_type": "dividend_income",
        "thesis_statement": "AAPL dividend income thesis for testing",
        "origin": {
            "skill": "test-skill",
            "output_file": "test_output.json",
        },
    }
    data.update(overrides)
    return data


def _register_and_get(state_dir, **overrides):
    """Register a thesis and return (thesis_id, thesis_dict)."""
    data = _make_thesis_data(**overrides)
    tid = thesis_store.register(state_dir, data)
    thesis = thesis_store.get(state_dir, tid)
    return tid, thesis


# -- Tests: register + get ----------------------------------------------------


def test_register_and_get_match(tmp_path: Path):
    """register → get should return matching thesis."""
    tid, thesis = _register_and_get(tmp_path)

    assert thesis["thesis_id"] == tid
    assert thesis["ticker"] == "AAPL"
    assert thesis["thesis_type"] == "dividend_income"
    assert thesis["status"] == "IDEA"
    assert len(thesis["status_history"]) == 1
    assert thesis["status_history"][0]["status"] == "IDEA"
    assert thesis["created_at"] is not None
    assert thesis["updated_at"] is not None


def test_thesis_id_contains_hash4(tmp_path: Path):
    """thesis_id should contain a 4-char hex hash suffix."""
    tid, _ = _register_and_get(tmp_path)
    parts = tid.split("_")
    assert len(parts) == 5  # th, ticker, abbr, date, hash4
    assert parts[0] == "th"
    assert parts[1] == "aapl"
    assert parts[2] == "div"
    assert len(parts[3]) == 8  # YYYYMMDD
    assert len(parts[4]) == 4  # hash4


def test_same_input_idempotent(tmp_path: Path):
    """Same input data should return the same thesis_id (idempotent)."""
    tid1 = thesis_store.register(tmp_path, _make_thesis_data())
    tid2 = thesis_store.register(tmp_path, _make_thesis_data())
    assert tid1 == tid2


def test_different_content_different_ids(tmp_path: Path):
    """Different thesis content should produce different IDs."""
    tid1 = thesis_store.register(
        tmp_path,
        _make_thesis_data(
            thesis_statement="thesis A",
        ),
    )
    tid2 = thesis_store.register(
        tmp_path,
        _make_thesis_data(
            thesis_statement="thesis B",
        ),
    )
    assert tid1 != tid2


def test_register_missing_required_field(tmp_path: Path):
    """Missing required field should raise ValueError."""
    with pytest.raises(ValueError, match="Missing required field"):
        thesis_store.register(tmp_path, {"ticker": "AAPL", "thesis_type": "dividend_income"})


def test_register_invalid_thesis_type(tmp_path: Path):
    """Invalid thesis_type should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid thesis_type"):
        thesis_store.register(tmp_path, _make_thesis_data(thesis_type="unknown_type"))


def test_find_by_fingerprint_yaml_fallback(tmp_path: Path):
    """When index is empty, fingerprint lookup should fall back to YAML scan."""
    tid = thesis_store.register(tmp_path, _make_thesis_data())
    # Remove index to simulate empty/corrupt
    index_path = tmp_path / thesis_store.INDEX_FILE
    index_path.write_text('{"version": 1, "theses": {}}')
    # Should still find via YAML fallback
    thesis = thesis_store.get(tmp_path, tid)
    fp = thesis.get("origin_fingerprint")
    found = thesis_store._find_by_fingerprint(tmp_path, fp)
    assert found == tid


def test_register_updates_index(tmp_path: Path):
    """Registration should update _index.json."""
    tid = thesis_store.register(tmp_path, _make_thesis_data())
    index = thesis_store._load_index(tmp_path)
    assert tid in index["theses"]
    assert index["theses"][tid]["ticker"] == "AAPL"
    assert index["theses"][tid]["status"] == "IDEA"


def test_register_sets_next_review_date(tmp_path: Path):
    """Registration should set next_review_date based on interval."""
    tid, thesis = _register_and_get(tmp_path)
    assert thesis["monitoring"]["next_review_date"] is not None


# -- Tests: transition ---------------------------------------------------------


def test_transition_forward_path(tmp_path: Path):
    """IDEA → ENTRY_READY → ACTIVE (via open_position) should log history."""
    tid, _ = _register_and_get(tmp_path)

    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "validated")
    thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-14T10:00:00+00:00")

    thesis = thesis_store.get(tmp_path, tid)
    assert thesis["status"] == "ACTIVE"
    assert len(thesis["status_history"]) == 3
    assert thesis["status_history"][0]["status"] == "IDEA"
    assert thesis["status_history"][1]["status"] == "ENTRY_READY"
    assert thesis["status_history"][2]["status"] == "ACTIVE"


def test_transition_backward_raises(tmp_path: Path):
    """ACTIVE → IDEA should raise ValueError."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "validated")
    thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-14T10:00:00+00:00")

    with pytest.raises(ValueError, match="Cannot transition backward"):
        thesis_store.transition(tmp_path, tid, "IDEA", "oops")


def test_transition_to_active_raises(tmp_path: Path):
    """transition() to ACTIVE should raise, forcing use of open_position()."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")

    with pytest.raises(ValueError, match="Use open_position"):
        thesis_store.transition(tmp_path, tid, "ACTIVE", "bad")


def test_terminate_any_to_invalidated(tmp_path: Path):
    """Any non-terminal status should allow → INVALIDATED via terminate()."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.terminate(tmp_path, tid, "INVALIDATED", "kill criteria triggered")

    thesis = thesis_store.get(tmp_path, tid)
    assert thesis["status"] == "INVALIDATED"


def test_transition_from_terminal_raises(tmp_path: Path):
    """Cannot transition from INVALIDATED."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.terminate(tmp_path, tid, "INVALIDATED", "killed")

    with pytest.raises(ValueError, match="Cannot transition from terminal"):
        thesis_store.transition(tmp_path, tid, "IDEA", "oops")


# -- Tests: open_position ------------------------------------------------------


def test_open_position_sets_entry_and_activates(tmp_path: Path):
    """open_position should set entry data and transition to ACTIVE."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    thesis = thesis_store.open_position(
        tmp_path, tid, 155.0, "2026-03-20T10:00:00+00:00", shares=100
    )

    assert thesis["status"] == "ACTIVE"
    assert thesis["entry"]["actual_price"] == 155.0
    assert thesis["entry"]["actual_date"] == "2026-03-20T10:00:00+00:00"
    assert thesis["position"]["shares"] == 100


def test_open_position_from_idea_raises(tmp_path: Path):
    """open_position from IDEA (not ENTRY_READY) should raise."""
    tid, _ = _register_and_get(tmp_path)
    with pytest.raises(ValueError, match="requires ENTRY_READY"):
        thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-20T10:00:00+00:00")


# -- Tests: terminate ---------------------------------------------------------


def test_terminate_active_invalidated_with_price(tmp_path: Path):
    """terminate ACTIVE→INVALIDATED with price should compute P&L."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00")

    thesis = thesis_store.terminate(
        tmp_path,
        tid,
        "INVALIDATED",
        "kill criteria",
        actual_price=140.0,
        actual_date="2026-03-10T10:00:00+00:00",
    )
    assert thesis["status"] == "INVALIDATED"
    assert thesis["outcome"]["pnl_pct"] == pytest.approx(-6.67, abs=0.01)
    assert thesis["outcome"]["holding_days"] == 9


def test_terminate_active_invalidated_no_price(tmp_path: Path):
    """terminate ACTIVE→INVALIDATED without price should leave P&L null."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00")

    thesis = thesis_store.terminate(tmp_path, tid, "INVALIDATED", "kill criteria")
    assert thesis["status"] == "INVALIDATED"
    assert thesis["outcome"]["pnl_pct"] is None


def test_terminate_idea_invalidated(tmp_path: Path):
    """terminate IDEA→INVALIDATED (no position) should work."""
    tid, _ = _register_and_get(tmp_path)
    thesis = thesis_store.terminate(tmp_path, tid, "INVALIDATED", "not interested")
    assert thesis["status"] == "INVALIDATED"


def test_terminate_closed_delegates(tmp_path: Path):
    """terminate with CLOSED should delegate to close()."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00")

    thesis = thesis_store.terminate(
        tmp_path,
        tid,
        "CLOSED",
        "target_hit",
        actual_price=165.0,
        actual_date="2026-04-01T10:00:00+00:00",
    )
    assert thesis["status"] == "CLOSED"
    assert thesis["outcome"]["pnl_pct"] == 10.0


# -- Tests: attach_position ----------------------------------------------------


def _make_position_report(tmp_path: Path, **overrides):
    """Create a mock position-sizer JSON report."""
    report = {
        "schema_version": "1.0",
        "mode": "shares",
        "parameters": {
            "entry_price": 150.00,
            "stop_price": 142.00,
            "account_size": 100000,
            "risk_pct": 1.0,
        },
        "calculations": {
            "fixed_fractional": {"method": "fixed_fractional", "shares": 125},
        },
        "final_recommended_shares": 125,
        "final_position_value": 18750.00,
        "final_risk_dollars": 1000.00,
        "final_risk_pct": 0.01,
    }
    report.update(overrides)
    report_path = tmp_path / "position_report.json"
    report_path.write_text(json.dumps(report))
    return str(report_path)


def test_attach_position_populates_section(tmp_path: Path):
    """attach_position should populate thesis.position with raw_source."""
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir)
    report_path = _make_position_report(tmp_path)

    thesis = thesis_store.attach_position(state_dir, tid, report_path)

    assert thesis["position"] is not None
    assert thesis["position"]["shares"] == 125
    assert thesis["position"]["position_value"] == 18750.00
    assert thesis["position"]["risk_dollars"] == 1000.00
    assert thesis["position"]["raw_source"]["skill"] == "position-sizer"
    assert thesis["position"]["raw_source"]["fields"]["final_recommended_shares"] == 125


def test_attach_position_mismatched_entry_raises(tmp_path: Path):
    """attach_position with wrong expected_entry should raise ValueError."""
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir)
    report_path = _make_position_report(tmp_path)

    with pytest.raises(ValueError, match="Entry price mismatch"):
        thesis_store.attach_position(state_dir, tid, report_path, expected_entry=999.99)


def test_attach_position_budget_mode_raises(tmp_path: Path):
    """attach_position with budget mode report should raise ValueError."""
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir)
    report_path = _make_position_report(tmp_path, mode="budget")

    with pytest.raises(ValueError, match="mode is 'budget'"):
        thesis_store.attach_position(state_dir, tid, report_path)


# -- Tests: close --------------------------------------------------------------


def test_attach_position_atr_based_method(tmp_path: Path):
    """attach_position should detect atr_based sizing method."""
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir)
    report = {
        "schema_version": "1.0",
        "mode": "shares",
        "parameters": {"entry_price": 150.00, "stop_price": 142.00},
        "calculations": {
            "fixed_fractional": None,
            "atr_based": {"method": "atr_based", "shares": 100, "stop_price": 142.00},
            "kelly": None,
        },
        "final_recommended_shares": 100,
        "final_position_value": 15000.00,
        "final_risk_dollars": 800.00,
        "final_risk_pct": 0.008,
    }
    report_path = tmp_path / "atr_report.json"
    report_path.write_text(json.dumps(report))

    thesis = thesis_store.attach_position(state_dir, tid, str(report_path))
    assert thesis["position"]["sizing_method"] == "atr_based"


def test_attach_position_kelly_method(tmp_path: Path):
    """attach_position should detect kelly sizing method."""
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir)
    report = {
        "schema_version": "1.0",
        "mode": "shares",
        "parameters": {"entry_price": 150.00, "stop_price": 142.00},
        "calculations": {
            "fixed_fractional": None,
            "atr_based": None,
            "kelly": {"method": "kelly", "kelly_pct": 10.0, "half_kelly_pct": 5.0},
        },
        "final_recommended_shares": 80,
        "final_position_value": 12000.00,
        "final_risk_dollars": 640.00,
        "final_risk_pct": 0.0064,
    }
    report_path = tmp_path / "kelly_report.json"
    report_path.write_text(json.dumps(report))

    thesis = thesis_store.attach_position(state_dir, tid, str(report_path))
    assert thesis["position"]["sizing_method"] == "kelly"


def test_close_computes_pnl_and_holding_days(tmp_path: Path):
    """close() should compute pnl_dollars, pnl_pct, and holding_days."""
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir)

    # Advance to ACTIVE via open_position
    thesis_store.transition(state_dir, tid, "ENTRY_READY", "validated")
    thesis_store.open_position(state_dir, tid, 150.00, "2026-03-01T10:00:00+00:00")

    # Attach position for pnl_dollars calculation
    report_path = _make_position_report(tmp_path)
    thesis_store.attach_position(state_dir, tid, report_path)

    # Close
    thesis = thesis_store.close(
        state_dir,
        tid,
        exit_reason="target_hit",
        actual_price=165.00,
        actual_date="2026-04-01T10:00:00+00:00",
    )

    assert thesis["status"] == "CLOSED"
    assert thesis["outcome"]["pnl_pct"] == 10.0  # (165-150)/150 * 100
    assert thesis["outcome"]["pnl_dollars"] == 1875.0  # 15 * 125 shares
    assert thesis["outcome"]["holding_days"] == 31
    assert thesis["exit"]["exit_reason"] == "target_hit"


def test_close_non_active_raises(tmp_path: Path):
    """close() on non-ACTIVE thesis should raise ValueError."""
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir)

    with pytest.raises(ValueError, match="Can only close ACTIVE"):
        thesis_store.close(state_dir, tid, "manual", 160.0, "2026-04-01T00:00:00+00:00")


# -- Tests: schema validation --------------------------------------------------


def test_close_with_invalid_exit_reason_fails(tmp_path: Path):
    """close() with invalid exit_reason should fail validation."""
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir)
    thesis_store.transition(state_dir, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(state_dir, tid, 150.0, "2026-03-01T10:00:00+00:00")

    with pytest.raises(ValueError):
        thesis_store.close(state_dir, tid, "banana", 160.0, "2026-04-01T00:00:00+00:00")


def test_register_without_origin_fails(tmp_path: Path):
    """Registering without origin should fail early validation."""
    data = {
        "ticker": "AAPL",
        "thesis_type": "dividend_income",
        "thesis_statement": "test thesis",
        # no origin
    }
    # register() validates origin sub-fields before fingerprint check
    with pytest.raises(ValueError, match="origin.skill"):
        thesis_store.register(tmp_path, data)


def test_exit_date_before_entry_date_fails(tmp_path: Path):
    """close() with exit_date < entry_date should fail validation."""
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir)
    thesis_store.transition(state_dir, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(state_dir, tid, 150.0, "2026-04-01T10:00:00+00:00")

    with pytest.raises(ValueError, match="exit.actual_date must be >= entry.actual_date"):
        thesis_store.close(state_dir, tid, "manual", 155.0, "2026-03-01T10:00:00+00:00")


# -- Tests: source date --------------------------------------------------------


def test_register_with_source_date(tmp_path: Path):
    """_source_date should set thesis_id, created_at, status_history, next_review from source."""
    data = _make_thesis_data(_source_date="2026-02-20")
    tid = thesis_store.register(tmp_path, data)
    thesis = thesis_store.get(tmp_path, tid)

    # thesis_id should contain 20260220, not today
    assert "_20260220_" in tid
    # created_at should reflect source date
    assert thesis["created_at"].startswith("2026-02-20")
    # updated_at should be now (not source date)
    assert not thesis["updated_at"].startswith("2026-02-20")
    # status_history[0].at should use source date, not now
    assert thesis["status_history"][0]["at"].startswith("2026-02-20")
    # next_review_date should be source_date + 30 days = 2026-03-22
    assert thesis["monitoring"]["next_review_date"] == "2026-03-22"


def test_register_without_source_date_uses_today(tmp_path: Path):
    """Without _source_date, register uses today's date."""
    data = _make_thesis_data()
    tid = thesis_store.register(tmp_path, data)
    # Should not contain a past date
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    assert f"_{today}_" in tid


# -- Tests: query and list -----------------------------------------------------


def test_query_by_date_range(tmp_path: Path):
    """query(date_from=, date_to=) should filter by created_at."""
    thesis_store.register(tmp_path, _make_thesis_data(ticker="OLD", _source_date="2026-01-15"))
    thesis_store.register(tmp_path, _make_thesis_data(ticker="MID", _source_date="2026-02-15"))
    thesis_store.register(tmp_path, _make_thesis_data(ticker="NEW", _source_date="2026-03-15"))

    # Only MID
    results = thesis_store.query(tmp_path, date_from="2026-02-01", date_to="2026-02-28")
    tickers = [r["ticker"] for r in results]
    assert "MID" in tickers
    assert "OLD" not in tickers
    assert "NEW" not in tickers

    # MID + NEW
    results = thesis_store.query(tmp_path, date_from="2026-02-01")
    tickers = [r["ticker"] for r in results]
    assert "MID" in tickers
    assert "NEW" in tickers
    assert "OLD" not in tickers


def test_query_by_ticker(tmp_path: Path):
    """query(ticker=) should filter correctly."""
    thesis_store.register(tmp_path, _make_thesis_data(ticker="AAPL"))
    thesis_store.register(tmp_path, _make_thesis_data(ticker="MSFT"))

    results = thesis_store.query(tmp_path, ticker="AAPL")
    assert len(results) == 1
    assert results[0]["ticker"] == "AAPL"


def test_list_review_due(tmp_path: Path):
    """list_review_due should return theses with due dates."""
    tid = thesis_store.register(tmp_path, _make_thesis_data())
    # Override next_review_date to past
    thesis_store.update(
        tmp_path,
        tid,
        {
            "monitoring": {"next_review_date": "2026-01-01"},
        },
    )

    due = thesis_store.list_review_due(tmp_path, "2026-03-14")
    assert len(due) == 1
    assert due[0]["thesis_id"] == tid

    not_due = thesis_store.list_review_due(tmp_path, "2025-12-31")
    assert len(not_due) == 0


def test_list_active(tmp_path: Path):
    """list_active should return only ACTIVE theses."""
    tid1 = thesis_store.register(tmp_path, _make_thesis_data(ticker="AAPL"))
    thesis_store.register(tmp_path, _make_thesis_data(ticker="MSFT"))
    thesis_store.transition(tmp_path, tid1, "ENTRY_READY", "ok")
    thesis_store.open_position(tmp_path, tid1, 150.0, "2026-03-14T10:00:00+00:00")

    active = thesis_store.list_active(tmp_path)
    assert len(active) == 1
    assert active[0]["ticker"] == "AAPL"


# -- Tests: mark_reviewed ------------------------------------------------------


def test_mark_reviewed_updates_dates(tmp_path: Path):
    """mark_reviewed should update last/next review dates."""
    tid, _ = _register_and_get(tmp_path)
    thesis = thesis_store.mark_reviewed(tmp_path, tid, review_date="2026-04-01", outcome="OK")

    assert thesis["monitoring"]["last_review_date"] == "2026-04-01"
    assert thesis["monitoring"]["next_review_date"] == "2026-05-01"
    assert thesis["monitoring"]["review_status"] == "OK"


def test_mark_reviewed_escalation(tmp_path: Path):
    """mark_reviewed with WARN outcome should set review_status."""
    tid, _ = _register_and_get(tmp_path)
    thesis = thesis_store.mark_reviewed(tmp_path, tid, review_date="2026-04-01", outcome="WARN")

    assert thesis["monitoring"]["review_status"] == "WARN"


def test_mark_reviewed_notes_to_alerts(tmp_path: Path):
    """mark_reviewed with notes should append to alerts."""
    tid, _ = _register_and_get(tmp_path)
    thesis = thesis_store.mark_reviewed(
        tmp_path,
        tid,
        review_date="2026-04-01",
        outcome="REVIEW",
        notes="FCF coverage dropped below 1.5x",
    )

    assert len(thesis["monitoring"]["alerts"]) == 1
    assert (
        "[2026-04-01] REVIEW: FCF coverage dropped below 1.5x" in thesis["monitoring"]["alerts"][0]
    )


def test_mark_reviewed_terminal_raises(tmp_path: Path):
    """mark_reviewed on CLOSED thesis should raise ValueError."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.terminate(tmp_path, tid, "INVALIDATED", "killed")

    with pytest.raises(ValueError, match="Cannot review terminal"):
        thesis_store.mark_reviewed(tmp_path, tid, review_date="2026-04-01")


def test_mark_reviewed_next_based_on_review_date(tmp_path: Path):
    """next_review should be review_date + interval, not now + interval."""
    tid, _ = _register_and_get(tmp_path)
    thesis = thesis_store.mark_reviewed(tmp_path, tid, review_date="2026-01-15")
    # 2026-01-15 + 30 = 2026-02-14
    assert thesis["monitoring"]["next_review_date"] == "2026-02-14"


# -- Tests: rebuild_index / validate_state ------------------------------------


def test_rebuild_index_from_scratch(tmp_path: Path):
    """rebuild_index should recreate index from YAML files."""
    tid = thesis_store.register(tmp_path, _make_thesis_data())
    # Delete index
    (tmp_path / thesis_store.INDEX_FILE).unlink()
    # Rebuild
    idx = thesis_store.rebuild_index(tmp_path)
    assert tid in idx["theses"]
    assert idx["theses"][tid]["ticker"] == "AAPL"


def test_rebuild_index_skips_corrupt(tmp_path: Path):
    """rebuild_index should skip corrupt YAML files."""
    thesis_store.register(tmp_path, _make_thesis_data())
    # Create corrupt file
    (tmp_path / "th_bad_pvt_20260314_0000.yaml").write_text("{{invalid yaml")
    idx = thesis_store.rebuild_index(tmp_path)
    assert len(idx["theses"]) == 1  # only the valid one


def test_rebuild_index_skips_schema_invalid(tmp_path: Path):
    """rebuild_index should skip YAML files that fail schema validation."""
    import yaml

    tid = thesis_store.register(tmp_path, _make_thesis_data())
    thesis = thesis_store.get(tmp_path, tid)

    # Create a schema-invalid thesis YAML (bogus status)
    bad = dict(thesis)
    bad["thesis_id"] = "th_bad_div_20260314_0000"
    bad["status"] = "BOGUS"
    bad_path = tmp_path / "th_bad_div_20260314_0000.yaml"
    bad_path.write_text(yaml.dump(bad, default_flow_style=False))

    idx = thesis_store.rebuild_index(tmp_path)
    assert tid in idx["theses"]
    assert "th_bad_div_20260314_0000" not in idx["theses"]


def test_validate_state_detects_missing(tmp_path: Path):
    """validate_state should detect files missing from index."""
    tid = thesis_store.register(tmp_path, _make_thesis_data())
    # Remove from index but keep YAML
    index = thesis_store._load_index(tmp_path)
    del index["theses"][tid]
    thesis_store._save_index(tmp_path, index)

    result = thesis_store.validate_state(tmp_path)
    assert not result["ok"]
    assert tid in result["missing_in_index"]


def test_validate_state_detects_orphan(tmp_path: Path):
    """validate_state should detect index entries without YAML files."""
    tid = thesis_store.register(tmp_path, _make_thesis_data())
    # Remove YAML but keep index entry
    (tmp_path / f"{tid}.yaml").unlink()

    result = thesis_store.validate_state(tmp_path)
    assert not result["ok"]
    assert tid in result["orphaned_in_index"]


# -- Tests: link_report -------------------------------------------------------


def test_link_report(tmp_path: Path):
    """link_report should append to linked_reports."""
    tid, _ = _register_and_get(tmp_path)
    thesis = thesis_store.link_report(
        tmp_path,
        tid,
        skill="us-stock-analysis",
        file="reports/aapl_analysis.md",
        date="2026-03-14",
    )
    assert len(thesis["linked_reports"]) == 1
    assert thesis["linked_reports"][0]["skill"] == "us-stock-analysis"


# -- Tests: FormatChecker (Step 1) -------------------------------------------


def test_open_position_bad_date_format_fails(tmp_path: Path):
    """open_position with invalid date format should fail validation."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")

    with pytest.raises(ValueError):
        thesis_store.open_position(tmp_path, tid, 150.0, "not-a-date")


def test_format_checker_rejects_no_timezone(tmp_path: Path):
    """date-time without timezone offset should fail validation."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")

    with pytest.raises(ValueError):
        thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-14T09:00:00")


def test_format_checker_rejects_space_separator(tmp_path: Path):
    """date-time with space separator should fail validation."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")

    with pytest.raises(ValueError):
        thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-14 09:00:00+00:00")


def test_close_bad_date_format_fails(tmp_path: Path):
    """close() with invalid date format should fail validation."""
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir)
    thesis_store.transition(state_dir, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(state_dir, tid, 150.0, "2026-03-01T10:00:00+00:00")

    with pytest.raises(ValueError):
        thesis_store.close(state_dir, tid, "manual", 160.0, "not-a-date")


# -- Tests: transition terminal block (Step 2) --------------------------------


def test_transition_to_closed_raises(tmp_path: Path):
    """transition() to CLOSED should raise — use close() instead."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-14T10:00:00+00:00")

    with pytest.raises(ValueError, match="terminal status"):
        thesis_store.transition(tmp_path, tid, "CLOSED", "bad")


def test_transition_to_invalidated_raises(tmp_path: Path):
    """transition() to INVALIDATED should raise — use terminate() instead."""
    tid, _ = _register_and_get(tmp_path)

    with pytest.raises(ValueError, match="terminal status"):
        thesis_store.transition(tmp_path, tid, "INVALIDATED", "bad")


# -- Tests: INVALIDATED invariant (Step 3) ------------------------------------


def test_terminate_invalidated_exit_before_entry_fails(tmp_path: Path):
    """INVALIDATED with exit_date < entry_date should fail validation."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-10T10:00:00+00:00")

    with pytest.raises(ValueError, match="exit.actual_date must be >= entry.actual_date"):
        thesis_store.terminate(
            tmp_path,
            tid,
            "INVALIDATED",
            "kill criteria",
            actual_price=140.0,
            actual_date="2026-03-01T10:00:00+00:00",  # before entry
        )


def test_terminate_invalidated_holding_days_nonnegative(tmp_path: Path):
    """INVALIDATED with valid dates should have non-negative holding_days."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00")

    thesis = thesis_store.terminate(
        tmp_path,
        tid,
        "INVALIDATED",
        "kill criteria",
        actual_price=140.0,
        actual_date="2026-03-10T10:00:00+00:00",
    )
    assert thesis["outcome"]["holding_days"] >= 0


# -- Tests: Fingerprint improvements (Step 4) --------------------------------


def test_fingerprint_ignores_output_file(tmp_path: Path):
    """Different output_file values should produce same thesis (same fingerprint)."""
    data1 = _make_thesis_data(origin={"skill": "test-skill", "output_file": "file_v1.json"})
    data2 = _make_thesis_data(origin={"skill": "test-skill", "output_file": "file_v2.json"})

    tid1 = thesis_store.register(tmp_path, data1)
    tid2 = thesis_store.register(tmp_path, data2)
    assert tid1 == tid2


def test_register_invalid_input_not_masked_by_idempotency(tmp_path: Path):
    """Invalid input should raise even if fingerprint matches existing thesis."""
    thesis_store.register(tmp_path, _make_thesis_data())

    # Same content but missing origin.output_file — must not return existing ID
    bad_data = _make_thesis_data()
    bad_data["origin"] = {"skill": "test-skill"}  # missing output_file

    with pytest.raises(ValueError, match="origin.output_file"):
        thesis_store.register(tmp_path, bad_data)


def test_register_schema_violation_not_masked_by_idempotency(tmp_path: Path):
    """Schema violation should raise even when fingerprint matches existing thesis."""
    thesis_store.register(tmp_path, _make_thesis_data())

    # Same fingerprint-relevant content, but confidence_score > 1.0 (schema max)
    bad_data = _make_thesis_data(confidence_score=999)

    with pytest.raises(ValueError, match="validation failed"):
        thesis_store.register(tmp_path, bad_data)


def test_fingerprint_fallback_partial_index(tmp_path: Path):
    """YAML scan should prevent duplicates even when index has partial entries."""
    data_a = _make_thesis_data(ticker="AAPL")
    data_b = _make_thesis_data(ticker="MSFT")

    thesis_store.register(tmp_path, data_a)
    tid_b = thesis_store.register(tmp_path, data_b)

    # Remove tid_b from index but keep YAML
    index = thesis_store._load_index(tmp_path)
    del index["theses"][tid_b]
    thesis_store._save_index(tmp_path, index)

    # Re-register same data for B — should find via YAML fallback
    tid_b2 = thesis_store.register(tmp_path, data_b)
    assert tid_b2 == tid_b


# -- Tests: validate_state schema-aware (Step 5) ------------------------------


def test_validate_state_detects_schema_error(tmp_path: Path):
    """validate_state should report schema-invalid YAML files."""
    import yaml

    tid = thesis_store.register(tmp_path, _make_thesis_data())
    thesis = thesis_store.get(tmp_path, tid)

    # Corrupt the thesis: set an invalid status
    thesis["status"] = "BOGUS"
    yaml_path = tmp_path / f"{tid}.yaml"
    yaml_path.write_text(yaml.dump(thesis, default_flow_style=False))

    result = thesis_store.validate_state(tmp_path)
    assert not result["ok"]
    assert len(result["schema_errors"]) == 1
    assert result["schema_errors"][0]["thesis_id"] == tid


# -- Tests: Backfill timestamps (Step 6) --------------------------------------


def test_open_position_backfill_event_date(tmp_path: Path):
    """event_date should override status_history.at for backfilling."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")

    # Use a future date that is after the IDEA/ENTRY_READY timestamps
    backfill_date = "2027-06-15T10:00:00+00:00"
    thesis = thesis_store.open_position(
        tmp_path, tid, 150.0, "2027-06-15T10:00:00+00:00", event_date=backfill_date
    )

    active_entry = thesis["status_history"][-1]
    assert active_entry["status"] == "ACTIVE"
    assert active_entry["at"] == backfill_date


# -- Tests: Blocker #1 — Cross-timezone date comparison -----------------------


def test_cross_timezone_exit_after_entry_succeeds(tmp_path: Path):
    """exit in UTC is AFTER entry in JST (real time) — should succeed."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    # entry: 2026-03-01 00:30 JST = 2026-02-28 15:30 UTC
    thesis_store.open_position(tmp_path, tid, 100.0, "2026-03-01T00:30:00+09:00")
    # exit: 2026-02-28 23:00 UTC — this is AFTER entry in real time
    thesis = thesis_store.close(tmp_path, tid, "target_hit", 110.0, "2026-02-28T23:00:00+00:00")
    assert thesis["status"] == "CLOSED"
    assert thesis["outcome"]["holding_days"] == 0


def test_cross_timezone_exit_before_entry_fails(tmp_path: Path):
    """exit in UTC is BEFORE entry in JST (real time) — should fail."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    # entry: 2026-03-01 00:30 JST = 2026-02-28 15:30 UTC
    thesis_store.open_position(tmp_path, tid, 100.0, "2026-03-01T00:30:00+09:00")
    # exit: 2026-02-28 10:00 UTC — this is BEFORE entry in real time
    with pytest.raises(ValueError, match="exit.actual_date must be >= entry.actual_date"):
        thesis_store.close(tmp_path, tid, "stop_hit", 95.0, "2026-02-28T10:00:00+00:00")


# -- Tests: Blocker #2 — Protected identity fields in update() ---------------


def test_update_ticker_rejected(tmp_path: Path):
    """update() must reject ticker changes."""
    tid, _ = _register_and_get(tmp_path)
    with pytest.raises(ValueError, match="Cannot update protected field: ticker"):
        thesis_store.update(tmp_path, tid, {"ticker": "MSFT"})


def test_update_thesis_type_rejected(tmp_path: Path):
    """update() must reject thesis_type changes."""
    tid, _ = _register_and_get(tmp_path)
    with pytest.raises(ValueError, match="Cannot update protected field: thesis_type"):
        thesis_store.update(tmp_path, tid, {"thesis_type": "pivot_breakout"})


def test_update_origin_fingerprint_rejected(tmp_path: Path):
    """update() must reject origin_fingerprint changes."""
    tid, _ = _register_and_get(tmp_path)
    with pytest.raises(ValueError, match="Cannot update protected field: origin_fingerprint"):
        thesis_store.update(tmp_path, tid, {"origin_fingerprint": "hack"})


# -- Tests: Blocker #3 — validate_state full index comparison -----------------


def test_validate_state_detects_review_date_drift(tmp_path: Path):
    """validate_state() must detect next_review_date drift in index."""
    tid, _ = _register_and_get(tmp_path)

    # Tamper with _index.json next_review_date
    index_path = tmp_path / "_index.json"
    with open(index_path) as f:
        index = json.load(f)
    index["theses"][tid]["next_review_date"] = "2099-01-01"
    with open(index_path, "w") as f:
        json.dump(index, f)

    result = thesis_store.validate_state(tmp_path)
    assert not result["ok"]
    mismatches = [m for m in result["field_mismatches"] if m["field"] == "next_review_date"]
    assert len(mismatches) == 1
    assert mismatches[0]["index_value"] == "2099-01-01"


# -- Tests: Medium #4 — status_history monotonic ordering ---------------------


def test_event_date_before_previous_history_fails(tmp_path: Path):
    """open_position with event_date before IDEA.at should fail validation."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")

    # IDEA.at and ENTRY_READY.at are recent (2026-03-16ish)
    # Try to open_position with event_date far in the past
    with pytest.raises(ValueError, match="status_history.*is before"):
        thesis_store.open_position(
            tmp_path,
            tid,
            150.0,
            "2020-01-01T10:00:00+00:00",
            event_date="2020-01-01T10:00:00+00:00",
        )


# -- Tests: Strict date format validation -------------------------------------


def test_update_non_padded_date_rejected(tmp_path: Path):
    """update() must reject non-zero-padded dates like '2026-1-1'."""
    tid, _ = _register_and_get(tmp_path)
    with pytest.raises(ValueError, match="not a 'date'|date must be YYYY-MM-DD"):
        thesis_store.update(tmp_path, tid, {"monitoring": {"next_review_date": "2026-1-1"}})


def test_link_report_non_padded_date_rejected(tmp_path: Path):
    """link_report() must reject non-zero-padded dates."""
    tid, _ = _register_and_get(tmp_path)
    with pytest.raises(ValueError, match="not a 'date'|date must be YYYY-MM-DD"):
        thesis_store.link_report(tmp_path, tid, "test-skill", "report.md", "2026-1-1")


def test_list_review_due_uses_parsed_date(tmp_path: Path):
    """list_review_due() should use parsed date comparison, not string."""
    tid, _ = _register_and_get(tmp_path)

    # Verify the thesis shows up as due when as_of is far in the future
    results = thesis_store.list_review_due(tmp_path, "2099-12-31")
    assert any(r["thesis_id"] == tid for r in results)

    # Verify the thesis does NOT show up when as_of is far in the past
    results = thesis_store.list_review_due(tmp_path, "2000-01-01")
    assert not any(r["thesis_id"] == tid for r in results)


# -- Tests: fractional shares --------------------------------------------------


def test_fractional_shares_end_to_end(tmp_path: Path):
    """open_position with fractional shares → close P&L uses the float qty."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00", shares=7.86)
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["shares"] == 7.86
    assert isinstance(t["position"]["shares"], float)

    thesis_store.close(tmp_path, tid, "target_hit", 165.0, "2026-03-20T10:00:00+00:00")
    t = thesis_store.get(tmp_path, tid)
    assert t["outcome"]["pnl_dollars"] == round((165.0 - 150.0) * 7.86, 2)


@pytest.mark.parametrize("bad_shares", [0, -1, -0.5])
def test_schema_rejects_nonpositive_shares(tmp_path: Path, bad_shares):
    """exclusiveMinimum:0 — zero and negatives are rejected on save."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    with pytest.raises(ValueError, match="Schema validation failed"):
        thesis_store.open_position(
            tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00", shares=bad_shares
        )


def test_schema_accepts_integer_shares_backward_compat(tmp_path: Path):
    """Existing integer-shares theses stay valid (number ⊇ integer)."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00", shares=100)
    t = thesis_store.get(tmp_path, tid)  # get() implies schema-valid
    assert t["position"]["shares"] == 100


# -- Tests: lifecycle CLI (main(argv)) ----------------------------------------


def test_cli_main_lifecycle_full_sequence(tmp_path: Path, capsys):
    """register (lib) → transition → open-position → close all via main([...])
    with a date-only --actual-date that persists as a tz-aware date-time."""
    # _source_date backdates the IDEA stamp so the fully backdated chain
    # (IDEA == ENTRY_READY == ACTIVE == 2026-03-01) stays monotonic.
    tid, _ = _register_and_get(tmp_path, _source_date="2026-03-01")
    sd = str(tmp_path)

    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "transition",
                tid,
                "ENTRY_READY",
                "--reason",
                "validated",
                "--event-date",
                "2026-03-01",
            ]
        )
        == 0
    )
    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "150.0",
                "--actual-date",
                "2026-03-01",
                "--shares",
                "7.86",
                "--event-date",
                "2026-03-01",
            ]
        )
        == 0
    )
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "ACTIVE"
    assert t["position"]["shares"] == 7.86
    # date-only CLI arg widened to tz-aware date-time
    assert t["entry"]["actual_date"] == "2026-03-01T00:00:00+00:00"

    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "close",
                tid,
                "--exit-reason",
                "target_hit",
                "--actual-price",
                "165.0",
                "--actual-date",
                "2026-03-20",
            ]
        )
        == 0
    )
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "CLOSED"
    assert t["outcome"]["pnl_dollars"] == round((165.0 - 150.0) * 7.86, 2)


def test_cli_main_attach_and_terminate(tmp_path: Path):
    """attach-position + terminate INVALIDATED via main([...])."""
    tid, _ = _register_and_get(tmp_path)
    sd = str(tmp_path)
    report = _make_position_report(tmp_path)

    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "attach-position",
                tid,
                "--report",
                report,
            ]
        )
        == 0
    )
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["shares"] == 125

    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "terminate",
                tid,
                "--terminal-status",
                "INVALIDATED",
                "--exit-reason",
                "thesis broke",
            ]
        )
        == 0
    )
    assert thesis_store.get(tmp_path, tid)["status"] == "INVALIDATED"


def test_cli_main_existing_subcommands_regression(tmp_path: Path):
    """The pre-existing subcommands still work through the refactored main()."""
    tid, _ = _register_and_get(tmp_path)
    sd = str(tmp_path)
    assert thesis_store.main(["--state-dir", sd, "list"]) == 0
    assert thesis_store.main(["--state-dir", sd, "get", tid]) == 0
    assert thesis_store.main(["--state-dir", sd, "review-due"]) == 0
    assert thesis_store.main(["--state-dir", sd, "rebuild-index"]) == 0
    assert thesis_store.main(["--state-dir", sd, "doctor"]) == 0
    assert thesis_store.main(["--state-dir", sd, "mark-reviewed", tid]) == 0
    # no subcommand → help, non-zero
    assert thesis_store.main(["--state-dir", sd]) == 1


def test_transition_event_date_backdates_history(tmp_path: Path):
    """transition(event_date=...) stamps status_history.at, not now."""
    tid, _ = _register_and_get(tmp_path, _source_date="2026-03-01")
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "backdated", event_date="2026-03-01")
    t = thesis_store.get(tmp_path, tid)
    assert t["status_history"][1]["at"] == "2026-03-01T00:00:00+00:00"


def test_transition_without_event_date_regression(tmp_path: Path):
    """Existing callers (no event_date) still stamp ~now and pass."""
    tid, _ = _register_and_get(tmp_path)
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    t = thesis_store.get(tmp_path, tid)
    # IDEA stamped at register (~now), ENTRY_READY at ~now → still monotonic
    assert t["status_history"][1]["status"] == "ENTRY_READY"
    assert "T" in t["status_history"][1]["at"]


def test_backdate_monotonicity_negative_control(tmp_path: Path):
    """Without --event-date on transition, a later backdated open_position
    breaks status_history monotonicity (this is WHY transition gained
    event_date)."""
    tid, _ = _register_and_get(tmp_path)  # IDEA @ ~now
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")  # @ ~now
    # Full ISO past timestamp → exercises the monotonicity guard (a bare
    # date-only would fail the date-time FormatChecker first; the CLI layer
    # is what coerces date-only, which is why _coerce_dt exists).
    with pytest.raises(ValueError, match="is before"):
        thesis_store.open_position(
            tmp_path,
            tid,
            150.0,
            "2026-03-01T10:00:00+00:00",
            shares=7.86,
            event_date="2020-01-01T00:00:00+00:00",
        )
