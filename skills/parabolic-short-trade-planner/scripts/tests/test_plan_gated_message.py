"""Plan-gated FMP refusals are named as such in the fail-closed errors (issue #707)."""

from __future__ import annotations

import argparse
from types import SimpleNamespace

import fmp_client
import pytest
import screen_parabolic


class _Refusing:
    def __init__(self, status):
        self.status = status
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        return SimpleNamespace(status_code=self.status, text="Restricted Endpoint", json=list)


@pytest.mark.parametrize("status", [402, 403])
def test_plan_gated_universe_fetch_names_the_plan_restriction(monkeypatch, status):
    monkeypatch.setattr(fmp_client.time, "sleep", lambda *_: None)
    real_init = fmp_client.FMPClient.__init__

    def init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        self.session = _Refusing(status)

    monkeypatch.setattr(fmp_client.FMPClient, "__init__", init)
    monkeypatch.setattr(fmp_client.FMPClient, "_fetch_constituents_csv", lambda self: None)
    args = argparse.Namespace(api_key="k", universe="sp500", as_of=None)
    with pytest.raises(SystemExit) as exc:
        screen_parabolic.run_live(args, "2026-11-13")
    message = str(exc.value)
    assert "plan restriction" in message
    assert "getting-started.md#fmp-plans" in message
