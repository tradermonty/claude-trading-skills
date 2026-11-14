"""Golden clean-path reports (issue #655).

The fixture has 83 bars per index, so ``detect_power_trend`` runs its full
calculation instead of the "Insufficient data" path. The expected JSON and
Markdown were produced once by ``main()``; on origin/main the same fixture
differs only by the new ``data_gap`` / ``data_quality`` keys (see the PR body).
"""

import json
from datetime import datetime
from pathlib import Path

import ftd_detector
import pytest
import requests

FIXTURES = Path(__file__).parent / "fixtures"
FIXED_NOW = datetime(2026, 11, 13, 9, 30, 0)


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FIXED_NOW


class FixtureClient:
    def __init__(self, data):
        self.data = data

    def get_historical_prices(self, symbol, days):
        return {"historical": self.data["histories"][symbol]}

    def get_quote(self, symbol):
        return self.data["quotes"][symbol]

    def get_api_stats(self):
        return {"api_calls_made": 4, "cache_entries": 0}


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("golden fixtures must not make network requests")

    monkeypatch.setattr(requests.sessions.Session, "request", unexpected_request)


def run_golden(monkeypatch, tmp_path):
    data = json.loads((FIXTURES / "golden_clean_history.json").read_text(encoding="utf-8"))
    client = FixtureClient(data)
    monkeypatch.setattr(ftd_detector, "FMPClient", lambda api_key: client)
    monkeypatch.setattr(ftd_detector, "datetime", _FixedDatetime)
    monkeypatch.setattr("sys.argv", ["ftd_detector.py", "--output-dir", str(tmp_path)])
    ftd_detector.main()
    stem = "ftd_detector_2026-11-13_093000"
    report = json.loads((tmp_path / f"{stem}.json").read_text(encoding="utf-8"))
    markdown = (tmp_path / f"{stem}.md").read_text(encoding="utf-8")
    return report, markdown


def test_fixture_is_long_enough_for_power_trend():
    data = json.loads((FIXTURES / "golden_clean_history.json").read_text(encoding="utf-8"))
    for history in data["histories"].values():
        assert len(history) >= 55


def test_clean_json_matches_golden(monkeypatch, tmp_path):
    report, _ = run_golden(monkeypatch, tmp_path)
    expected = json.loads((FIXTURES / "golden_expected.json").read_text(encoding="utf-8"))
    assert report == expected
    assert report["data_gap"] is False
    assert report["power_trend"]["ema_21"] is not None  # full power-trend path ran


def test_clean_markdown_matches_golden(monkeypatch, tmp_path):
    _, markdown = run_golden(monkeypatch, tmp_path)
    expected = (FIXTURES / "golden_expected.md").read_text(encoding="utf-8")
    assert markdown == expected
    assert "Data quality" not in markdown
