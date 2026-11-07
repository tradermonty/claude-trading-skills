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
FMP_CONTRACTS = {k: v for k, v in CONTRACTS.items() if v.provider == "fmp"}
TRADER_MONTY_CONTRACTS = {k: v for k, v in CONTRACTS.items() if v.provider == "trader-monty"}


def _skill_ids() -> list[str]:
    data = yaml.safe_load((REPO_ROOT / "skills-index.yaml").read_text(encoding="utf-8"))
    return [s["id"] for s in data["skills"]]


SKILL_IDS = _skill_ids()


# ---------------------------------------------------------------------------
# D1: every contract passes check; fixture has >=1 row; owners exist
# ---------------------------------------------------------------------------


def test_expected_contracts_are_present():
    assert set(FMP_CONTRACTS) == {
        "company-screener",
        "sp500-constituent",
        "profile",
        "quote",
        "historical-price-eod-full",
        "historical-price-eod-dividend-adjusted",
        "historical-price-eod-light",
        "earnings-calendar",
        "economic-calendar",
        "income-statement",
        "ratios",
    }
    assert set(TRADER_MONTY_CONTRACTS) == {
        "market-breadth-data",
        "market-breadth-summary",
        "uptrend-ratio-timeseries",
        "uptrend-sector-summary",
    }
    assert set(CONTRACTS) == set(FMP_CONTRACTS) | set(TRADER_MONTY_CONTRACTS)


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


def test_expected_legacy_alias_holders():
    assert sorted(_contracts_with_legacy_aliases()) == [
        "company-screener",
        "market-breadth-data",
        "profile",
    ]


@pytest.mark.parametrize(
    "contract_name,legacy_key,canonical",
    [
        (name, k, v["canonical"])
        for name in _contracts_with_legacy_aliases()
        for k, v in CONTRACTS[name].legacy_aliases.items()
        if v["canonical"] in CONTRACTS[name].required_fields
    ],
)
def test_rename_canonical_to_legacy_is_a_fatal_anomaly(contract_name, legacy_key, canonical):
    contract = CONTRACTS[contract_name]
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
# D2b: income-statement + ratios (Issue #332 slice) drift on the real fixtures
# ---------------------------------------------------------------------------


def test_income_statement_required_fields_are_present_in_fixture():
    contract = CONTRACTS["income-statement"]
    assert contract.non_empty.get("min_rows", 0) >= 1
    for field in ("symbol", "date", "revenue"):
        assert field in contract.required_fields
        assert contract.required_fields[field]["nullable"] is False
    result = validate_rows(contract, contract.fixture)
    assert result.ok is True


def test_income_statement_dropped_field_is_missing_required_field():
    contract = CONTRACTS["income-statement"]
    row = copy.deepcopy(contract.fixture[0])
    del row["revenue"]
    result = validate_rows(contract, [row])
    assert result.ok is False
    assert any(a.code == "missing_required_field:revenue" for a in result.fatal_anomalies)


def test_ratios_required_fields_are_present_in_fixture():
    contract = CONTRACTS["ratios"]
    assert contract.non_empty.get("min_rows", 0) >= 1
    for field in ("symbol", "date", "priceToEarningsRatio", "priceToBookRatio"):
        assert field in contract.required_fields
    assert contract.required_fields["priceToEarningsRatio"].get("reject_all_null") is True
    assert contract.required_fields["priceToBookRatio"].get("reject_all_null") is True
    result = validate_rows(contract, contract.fixture)
    assert result.ok is True


def test_ratios_null_pe_pb_rows_are_all_null_required_field():
    contract = CONTRACTS["ratios"]
    rows = copy.deepcopy(contract.fixture)
    for row in rows:
        row["priceToEarningsRatio"] = None
        row["priceToBookRatio"] = None
    result = validate_rows(contract, rows)
    assert result.ok is False
    assert any(
        a.code == "all_null_required_field:priceToEarningsRatio" for a in result.fatal_anomalies
    )


def test_ratios_wrong_type_is_fatal():
    contract = CONTRACTS["ratios"]
    row = copy.deepcopy(contract.fixture[0])
    row["priceToEarningsRatio"] = "not-a-number"
    result = validate_rows(contract, [row])
    assert result.ok is False
    assert any(a.code.startswith("wrong_type:priceToEarningsRatio") for a in result.fatal_anomalies)


def test_ratios_empty_list_is_fatal_empty_response():
    contract = CONTRACTS["ratios"]
    assert contract.non_empty.get("min_rows", 0) >= 1
    result = validate_rows(contract, [])
    assert result.ok is False
    assert any(a.code == "empty_response" for a in result.fatal_anomalies)


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
HIST_ADJUSTED_FIXTURE = CONTRACTS["historical-price-eod-dividend-adjusted"].fixture
QUOTE_FIXTURE = CONTRACTS["quote"].fixture
PROFILE_FIXTURE = CONTRACTS["profile"].fixture
EARNINGS_FIXTURE = CONTRACTS["earnings-calendar"].fixture
SCREENER_FIXTURE = CONTRACTS["company-screener"].fixture
SP500_FIXTURE = CONTRACTS["sp500-constituent"].fixture
INCOME_FIXTURE = CONTRACTS["income-statement"].fixture
RATIOS_FIXTURE = CONTRACTS["ratios"].fixture
ECONOMIC_FIXTURE = CONTRACTS["economic-calendar"].fixture


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


def test_contract_query_values_are_all_strings():
    """check_provider_contracts.py sends `dict(contract.query)` straight into
    requests' `params=`; a JSON boolean for includeReportTimes would be sent
    as Python `True`, which the API rejects with HTTP 400 (only the strings
    "true"/"false" are accepted). The same guard applies to every contract:
    the canary runs offline-statically recorded string queries, never int/
    bool fast paths."""
    for name in sorted(CONTRACTS):
        contract = CONTRACTS[name]
        for key, value in contract.query.items():
            assert isinstance(value, str), f"{name}: {key}={value!r} is not a str"


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


def test_us_undervalued_growth_screener_company_screener_accepts_fixture(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load_client_module("skills/us-undervalued-growth-screener/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    captured: dict = {}

    def fake_request_json(url, params=None, **kwargs):
        captured["url"] = url
        captured["params"] = dict(params or {})
        if "company-screener" in url:
            return copy.deepcopy(SCREENER_FIXTURE)
        return None

    monkeypatch.setattr(client, "_request_json", fake_request_json)

    universe = client.get_company_screener(
        exchange="NASDAQ",
        min_market_cap=200_000_000_000,
        max_market_cap=6_000_000_000_000,
        min_price=1.0,
        limit=10,
    )

    # The client routes the screener to /stable. Only the generated garp
    # client pins the isEtf/isFund/isActivelyTrading filters server-side;
    # the ad-hoc consumers filter on response-row fields client-side.
    assert "company-screener" in captured["url"]
    assert captured["params"]["exchange"] == "NASDAQ"
    assert captured["params"]["marketCapMoreThan"] == 200_000_000_000
    assert captured["params"]["marketCapLowerThan"] == 6_000_000_000_000
    assert captured["params"]["isEtf"] == "false"
    assert captured["params"]["isFund"] == "false"
    assert captured["params"]["isActivelyTrading"] == "true"

    assert isinstance(universe, list) and len(universe) == len(SCREENER_FIXTURE)
    assert all(isinstance(row, dict) for row in universe)
    for row in universe:
        assert row["symbol"]
        assert "marketCap" in row


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
    if path == "/stable/historical-price-eod/light":
        return 200, copy.deepcopy(CONTRACTS["historical-price-eod-light"].fixture)
    if path == "/stable/sp500-constituent":
        return 200, copy.deepcopy(SP500_FIXTURE)
    if "company-screener" in path:
        return 200, copy.deepcopy(SCREENER_FIXTURE)
    if "profile" in path:
        return 200, copy.deepcopy(PROFILE_FIXTURE)
    if "quote" in path:
        return 200, copy.deepcopy(QUOTE_FIXTURE)
    if path.endswith("/dividend-adjusted"):
        return 200, copy.deepcopy(HIST_ADJUSTED_FIXTURE)
    if "historical-price-eod" in path:
        return 200, copy.deepcopy(HIST_FIXTURE)
    if "earnings-calendar" in path:
        return 200, copy.deepcopy(EARNINGS_FIXTURE)
    if path == "/stable/economic-calendar":
        return 200, copy.deepcopy(ECONOMIC_FIXTURE)
    if "income-statement" in path:
        return 200, copy.deepcopy(INCOME_FIXTURE)
    if "ratios" in path:
        return 200, copy.deepcopy(RATIOS_FIXTURE)
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
        "company-screener",
        "sp500-constituent",
        "profile",
        "quote",
        "historical-price-eod-full",
        "historical-price-eod-dividend-adjusted",
        "historical-price-eod-light",
        "earnings-calendar",
        "economic-calendar",
        "income-statement",
        "ratios",
    }
    for entry in report["contracts"].values():
        assert entry["ok"] is True
    assert report["ok"] is True
    assert report["budget"] == {"max": len(FMP_CONTRACTS), "used": len(FMP_CONTRACTS)}
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
    assert report["budget"] == {"max": len(FMP_CONTRACTS), "used": len(FMP_CONTRACTS)}
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
    # exactly the loaded contracts must NOT refuse to start.
    monkeypatch.setenv("FMP_API_KEY", "FAKEKEY123")
    monkeypatch.setattr(
        check_provider_contracts, "_build_requests_fetch", lambda api_key: _stub_fetch_ok
    )
    report_path = tmp_path / "default_budget.json"
    exit_code = check_provider_contracts.main(["canary", "--report", str(report_path)])
    assert exit_code == 0
    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["budget"] == {"max": len(FMP_CONTRACTS), "used": len(FMP_CONTRACTS)}


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


@pytest.mark.parametrize("row_count", [1, 3])
def test_profile_all_null_market_cap_is_fatal(row_count):
    contract = CONTRACTS["profile"]
    row = copy.deepcopy(contract.fixture[0])
    row["marketCap"] = None
    result = validate_rows(contract, [copy.deepcopy(row) for _ in range(row_count)])
    assert [a.code for a in result.fatal_anomalies] == ["all_null_required_field:marketCap"]
    assert not result.ok


@pytest.mark.parametrize("value", [0, 1, 123.5])
def test_profile_mixed_null_and_populated_market_cap_is_allowed(value):
    contract = CONTRACTS["profile"]
    rows = [copy.deepcopy(contract.fixture[0]) for _ in range(2)]
    rows[0]["marketCap"] = None
    rows[1]["marketCap"] = value
    assert validate_rows(contract, rows).ok


@pytest.mark.parametrize("policy", [False, "absent"])
def test_all_null_rejection_is_opt_in(policy):
    contract = copy.deepcopy(CONTRACTS["profile"])
    if policy == "absent":
        contract.required_fields["marketCap"].pop("reject_all_null")
    else:
        contract.required_fields["marketCap"]["reject_all_null"] = policy
    contract.fixture[0]["marketCap"] = None
    assert validate_rows(contract, contract.fixture).ok


def test_all_null_unreported_earnings_values_remain_allowed():
    contract = CONTRACTS["earnings-calendar"]
    rows = copy.deepcopy(contract.fixture)
    for row in rows:
        for name, spec in contract.required_fields.items():
            if spec.get("nullable", False):
                row[name] = None
    assert validate_rows(contract, rows).ok


@pytest.mark.parametrize(
    "bad_row,expected",
    [
        ({}, "missing_required_field:marketCap"),
        (None, "row_not_object"),
        ({"marketCap": "null"}, "wrong_type:marketCap:str"),
    ],
)
def test_all_null_rule_does_not_hide_other_response_defects(bad_row, expected):
    contract = CONTRACTS["profile"]
    row = copy.deepcopy(contract.fixture[0])
    row["marketCap"] = None
    result = validate_rows(contract, [row, bad_row])
    codes = [a.code for a in result.fatal_anomalies]
    assert expected in codes
    assert "all_null_required_field:marketCap" not in codes
    assert not result.ok


@pytest.mark.parametrize("value", [None, 0, 1, "true", "false", [], {}])
@pytest.mark.parametrize("rows", [[], None, {}, "fixture"])
def test_invalid_all_null_policy_fails_even_on_empty_response(value, rows):
    contract = copy.deepcopy(CONTRACTS["profile"])
    contract.required_fields["marketCap"]["reject_all_null"] = value
    contract.non_empty["min_rows"] = 0
    payload = contract.fixture if rows == "fixture" else rows
    result = validate_rows(contract, payload)
    assert not result.ok
    assert "invalid_contract_rule:marketCap:reject_all_null" in [
        a.code for a in result.fatal_anomalies
    ]
    assert any(
        "invalid_contract_rule:marketCap:reject_all_null" in error
        for error in validate_contract_file(contract, SKILL_IDS)
    )


def test_empty_response_retains_its_original_anomaly():
    result = validate_rows(CONTRACTS["profile"], [])
    assert [a.code for a in result.fatal_anomalies] == ["empty_response"]


def test_offline_check_rejects_all_null_fixture(monkeypatch, capsys):
    contracts = copy.deepcopy(CONTRACTS)
    contracts["profile"].fixture[0]["marketCap"] = None
    monkeypatch.setattr(check_provider_contracts, "load_contracts", lambda root: contracts)
    assert check_provider_contracts.main(["check"]) == 1
    assert "all_null_required_field:marketCap" in capsys.readouterr().err


def test_canary_all_null_profile_reports_fatal_and_exits_one(tmp_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "FAKEKEY123")

    def fetch(path, query):
        status, rows = _stub_fetch_ok(path, query)
        if path == "/stable/profile":
            for row in rows:
                row["marketCap"] = None
        return status, rows

    monkeypatch.setattr(check_provider_contracts, "_build_requests_fetch", lambda key: fetch)
    report_path = tmp_path / "all_null.json"
    assert check_provider_contracts.main(["canary", "--report", str(report_path)]) == 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["contracts"]["profile"] == {
        "status": 200,
        "rows": len(PROFILE_FIXTURE),
        "anomalies": [
            {"code": "all_null_required_field:marketCap", "severity": "fatal", "count": 1}
        ],
        "deprecations": [],
        "ok": False,
    }
    assert all(entry["ok"] for key, entry in report["contracts"].items() if key != "profile")
    assert report["budget"] == {"max": len(FMP_CONTRACTS), "used": len(FMP_CONTRACTS)}


# S&P 500 constituent contract and existing fallback boundary.
@pytest.fixture
def sp500_offline(monkeypatch):
    import requests

    monkeypatch.delenv("FMP_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected HTTP request")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)


@pytest.mark.parametrize("field", ["symbol", "name", "sector"])
@pytest.mark.parametrize("mutation", ["missing", "null", "wrong_type"])
def test_sp500_required_fields_detect_drift(field, mutation, sp500_offline):
    rows = copy.deepcopy(SP500_FIXTURE)
    if mutation == "missing":
        del rows[0][field]
        code = f"missing_required_field:{field}"
    elif mutation == "null":
        rows[0][field] = None
        code = f"null_required_field:{field}"
    else:
        rows[0][field] = 123
        code = f"wrong_type:{field}:int"
    result = validate_rows(CONTRACTS["sp500-constituent"], rows)
    assert not result.ok
    assert code in [a.code for a in result.fatal_anomalies]


@pytest.mark.parametrize("status", [402, 403, 429, 500, -1])
@pytest.mark.parametrize("name", sorted(FMP_CONTRACTS))
def test_canary_rejects_http_failure_even_with_valid_rows(name, status, sp500_offline):
    contract = CONTRACTS[name]
    result = check_provider_contracts.run_canary(
        {name: contract}, lambda path, query: (status, copy.deepcopy(contract.fixture))
    )[name]
    assert result["status"] == status
    assert not result["ok"]
    assert result["anomalies"] == [
        {"code": f"http_status:{status}", "severity": "fatal", "count": 1}
    ]


def test_sp500_canary_empty_response_is_not_masked(sp500_offline):
    result = check_provider_contracts.run_canary(
        {"sp500-constituent": CONTRACTS["sp500-constituent"]}, lambda path, query: (200, [])
    )["sp500-constituent"]
    assert not result["ok"]
    assert result["anomalies"] == [{"code": "empty_response", "severity": "fatal", "count": 1}]


@pytest.mark.parametrize("skill", ["vcp-screener", "parabolic-short-trade-planner"])
def test_sp500_clients_accept_recording_and_cache(skill, monkeypatch, sp500_offline):
    mod = _load_client_module(f"skills/{skill}/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="offline")
    calls = []

    def fetch(url, params):
        calls.append((url, params))
        return copy.deepcopy(SP500_FIXTURE)

    monkeypatch.setattr(client, "_rate_limited_get", fetch)
    rows = client.get_sp500_constituents()
    assert rows == SP500_FIXTURE
    assert validate_rows(CONTRACTS["sp500-constituent"], rows).ok
    assert client.get_sp500_constituents() is rows
    assert len(calls) == 1
    assert calls[0][0] == "https://financialmodelingprep.com/stable/sp500-constituent"


@pytest.mark.parametrize("skill", ["vcp-screener", "parabolic-short-trade-planner"])
@pytest.mark.parametrize("status", [200, 402, 403])
def test_sp500_clients_fallback_after_empty_or_denied_response(
    skill, status, monkeypatch, sp500_offline
):
    from types import SimpleNamespace

    mod = _load_client_module(f"skills/{skill}/scripts/fmp_client.py")
    client = mod.FMPClient(api_key="offline")
    monkeypatch.setattr(mod.time, "sleep", lambda seconds: None)
    provider_calls = []
    csv_calls = []

    def provider_get(url, **kwargs):
        provider_calls.append(url)
        return SimpleNamespace(status_code=status, text="tier unavailable", json=lambda: [])

    def csv_get(url, **kwargs):
        csv_calls.append((url, kwargs))
        return SimpleNamespace(
            status_code=200,
            text="Symbol,Security,GICS Sector,GICS Sub-Industry\n"
            "BRK.B,Berkshire Hathaway,Financials,Multi-Sector Holdings\n",
        )

    monkeypatch.setattr(client.session, "get", provider_get)
    monkeypatch.setattr(mod.requests, "get", csv_get)
    rows = client.get_sp500_constituents()
    assert rows == [
        {
            "symbol": "BRK-B",
            "name": "Berkshire Hathaway",
            "sector": "Financials",
            "subSector": "Multi-Sector Holdings",
        }
    ]
    assert client.get_sp500_constituents() is rows
    assert len(provider_calls) == len(csv_calls) == 1
    assert csv_calls[0] == (
        "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv",
        {"timeout": 30},
    )


def test_sp500_recording_reaches_parabolic_universe_resolver(sp500_offline):
    # Isolate calculator imports from other skill modules in the repo test process.
    code = """
import argparse
import importlib.util
import json
import sys
import requests
from pathlib import Path

def forbidden(*args, **kwargs):
    raise AssertionError('unexpected HTTP request')
requests.sessions.Session.request = forbidden
root = Path.cwd()
spec = importlib.util.spec_from_file_location(
    'sp500_screen', root / 'skills/parabolic-short-trade-planner/scripts/screen_parabolic.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
from fmp_client import FMPClient
rows = json.loads(sys.stdin.read())
client = FMPClient(api_key='offline')
client._rate_limited_get = lambda *args, **kwargs: rows
assert mod._resolve_universe(argparse.Namespace(universe='sp500'), client) == [
    'VYLR', 'BE', 'ILMN', 'P', 'RDDT']
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(SP500_FIXTURE),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


# Economic-calendar (#332): the recorded contract must exercise its real consumer.


def _economic_consumer():
    from unittest.mock import patch

    client_module = _load_client_module("skills/economic-calendar-fetcher/scripts/fmp_client.py")
    with patch.dict(sys.modules, {"fmp_client": client_module}):
        return _load_client_module(
            "skills/economic-calendar-fetcher/scripts/get_economic_calendar.py"
        )


def test_economic_calendar_contract_matches_standalone_required_fields():
    consumer = _economic_consumer()
    contract = CONTRACTS["economic-calendar"]
    assert set(contract.required_fields) == set(consumer.REQUIRED_TEXT_FIELDS) | set(
        consumer.NULLABLE_NUMBER_FIELDS
    )
    for field in consumer.REQUIRED_TEXT_FIELDS:
        assert contract.required_fields[field] == {"types": ["str"], "nullable": False}
    for field in consumer.NULLABLE_NUMBER_FIELDS:
        assert contract.required_fields[field] == {"types": ["int", "float"], "nullable": True}


def test_economic_calendar_recording_reaches_consumer(monkeypatch):
    consumer = _economic_consumer()
    calls = []

    def fake(self, url, params=None, quiet=False):
        calls.append((url, params))
        return copy.deepcopy(ECONOMIC_FIXTURE)

    monkeypatch.setattr(consumer.FMPClient, "_rate_limited_get", fake)
    rows = consumer.fetch_economic_calendar("2026-10-01", "2026-10-07", "test-key")
    assert rows == ECONOMIC_FIXTURE
    assert calls == [
        (
            "https://financialmodelingprep.com/stable/economic-calendar",
            CONTRACTS["economic-calendar"].query,
        )
    ]
    assert "None" in {r["impact"] for r in rows}  # provider's string, not JSON null


@pytest.mark.parametrize("field", sorted(CONTRACTS["economic-calendar"].required_fields))
def test_economic_calendar_renamed_fields_fail_contract_and_consumer(monkeypatch, field):
    consumer = _economic_consumer()
    row = copy.deepcopy(ECONOMIC_FIXTURE[0])
    row["renamed_" + field] = row.pop(field)
    assert not validate_rows(CONTRACTS["economic-calendar"], [row]).ok
    monkeypatch.setattr(consumer.FMPClient, "_rate_limited_get", lambda *a, **k: [row])
    with pytest.raises(consumer.EconomicCalendarSchemaError):
        consumer.fetch_economic_calendar("2026-10-01", "2026-10-07", "test-key")


@pytest.mark.parametrize("field", sorted(CONTRACTS["economic-calendar"].required_fields))
def test_economic_calendar_retyped_fields_fail_contract_and_consumer(monkeypatch, field):
    consumer = _economic_consumer()
    row = copy.deepcopy(ECONOMIC_FIXTURE[0])
    row[field] = {"wrong": "type"}
    assert not validate_rows(CONTRACTS["economic-calendar"], [row]).ok
    monkeypatch.setattr(consumer.FMPClient, "_rate_limited_get", lambda *a, **k: [row])
    with pytest.raises(consumer.EconomicCalendarSchemaError):
        consumer.fetch_economic_calendar("2026-10-01", "2026-10-07", "test-key")


def test_economic_calendar_all_null_readings_are_valid():
    consumer = _economic_consumer()
    rows = copy.deepcopy(ECONOMIC_FIXTURE)
    for row in rows:
        for field in consumer.NULLABLE_NUMBER_FIELDS:
            row[field] = None
    assert validate_rows(CONTRACTS["economic-calendar"], rows).ok
    consumer.validate_economic_events(rows)


def test_economic_calendar_canary_flags_known_populated_window_empty():
    from scripts.check_provider_contracts import run_canary

    contract = CONTRACTS["economic-calendar"]
    result = run_canary({"economic-calendar": contract}, lambda path, query: (200, []))
    assert not result["economic-calendar"]["ok"]
    assert any(a["code"] == "empty_response" for a in result["economic-calendar"]["anomalies"])


# ---------------------------------------------------------------------------
# Public CSV providers (trader-monty): framework, canary, and fixtures
# ---------------------------------------------------------------------------

from scripts.provider_contracts import (  # noqa: E402
    Anomaly,
    RowValidation,
    parse_csv_rows,
)


def _csv_contract_data(**overrides):
    data = {
        "schema_version": 1,
        "provider": "trader-monty",
        "endpoint": "demo-csv",
        "path": "/demo/demo.csv",
        "format": "csv",
        "url": "https://tradermonty.github.io/demo/demo.csv",
        "query": {},
        "contract_version": 1,
        "recorded_on": "2026-10-24",
        "recording": "test",
        "owners": ["market-breadth-analyzer"],
        "tier_notes": "",
        "required_fields": {
            "Date": {"types": ["str"]},
            "Value": {"types": ["float", "int"], "nullable": True},
        },
        "optional_fields": [],
        "legacy_aliases": {},
        "non_empty": {"min_rows": 1},
        "fixture": [{"Date": "2026-10-23", "Value": 1.5}],
    }
    data.update(overrides)
    return data


def _write_csv_contract(tmp_path, **overrides):
    data = _csv_contract_data(**overrides)
    folder = tmp_path / "config" / "provider-contracts" / data["provider"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{data['endpoint']}.v1.json").write_text(json.dumps(data), encoding="utf-8")
    return load_contracts(tmp_path)[data["endpoint"]]


def _errors_for(tmp_path, **overrides):
    contract = _write_csv_contract(tmp_path, **overrides)
    return validate_contract_file(contract, SKILL_IDS)


def test_parse_csv_rows_coerces_cells():
    text = (
        "name,flag,n,x,e,when,empty\n"
        'A,True,3,1.5,1e3,2026-10-23,\n"B, Inc",FALSE,-4,.5,2.5E-2,2026-10-24,\n'
    )
    rows, anomalies = parse_csv_rows(text)
    assert anomalies == []
    assert rows[0] == {
        "name": "A",
        "flag": True,
        "n": 3,
        "x": 1.5,
        "e": 1000.0,
        "when": "2026-10-23",
        "empty": None,
    }
    assert rows[1]["name"] == "B, Inc"
    assert rows[1]["flag"] is False
    assert rows[1]["n"] == -4 and isinstance(rows[1]["n"], int)
    assert rows[1]["x"] == 0.5
    assert rows[1]["e"] == 0.025


@pytest.mark.parametrize("cell", ["nan", "NaN", "inf", "-inf", "Infinity", "1e999"])
def test_parse_csv_rows_keeps_non_finite_as_str(cell):
    rows, _ = parse_csv_rows(f"v\n{cell}\n")
    assert rows == [{"v": cell}]
    assert isinstance(rows[0]["v"], str)


@pytest.mark.parametrize("cell", ["tRuE", "TRUE", "true"])
def test_parse_csv_rows_bool_any_case(cell):
    rows, _ = parse_csv_rows(f"v\n{cell}\n")
    assert rows == [{"v": True}]


def test_parse_csv_rows_header_only_and_blank():
    assert parse_csv_rows("a,b\n") == ([], [])
    assert parse_csv_rows("") == ([], [])


def test_parse_csv_rows_strips_bom():
    rows, _ = parse_csv_rows("﻿Date,V\n2026-10-23,1\n")
    assert rows == [{"Date": "2026-10-23", "V": 1}]


def test_parse_csv_rows_short_row_maps_missing_to_none():
    rows, anomalies = parse_csv_rows("a,b,c\n1,2\n")
    assert anomalies == []
    assert rows == [{"a": 1, "b": 2, "c": None}]


def test_parse_csv_rows_extra_cell_is_fatal_and_dropped():
    rows, anomalies = parse_csv_rows("a,b\n1,2,3\n4,5\n6,7,8,9\n")
    assert [a.code for a in anomalies] == ["extra_cells", "extra_cells"]
    assert all(a.severity == "fatal" for a in anomalies)
    assert rows == [{"a": 1, "b": 2}, {"a": 4, "b": 5}, {"a": 6, "b": 7}]
    assert all(None not in row and set(row) == {"a", "b"} for row in rows)


def test_csv_contract_valid_baseline(tmp_path):
    assert _errors_for(tmp_path) == []


@pytest.mark.parametrize(
    "overrides,fragment",
    [
        ({"format": "xml"}, "format"),
        ({"url": "http://tradermonty.github.io/demo/demo.csv"}, "https"),
        ({"url": "https://example.com/demo/demo.csv"}, "host"),
        ({"url": "https://tradermonty.github.io/demo/demo.csv?x=1"}, "query"),
        ({"url": "https://tradermonty.github.io:8443/demo/demo.csv"}, "host"),
        ({"url": "https://user@tradermonty.github.io/demo/demo.csv"}, "host"),
        ({"url": ""}, "url"),
        ({"query": {"x": "1"}}, "query"),
        ({"path": "/other.csv"}, "path"),
        ({"max_bytes": 0}, "max_bytes"),
        ({"max_bytes": -5}, "max_bytes"),
        ({"max_bytes": "big"}, "max_bytes"),
        ({"max_bytes": True}, "max_bytes"),
        ({"required_values": {"Date": "2026-10-23"}}, "required_values"),
        ({"required_values": {"Nope": ["x"]}}, "required_values"),
    ],
)
def test_csv_contract_rejects_invalid_shape(tmp_path, overrides, fragment):
    errors = _errors_for(tmp_path, **overrides)
    assert errors, overrides
    assert any(fragment in e for e in errors), errors


def test_json_contract_forbids_url_and_max_bytes(tmp_path):
    errors = _errors_for(tmp_path, format="json", url="https://tradermonty.github.io/demo/demo.csv")
    assert any("url" in e for e in errors)
    errors = _errors_for(tmp_path, format="json", url="", max_bytes=1024, endpoint="demo-json")
    assert any("max_bytes" in e for e in errors)


def test_csv_contract_default_format_is_json_and_default_max_bytes(tmp_path):
    contract = _write_csv_contract(tmp_path)
    assert contract.format == "csv"
    assert contract.max_bytes is None
    assert contract.effective_max_bytes == 2 * 1024 * 1024
    contract = _write_csv_contract(tmp_path, max_bytes=16 * 1024 * 1024, endpoint="big")
    assert contract.effective_max_bytes == 16 * 1024 * 1024
    for fmp in FMP_CONTRACTS.values():
        assert fmp.format == "json" and fmp.url == ""


def test_required_values_pass_and_fail(tmp_path):
    contract = _write_csv_contract(
        tmp_path,
        required_fields={"w": {"types": ["str"]}},
        required_values={"w": ["all", "other"]},
        fixture=[{"w": "all"}, {"w": "other"}],
    )
    assert validate_rows(contract, contract.fixture).ok
    result = validate_rows(contract, [{"w": "all"}])
    assert [a.code for a in result.fatal_anomalies] == ["missing_required_value:w=other"]
    assert not validate_rows(contract, [{"w": "x"}]).ok


def test_fixture_missing_required_value_fails_check(tmp_path):
    errors = _errors_for(
        tmp_path,
        required_fields={"w": {"types": ["str"]}},
        required_values={"w": ["all"]},
        fixture=[{"w": "x"}],
    )
    assert any("missing_required_value:w=all" in e for e in errors)


def test_summarized_dedupes_with_count_in_first_seen_order():
    result = RowValidation(
        [
            Anomaly("a", "fatal"),
            Anomaly("b", "deprecation"),
            Anomaly("a", "fatal"),
            Anomaly("c", "fatal"),
            Anomaly("a", "fatal"),
        ]
    )
    assert result.summarized() == [
        {"code": "a", "severity": "fatal", "count": 3},
        {"code": "b", "severity": "deprecation", "count": 1},
        {"code": "c", "severity": "fatal", "count": 1},
    ]
    assert result.summarized("fatal") == [
        {"code": "a", "severity": "fatal", "count": 3},
        {"code": "c", "severity": "fatal", "count": 1},
    ]


def test_summarized_collapses_30k_row_rename(tmp_path):
    contract = _write_csv_contract(tmp_path)
    rows = [{"Date": "2026-10-23", "Val": 1.0} for _ in range(30000)]
    result = validate_rows(contract, rows)
    assert len(result.anomalies) == 30000
    assert result.summarized() == [
        {"code": "missing_required_field:Value", "severity": "fatal", "count": 30000}
    ]


def test_validate_rows_keeps_per_row_anomalies_for_fmp():
    contract = CONTRACTS["profile"]
    result = validate_rows(contract, [{} for _ in range(3)])
    assert len([a for a in result.anomalies if a.code == "missing_required_field:symbol"]) == 3


def test_duplicate_endpoint_across_providers_still_rejected(tmp_path):
    for provider in ("fmp", "trader-monty"):
        folder = tmp_path / "config" / "provider-contracts" / provider
        folder.mkdir(parents=True)
        (folder / "dup.v1.json").write_text(
            json.dumps(_csv_contract_data(provider=provider, endpoint="dup")), encoding="utf-8"
        )
    with pytest.raises(ContractLoadError, match="duplicate endpoint 'dup'"):
        load_contracts(tmp_path)


# --- real trader-monty contracts -------------------------------------------


def test_trader_monty_contracts_pass_check():
    for name, contract in TRADER_MONTY_CONTRACTS.items():
        assert contract.format == "csv", name
        assert contract.recorded_on == "2026-10-24", name
        assert validate_contract_file(contract, SKILL_IDS) == [], name
    assert check_provider_contracts.main(["check"]) == 0


def test_trader_monty_contract_shapes():
    breadth = TRADER_MONTY_CONTRACTS["market-breadth-data"]
    assert breadth.url == (
        "https://tradermonty.github.io/market-breadth-analysis/market_breadth_data.csv"
    )
    assert breadth.owners == [
        "market-breadth-analyzer",
        "market-top-detector",
        "breadth-chart-analyst",
    ]
    assert set(breadth.required_fields) == {
        "Date",
        "S&P500_Price",
        "Breadth_Index_Raw",
        "Breadth_Index_200MA",
        "Breadth_Index_8MA",
        "Breadth_200MA_Trend",
        "Bearish_Signal",
        "Is_Peak",
        "Is_Trough",
        "Is_Trough_8MA_Below_04",
    }
    assert breadth.required_fields["Breadth_200MA_Trend"]["types"] == ["int"]
    assert "Breadth_50_Index_Raw" in breadth.optional_fields
    ts = TRADER_MONTY_CONTRACTS["uptrend-ratio-timeseries"]
    assert ts.max_bytes == 16 * 1024 * 1024
    assert ts.required_values == {"worksheet": ["all"]}
    assert ts.required_fields["ratio"]["reject_all_null"] is True
    assert ts.required_fields["ma_10"]["nullable"] is True
    assert ts.required_fields["slope"]["nullable"] is True
    assert any(r["ma_10"] is None for r in ts.fixture)
    assert any(r["slope"] is None for r in ts.fixture)
    assert any(r["worksheet"] == "all" for r in ts.fixture)
    summary = TRADER_MONTY_CONTRACTS["market-breadth-summary"]
    assert summary.required_values == {
        "Metric": ["Average Peaks (200MA)", "Average Troughs (8MA < 0.4)"]
    }
    assert set(TRADER_MONTY_CONTRACTS["uptrend-sector-summary"].required_fields) == {
        "Sector",
        "Ratio",
        "10MA",
        "Trend",
        "Slope",
        "Status",
    }
    for contract in TRADER_MONTY_CONTRACTS.values():
        assert 5 <= len(contract.fixture) <= 10, contract.endpoint
        assert contract.provider == "trader-monty"


def test_breadth_aliases_are_consumer_tolerated_alternates():
    aliases = TRADER_MONTY_CONTRACTS["market-breadth-data"].legacy_aliases
    assert {k: v["canonical"] for k, v in aliases.items()} == {
        "SP500_Price": "S&P500_Price",
        "Breadth_200MA": "Breadth_Index_200MA",
        "Breadth_8MA": "Breadth_Index_8MA",
        "Trend": "Breadth_200MA_Trend",
    }


def _contract_csv_text(contract):
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(contract.fixture[0]), lineterminator="\n")
    writer.writeheader()
    for row in contract.fixture:
        writer.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return buffer.getvalue()


@pytest.mark.parametrize("name", sorted(TRADER_MONTY_CONTRACTS))
def test_trader_monty_fixture_roundtrips_through_csv_text(name):
    contract = TRADER_MONTY_CONTRACTS[name]
    rows, anomalies = parse_csv_rows(_contract_csv_text(contract))
    assert anomalies == []
    assert rows == contract.fixture
    assert validate_rows(contract, rows).ok


_BREADTH_BOOL_COLUMNS = ("Bearish_Signal", "Is_Peak", "Is_Trough", "Is_Trough_8MA_Below_04")


@pytest.mark.parametrize("column", _BREADTH_BOOL_COLUMNS)
@pytest.mark.parametrize("cell", ["Y", "N", "T", "1", "yes"])
def test_breadth_bool_columns_reject_non_bool_values(column, cell):
    """Owners disagree on non-True/False spellings (market-top-detector reads them as
    False), so any of them must be fatal drift rather than a silently passing str/int.
    The value goes through CSV text so the coercion step is part of the check."""
    contract = TRADER_MONTY_CONTRACTS["market-breadth-data"]
    row = copy.deepcopy(contract.fixture[0])
    row[column] = cell
    drifted = copy.copy(contract)
    drifted.fixture = [row]
    rows, anomalies = parse_csv_rows(_contract_csv_text(drifted))
    assert anomalies == []
    result = validate_rows(contract, rows)
    assert not result.ok
    assert any(a.code.startswith(f"wrong_type:{column}:") for a in result.fatal_anomalies)


@pytest.mark.parametrize("name", sorted(TRADER_MONTY_CONTRACTS))
def test_trader_monty_every_required_field_rename_is_fatal(name):
    contract = TRADER_MONTY_CONTRACTS[name]
    for column in contract.required_fields:
        rows = copy.deepcopy(contract.fixture)
        for row in rows:
            row[column + "_renamed"] = row.pop(column)
        codes = [a.code for a in validate_rows(contract, rows).fatal_anomalies]
        assert any(c.endswith(f":{column}") for c in codes), (name, column, codes)


# --- canary ----------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status=200, body=b"", chunk=7):
        self.status_code = status
        self._body = body
        self._chunk = chunk
        self.closed = False

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self._body), self._chunk):
            yield self._body[i : i + self._chunk]

    def close(self):
        self.closed = True


def _stub_public_fetch(contract):
    rows, anomalies = parse_csv_rows(_contract_csv_text(contract))
    return check_provider_contracts.FetchResult(200, rows, anomalies)


def _use_stub_public_fetch(monkeypatch):
    monkeypatch.setattr(
        check_provider_contracts, "_build_public_csv_fetch", lambda: _stub_public_fetch
    )


def test_canary_provider_filter_and_budget(tmp_path, monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    _use_stub_public_fetch(monkeypatch)
    report_path = tmp_path / "tm.json"
    code = check_provider_contracts.main(
        ["canary", "--provider", "trader-monty", "--report", str(report_path)]
    )
    assert code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["provider"] == "trader-monty"
    assert set(report["contracts"]) == set(TRADER_MONTY_CONTRACTS)
    assert report["budget"] == {
        "max": len(TRADER_MONTY_CONTRACTS),
        "used": len(TRADER_MONTY_CONTRACTS),
    }
    assert report["ok"] is True


def test_canary_default_provider_is_fmp_and_requires_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    report_path = tmp_path / "x.json"
    assert check_provider_contracts.main(["canary", "--report", str(report_path)]) == 1
    assert "FMP_API_KEY" in capsys.readouterr().err
    assert not report_path.exists()


def test_canary_default_fmp_run_report_has_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "FAKEKEY123")
    monkeypatch.setattr(
        check_provider_contracts, "_build_requests_fetch", lambda api_key: _stub_fetch_ok
    )
    report_path = tmp_path / "fmp.json"
    assert check_provider_contracts.main(["canary", "--report", str(report_path)]) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["provider"] == "fmp"
    assert set(report["contracts"]) == set(FMP_CONTRACTS)


def test_canary_provider_all_runs_both(tmp_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "FAKEKEY123")
    monkeypatch.setattr(
        check_provider_contracts, "_build_requests_fetch", lambda api_key: _stub_fetch_ok
    )
    _use_stub_public_fetch(monkeypatch)
    report_path = tmp_path / "all.json"
    args = ["canary", "--provider", "all", "--report", str(report_path)]
    assert check_provider_contracts.main(args) == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["provider"] == "all"
    assert set(report["contracts"]) == set(CONTRACTS)
    assert report["budget"]["max"] == len(CONTRACTS)


def test_canary_trader_monty_budget_refuses(tmp_path, capsys):
    report_path = tmp_path / "no.json"
    code = check_provider_contracts.main(
        ["canary", "--provider", "trader-monty", "--max-calls", "2", "--report", str(report_path)]
    )
    assert code == 1
    assert "refusing to start" in capsys.readouterr().err
    assert not report_path.exists()


def test_canary_default_report_path_is_provider_named():
    path = check_provider_contracts._default_report_path("trader-monty")
    assert path.name.startswith("trader-monty_canary_") and path.parent.name == "reports"
    assert check_provider_contracts._default_report_path("fmp").name.startswith("fmp_canary_")
    assert check_provider_contracts._default_report_path().name.startswith("fmp_canary_")


def test_run_canary_bare_callable_with_non_fmp_contract_raises():
    with pytest.raises(TypeError):
        check_provider_contracts.run_canary(
            {"market-breadth-data": TRADER_MONTY_CONTRACTS["market-breadth-data"]},
            lambda path, query: (200, []),
        )


def test_run_canary_dict_dispatch_by_provider():
    contracts = {
        "profile": CONTRACTS["profile"],
        "market-breadth-summary": CONTRACTS["market-breadth-summary"],
    }
    fetchers = {
        "fmp": lambda c: check_provider_contracts.FetchResult(
            200, copy.deepcopy(PROFILE_FIXTURE), []
        ),
        "trader-monty": _stub_public_fetch,
    }
    results = check_provider_contracts.run_canary(contracts, fetchers)
    assert results["profile"]["ok"] and results["market-breadth-summary"]["ok"]


def _run_one(name, fetch_result):
    return check_provider_contracts.run_canary(
        {name: CONTRACTS[name]}, {"trader-monty": lambda c: fetch_result}
    )[name]


def test_canary_non_200_csv_is_exactly_http_status():
    result = _run_one("market-breadth-data", check_provider_contracts.FetchResult(404, None, []))
    assert result["anomalies"] == [{"code": "http_status:404", "severity": "fatal", "count": 1}]
    assert result["ok"] is False and result["rows"] == 0


def test_canary_redirect_csv_is_exactly_http_status():
    result = _run_one("market-breadth-data", check_provider_contracts.FetchResult(301, None, []))
    assert result["anomalies"] == [{"code": "http_status:301", "severity": "fatal", "count": 1}]


def test_canary_transport_error_replaces_http_status():
    result = _run_one(
        "market-breadth-data",
        check_provider_contracts.FetchResult(-1, None, [Anomaly("transport_error", "fatal")]),
    )
    assert result["anomalies"] == [{"code": "transport_error", "severity": "fatal", "count": 1}]


def test_canary_renamed_column_collapses_to_one_entry():
    contract = CONTRACTS["uptrend-ratio-timeseries"]
    rows = [dict(r) for _ in range(4000) for r in contract.fixture]
    for row in rows:
        row["count_x"] = row.pop("count")
    fetched = check_provider_contracts.FetchResult(200, rows, [])
    result = _run_one("uptrend-ratio-timeseries", fetched)
    assert result["anomalies"] == [
        {"code": "missing_required_field:count", "severity": "fatal", "count": len(rows)}
    ]
    assert result["ok"] is False


def test_canary_missing_required_value_is_fatal():
    contract = CONTRACTS["market-breadth-summary"]
    rows = [r for r in copy.deepcopy(contract.fixture) if r["Metric"] != "Average Peaks (200MA)"]
    result = _run_one("market-breadth-summary", check_provider_contracts.FetchResult(200, rows, []))
    assert [a["code"] for a in result["anomalies"]] == [
        "missing_required_value:Metric=Average Peaks (200MA)"
    ]


def test_canary_extra_anomalies_are_merged():
    contract = CONTRACTS["market-breadth-summary"]
    fetched = check_provider_contracts.FetchResult(
        200, copy.deepcopy(contract.fixture), [Anomaly("extra_cells", "fatal")] * 2
    )
    result = _run_one("market-breadth-summary", fetched)
    assert result["anomalies"] == [{"code": "extra_cells", "severity": "fatal", "count": 2}]
    assert result["ok"] is False


def test_canary_deprecations_are_summarized():
    contract = CONTRACTS["market-breadth-data"]
    rows = copy.deepcopy(contract.fixture)
    for row in rows:
        row["SP500_Price"] = row["S&P500_Price"]
    result = _run_one("market-breadth-data", check_provider_contracts.FetchResult(200, rows, []))
    assert result["ok"] is True
    assert result["deprecations"] == [
        {"code": "legacy_alias_present:SP500_Price", "severity": "deprecation", "count": len(rows)}
    ]


def test_canary_header_only_csv_is_empty_response():
    result = _run_one("market-breadth-data", check_provider_contracts.FetchResult(200, [], []))
    assert [a["code"] for a in result["anomalies"]] == ["empty_response"]


def test_legacy_fmp_path_still_reports_http_status_minus_one():
    result = check_provider_contracts.run_canary(
        {"profile": CONTRACTS["profile"]},
        lambda path, query: (-1, {"error": "boom"}),
    )["profile"]
    assert result["anomalies"][-1] == {"code": "http_status:-1", "severity": "fatal", "count": 1}


# --- public CSV fetch (HTTP layer) -----------------------------------------


class _CsvStub:
    endpoint = "stub"
    url = "https://tradermonty.github.io/demo/demo.csv"

    def __init__(self, max_bytes):
        self.effective_max_bytes = max_bytes


def _patch_get(monkeypatch, response=None, exc=None):
    import requests

    calls = []

    def fake_get(*args, **kwargs):
        calls.append((args, kwargs))
        if exc is not None:
            raise exc
        return response

    monkeypatch.setattr(requests, "get", fake_get)
    return calls


def _public_fetch(max_bytes=1024):
    return check_provider_contracts._build_public_csv_fetch()(_CsvStub(max_bytes))


def test_public_fetch_call_has_no_credentials_and_no_redirects(monkeypatch):
    calls = _patch_get(monkeypatch, _FakeResponse(200, b"a,b\n1,2\n"))
    result = _public_fetch()
    assert result.status == 200
    assert result.rows == [{"a": 1, "b": 2}]
    ((args, kwargs),) = calls
    assert args == ("https://tradermonty.github.io/demo/demo.csv",)
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True
    assert kwargs["timeout"] == 30
    assert not ({"params", "headers", "auth", "cookies"} & set(kwargs))


def test_public_fetch_body_size_boundary(monkeypatch):
    body = b"a\n" + b"1" * 6 + b"\n"
    _patch_get(monkeypatch, _FakeResponse(200, body))
    ok = _public_fetch(len(body))
    assert ok.rows == [{"a": 111111}] and ok.extra_anomalies == []
    _patch_get(monkeypatch, _FakeResponse(200, body))
    big = _public_fetch(len(body) - 1)
    assert big.status == 200 and big.rows is None
    assert [a.code for a in big.extra_anomalies] == [f"body_too_large:{len(body) - 1}"]


def test_public_fetch_non_200_and_redirect_have_no_rows(monkeypatch):
    for status in (404, 301, 500):
        response = _FakeResponse(status, b"<html>")
        _patch_get(monkeypatch, response)
        result = _public_fetch()
        assert (result.status, result.rows, result.extra_anomalies) == (status, None, [])
        assert response.closed


def test_public_fetch_transport_error(monkeypatch, capsys):
    import requests

    _patch_get(
        monkeypatch,
        exc=requests.exceptions.ConnectionError("boom https://x/?apikey=SECRET123 down"),
    )
    result = _public_fetch()
    assert result.status == -1 and result.rows is None
    assert [a.code for a in result.extra_anomalies] == ["transport_error"]
    err = capsys.readouterr().err
    assert "SECRET123" not in err and "apikey=REDACTED" in err


def test_public_fetch_undecodable_body_is_decode_error(monkeypatch):
    _patch_get(monkeypatch, _FakeResponse(200, b"a\n\xff\xfe\n"))
    result = _public_fetch()
    assert result.status == 200 and result.rows is None
    assert [a.code for a in result.extra_anomalies] == ["decode_error"]


def test_public_fetch_nul_byte_body_never_aborts(monkeypatch):
    # Python >= 3.11 parses NUL; older csv raises. Either way no exception escapes.
    _patch_get(monkeypatch, _FakeResponse(200, b"a,b\n1,\x002\n"))
    result = _public_fetch()
    assert result.status == 200
    assert result.rows is not None or [a.code for a in result.extra_anomalies] == ["parse_error"]


def test_public_fetch_oversized_field_is_parse_error(monkeypatch):
    _patch_get(monkeypatch, _FakeResponse(200, b"a\n" + b"x" * 200_000 + b"\n"))
    result = _public_fetch(max_bytes=1_000_000)
    assert result.status == 200 and result.rows is None
    assert [(a.code, a.severity) for a in result.extra_anomalies] == [
        ("parse_error", check_provider_contracts.FATAL)
    ]


def test_canary_parse_error_does_not_abort_other_contracts(tmp_path, monkeypatch):
    import requests

    monkeypatch.delenv("FMP_API_KEY", raising=False)
    bad = "uptrend-ratio-timeseries"
    real_fetch = check_provider_contracts._build_public_csv_fetch()

    def fetch(contract):
        if contract.endpoint == bad:
            monkeypatch.setattr(
                requests, "get", lambda *a, **k: _FakeResponse(200, b"a\n" + b"x" * 200_000 + b"\n")
            )
            return real_fetch(contract)
        return _stub_public_fetch(contract)

    monkeypatch.setattr(check_provider_contracts, "_build_public_csv_fetch", lambda: fetch)
    report_path = tmp_path / "tm.json"
    code = check_provider_contracts.main(
        ["canary", "--provider", "trader-monty", "--report", str(report_path)]
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == 1
    assert set(report["contracts"]) == set(TRADER_MONTY_CONTRACTS)
    assert report["contracts"][bad]["ok"] is False
    assert any(a["code"] == "parse_error" for a in report["contracts"][bad]["anomalies"])
    others = [v for k, v in report["contracts"].items() if k != bad]
    assert others and all(v["ok"] for v in others)


def test_public_fetch_decodes_bom(monkeypatch):
    _patch_get(monkeypatch, _FakeResponse(200, "﻿a\n1\n".encode()))
    assert _public_fetch().rows == [{"a": 1}]


def test_public_fetch_extra_cells_reported(monkeypatch):
    _patch_get(monkeypatch, _FakeResponse(200, b"a\n1,2\n"))
    result = _public_fetch()
    assert result.rows == [{"a": 1}]
    assert [a.code for a in result.extra_anomalies] == ["extra_cells"]
