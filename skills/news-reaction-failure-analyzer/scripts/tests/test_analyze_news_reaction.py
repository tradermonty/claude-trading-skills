"""Tests for analyze_news_reaction.py — CLI logic (fallback chain, detector-json,
events validation, redaction, report generation).

Network calls are stubbed out with a fake `requests.Session`; no live FMP
calls are made here. Run with:
    python3 -m pytest skills/news-reaction-failure-analyzer/scripts/tests/ -v
"""

import argparse
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_news_reaction as analyzer  # noqa: E402
from analyze_news_reaction import (  # noqa: E402
    PRICE_SOURCE_CHAINS,
    PriceClient,
    _redact,
    build_event_record,
    build_run_context,
    fetch_price_series,
    generate_json_report,
    generate_markdown_report,
    resolve_direction_from_detector,
    validate_events,
)

# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {})})
        return self.responses.pop(0)


def make_eod_rows(dates, closes):
    return [{"symbol": "X", "date": d, "close": c} for d, c in zip(dates, closes)]


TRADING_DATES = [f"2026-06-{i:02d}" for i in range(1, 30)]
CLOSES = [100 + i * 0.3 for i in range(len(TRADING_DATES))]


# ---------------------------------------------------------------------------
# Price-source fallback chain
# ---------------------------------------------------------------------------


class TestPriceSourceChains:
    def test_all_65_cot_markets_documented_or_deliberately_absent(self):
        # Spot-check a representative sample from every sector in §6 exists.
        for symbol in ("ES", "NQ", "VX", "GC", "CL", "ZN", "DX", "B6", "BT"):
            assert symbol in PRICE_SOURCE_CHAINS

    def test_chain_entries_are_3_tuples(self):
        for chain in PRICE_SOURCE_CHAINS.values():
            for entry in chain:
                assert len(entry) == 3  # (price_symbol, kind, invert)
                symbol, kind, invert = entry
                assert kind in ("futures", "etf")
                assert isinstance(invert, bool)


class TestFetchPriceSeries:
    def test_primary_success_no_proxy(self):
        client = PriceClient(api_key="fake", sleep_seconds=0.0)
        rows = make_eod_rows(TRADING_DATES, CLOSES)
        client.session = _FakeSession([_FakeResponse(rows, status_code=200)])
        chain = [("ESUSD", "futures", False)]
        result = fetch_price_series(client, chain, "2026-06-01", "2026-06-29", as_of="2026-06-29")
        assert result["error"] is None
        assert result["price_symbol"] == "ESUSD"
        assert result["proxy_used"] is False
        assert len(result["series"]) == len(TRADING_DATES)

    def test_402_falls_back_to_etf_proxy(self):
        client = PriceClient(api_key="fake", sleep_seconds=0.0)
        rows = make_eod_rows(TRADING_DATES, CLOSES)
        client.session = _FakeSession(
            [
                _FakeResponse({"error": "restricted"}, status_code=402),
                _FakeResponse(rows, status_code=200),
            ]
        )
        chain = [("NQUSD", "futures", False), ("QQQ", "etf", False)]
        result = fetch_price_series(client, chain, "2026-06-01", "2026-06-29", as_of="2026-06-29")
        assert result["error"] is None
        assert result["price_symbol"] == "QQQ"
        assert result["proxy_used"] is True

    def test_zero_rows_is_treated_as_failure_and_advances_chain(self):
        client = PriceClient(api_key="fake", sleep_seconds=0.0)
        rows = make_eod_rows(TRADING_DATES, CLOSES)
        client.session = _FakeSession(
            [
                _FakeResponse([], status_code=200),  # VXUSD-style: 200 but 0 rows
                _FakeResponse(rows, status_code=200),
            ]
        )
        chain = [("VXUSD", "futures", False), ("SOMEPROXY", "etf", False)]
        result = fetch_price_series(client, chain, "2026-06-01", "2026-06-29", as_of="2026-06-29")
        assert result["error"] is None
        assert result["price_symbol"] == "SOMEPROXY"
        assert result["proxy_used"] is True

    def test_all_chain_members_fail_is_no_price_source(self):
        client = PriceClient(api_key="fake", sleep_seconds=0.0)
        client.session = _FakeSession(
            [
                _FakeResponse({}, status_code=402),
                _FakeResponse([], status_code=200),
            ]
        )
        chain = [("VXUSD", "futures", False), ("NOPROXY", "etf", False)]
        result = fetch_price_series(client, chain, "2026-06-01", "2026-06-29", as_of="2026-06-29")
        assert result["error"] == "no_price_source"
        assert result["series"] == []
        assert len(result["attempts"]) == 2

    def test_single_member_chain_no_fallback_available(self):
        client = PriceClient(api_key="fake", sleep_seconds=0.0)
        client.session = _FakeSession([_FakeResponse({}, status_code=402)])
        chain = [("ZQUSD", "futures", False)]
        result = fetch_price_series(client, chain, "2026-06-01", "2026-06-29", as_of="2026-06-29")
        assert result["error"] == "no_price_source"


def _weekday_dates(start, count):
    dates = []
    d = start
    while len(dates) < count:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += timedelta(days=1)
    return dates


# ---------------------------------------------------------------------------
# P1-2 regression: --as-of is an information cutoff, not just a report
# label. A backdated run must never see prices dated after it -- the fetch
# range intentionally over-requests forward days (PRICE_FETCH_LOOKAHEAD_DAYS)
# so a live/current-date run has real bars near the window edge, but on a
# backdated run those would be real future-relative-to-as_of prices
# (lookahead bias) unless clipped.
# ---------------------------------------------------------------------------


class TestAsOfInformationCutoff:
    def _fetch(self, dates, closes, as_of):
        rows = make_eod_rows(dates, closes)
        client = PriceClient(api_key="fake", sleep_seconds=0.0)
        client.session = _FakeSession([_FakeResponse(rows, status_code=200)])
        return fetch_price_series(
            client, [("ESUSD", "futures", False)], dates[0], dates[-1], as_of=as_of
        )

    def test_fetch_price_series_never_returns_bars_after_as_of(self):
        dates = _weekday_dates(date(2026, 5, 1), 90)
        as_of = dates[69]  # cutoff in the middle of the fetched range
        closes = [100.0 + i * 0.1 for i in range(len(dates))]
        result = self._fetch(dates, closes, as_of)
        assert result["error"] is None
        returned_dates = [d for d, _ in result["series"]]
        assert returned_dates == dates[:70]
        assert all(d <= as_of for d in returned_dates)

    def test_event_one_session_before_as_of_is_insufficient_price_window(self):
        dates = _weekday_dates(date(2026, 5, 1), 90)
        as_of = dates[69]
        closes = [100.0 + i * 0.1 for i in range(len(dates))]
        series = self._fetch(dates, closes, as_of)["series"]
        # Only 1 forward bar (the as_of bar itself) remains in the
        # truncated series -- return_3d needs 2 (close[idx+2]).
        event = make_event(event_time=f"{dates[68]}T10:00:00-04:00")
        record = build_event_record(event, series, "CROWDED_LONG")
        assert record["usable"] is False
        assert record["reason"] == "insufficient_price_window"

    def test_event_four_sessions_before_as_of_is_usable(self):
        dates = _weekday_dates(date(2026, 5, 1), 90)
        as_of = dates[69]
        closes = [100.0 + i * 0.1 for i in range(len(dates))]
        series = self._fetch(dates, closes, as_of)["series"]
        # 4 forward bars remain in the truncated series -- more than
        # enough for the 3-session return_3d window.
        event = make_event(event_time=f"{dates[65]}T10:00:00-04:00")
        record = build_event_record(event, series, "CROWDED_LONG")
        assert record["usable"] is True


# ---------------------------------------------------------------------------
# Detector-json handling: symbol in markets / in skipped / absent / NEUTRAL / stale
# ---------------------------------------------------------------------------


def make_detector_json(as_of="2026-07-12", data_date="2026-07-07", markets=None, skipped=None):
    return {
        "schema_version": "1.0",
        "skill": "cot-contrarian-detector",
        "run_context": {"as_of": as_of, "data_date": data_date},
        "markets": markets or [],
        "skipped": skipped or [],
    }


class TestResolveDirectionFromDetector:
    def test_symbol_present_and_crowded_long(self):
        detector = make_detector_json(markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}])
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction == "CROWDED_LONG"
        assert reason is None

    def test_symbol_present_and_crowded_short(self):
        detector = make_detector_json(markets=[{"symbol": "B6", "classification": "CROWDED_SHORT"}])
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "B6", as_of="2026-07-12", max_age_days=10
        )
        assert direction == "CROWDED_SHORT"
        assert reason is None

    def test_symbol_absent_from_markets_and_skipped(self):
        detector = make_detector_json(markets=[{"symbol": "GC", "classification": "NEUTRAL"}])
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_missing_symbol"

    def test_symbol_in_skipped_list(self):
        detector = make_detector_json(
            markets=[], skipped=[{"symbol": "VX", "reason": "insufficient history"}]
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "VX", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_missing_symbol"

    def test_neutral_classification_refuses_without_explicit_direction(self):
        detector = make_detector_json(markets=[{"symbol": "GC", "classification": "NEUTRAL"}])
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "GC", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "not_crowded"

    def test_stale_detector_json(self):
        detector = make_detector_json(
            as_of="2026-06-01",
            data_date="2026-05-27",
            markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}],
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_json_stale"

    def test_fresh_detector_json_within_max_age(self):
        detector = make_detector_json(
            as_of="2026-07-10",
            data_date="2026-07-07",
            markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}],
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction == "CROWDED_LONG"
        assert reason is None

    # --- P2-3 regression: a detector-json's vintage (data_date) must be
    # trustworthy before the classification it carries is used -- missing,
    # unparsable, or future-dated all fail closed now (an explicit
    # --direction still bypasses this whole function, unchanged).

    def test_missing_data_date_fails_closed(self):
        detector = make_detector_json(
            as_of=None,
            data_date=None,
            markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}],
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_missing_data_date"

    def test_unparsable_data_date_fails_closed(self):
        detector = make_detector_json(
            data_date="not-a-date",
            markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}],
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_invalid_data_date"

    def test_future_dated_data_date_fails_closed(self):
        # data_date after --as-of: the detector claims to know about data
        # from the future relative to this run -- untrustworthy, not just
        # "not stale".
        detector = make_detector_json(
            as_of="2026-07-20",
            data_date="2026-07-15",
            markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}],
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_future_data_date"

    # --- P1 regression: structurally-malformed (valid JSON, wrong shape)
    # detector-json must never crash -- always fail-closed with a reason.

    def test_top_level_list_is_malformed_not_a_crash(self):
        direction, reason, _ctx = resolve_direction_from_detector(
            [], "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "malformed_detector_json"

    def test_top_level_none_is_malformed_not_a_crash(self):
        direction, reason, _ctx = resolve_direction_from_detector(
            None, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "malformed_detector_json"

    def test_top_level_string_is_malformed_not_a_crash(self):
        direction, reason, _ctx = resolve_direction_from_detector(
            "oops", "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "malformed_detector_json"

    def test_markets_not_a_list_is_treated_as_no_markets_not_a_crash(self):
        detector = {"run_context": {}, "markets": "oops", "skipped": []}
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_missing_symbol"

    def test_markets_items_not_dicts_are_skipped_not_a_crash(self):
        detector = {"run_context": {}, "markets": [1, 2, 3, "ES"], "skipped": []}
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_missing_symbol"

    def test_skipped_not_a_list_is_treated_as_empty_not_a_crash(self):
        detector = {
            # data_date present and fresh here so this test isolates the
            # `skipped` shape guard, not the P2-3 data_date checks below.
            "run_context": {"as_of": "2026-07-12", "data_date": "2026-07-07"},
            "markets": [{"symbol": "ES", "classification": "CROWDED_LONG"}],
            "skipped": "oops",
        }
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction == "CROWDED_LONG"
        assert reason is None

    def test_run_context_not_a_dict_is_treated_as_empty_not_a_crash(self):
        # run_context="oops" coerces to {} without crashing -- but that
        # also means no data_date survives, so this now correctly fails
        # closed via the P2-3 guard rather than silently succeeding (there
        # is no way to both ignore an invalid run_context AND trust a
        # data_date that lives inside it).
        detector = {
            "run_context": "oops",
            "markets": [{"symbol": "ES", "classification": "CROWDED_LONG"}],
        }
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_missing_data_date"


# ---------------------------------------------------------------------------
# Events JSON validation
# ---------------------------------------------------------------------------


def make_event(**overrides):
    base = {
        "event_id": "e1",
        "event": "Test headline",
        "event_time": "2026-07-08T14:30:00-04:00",
        "source_url": "https://example.com/a",
        "source_tier": "wire",
        "expected_impact": "BULLISH",
    }
    base.update(overrides)
    return base


class TestValidateEvents:
    def test_valid_event_passes(self):
        events = [make_event()]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert len(valid) == 1
        assert dropped == []

    def test_missing_source_url_is_dropped(self):
        events = [make_event(source_url=None)]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert valid == []
        assert dropped[0]["event_id"] == "e1"
        assert dropped[0]["reason"] == "missing_source_url"

    def test_missing_expected_impact_is_dropped(self):
        events = [make_event(expected_impact=None)]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert valid == []
        assert dropped[0]["reason"] == "missing_expected_impact"

    def test_invalid_expected_impact_value_is_dropped(self):
        events = [make_event(expected_impact="SIDEWAYS")]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert valid == []
        assert dropped[0]["reason"] == "missing_expected_impact"

    def test_unparsable_event_time_is_dropped(self):
        events = [make_event(event_time="not-a-date")]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert valid == []
        assert dropped[0]["reason"] == "unparsable_event_time"

    def test_naive_event_time_is_dropped(self):
        events = [make_event(event_time="2026-07-08T14:30:00")]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert valid == []
        assert dropped[0]["reason"] == "unparsable_event_time"

    def test_event_outside_window_is_dropped(self):
        events = [make_event(event_time="2026-01-01T10:00:00-04:00")]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert valid == []
        assert dropped[0]["reason"] == "outside_window"

    def test_multiple_events_mixed_valid_and_dropped(self):
        events = [
            make_event(event_id="e1"),
            make_event(event_id="e2", source_url=None),
            make_event(event_id="e3", expected_impact="BEARISH"),
        ]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert {e["event_id"] for e in valid} == {"e1", "e3"}
        assert len(dropped) == 1
        assert dropped[0]["event_id"] == "e2"

    # --- P1 regression: items that aren't dicts (e.g. {"events": [1,2,3]})
    # must be dropped individually, never crash the whole run.

    def test_non_dict_items_are_dropped_individually_not_a_crash(self):
        events = [1, "oops", None, make_event(event_id="e1")]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert {e["event_id"] for e in valid} == {"e1"}
        assert len(dropped) == 3
        assert all(d["reason"] == "malformed_event_item" for d in dropped)

    def test_all_items_malformed_yields_no_valid_events_not_a_crash(self):
        events = [1, 2, 3]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert valid == []
        assert len(dropped) == 3

    # --- P3: source_tier not in the 4 allowed values (primary|official|
    # wire|portal) -- keep the event (tier doesn't affect verdict math) but
    # note the anomaly rather than silently accepting or dropping it.

    def test_invalid_source_tier_is_kept_with_note(self):
        events = [make_event(source_tier="rumor")]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert len(valid) == 1
        assert dropped == []
        assert valid[0]["source_tier_invalid"] is True

    def test_missing_source_tier_is_kept_with_note(self):
        events = [make_event(source_tier=None)]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert len(valid) == 1
        assert valid[0]["source_tier_invalid"] is True

    def test_valid_source_tiers_pass_through_without_note(self):
        for tier in ("primary", "official", "wire", "portal"):
            events = [make_event(event_id=tier, source_tier=tier)]
            valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
            assert len(valid) == 1
            assert valid[0].get("source_tier_invalid") is not True

    # --- P2 regression (round-2 re-review): window/as-of comparisons must
    # use the ET calendar date (the same ET used for the 16:00 close
    # cutoff elsewhere), not the raw offset the curator happened to write
    # -- otherwise the same market moment is judged differently by input
    # timezone, and a late-Pacific timestamp that's actually ET-the-next-
    # day admits news-side lookahead.

    def test_late_utc_timestamp_that_is_still_et_evening_is_included(self):
        # 2026-07-13T00:30:00+00:00 = 2026-07-12 20:30 ET -- within as_of
        # 2026-07-12's window. The raw (non-ET) date would read 07-13 and
        # wrongly exclude it.
        events = [make_event(event_time="2026-07-13T00:30:00+00:00")]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert len(valid) == 1
        assert dropped == []

    def test_late_pacific_timestamp_that_is_actually_et_next_day_is_excluded(self):
        # 2026-07-12T23:30:00-07:00 = 2026-07-13 02:30 ET -- AFTER as_of
        # 2026-07-12, i.e. news-side lookahead if admitted. The raw
        # (non-ET) date would read 07-12 and wrongly admit it.
        events = [make_event(event_time="2026-07-12T23:30:00-07:00")]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert valid == []
        assert dropped[0]["reason"] == "outside_window"

    def test_et_native_timestamp_is_unaffected_by_the_normalization(self):
        # Regression sanity check: an already-ET-offset timestamp (the
        # make_event() default, -04:00) behaves identically before and
        # after normalizing through ET.
        events = [make_event(event_time="2026-07-08T14:30:00-04:00")]
        valid, dropped = validate_events(events, as_of="2026-07-12", window_days=10)
        assert len(valid) == 1
        assert dropped == []


# ---------------------------------------------------------------------------
# P1 regression, end-to-end: the CLI itself must never crash on a
# structurally-malformed (valid JSON, wrong shape) --events-json or
# --detector-json -- it must always exit 0 and write a clean
# INSUFFICIENT_EVIDENCE report, exactly like every other fail-closed
# degradation path (no_events_provided, no_price_source, etc.).
# ---------------------------------------------------------------------------


class TestMainFailsClosedOnMalformedInput:
    def _run_cli(self, tmp_path, extra_args, symbol="B6"):
        out_dir = tmp_path / "out"
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "analyze_news_reaction.py"),
            "--symbol",
            symbol,
            "--output-dir",
            str(out_dir),
            "--api-key",
            "FAKE",
            *extra_args,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result, out_dir

    def _report(self, out_dir, symbol="B6"):
        report_files = list(out_dir.glob(f"nrf_{symbol}_*.json"))
        assert len(report_files) == 1, f"expected exactly 1 report, found {report_files}"
        return json.loads(report_files[0].read_text(encoding="utf-8"))

    def _run_main_in_process(
        self,
        tmp_path,
        monkeypatch,
        events,
        fetch_result,
        build_record=None,
        symbol="B6",
    ):
        out_dir = tmp_path / "out"
        events_path = tmp_path / "events.json"
        events_path.write_text(json.dumps({"events": events}), encoding="utf-8")
        args = argparse.Namespace(
            symbol=symbol,
            price_symbol=None,
            direction="CROWDED_SHORT",
            detector_json=None,
            max_detector_age_days=10,
            events_json=str(events_path),
            window_days=10,
            min_events=3,
            z_threshold=0.5,
            drift_z=1.45,
            as_of="2026-07-12",
            output_dir=str(out_dir),
            format="json",
            api_key="FAKE",  # pragma: allowlist secret
            sleep_seconds=0.0,
        )
        monkeypatch.setattr(analyzer, "parse_arguments", lambda: args)
        monkeypatch.setattr(analyzer, "fetch_price_series", lambda *args, **kwargs: fetch_result)
        if build_record is not None:
            monkeypatch.setattr(analyzer, "build_event_record", build_record)

        with pytest.raises(SystemExit) as exc_info:
            analyzer.main()

        assert exc_info.value.code == 0
        return self._report(out_dir, symbol=symbol)

    def test_events_json_top_level_null_exits_0_and_writes_report(self, tmp_path):
        events_path = tmp_path / "events_null.json"
        events_path.write_text("null", encoding="utf-8")

        result, out_dir = self._run_cli(
            tmp_path,
            ["--direction", "CROWDED_SHORT", "--events-json", str(events_path)],
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert payload["verdict_reason"] == "malformed_events_json"

    def test_events_json_events_value_not_a_list_exits_0(self, tmp_path):
        events_path = tmp_path / "events_bad_shape.json"
        events_path.write_text('{"events": "not-a-list"}', encoding="utf-8")

        result, out_dir = self._run_cli(
            tmp_path,
            ["--direction", "CROWDED_SHORT", "--events-json", str(events_path)],
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert payload["verdict_reason"] == "malformed_events_json"

    def test_events_json_items_not_dicts_degrades_to_insufficient_evidence(self, tmp_path):
        # validate_events() itself (unit-tested directly in
        # TestValidateEvents.test_non_dict_items_are_dropped_individually_not_a_crash)
        # already proves [1, 2, 3] are dropped individually as
        # malformed_event_item. Here we only need the CLI-level guarantee:
        # never crash, always exit 0 with a report. An unmapped --symbol
        # short-circuits to the no_price_source INSUFFICIENT_EVIDENCE path
        # before the price-fetch/network layer, so this stays a true
        # no-live-FMP-call test (see module docstring) instead of racing a
        # real HTTP request with a fake API key.
        events_path = tmp_path / "events_bad_items.json"
        events_path.write_text('{"events": [1, 2, 3]}', encoding="utf-8")

        result, out_dir = self._run_cli(
            tmp_path,
            ["--direction", "CROWDED_SHORT", "--events-json", str(events_path)],
            symbol="ZZFAKE",
        )

        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir, symbol="ZZFAKE")
        assert payload["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert payload["verdict_reason"] == "no_price_source"
        assert payload["dropped_events"] == [
            {"event_id": "?", "reason": "malformed_event_item"},
            {"event_id": "?", "reason": "malformed_event_item"},
            {"event_id": "?", "reason": "malformed_event_item"},
        ]

    def test_fetch_failure_preserves_validation_drops(self, tmp_path, monkeypatch):
        events = [make_event(event_id="valid"), make_event(event_id="missing-url", source_url=None)]
        fetch_result = {
            "price_symbol": None,
            "source_kind": None,
            "proxy_used": False,
            "inverted": False,
            "series": [],
            "error": "no_price_source",
        }

        payload = self._run_main_in_process(tmp_path, monkeypatch, events, fetch_result)

        assert payload["verdict_reason"] == "no_price_source"
        assert payload["dropped_events"] == [
            {"event_id": "missing-url", "reason": "missing_source_url"}
        ]

    def test_no_usable_events_preserves_all_accumulated_drops(self, tmp_path, monkeypatch):
        events = [make_event(event_id="valid"), make_event(event_id="missing-url", source_url=None)]
        fetch_result = {
            "price_symbol": "GBPUSD",
            "source_kind": "futures",
            "proxy_used": False,
            "inverted": False,
            "series": [("2026-07-08", 100.0)],
            "error": None,
        }

        def unusable_record(event, series, direction):
            return {"usable": False, "reason": "insufficient_price_history"}

        payload = self._run_main_in_process(
            tmp_path,
            monkeypatch,
            events,
            fetch_result,
            build_record=unusable_record,
        )

        assert payload["verdict_reason"] == "no_usable_events"
        assert payload["dropped_events"] == [
            {"event_id": "missing-url", "reason": "missing_source_url"},
            {"event_id": "valid", "reason": "insufficient_price_history"},
        ]

    def test_detector_json_top_level_list_exits_0(self, tmp_path):
        detector_path = tmp_path / "detector_list.json"
        detector_path.write_text("[]", encoding="utf-8")

        # No --direction here so main() is forced through
        # resolve_direction_from_detector().
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(detector_path)])

        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert payload["verdict_reason"] == "malformed_detector_json"

    def test_detector_json_markets_not_a_list_exits_0(self, tmp_path):
        detector_path = tmp_path / "detector_bad_markets.json"
        detector_path.write_text('{"markets": "oops"}', encoding="utf-8")

        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(detector_path)])

        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert payload["verdict_reason"] == "detector_missing_symbol"

    # --- P1 regression (round-2 re-review): data_date must be a REQUIRED,
    # non-empty string -- no as_of fallback (that would mask a genuinely
    # unknown COT vintage as fresh), and no crash on a non-string value
    # (data_date[:10] used to raise TypeError before it ever reached
    # datetime.strptime's ValueError handler).

    def _detector_json(self, tmp_path, data_date, filename):
        detector = {
            "run_context": {"as_of": "2026-07-12", "data_date": data_date},
            "markets": [{"symbol": "B6", "classification": "CROWDED_SHORT"}],
            "skipped": [],
        }
        path = tmp_path / filename
        path.write_text(json.dumps(detector), encoding="utf-8")
        return path

    def test_detector_json_missing_data_date_is_not_masked_by_as_of(self, tmp_path):
        # run_context.as_of present but NO data_date key at all -- must NOT
        # be silently treated as fresh via an as_of fallback (age computed
        # against as_of would come out exactly 0, hiding a genuinely
        # unknown COT data vintage).
        detector_path = tmp_path / "detector_no_data_date.json"
        detector_path.write_text(
            json.dumps(
                {
                    "run_context": {"as_of": "2026-07-12"},
                    "markets": [{"symbol": "B6", "classification": "CROWDED_SHORT"}],
                    "skipped": [],
                }
            ),
            encoding="utf-8",
        )
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(detector_path)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict"] == "INSUFFICIENT_EVIDENCE"
        assert payload["verdict_reason"] == "detector_missing_data_date"

    def test_detector_json_empty_string_data_date_exits_0(self, tmp_path):
        detector_path = self._detector_json(tmp_path, "", "detector_empty_date.json")
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(detector_path)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict_reason"] == "detector_missing_data_date"

    def test_detector_json_int_data_date_exits_0_not_a_crash(self, tmp_path):
        detector_path = self._detector_json(tmp_path, 123, "detector_int_date.json")
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(detector_path)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict_reason"] == "detector_invalid_data_date"

    def test_detector_json_list_data_date_exits_0_not_a_crash(self, tmp_path):
        detector_path = self._detector_json(tmp_path, ["2026-07-07"], "detector_list_date.json")
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(detector_path)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict_reason"] == "detector_invalid_data_date"

    def test_detector_json_dict_data_date_exits_0_not_a_crash(self, tmp_path):
        detector_path = self._detector_json(
            tmp_path, {"date": "2026-07-07"}, "detector_dict_date.json"
        )
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(detector_path)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict_reason"] == "detector_invalid_data_date"

    def test_detector_json_bool_data_date_exits_0_not_a_crash(self, tmp_path):
        detector_path = self._detector_json(tmp_path, True, "detector_bool_date.json")
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(detector_path)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict_reason"] == "detector_invalid_data_date"


# ---------------------------------------------------------------------------
# Per-event price computation glue (build_event_record)
# ---------------------------------------------------------------------------


class TestBuildEventRecord:
    def _series(self):
        # 60+ trading days before the event (default daily_stdev needs >=20
        # samples, lookback 60) plus a few after, so the event has a real
        # window on both sides.
        dates = []
        d = date(2026, 1, 1)
        while len(dates) < 90:
            if d.weekday() < 5:
                dates.append(d.isoformat())
            d += timedelta(days=1)
        closes = [100.0 + (i % 5) * 0.5 for i in range(len(dates))]
        return list(zip(dates, closes))

    def test_usable_event_produces_full_record(self):
        # Event on the 70th trading day: ~69 days of history before it
        # (>= the 20-sample stdev minimum) and 20 trading days after it.
        event_date = self._series()[69][0]
        event = make_event(event_time=f"{event_date}T10:00:00-04:00")
        record = build_event_record(event, self._series(), "CROWDED_LONG")
        assert record["usable"] is True
        assert record["effective_date"] is not None
        assert record["zscore_3d"] is not None or record["return_3d"] is not None
        assert record["reaction"] in ("RESPONDED", "OPPOSITE", "FAILED_TO_RESPOND", None)

    def test_event_time_after_series_end_is_unusable(self):
        event = make_event(event_time="2099-01-01T10:00:00-04:00")
        record = build_event_record(event, self._series(), "CROWDED_LONG")
        assert record["usable"] is False
        assert record["reason"] is not None

    def test_empty_series_is_unusable(self):
        event = make_event()
        record = build_event_record(event, [], "CROWDED_LONG")
        assert record["usable"] is False


# ---------------------------------------------------------------------------
# Report generation + run_context
# ---------------------------------------------------------------------------


class TestBuildRunContext:
    def test_includes_required_fields(self):
        ctx = build_run_context(
            price_symbol="ESUSD",
            price_source="futures",
            proxy_used=False,
            inverted=False,
            window_days=10,
            min_events=3,
            z_threshold=0.5,
            drift_z=1.45,
            as_of="2026-07-12",
            detector_json="reports/cot_crowding_2026-07-12.json",
            detector_age_days=5,
        )
        for key in (
            "price_symbol",
            "price_source",
            "proxy_used",
            "inverted",
            "window_days",
            "min_events",
            "z_threshold",
            "drift_z",
            "thresholds_doc",
            "as_of",
            "detector_json",
            "detector_age_days",
        ):
            assert key in ctx


class TestReportGeneration:
    def _sample_output(self):
        run_context = build_run_context(
            price_symbol="ESUSD",
            price_source="futures",
            proxy_used=False,
            inverted=False,
            window_days=10,
            min_events=3,
            z_threshold=0.5,
            drift_z=1.45,
            as_of="2026-07-12",
            detector_json=None,
            detector_age_days=None,
        )
        return {
            "schema_version": "1.0",
            "skill": "news-reaction-failure-analyzer",
            "symbol": "ES",
            "direction": "CROWDED_LONG",
            "expected_direction": "BULLISH",
            "actual_reaction": "FAILED_TO_RALLY",
            "verdict": "CONFIRMED",
            "confidence": "HIGH",
            "relevant_events_used": 4,
            "aggregate": {"mean_z3": -1.5, "drift_stat": -3.0, "responded_ratio": 0.0},
            "evidence": [
                {
                    "event_id": "e1",
                    "event": "Fed cuts rates",
                    "source_url": "https://example.com",
                    "event_time": "2026-07-08T14:30:00-04:00",
                    "expected_impact": "BULLISH",
                    "effective_date": "2026-07-08",
                    "return_1d": -0.2,
                    "return_3d": -1.1,
                    "zscore_1d": -0.31,
                    "zscore_3d": -0.90,
                    "reaction": "OPPOSITE",
                }
            ],
            "dropped_events": [{"event_id": "e9", "reason": "missing_source_url"}],
            "run_context": run_context,
        }

    def test_json_report_matches_schema(self, tmp_path):
        output = self._sample_output()
        out = tmp_path / "nrf_ES_2026-07-12.json"
        generate_json_report(output, str(out))
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["verdict"] == "CONFIRMED"
        assert payload["actual_reaction"] == "FAILED_TO_RALLY"
        assert payload["run_context"]["price_symbol"] == "ESUSD"
        assert payload["evidence"][0]["event"] == "Fed cuts rates"

    def test_markdown_report_has_expected_sections(self, tmp_path):
        output = self._sample_output()
        out = tmp_path / "nrf_ES_2026-07-12.md"
        generate_markdown_report(output, str(out))
        text = out.read_text(encoding="utf-8")
        assert "CONFIRMED" in text
        assert "FAILED_TO_RALLY" in text
        assert "Fed cuts rates" in text

    # --- P3 follow-up: source_tier_invalid must survive into the
    # user-facing report, not just validate_events()'s return value.

    def test_json_report_includes_source_tier_invalid_flag(self, tmp_path):
        output = self._sample_output()
        output["evidence"][0]["source_tier"] = "rumor"
        output["evidence"][0]["source_tier_invalid"] = True
        out = tmp_path / "nrf_ES_2026-07-12.json"
        generate_json_report(output, str(out))
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["evidence"][0]["source_tier_invalid"] is True

    def test_markdown_report_flags_invalid_source_tier_with_asterisk(self, tmp_path):
        output = self._sample_output()
        output["evidence"][0]["source_tier"] = "rumor"
        output["evidence"][0]["source_tier_invalid"] = True
        out = tmp_path / "nrf_ES_2026-07-12.md"
        generate_markdown_report(output, str(out))
        text = out.read_text(encoding="utf-8")
        assert "rumor*" in text
        assert "source_tier not in" in text

    def test_markdown_report_omits_tier_footnote_when_all_tiers_valid(self, tmp_path):
        output = self._sample_output()
        out = tmp_path / "nrf_ES_2026-07-12.md"
        generate_markdown_report(output, str(out))
        text = out.read_text(encoding="utf-8")
        assert "source_tier not in" not in text


# ---------------------------------------------------------------------------
# API key redaction (self-contained copy of the cot-contrarian-detector
# pattern: value-based primary + pattern-family secondary, all 4 leak forms)
# ---------------------------------------------------------------------------


class TestRedact:
    def test_redacts_apikey_query_string(self):
        result = _redact("GET /x?apikey=SECRETKEY123&symbol=ES")
        assert "SECRETKEY123" not in result
        assert "***REDACTED***" in result

    def test_redacts_json_form(self):
        result = _redact('{"apikey": "SECRETKEY123"}')
        assert "SECRETKEY123" not in result

    def test_redacts_single_quoted_mixed_case_form(self):
        result = _redact("{'apiKey': 'SECRETKEY123'}")
        assert "SECRETKEY123" not in result

    def test_redacts_url_encoded_form(self):
        result = _redact("apikey%3DSECRETKEY123")
        assert "SECRETKEY123" not in result

    def test_redacts_spaced_form(self):
        result = _redact("apikey = SECRETKEY123")
        assert "SECRETKEY123" not in result

    def test_value_based_redaction_catches_bare_key_with_no_marker(self):
        text = "Invalid credential: SECRETKEY123"
        secret = "SECRETKEY123"  # pragma: allowlist secret
        assert "SECRETKEY123" in _redact(text)  # pattern-based alone misses it
        assert secret not in _redact(text, secret=secret)

    def test_empty_and_none_secret_safe(self):
        text = "plain error"
        assert _redact(text, secret=None) == text
        assert _redact(text, secret="") == text


class TestPriceClientRedaction:
    SECRET = "SECRETKEY123"  # pragma: allowlist secret

    def test_connection_error_redacted(self, capsys):
        client = PriceClient(api_key=self.SECRET, sleep_seconds=0.0)
        secret = self.SECRET

        class _RaisingSession:
            def get(self, url, params=None, timeout=None):
                raise requests.exceptions.ConnectionError(
                    f"Max retries exceeded with url: /x?apikey={secret} (Caused by ...)"
                )

        client.session = _RaisingSession()
        import analyze_news_reaction as mod

        original_sleep = mod.time.sleep
        mod.time.sleep = lambda _s: None
        try:
            rows, error = client.get_eod_rows("ESUSD", "2026-06-01", "2026-06-29")
        finally:
            mod.time.sleep = original_sleep
        assert rows is None
        assert self.SECRET not in error
        assert "***REDACTED***" in error
        captured = capsys.readouterr()
        assert self.SECRET not in captured.err
