"""Live-mode provider failures must fail closed (issue #778 security checklist).

``FMPClient`` returns ``None`` on HTTP, JSON and transport errors. Before this
fix ``run_live`` coerced those ``None`` values to empty results, so a failed
universe fetch produced a normal "no candidates" report, and a failed earnings
calendar silently disabled the earnings-blackout exclusion.
"""

from __future__ import annotations

import json
from pathlib import Path

import fmp_client
import pytest
import screen_parabolic

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "dry_run_minimal.json"
MARKER = "MARKERKEY778"


def _fixture_bars(ticker: str = "XYZ") -> list[dict]:
    fixture = json.loads(FIXTURE_PATH.read_text())
    for sym in fixture["symbols"]:
        if sym["ticker"] == ticker:
            return sym["bars"]
    raise AssertionError(f"{ticker} missing from fixture")


class FakeClient:
    """Stand-in for FMPClient with scripted per-endpoint results."""

    universe: list[dict] | None = [{"symbol": "XYZ"}, {"symbol": "BAD"}]
    earnings: list[dict] | None = []
    prices: dict[str, dict | None] = {}

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key
        self.api_calls_made = 0

    def get_sp500_constituents(self):
        return self.universe

    def get_earnings_calendar(self, from_date, to_date):
        return self.earnings

    def get_historical_prices(self, symbol, days=365):
        self.api_calls_made += 1
        return self.prices.get(symbol)

    def get_company_profile(self, symbol):
        return {"mktCap": 5_000_000_000, "exchangeShortName": "NASDAQ"}


@pytest.fixture
def fake_client(monkeypatch):
    class Client(FakeClient):
        universe = [{"symbol": "XYZ"}, {"symbol": "BAD"}]
        earnings = []
        prices = {
            "XYZ": {"symbol": "XYZ", "historical": _fixture_bars()},
            "BAD": None,
        }

    monkeypatch.setattr(fmp_client, "FMPClient", Client)
    monkeypatch.setenv("FMP_API_KEY", MARKER)
    return Client


def _run(tmp_path, capsys):
    rc = screen_parabolic.main(["--output-dir", str(tmp_path)])
    out = capsys.readouterr()
    return rc, out


def test_universe_fetch_failure_exits_nonzero_without_report(fake_client, tmp_path, capsys):
    fake_client.universe = None

    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, capsys)

    assert exc.value.code not in (0, None)
    assert "universe" in str(exc.value.code).lower()
    assert list(tmp_path.iterdir()) == []


def test_empty_universe_exits_nonzero_without_report(fake_client, tmp_path, capsys):
    fake_client.universe = []

    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, capsys)

    assert exc.value.code not in (0, None)
    assert list(tmp_path.iterdir()) == []


def test_earnings_calendar_failure_exits_nonzero_without_report(fake_client, tmp_path, capsys):
    fake_client.earnings = None

    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, capsys)

    assert exc.value.code not in (0, None)
    assert "earnings" in str(exc.value.code).lower()
    assert list(tmp_path.iterdir()) == []


def test_non_list_earnings_payload_exits_nonzero_without_report(fake_client, tmp_path, capsys):
    # A 200 error body such as {"Error Message": ...} is not a calendar.
    fake_client.earnings = {"Error Message": "Limit Reach"}

    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, capsys)

    assert exc.value.code not in (0, None)
    assert "earnings" in str(exc.value.code).lower()
    assert list(tmp_path.iterdir()) == []


def test_real_client_passes_error_dict_through(monkeypatch):
    # Pins the real FMPClient contract the isinstance check relies on.
    client = fmp_client.FMPClient(api_key=MARKER)
    monkeypatch.setattr(client, "_rate_limited_get", lambda *a, **k: {"Error Message": "x"})

    assert not isinstance(client.get_earnings_calendar("2026-01-01", "2026-01-31"), list)


def test_budget_exhausted_before_any_price_fetch_exits_nonzero(fake_client, tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        screen_parabolic.main(["--output-dir", str(tmp_path), "--max-api-calls", "0"])

    assert exc.value.code not in (0, None)
    assert "max-api-calls" in str(exc.value.code)
    assert list(tmp_path.iterdir()) == []


def test_valid_empty_earnings_calendar_is_not_a_failure(fake_client, tmp_path, capsys):
    fake_client.earnings = []

    rc, _ = _run(tmp_path, capsys)

    assert rc == 0


def test_all_price_fetches_failing_exits_nonzero_without_report(fake_client, tmp_path, capsys):
    fake_client.prices = {"XYZ": None, "BAD": None}

    with pytest.raises(SystemExit) as exc:
        _run(tmp_path, capsys)

    assert exc.value.code not in (0, None)
    assert "price" in str(exc.value.code).lower()
    assert list(tmp_path.iterdir()) == []


def test_partial_price_failures_are_recorded_in_report(fake_client, tmp_path, capsys):
    rc, out = _run(tmp_path, capsys)

    assert rc == 0
    [json_path] = sorted(tmp_path.glob("*.json"))
    report = json.loads(json_path.read_text())
    quality = report["data_quality"]
    assert quality["universe_size"] == 2
    assert quality["symbols_evaluated"] == 1
    assert quality["price_fetch_failures"] == ["BAD"]
    assert MARKER not in out.out + out.err
    assert MARKER not in json_path.read_text()


def test_dry_run_report_has_no_live_data_quality_block(tmp_path):
    rc = screen_parabolic.main(
        [
            "--dry-run",
            "--fixture",
            str(FIXTURE_PATH),
            "--output-dir",
            str(tmp_path),
            "--as-of",
            "2026-04-30",
        ]
    )

    assert rc == 0
    [json_path] = sorted(tmp_path.glob("*.json"))
    assert "data_quality" not in json.loads(json_path.read_text())
