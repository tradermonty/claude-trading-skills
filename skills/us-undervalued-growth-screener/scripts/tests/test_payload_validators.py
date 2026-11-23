"""HTTP-200 error bodies must not be cached for any consumed endpoint (PR #856 review)."""

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fmp_client as CLIENT

ERROR_BODY = {"message": "Exclusive Endpoint"}


def _client(tmp_path, *, max_api_calls=10):
    return CLIENT.FMPClient(
        api_key="test",  # pragma: allowlist secret - mocked transport only
        max_api_calls=max_api_calls,
        cache_path=tmp_path / "cache.sqlite",
        rate_limit_delay=0,
    )


def _resp(payload):
    return mock.Mock(status_code=200, json=lambda: payload)


def _recovers(tmp_path, call, good_payload):
    """Error body on stable + v3 fallback first, then a good body: must recover."""
    client = _client(tmp_path)
    sequence = [_resp(ERROR_BODY), _resp(ERROR_BODY), _resp(good_payload)]
    with mock.patch.object(client.session, "get", side_effect=sequence) as transport:
        first = call(client)
        second = call(client)
        assert transport.call_count == 3
    client.close()
    return first, second


def test_ratios_ttm_error_body_is_not_cached(tmp_path):
    good = [{"symbol": "AAA", "peRatioTTM": 12}]
    first, second = _recovers(tmp_path, lambda c: c.get_ratios_ttm("AAA"), good)
    assert first == []
    assert second == good


def test_key_metrics_ttm_error_body_is_not_cached(tmp_path):
    good = [{"symbol": "BBB", "roicTTM": 0.2}]
    first, second = _recovers(tmp_path, lambda c: c.get_key_metrics_ttm("BBB"), good)
    assert first == []
    assert second == good


def test_profile_error_body_is_not_cached(tmp_path):
    good = [{"symbol": "CCC", "companyName": "C Corp"}]
    first, second = _recovers(tmp_path, lambda c: c.get_profile("CCC"), good)
    assert first is None
    assert second == good[0]


def test_stock_peers_error_body_is_not_cached(tmp_path):
    good = [{"symbol": "DDD", "peersList": ["EEE", "FFF"]}]
    first, second = _recovers(tmp_path, lambda c: c.get_stock_peers("DDD"), good)
    assert first == []
    assert second == ["EEE", "FFF"]


def test_quotes_error_body_is_not_cached(tmp_path):
    good = [{"symbol": "GGG", "price": 10}]
    first, second = _recovers(tmp_path, lambda c: c.get_quotes(["GGG"]), good)
    assert first == {}
    assert second == {"GGG": good[0]}


def _history(client):
    return client.get_historical_prices("HHH", from_date="2026-01-01", to_date="2026-01-05")


def test_historical_prices_error_body_is_not_cached(tmp_path):
    good = [{"date": "2026-01-02", "close": 5}]
    first, second = _recovers(tmp_path, _history, good)
    assert first == []
    assert second == good


def test_historical_prices_legacy_dict_shape_still_accepted(tmp_path):
    client = _client(tmp_path, max_api_calls=3)
    body = {"historical": [{"date": "2026-01-02", "close": 5}]}
    with mock.patch.object(client.session, "get", return_value=_resp(body)):
        assert _history(client) == body["historical"]
    client.close()


def test_genuine_empty_historical_prices_still_cached(tmp_path):
    client = _client(tmp_path, max_api_calls=3)
    with mock.patch.object(client.session, "get", return_value=_resp([])) as transport:
        assert _history(client) == []
        assert _history(client) == []
        assert transport.call_count == 1
    client.close()


def test_cached_error_body_is_evicted_for_ttm_endpoint(tmp_path):
    client = _client(tmp_path, max_api_calls=2)
    url = f"{client.STABLE_URL}/ratios-ttm"
    client.cache.put(client.cache.make_key(url, {"symbol": "AAA"}), ERROR_BODY)
    good = [{"symbol": "AAA", "peRatioTTM": 12}]
    with mock.patch.object(client.session, "get", return_value=_resp(good)) as transport:
        assert client.get_ratios_ttm("AAA") == good
        assert transport.call_count == 1
    client.close()


# --- Breaker exclusions and the schema-failure streak bound ---


def test_empty_response_does_not_trip_breaker(tmp_path):
    client = _client(tmp_path, max_api_calls=20)
    url = f"{client.STABLE_URL}/profile"
    with mock.patch.object(client.session, "get", return_value=_resp([])):
        for symbol in ("A1", "A2", "A3", "A4"):
            client._request_json(url, {"symbol": symbol})
    assert [f["reason"] for f in client.failures].count("empty_response") == 4
    assert not any(client._endpoint_failures.values())
    assert not client._disabled_endpoints
    client.close()


def test_cached_payload_invalid_does_not_trip_breaker(tmp_path):
    client = _client(tmp_path, max_api_calls=20)
    url = f"{client.STABLE_URL}/income-statement"
    good = [{"symbol": "X", "revenue": 1}]
    with mock.patch.object(client.session, "get", return_value=_resp(good)):
        for symbol in ("A1", "A2", "A3", "A4"):
            params = {"symbol": symbol}
            client.cache.put(client.cache.make_key(url, params), ERROR_BODY)
            client._request_json(url, params, validate=CLIENT._valid_records_payload)
    assert [f["reason"] for f in client.failures].count("cached_payload_invalid") == 4
    assert not any(client._endpoint_failures.values())
    assert not client._disabled_endpoints
    client.close()


def test_repeated_schema_failures_without_success_disable_endpoint(tmp_path):
    client = _client(tmp_path, max_api_calls=100)
    threshold = client.SCHEMA_FAILURE_STREAK_THRESHOLD
    url = f"{client.STABLE_URL}/income-statement"
    with mock.patch.object(client.session, "get", return_value=_resp([ERROR_BODY])) as transport:
        for i in range(threshold + 5):
            client._request_json(url, {"symbol": f"S{i}"}, validate=CLIENT._valid_records_payload)
        assert transport.call_count == threshold
    assert url in client._disabled_endpoints
    client.close()


def test_schema_failure_streak_resets_on_success(tmp_path):
    client = _client(tmp_path, max_api_calls=200)
    threshold = client.SCHEMA_FAILURE_STREAK_THRESHOLD
    url = f"{client.STABLE_URL}/income-statement"
    bad, good = _resp([ERROR_BODY]), _resp([{"symbol": "OK", "revenue": 1}])
    sequence = [bad] * (threshold - 1) + [good] + [bad] * (threshold - 1)
    with mock.patch.object(client.session, "get", side_effect=sequence):
        for i in range(len(sequence)):
            client._request_json(url, {"symbol": f"S{i}"}, validate=CLIENT._valid_records_payload)
    assert url not in client._disabled_endpoints
    client.close()
