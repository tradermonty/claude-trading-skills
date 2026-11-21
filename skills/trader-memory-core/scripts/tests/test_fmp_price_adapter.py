"""Exercise the adapter through the actual generated client's fake HTTP session."""

import subprocess
import sys
import traceback
import types
import urllib.error
import zipfile
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote, quote_plus

import fmp_price_adapter
import pytest
import requests
import thesis_review

SECRET = "memory-marker /+&key"  # pragma: allowlist secret


class Response:
    def __init__(self, data=None, status=200, text=""):
        self.data, self.status_code, self.text = data, status, text

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}
        self.closed = False

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.closed = True


def row(day="2020-01-02", close=110, **kw):
    return {"symbol": "AAA", "date": day, "close": close, **kw}


@pytest.fixture
def http(monkeypatch):
    sessions = []

    def configure(*responses):
        session = Session(*responses)
        sessions.append(session)
        return session

    def factory():
        assert sessions, "unexpected request"
        return sessions[-1]

    monkeypatch.setattr(requests, "Session", factory)
    monkeypatch.setattr("time.sleep", lambda _: None)
    # The pre-migration adapter must fail rather than perform a real HTTP call.
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("legacy HTTP used"))
    return configure


def get(adapter=None, ticker="AAA", start="2020-01-01", end="2020-01-31"):
    return (adapter or fmp_price_adapter.FMPPriceAdapter(SECRET)).get_daily_closes(
        ticker, start, end
    )


def test_explicit_range_real_transport_and_adjusted_preference(http):
    session = http(
        Response([row("2020-02-01"), row("2020-01-03", adjClose=105), row(), row("2019-12-31")])
    )
    assert get() == [{"date": "2020-01-02", "close": 110.0}, {"date": "2020-01-03", "close": 105.0}]
    assert session.calls == [
        (
            "https://financialmodelingprep.com/stable/historical-price-eod/full",
            {"symbol": "AAA", "from": "2020-01-01", "to": "2020-01-31", "apikey": SECRET},
            30,
        )
    ]
    assert "Authorization" not in session.headers
    assert session.closed


def test_empty_history_never_falls_back_and_later_call_works(http):
    session = http(Response([]))
    adapter = fmp_price_adapter.FMPPriceAdapter(SECRET)
    assert get(adapter) == []
    assert len(session.calls) == 1 and session.closed
    later = http(Response([row()]))
    assert get(adapter) == [{"date": "2020-01-02", "close": 110.0}]
    assert later.closed


def test_past_long_range_never_truncated(http):
    start = date(2015, 1, 1)
    rows = [row((start + timedelta(days=i)).isoformat()) for i in range(1000)]
    session = http(Response(list(reversed(rows))))
    result = get(start=rows[0]["date"], end=rows[-1]["date"])
    assert [r["date"] for r in result] == [r["date"] for r in rows]
    assert "timeseries" not in session.calls[0][1]


@pytest.mark.parametrize("symbol", ["BRK.B", "BRK-B", "brk.b"])
def test_symbol_equivalence(http, symbol):
    http(Response([row(symbol=symbol)]))
    assert get(ticker="BRK-B")[0]["close"] == 110


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"historical": [row()]},
        "bad",
        [None],
        [row(symbol=None)],
        [row(symbol="BBB")],
        [row(day="2020-02-30")],
        [row(day="20200102")],
        [row(day="2020-01-02T00:00:00Z")],
        [{"symbol": "AAA", "date": "2020-01-02"}],
        [row(), row()],
        [row(), row(symbol="BBB")],
    ],
)
def test_invalid_evidence_rejected(http, payload):
    session = http(Response(payload))
    with pytest.raises(ValueError, match="Invalid FMP price data"):
        get()
    assert session.closed
    assert len(session.calls) == 1


@pytest.mark.parametrize(
    "value", [None, True, False, 0, -1, "110", float("nan"), float("inf"), 10**1000]
)
@pytest.mark.parametrize("field", ["close", "adjClose"])
def test_invalid_price_never_falls_back_or_becomes_zero(http, value, field):
    session = http(Response([row(**{field: value})]))
    with pytest.raises(ValueError, match="Invalid FMP price data"):
        get()
    assert session.closed


@pytest.mark.parametrize(
    "start,end",
    [
        ("20200101", "2020-01-31"),
        ("bad", "2020-01-31"),
        ("2020-01-01", "2020-02-30"),
        ("2020-02-01", "2020-01-01"),
    ],
)
def test_invalid_date_range_makes_no_request(http, start, end):
    session = http(Response([row()]))
    with pytest.raises(ValueError):
        get(start=start, end=end)
    assert session.calls == []


def test_no_api_key_raises_before_network(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    with pytest.raises(ValueError, match="FMP API key required"):
        fmp_price_adapter.FMPPriceAdapter()


def test_env_and_explicit_key_precedence(http, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "environment-marker")
    session = http(Response([]))
    get(fmp_price_adapter.FMPPriceAdapter())
    assert session.calls[0][1]["apikey"] == "environment-marker"  # pragma: allowlist secret
    session = http(Response([]))
    get(fmp_price_adapter.FMPPriceAdapter(SECRET))
    assert session.calls[0][1]["apikey"] == SECRET


@pytest.mark.parametrize(
    "failure",
    [
        requests.ConnectionError(
            f"URL?apikey={SECRET} {quote(SECRET, safe='')} {quote_plus(SECRET)}"
        ),
        requests.Timeout(f"key {SECRET}"),
        Response(status=403, text=SECRET),
        Response(ValueError(SECRET)),
        Response(status=429),
    ],
)
def test_failures_safe_across_outputs_and_tracebacks(http, failure, capsys, caplog):
    session = http(failure, failure)
    with pytest.raises(urllib.error.URLError, match="FMP price request failed") as caught:
        get()
    output = capsys.readouterr()
    text = (
        output.out
        + output.err
        + caplog.text
        + "".join(traceback.format_exception(caught.type, caught.value, caught.tb))
    )
    for marker in [SECRET, quote(SECRET, safe=""), quote_plus(SECRET)]:
        assert marker not in text
    assert session.closed
    assert all("/stable/" in call[0] for call in session.calls)


def test_invalid_response_yields_null_mae_mfe(http):
    http(Response([row(close=float("nan"))]))
    thesis = {
        "ticker": "AAA",
        "entry": {"actual_price": 100, "actual_date": "2020-01-01"},
        "exit": {"actual_date": "2020-01-31"},
    }
    result = thesis_review.compute_mae_mfe(thesis, fmp_price_adapter.FMPPriceAdapter(SECRET))
    assert result == {"mae_pct": None, "mfe_pct": None, "mae_mfe_source": None}


def test_valid_response_calculates_mae_mfe(http):
    http(Response([row(close=90), row("2020-01-03", close=120)]))
    thesis = {
        "ticker": "AAA",
        "entry": {"actual_price": 100, "actual_date": "2020-01-01"},
        "exit": {"actual_date": "2020-01-31"},
    }
    assert thesis_review.compute_mae_mfe(thesis, fmp_price_adapter.FMPPriceAdapter(SECRET)) == {
        "mae_pct": -10.0,
        "mfe_pct": 20.0,
        "mae_mfe_source": "fmp_eod",
    }


def test_keyless_core_imports_do_not_load_requests():
    scripts = Path(fmp_price_adapter.__file__).parent
    code = "import sys; sys.path.insert(0, sys.argv[1]); sys.modules['requests'] = None; import fmp_price_adapter, thesis_review; assert thesis_review.compute_mae_mfe({})['mae_pct'] is None"
    result = subprocess.run(
        [sys.executable, "-c", code, str(scripts)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_global_module_collision_cannot_select_another_skill(http, monkeypatch):
    monkeypatch.setitem(sys.modules, "fmp_client", types.SimpleNamespace(FMPClient=None))
    http(Response([row()]))
    assert get()[0]["close"] == 110


def test_one_429_retry_uses_same_exact_range(http):
    session = http(Response(status=429), Response([row()]))
    assert get()[0]["close"] == 110
    assert len(session.calls) == 2 and session.calls[0] == session.calls[1]
    assert session.closed


def test_extracted_standalone_uses_its_own_generated_transport(tmp_path):
    root = Path(__file__).resolve().parents[4]
    package = root / "skill-packages/trader-memory-core.skill"
    with zipfile.ZipFile(package) as archive:
        archive.extractall(tmp_path)
    scripts = tmp_path / "trader-memory-core/scripts"
    code = """
import sys, types
sys.path.insert(0, sys.argv[1])
sys.modules['fmp_client'] = types.SimpleNamespace(FMPClient=None)
import requests
class Response:
    status_code = 200
    def json(self):
        return [{'symbol': 'AAA', 'date': '2020-01-02', 'close': 110}]
class Session:
    def get(self, url, params, timeout):
        assert '/stable/' in url and timeout == 30
        assert params == {'symbol': 'AAA', 'from': '2020-01-01', 'to': '2020-01-31', 'apikey': 'fictional-marker'}  # pragma: allowlist secret
        return Response()
    def close(self):
        pass
requests.Session = Session
from fmp_price_adapter import FMPPriceAdapter
assert FMPPriceAdapter('fictional-marker').get_daily_closes('AAA', '2020-01-01', '2020-01-31') == [{'date': '2020-01-02', 'close': 110.0}]
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(scripts)], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
