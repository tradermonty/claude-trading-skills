"""--fmp-universe on a plan without the company screener must say so (issue #707)."""

import sys
from argparse import Namespace
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

import screen_exhaustion_hammer as mod  # noqa: E402


class _Response:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text

    def json(self):
        return []


class _Session:
    def __init__(self, status_code, text="Restricted Endpoint"):
        self.status_code = status_code
        self.text = text
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        return _Response(self.status_code, self.text)


def _args():
    return Namespace(
        prices_json=None,
        profiles_json=None,
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
    _check(status, "Restricted Endpoint", monkeypatch, plan=True)


def test_invalid_key_403_is_not_called_a_plan_restriction(monkeypatch):
    _check(403, "Invalid API KEY.", monkeypatch, plan=False)


def _check(status, body, monkeypatch, plan):
    real_init = mod.FMPClient.__init__

    def init(self, *a, **k):
        real_init(self, *a, **k)
        self._client.session = _Session(status, body)

    monkeypatch.setattr(mod.FMPClient, "__init__", init)
    with pytest.raises(ValueError) as exc:
        mod.collect_price_data(_args(), {})
    message = str(exc.value)
    assert "No symbols to process" not in message
    if plan:
        assert "plan does not include" in message and "getting-started.md#fmp-plans" in message
    else:
        assert "plan does not include" not in message and "API key" in message
