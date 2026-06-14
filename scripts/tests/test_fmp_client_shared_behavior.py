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
