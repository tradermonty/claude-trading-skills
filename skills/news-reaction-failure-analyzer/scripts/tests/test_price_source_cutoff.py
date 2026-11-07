"""End-to-end tests for the as_of information cutoff in price-source selection
and for the price_attempts transparency field.

All HTTP is stubbed at ``requests.Session.get``; no live FMP calls are made.
"""

import argparse
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest
import requests

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_news_reaction as analyzer  # noqa: E402

AS_OF = "2026-07-10"  # a Friday
KEY = "SECRET-KEY-VALUE-123"  # pragma: allowlist secret
MARKER = "LEAK-MARKER-BODY"


def weekday_rows(path_sign, count=90, end=AS_OF):
    """Weekday bars ending at `end`; path_sign flips the post-event drift."""
    days = []
    cursor = date.fromisoformat(end)
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    days.reverse()
    price = 100.0
    rows = []
    for i, day in enumerate(days):
        price *= 1 + 0.004 * math.sin(i * 1.7) + path_sign * (0.01 if i >= count - 8 else 0.0)
        rows.append({"symbol": "X", "date": day.isoformat(), "price": round(price, 4)})
    return rows


EVENTS = [
    {
        "event_id": f"e{i}",
        "event": "headline",
        "event_time": f"2026-07-0{day}T10:00:00-04:00",
        "source_url": "https://example.com/a",
        "source_tier": "wire",
        "expected_impact": "BULLISH",
    }
    for i, day in enumerate((1, 2, 6, 7), start=1)
]


class Stub:
    """Maps price symbol -> (status, body) and records calls."""

    def __init__(self, by_symbol):
        self.by_symbol = by_symbol
        self.calls = []

    def __call__(self, url, params):
        symbol = params["symbol"]
        self.calls.append(symbol)
        status, body = self.by_symbol[symbol]
        text = body if isinstance(body, str) else json.dumps(body)
        return type(
            "Resp",
            (),
            {"status_code": status, "text": text, "json": lambda self_: body},
        )()


def run_main(tmp_path, monkeypatch, by_symbol, symbol="NQ", fmt="both"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "out"
    events_path = tmp_path / "events.json"
    events_path.write_text(json.dumps({"events": EVENTS}), encoding="utf-8")
    args = argparse.Namespace(
        symbol=symbol,
        price_symbol=None,
        direction="CROWDED_LONG",
        detector_json=None,
        max_detector_age_days=10,
        events_json=str(events_path),
        window_days=10,
        min_events=1,
        z_threshold=0.5,
        drift_z=1.45,
        as_of=AS_OF,
        output_dir=str(out_dir),
        format=fmt,
        api_key=KEY,
        sleep_seconds=0.0,
    )
    monkeypatch.setattr(analyzer, "parse_arguments", lambda: args)
    monkeypatch.setattr(analyzer.time, "sleep", lambda _s: None)
    stub = Stub(by_symbol)
    monkeypatch.setattr(
        requests.Session, "get", lambda session, url, params=None, timeout=None: stub(url, params)
    )
    run_to_completion()
    report = json.loads(next(out_dir.glob(f"nrf_{symbol}_*.json")).read_text(encoding="utf-8"))
    md_files = list(out_dir.glob(f"nrf_{symbol}_*.md"))
    markdown = md_files[0].read_text(encoding="utf-8") if md_files else ""
    return report, markdown, stub


def run_to_completion():
    """main() returns normally on a verdict and sys.exit(0)s on early exits."""
    try:
        analyzer.main()
    except SystemExit as exc:
        assert exc.code == 0


def verdict_fingerprint(report):
    return (
        report["verdict"],
        report["run_context"]["price_symbol"],
        report["aggregate"],
        report["relevant_events_used"],
    )


@pytest.fixture
def primary_rows():
    return weekday_rows(path_sign=-1)


@pytest.fixture
def proxy_rows():
    return weekday_rows(path_sign=+1)


def test_bad_row_after_as_of_does_not_change_source_or_verdict(
    tmp_path, monkeypatch, primary_rows, proxy_rows
):
    baseline, _, _ = run_main(
        tmp_path / "a", monkeypatch, {"NQUSD": (200, primary_rows), "QQQ": (200, proxy_rows)}
    )
    future_bad = {"symbol": "X", "date": "2026-07-13", "price": None}
    with_bad, _, stub = run_main(
        tmp_path / "b",
        monkeypatch,
        {"NQUSD": (200, primary_rows + [future_bad]), "QQQ": (200, proxy_rows)},
    )
    assert stub.calls == ["NQUSD"]
    assert with_bad["run_context"]["price_symbol"] == "NQUSD"
    assert verdict_fingerprint(with_bad) == verdict_fingerprint(baseline)
    # Sanity: the proxy path really would have given a different answer.
    proxy_only, _, _ = run_main(
        tmp_path / "c", monkeypatch, {"NQUSD": (402, "x"), "QQQ": (200, proxy_rows)}
    )
    assert proxy_only["aggregate"] != baseline["aggregate"]


def test_unparseable_date_after_cutoff_is_still_drift(tmp_path, monkeypatch, primary_rows):
    report, _, stub = run_main(
        tmp_path,
        monkeypatch,
        {
            "NQUSD": (200, primary_rows + [{"date": "13/07/2026", "price": 1}]),
            "QQQ": (200, weekday_rows(+1)),
        },
    )
    assert stub.calls == ["NQUSD", "QQQ"]
    assert report["run_context"]["price_attempts"][0]["status"] == "schema_drift:invalid_date"


def test_bad_row_inside_window_still_rejects_whole_source(
    tmp_path, monkeypatch, primary_rows, proxy_rows
):
    bad = list(primary_rows)
    bad[40] = {"symbol": "X", "date": bad[40]["date"], "price": None}
    report, _, stub = run_main(
        tmp_path, monkeypatch, {"NQUSD": (200, bad), "QQQ": (200, proxy_rows)}
    )
    assert stub.calls == ["NQUSD", "QQQ"]
    assert report["run_context"]["price_symbol"] == "QQQ"
    attempts = report["run_context"]["price_attempts"]
    assert attempts[0]["status"] == "schema_drift:invalid_price"
    assert attempts[1]["status"] == "ok"


def test_all_future_rows_report_no_usable_rows(tmp_path, monkeypatch):
    future = [{"symbol": "X", "date": "2026-07-13", "price": 100}]
    report, _, _ = run_main(tmp_path, monkeypatch, {"ESUSD": (200, future)}, symbol="ES")
    assert report["verdict_reason"] == "no_price_source"
    assert report["run_context"]["price_attempts"] == [
        {
            "symbol": "ES",
            "price_symbol": "ESUSD",
            "kind": "futures",
            "status": "no_rows_before_as_of",
        }
    ]


def test_malformed_future_row_alone_is_not_a_usable_row(tmp_path, monkeypatch):
    future = [{"symbol": "X", "date": "2026-07-13", "price": None}]
    report, _, _ = run_main(tmp_path, monkeypatch, {"ESUSD": (200, future)}, symbol="ES")
    assert report["verdict_reason"] == "no_price_source"
    assert report["run_context"]["price_attempts"][0]["status"] in (
        "0 rows",
        "no_rows_before_as_of",
    )


def test_drift_reason_visible_in_json_and_markdown(tmp_path, monkeypatch, proxy_rows):
    drifted = [{"date": "2026-07-09", "close": 100}]
    report, markdown, _ = run_main(
        tmp_path, monkeypatch, {"NQUSD": (200, drifted), "QQQ": (200, proxy_rows)}
    )
    attempts = report["run_context"]["price_attempts"]
    assert attempts[0] == {
        "symbol": "NQ",
        "price_symbol": "NQUSD",
        "kind": "futures",
        "status": "schema_drift:missing_price",
    }
    assert attempts[1]["status"] == "ok"
    assert "schema_drift:missing_price" in markdown
    assert "had no usable price feed" not in markdown


def test_http_error_body_and_key_never_reach_outputs(tmp_path, monkeypatch, proxy_rows, capsys):
    body = f"{MARKER} apikey={KEY}"
    report, markdown, _ = run_main(
        tmp_path, monkeypatch, {"NQUSD": (403, body), "QQQ": (200, proxy_rows)}
    )
    assert report["run_context"]["price_attempts"][0]["status"] == "http_403"
    captured = capsys.readouterr()
    everything = json.dumps(report) + markdown + captured.out + captured.err
    assert MARKER not in everything
    assert KEY not in everything


@pytest.mark.parametrize(
    "exc", [ValueError(f"{MARKER} {KEY}"), requests.Timeout(f"{MARKER} {KEY}")]
)
def test_transport_and_json_errors_are_static_codes(tmp_path, monkeypatch, proxy_rows, exc, capsys):
    class Boom:
        status_code = 200
        text = ""

        def json(self):
            raise exc

    def get(session, url, params=None, timeout=None):
        if params["symbol"] == "NQUSD":
            if isinstance(exc, requests.RequestException):
                raise exc
            return Boom()
        return Stub({"QQQ": (200, proxy_rows)})(url, params)

    tmp_path.mkdir(parents=True, exist_ok=True)
    out_dir = tmp_path / "out"
    events_path = tmp_path / "events.json"
    events_path.write_text(json.dumps({"events": EVENTS}), encoding="utf-8")
    args = argparse.Namespace(
        symbol="NQ",
        price_symbol=None,
        direction="CROWDED_LONG",
        detector_json=None,
        max_detector_age_days=10,
        events_json=str(events_path),
        window_days=10,
        min_events=1,
        z_threshold=0.5,
        drift_z=1.45,
        as_of=AS_OF,
        output_dir=str(out_dir),
        format="both",
        api_key=KEY,
        sleep_seconds=0.0,
    )
    monkeypatch.setattr(analyzer, "parse_arguments", lambda: args)
    monkeypatch.setattr(analyzer.time, "sleep", lambda _s: None)
    monkeypatch.setattr(requests.Session, "get", get)
    run_to_completion()
    report_text = next(out_dir.glob("nrf_NQ_*.json")).read_text(encoding="utf-8")
    markdown = next(out_dir.glob("nrf_NQ_*.md")).read_text(encoding="utf-8")
    captured = capsys.readouterr()
    status = json.loads(report_text)["run_context"]["price_attempts"][0]["status"]
    assert status in ("request_exception", "invalid_json")
    assert MARKER not in report_text + markdown
    assert KEY not in report_text + markdown + captured.out


def test_price_attempts_present_on_early_exits(tmp_path, monkeypatch):
    report, markdown, stub = run_main(tmp_path, monkeypatch, {}, symbol="ZZFAKE")
    assert report["run_context"]["price_attempts"] == []
    assert stub.calls == []
    assert "Price attempts" not in markdown or "none" in markdown.lower()


@pytest.mark.parametrize(
    "error,expected",
    [
        ("schema_drift:invalid_price", "schema_drift:invalid_price"),
        ("HTTP 402: restricted LEAK", "http_402"),
        ("HTTP 503", "http_503"),
        ("invalid JSON response: LEAK", "invalid_json"),
        ("request exception: LEAK", "request_exception"),
        ("whatever LEAK", "error"),
        ("schema_drift:LEAK", "error"),
    ],
)
def test_status_code_for_error_is_static(error, expected):
    assert analyzer._status_code_for_error(error) == expected
