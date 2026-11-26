"""CoinGecko universe capture, bounded canary and policy regressions (#332)."""

import copy
import json
from pathlib import Path

import pytest
import requests
import yaml

from scripts import check_provider_contracts as cli
from scripts.provider_contracts import load_contracts, validate_contract_file, validate_rows

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = load_contracts(ROOT)["coins-markets"]


@pytest.mark.parametrize("field", ["id", "symbol"])
@pytest.mark.parametrize("value", [None, 1, True, "", "  ", [], {}])
def test_consumed_identifier_drift_is_fatal(field, value):
    rows = copy.deepcopy(CONTRACT.fixture)
    rows[0][field] = value
    assert not validate_rows(CONTRACT, rows).ok


@pytest.mark.parametrize("field", ["id", "symbol"])
def test_consumed_field_rename_is_fatal(field):
    rows = copy.deepcopy(CONTRACT.fixture)
    rows[0][field + "_renamed"] = rows[0].pop(field)
    assert not validate_rows(CONTRACT, rows).ok


@pytest.mark.parametrize("rule", [None, 1, "true"])
def test_invalid_nonblank_policy_fails_closed(rule):
    c = copy.deepcopy(CONTRACT)
    c.required_fields["id"]["non_blank"] = rule
    assert not validate_rows(c, c.fixture).ok
    assert validate_contract_file(c, ["crypto-regime-analyzer"])


def test_nonblank_is_opt_in_and_requires_string_policy():
    c = copy.deepcopy(CONTRACT)
    c.required_fields["id"]["non_blank"] = False
    rows = copy.deepcopy(c.fixture)
    rows[0]["id"] = ""
    assert validate_rows(c, rows).ok
    c.required_fields["id"].update(types=["int"], non_blank=True)
    assert not validate_rows(c, [{"id": 1, "symbol": "btc"}]).ok


class Response:
    def __init__(self, body, status=200):
        self.body, self.status_code, self.closed = body, status, False

    def iter_content(self, chunk_size):
        yield self.body

    def close(self):
        self.closed = True


@pytest.mark.parametrize(
    "status,body,code",
    [
        (200, b"bad json", "parse_error"),
        (200, b"\xff", "parse_error"),
        (200, b"x" * (2 * 1024 * 1024 + 1), "body_too_large"),
        (302, b"private", "http_status:302"),
        (429, b"private", "http_status:429"),
        (403, b"private", "http_status:403"),
    ],
)
def test_failed_probe_is_bounded_closed_and_contains_no_body(monkeypatch, status, body, code):
    response = Response(body, status)
    calls = []

    def get(url, **kw):
        calls.append((url, kw))
        return response

    monkeypatch.setattr(requests, "get", get)
    result = cli.run_canary(
        {CONTRACT.endpoint: CONTRACT}, {"coingecko": cli._build_coingecko_fetch()}
    )[CONTRACT.endpoint]
    assert not result["ok"] and code in {a["code"] for a in result["anomalies"]}
    assert response.closed and len(calls) == 1
    assert calls[0][0] == "https://api.coingecko.com/api/v3/coins/markets"
    assert calls[0][1]["timeout"] == 30
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["stream"] is True
    assert "private" not in json.dumps(result)


def test_transport_exception_is_not_logged_or_retried(monkeypatch, capsys):
    calls = []

    def get(*a, **kw):
        calls.append(1)
        raise requests.RequestException("sensitive provider details")

    monkeypatch.setattr(requests, "get", get)
    result = cli._build_coingecko_fetch()(CONTRACT)
    assert result.status == -1 and result.extra_anomalies[0].code == "transport_error"
    assert len(calls) == 1
    captured = capsys.readouterr()
    assert "sensitive" not in captured.out + captured.err


def test_unreviewed_path_or_query_cannot_send_request(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("network"))
    cases = [
        ("endpoint_path", "//other.invalid"),
        ("query", {"apikey": "secret"}),  # pragma: allowlist secret -- invalid-query fixture
    ]
    for field, value in cases:
        c = copy.deepcopy(CONTRACT)
        setattr(c, field, value)
        assert validate_contract_file(c, ["crypto-regime-analyzer"])
        assert cli._build_coingecko_fetch()(c).status == -1


def test_keyless_cli_uses_one_call_and_refuses_insufficient_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "load_contracts", lambda root: {CONTRACT.endpoint: CONTRACT})
    calls = []
    response = Response(json.dumps(CONTRACT.fixture).encode())
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    def get(*a, **kw):
        calls.append(1)
        return response

    monkeypatch.setattr(requests, "get", get)
    path = tmp_path / "report.json"
    args = ["canary", "--provider", "coingecko", "--report", str(path)]
    assert cli.main(args + ["--max-calls", "0"]) == 1
    assert calls == [] and not path.exists()
    assert cli.main(args + ["--max-calls", "1"]) == 0
    assert len(calls) == 1 and response.closed
    report = json.loads(path.read_text())
    assert report["budget"] == {"max": 1, "used": 1}
    assert report["provider"] == "coingecko" and report["ok"]
    assert cli.health_errors(report, {CONTRACT.endpoint}, "coingecko", "success", 0) == []
    assert "Public CSV" not in cli.render_summary(report)


def test_workflow_keeps_health_mandatory_and_credentials_absent():
    path = ROOT / ".github/workflows/coingecko-contract-canary.yml"
    body = path.read_text()
    workflow = yaml.safe_load(body)
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["canary"]
    assert job["timeout-minutes"] == 5 and not job.get("continue-on-error")
    probe = next(s for s in job["steps"] if s.get("id") == "probe")
    assert probe["continue-on-error"] and "--max-calls 3" in probe["run"]
    assert "rm -f reports/coingecko-canary-report.json" in probe["run"]
    health = next(s for s in job["steps"] if " health " in s.get("run", ""))
    assert health["if"] == "always()" and not health.get("continue-on-error")
    assert "secrets." not in body and "--provider coingecko" in health["run"]
