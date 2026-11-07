"""Recorded light-endpoint contract and real consumer boundary regressions."""

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from scripts.check_provider_contracts import run_canary
from scripts.provider_contracts import load_contracts, validate_contract_file, validate_rows

ROOT = Path(__file__).resolve().parents[2]
ENDPOINT = "historical-price-eod-light"


@pytest.fixture
def contract():
    return load_contracts(ROOT)[ENDPOINT]


@pytest.fixture
def nrf(monkeypatch):
    directory = ROOT / "skills/news-reaction-failure-analyzer/scripts"
    monkeypatch.syspath_prepend(str(directory))
    spec = importlib.util.spec_from_file_location(
        "light_contract_consumer", directory / "analyze_news_reaction.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    return module


def client_with(nrf, rows, status=200):
    response = SimpleNamespace(
        status_code=status, text="synthetic HTTP response", json=Mock(return_value=rows)
    )
    client = nrf.PriceClient("fixture-only", sleep_seconds=0)
    client.session.get = Mock(return_value=response)
    return client


def series(nrf, client, cutoff="2026-10-30", fallback=False):
    chain = [("SPY", "etf", False)]
    if fallback:
        chain.append(("QQQ", "etf", False))
    return nrf.fetch_price_series(client, chain, "2026-10-26", "2026-10-30", cutoff)


def test_recorded_contract_and_consumer_agree(contract, nrf):
    assert contract.endpoint_path == "/stable/historical-price-eod/light"
    assert contract.owners == ["news-reaction-failure-analyzer"]
    assert contract.query == {"symbol": "SPY", "from": "2026-10-26", "to": "2026-10-30"}
    assert len(contract.fixture) == 5
    assert not validate_contract_file(contract, contract.owners)
    client = client_with(nrf, copy.deepcopy(contract.fixture))
    result = series(nrf, client)
    assert result["error"] is None
    assert result["series"] == sorted((row["date"], row["price"]) for row in contract.fixture)
    assert result["proxy_used"] is True
    client.session.get.assert_called_once()
    assert client.session.get.call_args.args == (nrf.STABLE_EOD_URL,)
    assert client.session.get.call_args.kwargs["params"]["from"] == contract.query["from"]
    assert client.session.get.call_args.kwargs["timeout"] == 30


@pytest.mark.parametrize("field", ["date", "price"])
@pytest.mark.parametrize("mutation", ["missing", "renamed", "null", "wrong_type"])
def test_light_contract_detects_required_field_drift(contract, field, mutation):
    rows = copy.deepcopy(contract.fixture)
    for row in rows:
        if mutation == "missing":
            del row[field]
        elif mutation == "renamed":
            row[field + "_renamed"] = row.pop(field)
        else:
            row[field] = None if mutation == "null" else ({} if field == "date" else "unusable")
    assert not validate_rows(contract, rows).ok


@pytest.mark.parametrize("price", [float("nan"), float("inf"), -float("inf"), True, 10**400])
def test_light_contract_rejects_unusable_numeric_prices(contract, price):
    rows = copy.deepcopy(contract.fixture)
    rows[0]["price"] = price
    assert not validate_rows(contract, rows).ok
    invalid_fixture = copy.deepcopy(contract)
    invalid_fixture.fixture = rows
    assert validate_contract_file(invalid_fixture, contract.owners)
    probe = run_canary({ENDPOINT: contract}, lambda path, query: (200, rows))[ENDPOINT]
    assert probe["ok"] is False


@pytest.mark.parametrize("value", ["true", 1, None, [], {}])
def test_malformed_finite_policy_is_fatal_even_for_empty_rows(value):
    contract = copy.deepcopy(load_contracts(ROOT)["quote"])
    contract.required_fields["price"]["finite"] = value
    assert not validate_rows(contract, []).ok
    assert any("finite" in message for message in validate_contract_file(contract, contract.owners))


@pytest.mark.parametrize(
    "rows",
    [
        None,
        {},
        "private-body",
        [None],
        ["private-row"],
        [True],
        [{"date": "2026-10-26"}],
        [{"date": "2026-10-26", "close": 100}],
        [{"date": "2026-10-26", "price": "private-price"}],
        [{"date": "2026-10-26", "price": None}],
        [{"date": "2026-10-26", "price": True}],
        [{"date": "2026-10-26", "price": float("nan")}],
        [{"date": "2026-10-26", "price": float("inf")}],
        [{"date": "2026-10-26", "price": 10**400}],
        [{"date": "private-date", "price": 100}],
        [{"date": "2026-02-30", "price": 100}],
        [{"date": "20261026", "price": 100}],
        [{"date": None, "price": 100}],
    ],
)
def test_consumer_rejects_drift_without_echoing_payload(nrf, rows):
    client = client_with(nrf, rows)
    result = series(nrf, client)
    assert result["error"] == "no_price_source"
    assert result["series"] == []
    assert "schema_drift:" in result["attempts"][0]["status"]
    assert "private" not in json.dumps(result)


def test_schema_drift_preserves_successful_proxy_fallback(contract, nrf):
    client = client_with(nrf, None)
    client.session.get.side_effect = [
        SimpleNamespace(status_code=200, json=lambda: [{"date": "2026-10-26", "close": 100}]),
        SimpleNamespace(status_code=200, json=lambda: copy.deepcopy(contract.fixture)),
    ]
    result = series(nrf, client, fallback=True)
    assert result["error"] is None and result["price_symbol"] == "QQQ"
    assert "schema_drift:" in result["attempts"][0]["status"]
    assert result["attempts"][1]["status"] == "ok"


def test_empty_and_all_future_results_have_distinct_reasons(nrf):
    empty = series(nrf, client_with(nrf, []))
    future = series(nrf, client_with(nrf, [{"date": "2026-10-31", "price": 100}]))
    assert empty["error"] == future["error"] == "no_price_source"
    assert empty["attempts"][0]["status"] == "0 rows"
    assert future["attempts"][0]["status"] == "no_rows_before_as_of"


def test_mixed_as_of_rows_are_clipped(contract, nrf):
    result = series(nrf, client_with(nrf, contract.fixture), cutoff="2026-10-28")
    assert result["error"] is None
    assert [day for day, _ in result["series"]] == ["2026-10-26", "2026-10-27", "2026-10-28"]


@pytest.mark.parametrize("status", [402, 403, 429, 500])
def test_denied_http_status_is_not_accepted(contract, nrf, status):
    result = series(nrf, client_with(nrf, contract.fixture, status))
    assert result["error"] == "no_price_source"
    assert result["attempts"][0]["status"] == f"http_{status}"
    probe = run_canary({ENDPOINT: contract}, lambda path, query: (status, contract.fixture))[
        ENDPOINT
    ]
    assert probe["ok"] is False
    assert any(item["code"] == f"http_status:{status}" for item in probe["anomalies"])


@pytest.mark.parametrize("failure", [ValueError("fixture-only"), requests.Timeout("fixture-only")])
def test_invalid_json_and_transport_fail_safely(nrf, failure, capsys):
    client = client_with(nrf, [])
    if isinstance(failure, ValueError):
        client.session.get.return_value.json.side_effect = failure
    else:
        client.session.get.side_effect = failure
    result = series(nrf, client)
    assert result["error"] == "no_price_source"
    assert "fixture-only" not in json.dumps(result) + capsys.readouterr().err


@pytest.mark.parametrize("rows", [[], [{"date": "2026-10-26", "close": 100}]])
def test_canary_empty_and_schema_drift_are_fatal(contract, rows):
    result = run_canary({ENDPOINT: contract}, lambda path, query: (200, rows))[ENDPOINT]
    assert result["ok"] is False and result["anomalies"]


@pytest.mark.parametrize("types", [["str"], [], [{}], [["int"]], "int"])
def test_finite_rule_requires_numeric_type_declarations(types):
    contract = copy.deepcopy(load_contracts(ROOT)["quote"])
    contract.required_fields["price"].update(types=types, finite=True)
    result = validate_rows(contract, [])
    assert any(item.code == "invalid_contract_rule:price:finite" for item in result.fatal_anomalies)


def test_finite_policy_is_opt_in_for_existing_contracts():
    contract = copy.deepcopy(load_contracts(ROOT)["quote"])
    rows = copy.deepcopy(contract.fixture)
    rows[0]["price"] = float("inf")
    assert validate_rows(contract, rows).ok
    contract.required_fields["price"]["finite"] = True
    assert not validate_rows(contract, rows).ok


@pytest.mark.parametrize("close", [None, "private-close", float("nan"), float("inf"), 999, True])
def test_light_price_cannot_be_shadowed_by_extra_close(nrf, close):
    client = client_with(nrf, [{"date": "2026-10-26", "price": 100.0, "close": close}])
    result = series(nrf, client)
    assert result["error"] is None
    assert result["series"] == [("2026-10-26", 100.0)]


@pytest.mark.parametrize("types", [None, 3])
def test_invalid_finite_rule_does_not_crash_on_nonempty_rows(types):
    contract = copy.deepcopy(load_contracts(ROOT)["quote"])
    contract.required_fields["price"].update(types=types, finite=True)
    result = validate_rows(contract, contract.fixture)
    assert any(item.code == "invalid_contract_rule:price:finite" for item in result.fatal_anomalies)
    assert any(
        "invalid_contract_rule:price:finite" in message
        for message in validate_contract_file(contract, contract.owners)
    )
    probe = run_canary({ENDPOINT: contract}, lambda path, query: (200, contract.fixture))[ENDPOINT]
    assert probe["ok"] is False


# --- Date-format rule (iso_date) -------------------------------------------


@pytest.mark.parametrize("bad", ["10/30/2026", "20261030", "2026-02-30", "2026-10-30T00:00:00", ""])
def test_light_contract_flags_non_iso_dates_in_canary(contract, bad):
    rows = copy.deepcopy(contract.fixture)
    rows[2]["date"] = bad
    result = validate_rows(contract, rows)
    assert any(a.code == "invalid_date_format:date" for a in result.fatal_anomalies)
    probe = run_canary({ENDPOINT: contract}, lambda path, query: (200, rows))[ENDPOINT]
    assert probe["ok"] is False


@pytest.mark.parametrize("value", ["true", 1, None])
def test_malformed_iso_date_policy_is_fatal(value):
    contract = copy.deepcopy(load_contracts(ROOT)[ENDPOINT])
    contract.required_fields["date"]["iso_date"] = value
    result = validate_rows(contract, contract.fixture)
    assert any(a.code == "invalid_contract_rule:date:iso_date" for a in result.fatal_anomalies)


def test_iso_date_requires_exactly_str_type():
    contract = copy.deepcopy(load_contracts(ROOT)[ENDPOINT])
    contract.required_fields["price"]["iso_date"] = True
    result = validate_rows(contract, contract.fixture)
    assert any(a.code == "invalid_contract_rule:price:iso_date" for a in result.fatal_anomalies)


def test_iso_date_is_opt_in_for_existing_contracts():
    contract = copy.deepcopy(load_contracts(ROOT)[ENDPOINT])
    contract.required_fields["date"].pop("iso_date")
    rows = copy.deepcopy(contract.fixture)
    rows[0]["date"] = "10/30/2026"
    assert validate_rows(contract, rows).ok


# --- Mutation-resistance tests ----------------------------------------------


@pytest.mark.parametrize("position", [0, 2, 4])
@pytest.mark.parametrize("bad", [{"price": None}, {"date": "10/30/2026"}, {"price": "x"}])
def test_consumer_checks_every_row_not_just_first_or_last(nrf, contract, position, bad):
    rows = copy.deepcopy(contract.fixture)
    rows[position].update(bad)
    result = series(nrf, client_with(nrf, rows))
    assert result["error"] == "no_price_source"
    assert result["attempts"][0]["status"].startswith("schema_drift:")


def test_consumer_flags_missing_date_key(nrf, contract):
    rows = copy.deepcopy(contract.fixture)
    del rows[3]["date"]
    result = series(nrf, client_with(nrf, rows))
    assert result["attempts"][0]["status"] == "schema_drift:missing_date"


@pytest.mark.parametrize("position", [0, 2, 4])
@pytest.mark.parametrize("price", [float("nan"), float("inf"), 10**400])
def test_finite_rule_is_applied_to_every_row(contract, position, price):
    rows = copy.deepcopy(contract.fixture)
    rows[position]["price"] = price
    codes = [a.code for a in validate_rows(contract, rows).fatal_anomalies]
    assert codes == ["non_finite_required_field:price"]


@pytest.mark.parametrize("position", [0, 2, 4])
def test_close_is_stripped_from_every_row(nrf, contract, position):
    rows = copy.deepcopy(contract.fixture)
    rows[position]["close"] = 999
    result = series(nrf, client_with(nrf, rows))
    expected = sorted((row["date"], row["price"]) for row in contract.fixture)
    assert result["series"] == expected


def test_integer_prices_are_accepted(nrf, contract):
    rows = copy.deepcopy(contract.fixture)
    for row in rows:
        row["price"] = 100
    assert validate_rows(contract, rows).ok
    result = series(nrf, client_with(nrf, rows))
    assert result["error"] is None
    assert all(price == 100 for _, price in result["series"])


def test_fixture_has_exactly_the_documented_fields(contract):
    for row in contract.fixture:
        assert set(row) == {"symbol", "date", "price", "volume"}
