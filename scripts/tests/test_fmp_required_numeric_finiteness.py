"""Recorded FMP required numeric data must be finite before canary success."""

import copy
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
import requests

from scripts import check_provider_contracts as cli
from scripts.notify_provider_drift import parse_report
from scripts.provider_contracts import load_contracts, validate_contract_file, validate_rows

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = {name: c for name, c in load_contracts(ROOT).items() if c.provider == "fmp"}
NUMERIC_FIELDS = [
    (name, field)
    for name, contract in CONTRACTS.items()
    for field, rule in contract.required_fields.items()
    if rule["types"] and set(rule["types"]) <= {"int", "float"}
]
FIELD_IDS = [f"{name}.{field}" for name, field in NUMERIC_FIELDS]


@pytest.mark.parametrize("name,field", NUMERIC_FIELDS, ids=FIELD_IDS)
def test_every_required_fmp_numeric_field_declares_finite_policy(name, field):
    assert CONTRACTS[name].required_fields[field].get("finite") is True


BAD_VALUES = [
    ("huge_int", 10**400),
    ("nan", float("nan")),
    ("inf", float("inf")),
    ("neg_inf", -float("inf")),
]
BAD_CASES = [
    pytest.param(name, field, value, id=f"{name}.{field}-{label}")
    for name, field in NUMERIC_FIELDS
    for label, value in BAD_VALUES
    if label == "huge_int" or "float" in CONTRACTS[name].required_fields[field]["types"]
]


@pytest.mark.parametrize("name,field,value", BAD_CASES)
def test_nonfinite_required_values_fail_rows_fixture_and_canary(name, field, value):
    contract = CONTRACTS[name]
    # Put the invalid observation between valid observations, not just first/last.
    rows = [copy.deepcopy(contract.fixture[0]) for _ in range(3)]
    rows[1][field] = value
    expected = f"non_finite_required_field:{field}"
    result = validate_rows(contract, rows)
    assert not result.ok
    assert [a.code for a in result.fatal_anomalies] == [expected]
    invalid_fixture = copy.deepcopy(contract)
    invalid_fixture.fixture = rows
    assert any(
        expected in error for error in validate_contract_file(invalid_fixture, contract.owners)
    )
    probe = cli.run_canary({name: contract}, lambda path, query: (200, rows))[name]
    assert probe["ok"] is False
    assert probe["anomalies"] == [{"code": expected, "severity": "fatal", "count": 1}]
    json.dumps(probe, allow_nan=False)


@pytest.mark.parametrize("name,field", NUMERIC_FIELDS, ids=FIELD_IDS)
@pytest.mark.parametrize("value", [0, -1, 1, 10**30])
def test_finite_numeric_values_remain_valid_without_new_range_rules(name, field, value):
    contract = CONTRACTS[name]
    rows = copy.deepcopy(contract.fixture)
    rows[0][field] = value
    assert validate_rows(contract, rows).ok


@pytest.mark.parametrize("name,field", NUMERIC_FIELDS, ids=FIELD_IDS)
@pytest.mark.parametrize("value", [True, "1"])
def test_finite_policy_does_not_coerce_bool_or_numeric_strings(name, field, value):
    contract = CONTRACTS[name]
    rows = copy.deepcopy(contract.fixture)
    rows[0][field] = value
    result = validate_rows(contract, rows)
    assert not result.ok
    assert any(a.code.startswith(f"wrong_type:{field}:") for a in result.fatal_anomalies)


NULLABLE_FIELDS = [
    (n, f) for n, f in NUMERIC_FIELDS if CONTRACTS[n].required_fields[f].get("nullable")
]


@pytest.mark.parametrize("name,field", NULLABLE_FIELDS)
def test_individual_nulls_still_follow_declared_nullability(name, field):
    contract = CONTRACTS[name]
    rows = copy.deepcopy(contract.fixture)
    # Keep a populated row so reject_all_null remains independently meaningful.
    populated = next(row for row in rows if row[field] is not None)
    rows.append(copy.deepcopy(populated))
    rows[0][field] = None
    assert validate_rows(contract, rows).ok


@pytest.mark.parametrize("overflow", [False, True], ids=["healthy", "json-overflow"])
def test_actual_cli_fetch_decode_and_complete_report(monkeypatch, tmp_path, capsys, overflow):
    key = "finite-test-key"
    body_marker = "PRIVATE-PAYLOAD-MARKER"
    monkeypatch.setenv("FMP_API_KEY", key)
    by_path = {c.endpoint_path: c for c in CONTRACTS.values()}
    calls = []

    def get(url, *, params, timeout):
        assert timeout == 30
        contract = by_path[urlparse(url).path]
        assert params == {**contract.query, "apikey": key}
        calls.append(contract.endpoint)
        rows = copy.deepcopy(contract.fixture)
        if overflow and contract.endpoint == "quote":
            rows = [copy.deepcopy(rows[0]) for _ in range(3)]
            rows[1]["price"] = "OVERFLOW-TOKEN"
            rows[1]["name"] = body_marker
        # Response.json() genuinely decodes the standard JSON numeric token 1e400.
        body = json.dumps(rows, allow_nan=False).replace('"OVERFLOW-TOKEN"', "1e400")
        response = requests.Response()
        response.status_code = 200
        response.encoding = "utf-8"
        response._content = body.encode("utf-8")
        response.headers["Content-Type"] = "application/json"
        return response

    monkeypatch.setattr(requests, "get", get)
    report_path = tmp_path / "canary.json"
    code = cli.main(
        [
            "canary",
            "--provider",
            "fmp",
            "--max-calls",
            str(len(CONTRACTS)),
            "--report",
            str(report_path),
        ]
    )
    assert code == int(overflow)
    text = report_path.read_text()
    report = json.loads(text)
    assert report["ok"] is (not overflow)
    assert set(report["contracts"]) == set(CONTRACTS)
    assert calls == sorted(CONTRACTS)
    assert report["budget"] == {"max": len(CONTRACTS), "used": len(CONTRACTS)}
    assert report["contracts"]["sp500-constituent"]["ok"] is True
    if overflow:
        assert calls.index("quote") < calls.index("sp500-constituent")
        assert report["contracts"]["quote"]["anomalies"] == [
            {"code": "non_finite_required_field:price", "severity": "fatal", "count": 1}
        ]
    json.dumps(report, allow_nan=False)
    parse_report(report)  # Actual notifier accepts the complete report without any write.
    output = capsys.readouterr()
    for private in (key, body_marker, "OVERFLOW-TOKEN"):
        assert private not in text + output.out + output.err
