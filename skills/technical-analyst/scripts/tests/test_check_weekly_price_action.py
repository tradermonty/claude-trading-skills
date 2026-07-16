"""Tests for check_weekly_price_action.py -- CLI logic (price-source fallback
chain, detector-json guards, redaction, report generation).

Network calls are stubbed out with a fake `requests.Session`; no live FMP
calls are made here. Run with:
    python3 -m pytest skills/technical-analyst/scripts/tests/test_check_weekly_price_action.py -v
"""

from __future__ import annotations

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

from check_weekly_price_action import (  # noqa: E402
    PRICE_SOURCE_CHAINS,
    PriceClient,
    _min_weeks_type,
    _redact,
    build_run_context,
    fetch_price_series,
    generate_json_report,
    generate_markdown_report,
    load_json_file,
    resolve_direction_from_detector,
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
    return [
        {
            "symbol": "X",
            "date": d,
            "open": c,
            "high": c + 0.5,
            "low": c - 0.5,
            "close": c,
            "volume": 100,
        }
        for d, c in zip(dates, closes)
    ]


def _weekday_dates(start, count):
    dates = []
    d = start
    while len(dates) < count:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += timedelta(days=1)
    return dates


# ---------------------------------------------------------------------------
# Price-source fallback chain
# ---------------------------------------------------------------------------


class TestPriceSourceChains:
    def test_representative_symbols_documented(self):
        for symbol in ("ES", "NQ", "VX", "GC", "CL", "ZN", "DX", "B6", "BT"):
            assert symbol in PRICE_SOURCE_CHAINS

    def test_chain_entries_are_3_tuples(self):
        for chain in PRICE_SOURCE_CHAINS.values():
            for entry in chain:
                assert len(entry) == 3
                symbol, kind, invert = entry
                assert kind in ("futures", "etf")
                assert isinstance(invert, bool)


class TestFetchPriceSeries:
    def test_primary_success_no_proxy(self):
        client = PriceClient(api_key="fake", sleep_seconds=0.0)
        dates = _weekday_dates(date(2026, 1, 1), 90)
        closes = [100 + i * 0.3 for i in range(len(dates))]
        rows = make_eod_rows(dates, closes)
        client.session = _FakeSession([_FakeResponse(rows, status_code=200)])
        chain = [("ESUSD", "futures", False)]
        result = fetch_price_series(client, chain, dates[0], dates[-1], as_of=dates[-1])
        assert result["error"] is None
        assert result["price_symbol"] == "ESUSD"
        assert result["proxy_used"] is False
        assert len(result["daily_bars"]) == len(dates)

    def test_402_falls_back_to_etf_proxy(self):
        client = PriceClient(api_key="fake", sleep_seconds=0.0)
        dates = _weekday_dates(date(2026, 1, 1), 90)
        closes = [100 + i * 0.3 for i in range(len(dates))]
        rows = make_eod_rows(dates, closes)
        client.session = _FakeSession(
            [
                _FakeResponse({"error": "restricted"}, status_code=402),
                _FakeResponse(rows, status_code=200),
            ]
        )
        chain = [("NQUSD", "futures", False), ("QQQ", "etf", False)]
        result = fetch_price_series(client, chain, dates[0], dates[-1], as_of=dates[-1])
        assert result["error"] is None
        assert result["price_symbol"] == "QQQ"
        assert result["proxy_used"] is True

    def test_zero_rows_is_treated_as_failure_and_advances_chain(self):
        client = PriceClient(api_key="fake", sleep_seconds=0.0)
        dates = _weekday_dates(date(2026, 1, 1), 90)
        closes = [100 + i * 0.3 for i in range(len(dates))]
        rows = make_eod_rows(dates, closes)
        client.session = _FakeSession(
            [
                _FakeResponse([], status_code=200),
                _FakeResponse(rows, status_code=200),
            ]
        )
        chain = [("VXUSD", "futures", False), ("SOMEPROXY", "etf", False)]
        result = fetch_price_series(client, chain, dates[0], dates[-1], as_of=dates[-1])
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
        result = fetch_price_series(client, chain, "2026-01-01", "2026-03-01", as_of="2026-03-01")
        assert result["error"] == "no_price_source"
        assert result["daily_bars"] == []
        assert len(result["attempts"]) == 2

    def test_field_fallback_close_or_price(self):
        # `full` endpoint uses close; verify the fallback to `price` (light
        # endpoint's field) still works if a chain member returns that shape.
        client = PriceClient(api_key="fake", sleep_seconds=0.0)
        dates = _weekday_dates(date(2026, 1, 1), 40)
        rows = [
            {"date": d, "open": 1, "high": 2, "low": 0.5, "price": 1.5, "volume": 10} for d in dates
        ]
        client.session = _FakeSession([_FakeResponse(rows, status_code=200)])
        chain = [("XUSD", "futures", False)]
        result = fetch_price_series(client, chain, dates[0], dates[-1], as_of=dates[-1])
        assert result["error"] is None
        assert result["daily_bars"][0]["close"] == 1.5


class TestAsOfInformationCutoff:
    def test_daily_bars_never_include_dates_after_as_of(self):
        client = PriceClient(api_key="fake", sleep_seconds=0.0)
        dates = _weekday_dates(date(2026, 1, 1), 90)
        closes = [100.0 + i * 0.1 for i in range(len(dates))]
        rows = make_eod_rows(dates, closes)
        client.session = _FakeSession([_FakeResponse(rows, status_code=200)])
        as_of = dates[69]
        result = fetch_price_series(
            client, [("ESUSD", "futures", False)], dates[0], dates[-1], as_of=as_of
        )
        returned_dates = [b["date"] for b in result["daily_bars"]]
        assert returned_dates == dates[:70]
        assert all(d <= as_of for d in returned_dates)


# ---------------------------------------------------------------------------
# load_json_file: distinguishes an unreadable/missing file from a
# syntactically-invalid one (P1 regression, user re-review of PR #247) so
# main() can route each to its own named, fail-closed reason instead of
# exiting 1 with no report for either.
# ---------------------------------------------------------------------------


class TestLoadJsonFile:
    def test_missing_file_returns_unreadable_reason(self, tmp_path):
        data, error, reason = load_json_file(str(tmp_path / "does_not_exist.json"))
        assert data is None
        assert error is not None
        assert reason == "unreadable"

    def test_invalid_json_syntax_returns_parse_error_reason(self, tmp_path):
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("{bad json", encoding="utf-8")
        data, error, reason = load_json_file(str(bad_path))
        assert data is None
        assert error is not None
        assert reason == "parse_error"

    def test_valid_json_returns_no_error_or_reason(self, tmp_path):
        good_path = tmp_path / "good.json"
        good_path.write_text('{"a": 1}', encoding="utf-8")
        data, error, reason = load_json_file(str(good_path))
        assert data == {"a": 1}
        assert error is None
        assert reason is None

    # --- Residual P1 (user re-review round 2 of PR #247): a file that is
    # readable but NOT valid UTF-8 raises UnicodeDecodeError -- a
    # ValueError subclass, NOT an OSError -- so it used to escape the
    # `except OSError` clause entirely and crash with a traceback instead
    # of failing closed. UnicodeDecodeError IS a UnicodeError, so
    # `except (OSError, UnicodeError)` catches both without widening the
    # net to unrelated exception types (e.g. MemoryError still propagates,
    # which is correct -- that's not a "this input is bad" condition).

    def test_non_utf8_bytes_returns_unreadable_reason_not_a_crash(self, tmp_path):
        binary_path = tmp_path / "binary.json"
        binary_path.write_bytes(b"\xff\xfe\x00bad")
        data, error, reason = load_json_file(str(binary_path))
        assert data is None
        assert error is not None
        assert reason == "unreadable"

    def test_directory_path_returns_unreadable_reason_not_a_crash(self, tmp_path):
        # IsADirectoryError is an OSError subclass -- already covered by
        # the existing `except OSError`, but cheap to pin explicitly since
        # it's the same "can we even open this as a file" question as the
        # missing-file and non-UTF-8 cases above.
        dir_path = tmp_path / "a_directory"
        dir_path.mkdir()
        data, error, reason = load_json_file(str(dir_path))
        assert data is None
        assert error is not None
        assert reason == "unreadable"


# ---------------------------------------------------------------------------
# Detector-json handling (verbatim behavior copy of #245's hardened guards)
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
        detector = make_detector_json(markets=[{"symbol": "BT", "classification": "CROWDED_LONG"}])
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "BT", as_of="2026-07-12", max_age_days=10
        )
        assert direction == "CROWDED_LONG"
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

    def test_missing_data_date_fails_closed_no_as_of_fallback(self):
        detector = make_detector_json(
            as_of="2026-07-12",
            data_date=None,
            markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}],
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_missing_data_date"

    def test_empty_string_data_date_fails_closed(self):
        detector = make_detector_json(
            data_date="", markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}]
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_missing_data_date"

    def test_non_string_data_date_int_fails_closed_not_a_crash(self):
        detector = make_detector_json(
            data_date=123, markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}]
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_invalid_data_date"

    def test_non_string_data_date_list_fails_closed_not_a_crash(self):
        detector = make_detector_json(
            data_date=["2026-07-07"], markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}]
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_invalid_data_date"

    def test_non_string_data_date_dict_fails_closed_not_a_crash(self):
        detector = make_detector_json(
            data_date={"date": "2026-07-07"},
            markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}],
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_invalid_data_date"

    def test_non_string_data_date_bool_fails_closed_not_a_crash(self):
        detector = make_detector_json(
            data_date=True, markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}]
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_invalid_data_date"

    def test_unparsable_data_date_fails_closed(self):
        detector = make_detector_json(
            data_date="not-a-date", markets=[{"symbol": "ES", "classification": "CROWDED_LONG"}]
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "ES", as_of="2026-07-12", max_age_days=10
        )
        assert direction is None
        assert reason == "detector_invalid_data_date"

    def test_future_dated_data_date_fails_closed(self):
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

    def test_fresh_detector_json_within_max_age(self):
        detector = make_detector_json(
            as_of="2026-07-10",
            data_date="2026-07-07",
            markets=[{"symbol": "BT", "classification": "CROWDED_LONG"}],
        )
        direction, reason, _ctx = resolve_direction_from_detector(
            detector, "BT", as_of="2026-07-12", max_age_days=10
        )
        assert direction == "CROWDED_LONG"
        assert reason is None

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

    def test_run_context_not_a_dict_is_treated_as_empty_not_a_crash(self):
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
# CLI end-to-end: fail-closed behavior, output filenames
# ---------------------------------------------------------------------------


class TestMainFailsClosedOnMalformedInput:
    def _run_cli(self, tmp_path, extra_args, symbol="ZZFAKE", as_of="2026-07-12"):
        out_dir = tmp_path / "out"
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "check_weekly_price_action.py"),
            "--symbol",
            symbol,
            "--as-of",
            as_of,
            "--output-dir",
            str(out_dir),
            "--api-key",
            "FAKE",
            *extra_args,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result, out_dir

    def _report(self, out_dir, symbol="ZZFAKE", as_of="2026-07-12"):
        report_files = list(out_dir.glob(f"ta_confirmation_{symbol}_{as_of}.json"))
        assert len(report_files) == 1, f"expected exactly 1 report, found {report_files}"
        return json.loads(report_files[0].read_text(encoding="utf-8"))

    def _run_main_no_network(
        self, monkeypatch, tmp_path, extra_args, symbol="ZZFAKE", as_of="2026-07-12"
    ):
        """In-process `main()` invocation with `PriceClient.get_eod_rows`
        monkeypatched to fail immediately -- no real HTTP request is ever
        constructed (the real method body, including `requests.Session`,
        never executes). Unlike the subprocess-based `_run_cli` helper,
        this stays hermetic (offline-safe, no 429/5xx retry-storm risk)
        for the two tests below that exercise a genuine price-fetch
        failure rather than short-circuiting before it (code review P2-2)."""
        import check_weekly_price_action as mod

        out_dir = tmp_path / "out"
        monkeypatch.setattr(
            mod.PriceClient,
            "get_eod_rows",
            lambda self, symbol, from_date, to_date: (None, "HTTP 401: unauthorized"),
        )
        argv = [
            "check_weekly_price_action.py",
            "--symbol",
            symbol,
            "--as-of",
            as_of,
            "--output-dir",
            str(out_dir),
            "--api-key",
            "FAKE",
            *extra_args,
        ]
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as exc_info:
            mod.main()
        return exc_info.value.code, out_dir

    def test_unmapped_symbol_with_explicit_direction_is_no_price_source(
        self, monkeypatch, tmp_path
    ):
        code, out_dir = self._run_main_no_network(
            monkeypatch, tmp_path, ["--direction", "CROWDED_LONG"]
        )
        assert code == 0
        payload = self._report(out_dir)
        assert payload["verdict"] == "INSUFFICIENT_DATA"
        assert payload["verdict_reason"] == "no_price_source"
        assert payload["mode"] == "data"

    def test_output_filename_pattern(self, monkeypatch, tmp_path):
        code, out_dir = self._run_main_no_network(
            monkeypatch, tmp_path, ["--direction", "CROWDED_SHORT"], symbol="ZQ", as_of="2026-05-01"
        )
        assert code == 0
        json_path = out_dir / "ta_confirmation_ZQ_2026-05-01.json"
        md_path = out_dir / "ta_confirmation_ZQ_2026-05-01.md"
        assert json_path.is_file()
        assert md_path.is_file()

    def test_no_direction_no_detector_is_insufficient_data(self, tmp_path):
        result, out_dir = self._run_cli(tmp_path, [])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict"] == "INSUFFICIENT_DATA"
        assert payload["verdict_reason"] == "no_direction_provided"

    # --- P1 regression (user re-review of PR #247): a missing or
    # syntactically-invalid --detector-json file used to exit 1 with NO
    # report -- violating SKILL.md's own fail-closed contract
    # (INSUFFICIENT_DATA / no crash / exit 0 / report written). Neither
    # case touches the network (both fail before direction resolution
    # reaches the price-fetch stage), so subprocess is safe here, same as
    # the other malformed-input tests in this class.

    def test_detector_json_missing_file_is_insufficient_data_exit_0(self, tmp_path):
        nonexistent_path = tmp_path / "does_not_exist.json"
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(nonexistent_path)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict"] == "INSUFFICIENT_DATA"
        assert payload["verdict_reason"] == "detector_json_unreadable"

    def test_detector_json_invalid_syntax_is_insufficient_data_exit_0(self, tmp_path):
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("{bad json", encoding="utf-8")
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(bad_path)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict"] == "INSUFFICIENT_DATA"
        assert payload["verdict_reason"] == "detector_json_parse_error"

    # --- Residual P1 (user re-review round 2 of PR #247): a readable but
    # non-UTF-8 --detector-json file raises UnicodeDecodeError, which
    # `except OSError` alone does not catch -- used to crash with a
    # traceback and exit 1, no report. Repro exactly as given: a raw byte
    # sequence that is not valid UTF-8.

    def test_detector_json_non_utf8_bytes_is_insufficient_data_exit_0_no_traceback(self, tmp_path):
        binary_path = tmp_path / "binary.json"
        binary_path.write_bytes(b"\xff\xfe\x00bad")
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(binary_path)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Traceback" not in result.stderr
        payload = self._report(out_dir)
        assert payload["verdict"] == "INSUFFICIENT_DATA"
        assert payload["verdict_reason"] == "detector_json_unreadable"

    def test_detector_json_top_level_list_exits_0(self, tmp_path):
        detector_path = tmp_path / "detector_list.json"
        detector_path.write_text("[]", encoding="utf-8")
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(detector_path)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict"] == "INSUFFICIENT_DATA"
        assert payload["verdict_reason"] == "malformed_detector_json"

    def test_detector_json_missing_data_date_not_masked_by_as_of(self, tmp_path):
        detector_path = tmp_path / "detector_no_date.json"
        detector_path.write_text(
            json.dumps(
                {
                    "run_context": {"as_of": "2026-07-12"},
                    "markets": [{"symbol": "ZZFAKE", "classification": "CROWDED_SHORT"}],
                    "skipped": [],
                }
            ),
            encoding="utf-8",
        )
        result, out_dir = self._run_cli(tmp_path, ["--detector-json", str(detector_path)])
        assert result.returncode == 0, f"stderr: {result.stderr}"
        payload = self._report(out_dir)
        assert payload["verdict_reason"] == "detector_missing_data_date"

    def test_missing_api_key_exits_nonzero_with_redacted_message(self, tmp_path):
        out_dir = tmp_path / "out"
        cmd = [
            sys.executable,
            str(SCRIPT_DIR / "check_weekly_price_action.py"),
            "--symbol",
            "BT",
            "--direction",
            "CROWDED_LONG",
            "--as-of",
            "2026-07-12",
            "--output-dir",
            str(out_dir),
        ]
        env = {"PATH": "/usr/bin:/bin"}  # no FMP_API_KEY
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, env=env)
        assert result.returncode != 0
        assert "api-key" in result.stderr.lower() or "api_key" in result.stderr.lower()


# ---------------------------------------------------------------------------
# --min-weeks lower-bound validation (code review P3): min_weeks=0 (or
# negative) would otherwise skip the `n < min_weeks` floor check entirely
# (0 < 0 is False), so empty/near-empty price data would emit NOT_CONFIRMED
# instead of the correct INSUFFICIENT_DATA.
# ---------------------------------------------------------------------------


class TestMinWeeksValidation:
    def test_positive_int_type_accepts_valid_values(self):
        assert _min_weeks_type("1") == 1
        assert _min_weeks_type("30") == 30

    def test_positive_int_type_rejects_zero(self):
        with pytest.raises(argparse.ArgumentTypeError):
            _min_weeks_type("0")

    def test_positive_int_type_rejects_negative(self):
        with pytest.raises(argparse.ArgumentTypeError):
            _min_weeks_type("-5")

    def test_positive_int_type_rejects_non_integer(self):
        with pytest.raises(argparse.ArgumentTypeError):
            _min_weeks_type("abc")

    def test_cli_rejects_min_weeks_zero_with_clear_error(self, monkeypatch, tmp_path, capsys):
        import check_weekly_price_action as mod

        argv = [
            "check_weekly_price_action.py",
            "--symbol",
            "BT",
            "--direction",
            "CROWDED_LONG",
            "--as-of",
            "2026-07-12",
            "--output-dir",
            str(tmp_path / "out"),
            "--api-key",
            "FAKE",
            "--min-weeks",
            "0",
        ]
        monkeypatch.setattr(sys, "argv", argv)
        with pytest.raises(SystemExit) as exc_info:
            mod.parse_arguments()
        assert exc_info.value.code == 2  # argparse's usage-error exit code
        captured = capsys.readouterr()
        assert "min-weeks" in captured.err
        assert ">= 1" in captured.err or "at least 1" in captured.err


# ---------------------------------------------------------------------------
# Report generation + run_context
# ---------------------------------------------------------------------------


class TestBuildRunContext:
    def test_includes_required_fields(self):
        ctx = build_run_context(
            price_symbol="BTCUSD",
            price_source="futures",
            proxy_used=False,
            as_of="2026-07-12",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=4,
            min_weeks=30,
            detector_json=None,
            detector_age_days=None,
        )
        for key in (
            "price_symbol",
            "price_source",
            "proxy_used",
            "as_of",
            "lookbacks",
            "recency",
            "min_weeks",
            "detector_json",
            "detector_age_days",
            "schema_version",
        ):
            assert key in ctx
        assert ctx["schema_version"] == "1.0"
        assert ctx["lookbacks"]["swing_lookback_weeks"] == 13
        assert ctx["lookbacks"]["extreme_lookback_weeks"] == 52
        assert ctx["recency"]["signal_recency_weeks"] == 4


class TestReportGeneration:
    def _sample_output(self):
        run_context = build_run_context(
            price_symbol="BTCUSD",
            price_source="futures",
            proxy_used=False,
            as_of="2026-07-12",
            swing_lookback_weeks=13,
            extreme_lookback_weeks=52,
            signal_recency_weeks=4,
            min_weeks=30,
            detector_json=None,
            detector_age_days=None,
        )
        return {
            "symbol": "BT",
            "direction": "CROWDED_LONG",
            "mode": "data",
            "verdict": "CONFIRMED",
            "confidence": "HIGH",
            "verdict_reason": "key_reversal",
            "checks": {
                "weekly_key_reversal": {
                    "triggered": True,
                    "week_of": "2026-07-06",
                    "swing_window_weeks_used": 13,
                    "extreme_window_weeks_used": 52,
                    "is_full_window_extreme": True,
                    "detail": "x",
                },
                "failed_extreme": {
                    "triggered": False,
                    "attempted_level": None,
                    "week_of": None,
                    "window_weeks_used": None,
                    "detail": "x",
                },
                "failed_breakout": {
                    "triggered": False,
                    "breakout_level": None,
                    "week_of": None,
                    "window_weeks_used": None,
                    "detail": "x",
                },
                "continuation": {
                    "new_closing_extreme_with_crowd": False,
                    "week_of": None,
                    "window_weeks_used": None,
                },
            },
            "swing_levels": {
                "nearest_swing_high": {"price": 120.0, "week_of": "2026-06-01", "fallback": False},
                "nearest_swing_low": {"price": 90.0, "week_of": "2026-05-01", "fallback": False},
                "stop_reference": 120.0,
            },
            "weekly_bars_used": 60,
            "last_completed_week": "2026-07-06",
            "handoff": {
                "price_action": {
                    "verdict": "CONFIRMED",
                    "confidence": "HIGH",
                    "stop_reference": 120.0,
                    "report_path": "reports/ta_confirmation_BT_2026-07-12.json",
                }
            },
            "run_context": run_context,
        }

    def test_json_report_matches_schema(self, tmp_path):
        output = self._sample_output()
        out = tmp_path / "ta_confirmation_BT_2026-07-12.json"
        generate_json_report(output, str(out))
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["verdict"] == "CONFIRMED"
        assert payload["run_context"]["price_symbol"] == "BTCUSD"
        assert payload["handoff"]["price_action"]["stop_reference"] == 120.0

    def test_markdown_report_has_expected_sections(self, tmp_path):
        output = self._sample_output()
        out = tmp_path / "ta_confirmation_BT_2026-07-12.md"
        generate_markdown_report(output, str(out))
        text = out.read_text(encoding="utf-8")
        assert "CONFIRMED" in text
        assert "BT" in text
        assert "key_reversal" in text


# ---------------------------------------------------------------------------
# API key redaction (self-contained copy of the #245 pattern)
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
        assert "SECRETKEY123" in _redact(text)
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
        import check_weekly_price_action as mod

        original_sleep = mod.time.sleep
        mod.time.sleep = lambda _s: None
        try:
            rows, error = client.get_eod_rows("BTCUSD", "2026-06-01", "2026-06-29")
        finally:
            mod.time.sleep = original_sleep
        assert rows is None
        assert self.SECRET not in error
        assert "***REDACTED***" in error
        captured = capsys.readouterr()
        assert self.SECRET not in captured.err
