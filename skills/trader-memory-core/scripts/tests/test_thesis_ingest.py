"""Tests for thesis_ingest.py — adapter conversion and registration."""

import json
from pathlib import Path

import pytest
import thesis_ingest
import thesis_store

# -- Helpers -------------------------------------------------------------------


def _write_json(tmp_path: Path, data, filename="input.json"):
    path = tmp_path / filename
    path.write_text(json.dumps(data))
    return str(path)


# -- Tests: kanchi adapter -----------------------------------------------------


def test_ingest_kanchi(tmp_path: Path):
    """kanchi JSON → thesis with dividend_income, entry.target_price populated."""
    state_dir = tmp_path / "theses"
    record = {
        "ticker": "JNJ",
        "buy_target_price": 148.50,
        "current_yield_pct": 3.2,
        "signal": "BUY",
        "grade": "A",
    }
    input_file = _write_json(tmp_path, {"candidates": [record]})

    ids = thesis_ingest.ingest("kanchi-dividend-sop", input_file, str(state_dir))
    assert len(ids) == 1

    thesis = thesis_store.get(state_dir, ids[0])
    assert thesis["ticker"] == "JNJ"
    assert thesis["thesis_type"] == "dividend_income"
    assert thesis["entry"]["target_price"] == 148.50
    assert thesis["origin"]["skill"] == "kanchi-dividend-sop"
    assert thesis["origin"]["raw_provenance"]["current_yield_pct"] == 3.2


# -- Tests: earnings adapter ---------------------------------------------------


def test_ingest_earnings(tmp_path: Path):
    """earnings JSON → grade in raw_provenance, screening_grade canonical."""
    state_dir = tmp_path / "theses"
    record = {
        "symbol": "NVDA",
        "grade": "A",
        "composite_score": 92.5,
        "gap_pct": 8.3,
        "sector": "Technology",
    }
    input_file = _write_json(tmp_path, {"results": [record]})

    ids = thesis_ingest.ingest("earnings-trade-analyzer", input_file, str(state_dir))
    assert len(ids) == 1

    thesis = thesis_store.get(state_dir, ids[0])
    assert thesis["ticker"] == "NVDA"
    assert thesis["thesis_type"] == "earnings_drift"
    assert thesis["origin"]["screening_grade"] == "A"
    assert thesis["origin"]["screening_score"] == 92.5
    assert thesis["origin"]["raw_provenance"]["gap_pct"] == 8.3
    assert thesis["market_context"]["sector"] == "Technology"


# -- Tests: vcp adapter --------------------------------------------------------


def test_ingest_vcp(tmp_path: Path):
    """vcp JSON → pivot_breakout type."""
    state_dir = tmp_path / "theses"
    record = {
        "symbol": "PLTR",
        "distance_from_pivot_pct": 2.3,
        "entry_ready": True,
        "composite_score": 78.0,
    }
    input_file = _write_json(tmp_path, {"results": [record]})

    ids = thesis_ingest.ingest("vcp-screener", input_file, str(state_dir))
    assert len(ids) == 1

    thesis = thesis_store.get(state_dir, ids[0])
    assert thesis["ticker"] == "PLTR"
    assert thesis["thesis_type"] == "pivot_breakout"
    assert thesis["origin"]["raw_provenance"]["entry_ready"] is True


# -- Tests: pead adapter -------------------------------------------------------


def test_ingest_pead(tmp_path: Path):
    """pead JSON → entry_price and stop_loss mapped."""
    state_dir = tmp_path / "theses"
    record = {
        "symbol": "CRWD",
        "entry_price": 380.00,
        "stop_loss": 355.00,
        "status": "SIGNAL_READY",
        "grade": "B",
    }
    input_file = _write_json(tmp_path, {"results": [record]})

    ids = thesis_ingest.ingest("pead-screener", input_file, str(state_dir))
    assert len(ids) == 1

    thesis = thesis_store.get(state_dir, ids[0])
    assert thesis["entry"]["target_price"] == 380.00
    assert thesis["exit"]["stop_loss"] == 355.00


# -- Tests: canslim adapter ----------------------------------------------------


def test_ingest_canslim(tmp_path: Path):
    """canslim JSON → growth_momentum type."""
    state_dir = tmp_path / "theses"
    record = {
        "symbol": "META",
        "rating": "A",
        "composite_score": 85.0,
    }
    input_file = _write_json(tmp_path, [record])

    ids = thesis_ingest.ingest("canslim-screener", input_file, str(state_dir))
    assert len(ids) == 1

    thesis = thesis_store.get(state_dir, ids[0])
    assert thesis["thesis_type"] == "growth_momentum"
    assert thesis["origin"]["screening_grade"] == "A"


# -- Tests: raw_provenance preserved -------------------------------------------


def test_all_adapters_preserve_raw_provenance(tmp_path: Path):
    """All adapters should preserve original data in raw_provenance."""
    state_dir = tmp_path / "theses"
    record = {
        "symbol": "TEST",
        "grade": "B",
        "composite_score": 70.0,
        "custom_field": "custom_value",
    }
    input_file = _write_json(tmp_path, {"results": [record]})

    ids = thesis_ingest.ingest("earnings-trade-analyzer", input_file, str(state_dir))
    thesis = thesis_store.get(state_dir, ids[0])
    assert thesis["origin"]["raw_provenance"]["custom_field"] == "custom_value"


# -- Tests: error handling -----------------------------------------------------


def test_unknown_source_raises(tmp_path: Path):
    """Unknown --source should raise ValueError."""
    input_file = _write_json(tmp_path, [{"ticker": "AAPL"}])
    with pytest.raises(ValueError, match="Unknown source"):
        thesis_ingest.ingest("nonexistent-skill", input_file, str(tmp_path))


def test_missing_required_fields_raises(tmp_path: Path):
    """Missing required fields should raise validation error."""
    state_dir = tmp_path / "theses"
    record = {"not_a_ticker": "AAPL"}  # missing 'ticker' or 'symbol'
    input_file = _write_json(tmp_path, {"results": [record]})

    # Should log error but not raise (continues to next record)
    ids = thesis_ingest.ingest("earnings-trade-analyzer", input_file, str(state_dir))
    assert len(ids) == 0


# -- Tests: edge adapter -------------------------------------------------------


def test_edge_research_only_skipped(tmp_path: Path):
    """edge ticket with research_only=True → skip with warning."""
    state_dir = tmp_path / "theses"
    record = {
        "id": "ticket_001",
        "ticker": "SPY",
        "hypothesis_type": "breakout",
        "research_only": True,
    }
    input_file = _write_json(tmp_path, record)

    ids = thesis_ingest.ingest("edge-candidate-agent", input_file, str(state_dir))
    assert len(ids) == 0


def test_edge_market_basket_skipped(tmp_path: Path):
    """edge ticket with MARKET_BASKET → skip with warning."""
    state_dir = tmp_path / "theses"
    record = {
        "id": "ticket_002",
        "universe": "MARKET_BASKET",
        "hypothesis_type": "momentum",
    }
    input_file = _write_json(tmp_path, record)

    ids = thesis_ingest.ingest("edge-candidate-agent", input_file, str(state_dir))
    assert len(ids) == 0


# -- Tests: fix verification ---------------------------------------------------


def test_ingest_kanchi_rows_key(tmp_path: Path):
    """kanchi build_entry_signals.py uses 'rows' key, not 'candidates'."""
    state_dir = tmp_path / "theses"
    record = {"ticker": "PG", "buy_target_price": 165.00}
    input_file = _write_json(tmp_path, {"rows": [record]})

    ids = thesis_ingest.ingest("kanchi-dividend-sop", input_file, str(state_dir))
    assert len(ids) == 1
    thesis = thesis_store.get(state_dir, ids[0])
    assert thesis["ticker"] == "PG"
    assert thesis["entry"]["target_price"] == 165.00


def test_edge_ticket_top_level_entry_exit(tmp_path: Path):
    """edge ticket uses top-level entry/exit, not signals.entry."""
    state_dir = tmp_path / "theses"
    record = {
        "id": "edge_vcp_v1",
        "ticker": "AMZN",
        "hypothesis_type": "breakout",
        "entry_family": "pivot_breakout",
        "mechanism_tag": "behavior",
        "entry": {"conditions": ["breakout above pivot", "volume > 1.5x avg"]},
        "exit": {"stop_loss_pct": 0.07, "take_profit_rr": 2.0, "time_stop_days": 20},
    }
    input_file = _write_json(tmp_path, record)

    ids = thesis_ingest.ingest("edge-candidate-agent", input_file, str(state_dir))
    assert len(ids) == 1
    thesis = thesis_store.get(state_dir, ids[0])
    assert thesis["entry"]["conditions"] == ["breakout above pivot", "volume > 1.5x avg"]
    assert thesis["exit"]["stop_loss_pct"] == 0.07
    assert thesis["exit"]["take_profit_rr"] == 2.0
    assert thesis["exit"]["time_stop_days"] == 20


# -- Tests: source date propagation --------------------------------------------


def test_ingest_propagates_as_of_date(tmp_path: Path):
    """as_of from report metadata should become thesis_id date and created_at."""
    state_dir = tmp_path / "theses"
    data = {
        "as_of": "2026-02-20",
        "generated_at": "2026-02-20T10:00:00Z",
        "rows": [{"ticker": "KO", "buy_target_price": 60.00}],
    }
    input_file = _write_json(tmp_path, data)

    ids = thesis_ingest.ingest("kanchi-dividend-sop", input_file, str(state_dir))
    assert len(ids) == 1
    assert "_20260220_" in ids[0]
    thesis = thesis_store.get(state_dir, ids[0])
    assert thesis["created_at"].startswith("2026-02-20")


def test_ingest_uses_generated_at_as_fallback(tmp_path: Path):
    """generated_at should be used if as_of is absent."""
    state_dir = tmp_path / "theses"
    data = {
        "generated_at": "2026-01-10T08:30:00Z",
        "results": [{"symbol": "GOOG", "grade": "B", "composite_score": 72.0}],
    }
    input_file = _write_json(tmp_path, data)

    ids = thesis_ingest.ingest("earnings-trade-analyzer", input_file, str(state_dir))
    assert "_20260110_" in ids[0]


# -- Tests: duplicate handling -------------------------------------------------


def test_duplicate_ingest_is_idempotent(tmp_path: Path):
    """Same input ingested twice should return the same thesis_id (idempotent)."""
    state_dir = tmp_path / "theses"
    record = {"symbol": "AAPL", "grade": "A", "composite_score": 90.0}
    input_file = _write_json(tmp_path, {"results": [record]})

    ids1 = thesis_ingest.ingest("earnings-trade-analyzer", input_file, str(state_dir))
    ids2 = thesis_ingest.ingest("earnings-trade-analyzer", input_file, str(state_dir))

    assert ids1[0] == ids2[0]


# -- Tests: manual adapter -----------------------------------------------------


def test_ingest_manual_single_record_fractional(tmp_path: Path):
    """A free-form single dict (no results/candidates wrapper) → schema-valid
    IDEA thesis; fractional shares preserved in raw_provenance; stop/target
    land in existing exit.* fields; entry.* left empty."""
    state_dir = tmp_path / "theses"
    record = {
        "ticker": "AMD",
        "thesis_statement": "AMD AI accelerator momentum, fractional IBI Smart position",
        "thesis_type": "growth_momentum",
        "entry_price": 142.10,
        "entry_date": "2026-05-02",
        "shares": 7.86,
        "stop_price": 128.0,
        "target_price": 180.0,
    }
    input_file = _write_json(tmp_path, record)

    ids = thesis_ingest.ingest("manual", input_file, str(state_dir))
    assert len(ids) == 1

    thesis = thesis_store.get(state_dir, ids[0])  # get() implies schema-valid
    assert thesis["status"] == "IDEA"
    assert thesis["ticker"] == "AMD"
    assert thesis["thesis_type"] == "growth_momentum"
    assert thesis["origin"]["skill"] == "manual"
    assert thesis["origin"]["raw_provenance"]["shares"] == 7.86
    assert thesis["origin"]["raw_provenance"]["entry_price"] == 142.10
    assert thesis["exit"]["stop_loss"] == 128.0
    assert thesis["exit"]["take_profit"] == 180.0
    # entry_price/date NOT mapped to entry.* (set later by open-position)
    assert thesis["entry"].get("actual_price") is None
    assert thesis["entry"].get("target_price") is None
    assert thesis["position"] is None
    # _source_date from entry_date → IDEA history stamped that day
    assert thesis["status_history"][0]["at"] == "2026-05-02T00:00:00+00:00"
    assert "_20260502_" in ids[0]


def test_ingest_manual_array(tmp_path: Path):
    """A list of manual records registers N theses."""
    state_dir = tmp_path / "theses"
    records = [
        {
            "ticker": "TSLA",
            "thesis_statement": "TSLA swing",
            "thesis_type": "growth_momentum",
            "entry_date": "2026-05-02",
        },
        {
            "ticker": "OIH",
            "thesis_statement": "OIH energy services",
            "thesis_type": "mean_reversion",
            "entry_date": "2026-05-03",
        },
    ]
    input_file = _write_json(tmp_path, records)

    ids = thesis_ingest.ingest("manual", input_file, str(state_dir))
    assert len(ids) == 2
    tickers = {thesis_store.get(state_dir, i)["ticker"] for i in ids}
    assert tickers == {"TSLA", "OIH"}


def test_ingest_manual_missing_ticker_reaches_adapter(tmp_path: Path):
    """A dict with no ticker/id/symbol still reaches the manual adapter
    (source-aware _extract_records) and yields the clear field error; ingest
    registers 0."""
    state_dir = tmp_path / "theses"
    input_file = _write_json(
        tmp_path, {"thesis_statement": "no ticker", "thesis_type": "growth_momentum"}
    )

    ids = thesis_ingest.ingest("manual", input_file, str(state_dir))
    assert ids == []  # adapter raised, ingest logged + skipped

    # The adapter's message is explicit (not the generic _extract_records one)
    with pytest.raises(ValueError, match="Missing required field 'ticker'"):
        thesis_ingest.ingest_manual(
            {"thesis_statement": "x", "thesis_type": "growth_momentum"}, "f.json"
        )


def test_ingest_manual_invalid_thesis_type(tmp_path: Path):
    """Bad thesis_type → clear error, 0 registered."""
    state_dir = tmp_path / "theses"
    input_file = _write_json(
        tmp_path,
        {"ticker": "AMD", "thesis_statement": "x", "thesis_type": "not_a_type"},
    )
    ids = thesis_ingest.ingest("manual", input_file, str(state_dir))
    assert ids == []
    with pytest.raises(ValueError, match="Invalid or missing 'thesis_type'"):
        thesis_ingest.ingest_manual(
            {"ticker": "AMD", "thesis_statement": "x", "thesis_type": "not_a_type"},
            "f.json",
        )


@pytest.mark.parametrize("entry_date", ["2026-05-02", "2026-05-02T10:00:00+00:00"])
def test_ingest_manual_source_date_normalized(tmp_path: Path, entry_date: str):
    """Date-only and full-ISO entry_date both yield a date-only _source_date
    (register() builds 'YYYY-MM-DDT00:00:00+00:00')."""
    state_dir = tmp_path / "theses"
    input_file = _write_json(
        tmp_path,
        {
            "ticker": "NVDA",
            "thesis_statement": "NVDA",
            "thesis_type": "growth_momentum",
            "entry_date": entry_date,
        },
    )
    ids = thesis_ingest.ingest("manual", input_file, str(state_dir))
    assert len(ids) == 1
    thesis = thesis_store.get(state_dir, ids[0])
    assert thesis["status_history"][0]["at"] == "2026-05-02T00:00:00+00:00"
    assert "_20260502_" in ids[0]


def test_manual_backdated_lifecycle_monotonic_e2e(tmp_path: Path):
    """The issue's repro: a pre-existing fractional broker position reaches
    ACTIVE via manual ingest → transition --event-date → open-position
    --event-date, and the fully backdated status_history saves cleanly
    (IDEA == ENTRY_READY == ACTIVE == entry date)."""
    state_dir = tmp_path / "theses"
    input_file = _write_json(
        tmp_path,
        {
            "ticker": "AMD",
            "thesis_statement": "AMD fractional position from IBI Smart",
            "thesis_type": "growth_momentum",
            "entry_price": 142.10,
            "entry_date": "2026-05-02",
            "shares": 7.86,
        },
    )
    ids = thesis_ingest.ingest("manual", input_file, str(state_dir))
    tid = ids[0]
    sd = str(state_dir)

    assert (
        thesis_store.main(
            [
                "--state-dir",
                sd,
                "transition",
                tid,
                "ENTRY_READY",
                "--reason",
                "existing IBI Smart position",
                "--event-date",
                "2026-05-02",
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
                "142.10",
                "--actual-date",
                "2026-05-02",
                "--shares",
                "7.86",
                "--event-date",
                "2026-05-02",
            ]
        )
        == 0
    )

    t = thesis_store.get(state_dir, tid)  # get() implies it saved + validated
    assert t["status"] == "ACTIVE"
    assert t["position"]["shares"] == 7.86
    ats = [h["at"] for h in t["status_history"]]
    assert ats == ["2026-05-02T00:00:00+00:00"] * 3
