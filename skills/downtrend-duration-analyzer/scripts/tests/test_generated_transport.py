"""#495: exercise domain adapters through generated fake HTTP sessions, offline."""

import importlib
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import quote, quote_plus

import analyze_downtrends as adt
import pytest
import requests

SECRET = "fictional/key+with spaces?"  # pragma: allowlist secret


class Response:
    def __init__(self, payload=None, status=200, text="", invalid=False):
        self.payload, self.status_code, self.text, self.invalid = payload, status, text, invalid

    def json(self):
        if self.invalid:
            raise ValueError(f"invalid JSON {SECRET}")
        return self.payload


class Session:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}
        self.closed = False

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params), timeout))
        assert self.responses, "unexpected HTTP request"
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        self.closed = True


def bar(day="2020-01-02", **kwargs):
    return {
        "date": day,
        "open": 100,
        "high": 110,
        "low": 90,
        "close": 105,
        "volume": 1234,
        **kwargs,
    }


@pytest.fixture
def client(monkeypatch):
    value = adt.FMPClient(SECRET)
    value.session.close()
    value.RATE_LIMIT_DELAY = 0
    module = importlib.import_module(value.__class__.__module__)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    yield value
    value.session.close()


def history(client, symbol="AAA", start="2020-01-01", end="2020-01-31"):
    return adt.fetch_historical_prices(SECRET, symbol, start, end, client=client)


def test_screener_params_and_query_auth(client):
    rows = [{"symbol": "AAA", "sector": "Energy", "marketCap": 5e9}]
    client.session = Session(Response(rows))
    assert adt.fetch_stock_list(SECRET, "Energy", client=client) == rows
    assert client.session.calls == [
        (
            "https://financialmodelingprep.com/stable/company-screener",
            {"isActivelyTrading": "true", "limit": 500, "sector": "Energy", "apikey": SECRET},
            30,
        )
    ]
    assert "apikey" not in client.session.headers
    assert not client.session.closed


def test_no_sector_filter_when_unspecified(client):
    client.session = Session(Response([]))
    assert adt.fetch_stock_list(SECRET, client=client) == []
    assert "sector" not in client.session.calls[0][1]


def test_flat_stable_history_exact_range_sorting_and_values(client):
    rows = [bar("2020-01-03", close=109), bar(), bar("2020-02-01", close=107)]
    client.session = Session(Response(rows))
    frame = history(client)
    assert list(frame) == ["date", "open", "high", "low", "close", "volume"]
    assert frame.date.dt.strftime("%Y-%m-%d").tolist() == ["2020-01-02", "2020-01-03"]
    assert frame.close.tolist() == [105, 109]
    assert frame.volume.tolist() == [1234, 1234]
    assert client.session.calls == [
        (
            "https://financialmodelingprep.com/stable/historical-price-eod/full",
            {"symbol": "AAA", "from": "2020-01-01", "to": "2020-01-31", "apikey": SECRET},
            30,
        )
    ]
    assert not client.session.closed


def test_long_past_window_has_no_today_bound_or_row_limit(client):
    start = date(2015, 1, 1)
    rows = [bar((start + timedelta(days=i)).isoformat()) for i in range(1000)]
    client.session = Session(Response(list(reversed(rows))))
    frame = history(client, start=rows[0]["date"], end=rows[-1]["date"])
    assert len(frame) == 1000
    assert frame.date.dt.strftime("%Y-%m-%d").tolist() == [r["date"] for r in rows]
    assert "timeseries" not in client.session.calls[0][1]


@pytest.mark.parametrize(
    "payload", [None, {}, "bad", [None], [{"symbol": None}], [{"symbol": " "}]]
)
def test_invalid_screener_payload_is_visible(client, payload, capsys):
    client.session = Session(Response(payload))
    assert adt.fetch_stock_list(SECRET, client=client) == []
    assert "Error fetching stock list" in capsys.readouterr().err
    assert len(client.session.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        "bad",
        [None],
        [{"date": "2020-01-02"}],
        [bar(date="invalid")],
        [bar(close=None)],
        [bar(close=True)],
        [bar(close="105")],
        [bar(close=float("nan"))],
        [bar(volume=float("inf"))],
        [bar(symbol="BBB")],
    ],
)
def test_invalid_history_is_visible_and_never_fabricated(client, payload, capsys):
    client.session = Session(Response(payload))
    assert history(client).empty
    assert "Error fetching prices" in capsys.readouterr().err
    assert len(client.session.calls) == 1


def test_dot_hyphen_symbol_equivalence(client):
    client.session = Session(Response([bar(symbol="BRK.B")]))
    assert len(history(client, symbol="BRK-B")) == 1


@pytest.mark.parametrize("kind", ["empty", "http", "shape"])
def test_multiple_failures_do_not_disable_later_symbol(client, kind):
    response = {"empty": Response([]), "http": Response(status=403), "shape": Response({})}[kind]
    client.session = Session(*([response] * 4), Response([bar()]))
    for _ in range(4):
        assert history(client).empty
    assert len(history(client, symbol="ZZZ")) == 1
    assert len(client.session.calls) == 5
    assert all("/stable/" in c[0] for c in client.session.calls)


@pytest.mark.parametrize("route", ["screener", "history"])
@pytest.mark.parametrize("failure", ["request", "http", "json"])
def test_generated_failures_redact_raw_and_encoded_keys(client, route, failure, capsys):
    text = " ".join([SECRET, quote(SECRET, safe=""), quote_plus(SECRET, safe="")])
    result = {
        "request": requests.ConnectionError(text),
        "http": Response(status=403, text=text),
        "json": Response(invalid=True),
    }[failure]
    client.session = Session(result, result)
    if route == "screener":
        assert adt.fetch_stock_list(SECRET, client=client) == []
    else:
        assert history(client).empty
    captured = capsys.readouterr()
    diagnostics = captured.out + captured.err + str(client._last_error)
    assert captured.err
    for secret in [SECRET, quote(SECRET, safe=""), quote_plus(SECRET, safe="")]:
        assert secret not in diagnostics
    assert len(client.session.calls) == (2 if failure == "json" else 1)


@pytest.mark.parametrize("status", [429, "invalid-json"])
def test_bounded_shared_retry_preserves_exact_request(client, status):
    first = Response(status=429) if status == 429 else Response(invalid=True)
    client.session = Session(first, Response([bar()]))
    assert len(history(client)) == 1
    assert len(client.session.calls) == 2
    assert client.session.calls[0] == client.session.calls[1]


def test_quota_exhaustion_stops_further_network_calls(client):
    client.session = Session(Response(status=429), Response(status=429))
    assert history(client).empty
    assert history(client, symbol="BBB").empty
    assert len(client.session.calls) == 2


def test_main_reuses_and_closes_one_client(monkeypatch, tmp_path):
    module = importlib.import_module(adt.FMPClient.__module__)
    session = Session(
        Response([{"symbol": "AAA"}, {"symbol": "BBB"}]), Response([bar()]), Response([bar()])
    )
    created = []

    def factory():
        created.append(session)
        return session

    monkeypatch.setattr(module.requests, "Session", factory)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    monkeypatch.setattr(
        sys, "argv", ["analyze_downtrends.py", "--api-key", SECRET, "--output-dir", str(tmp_path)]
    )
    adt.main()
    assert len(created) == 1 and session.closed
    assert len(session.calls) == 3
    assert {c[1].get("symbol") for c in session.calls[1:]} == {"AAA", "BBB"}
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_main_closes_client_on_system_exit(monkeypatch, tmp_path):
    module = importlib.import_module(adt.FMPClient.__module__)
    session = Session(Response([]))
    monkeypatch.setattr(module.requests, "Session", lambda: session)
    monkeypatch.setattr(
        sys, "argv", ["analyze_downtrends.py", "--api-key", SECRET, "--output-dir", str(tmp_path)]
    )
    with pytest.raises(SystemExit) as exc:
        adt.main()
    assert exc.value.code == 1 and session.closed
    assert not list(tmp_path.glob("*.json"))


def test_main_closes_client_on_unexpected_exception(monkeypatch, tmp_path):
    module = importlib.import_module(adt.FMPClient.__module__)
    session = Session(Response([{"symbol": "AAA"}]))
    monkeypatch.setattr(module.requests, "Session", lambda: session)
    monkeypatch.setattr(
        adt, "analyze_symbol", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("test"))
    )
    monkeypatch.setattr(
        sys, "argv", ["analyze_downtrends.py", "--api-key", SECRET, "--output-dir", str(tmp_path)]
    )
    with pytest.raises(RuntimeError, match="test"):
        adt.main()
    assert session.closed


@pytest.mark.parametrize("route", ["screener", "history"])
def test_standalone_helper_closes_its_own_client(monkeypatch, route):
    module = importlib.import_module(adt.FMPClient.__module__)
    session = Session(Response([]))
    monkeypatch.setattr(module.requests, "Session", lambda: session)
    if route == "screener":
        assert adt.fetch_stock_list(SECRET) == []
    else:
        assert adt.fetch_historical_prices(SECRET, "AAA", "2020-01-01", "2020-01-31").empty
    assert session.closed


@pytest.mark.parametrize("source", ["cli", "env"])
def test_blank_key_exits_cleanly_before_transport(monkeypatch, source, capsys):
    monkeypatch.setenv("FMP_API_KEY", "usable-env-key" if source == "cli" else " \t ")
    argv = (
        ["analyze_downtrends.py", "--api-key", " \t "]
        if source == "cli"
        else ["analyze_downtrends.py"]
    )
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc:
        adt.main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert "API key required" in output.err and "Traceback" not in output.err


def test_foreign_fmp_module_is_preserved(tmp_path):
    script_dir = Path(adt.__file__).resolve().parent
    code = """
import sys, types
sys.path.insert(0, sys.argv[1])
foreign = types.SimpleNamespace(FMPClient=object)
sys.modules["fmp_client"] = foreign
import analyze_downtrends as target
from pathlib import Path
assert Path(sys.modules[target.FMPClient.__module__].__file__).resolve() == Path(sys.argv[1]) / "fmp_client.py"
assert hasattr(target.FMPClient, "fetch_downtrend_history")
assert sys.modules["fmp_client"] is foreign
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(script_dir)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
