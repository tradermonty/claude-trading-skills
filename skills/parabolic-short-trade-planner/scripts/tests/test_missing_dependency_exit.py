"""Alpaca paths without ``requests`` exit 2 with a requirements.txt hint (#497)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import generate_pre_market_plan as g2
import monitor_intraday_trigger as mit
import pytest

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def no_requests(monkeypatch):
    """Make ``import requests`` fail and force the Alpaca adapters to re-import."""
    monkeypatch.setitem(sys.modules, "requests", None)
    for name in ("alpaca_inventory_adapter", "alpaca_market_data_adapter"):
        monkeypatch.delitem(sys.modules, name, raising=False)


def test_generate_plan_alpaca_broker_without_requests_exits_2(no_requests, capsys, tmp_path):
    phase1 = tmp_path / "phase1.json"
    phase1.write_text(
        json.dumps({"schema_version": "1.0", "as_of": "2026-04-30", "candidates": []}),
        encoding="utf-8",
    )
    rc = g2.main(
        [
            "--candidates-json",
            str(phase1),
            "--broker",
            "alpaca",
            "--output-dir",
            str(tmp_path),
            "--ssr-state-dir",
            str(tmp_path / "ssr"),
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR: requests library not found" in captured.err
    assert "requirements.txt" in captured.err
    assert "--broker none" in captured.err
    assert captured.out == ""


def test_monitor_alpaca_source_without_requests_exits_2(no_requests, capsys, tmp_path):
    rc = mit.main(
        [
            "--plans-json",
            str(FIXTURES / "phase2_plan_smoke.json"),
            "--bars-source",
            "alpaca",
            "--state-dir",
            str(tmp_path / "state"),
            "--output-dir",
            str(tmp_path),
            "--now-et",
            "2026-04-30T10:00:00-04:00",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR: requests library not found" in captured.err
    assert "requirements.txt" in captured.err
    assert "--bars-source fixture" in captured.err
