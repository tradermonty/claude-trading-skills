"""A quote refusal for plan reasons must not read as a market result (issue #707)."""

import json
import sys
from types import SimpleNamespace

import fmp_client
import screen_vcp
from coverage_client import CoverageFMPClient


class _Refusing:
    """Fake FMP transport: stable endpoints 402, legacy endpoints 403."""

    def __init__(self):
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        status = 402 if "/stable/" in url else 403
        return SimpleNamespace(status_code=status, text="Premium Query Parameter", json=list)


def test_plan_gated_quotes_end_with_a_plan_restriction_message(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(fmp_client.time, "sleep", lambda *_: None)
    real_init = CoverageFMPClient.__init__

    def init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        self.session = _Refusing()

    monkeypatch.setattr(CoverageFMPClient, "__init__", init)
    monkeypatch.setattr(screen_vcp, "FMPClient", CoverageFMPClient)
    symbols = [f"S{i}" for i in range(40)]
    monkeypatch.setattr(
        sys,
        "argv",
        ["screen_vcp.py", "--universe", *symbols, "--api-key", "k", "--output-dir", str(tmp_path)],
    )
    screen_vcp.main()
    out = capsys.readouterr().out
    report = json.loads(next(tmp_path.glob("vcp_screener_*.json")).read_text())
    assert report["evaluation_coverage"]["verdict"] == "not_evaluable"
    assert "plan restriction" in out
    assert "No VCP candidates found" not in out
