"""Tests for thesis_store.py — CRUD, transitions, and index management."""

import hashlib
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


def _state_file_hash(state_dir, thesis_id: str) -> str:
    """SHA-256 of the on-disk thesis YAML file — for byte-exact
    before/after comparison around a rejected mutation (duplicated here
    from test_thesis_store_futures.py per this suite's self-contained-
    per-file convention; Issue #254)."""
    path = Path(state_dir) / f"{thesis_id}.yaml"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index_file_hash(state_dir) -> str:
    """SHA-256 of the on-disk _index.json file — a rejection must leave
    BOTH the thesis YAML and the index untouched (_save_index() is only
    ever reached after _save_thesis() succeeds)."""
    path = Path(state_dir) / thesis_store.INDEX_FILE
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    index_path.write_text('{"version": 1, "theses": {}}', encoding="utf-8")
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
    report_path.write_text(json.dumps(report), encoding="utf-8")
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
    report_path.write_text(json.dumps(report), encoding="utf-8")

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
    report_path.write_text(json.dumps(report), encoding="utf-8")

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
    (tmp_path / "th_bad_pvt_20260314_0000.yaml").write_text("{{invalid yaml", encoding="utf-8")
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
    bad_path.write_text(yaml.dump(bad, default_flow_style=False), encoding="utf-8")

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
    yaml_path.write_text(yaml.dump(thesis, default_flow_style=False), encoding="utf-8")

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
    with open(index_path, "w", encoding="utf-8") as f:
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


# -- Tests: Issue #254 — equity shares finiteness/sanity validation ----------
# (pre-existing money-critical gap: shares=10**400 crashed close() with an
# uncaught OverflowError; shares=inf silently persisted pnl_dollars: inf.
# _valid_finite_positive() is the SAME huge-int-safe validator #253 added
# for futures multiplier — no new low-level helper needed, just missing
# call sites at the _validate_thesis() chokepoint + output-side P&L guards.)


def test_valid_finite_positive_rejects_bad_shares_values():
    """_valid_finite_positive() in the equity/shares context: huge int,
    inf, nan, non-positive all rejected cleanly (never raises); ordinary
    fractional/integer shares pass through as float."""
    assert thesis_store._valid_finite_positive(10**400) is None  # must not raise
    assert thesis_store._valid_finite_positive(float("inf")) is None
    assert thesis_store._valid_finite_positive(float("-inf")) is None
    assert thesis_store._valid_finite_positive(float("nan")) is None
    assert thesis_store._valid_finite_positive(0) is None
    assert thesis_store._valid_finite_positive(-1) is None
    assert thesis_store._valid_finite_positive(7.86) == 7.86
    assert thesis_store._valid_finite_positive(100) == 100.0


def test_valid_finite_nonneg_allows_zero_but_not_negative():
    """_valid_finite_nonneg() (new for #254): shares_remaining==0 (any
    CLOSED equity thesis) must be accepted, unlike _valid_finite_positive."""
    assert thesis_store._valid_finite_nonneg(0) == 0.0
    assert thesis_store._valid_finite_nonneg(0.0) == 0.0
    assert thesis_store._valid_finite_nonneg(-0.5) is None
    assert thesis_store._valid_finite_nonneg(float("nan")) is None
    assert thesis_store._valid_finite_nonneg(float("inf")) is None
    assert thesis_store._valid_finite_nonneg(10**400) is None  # must not raise


def test_open_position_rejects_huge_shares(tmp_path: Path):
    """Issue #254 (money-critical): shares=10**400 must be rejected with
    a clean ValueError at save time (D1 chokepoint) — the original bug
    crashed close() later with an uncaught OverflowError instead."""
    tid, _ = _register_and_get(tmp_path, ticker="EQHUGE")
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    before = _index_file_hash(tmp_path)
    with pytest.raises(ValueError, match="equity thesis position.shares is invalid"):
        thesis_store.open_position(
            tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00", shares=10**400
        )
    assert _index_file_hash(tmp_path) == before
    assert thesis_store.get(tmp_path, tid)["status"] == "ENTRY_READY"


def test_open_position_rejects_infinite_shares(tmp_path: Path):
    """Issue #254: shares=inf must be rejected — the original bug
    silently persisted a thesis that could open but never correctly
    close (pnl_dollars: inf)."""
    tid, _ = _register_and_get(tmp_path, ticker="EQINF")
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    with pytest.raises(ValueError, match="equity thesis position.shares is invalid"):
        thesis_store.open_position(
            tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00", shares=float("inf")
        )
    assert thesis_store.get(tmp_path, tid)["status"] == "ENTRY_READY"


def test_open_position_rejects_nan_shares(tmp_path: Path):
    """Issue #254: shares=nan must be rejected."""
    tid, _ = _register_and_get(tmp_path, ticker="EQNAN")
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    with pytest.raises(ValueError, match="equity thesis position.shares is invalid"):
        thesis_store.open_position(
            tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00", shares=float("nan")
        )
    assert thesis_store.get(tmp_path, tid)["status"] == "ENTRY_READY"


def test_open_position_rejects_shares_above_max_sanity_bound(tmp_path: Path):
    """Issue #254: a finite, ordinary-looking float just above
    _MAX_SHARES is rejected — the sanity cap, not just the finiteness
    check."""
    tid, _ = _register_and_get(tmp_path, ticker="EQCAPPLUS")
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    with pytest.raises(ValueError, match="exceeds the maximum sanity bound"):
        thesis_store.open_position(
            tmp_path,
            tid,
            150.0,
            "2026-03-01T10:00:00+00:00",
            shares=thesis_store._MAX_SHARES + 1,
        )


def test_open_position_accepts_shares_at_max_sanity_bound(tmp_path: Path):
    """Issue #254: _MAX_SHARES itself is a valid (if absurd) share count —
    the boundary is inclusive."""
    tid, _ = _register_and_get(tmp_path, ticker="EQCAPEXACT")
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    t = thesis_store.open_position(
        tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00", shares=thesis_store._MAX_SHARES
    )
    assert t["position"]["shares"] == thesis_store._MAX_SHARES


def test_open_position_accepts_fractional_shares_below_cap(tmp_path: Path):
    """Regression pin: ordinary fractional shares (0.5, 7.86) are
    unaffected by the new cap/finiteness checks."""
    tid, _ = _register_and_get(tmp_path, ticker="EQFRACOK")
    thesis_store.transition(tmp_path, tid, "ENTRY_READY", "ok")
    t = thesis_store.open_position(tmp_path, tid, 150.0, "2026-03-01T10:00:00+00:00", shares=0.5)
    assert t["position"]["shares"] == 0.5


def test_attach_position_rejects_huge_shares_in_report(tmp_path: Path):
    """Issue #254: attach_position() reads the position-sizer report with
    a plain (unhardened) json.load() and never validated
    final_recommended_shares before this fix — the D1 chokepoint at
    _save_thesis() closes this "for free" since attach also ends there."""
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir, ticker="EQATTACHHUGE")
    report_path = _make_position_report(tmp_path, final_recommended_shares=10**400)
    before = _state_file_hash(state_dir, tid)
    with pytest.raises(ValueError, match="equity thesis position.shares is invalid"):
        thesis_store.attach_position(state_dir, tid, report_path)
    assert _state_file_hash(state_dir, tid) == before


def test_attach_position_rejects_infinite_shares_in_report(tmp_path: Path):
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir, ticker="EQATTACHINF")
    report_path = _make_position_report(tmp_path, final_recommended_shares=float("inf"))
    with pytest.raises(ValueError, match="equity thesis position.shares is invalid"):
        thesis_store.attach_position(state_dir, tid, report_path)


def test_attach_position_rejects_nan_shares_in_report(tmp_path: Path):
    state_dir = tmp_path / "theses"
    tid, _ = _register_and_get(state_dir, ticker="EQATTACHNAN")
    report_path = _make_position_report(tmp_path, final_recommended_shares=float("nan"))
    with pytest.raises(ValueError, match="equity thesis position.shares is invalid"):
        thesis_store.attach_position(state_dir, tid, report_path)


def test_trim_rejects_huge_shares_sold(tmp_path: Path):
    """Issue #254: trim(shares_sold=10**400) is already rejected by the
    existing comparison-based range guard (0 < shares_sold <= remaining
    never raises OverflowError for huge ints — verified empirically),
    pinned here as a regression guard against that safety property."""
    tid = _active_with_shares(tmp_path, 10, ticker="EQTRIMHUGE")
    before = _state_file_hash(tmp_path, tid)
    with pytest.raises(ValueError, match="must be > 0 and"):
        thesis_store.trim(tmp_path, tid, 10**400, 120.0, "2026-05-10")
    assert _state_file_hash(tmp_path, tid) == before
    assert thesis_store.get(tmp_path, tid)["position"]["shares_remaining"] == 10


def test_trim_rejects_infinite_shares_sold(tmp_path: Path):
    tid = _active_with_shares(tmp_path, 10, ticker="EQTRIMINF")
    with pytest.raises(ValueError, match="must be > 0 and"):
        thesis_store.trim(tmp_path, tid, float("inf"), 120.0, "2026-05-10")
    assert thesis_store.get(tmp_path, tid)["position"]["shares_remaining"] == 10


def test_trim_rejects_nan_shares_sold(tmp_path: Path):
    tid = _active_with_shares(tmp_path, 10, ticker="EQTRIMNAN")
    with pytest.raises(ValueError, match="must be > 0 and"):
        thesis_store.trim(tmp_path, tid, float("nan"), 120.0, "2026-05-10")
    assert thesis_store.get(tmp_path, tid)["position"]["shares_remaining"] == 10


def test_close_rejects_overflowing_pnl_with_shares_at_cap(tmp_path: Path):
    """Issue #254 test#7: shares at exactly _MAX_SHARES (a legitimately-
    accepted, cap-respecting value) combined with an extreme (but
    individually finite — actual_price input validation is explicitly
    out of scope for #254, tracked as a follow-up) price makes the
    PRODUCT overflow to inf. Verified via computation:
    round(1e300 * 1e12, 2) == inf. close() must reject before persisting,
    leaving outcome.pnl_dollars null and the file byte-unchanged."""
    tid, _ = _register_and_get(tmp_path, ticker="EQOVERFLOWCAP", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    thesis_store.open_position(
        tmp_path,
        tid,
        1.0,
        "2026-05-01T00:00:00+00:00",
        shares=thesis_store._MAX_SHARES,
        event_date="2026-05-01T00:00:00+00:00",
    )
    before = _state_file_hash(tmp_path, tid)
    before_index = _index_file_hash(tmp_path)
    with pytest.raises(ValueError, match="not finite"):
        thesis_store.close(tmp_path, tid, "manual", 1e300, "2026-05-10T00:00:00+00:00")
    assert _state_file_hash(tmp_path, tid) == before
    assert _index_file_hash(tmp_path) == before_index
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "ACTIVE"
    assert t["outcome"]["pnl_dollars"] is None


def test_close_rejects_disk_corrupted_infinite_shares_d4_only(tmp_path: Path):
    """Issue #254 test#7b (P1 D4): a thesis whose shares became `.inf` on
    disk WITHOUT ever going through open_position()/attach_position() (a
    hand-edited file, or one written before this fix) is never re-
    validated on READ — _load_thesis() is a plain yaml.safe_load(), and
    _validate_thesis() (D1) only runs from _save_thesis() on WRITE. D4
    (the output-side guard inside close()/_finalize_outcome()) is the
    ONLY thing standing between this file and a crash/silent-inf
    persistence. Confirms D1 is NOT reachable on this path and D4 alone
    rejects it, leaving the file byte-unchanged."""
    import yaml

    tid = _active_with_shares(tmp_path, 10, ticker="EQDISKINF")
    thesis = thesis_store.get(tmp_path, tid)
    thesis["position"]["shares"] = float("inf")
    thesis["position"]["shares_remaining"] = float("inf")
    yaml_path = tmp_path / f"{tid}.yaml"
    yaml_path.write_text(yaml.dump(thesis, default_flow_style=False), encoding="utf-8")

    # Confirm the corrupted file round-trips on plain read (D1 not
    # executed on this path — _load_thesis()/get() do not validate).
    reloaded = thesis_store.get(tmp_path, tid)
    assert reloaded["position"]["shares"] == float("inf")

    before = _state_file_hash(tmp_path, tid)
    with pytest.raises(ValueError, match="not finite"):
        thesis_store.close(tmp_path, tid, "manual", 120.0, "2026-05-10T00:00:00+00:00")
    assert _state_file_hash(tmp_path, tid) == before


def test_trim_rejects_disk_corrupted_huge_int_shares_remaining_d4_only(tmp_path: Path):
    """Issue #254 test#7b variant: a disk-corrupted shares_remaining as a
    genuine (YAML-representable) huge Python int — not `.inf` — must
    raise via the try/except OverflowError layer specifically (bare
    math.isfinite() alone does not catch mid-arithmetic overflow; see
    _finalize_outcome()'s docstring). trim() must reject cleanly and
    leave the file byte-unchanged."""
    import yaml

    tid = _active_with_shares(tmp_path, 10, ticker="EQDISKHUGE")
    thesis = thesis_store.get(tmp_path, tid)
    thesis["position"]["shares"] = 10**400
    thesis["position"]["shares_remaining"] = 10**400
    yaml_path = tmp_path / f"{tid}.yaml"
    yaml_path.write_text(yaml.dump(thesis, default_flow_style=False), encoding="utf-8")

    before = _state_file_hash(tmp_path, tid)
    with pytest.raises(ValueError):  # must not raise OverflowError
        thesis_store.trim(tmp_path, tid, 1, 120.0, "2026-05-10")
    assert _state_file_hash(tmp_path, tid) == before


def test_terminate_invalidated_rejects_disk_corrupted_huge_shares_d4_only(tmp_path: Path):
    """Issue #254 test#7b variant: terminate()'s legacy no-cumulative-path
    branch (pnl_dollars *= shares) must also reject a disk-corrupted huge
    shares value cleanly via D4, not crash with OverflowError."""
    import yaml

    tid, _ = _register_and_get(tmp_path, ticker="EQDISKTERM", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    thesis_store.open_position(
        tmp_path,
        tid,
        100.0,
        "2026-05-01T00:00:00+00:00",
        shares=10,
        event_date="2026-05-01T00:00:00+00:00",
    )
    thesis = thesis_store.get(tmp_path, tid)
    thesis["position"]["shares"] = 10**400
    thesis["position"]["shares_remaining"] = 10**400
    yaml_path = tmp_path / f"{tid}.yaml"
    yaml_path.write_text(yaml.dump(thesis, default_flow_style=False), encoding="utf-8")

    before = _state_file_hash(tmp_path, tid)
    with pytest.raises(ValueError):  # must not raise OverflowError
        thesis_store.terminate(
            tmp_path,
            tid,
            "INVALIDATED",
            "thesis broke",
            actual_price=90.0,
            actual_date="2026-05-10T00:00:00+00:00",
        )
    assert _state_file_hash(tmp_path, tid) == before


def test_cli_open_position_rejects_nan_shares(tmp_path: Path):
    """Issue #254: the CLI --shares flag rejects "nan" at argparse level
    (exit 2, no traceback) via the new _strict_shares parser."""
    tid, _ = _register_and_get(tmp_path, ticker="EQCLINAN", _source_date="2026-03-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(["--state-dir", sd, "transition", tid, "ENTRY_READY", "--reason", "ok"])
        == 0
    )
    with pytest.raises(SystemExit) as exc_info:
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "150",
                "--actual-date",
                "2026-03-01",
                "--shares",
                "nan",
            ]
        )
    assert exc_info.value.code == 2


def test_cli_open_position_rejects_infinite_shares(tmp_path: Path):
    tid, _ = _register_and_get(tmp_path, ticker="EQCLIINF", _source_date="2026-03-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(["--state-dir", sd, "transition", tid, "ENTRY_READY", "--reason", "ok"])
        == 0
    )
    with pytest.raises(SystemExit) as exc_info:
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "150",
                "--actual-date",
                "2026-03-01",
                "--shares",
                "inf",
            ]
        )
    assert exc_info.value.code == 2


def test_cli_open_position_rejects_shares_above_cap(tmp_path: Path):
    tid, _ = _register_and_get(tmp_path, ticker="EQCLICAP", _source_date="2026-03-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(["--state-dir", sd, "transition", tid, "ENTRY_READY", "--reason", "ok"])
        == 0
    )
    with pytest.raises(SystemExit) as exc_info:
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "150",
                "--actual-date",
                "2026-03-01",
                "--shares",
                str(thesis_store._MAX_SHARES + 1),
            ]
        )
    assert exc_info.value.code == 2


def test_cli_open_position_rejects_huge_digit_string_shares(tmp_path: Path):
    """Issue #254 mechanism note: unlike the futures --contracts case
    (int() parses arbitrary precision, needs an explicit cap check), a
    400-digit --shares string goes through float() parsing, which
    SATURATES to inf rather than raising (verified empirically:
    float("1"+"0"*400) == inf, no exception) — so this is caught by the
    isfinite() check in _strict_shares, not a try/except. Different
    mechanism, same clean rejection with no traceback."""
    tid, _ = _register_and_get(tmp_path, ticker="EQCLIDIGITS", _source_date="2026-03-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(["--state-dir", sd, "transition", tid, "ENTRY_READY", "--reason", "ok"])
        == 0
    )
    huge_digits = "1" + "0" * 400
    with pytest.raises(SystemExit) as exc_info:
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "open-position",
                tid,
                "--actual-price",
                "150",
                "--actual-date",
                "2026-03-01",
                "--shares",
                huge_digits,
            ]
        )
    assert exc_info.value.code == 2


def test_cli_open_position_accepts_fractional_shares_no_regression(tmp_path: Path):
    """Regression pin: --shares 7.86 (fractional, the common real-world
    case) is unaffected by the new strict parser."""
    tid, _ = _register_and_get(tmp_path, ticker="EQCLIFRACOK", _source_date="2026-03-01")
    sd = str(tmp_path)
    assert (
        thesis_store.main(["--state-dir", sd, "transition", tid, "ENTRY_READY", "--reason", "ok"])
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
                "150",
                "--actual-date",
                "2026-03-01",
                "--shares",
                "7.86",
            ]
        )
        == 0
    )
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["shares"] == 7.86


def test_cli_trim_rejects_nan_shares_sold(tmp_path: Path):
    """Issue #254: the CLI --shares-sold flag (trim) rejects "nan" too."""
    tid = _active_with_shares(tmp_path, 10, ticker="EQCLITRIMNAN")
    sd = str(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "trim",
                tid,
                "--shares-sold",
                "nan",
                "--price",
                "120",
                "--date",
                "2026-05-10",
            ]
        )
    assert exc_info.value.code == 2


def test_cli_trim_accepts_fractional_shares_sold_no_regression(tmp_path: Path):
    """Regression pin: --shares-sold with a fractional value still works."""
    tid = _active_with_shares(tmp_path, 7.86, ticker="EQCLITRIMFRACOK")
    sd = str(tmp_path)
    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "trim",
                tid,
                "--shares-sold",
                "4.0",
                "--price",
                "120",
                "--date",
                "2026-05-10",
            ]
        )
        == 0
    )
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["shares_remaining"] == pytest.approx(3.86)


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


# -- Tests: PR-80B partial close (PARTIALLY_CLOSED + shares_remaining + trim) --


def _active_with_shares(tmp_path: Path, shares, entry_price=100.0, **overrides):
    """Register → ENTRY_READY → ACTIVE @2026-05-01 with `shares` (chain
    backdated so later-dated trims stay status_history-monotonic).

    `**overrides` (e.g. ticker=...) flow to _register_and_get so a single
    test can build multiple distinct theses (default _make_thesis_data is
    fingerprint-idempotent — same args ⇒ same thesis)."""
    tid, _ = _register_and_get(tmp_path, _source_date="2026-05-01", **overrides)
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    thesis_store.open_position(
        tmp_path,
        tid,
        entry_price,
        "2026-05-01T00:00:00+00:00",
        shares=shares,
        event_date="2026-05-01T00:00:00+00:00",
    )
    return tid


def test_open_position_sets_shares_remaining(tmp_path: Path):
    tid = _active_with_shares(tmp_path, 10)
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["shares"] == 10
    assert t["position"]["shares_remaining"] == 10


def test_attach_then_open_position_no_shares_sets_remaining(tmp_path: Path):
    """attach_position() sets shares_remaining; open_position without --shares
    must not leave a PR-80B record looking legacy."""
    tid, _ = _register_and_get(tmp_path, _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    report = _make_position_report(tmp_path)  # final_recommended_shares = 125
    thesis_store.attach_position(tmp_path, tid, report)
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["shares_remaining"] == 125
    thesis_store.open_position(
        tmp_path, tid, 150.0, "2026-05-01T00:00:00+00:00", event_date="2026-05-01T00:00:00+00:00"
    )
    t = thesis_store.get(tmp_path, tid)
    assert t["position"]["shares_remaining"] == t["position"]["shares"] == 125


@pytest.mark.parametrize("end_status", ["PARTIALLY_CLOSED", "CLOSED", "INVALIDATED"])
def test_attach_position_rejected_post_open(tmp_path: Path, end_status):
    """attach_position() must refuse PARTIALLY_CLOSED / CLOSED / INVALIDATED —
    re-writing shares_remaining == shares would violate the invariant and
    clobber the trim ledger."""
    report = _make_position_report(tmp_path)
    tid = _active_with_shares(tmp_path, 10, ticker=f"ATCH{end_status[:3]}")

    if end_status == "PARTIALLY_CLOSED":
        thesis_store.trim(tmp_path, tid, 4, 120.0, "2026-05-10")
    elif end_status == "CLOSED":
        thesis_store.trim(tmp_path, tid, 10, 120.0, "2026-05-10")  # trim-to-zero
    else:  # INVALIDATED
        thesis_store.terminate(tmp_path, tid, "INVALIDATED", "thesis broke")

    assert thesis_store.get(tmp_path, tid)["status"] == end_status
    with pytest.raises(ValueError, match="attach_position\\(\\) not allowed"):
        thesis_store.attach_position(tmp_path, tid, report)


def test_trim_active_to_partially_closed(tmp_path: Path):
    tid = _active_with_shares(tmp_path, 10)
    t = thesis_store.trim(tmp_path, tid, 4, 120.0, "2026-05-10")
    assert t["status"] == "PARTIALLY_CLOSED"
    assert t["position"]["shares_remaining"] == 6
    led = t["status_history"][-1]
    assert led["status"] == "PARTIALLY_CLOSED"
    assert led["shares_sold"] == 4
    assert led["price"] == 120.0
    assert led["proceeds"] == 480.0
    assert led["realized_pnl"] == 80.0  # (120-100)*4
    assert led["at"] == "2026-05-10T00:00:00+00:00"  # --date persisted


def test_multi_trim_then_close_cumulative(tmp_path: Path):
    """entry 100 / 10sh; trim 4@120 (+80), trim 3@130 (+90), close 3@90 (−30)
    → cumulative pnl_dollars 140, pnl_pct 140/(100*10)*100 = 14.0."""
    tid = _active_with_shares(tmp_path, 10)
    thesis_store.trim(tmp_path, tid, 4, 120.0, "2026-05-10")
    thesis_store.trim(tmp_path, tid, 3, 130.0, "2026-05-15")
    t = thesis_store.close(tmp_path, tid, "manual", 90.0, "2026-05-20T00:00:00+00:00")
    assert t["status"] == "CLOSED"
    assert t["position"]["shares_remaining"] == 0
    assert t["outcome"]["pnl_dollars"] == 140.0
    assert t["outcome"]["pnl_pct"] == 14.0
    assert t["outcome"]["holding_days"] == 19  # 2026-05-01 → 2026-05-20
    ledger = [h for h in t["status_history"] if "realized_pnl" in h]
    assert [h["realized_pnl"] for h in ledger] == [80.0, 90.0, -30.0]
    # exactly one terminal entry, and it is CLOSED
    assert sum(1 for h in t["status_history"] if h["status"] == "CLOSED") == 1
    assert t["status_history"][-1]["status"] == "CLOSED"


def test_trim_to_zero_closes_with_default_exit_reason(tmp_path: Path):
    tid = _active_with_shares(tmp_path, 10)
    thesis_store.trim(tmp_path, tid, 6, 120.0, "2026-05-10")
    t = thesis_store.trim(tmp_path, tid, 4, 130.0, "2026-05-15")
    assert t["status"] == "CLOSED"
    assert t["position"]["shares_remaining"] == 0
    assert t["exit"]["exit_reason"] == "manual"  # default
    assert t["exit"]["actual_price"] == 130.0
    assert t["exit"]["actual_date"] == "2026-05-15T00:00:00+00:00"
    # (120-100)*6 + (130-100)*4 = 120 + 120 = 240
    assert t["outcome"]["pnl_dollars"] == 240.0
    # only one CLOSED entry (trim's own ledger entry, not duplicated)
    assert sum(1 for h in t["status_history"] if h["status"] == "CLOSED") == 1


def test_trim_to_zero_exit_reason_override(tmp_path: Path):
    tid = _active_with_shares(tmp_path, 5)
    t = thesis_store.trim(tmp_path, tid, 5, 80.0, "2026-05-10", exit_reason="stop_hit")
    assert t["status"] == "CLOSED"
    assert t["exit"]["exit_reason"] == "stop_hit"


def test_close_from_partially_closed_is_cumulative(tmp_path: Path):
    tid = _active_with_shares(tmp_path, 10)
    thesis_store.trim(tmp_path, tid, 7, 120.0, "2026-05-10")  # realized +140
    t = thesis_store.close(
        tmp_path, tid, "manual", 90.0, "2026-05-20T00:00:00+00:00"
    )  # remaining 3 @ 90 → (90-100)*3 = −30
    assert t["status"] == "CLOSED"
    assert t["outcome"]["pnl_dollars"] == 110.0  # 140 − 30
    assert sum(1 for h in t["status_history"] if h["status"] == "CLOSED") == 1


def test_trim_guards(tmp_path: Path):
    # Distinct tickers — _make_thesis_data defaults are fingerprint-idempotent,
    # so identical args would collapse to one thesis.
    # not ACTIVE/PARTIALLY_CLOSED (IDEA)
    tid, _ = _register_and_get(tmp_path, ticker="GUARDA")
    with pytest.raises(ValueError, match="Can only trim"):
        thesis_store.trim(tmp_path, tid, 1, 100.0, "2026-05-10")
    # ACTIVE but no position/shares (open-position without --shares)
    tid2, _ = _register_and_get(tmp_path, ticker="GUARDB", _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid2, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    thesis_store.open_position(
        tmp_path,
        tid2,
        100.0,
        "2026-05-01T00:00:00+00:00",
        event_date="2026-05-01T00:00:00+00:00",
    )
    with pytest.raises(ValueError, match="requires a recorded position"):
        thesis_store.trim(tmp_path, tid2, 1, 100.0, "2026-05-10")
    # shares_sold > remaining and <= 0
    tid3 = _active_with_shares(tmp_path, 5, ticker="GUARDC")
    with pytest.raises(ValueError, match="must be > 0 and"):
        thesis_store.trim(tmp_path, tid3, 6, 100.0, "2026-05-10")
    with pytest.raises(ValueError, match="must be > 0 and"):
        thesis_store.trim(tmp_path, tid3, 0, 100.0, "2026-05-10")


def test_trim_fractional_precision_to_zero(tmp_path: Path):
    tid = _active_with_shares(tmp_path, 7.86)
    t = thesis_store.trim(tmp_path, tid, 4.00, 120.0, "2026-05-10")
    assert t["status"] == "PARTIALLY_CLOSED"
    assert t["position"]["shares_remaining"] == 3.86
    t = thesis_store.trim(tmp_path, tid, 3.86, 130.0, "2026-05-15")
    assert t["status"] == "CLOSED"
    assert t["position"]["shares_remaining"] == 0  # epsilon-snapped


def test_transition_into_partially_closed_blocked(tmp_path: Path):
    tid = _active_with_shares(tmp_path, 10)
    with pytest.raises(ValueError, match="Use trim\\(\\)"):
        thesis_store.transition(tmp_path, tid, "PARTIALLY_CLOSED", "nope")


def test_partially_closed_requires_shares_remaining(tmp_path: Path):
    """A PARTIALLY_CLOSED thesis with no shares_remaining is rejected (no
    legacy leniency for this PR-80B-only status)."""
    tid = _active_with_shares(tmp_path, 10)
    thesis_store.trim(tmp_path, tid, 4, 120.0, "2026-05-10")  # → PARTIALLY_CLOSED
    t = thesis_store.get(tmp_path, tid)
    del t["position"]["shares_remaining"]
    with pytest.raises(ValueError, match="requires position.shares_remaining"):
        thesis_store._validate_thesis(t)


def test_closed_shares_remaining_zero_passes_schema(tmp_path: Path):
    """Regression for the minimum:0 schema fix — a CLOSED thesis persisting
    shares_remaining == 0 must NOT be rejected at the JSON-Schema layer."""
    tid = _active_with_shares(tmp_path, 10)
    thesis_store.trim(tmp_path, tid, 10, 120.0, "2026-05-10")  # full close-out
    t = thesis_store.get(tmp_path, tid)  # get() implies schema-valid
    assert t["status"] == "CLOSED"
    assert t["position"]["shares_remaining"] == 0
    thesis_store._validate_thesis(t)  # explicit: no raise


def test_legacy_active_without_shares_remaining_valid(tmp_path: Path):
    """A legacy ACTIVE thesis (no shares_remaining key) still validates."""
    tid = _active_with_shares(tmp_path, 10)
    t = thesis_store.get(tmp_path, tid)
    del t["position"]["shares_remaining"]
    thesis_store._validate_thesis(t)  # ACTIVE leniency: no raise


def test_terminate_invalidated_no_price_unchanged(tmp_path: Path):
    """attach-position then terminate INVALIDATED with no price → one plain
    INVALIDATED entry, no P&L, shares_remaining untouched (pre-PR-80B path)."""
    tid, _ = _register_and_get(tmp_path, _source_date="2026-05-01")
    thesis_store.transition(
        tmp_path, tid, "ENTRY_READY", "ok", event_date="2026-05-01T00:00:00+00:00"
    )
    report = _make_position_report(tmp_path)
    thesis_store.attach_position(tmp_path, tid, report)
    thesis_store.open_position(
        tmp_path, tid, 150.0, "2026-05-01T00:00:00+00:00", event_date="2026-05-01T00:00:00+00:00"
    )
    t = thesis_store.terminate(tmp_path, tid, "INVALIDATED", "thesis broke")
    assert t["status"] == "INVALIDATED"
    assert t["outcome"]["pnl_dollars"] is None
    assert t["position"]["shares_remaining"] == 125  # untouched
    assert sum(1 for h in t["status_history"] if h["status"] == "INVALIDATED") == 1
    assert "realized_pnl" not in t["status_history"][-1]


def test_terminate_invalidated_from_partially_closed_cumulative(tmp_path: Path):
    tid = _active_with_shares(tmp_path, 10)
    thesis_store.trim(tmp_path, tid, 6, 120.0, "2026-05-10")  # realized +120
    t = thesis_store.terminate(
        tmp_path,
        tid,
        "INVALIDATED",
        "broke",
        actual_price=90.0,
        actual_date="2026-05-20T00:00:00+00:00",
    )  # remaining 4 @ 90 → (90-100)*4 = −40
    assert t["status"] == "INVALIDATED"
    assert t["outcome"]["pnl_dollars"] == 80.0  # 120 − 40, not double-counted
    assert sum(1 for h in t["status_history"] if h["status"] == "INVALIDATED") == 1


def test_cli_trim_subcommand(tmp_path: Path):
    tid = _active_with_shares(tmp_path, 10)
    sd = str(tmp_path)
    rc = thesis_store.main(
        [
            "--state-dir",
            sd,
            "trim",
            tid,
            "--shares-sold",
            "4",
            "--price",
            "120",
            "--date",
            "2026-05-10",
        ]
    )
    assert rc == 0
    t = thesis_store.get(tmp_path, tid)
    assert t["status"] == "PARTIALLY_CLOSED"
    assert t["position"]["shares_remaining"] == 6
    assert t["status_history"][-1]["at"] == "2026-05-10T00:00:00+00:00"
