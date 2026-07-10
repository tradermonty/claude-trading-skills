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
