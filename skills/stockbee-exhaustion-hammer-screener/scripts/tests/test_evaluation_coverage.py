"""evaluation_coverage for the exhaustion hammer screen (#711)."""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import screen_exhaustion_hammer as ehs  # noqa: E402


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
    assert ehs.fetch_failure_reason(last_error) == reason


def _rows(n=90, close=100.0):
    rows, day = [], date(2026, 6, 26)
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

    def __init__(self, answers, quote_budget=()):
        self.answers = answers
        self.quote_budget = set(quote_budget)
        self.last_fetch_error = None

    def get_historical_prices(self, symbol, days=120):
        rows, error = self.answers[symbol]
        if rows == "BUDGET":
            raise ehs.ApiCallBudgetExceeded("budget")
        self.last_fetch_error = error
        return rows

    def get_quote_bar(self, symbol, asof_date=None):
        if symbol in self.quote_budget:
            raise ehs.ApiCallBudgetExceeded("budget")
        return None

    def get_api_stats(self):
        return {}


def _args(symbols, **kw):
    base = dict(
        prices_json=None,
        profiles_json=None,
        fmp_universe=False,
        symbols=symbols,
        universe_file=None,
        max_symbols=300,
        api_key="k",
        max_api_calls=10,
        history_days=120,
        use_quote_latest=False,
        asof_date=None,
    )
    base.update(kw)
    return Namespace(**base)


def test_collect_records_one_reason_per_requested_symbol(monkeypatch):
    answers = {
        "AAA": (_rows(), None),
        "BBB": ([], "HTTP 402 - Restricted Endpoint"),
        "CCC": ([], None),
        "DDD": ([{"date": "2026-06-26", "open": 0, "high": 0, "low": 0, "close": 0}], None),
        "EEE": ("BUDGET", None),
        "FFF": (_rows(), None),
    }
    monkeypatch.setattr(ehs, "FMPClient", lambda **_: _Client(answers))
    outcomes = {}
    price_data, _, _ = ehs.collect_price_data(_args(list(answers)), outcomes)
    assert set(price_data) == {"AAA"}
    assert outcomes == {
        "AAA": None,
        "BBB": "plan_gated",
        "CCC": "missing_data",
        "DDD": "invalid_data",
        "EEE": "not_requested",
        "FFF": "not_requested",
    }


def test_budget_stop_in_the_quote_fetch_is_not_requested(monkeypatch):
    answers = {s: (_rows(), None) for s in ("AAA", "BBB", "CCC")}
    monkeypatch.setattr(ehs, "FMPClient", lambda **_: _Client(answers, quote_budget={"BBB"}))
    outcomes = {}
    price_data, _, _ = ehs.collect_price_data(_args(list(answers), use_quote_latest=True), outcomes)
    assert set(price_data) == {"AAA"}
    assert outcomes == {"AAA": None, "BBB": "not_requested", "CCC": "not_requested"}


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


def _run(monkeypatch, tmp_path, argv):
    monkeypatch.setattr(sys, "argv", ["prog", "--output-dir", str(tmp_path), *argv])
    ehs.main()
    (report,) = tmp_path.glob("stockbee_exhaustion_hammer_*.json")
    (markdown,) = tmp_path.glob("stockbee_exhaustion_hammer_*.md")
    return json.loads(report.read_text()), markdown.read_text()


def _main(monkeypatch, tmp_path, answer, symbols):
    shared = ehs._load_shared_fmp()
    session = _Session(answer)
    monkeypatch.setattr(shared.requests, "Session", lambda: session)
    monkeypatch.setattr(shared.time, "sleep", lambda _: None)
    argv = ["--api-key", "k", "--max-api-calls", "1000", "--symbols", *symbols]
    return _run(monkeypatch, tmp_path, argv)


SYMBOLS = [f"S{i:02d}" for i in range(10)]


def test_every_symbol_plan_gated_is_not_evaluable(monkeypatch, tmp_path, capsys):
    report, markdown = _main(monkeypatch, tmp_path, lambda n, s: _Response(status=402), SYMBOLS)
    coverage = report["evaluation_coverage"]
    assert coverage == {
        "schema_version": "1.0",
        "universe_size": 10,
        "evaluated": 0,
        "not_evaluated": 10,
        "not_evaluated_reasons": {"plan_gated": 10},
        "verdict": "not_evaluable",
    }
    assert not ehs.coverage_contract.validate_evaluation_coverage(coverage)
    assert "- Evaluation coverage: 0/10 evaluated (not_evaluable)" in markdown
    assert "Result undetermined: incomplete evaluation coverage." in markdown
    assert "No non-rejected candidates found." not in markdown
    assert "Result undetermined" in capsys.readouterr().out


def test_rate_limit_midway_is_partial(monkeypatch, tmp_path):
    def answer(n, symbol):
        return _Response(_rows()) if n <= 4 else _Response(status=429)

    report, markdown = _main(monkeypatch, tmp_path, answer, SYMBOLS)
    coverage = report["evaluation_coverage"]
    assert (coverage["evaluated"], coverage["verdict"]) == (4, "partial")
    assert coverage["not_evaluated_reasons"] == {"rate_limited": 6}
    assert "- Not evaluated: rate_limited: 6." in markdown


def test_short_history_is_not_a_negative_decision(monkeypatch, tmp_path):
    def answer(n, symbol):
        return _Response(_rows(5) if symbol == "S00" else _rows())

    report, _ = _main(monkeypatch, tmp_path, answer, SYMBOLS)
    coverage = report["evaluation_coverage"]
    assert coverage["not_evaluated_reasons"] == {"insufficient_history": 1}
    assert (coverage["evaluated"], coverage["verdict"]) == (9, "partial")


def test_complete_run_keeps_the_plain_zero_message(monkeypatch, tmp_path):
    report, markdown = _main(monkeypatch, tmp_path, lambda n, s: _Response(_rows()), SYMBOLS)
    assert report["evaluation_coverage"]["verdict"] == "complete"
    assert "- Evaluation coverage: 10/10 evaluated (complete)" in markdown
    assert "No non-rejected candidates found." in markdown
    assert "Result undetermined" not in markdown


BAD_ROW = {"date": "2026-06-26", "open": 0, "high": 0, "low": 0, "close": 0}


def test_offline_universe_keeps_symbols_without_usable_bars(monkeypatch, tmp_path):
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps({"AAA": _rows(), "DDD": [], "EEE": [BAD_ROW]}))
    report, markdown = _run(monkeypatch, tmp_path / "out", ["--prices-json", str(prices)])
    coverage = report["evaluation_coverage"]
    assert coverage["universe_size"] == 3
    assert coverage["not_evaluated_reasons"] == {"invalid_data": 1, "missing_data": 1}
    assert (coverage["evaluated"], coverage["verdict"]) == (1, "partial")
    assert "No non-rejected candidates found." not in markdown


def test_offline_explicit_symbol_missing_from_the_file(monkeypatch, tmp_path):
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps({"AAA": _rows(), "EEE": [BAD_ROW]}))
    argv = ["--prices-json", str(prices), "--symbols", "AAA", "EEE", "ZZZ"]
    report, _ = _run(monkeypatch, tmp_path / "out", argv)
    coverage = report["evaluation_coverage"]
    assert coverage["universe_size"] == 3
    assert coverage["not_evaluated_reasons"] == {"invalid_data": 1, "missing_data": 1}


def test_offline_cap_counts_the_file_universe(monkeypatch, tmp_path):
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps({"AAA": [], "BBB": _rows(), "CCC": _rows()}))
    argv = ["--prices-json", str(prices), "--max-symbols", "2"]
    report, _ = _run(monkeypatch, tmp_path / "out", argv)
    assert report["evaluation_coverage"]["universe_size"] == 2
    assert [c["symbol"] for c in report["candidates"]] == ["BBB"]


def test_cached_history_resets_the_last_fetch_error(monkeypatch):
    shared = ehs._load_shared_fmp()

    def answer(n, symbol):
        return _Response([]) if symbol == "AAA" else _Response(status=500)

    monkeypatch.setattr(shared.requests, "Session", lambda: _Session(answer))
    monkeypatch.setattr(shared.time, "sleep", lambda _: None)
    client = ehs.FMPClient(api_key="k", max_api_calls=100)
    client.get_historical_prices("AAA")
    client.get_historical_prices("BBB")
    assert client.last_fetch_error is not None
    assert client.get_historical_prices("AAA") == []
    assert client.last_fetch_error is None
