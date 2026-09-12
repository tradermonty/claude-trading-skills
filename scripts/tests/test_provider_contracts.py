"""Tests for the FMP provider response contracts (Issue #332).

Covers: contract file structural validation (D1), the #328 rename
regression + missing/null/wrong-type/empty anomaly detection (D2), the ten
generated ``fmp_client.py`` files exercised against the real contract
fixtures (D3), the CLI's network-free ``check`` (D5), importability with
``requests`` blocked (D6), and the injectable-fetch ``canary`` (D7).

Consumer field-contract tests for earnings-trade-analyzer / pead-screener
(plan section D item 4, "D4") are intentionally NOT here — see
``skills/earnings-trade-analyzer/scripts/tests/test_earnings_trade_analyzer.py``
and ``skills/pead-screener/scripts/tests/test_pead_screener.py`` instead.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts import check_provider_contracts  # noqa: E402
from scripts.fmp_client.registry import SKILLS  # noqa: E402
from scripts.provider_contracts import (  # noqa: E402
    ContractLoadError,
    load_contracts,
    redact_url,
    validate_contract_file,
    validate_rows,
)

CONTRACTS = load_contracts(REPO_ROOT)


def _skill_ids() -> list[str]:
    data = yaml.safe_load((REPO_ROOT / "skills-index.yaml").read_text(encoding="utf-8"))
    return [s["id"] for s in data["skills"]]


SKILL_IDS = _skill_ids()


# ---------------------------------------------------------------------------
# D1: every contract passes check; fixture has >=1 row; owners exist
# ---------------------------------------------------------------------------


def test_four_contracts_are_present():
    assert set(CONTRACTS) == {
        "profile",
        "quote",
        "historical-price-eod-full",
        "earnings-calendar",
    }


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_contract_file_is_valid(name):
    contract = CONTRACTS[name]
    errors = validate_contract_file(contract, SKILL_IDS)
    assert errors == []


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_contract_fixture_has_at_least_one_row(name):
    assert len(CONTRACTS[name].fixture) >= 1


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_contract_owners_exist_in_skills_index(name):
    contract = CONTRACTS[name]
    assert contract.owners
    for owner in contract.owners:
        assert owner in SKILL_IDS, owner


def test_check_cli_passes_on_real_contracts():
    assert check_provider_contracts.main(["check"]) == 0


# ---------------------------------------------------------------------------
# D2: rename regression + missing/null/wrong-type/empty anomaly detection
# ---------------------------------------------------------------------------


def _contracts_with_legacy_aliases():
    return [name for name, c in CONTRACTS.items() if c.legacy_aliases]


def test_only_profile_declares_legacy_aliases():
    assert _contracts_with_legacy_aliases() == ["profile"]


@pytest.mark.parametrize(
    "legacy_key,canonical",
    [
        (k, v["canonical"])
        for k, v in CONTRACTS["profile"].legacy_aliases.items()
        if v["canonical"] in CONTRACTS["profile"].required_fields
    ],
)
def test_rename_canonical_to_legacy_is_a_fatal_anomaly(legacy_key, canonical):
    contract = CONTRACTS["profile"]
    row = copy.deepcopy(contract.fixture[0])
    row[legacy_key] = row.pop(canonical)
    result = validate_rows(contract, [row])
    assert result.ok is False
    codes = [a.code for a in result.fatal_anomalies]
    assert f"canonical_absent_legacy_present:{legacy_key}->{canonical}" in codes


def test_rename_optional_field_to_its_legacy_alias_is_not_flagged():
    # lastDiv -> lastDividend: lastDividend is optional, not required, so a
    # renamed-only row (no canonical_absent_legacy_present check applies to
    # optional fields) produces no anomaly at all.
    contract = CONTRACTS["profile"]
    row = copy.deepcopy(contract.fixture[0])
    row["lastDiv"] = row.pop("lastDividend")
    result = validate_rows(contract, [row])
    assert result.ok is True


def test_legacy_alias_present_alongside_canonical_is_a_deprecation_only():
    contract = CONTRACTS["profile"]
    row = copy.deepcopy(contract.fixture[0])
    row["mktCap"] = row["marketCap"]  # both present: informational, not fatal
    result = validate_rows(contract, [row])
    assert result.ok is True
    codes = [a.code for a in result.deprecations]
    assert "legacy_alias_present:mktCap" in codes


def test_dropped_required_field_is_missing_required_field():
    contract = CONTRACTS["quote"]
    row = copy.deepcopy(contract.fixture[0])
    del row["marketCap"]
    result = validate_rows(contract, [row])
    assert result.ok is False
    assert any(a.code == "missing_required_field:marketCap" for a in result.fatal_anomalies)


def test_null_on_non_nullable_required_field_is_fatal():
    contract = CONTRACTS["historical-price-eod-full"]
    row = copy.deepcopy(contract.fixture[0])
    row["close"] = None
    result = validate_rows(contract, [row])
    assert result.ok is False
    assert any(a.code == "null_required_field:close" for a in result.fatal_anomalies)


def test_null_on_nullable_required_field_is_not_fatal():
    contract = CONTRACTS["earnings-calendar"]
    row = copy.deepcopy(contract.fixture[0])
    row["epsActual"] = None
    result = validate_rows(contract, [row])
    assert result.ok is True


def test_wrong_type_is_fatal():
    contract = CONTRACTS["quote"]
    row = copy.deepcopy(contract.fixture[0])
    row["volume"] = "not-a-number"
    result = validate_rows(contract, [row])
    assert result.ok is False
    assert any(a.code == "wrong_type:volume:str" for a in result.fatal_anomalies)


def test_empty_list_is_fatal_empty_response():
    contract = CONTRACTS["profile"]
    assert contract.non_empty.get("min_rows", 0) >= 1
    result = validate_rows(contract, [])
    assert result.ok is False
    assert any(a.code == "empty_response" for a in result.fatal_anomalies)


def test_none_response_is_fatal_empty_response():
    contract = CONTRACTS["profile"]
    result = validate_rows(contract, None)
    assert result.ok is False
    assert any(a.code == "empty_response" for a in result.fatal_anomalies)


def test_not_a_list_is_fatal():
    contract = CONTRACTS["quote"]
    result = validate_rows(contract, {"not": "a list"})
    assert result.ok is False
    assert any(a.code == "not_a_list" for a in result.fatal_anomalies)


def test_row_not_object_is_fatal():
    contract = CONTRACTS["quote"]
    result = validate_rows(contract, ["not-a-dict"])
    assert result.ok is False
    assert any(a.code == "row_not_object" for a in result.fatal_anomalies)


# ---------------------------------------------------------------------------
# D3: the ten generated fmp_client.py clients exercised on the real fixtures
# ---------------------------------------------------------------------------


def _load_client_module(rel_path: str):
    abs_path = REPO_ROOT / rel_path
    skill = abs_path.parent.parent.name.replace("-", "_")
    name = f"_provider_contracts_{skill}"
    sys.modules.pop(name, None)
    sys.modules.pop("_fmp_compat", None)
    sys.path.insert(0, str(abs_path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, str(abs_path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(abs_path.parent))


HIST_FIXTURE = CONTRACTS["historical-price-eod-full"].fixture
QUOTE_FIXTURE = CONTRACTS["quote"].fixture
PROFILE_FIXTURE = CONTRACTS["profile"].fixture
EARNINGS_FIXTURE = CONTRACTS["earnings-calendar"].fixture


def _assert_hist_row(row):
    for f in ("date", "open", "high", "low", "close", "volume"):
        assert f in row, f


CORE_TEMPLATE_SKILLS = [
    "pead-screener",
    "earnings-trade-analyzer",
    "ibd-distribution-day-monitor",
    "vcp-screener",
    "parabolic-short-trade-planner",
    "ftd-detector",
]


@pytest.mark.parametrize("skill", CORE_TEMPLATE_SKILLS)
def test_core_template_client_historical_prices_accepts_fixture(skill, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    config = SKILLS[skill]
    mod = _load_client_module(f"skills/{skill}/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: copy.deepcopy(HIST_FIXTURE))

    data = client.get_historical_prices("AAPL", days=5)
    if config.hist_return_list:
        assert isinstance(data, list)
        assert data
        _assert_hist_row(data[0])
    else:
        assert isinstance(data, dict)
        assert "historical" in data
        assert data["historical"]
        _assert_hist_row(data["historical"][0])


QUOTE_CLIENTS = ["vcp-screener", "parabolic-short-trade-planner", "ftd-detector"]


@pytest.mark.parametrize("skill", QUOTE_CLIENTS)
def test_core_template_client_quote_accepts_fixture(skill, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    assert SKILLS[skill].has_quote
    mod = _load_client_module(f"skills/{skill}/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: copy.deepcopy(QUOTE_FIXTURE))

    quotes = client.get_quote("AAPL")
    assert isinstance(quotes, list)
    assert quotes[0]["symbol"] == "AAPL"
    assert "marketCap" in quotes[0]


FAMILY_B_SKILLS = ["pead-screener", "earnings-trade-analyzer", "ibd-distribution-day-monitor"]


@pytest.mark.parametrize("skill", FAMILY_B_SKILLS)
def test_family_b_client_company_profiles_accepts_fixture(skill, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    assert SKILLS[skill].family == "B"
    mod = _load_client_module(f"skills/{skill}/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: copy.deepcopy(PROFILE_FIXTURE))

    profiles = client.get_company_profiles(["AAPL"])
    assert "AAPL" in profiles
    assert "marketCap" in profiles["AAPL"]
    assert "exchange" in profiles["AAPL"]


@pytest.mark.parametrize("skill", FAMILY_B_SKILLS)
def test_family_b_client_earnings_calendar_accepts_fixture(skill, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load_client_module(f"skills/{skill}/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    monkeypatch.setattr(
        client, "_rate_limited_get", lambda *a, **k: copy.deepcopy(EARNINGS_FIXTURE)
    )

    rows = client.get_earnings_calendar("2026-09-04", "2026-09-04")
    assert isinstance(rows, list) and rows
    for row in rows:
        for f in (
            "symbol",
            "date",
            "epsActual",
            "epsEstimated",
            "revenueActual",
            "revenueEstimated",
        ):
            assert f in row


@pytest.mark.parametrize("skill", FAMILY_B_SKILLS)
def test_family_b_client_earnings_calendar_requests_report_times(skill, monkeypatch):
    """Issue #352: the client must ask for includeReportTimes=true (a string,
    not a JSON boolean) so the provider includes the `time` (bmo/amc/null)
    field on each row."""
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load_client_module(f"skills/{skill}/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret

    captured = {}

    def fake_get(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = params
        return copy.deepcopy(EARNINGS_FIXTURE)

    monkeypatch.setattr(client, "_rate_limited_get", fake_get)

    client.get_earnings_calendar("2026-09-04", "2026-09-04")

    assert captured["params"]["includeReportTimes"] == "true"


def test_earnings_calendar_fixture_rows_carry_time_field():
    """Issue #352: the recorded fixture must reflect includeReportTimes=true
    responses (time present as bmo/amc/None), not the pre-#352 shape."""
    for row in EARNINGS_FIXTURE:
        assert "time" in row


def test_earnings_calendar_fixture_covers_bmo_amc_and_null_timing():
    times = {row.get("time") for row in EARNINGS_FIXTURE}
    assert {"bmo", "amc", None} <= times


def test_earnings_calendar_missing_time_field_is_a_fatal_regression():
    """A response missing `time` entirely (e.g. includeReportTimes dropped
    again) must be caught as missing_required_field, not silently accepted."""
    contract = CONTRACTS["earnings-calendar"]
    row = copy.deepcopy(contract.fixture[0])
    del row["time"]
    result = validate_rows(contract, [row])
    assert result.ok is False
    assert any(a.code == "missing_required_field:time" for a in result.fatal_anomalies)


def test_earnings_calendar_query_values_are_all_strings():
    """check_provider_contracts.py sends `dict(contract.query)` straight into
    requests' `params=`; a JSON boolean for includeReportTimes would be sent
    as Python `True`, which the API rejects with HTTP 400 (only the strings
    "true"/"false" are accepted)."""
    contract = CONTRACTS["earnings-calendar"]
    for key, value in contract.query.items():
        assert isinstance(value, str), f"{key}={value!r} is not a str"


# --- specials: canslim, macro, market-top, us-undervalued-growth-screener ---


def test_canslim_special_historical_and_quote_and_profile_accept_fixture(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load_client_module("skills/canslim-screener/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret

    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: copy.deepcopy(HIST_FIXTURE))
    hist = client.get_historical_prices("AAPL", days=5)
    assert isinstance(hist, dict) and "historical" in hist
    _assert_hist_row(hist["historical"][0])

    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: copy.deepcopy(QUOTE_FIXTURE))
    quote = client.get_quote("AAPL")
    assert isinstance(quote, list) and quote[0]["symbol"] == "AAPL"

    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: copy.deepcopy(PROFILE_FIXTURE))
    profile = client.get_profile("AAPL")
    assert isinstance(profile, list)
    # canslim keeps the documented mktCap alias shim for its own screener code.
    assert profile[0]["mktCap"] == profile[0]["marketCap"]


def test_macro_special_historical_accepts_fixture(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load_client_module("skills/macro-regime-detector/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: copy.deepcopy(HIST_FIXTURE))

    data = client.get_historical_prices("AAPL", days=5)
    assert mod._has_usable_history(data)
    _assert_hist_row(data["historical"][0])


def test_market_top_special_historical_and_quote_accept_fixture(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load_client_module("skills/market-top-detector/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret

    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: copy.deepcopy(HIST_FIXTURE))
    hist = client.get_historical_prices("AAPL", days=5)
    assert mod._has_usable_history(hist)
    _assert_hist_row(hist["historical"][0])

    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: copy.deepcopy(QUOTE_FIXTURE))
    quote = client.get_quote("AAPL")
    assert isinstance(quote, list) and quote[0]["symbol"] == "AAPL"


def test_us_undervalued_growth_screener_historical_profile_quotes_accept_fixture(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load_client_module("skills/us-undervalued-growth-screener/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret

    def fake_request_json(url, params=None, **kwargs):
        if "historical-price-eod" in url:
            return copy.deepcopy(HIST_FIXTURE)
        if "profile" in url:
            return copy.deepcopy(PROFILE_FIXTURE)
        if "quote" in url:
            return copy.deepcopy(QUOTE_FIXTURE)
        return None

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    hist = client.get_historical_prices("AAPL", from_date="2026-08-31", to_date="2026-09-04")
    assert isinstance(hist, list) and hist
    _assert_hist_row(hist[0])

    profile = client.get_profile("AAPL")
    assert isinstance(profile, dict)
    assert "marketCap" in profile

    quotes = client.get_quotes(["AAPL"])
    assert "AAPL" in quotes
    assert "marketCap" in quotes["AAPL"]


# ---------------------------------------------------------------------------
# D5: `check` is network-free
# ---------------------------------------------------------------------------


def test_check_is_network_free(monkeypatch):
    import socket

    def _forbidden(*args, **kwargs):
        raise AssertionError("network access attempted during `check`")

    monkeypatch.setattr(socket, "socket", _forbidden)
    assert check_provider_contracts.main(["check"]) == 0


# ---------------------------------------------------------------------------
# D6: the CLI module imports with `requests` blocked
# ---------------------------------------------------------------------------


def test_module_imports_with_requests_blocked():
    script = (
        "import sys\n"
        "sys.modules['requests'] = None\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "import scripts.check_provider_contracts as m\n"
        "import scripts.provider_contracts as p\n"
        "print('IMPORT_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout


# ---------------------------------------------------------------------------
# D7: canary with an injectable stub fetch
# ---------------------------------------------------------------------------


def _stub_fetch_ok(path, query):
    if "profile" in path:
        return 200, copy.deepcopy(PROFILE_FIXTURE)
    if "quote" in path:
        return 200, copy.deepcopy(QUOTE_FIXTURE)
    if "historical-price-eod" in path:
        return 200, copy.deepcopy(HIST_FIXTURE)
    if "earnings-calendar" in path:
        return 200, copy.deepcopy(EARNINGS_FIXTURE)
    return 404, None


def test_canary_success_writes_report_and_never_leaks_the_key(tmp_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "FAKEKEY123")
    monkeypatch.setattr(
        check_provider_contracts, "_build_requests_fetch", lambda api_key: _stub_fetch_ok
    )

    report_path = tmp_path / "canary_ok.json"
    exit_code = check_provider_contracts.main(["canary", "--report", str(report_path)])

    assert exit_code == 0
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert set(report["contracts"]) == {
        "profile",
        "quote",
        "historical-price-eod-full",
        "earnings-calendar",
    }
    for entry in report["contracts"].values():
        assert entry["ok"] is True
    assert report["ok"] is True
    assert report["budget"] == {"max": len(CONTRACTS), "used": len(CONTRACTS)}
    assert "FAKEKEY123" not in report_path.read_text(encoding="utf-8")


def test_canary_detects_anomalies_and_exits_1(tmp_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "FAKEKEY123")

    def stub_fetch_broken_profile(path, query):
        if "profile" in path:
            bad = copy.deepcopy(PROFILE_FIXTURE[0])
            bad["mktCap"] = bad.pop("marketCap")
            return 200, [bad]
        return _stub_fetch_ok(path, query)

    monkeypatch.setattr(
        check_provider_contracts, "_build_requests_fetch", lambda api_key: stub_fetch_broken_profile
    )

    report_path = tmp_path / "canary_bad.json"
    exit_code = check_provider_contracts.main(["canary", "--report", str(report_path)])

    assert exit_code == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["contracts"]["profile"]["ok"] is False
    codes = [a["code"] for a in report["contracts"]["profile"]["anomalies"]]
    assert any(c.startswith("canonical_absent_legacy_present:mktCap->marketCap") for c in codes)
    assert report["ok"] is False
    assert report["budget"] == {"max": len(CONTRACTS), "used": len(CONTRACTS)}
    assert "FAKEKEY123" not in report_path.read_text(encoding="utf-8")


def test_canary_max_calls_budget_refuses_to_start(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("FMP_API_KEY", "FAKEKEY123")
    monkeypatch.setattr(
        check_provider_contracts, "_build_requests_fetch", lambda api_key: _stub_fetch_ok
    )

    report_path = tmp_path / "should_not_exist.json"
    exit_code = check_provider_contracts.main(
        ["canary", "--max-calls", "2", "--report", str(report_path)]
    )

    assert exit_code == 1
    assert not report_path.exists()
    captured = capsys.readouterr()
    assert "refusing to start" in captured.err
    assert "FAKEKEY123" not in captured.err
    assert "FAKEKEY123" not in captured.out


def test_redact_url_strips_apikey():
    url = "https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey=SECRET123"
    redacted = redact_url(url)
    assert "SECRET123" not in redacted
    assert "apikey=REDACTED" in redacted


def test_canary_default_max_calls_is_number_of_loaded_contracts(tmp_path, monkeypatch):
    # No --max-calls given: the budget defaults to len(contracts), so probing
    # exactly the real four contracts must NOT refuse to start.
    monkeypatch.setenv("FMP_API_KEY", "FAKEKEY123")
    monkeypatch.setattr(
        check_provider_contracts, "_build_requests_fetch", lambda api_key: _stub_fetch_ok
    )
    report_path = tmp_path / "default_budget.json"
    exit_code = check_provider_contracts.main(["canary", "--report", str(report_path)])
    assert exit_code == 0
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["budget"] == {"max": len(CONTRACTS), "used": len(CONTRACTS)}


def test_build_requests_fetch_redacts_apikey_from_exception_message(monkeypatch):
    import requests

    def fake_get(url, params=None, timeout=None):
        raise requests.exceptions.ConnectionError(
            f"Failed to establish a new connection: {url}?apikey=FAKEKEY123 unreachable"
        )

    monkeypatch.setattr(requests, "get", fake_get)
    fetch = check_provider_contracts._build_requests_fetch("FAKEKEY123")

    status, payload = fetch("/stable/profile", {"symbol": "AAPL"})

    assert status == -1
    assert "FAKEKEY123" not in payload["error"]
    assert "apikey=REDACTED" in payload["error"]


# ---------------------------------------------------------------------------
# D7 cont'd / item 7: malformed JSON and duplicate-endpoint contract loading
# ---------------------------------------------------------------------------

_MINIMAL_CONTRACT_PAYLOAD = {
    "schema_version": 1,
    "provider": "fmp",
    "endpoint": "profile",
    "path": "/stable/profile",
    "query": {"symbol": "AAPL"},
    "contract_version": 1,
    "recorded_on": "2026-09-05",
    "recording": "test fixture",
    "owners": ["pead-screener"],
    "tier_notes": "",
    "required_fields": {},
    "optional_fields": [],
    "legacy_aliases": {},
    "known_gaps": [],
    "non_empty": {"min_rows": 0},
    "fixture": [],
}


def test_load_contracts_raises_on_malformed_json(tmp_path):
    provider_dir = tmp_path / "config" / "provider-contracts" / "fmp"
    provider_dir.mkdir(parents=True)
    (provider_dir / "broken.v1.json").write_text("{not valid json", encoding="utf-8")

    with pytest.raises(ContractLoadError, match="malformed JSON"):
        load_contracts(tmp_path)


def test_load_contracts_raises_on_duplicate_endpoint(tmp_path):
    provider_dir = tmp_path / "config" / "provider-contracts" / "fmp"
    provider_dir.mkdir(parents=True)
    (provider_dir / "profile.v1.json").write_text(
        json.dumps(_MINIMAL_CONTRACT_PAYLOAD), encoding="utf-8"
    )
    (provider_dir / "profile.v2.json").write_text(
        json.dumps(_MINIMAL_CONTRACT_PAYLOAD), encoding="utf-8"
    )

    with pytest.raises(ContractLoadError, match="duplicate endpoint 'profile'"):
        load_contracts(tmp_path)


def test_check_cli_reports_malformed_contract_cleanly_instead_of_a_traceback(
    tmp_path, monkeypatch, capsys
):
    provider_dir = tmp_path / "config" / "provider-contracts" / "fmp"
    provider_dir.mkdir(parents=True)
    (provider_dir / "broken.v1.json").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(check_provider_contracts, "_REPO_ROOT", tmp_path)

    exit_code = check_provider_contracts.main(["check"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "malformed JSON" in captured.err
