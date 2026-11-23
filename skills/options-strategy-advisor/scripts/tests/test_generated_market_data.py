"""Real generated transport with synthetic HTTP: no live API or pricing changes."""

import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import black_scholes as bs
import pytest
import requests

KEY = "fictional+secret&495"  # pragma: allowlist secret
AS_OF = date(2026, 11, 20)


class Response:
    def __init__(self, payload=None, status=200, text=""):
        self.status_code = status
        self.payload = payload
        self.text = text

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


@pytest.fixture
def scripted(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)

    def setup(*outcomes):
        pending = list(outcomes)
        calls = []
        closed = []
        original_close = requests.Session.close

        def get(url, params=None, headers=None, timeout=None):
            calls.append((url, dict(params or {}), timeout))
            if not pending:
                raise AssertionError("unexpected request")
            item = pending.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        def close(self):
            closed.append(self)
            original_close(self)

        monkeypatch.setattr(requests, "get", get)  # safe baseline reproduction of old wrappers
        monkeypatch.setattr(requests.Session, "get", lambda self, *a, **kw: get(*a, **kw))
        monkeypatch.setattr(requests.Session, "close", close)
        return calls, closed

    return setup


def history():
    return [
        {"symbol": "AAPL", "date": day, "close": price}
        for day, price in [("2026-11-20", 102), ("2026-11-19", 101), ("2026-11-18", 100)]
    ]


def test_stable_flat_history_oldest_first_and_session_closed(scripted):
    calls, closed = scripted(Response(history()))
    assert bs.fetch_historical_prices_for_hv("AAPL", KEY, days=3) == [100.0, 101.0, 102.0]
    assert calls[0][0].endswith("/stable/historical-price-eod/full")
    assert calls[0][1] == {"symbol": "AAPL", "apikey": KEY}
    assert calls[0][2] == 30
    assert len(closed) == 1


def test_history_newest_selection_not_provider_array_order(scripted):
    rows = history()[::-1]
    scripted(Response(rows))
    assert bs.fetch_historical_prices_for_hv("AAPL", KEY, days=2, as_of=AS_OF) == [101.0, 102.0]


@pytest.mark.parametrize("wrapper", ["historical", "batch"])
def test_matching_historical_envelopes_without_legacy_http(scripted, wrapper):
    payload = {"symbol": "AAPL", "historical": history()}
    if wrapper == "batch":
        payload = {"historicalStockList": [{"symbol": "OTHER", "historical": []}, payload]}
    calls, _ = scripted(Response(payload))
    assert bs.fetch_historical_prices_for_hv("AAPL", KEY, 3, as_of=AS_OF) == [100.0, 101.0, 102.0]
    assert len(calls) == 1 and "/api/v3/" not in calls[0][0]


@pytest.mark.parametrize("bad", [None, True, "bad", float("nan"), float("inf"), 0, -1, 10**400])
@pytest.mark.parametrize("field", ["close", "adjClose"])
def test_bad_consumed_history_price_is_unavailable(scripted, bad, field):
    rows = history()
    if field == "adjClose":
        for r in rows:
            r["adjClose"] = r["close"]
    rows[0][field] = bad
    scripted(Response({"symbol": "AAPL", "historical": rows}))
    assert bs.fetch_historical_prices_for_hv("AAPL", KEY, 3, as_of=AS_OF) is None


def test_all_adjusted_prices_used_but_mixed_basis_refused(scripted):
    rows = history()
    for r in rows:
        r["adjClose"] = r["close"] / 2
    scripted(Response(rows))
    assert bs.fetch_historical_prices_for_hv("AAPL", KEY, 3, as_of=AS_OF) == [50.0, 50.5, 51.0]
    del rows[0]["adjClose"]
    scripted(Response(rows))
    assert bs.fetch_historical_prices_for_hv("AAPL", KEY, 3, as_of=AS_OF) is None


@pytest.mark.parametrize("case", ["duplicate", "bad_date", "wrong_symbol", "ambiguous_batch"])
def test_history_identity_and_date_evidence_cannot_be_fabricated(scripted, case):
    rows = history()
    if case == "duplicate":
        rows[0]["date"] = rows[1]["date"]
    if case == "bad_date":
        rows[0]["date"] = "invalid"
    if case == "wrong_symbol":
        rows[0]["symbol"] = "OTHER"
    payload = rows
    if case == "ambiguous_batch":
        payload = {"historicalStockList": [{"symbol": "AAPL", "historical": rows}] * 2}
    scripted(Response(payload))
    assert bs.fetch_historical_prices_for_hv("AAPL", KEY, 3, as_of=AS_OF) is None


def test_future_history_ignored_before_consuming_price(scripted):
    rows = history() + [{"date": "2030-01-01", "symbol": "AAPL", "close": "bad"}]
    scripted(Response(rows))
    assert bs.fetch_historical_prices_for_hv("AAPL", KEY, 3, as_of=AS_OF) == [100.0, 101.0, 102.0]


@pytest.mark.parametrize("days", [True, 0, -1, 1.5, None])
def test_invalid_days_rejected_before_http(scripted, days):
    calls, _ = scripted()
    with pytest.raises(ValueError):
        bs.fetch_historical_prices_for_hv("AAPL", KEY, days, as_of=AS_OF)
    assert not calls


@pytest.mark.parametrize("status", [402, 403])
def test_quote_failure_never_uses_legacy_endpoint(scripted, status):
    calls, closed = scripted(Response(status=status), Response(status=status))
    assert bs.get_current_stock_price("AAPL", KEY) is None
    assert len(calls) == 1 and len(closed) == 1
    assert "/api/v3/" not in calls[0][0]


def test_quote_malformed_json_uses_shared_retry(scripted):
    calls, closed = scripted(
        Response(ValueError("bad json")), Response([{"symbol": "AAPL", "price": 150}])
    )
    assert bs.get_current_stock_price("AAPL", KEY) == 150.0
    assert len(calls) == 2 and len(closed) == 1


@pytest.mark.parametrize("bad", [None, True, 0, -1, "bad", float("nan"), float("inf"), 10**400])
def test_quote_bad_prices_do_not_enter_model(scripted, bad):
    scripted(Response([{"symbol": "AAPL", "price": bad}]))
    assert bs.get_current_stock_price("AAPL", KEY) is None


def test_exhausted_429_and_timeout_redact_markers_and_close(scripted, capsys):
    for outcome in [
        Response(status=429),
        requests.Timeout("URL apikey=" + KEY + " " + quote(KEY, safe="")),
    ]:
        _, closed = scripted(outcome, outcome)
        assert bs.get_current_stock_price("AAPL", KEY) is None
        output = capsys.readouterr()
        text = output.out + output.err
        assert KEY not in text and quote(KEY, safe="") not in text
        assert len(closed) == 1


@pytest.mark.parametrize("field", ["lastDividend", "lastDiv"])
def test_profile_dividend_alias_and_verified_zero(scripted, capsys, field):
    scripted(Response([{"symbol": "AAPL", field: 2.0, "price": 100.0}]))
    assert bs.get_dividend_yield("AAPL", KEY) == 0.02
    scripted(Response([{"symbol": "AAPL", field: 0.0, "price": 100.0}]))
    assert bs.get_dividend_yield("AAPL", KEY) == 0.0
    assert "fallback" not in capsys.readouterr().err


@pytest.mark.parametrize(
    "row",
    [
        {},
        {"symbol": "OTHER", "price": 100, "lastDividend": 2},
        {"symbol": "AAPL", "price": 0, "lastDividend": 2},
        {"symbol": "AAPL", "price": 100, "lastDividend": float("nan")},
        {"symbol": "AAPL", "price": 1e-308, "lastDividend": 1e308},
    ],
)
def test_unavailable_profile_is_explicit_legacy_zero_not_confirmed_no_dividend(
    scripted, capsys, row
):
    scripted(Response([row]))
    assert bs.get_dividend_yield("AAPL", KEY) == 0.0
    assert "unverified" in capsys.readouterr().err.lower()


def test_missing_key_never_uses_ambient_credentials(scripted, monkeypatch):
    calls, _ = scripted()
    monkeypatch.setenv("FMP_API_KEY", "another-fictional-value")
    assert bs.get_current_stock_price("AAPL", "") is None
    assert not calls


@pytest.mark.parametrize("failure", ["request", "close"])
def test_session_failures_discard_quote_and_redact_diagnostics(
    scripted, monkeypatch, capsys, failure
):
    calls, _ = scripted(Response([{"symbol": "AAPL", "price": 150}]))
    closed = []

    def fail(*args, **kwargs):
        raise RuntimeError("provider echoed " + KEY + " " + quote(KEY, safe=""))

    def close(session):
        closed.append(session)
        if failure == "close":
            fail()

    monkeypatch.setattr(requests.Session, "close", close)
    if failure == "request":
        monkeypatch.setattr(requests.Session, "get", fail)
    assert bs.get_current_stock_price("AAPL", KEY) is None
    assert len(closed) == 1
    assert len(calls) == (1 if failure == "close" else 0)
    output = capsys.readouterr()
    assert "unavailable" in output.err
    assert KEY not in output.out + output.err
    assert quote(KEY, safe="") not in output.out + output.err


@pytest.mark.parametrize(
    "payload",
    [
        {"historicalStockList": {}},
        {"historicalStockList": [None]},
        {"historicalStockList": [], "historical": history()},
        {"symbol": "AAPL", "historical": [None]},
    ],
)
def test_malformed_history_envelopes_are_unavailable_and_close_session(scripted, payload):
    calls, closed = scripted(Response(payload))
    assert bs.fetch_historical_prices_for_hv("AAPL", KEY, as_of=AS_OF) is None
    assert len(calls) == len(closed) == 1


@pytest.mark.parametrize("as_of", ["2026-11-20", 42, datetime(2026, 11, 20)])
def test_invalid_as_of_rejected_before_http(scripted, as_of):
    calls, closed = scripted()
    with pytest.raises(ValueError, match="as_of must be a date"):
        bs.fetch_historical_prices_for_hv("AAPL", KEY, as_of=as_of)
    assert not calls and not closed


def test_manual_demo_and_formulas_never_need_http():
    script = Path(bs.__file__).resolve()
    code = (
        'import requests,runpy\nrequests.Session.get=lambda *a,**k: (_ for _ in ()).throw(AssertionError("HTTP forbidden"))\nrunpy.run_path('
        + repr(str(script))
        + ',run_name="__main__")'
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    assert "CALL OPTION" in result.stdout and "PUT OPTION" in result.stdout


def test_history_does_not_mutate_evidence(scripted):
    import copy

    rows = history()[::-1]
    original = copy.deepcopy(rows)
    scripted(Response(rows))
    assert bs.fetch_historical_prices_for_hv("aapl", KEY, 2, as_of=AS_OF) == [101.0, 102.0]
    assert rows == original


def test_foreign_outer_identity_is_rejected_even_with_matching_batch(scripted):
    scripted(
        Response(
            {
                "symbol": "OTHER",
                "historicalStockList": [{"symbol": "AAPL", "historical": history()}],
            }
        )
    )
    assert bs.fetch_historical_prices_for_hv("AAPL", KEY, as_of=AS_OF) is None


def test_other_skills_cached_client_cannot_be_selected(scripted, monkeypatch):
    import types

    other = types.SimpleNamespace(FMPClient=None)
    monkeypatch.setitem(sys.modules, "fmp_client", other)
    scripted(Response([{"symbol": "AAPL", "price": "150.0"}]))
    assert bs.get_current_stock_price("AAPL", KEY) == 150.0
    assert sys.modules["fmp_client"] is other


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        [{"symbol": "OTHER", "price": 100}],
        [{"price": 100}],
        [{"symbol": "AAPL", "price": 100}] * 2,
    ],
)
def test_quote_requires_one_matching_record(scripted, payload):
    scripted(Response(payload))
    assert bs.get_current_stock_price("AAPL", KEY) is None


def test_manual_model_import_without_requests():
    code = "import sys;sys.modules['requests']=None;sys.path.insert(0,sys.argv[1]);import black_scholes;assert black_scholes.OptionPricer(100,100,1,.03,.2).call_price()>0"
    result = subprocess.run(
        [sys.executable, "-c", code, str(Path(bs.__file__).parent)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


def test_extracted_package_uses_adjacent_transport_and_closes_session(tmp_path):
    import zipfile

    root = Path(__file__).resolve().parents[4]
    with zipfile.ZipFile(root / "skill-packages/options-strategy-advisor.skill") as archive:
        archive.extractall(tmp_path)
    scripts = tmp_path / "options-strategy-advisor/scripts"
    code = """
import sys, types, requests
sys.path.insert(0, sys.argv[1])
sys.modules['fmp_client'] = types.SimpleNamespace(FMPClient=None)
closed = []
class Response:
    status_code = 200
    def json(self):
        return [{'symbol': 'AAPL', 'price': 150}]
class Session:
    def get(self, url, params, timeout):
        assert url.endswith('/stable/quote') and timeout == 30
        assert params == {'symbol': 'AAPL', 'apikey': 'fictional-marker'}  # pragma: allowlist secret
        return Response()
    def close(self):
        closed.append(True)
requests.Session = Session
import black_scholes
assert black_scholes.get_current_stock_price('AAPL', 'fictional-marker') == 150.0
assert closed == [True]
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(scripts)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "guide",
    [
        "skills/options-strategy-advisor/SKILL.md",
        "docs/en/skills/options-strategy-advisor.md",
        "docs/ja/skills/options-strategy-advisor.md",
    ],
)
def test_documented_hv_example_has_enough_prices_for_returns(scripted, guide):
    import math
    from datetime import timedelta

    root = Path(__file__).resolve().parents[4]
    text = (root / guide).read_text()
    start = text.index("from black_scholes import fetch_historical_prices_for_hv,")
    code = text[start : text.index("```", start)]
    rows = [
        {
            "symbol": "AAPL",
            "date": (date(2020, 12, 1) - timedelta(days=i)).isoformat(),
            "close": 100 + (i % 7),
        }
        for i in range(91)
    ]
    scripted(Response(rows))
    namespace = {"api_key": KEY}
    exec(code, namespace)
    assert math.isfinite(namespace["HV"]) and namespace["HV"] > 0
    scripted(Response(rows[:90]))
    with pytest.raises(ValueError, match="evidence unavailable"):
        exec(code, {"api_key": KEY})
