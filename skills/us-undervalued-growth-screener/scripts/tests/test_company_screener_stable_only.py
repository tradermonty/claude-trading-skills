"""The company screener is stable-only and plan refusals are named (issue #707)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import fmp_client  # noqa: E402
from pipeline_common import _empty_universe_message  # noqa: E402


class _Session:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.payload = payload if payload is not None else []
        self.urls: list[str] = []

    def get(self, url, params=None, timeout=None):
        self.urls.append(url)
        return SimpleNamespace(
            status_code=self.status_code, text="Restricted Endpoint", json=lambda: self.payload
        )

    def close(self):
        pass


def _client(tmp_path, session):
    client = fmp_client.FMPClient(
        api_key="test-key",  # pragma: allowlist secret
        cache_path=tmp_path / "cache.sqlite3",
        rate_limit_delay=0.0,
    )
    client.session = session
    return client


def _screen(client):
    return client.get_company_screener(
        exchange="NASDAQ", min_market_cap=1e9, max_market_cap=2e9, min_price=5.0, limit=10
    )


def test_screener_uses_company_screener_and_never_calls_v3(tmp_path):
    session = _Session(200, [{"symbol": "AAA", "companyName": "A"}])
    rows = _screen(_client(tmp_path, session))
    assert [r["symbol"] for r in rows] == ["AAA"]
    assert session.urls == ["https://financialmodelingprep.com/stable/company-screener"]


@pytest.mark.parametrize("status", [402, 403])
def test_refused_screener_has_no_v3_fallback_and_reports_plan_restriction(tmp_path, status):
    session = _Session(status)
    client = _client(tmp_path, session)
    assert _screen(client) == []
    assert all("/api/v3/" not in url for url in session.urls)
    assert all(url.endswith("/stable/company-screener") for url in session.urls)
    message = _empty_universe_message(client)
    assert "plan restriction" in message
    assert "getting-started.md#fmp-plans" in message


def test_empty_universe_without_a_refusal_keeps_the_generic_message(tmp_path):
    client = _client(tmp_path, _Session(200, []))
    assert _screen(client) == []
    assert "plan restriction" not in _empty_universe_message(client)
