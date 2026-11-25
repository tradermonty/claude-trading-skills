"""Transport and fallback contract of this skill's generated FMP client."""

import requests
from fmp_client import FMPClient


class Response:
    def __init__(self, status, payload=None, body=""):
        self.status_code = status
        self.payload = payload
        self.text = body

    def json(self):
        return self.payload


class Session:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def get(self, url, *, params, timeout):
        self.calls.append((url, dict(params), timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def client(*outcomes):
    result = FMPClient(api_key="secret")
    result.session = Session(*outcomes)
    return result


def test_header_auth_and_cached_calendar():
    c = client(Response(200, [{"event": "CPI"}]))
    first = c.get_economic_calendar("2026-01-01", "2026-01-02")
    assert first == [{"event": "CPI"}]
    assert c.get_economic_calendar("2026-01-01", "2026-01-02") is first
    assert len(c.session.calls) == 1
    url, params, timeout = c.session.calls[0]
    assert url.endswith("/stable/economic-calendar")
    assert params == {"from": "2026-01-01", "to": "2026-01-02"}
    assert timeout == 30
    assert c.get_api_stats() == {
        "cache_entries": 1,
        "api_calls_made": 1,
        "rate_limit_reached": False,
    }


def test_http_error_redacts_query_key_and_preserves_status():
    c = client(Response(403, body="denied https://host/path?apikey=secret"))
    assert c._rate_limited_get("https://host/path", quiet=True) is None
    assert c._last_error == "HTTP 403 - denied https://host/path?apikey=REDACTED"
    assert c.api_calls_made == 1


def test_transport_error_redacts_query_key():
    c = client(requests.ConnectionError("https://host/path?apikey=secret"))
    assert c._rate_limited_get("https://host/path") is None
    assert c._last_error == "request exception: https://host/path?apikey=REDACTED"


def test_rate_limit_retries_then_stops(monkeypatch):
    monkeypatch.setattr("fmp_client.time.sleep", lambda _: None)
    c = client(Response(429), Response(429))
    assert c._rate_limited_get("https://host/path") is None
    assert c.rate_limit_reached
    assert c._last_error == "HTTP 429 (daily rate limit)"
    assert c.api_calls_made == 2
    assert c._rate_limited_get("https://host/path") is None
    assert c._last_error == "daily rate limit already reached"
    assert len(c.session.calls) == 2


def test_historical_fallback_normalizes_and_caches(monkeypatch):
    monkeypatch.setitem(
        FMPClient._request_with_fallback.__globals__,
        "_et_today",
        lambda: __import__("datetime").date(2026, 1, 10),
    )
    c = client(
        Response(403, body="stable forbidden"),
        Response(200, {"symbol": "ABC", "historical": [{"date": "2026-01-09"}]}),
    )
    result = c.get_historical_prices("ABC", days=2)
    assert result == {"symbol": "ABC", "historical": [{"date": "2026-01-09"}]}
    assert c.get_historical_prices("ABC", days=2) is result
    assert len(c.session.calls) == 2
    assert c.session.calls[0][1] == {"symbol": "ABC", "from": "2026-01-06", "to": "2026-01-10"}
    assert c.session.calls[1][0].endswith("/api/v3/historical-price-full/ABC")
    assert c.session.calls[1][1] == {"timeseries": 2}
    # A 403 is a per-call client/auth failure, not a provider outage: it must
    # not count toward the endpoint circuit breaker (#844).
    assert c._endpoint_failures.get(c.session.calls[0][0], 0) == 0


def test_historical_rejects_wrong_symbol_and_disables_failed_endpoint(monkeypatch):
    monkeypatch.setitem(
        FMPClient._request_with_fallback.__globals__,
        "_et_today",
        lambda: __import__("datetime").date(2026, 1, 10),
    )
    # The fallback endpoint returns a provider failure (500) so the breaker
    # still disables it; a 4xx would not count after #844.
    outcomes = [Response(200, [{"symbol": "WRONG", "date": "2026-01-09"}]), Response(500)] * 3
    c = client(*outcomes)
    for _ in range(3):
        assert c.get_historical_prices("ABC", days=2) is None
    assert len(c._disabled_endpoints) == 2
    assert c.get_historical_prices("ABC", days=2) is None
    assert len(c.session.calls) == 6
