"""A bad symbol must not poison cached responses or disable healthy symbols."""

import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fmp_client as CLIENT


def _client(tmp_path, *, max_api_calls):
    return CLIENT.FMPClient(
        api_key="test",  # pragma: allowlist secret - mocked transport only
        max_api_calls=max_api_calls,
        cache_path=tmp_path / "cache.sqlite",
        rate_limit_delay=0,
    )


def test_statement_error_object_is_not_cached(tmp_path):
    client = _client(tmp_path, max_api_calls=5)
    error = mock.Mock(status_code=200, json=lambda: {"message": "Exclusive endpoint"})
    good = mock.Mock(status_code=200, json=lambda: [{"symbol": "AAA", "revenue": 42}])
    with mock.patch.object(client.session, "get", side_effect=[error, error, good]) as transport:
        assert client.get_income_statement("AAA") == []
        assert client.get_income_statement("AAA") == [{"symbol": "AAA", "revenue": 42}]
        assert transport.call_count == 3
    client.close()


def test_previously_cached_statement_error_is_evicted(tmp_path):
    client = _client(tmp_path, max_api_calls=2)
    url = f"{client.STABLE_URL}/income-statement"
    key = client.cache.make_key(url, {"symbol": "AAA", "period": "annual", "limit": 6})
    client.cache.put(key, {"message": "Exclusive endpoint"})
    good = mock.Mock(status_code=200, json=lambda: [{"symbol": "AAA", "revenue": 42}])
    with mock.patch.object(client.session, "get", return_value=good) as transport:
        assert client.get_income_statement("AAA") == [{"symbol": "AAA", "revenue": 42}]
        assert client.get_income_statement("AAA") == [{"symbol": "AAA", "revenue": 42}]
        assert transport.call_count == 1
    client.close()


def test_bad_estimate_rows_do_not_disable_other_symbols(tmp_path):
    client = _client(tmp_path, max_api_calls=10)
    bad = mock.Mock(status_code=200, json=lambda: [{"date": "2027-12-31", "epsAvg": None}])
    good = mock.Mock(status_code=200, json=lambda: [{"date": "2027-12-31", "epsAvg": 1}])

    def response(url, **kwargs):
        return good if kwargs.get("params", {}).get("symbol") == "GOOD" else bad

    with mock.patch.object(client.session, "get", side_effect=response) as transport:
        for symbol in ("BAD1", "BAD2", "BAD3"):
            assert client.get_analyst_estimates_detailed(symbol)["status"] == "failed"
        result = client.get_analyst_estimates_detailed("GOOD")
        assert result["status"] == "ok"
        assert transport.call_count == 7
    client.close()


def test_repeated_server_errors_still_trip_endpoint_breaker(tmp_path):
    client = _client(tmp_path, max_api_calls=10)
    error = mock.Mock(status_code=500)
    with mock.patch.object(client.session, "get", return_value=error) as transport:
        for symbol in ("BAD1", "BAD2", "BAD3", "GOOD"):
            assert client.get_income_statement(symbol) == []
        stable_calls = [call for call in transport.call_args_list if "/stable/" in call.args[0]]
        assert len(stable_calls) == 3
    client.close()
