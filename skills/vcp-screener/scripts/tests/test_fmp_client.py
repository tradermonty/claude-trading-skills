#!/usr/bin/env python3
"""Tests for FMPClient.get_sp500_constituents stable-first fallback.

The legacy api/v3/sp500_constituent endpoint now 403s for current API keys,
so the client tries stable/sp500-constituent first and falls back to v3.
These tests drive a fake requests.Session so no network is touched.
"""

from fmp_client import FMPClient

_STABLE = "stable/sp500-constituent"
_V3 = "api/v3/sp500_constituent"

_CONSTITUENTS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology", "subSector": "Hardware"},
    {"symbol": "MSFT", "name": "Microsoft Corp.", "sector": "Technology", "subSector": "Software"},
]


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


class _FakeSession:
    """Maps a URL substring to a canned response; records requested URLs."""

    def __init__(self, url_map):
        self._url_map = url_map
        self.headers = {}
        self.requested = []

    def get(self, url, params=None, timeout=None):
        self.requested.append(url)
        for fragment, response in self._url_map.items():
            if fragment in url:
                return response
        return _FakeResponse(404, None, "unmapped")


def _client(url_map):
    client = FMPClient(api_key="test-key")
    client.RATE_LIMIT_DELAY = 0  # no sleeps in tests
    client.session = _FakeSession(url_map)
    return client


def test_stable_endpoint_used_when_available():
    client = _client({_STABLE: _FakeResponse(200, _CONSTITUENTS)})
    result = client.get_sp500_constituents()
    assert result == _CONSTITUENTS
    # v3 must not be called once stable succeeds.
    assert not any(_V3 in u for u in client.session.requested)


def test_falls_back_to_v3_on_stable_403():
    client = _client(
        {
            _STABLE: _FakeResponse(403, None, "Forbidden"),
            _V3: _FakeResponse(200, _CONSTITUENTS),
        }
    )
    result = client.get_sp500_constituents()
    assert result == _CONSTITUENTS
    assert any(_STABLE in u for u in client.session.requested)
    assert any(_V3 in u for u in client.session.requested)


def test_falls_back_when_stable_returns_wrong_shape():
    # Truthy-but-invalid payload (error dict) must not be accepted as data.
    client = _client(
        {
            _STABLE: _FakeResponse(200, {"Error Message": "Legacy Endpoint"}),
            _V3: _FakeResponse(200, _CONSTITUENTS),
        }
    )
    result = client.get_sp500_constituents()
    assert result == _CONSTITUENTS
    assert any(_V3 in u for u in client.session.requested)


# On free-tier keys created after 2025-08-31, NO FMP endpoint serves
# constituents: stable/sp500-constituent 402s (Restricted Endpoint) and
# api/v3/sp500_constituent 403s (Legacy Endpoint). The client then falls
# back to the public datasets/s-and-p-500-companies CSV.

_CSV_TEXT = (
    "Symbol,Security,GICS Sector,GICS Sub-Industry,Headquarters Location,"
    "Date added,CIK,Founded\n"
    'MMM,3M,Industrials,Industrial Conglomerates,"Saint Paul, Minnesota",'
    "1957-03-04,66740,1902\n"
    'BRK.B,Berkshire Hathaway,Financials,Multi-Sector Holdings,"Omaha, Nebraska",'
    "2010-02-16,1067983,1839\n"
)

_NO_FMP_TIER = {
    _STABLE: _FakeResponse(402, None, "Restricted Endpoint"),
    _V3: _FakeResponse(403, None, "Legacy Endpoint"),
}


def test_falls_back_to_public_csv_when_no_fmp_tier_serves_constituents(monkeypatch):
    client = _client(dict(_NO_FMP_TIER))
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeResponse(200, None, _CSV_TEXT)

    monkeypatch.setattr("fmp_client.requests.get", fake_get)
    result = client.get_sp500_constituents()

    # Dot-class symbols are normalized to FMP's dash style (BRK.B -> BRK-B).
    assert [c["symbol"] for c in result] == ["MMM", "BRK-B"]
    assert result[0] == {
        "symbol": "MMM",
        "name": "3M",
        "sector": "Industrials",
        "subSector": "Industrial Conglomerates",
    }
    assert "s-and-p-500-companies" in captured["url"]
    # The FMP apikey session header must not leak to the public host.
    assert "headers" not in captured["kwargs"]
    assert not any("s-and-p-500-companies" in u for u in client.session.requested)


def test_returns_none_when_fmp_and_csv_fallback_all_fail(monkeypatch):
    client = _client(dict(_NO_FMP_TIER))
    monkeypatch.setattr(
        "fmp_client.requests.get",
        lambda url, **kwargs: _FakeResponse(500, None, "upstream down"),
    )
    assert client.get_sp500_constituents() is None


def test_csv_fallback_not_used_when_fmp_succeeds(monkeypatch):
    client = _client({_STABLE: _FakeResponse(200, _CONSTITUENTS)})

    def fail_get(url, **kwargs):
        raise AssertionError("public CSV must not be fetched when FMP works")

    monkeypatch.setattr("fmp_client.requests.get", fail_get)
    assert client.get_sp500_constituents() == _CONSTITUENTS
