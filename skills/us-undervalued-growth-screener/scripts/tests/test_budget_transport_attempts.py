"""Timeouts must consume dispatch budget like any other transport attempt.

Issue #607: the global counter used to advance only after session.get
returned a response, so a ReadTimeout cost zero budget and stable->v3
fallback plus later symbols could transport far beyond max_api_calls.
"""

import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fmp_client as CLIENT


def _client(tmp_path, *, max_api_calls=1, rate_limit_delay=0):
    return CLIENT.FMPClient(
        api_key="test",  # pragma: allowlist secret - mocked transport only
        max_api_calls=max_api_calls,
        cache_path=tmp_path / "cache.sqlite",
        rate_limit_delay=rate_limit_delay,
    )


def _timeout_client(tmp_path, **kwargs):
    client = _client(tmp_path, **kwargs)
    transport = mock.Mock(side_effect=CLIENT.requests.ReadTimeout("fictional timeout"))
    return client, transport


def test_timeout_consumes_exact_budget(tmp_path):
    """AC-1: window budget of one allows exactly one dispatch attempt.

    The stable attempt is timed out and therefore consumed; the stable->v3
    fallback then meets the exhausted-budget guard and raises instead of
    transporting (issue repro: pre-fix `6 0 1`, post-fix `1 1 0`).
    """
    client, transport = _timeout_client(tmp_path)

    with mock.patch.object(client.session, "get", transport):
        with pytest.raises(CLIENT.ApiCallBudgetExceeded):
            client.get_profile("AAA")

    assert transport.call_count == 1
    assert client.api_calls_made == 1
    assert client.remaining_calls == 0


def test_next_symbol_cannot_bypass_cap(tmp_path):
    """AC-3: a second symbol cannot dispatch after the budget is exhausted."""
    client, transport = _timeout_client(tmp_path)

    with mock.patch.object(client.session, "get", transport):
        with pytest.raises(CLIENT.ApiCallBudgetExceeded):
            client.get_profile("AAA")
        with pytest.raises(CLIENT.ApiCallBudgetExceeded):
            client.get_profile("BBB")

    assert transport.call_count == 1
    assert client.api_calls_made == 1


def test_fallback_within_remaining_budget_returns_none(tmp_path):
    """AC-2a: two timed-out attempts exhaust a budget of two; no raise yet.

    get_profile returns None (stable and v3 both dispatched and consumed);
    a subsequent symbol with a zeroed remaining budget then raises.
    """
    client, transport = _timeout_client(tmp_path, max_api_calls=2)

    with mock.patch.object(client.session, "get", transport):
        profile = client.get_profile("AAA")
        assert profile is None
        assert transport.call_count == 2
        assert client.api_calls_made == 2
        with pytest.raises(CLIENT.ApiCallBudgetExceeded):
            client.get_profile("BBB")
    assert transport.call_count == 2


def test_pretripped_stable_refusal_consumes_zero(tmp_path):
    """AC-4 refusal leg + AC-2b: breaker-tripped stable URL refuses; only the
    v3 URL dispatches a counted HTTP-500 attempt (counted failures keep the
    accounting identical before and after #607).
    """
    client = _client(tmp_path, max_api_calls=2)
    client._disabled_endpoints.add(f"{client.STABLE_URL}/profile")
    transport = mock.Mock(return_value=mock.Mock(status_code=500, json=lambda: []))

    with mock.patch.object(client.session, "get", transport):
        profile = client.get_profile("AAA")

    assert profile is None
    assert transport.call_count == 1
    assert client.api_calls_made == 1
    assert remaining(client) == 1


def test_cache_hit_consumes_zero(tmp_path):
    """AC-4 cache leg: a cached payload is returned without dispatching."""
    client = _client(tmp_path, max_api_calls=1)
    key = client.cache.make_key(
        f"{client.STABLE_URL}/profile", {"symbol": "AAA", "apikey": client.api_key}
    )
    client.cache.put(key, [{"symbol": "AAA", "price": 12.0}])
    transport = mock.Mock(side_effect=AssertionError("transport must not be touched"))

    with mock.patch.object(client.session, "get", transport):
        profile = client.get_profile("AAA")

    assert profile == {"symbol": "AAA", "price": 12.0}
    assert client.api_calls_made == 0
    assert remaining(client) == 1


def test_paces_next_call_after_timeout(tmp_path):
    """A consumed attempt advances last_call_time and paces the next dispatch,
    even when the attempt failed with a transport exception."""
    client = _client(tmp_path, max_api_calls=2, rate_limit_delay=1.0)
    transport = mock.Mock(side_effect=CLIENT.requests.ReadTimeout("fictional timeout"))

    with (
        mock.patch.object(client.session, "get", transport),
        mock.patch.object(CLIENT.time, "sleep") as sleep,
    ):
        # Stable attempt (last_call_time init 0 -> no pacing), then the v3
        # fallback dispatch sees elapsed ~0 << delay and must sleep.
        assert client.get_profile("AAA") is None

    paced = [call.args[0] for call in sleep.call_args_list if call.args]
    assert paced and all(0 < value <= 1.0 for value in paced)
    assert transport.call_count == 2
    assert client.api_calls_made == 2
    assert client.last_call_time > 0


def test_success_path_for_three_symbols_counts_three(tmp_path):
    """Regression: normal 200 flows keep consuming exactly one per response."""
    client = _client(tmp_path, max_api_calls=3)
    payload = mock.Mock(status_code=200, json=lambda: [{"symbol": "S"}])
    transport = mock.Mock(side_effect=lambda *_args, **_kwargs: payload)

    with mock.patch.object(client.session, "get", transport):
        for symbol in ("AAA", "BBB", "CCC"):
            assert client.get_profile(symbol) == {"symbol": "S"}
        assert client.cache_hits == 0
        # The three responses were cached; a re-read is served from cache
        # before the (now exhausted) budget guard is reached.
        assert client.get_profile("AAA") == {"symbol": "S"}
        assert client.cache_hits == 1

    assert transport.call_count == 3
    assert client.api_calls_made == 3


def remaining(client):
    return client.max_api_calls - client.api_calls_made
