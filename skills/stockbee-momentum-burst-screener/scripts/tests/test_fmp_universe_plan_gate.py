"""--fmp-universe on a plan without the company screener must say so (issue #707)."""

import sys
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import screen_momentum_burst as mod  # noqa: E402


class _Response:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

    def json(self):
        return []


class _Session:
    def __init__(self, status_code):
        self.status_code = status_code
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        return _Response(self.status_code, "Restricted Endpoint")


def _args():
    return Namespace(
        prices_json=None,
        fmp_universe=True,
        api_key="test-key",  # pragma: allowlist secret
        max_api_calls=10,
        min_market_cap=2_000_000_000,
        min_price=5.0,
        min_volume=100_000,
        max_symbols=50,
        symbols=[],
        universe_file=None,
    )


@pytest.mark.parametrize("status", [402, 403])
def test_screener_plan_restriction_is_reported_not_no_symbols(status, monkeypatch):
    real_init = mod.FMPClient.__init__

    def init(self, *a, **k):
        real_init(self, *a, **k)
        self._client.session = _Session(status)

    monkeypatch.setattr(mod.FMPClient, "__init__", init)
    with pytest.raises(ValueError) as exc:
        mod.collect_price_data(_args(), {})
    message = str(exc.value)
    assert "plan" in message and "getting-started.md#fmp-plans" in message
    assert "No symbols to process" not in message
