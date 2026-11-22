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
