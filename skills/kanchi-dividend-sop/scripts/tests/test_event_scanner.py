"""WS-3 event-scanner tests (offline, NO live web — CR-2).

# DATA-DATE: 2026-05-17
# REVIEW-TRIGGER: MKC-Unilever close (mid-2027), WTRG-AWK close
"""

from event_scanner import (
    CLEAN_CONFIRMED,
    FAILED_DEGRADED,
    MAJOR_EVENT,
    MINOR_EVENT_CAUTION,
    NO_EVENT_FOUND,
    SKIPPED,
    FixtureEventScanner,
    ManualEventScanner,
    ScanResult,
    apply_event_cap,
    is_major_structural_event,
)


# --- D3: MKC-Unilever is a major structural event ---
def test_mkc_unilever_is_major_structural_event():
    major, reasons = is_major_structural_event(
        {
            "tx_value": 44_800,
            "market_cap": 16_000,
            "share_issuance_pct": 90,
            "structure": "merger_of_equals",
            "control_change": True,
        }
    )
    assert major is True
    assert any("tx_value" in r for r in reasons)


def test_small_bolt_on_is_not_major():
    major, reasons = is_major_structural_event(
        {"tx_value": 200, "market_cap": 30_000, "share_issuance_pct": 0}
    )
    assert major is False and reasons == []


def test_sector_specific_utility_materiality():
    major, reasons = is_major_structural_event(
        {
            "market_cap": 20_000,
            "tx_value": 0,
            "sector": "utilities",
            "sector_metrics": {
                "acq_or_capex_pct_rate_base": 12,
                "regulatory_approval_pending": True,
            },
        }
    )
    assert major is True
    assert "utility_acq_capex_gt_10pct_rate_base" in reasons


def test_rolling_24m_cumulative_mna():
    major, reasons = is_major_structural_event(
        {"market_cap": 10_000, "tx_value": 100, "rolling_24m_tx_value": 1_800}
    )
    assert major is True
    assert "rolling_24m_tx_gt_15pct_mcap" in reasons


# --- pessimistic cap (4th-review #5) ---
def test_major_event_caps_and_blocks_t1():
    scan = ScanResult(ticker="MKC", result=MAJOR_EVENT, reasons=["tx_value_280pct_mcap"])
    cap = apply_event_cap(scan, step5_triggered=False)
    assert cap["verdict_cap"] == "HOLD-REVIEW"
    assert cap["t1_blocked"] is True
    assert "major_structural_event" in cap["blockers"]


def test_skipped_scan_on_triggered_name_caps_hold_review():
    scan = ScanResult(ticker="CMCSA", result=SKIPPED)
    cap = apply_event_cap(scan, step5_triggered=True)
    assert cap["verdict_cap"] == "HOLD-REVIEW"
    assert cap["t1_blocked"] is True
    assert "event_scan_failed_or_skipped" in cap["blockers"]


def test_failed_scan_on_non_triggered_blocks_t1_only():
    scan = ScanResult(ticker="XYZ", result=FAILED_DEGRADED)
    cap = apply_event_cap(scan, step5_triggered=False)
    assert cap["verdict_cap"] is None  # not entry-ready -> no hard verdict cap
    assert cap["t1_blocked"] is True


def test_no_event_found_is_weaker_than_clean_confirmed():
    weak = apply_event_cap(ScanResult("A", NO_EVENT_FOUND), step5_triggered=True)
    strong = apply_event_cap(ScanResult("B", CLEAN_CONFIRMED), step5_triggered=True)
    assert weak["verdict_cap"] == "HOLD-REVIEW"
    assert strong["verdict_cap"] is None and strong["t1_blocked"] is False


def test_minor_event_is_caution_note_only():
    cap = apply_event_cap(ScanResult("C", MINOR_EVENT_CAUTION), step5_triggered=True)
    assert cap["verdict_cap"] is None and cap["t1_blocked"] is False


# --- scanners are injectable; unknown ticker is pessimistic NO_EVENT_FOUND ---
def test_fixture_scanner_unknown_ticker_pessimistic():
    s = FixtureEventScanner({"MKC": ScanResult("MKC", MAJOR_EVENT)})
    assert s.scan("MKC", "2026-05-17").result == MAJOR_EVENT
    assert s.scan("ZZZ", "2026-05-17").result == NO_EVENT_FOUND


def test_manual_scanner_missing_file_is_pessimistic(tmp_path):
    s = ManualEventScanner(tmp_path / "absent.json")
    assert s.scan("MKC", "2026-05-17").result == NO_EVENT_FOUND


def test_manual_scanner_reads_events(tmp_path):
    p = tmp_path / "events.json"
    p.write_text('{"events": {"MKC": {"result": "MAJOR_EVENT", "pending_mna": true}}}')
    s = ManualEventScanner(p)
    r = s.scan("mkc", "2026-05-17")
    assert r.result == MAJOR_EVENT and r.pending_mna is True
