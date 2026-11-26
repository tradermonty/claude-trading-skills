"""evaluation_coverage for the momentum burst screen (#711)."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import screen_momentum_burst as smb  # noqa: E402


@pytest.mark.parametrize(
    "last_error,reason",
    [
        (None, "missing_data"),
        ("HTTP 429 (daily rate limit)", "rate_limited"),
        ("daily rate limit already reached", "rate_limited"),
        ("HTTP 402 - Restricted Endpoint", "plan_gated"),
        ("HTTP 500 - oops", "provider_error"),
        ("request exception: timed out", "provider_error"),
        ("unexpected non-list response", "invalid_data"),
    ],
)
def test_fetch_failure_reason(last_error, reason):
    assert smb.fetch_failure_reason(last_error) == reason


def _rows(n=90, close=100.0):
    rows, day = [], date(2026, 3, 30)
    while len(rows) < n:
        if day.weekday() < 5:
            rows.append(
                {
                    "date": day.isoformat(),
                    "open": close,
                    "high": close + 1,
                    "low": close - 1,
                    "close": close,
                    "volume": 1_000_000,
                }
            )
        day -= timedelta(days=1)
    return rows


class _Client:
    """Per-symbol (rows, last_error); BUDGET raises the budget error."""

    def __init__(self, answers):
        self.answers = answers
        self.last_fetch_error = None

    def get_historical_prices(self, symbol, days=80):
        rows, error = self.answers[symbol]
        if rows == "BUDGET":
            raise smb.ApiCallBudgetExceeded("budget")
        self.last_fetch_error = error
        return rows

    def get_api_stats(self):
        return {}


def test_collect_records_one_reason_per_requested_symbol(monkeypatch):
    answers = {
        "AAA": (_rows(), None),
        "BBB": ([], "HTTP 402 - Restricted Endpoint"),
        "CCC": ([], None),
        "DDD": ([{"date": "2026-03-27", "open": 0, "high": 0, "low": 0, "close": 0}], None),
        "EEE": ("BUDGET", None),
        "FFF": (_rows(), None),
    }
    monkeypatch.setattr(smb, "FMPClient", lambda **_: _Client(answers))
    args = Namespace(
        prices_json=None,
        fmp_universe=False,
        symbols=list(answers),
        universe_file=None,
        max_symbols=300,
        api_key="k",
        max_api_calls=10,
        history_days=80,
    )
    outcomes = {}
    price_data, _ = smb.collect_price_data(args, outcomes)
    assert set(price_data) == {"AAA"}
    assert outcomes == {
        "AAA": None,
        "BBB": "plan_gated",
        "CCC": "missing_data",
        "DDD": "invalid_data",
        "EEE": "not_requested",
        "FFF": "not_requested",
    }


class _Response:
    def __init__(self, payload=None, status=200):
        self.payload, self.status_code, self.text = payload, status, ""

    def json(self):
        return self.payload


class _Session:
    def __init__(self, answer):
        self.answer, self.headers, self.calls = answer, {}, 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        return self.answer(self.calls, params["symbol"])

    def close(self):
        pass


def _main(monkeypatch, tmp_path, answer, symbols):
    shared = smb._load_shared_fmp()
    session = _Session(answer)
    monkeypatch.setattr(shared.requests, "Session", lambda: session)
    monkeypatch.setattr(shared.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prog",
            "--as-of",
            "2026-03-30",
            "--api-key",
            "k",
            "--max-api-calls",
            "1000",
            "--output-dir",
            str(tmp_path),
            "--symbols",
            *symbols,
        ],
    )
    smb.main()
    (report,) = tmp_path.glob("stockbee_momentum_burst_*.json")
    (markdown,) = tmp_path.glob("stockbee_momentum_burst_*.md")
    return json.loads(report.read_text()), markdown.read_text(), session


SYMBOLS = [f"S{i:02d}" for i in range(10)]


def test_every_symbol_plan_gated_is_not_evaluable(monkeypatch, tmp_path, capsys):
    report, markdown, _ = _main(monkeypatch, tmp_path, lambda n, s: _Response(status=402), SYMBOLS)
    coverage = report["evaluation_coverage"]
    assert coverage == {
        "schema_version": "1.0",
        "universe_size": 10,
        "evaluated": 0,
        "not_evaluated": 10,
        "not_evaluated_reasons": {"plan_gated": 10},
        "verdict": "not_evaluable",
    }
    assert not smb.coverage_contract.validate_evaluation_coverage(coverage)
    assert "- Evaluation coverage: 0/10 evaluated (not_evaluable)" in markdown
    assert "Result undetermined: incomplete evaluation coverage." in markdown
    assert "No non-rejected candidates found." not in markdown
    assert "Result undetermined" in capsys.readouterr().out


def test_rate_limit_midway_is_partial(monkeypatch, tmp_path):
    def answer(n, symbol):
        return _Response(_rows()) if n <= 4 else _Response(status=429)

    report, markdown, session = _main(monkeypatch, tmp_path, answer, SYMBOLS)
    coverage = report["evaluation_coverage"]
    assert (coverage["evaluated"], coverage["verdict"]) == (4, "partial")
    assert coverage["not_evaluated_reasons"] == {"rate_limited": 6}
    assert "- Not evaluated: rate_limited: 6." in markdown


def test_short_history_is_not_a_negative_decision(monkeypatch, tmp_path):
    def answer(n, symbol):
        return _Response(_rows(5) if symbol == "S00" else _rows())

    report, markdown, _ = _main(monkeypatch, tmp_path, answer, SYMBOLS)
    coverage = report["evaluation_coverage"]
    assert coverage["not_evaluated_reasons"] == {"insufficient_history": 1}
    assert (coverage["evaluated"], coverage["verdict"]) == (9, "partial")


def test_complete_run_keeps_the_plain_zero_message(monkeypatch, tmp_path):
    report, markdown, _ = _main(monkeypatch, tmp_path, lambda n, s: _Response(_rows()), SYMBOLS)
    assert report["evaluation_coverage"]["verdict"] == "complete"
    assert "- Evaluation coverage: 10/10 evaluated (complete)" in markdown
    assert "No non-rejected candidates found." in markdown
    assert "Result undetermined" not in markdown


def _future_rows(n=90):
    """Bars that all fall after the 2026-03-30 as-of session."""
    rows = _rows(n)
    for row in rows:
        row["date"] = (date.fromisoformat(row["date"]) + timedelta(days=200)).isoformat()
    return rows


def _bad_date_rows():
    rows = _rows()
    rows[0]["date"] = "not-a-date"
    return rows


NO_SESSION_CASES = [
    (_future_rows, "no_completed_price_data"),
    (_bad_date_rows, "invalid_price_date"),
]


@pytest.mark.parametrize("bad_rows,reason", NO_SESSION_CASES)
def test_bars_without_a_usable_session_are_not_a_negative_decision(
    monkeypatch, tmp_path, bad_rows, reason
):
    def answer(n, symbol):
        return _Response(bad_rows() if symbol == "S00" else _rows())

    report, _, _ = _main(monkeypatch, tmp_path, answer, SYMBOLS)
    coverage = report["evaluation_coverage"]
    assert coverage["not_evaluated_reasons"] == {reason: 1}
    assert (coverage["evaluated"], coverage["verdict"]) == (9, "partial")


@pytest.mark.parametrize("bad_rows,reason", NO_SESSION_CASES)
def test_offline_bars_without_a_usable_session_are_not_evaluable(
    monkeypatch, tmp_path, bad_rows, reason
):
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps({"AAA": bad_rows()}))
    out = tmp_path / "out"
    argv = ["prog", "--prices-json", str(prices), "--as-of", "2026-03-30", "--output-dir", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    smb.main()
    (report,) = out.glob("stockbee_momentum_burst_*.json")
    (markdown,) = out.glob("stockbee_momentum_burst_*.md")
    coverage = json.loads(report.read_text())["evaluation_coverage"]
    assert coverage["not_evaluated_reasons"] == {reason: 1}
    assert (coverage["evaluated"], coverage["verdict"]) == (0, "not_evaluable")
    assert "No non-rejected candidates found." not in markdown.read_text()


BAD_ROW = {"date": "2026-03-30", "open": 0, "high": 0, "low": 0, "close": 0}


def _offline(monkeypatch, tmp_path, payload, *extra):
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps(payload))
    out = tmp_path / "out"
    argv = ["prog", "--prices-json", str(prices), "--as-of", "2026-03-30", "--output-dir", str(out)]
    monkeypatch.setattr(sys, "argv", [*argv, *extra])
    smb.main()
    (report,) = out.glob("stockbee_momentum_burst_*.json")
    (markdown,) = out.glob("stockbee_momentum_burst_*.md")
    return json.loads(report.read_text())["evaluation_coverage"], markdown.read_text()


@pytest.mark.parametrize("field", ["historical", "bars", "prices"])
def test_offline_list_entry_with_empty_rows_stays_in_the_universe(monkeypatch, tmp_path, field):
    payload = [{"symbol": "AAA", "historical": _rows()}, {"symbol": "DDD", field: []}]
    coverage, markdown = _offline(monkeypatch, tmp_path, payload)
    assert coverage["universe_size"] == 2
    assert coverage["not_evaluated_reasons"] == {"missing_data": 1}
    assert (coverage["evaluated"], coverage["verdict"]) == (1, "partial")
    assert "No non-rejected candidates found." not in markdown


def test_offline_universe_keeps_symbols_without_usable_bars(monkeypatch, tmp_path):
    payload = {
        "AAA": _rows(),
        "BBB": {"historical": None},
        "CCC": None,
        "DDD": [],
        "EEE": [BAD_ROW],
    }
    coverage, _ = _offline(monkeypatch, tmp_path, payload)
    assert coverage["universe_size"] == 5
    assert coverage["not_evaluated_reasons"] == {"invalid_data": 1, "missing_data": 3}
    assert (coverage["evaluated"], coverage["verdict"]) == (1, "partial")


def test_offline_explicit_symbol_keeps_the_file_reason(monkeypatch, tmp_path):
    payload = {"AAA": _rows(), "EEE": [BAD_ROW]}
    coverage, _ = _offline(monkeypatch, tmp_path, payload, "--symbols", "AAA", "EEE", "ZZZ")
    assert coverage["universe_size"] == 3
    assert coverage["not_evaluated_reasons"] == {"invalid_data": 1, "missing_data": 1}


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        ([{"symbol": "DDD", "historical": None}], "missing_data"),
        ([{"symbol": "DDD"}], "missing_data"),
        ([{"ticker": "DDD", "bars": None, "prices": []}], "missing_data"),
        ([{"symbol": "DDD", "historical": "x"}], "invalid_data"),
        ([{"symbol": "DDD", "bars": {"date": "2026-03-30"}}], "invalid_data"),
        ([{"symbol": "DDD", "prices": [BAD_ROW]}], "invalid_data"),
        ({"DDD": None}, "missing_data"),
        ({"DDD": {"historical": None}}, "missing_data"),
        ({"DDD": {}}, "missing_data"),
        ({"DDD": "bad"}, "invalid_data"),
        ({"DDD": {"historical": 5}}, "invalid_data"),
        ({"symbols": {"DDD": {"historical": "x"}}}, "invalid_data"),
    ],
)
def test_read_prices_json_names_every_symbol_without_bars(tmp_path, payload, reason):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(payload))
    unusable: dict[str, str] = {}
    assert smb.read_prices_json(str(path), unusable) == {}
    assert unusable == {"DDD": reason}


def test_read_prices_json_takes_the_first_non_empty_field(tmp_path):
    path = tmp_path / "prices.json"
    path.write_text(
        json.dumps(
            [
                {"symbol": "AAA", "historical": [], "bars": _rows(3)},
                {"symbol": "BBB", "historical": "x", "prices": _rows(3)},
            ]
        )
    )
    unusable: dict[str, str] = {}
    assert sorted(smb.read_prices_json(str(path), unusable)) == ["AAA", "BBB"]
    assert unusable == {}


@pytest.mark.parametrize("bars_first", [True, False])
def test_read_prices_json_repeated_symbol_keeps_its_bars(tmp_path, bars_first):
    entries = [{"symbol": "AAA", "historical": _rows(3)}, {"symbol": "aaa", "historical": []}]
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(entries if bars_first else entries[::-1]))
    unusable: dict[str, str] = {}
    assert list(smb.read_prices_json(str(path), unusable)) == ["AAA"]
    assert unusable == {}


def test_read_prices_json_skips_list_items_that_name_no_symbol(tmp_path):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps([{"historical": _rows(3)}, {"symbol": "", "bars": []}, "junk", 7]))
    unusable: dict[str, str] = {}
    assert smb.read_prices_json(str(path), unusable) == {}
    assert unusable == {}


def _inf_volume_rows():
    rows = _rows(3)
    rows[1] = {**rows[1], "volume": "Infinity"}
    return rows


def _write(tmp_path, payload):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps(payload))
    return path


@pytest.mark.parametrize("bad_first", [True, False])
def test_read_prices_json_bad_rows_do_not_hide_a_usable_duplicate(tmp_path, bad_first):
    entries = [
        {"symbol": "AAA", "historical": _inf_volume_rows()},
        {"symbol": "AAA", "historical": _rows(90)},
    ]
    path = _write(tmp_path, entries if bad_first else entries[::-1])
    unusable: dict[str, str] = {}
    result = smb.read_prices_json(str(path), unusable)
    assert list(result) == ["AAA"]
    assert len(result["AAA"]) == 90
    assert unusable == {}


def test_read_prices_json_lone_entry_with_failing_rows_is_invalid_data(tmp_path):
    path = _write(
        tmp_path,
        [{"symbol": "AAA", "historical": _inf_volume_rows()}, {"symbol": "BBB", "bars": _rows(3)}],
    )
    unusable: dict[str, str] = {}
    assert list(smb.read_prices_json(str(path), unusable)) == ["BBB"]
    assert unusable == {"AAA": "invalid_data"}


def test_read_prices_json_map_entry_with_failing_rows_is_invalid_data(tmp_path):
    path = _write(
        tmp_path, {"AAA": {"historical": _inf_volume_rows()}, "BBB": {"historical": _rows(3)}}
    )
    unusable: dict[str, str] = {}
    assert list(smb.read_prices_json(str(path), unusable)) == ["BBB"]
    assert unusable == {"AAA": "invalid_data"}


def test_read_prices_json_first_populated_field_wins_over_later_ones(tmp_path):
    path = _write(
        tmp_path,
        [
            {
                "symbol": "AAA",
                "historical": _rows(5, close=100.0),
                "bars": _rows(7, close=200.0),
                "prices": _rows(9, close=300.0),
            }
        ],
    )
    result = smb.read_prices_json(str(path), {})
    assert len(result["AAA"]) == 5
    assert result["AAA"][0].close == 100.0


def test_read_prices_json_later_populated_duplicate_replaces_earlier(tmp_path):
    path = _write(
        tmp_path,
        [
            {"symbol": "AAA", "historical": _rows(5, close=100.0)},
            {"symbol": "aaa", "historical": _rows(7, close=200.0)},
        ],
    )
    unusable: dict[str, str] = {}
    result = smb.read_prices_json(str(path), unusable)
    assert len(result["AAA"]) == 7
    assert result["AAA"][0].close == 200.0
    assert unusable == {}


def test_cli_completes_when_an_earlier_duplicate_has_failing_rows(monkeypatch, tmp_path):
    path = _write(
        tmp_path,
        [
            {"symbol": "AAA", "historical": _inf_volume_rows()},
            {"symbol": "AAA", "historical": _rows(90)},
        ],
    )
    coverage = _cli_coverage(monkeypatch, tmp_path, path)
    assert coverage["universe_size"] == 1
    assert coverage["not_evaluated_reasons"] == {}
    assert coverage["evaluated"] == 1


def test_cli_reports_a_lone_failing_entry_as_invalid_data(monkeypatch, tmp_path):
    path = _write(tmp_path, [{"symbol": "AAA", "historical": _inf_volume_rows()}])
    coverage = _cli_coverage(monkeypatch, tmp_path, path)
    assert coverage["not_evaluated_reasons"] == {"invalid_data": 1}
    assert coverage["verdict"] == "not_evaluable"


def _cli_coverage(monkeypatch, tmp_path, path):
    out = tmp_path / "out"
    argv = ["prog", "--prices-json", str(path), "--as-of", "2026-03-30", "--output-dir", str(out)]
    monkeypatch.setattr(sys, "argv", argv)
    smb.main()
    (report,) = out.glob("stockbee_momentum_burst_*.json")
    return json.loads(report.read_text())["evaluation_coverage"]


def test_cached_history_resets_the_last_fetch_error(monkeypatch):
    shared = smb._load_shared_fmp()

    def answer(n, symbol):
        return _Response([]) if symbol == "AAA" else _Response(status=500)

    monkeypatch.setattr(shared.requests, "Session", lambda: _Session(answer))
    monkeypatch.setattr(shared.time, "sleep", lambda _: None)
    client = smb.FMPClient(api_key="k", max_api_calls=100)
    client.get_historical_prices("AAA")
    client.get_historical_prices("BBB")
    assert client.last_fetch_error is not None
    assert client.get_historical_prices("AAA") == []
    assert client.last_fetch_error is None
