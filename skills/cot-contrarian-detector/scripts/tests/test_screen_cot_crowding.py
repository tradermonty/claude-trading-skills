"""Tests for screen_cot_crowding.py — CLI logic (universe, analysis, reports).

Network calls are stubbed out with a fake `requests.Session`; no live FMP
calls are made here. Run with:
    python3 -m pytest skills/cot-contrarian-detector/scripts/tests/ -v
"""

import json
import sys
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from screen_cot_crowding import (  # noqa: E402
    CORE_SYMBOLS,
    CotClient,
    _redact,
    analyze_market,
    build_run_context,
    generate_json_report,
    generate_markdown_report,
    parse_symbols_arg,
    resolve_data_date,
    resolve_universe,
)


def make_row(date_str: str, long_pos: int, short_pos: int, oi: int = 2_000_000) -> dict:
    """Build one weekly report row using the exact FMP legacy field names."""
    return {
        "date": date_str,
        "name": "S&P 500 E-Mini (ES)",
        "sector": "INDICES",
        "contractUnits": "$50 x Index",
        "openInterestAll": oi,
        "noncommPositionsLongAll": long_pos,
        "noncommPositionsShortAll": short_pos,
        "pctOfOiNoncommLongAll": 5.0,
        "pctOfOiNoncommShortAll": 7.0,
        "tradersNoncommLongAll": 100,
        "tradersNoncommShortAll": 90,
    }


def default_args(**overrides) -> Namespace:
    base = dict(
        symbols=None,
        core=False,
        lookback_weeks=156,
        short_lookback_weeks=26,
        threshold_high=90.0,
        threshold_low=10.0,
        as_of="2026-07-07",
        output_dir="reports/",
        sleep_seconds=0.0,
        format="both",
        api_key=None,
    )
    base.update(overrides)
    return Namespace(**base)


class TestParseSymbolsArg:
    def test_splits_and_uppercases(self):
        assert parse_symbols_arg("es, gc,cl") == ["ES", "GC", "CL"]

    def test_drops_empty_entries(self):
        assert parse_symbols_arg("ES,,GC,") == ["ES", "GC"]


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


class _RaisingSession:
    """Session whose .get() always raises the given exception (retried until
    max_retries is exhausted, exercising the exception-message redaction path)."""

    def __init__(self, exc):
        self.exc = exc
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        raise self.exc


class TestResolveUniverse:
    def test_explicit_symbols(self):
        args = default_args(symbols="es,gc")
        client = CotClient(api_key="fake", sleep_seconds=0.0)
        symbols, mode = resolve_universe(args, client)
        assert symbols == ["ES", "GC"]
        assert mode == "explicit_symbols"

    def test_core_subset(self):
        args = default_args(core=True)
        client = CotClient(api_key="fake", sleep_seconds=0.0)
        symbols, mode = resolve_universe(args, client)
        assert symbols == CORE_SYMBOLS
        assert mode == "core"

    def test_all_markets_fetches_list(self):
        args = default_args()
        client = CotClient(api_key="fake", sleep_seconds=0.0)
        client.session = _FakeSession(
            [
                _FakeResponse(
                    [
                        {"symbol": "ES", "name": "S&P 500 E-Mini (ES)"},
                        {"symbol": "GC", "name": "Gold"},
                    ]
                )
            ]
        )
        symbols, mode = resolve_universe(args, client)
        assert symbols == ["ES", "GC"]
        assert mode == "all_markets"


class TestAnalyzeMarket:
    def test_fetch_error_is_skipped_with_reason(self):
        args = default_args()
        result = analyze_market("ES", [], "HTTP 500", args)
        assert result["status"] == "skipped"
        assert "HTTP 500" in result["reason"]

    def test_empty_rows_is_skipped(self):
        args = default_args()
        result = analyze_market("ES", [], None, args)
        assert result["status"] == "skipped"
        assert "no data" in result["reason"]

    def test_insufficient_history_below_short_lookback_is_skipped(self):
        args = default_args(short_lookback_weeks=26)
        rows = [make_row(f"2026-0{i}-01 00:00:00", 100 + i, 90, 2_000_000) for i in range(1, 6)]
        result = analyze_market("ES", rows, None, args)
        assert result["status"] == "skipped"
        assert "insufficient history" in result["reason"]
        assert result["weeks_available"] == 5

    def test_insufficient_history_below_primary_lookback_is_skipped(self):
        # 30 distinct weekly Tuesdays available, short_lookback=26 (met) but
        # primary lookback=156 (not met).
        start = date(2026, 1, 6)
        rows = [
            make_row(f"{(start + timedelta(weeks=i)).isoformat()} 00:00:00", 100 + i, 90)
            for i in range(30)
        ]
        args = default_args(lookback_weeks=156, short_lookback_weeks=26)
        result = analyze_market("ES", rows, None, args)
        assert result["status"] == "skipped"
        assert "insufficient history: 30/156" in result["reason"]

    def test_ok_result_shape_and_classification(self):
        args = default_args(
            lookback_weeks=4, short_lookback_weeks=2, threshold_high=90.0, threshold_low=10.0
        )
        rows = [
            make_row("2026-06-02 00:00:00", 100, 200),  # net -100 (min)
            make_row("2026-06-09 00:00:00", 150, 200),  # net -50
            make_row("2026-06-16 00:00:00", 180, 200),  # net -20
            make_row(
                "2026-06-23 00:00:00", 244103, 286994
            ),  # net -42891 (current, but not extreme in this window)
        ]
        # Overwrite last row to make current == window max so it classifies CROWDED_LONG
        rows[-1] = make_row("2026-06-23 00:00:00", 300, 200)  # net +100 (max)
        result = analyze_market("ES", rows, None, args)
        assert result["status"] == "ok"
        assert result["symbol"] == "ES"
        assert result["net_position"] == 100
        assert result["cot_index_3y"] == 100.0
        assert result["classification"] == "CROWDED_LONG"
        assert result["week_over_week_change"] == 100 - (-20)
        assert result["oi_normalized_net"] == 100 / 2_000_000

    def test_sorts_and_dedupes_before_computing(self):
        args = default_args(lookback_weeks=2, short_lookback_weeks=2)
        rows = [
            make_row("2026-06-09 00:00:00", 999, 0),  # stale duplicate, should be overwritten
            make_row("2026-06-02 00:00:00", 10, 5),  # net 5
            make_row("2026-06-09 00:00:00", 20, 5),  # net 15 (final value for this date)
        ]
        result = analyze_market("ES", rows, None, args)
        assert result["status"] == "ok"
        assert result["net_position"] == 15
        assert result["weeks_available"] == 2


class TestResolveDataDate:
    def test_returns_most_common_date(self):
        results = [
            {"status": "ok", "data_date": "2026-07-07"},
            {"status": "ok", "data_date": "2026-07-07"},
            {"status": "ok", "data_date": "2026-06-30"},
            {"status": "skipped"},
        ]
        assert resolve_data_date(results) == "2026-07-07"

    def test_no_ok_results_returns_none(self):
        assert resolve_data_date([{"status": "skipped"}]) is None


class TestReportGeneration:
    def _sample_results(self):
        args = default_args(lookback_weeks=4, short_lookback_weeks=2)
        rows_long = [
            make_row("2026-06-02 00:00:00", 100, 200),
            make_row("2026-06-09 00:00:00", 150, 200),
            make_row("2026-06-16 00:00:00", 180, 200),
            make_row("2026-06-23 00:00:00", 300, 200),  # net +100, max -> CROWDED_LONG
        ]
        rows_short = [
            make_row("2026-06-02 00:00:00", 200, 100),
            make_row("2026-06-09 00:00:00", 200, 150),
            make_row("2026-06-16 00:00:00", 200, 180),
            make_row("2026-06-23 00:00:00", 200, 300),  # net -100, min -> CROWDED_SHORT
        ]
        ok1 = analyze_market("ES", rows_long, None, args)
        ok2 = analyze_market("GC", rows_short, None, args)
        skipped = analyze_market("CL", [], None, args)
        return [ok1, ok2, skipped], args

    def test_json_report_includes_run_context_and_skipped(self, tmp_path):
        results, args = self._sample_results()
        run_context = build_run_context(args, ["ES", "GC", "CL"], "explicit_symbols", "2026-06-23")
        out = tmp_path / "cot_crowding_2026-07-07.json"
        generate_json_report(results, run_context, str(out))

        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["schema_version"] == "1.0"
        assert payload["run_context"]["universe_size"] == 3
        assert len(payload["markets"]) == 2
        assert len(payload["skipped"]) == 1
        assert payload["skipped"][0]["symbol"] == "CL"
        # Ranked by extremity descending; both ES/GC are equally extreme (100/0).
        symbols_in_order = [m["symbol"] for m in payload["markets"]]
        assert set(symbols_in_order) == {"ES", "GC"}

    def test_markdown_report_has_expected_sections(self, tmp_path):
        results, args = self._sample_results()
        run_context = build_run_context(args, ["ES", "GC", "CL"], "explicit_symbols", "2026-06-23")
        out = tmp_path / "cot_crowding_2026-07-07.md"
        generate_markdown_report(results, run_context, str(out))

        text = out.read_text(encoding="utf-8")
        assert "# COT Contrarian Crowding Report" in text
        assert "## Crowded Long" in text
        assert "## Crowded Short" in text
        assert "## Full Ranking" in text
        assert "## Biggest Week-over-Week Net Position Swings" in text
        assert "## Skipped Markets" in text
        assert "ES" in text and "GC" in text and "CL" in text


class TestCotClientBackoff:
    def test_retries_on_429_then_succeeds(self):
        client = CotClient(api_key="fake", sleep_seconds=0.0)
        client.session = _FakeSession(
            [
                _FakeResponse({"error": "rate limited"}, status_code=429),
                _FakeResponse([{"symbol": "ES", "name": "S&P 500 E-Mini (ES)"}], status_code=200),
            ]
        )
        # Monkeypatch time.sleep via the module under test's imported `time`.
        import screen_cot_crowding as mod

        original_sleep = mod.time.sleep
        mod.time.sleep = lambda _seconds: None
        try:
            data = client.get_market_list()
        finally:
            mod.time.sleep = original_sleep
        assert data == [{"symbol": "ES", "name": "S&P 500 E-Mini (ES)"}]
        assert len(client.session.calls) == 2

    def test_non_retryable_4xx_fails_immediately(self):
        client = CotClient(api_key="fake", sleep_seconds=0.0)
        client.session = _FakeSession([_FakeResponse({"error": "forbidden"}, status_code=403)])
        rows, error = client.get_report("ES", "2020-01-01", "2026-07-07")
        assert rows == []
        assert error is not None
        assert "403" in error
        assert len(client.session.calls) == 1


class TestRedact:
    """`_redact()` — the FMP API key must never survive into an error string."""

    def test_redacts_apikey_mid_query(self):
        text = "GET /stable/x?apikey=SECRETKEY123&symbol=ES failed"
        result = _redact(text)
        assert "SECRETKEY123" not in result
        assert "apikey=***REDACTED***" in result
        assert "symbol=ES" in result  # other params are left alone

    def test_redacts_apikey_at_end_of_string(self):
        text = "GET /stable/x?symbol=ES&apikey=SECRETKEY123"
        result = _redact(text)
        assert "SECRETKEY123" not in result
        assert result.endswith("apikey=***REDACTED***")

    def test_case_insensitive(self):
        result = _redact("...ApiKey=SECRETKEY123...")
        assert "SECRETKEY123" not in result
        assert "***REDACTED***" in result

    def test_no_apikey_present_is_unchanged(self):
        text = "plain connection error, no key here"
        assert _redact(text) == text

    def test_empty_string(self):
        assert _redact("") == ""

    def test_none_passthrough(self):
        assert _redact(None) is None

    # --- Additional leak shapes demonstrated by the reviewer ---------------
    # Pattern-based redaction alone only catches `apikey=...`; these cover
    # the other shapes an FMP error response or exception message might use.

    def test_redacts_json_double_quoted_form(self):
        result = _redact('{"apikey": "SECRETKEY123"}')
        assert "SECRETKEY123" not in result
        assert "***REDACTED***" in result

    def test_redacts_json_single_quoted_mixed_case_form(self):
        result = _redact("{'apiKey': 'SECRETKEY123'}")
        assert "SECRETKEY123" not in result
        assert "***REDACTED***" in result

    def test_redacts_url_encoded_form(self):
        result = _redact("...&apikey%3DSECRETKEY123&foo=bar")
        assert "SECRETKEY123" not in result
        assert "***REDACTED***" in result

    def test_redacts_spaced_equals_form(self):
        result = _redact("apikey = SECRETKEY123 rejected")
        assert "SECRETKEY123" not in result
        assert "***REDACTED***" in result

    def test_value_based_redaction_catches_bare_key_with_no_marker(self):
        """A bare key with no "apikey" marker at all (e.g. echoed into an
        HTML error page body) is invisible to pattern-based redaction —
        only passing the known secret catches it. This is the whole point
        of defense-in-depth: patterns alone are not sufficient."""
        text = "<html><body>Invalid credential: SECRETKEY123</body></html>"

        without_secret = _redact(text)
        assert "SECRETKEY123" in without_secret  # pattern-based alone misses it

        with_secret = _redact(text, secret="SECRETKEY123")
        assert "SECRETKEY123" not in with_secret
        assert "***REDACTED***" in with_secret

    def test_value_based_redaction_ignores_empty_or_none_secret(self):
        # An empty/None secret must not blow up or redact everything.
        text = "plain message with no key"
        assert _redact(text, secret=None) == text
        assert _redact(text, secret="") == text


class TestApiKeyRedactionOnErrorPaths:
    """The FMP key must never reach stderr or a returned/stored error string.

    `requests` exceptions (ConnectionError, Timeout, ...) embed the full
    request URL — including `?apikey=...` — in their str(). This must be
    redacted at the source in `_request_with_backoff` so every downstream
    consumer (WARN retry logs, the returned error string, skip `reason`
    fields, and generated reports) is automatically safe.
    """

    SECRET = "SECRETKEY123"  # pragma: allowlist secret

    def _connection_error(self) -> requests.exceptions.ConnectionError:
        return requests.exceptions.ConnectionError(
            "HTTPSConnectionPool(host='financialmodelingprep.com', port=443): "
            "Max retries exceeded with url: /stable/commitment-of-traders-report"
            f"?symbol=ES&from=2020-01-01&to=2026-07-07&apikey={self.SECRET} "
            "(Caused by NewConnectionError('...'))"
        )

    def test_connection_error_redacted_in_returned_error_and_stderr(self, capsys):
        client = CotClient(api_key=self.SECRET, sleep_seconds=0.0)
        client.session = _RaisingSession(self._connection_error())

        import screen_cot_crowding as mod

        original_sleep = mod.time.sleep
        mod.time.sleep = lambda _seconds: None
        try:
            rows, error = client.get_report("ES", "2020-01-01", "2026-07-07")
        finally:
            mod.time.sleep = original_sleep

        captured = capsys.readouterr()

        assert rows == []
        assert error is not None
        assert self.SECRET not in error
        assert "***REDACTED***" in error
        # Retry WARN lines are printed to stderr on every attempt.
        assert self.SECRET not in captured.err
        assert "***REDACTED***" in captured.err

    def test_non_200_response_text_redacted(self):
        # A response whose body happens to echo the request (e.g. a
        # validation-error API) must not leak the key either.
        payload = {"message": f"invalid request to url with apikey={self.SECRET}"}
        client = CotClient(api_key=self.SECRET, sleep_seconds=0.0)
        client.session = _FakeSession([_FakeResponse(payload, status_code=400)])

        rows, error = client.get_report("ES", "2020-01-01", "2026-07-07")

        assert rows == []
        assert error is not None
        assert self.SECRET not in error
        assert "***REDACTED***" in error

    def test_non_200_json_style_apikey_body_redacted_end_to_end(self):
        # {"apikey": "..."} in a response body, through the real client.
        payload = {"apikey": self.SECRET, "error": "invalid"}
        client = CotClient(api_key=self.SECRET, sleep_seconds=0.0)
        client.session = _FakeSession([_FakeResponse(payload, status_code=400)])

        rows, error = client.get_report("ES", "2020-01-01", "2026-07-07")

        assert rows == []
        assert error is not None
        assert self.SECRET not in error
        assert "***REDACTED***" in error

    def test_non_200_bare_value_body_redacted_end_to_end(self):
        """A body with no "apikey" marker at all -- only redacted because
        the client threads its own known api_key through as the secret
        (`_request_with_backoff` reads it from `params["apikey"]`)."""
        client = CotClient(api_key=self.SECRET, sleep_seconds=0.0)
        response = _FakeResponse({}, status_code=400)
        response.text = f"<html><body>Invalid credential: {self.SECRET}</body></html>"
        client.session = _FakeSession([response])

        rows, error = client.get_report("ES", "2020-01-01", "2026-07-07")

        assert rows == []
        assert error is not None
        assert self.SECRET not in error
        assert "***REDACTED***" in error

    def test_market_list_runtime_error_redacted(self, capsys):
        client = CotClient(api_key=self.SECRET, sleep_seconds=0.0)
        client.session = _RaisingSession(self._connection_error())

        import screen_cot_crowding as mod

        original_sleep = mod.time.sleep
        mod.time.sleep = lambda _seconds: None
        try:
            with pytest.raises(RuntimeError) as exc_info:
                client.get_market_list()
        finally:
            mod.time.sleep = original_sleep

        assert self.SECRET not in str(exc_info.value)
        assert "***REDACTED***" in str(exc_info.value)
        captured = capsys.readouterr()
        assert self.SECRET not in captured.err

    def test_fetch_error_never_leaks_into_skip_reason_or_reports(self, tmp_path):
        """End-to-end regression: a raw exception containing the key, fed
        through get_report -> analyze_market -> generate_json_report /
        generate_markdown_report, must never surface the key in report
        content (nor in run_context serialization)."""
        client = CotClient(api_key=self.SECRET, sleep_seconds=0.0)
        client.session = _RaisingSession(self._connection_error())

        import screen_cot_crowding as mod

        original_sleep = mod.time.sleep
        mod.time.sleep = lambda _seconds: None
        try:
            rows, error = client.get_report("ES", "2020-01-01", "2026-07-07")
        finally:
            mod.time.sleep = original_sleep

        args = default_args(lookback_weeks=4, short_lookback_weeks=2)
        result = analyze_market("ES", rows, error, args)
        assert result["status"] == "skipped"
        assert self.SECRET not in result["reason"]

        run_context = build_run_context(args, ["ES"], "explicit_symbols", None)
        assert self.SECRET not in json.dumps(run_context)

        json_path = tmp_path / "cot_crowding_test.json"
        md_path = tmp_path / "cot_crowding_test.md"
        generate_json_report([result], run_context, str(json_path))
        generate_markdown_report([result], run_context, str(md_path))

        assert self.SECRET not in json_path.read_text(encoding="utf-8")
        assert self.SECRET not in md_path.read_text(encoding="utf-8")
