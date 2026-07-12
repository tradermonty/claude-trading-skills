"""Cross-vendor runtime behavior tests for the generated family-B fmp_client.py.

Loads each skill's standalone vendored client by file path (same isolation as
``test_fmp_client_truncate_contract.py``) and asserts the shared family-B
invariants — budget enforcement and the get_api_stats shape — so the generated
clients are exercised at runtime in CI (these skills are absent from the
per-skill CI test matrix; ``scripts/tests/`` runs in CI).
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

FAMILY_B = [
    "skills/pead-screener/scripts/fmp_client.py",
    "skills/earnings-trade-analyzer/scripts/fmp_client.py",
    "skills/ibd-distribution-day-monitor/scripts/fmp_client.py",
]

FAMILY_A = [
    "skills/vcp-screener/scripts/fmp_client.py",
    "skills/parabolic-short-trade-planner/scripts/fmp_client.py",
    "skills/ftd-detector/scripts/fmp_client.py",
]

SPECIALS = [
    "skills/canslim-screener/scripts/fmp_client.py",
    "skills/macro-regime-detector/scripts/fmp_client.py",
    "skills/market-top-detector/scripts/fmp_client.py",
]


def _load(rel_path: str):
    abs_path = REPO_ROOT / rel_path
    skill = abs_path.parent.parent.name.replace("-", "_")
    name = f"_fmp_shared_{skill}"
    sys.modules.pop(name, None)
    sys.modules.pop("_fmp_compat", None)  # avoid leaking one skill's shim into another
    sys.path.insert(0, str(abs_path.parent))
    try:
        spec = importlib.util.spec_from_file_location(name, str(abs_path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(abs_path.parent))


@pytest.mark.parametrize("rel_path", FAMILY_B)
def test_budget_exceeded_raises(rel_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load(rel_path)
    client = mod.FMPClient(api_key="test_key", max_api_calls=0)  # pragma: allowlist secret
    with pytest.raises(mod.ApiCallBudgetExceeded):
        client._rate_limited_get("https://example.test/x")


@pytest.mark.parametrize("rel_path", FAMILY_B)
def test_api_stats_budget_shape(rel_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load(rel_path)
    client = mod.FMPClient(api_key="test_key", max_api_calls=200)  # pragma: allowlist secret
    stats = client.get_api_stats()
    assert set(stats) == {
        "cache_entries",
        "api_calls_made",
        "max_api_calls",
        "rate_limit_reached",
        "budget_remaining",
    }
    assert stats["max_api_calls"] == 200
    assert stats["budget_remaining"] == 200


@pytest.mark.parametrize("rel_path", FAMILY_B)
def test_no_quote_surface(rel_path):
    mod = _load(rel_path)
    assert not hasattr(mod.FMPClient, "get_quote")
    assert hasattr(mod.FMPClient, "get_historical_prices")
    assert hasattr(mod.FMPClient, "get_earnings_calendar")


@pytest.mark.parametrize("rel_path", FAMILY_A)
def test_family_a_quote_surface_no_budget(rel_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load(rel_path)
    assert hasattr(mod.FMPClient, "get_quote")
    assert hasattr(mod.FMPClient, "get_batch_quotes")
    assert hasattr(mod.FMPClient, "calculate_sma")
    assert not hasattr(mod, "ApiCallBudgetExceeded")
    # No budget surface: __init__ takes no max_api_calls, stats omit budget keys.
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    stats = client.get_api_stats()
    assert set(stats) == {"cache_entries", "api_calls_made", "rate_limit_reached"}


@pytest.mark.parametrize("rel_path", SPECIALS)
def test_special_clients_have_no_budget(rel_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load(rel_path)
    assert not hasattr(mod, "ApiCallBudgetExceeded")
    mod.FMPClient(api_key="test_key")  # pragma: allowlist secret


def test_canslim_special_surface_and_stats(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load("skills/canslim-screener/scripts/fmp_client.py")
    for method in (
        "get_income_statement",
        "get_quote",
        "get_historical_prices",
        "get_profile",
        "get_institutional_holders",
        "calculate_ema",
        "get_api_stats",
        "clear_cache",
    ):
        assert hasattr(mod.FMPClient, method)
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    assert set(client.get_api_stats()) == {
        "cache_entries",
        "rate_limit_reached",
        "retry_count",
    }


def test_macro_special_surface_and_stats(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load("skills/macro-regime-detector/scripts/fmp_client.py")
    assert hasattr(mod, "_has_usable_history")
    for method in (
        "get_historical_prices",
        "_get_from_yfinance",
        "get_batch_historical",
        "get_treasury_rates",
        "get_api_stats",
    ):
        assert hasattr(mod.FMPClient, method)
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    assert set(client.get_api_stats()) == {
        "cache_entries",
        "api_calls_made",
        "rate_limit_reached",
    }


def test_market_top_special_surface_and_stats(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "test_key")  # pragma: allowlist secret
    mod = _load("skills/market-top-detector/scripts/fmp_client.py")
    assert hasattr(mod, "_has_usable_history")
    for method in (
        "get_quote",
        "_get_quote_from_yfinance",
        "get_historical_prices",
        "_get_hist_from_yfinance",
        "get_batch_quotes",
        "get_batch_historical",
        "calculate_ema",
        "calculate_sma",
        "get_vix_term_structure",
        "get_api_stats",
    ):
        assert hasattr(mod.FMPClient, method)
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    assert set(client.get_api_stats()) == {
        "cache_entries",
        "api_calls_made",
        "rate_limit_reached",
    }


# Clients whose registry row includes the sp500_constituents extension.
CONSTITUENTS_CLIENTS = [
    "skills/vcp-screener/scripts/fmp_client.py",
    "skills/parabolic-short-trade-planner/scripts/fmp_client.py",
]

_CONSTITUENTS_CSV = (
    "Symbol,Security,GICS Sector,GICS Sub-Industry,Headquarters Location,"
    "Date added,CIK,Founded\n"
    'MMM,3M,Industrials,Industrial Conglomerates,"Saint Paul, Minnesota",'
    "1957-03-04,66740,1902\n"
    'BRK.B,Berkshire Hathaway,Financials,Multi-Sector Holdings,"Omaha, Nebraska",'
    "2010-02-16,1067983,1839\n"
)


class _FakeCsvResponse:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


@pytest.mark.parametrize("rel_path", CONSTITUENTS_CLIENTS)
def test_constituents_public_csv_fallback_when_no_fmp_tier(rel_path, monkeypatch):
    """Free tier: stable 402s, v3 403s — no FMP endpoint serves the list."""
    mod = _load(rel_path)
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    # _rate_limited_get returns None on 402/403 — simulate FMP unavailable.
    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: None)
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _FakeCsvResponse(200, _CONSTITUENTS_CSV)

    monkeypatch.setattr(mod.requests, "get", fake_get)
    result = client.get_sp500_constituents()

    # Dot-class symbols normalized to FMP's dash style (BRK.B -> BRK-B).
    assert [c["symbol"] for c in result] == ["MMM", "BRK-B"]
    assert result[0] == {
        "symbol": "MMM",
        "name": "3M",
        "sector": "Industrials",
        "subSector": "Industrial Conglomerates",
    }
    assert "s-and-p-500-companies" in captured["url"]
    # Bare requests.get: the FMP apikey session header must not leak.
    assert "headers" not in captured["kwargs"]


@pytest.mark.parametrize("rel_path", CONSTITUENTS_CLIENTS)
def test_constituents_csv_not_fetched_when_fmp_succeeds(rel_path, monkeypatch):
    mod = _load(rel_path)
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    fmp_rows = [
        {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology", "subSector": "Hardware"}
    ]
    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: list(fmp_rows))

    def fail_get(url, **kwargs):
        raise AssertionError("public CSV must not be fetched when FMP works")

    monkeypatch.setattr(mod.requests, "get", fail_get)
    assert client.get_sp500_constituents() == fmp_rows


@pytest.mark.parametrize("rel_path", CONSTITUENTS_CLIENTS)
def test_constituents_none_when_fmp_and_csv_both_fail(rel_path, monkeypatch):
    mod = _load(rel_path)
    client = mod.FMPClient(api_key="test_key")  # pragma: allowlist secret
    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: None)
    monkeypatch.setattr(
        mod.requests, "get", lambda url, **kwargs: _FakeCsvResponse(500, "upstream down")
    )
    assert client.get_sp500_constituents() is None
