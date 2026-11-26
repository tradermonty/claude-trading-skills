"""Nested/pair CoinGecko contracts, shared normalization and health boundaries."""

import copy
import json
from pathlib import Path

import pytest
import requests

from scripts import check_provider_contracts as cli
from scripts.provider_contracts import load_contracts, normalize_coingecko, validate_contract_file
from scripts.tests.test_coingecko_contracts import Response

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = {k: c for k, c in load_contracts(ROOT).items() if c.provider == "coingecko"}
BAD = [None, True, "1", 0, -1, float("nan"), float("inf"), 10**400]


@pytest.mark.parametrize("endpoint", ["global", "market-chart"])
def test_recorded_raw_response_normalizes_to_exact_fixture(endpoint):
    c = CONTRACTS[endpoint]
    assert normalize_coingecko(endpoint, c.response_fixture) == c.fixture
    assert validate_contract_file(c, ["crypto-regime-analyzer"]) == []
    mutated = copy.deepcopy(c)
    mutated.response_fixture = {}
    assert validate_contract_file(mutated, ["crypto-regime-analyzer"])
    mutated = copy.deepcopy(c)
    mutated.fixture[0][next(iter(mutated.required_fields))] = 42
    assert validate_contract_file(mutated, ["crypto-regime-analyzer"])


@pytest.mark.parametrize("endpoint", ["global", "market-chart"])
@pytest.mark.parametrize("value", BAD)
def test_non_numeric_or_nonfinite_values_fail_helper_and_actual_http_decoder(
    endpoint, value, monkeypatch
):
    payload = (
        {"data": {"market_cap_percentage": {"btc": value}}}
        if endpoint == "global"
        else {"prices": [[1000, value]]}
    )
    with pytest.raises(ValueError):
        normalize_coingecko(endpoint, payload)
    response = Response(json.dumps(payload).encode())
    monkeypatch.setattr(requests, "get", lambda *a, **k: response)
    result = cli.run_canary(
        {endpoint: CONTRACTS[endpoint]}, {"coingecko": cli._build_coingecko_fetch()}
    )[endpoint]
    assert not result["ok"] and result["rows"] == 1 and response.closed
    assert {a["code"] for a in result["anomalies"]} == {"invalid_coingecko_payload"}


@pytest.mark.parametrize("value", BAD)
def test_singleton_bad_timestamp_is_detected_by_canary(value, monkeypatch):
    response = Response(json.dumps({"prices": [[value, 100]]}).encode())
    monkeypatch.setattr(requests, "get", lambda *a, **k: response)
    result = cli._build_coingecko_fetch()(CONTRACTS["market-chart"])
    assert result.rows is None and result.observed_rows == 1
    assert result.extra_anomalies and response.closed


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"prices": []},
        {"prices": None},
        {"prices": [[1]]},
        {"prices": [[1, 2, 3]]},
        {"prices": [[2, 2], [1, 3]]},
        {"prices": [[1, 2], [1, 3]]},
        {"renamed_prices": [[1, 2]]},
    ],
)
def test_chart_shape_and_order_fail_closed(payload):
    with pytest.raises(ValueError):
        normalize_coingecko("market-chart", payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"data": []},
        {"data": {}},
        {"data": {"renamed": {"btc": 55}}},
        {"data": {"market_cap_percentage": {}}},
        {"data": {"market_cap_percentage": {"btc": 101}}},
    ],
)
def test_global_shape_and_range_fail_closed(payload):
    with pytest.raises(ValueError):
        normalize_coingecko("global", payload)


def _report(results):
    return {
        "generated_at": "2026-11-26T00:00:00+00:00",
        "provider": "coingecko",
        "budget": {"max": 3, "used": 3},
        "ok": all(r["ok"] for r in results.values()),
        "contracts": results,
    }


def test_three_call_budget_and_ordered_normalization(tmp_path, monkeypatch):
    calls = []

    def get(url, **kw):
        calls.append((url, kw))
        c = next(c for c in CONTRACTS.values() if url.endswith(c.endpoint_path))
        payload = c.response_fixture if c.endpoint != "coins-markets" else c.fixture
        return Response(json.dumps(payload).encode())

    monkeypatch.setattr(requests, "get", get)
    path = tmp_path / "report.json"
    args = ["canary", "--provider", "coingecko", "--report", str(path)]
    assert cli.main(args + ["--max-calls", "2"]) == 1
    assert calls == [] and not path.exists()
    assert cli.main(args + ["--max-calls", "3"]) == 0
    report = json.loads(path.read_text())
    assert len(calls) == 3 and report["budget"] == {"used": 3, "max": 3}
    assert set(report["contracts"]) == set(CONTRACTS)
    assert cli.health_errors(report, set(CONTRACTS), "coingecko", "success", 0) == []
    for _, kw in calls:
        assert kw["timeout"] == 30 and not kw["allow_redirects"] and kw["stream"]


@pytest.mark.parametrize("failed_endpoint", ["coins-markets", "global", "market-chart"])
@pytest.mark.parametrize("kind", ["http", "empty", "drift"])
def test_all_probes_continue_and_only_response_drift_is_report_only(failed_endpoint, kind):
    calls = []

    def fetch(c):
        calls.append(c.endpoint)
        if c.endpoint == failed_endpoint:
            if kind == "http":
                return cli.FetchResult(429, None)
            if kind == "empty":
                return cli.FetchResult(200, [])
            return cli.FetchResult(
                200, None, [cli.Anomaly("invalid_coingecko_payload", "fatal")], 1
            )
        return cli.FetchResult(200, c.fixture)

    results = cli.run_canary(CONTRACTS, {"coingecko": fetch})
    assert set(calls) == set(CONTRACTS) and not results[failed_endpoint]["ok"]
    errors = cli.health_errors(_report(results), set(CONTRACTS), "coingecko", "failure", 1)
    assert bool(errors) == (kind != "drift")
    # Existing all-provider policy deliberately remains unchanged.
    report = _report(results)
    report["provider"] = "all"
    assert cli.health_errors(report, set(CONTRACTS), "all", "failure", 1) == []


@pytest.mark.parametrize("value", [True, -1, "1", 1.5])
def test_invalid_response_evidence_override_cannot_forge_health(value):
    result = cli.run_canary(
        {"global": CONTRACTS["global"]},
        {"coingecko": lambda c: cli.FetchResult(200, c.fixture, observed_rows=value)},
    )["global"]
    assert not result["ok"] and result["rows"] == 0
    assert any(a["code"] == "invalid_response_evidence_count" for a in result["anomalies"])
