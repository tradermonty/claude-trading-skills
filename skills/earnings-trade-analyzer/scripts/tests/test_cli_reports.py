"""Offline CLI/report regressions for the Issue #293 coverage ratchet."""

import copy
import json
import sys
from datetime import datetime, timedelta

import analyze_earnings_trades as analyzer
import pytest
import requests


def _prices(gap, base=100, count=250):
    day = datetime(2026, 10, 2)
    rows = []
    while len(rows) < count:
        if day.weekday() < 5:
            index = len(rows)
            close = base * (1 - index * 0.001)
            rows.append(
                {
                    "date": day.date().isoformat(),
                    "open": close,
                    "high": close * 1.02,
                    "low": close * 0.98,
                    "close": close,
                    "volume": 3_000_000 if index < 20 else 1_000_000,
                }
            )
        day -= timedelta(days=1)
    rows[0]["open"] = rows[1]["close"] * (1 + gap / 100)
    return rows


@pytest.fixture
def cli(monkeypatch, tmp_path):
    monkeypatch.delenv("FMP_API_KEY", raising=False)

    def forbidden(*args, **kwargs):
        raise AssertionError("unexpected HTTP request")

    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 2, 18, 30, tzinfo=tz)

    monkeypatch.setattr(analyzer, "datetime", FixedDatetime)
    histories = {
        "ALPHA": _prices(3),
        "BETA": _prices(9),
        "LOW": _prices(3, base=20),
        "FLAT": _prices(0),
        "SHORT": _prices(3, count=49),
    }
    calendar = [
        {"symbol": symbol, "date": "2026-10-01", "time": "" if symbol == "ALPHA" else "amc"}
        for symbol in [*histories, "TINY"]
    ]
    profiles = {
        row["symbol"]: {
            "companyName": f"{row['symbol']} Inc.",
            "exchange": "NASDAQ",
            "marketCap": 5_000_000_000 if row["symbol"] == "BETA" else 1_000_000_000,
            "price": 100,
            "sector": "Technology",
            "industry": "Software",
        }
        for row in calendar
    }
    profiles["TINY"]["marketCap"] = 100_000_000
    state = {"history_calls": [], "calendar_calls": [], "init": [], "profiles": profiles}

    class Client:
        US_EXCHANGES = analyzer.FMPClient.US_EXCHANGES

        def __init__(self, api_key, max_api_calls):
            state["init"].append((api_key, max_api_calls))
            self.api_calls_made = 0
            self.max_api_calls = max_api_calls

        def get_earnings_calendar(self, start, end):
            state["calendar_calls"].append((start, end))
            self.api_calls_made += 1
            return copy.deepcopy(calendar)

        def get_company_profiles(self, symbols):
            assert set(symbols) == {row["symbol"] for row in calendar}
            self.api_calls_made += 1
            return copy.deepcopy(profiles)

        def get_historical_prices(self, symbol, days):
            state["history_calls"].append((symbol, days))
            self.api_calls_made += 1
            return copy.deepcopy(histories[symbol])

        def get_api_stats(self):
            return {
                "api_calls_made": self.api_calls_made,
                "max_api_calls": self.max_api_calls,
                "budget_remaining": self.max_api_calls - self.api_calls_made,
                "rate_limit_reached": False,
            }

    monkeypatch.setattr(analyzer, "FMPClient", Client)
    output = tmp_path / "reports"

    def run(*options):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "analyze_earnings_trades.py",
                "--api-key",
                "offline",
                "--as-of",
                "2026-10-02",
                "--lookback-days",
                "3",
                "--min-market-cap",
                "500000000",
                "--min-gap",
                "2",
                "--output-dir",
                str(output),
                *options,
            ],
        )
        analyzer.main()
        files = sorted(output.iterdir())
        assert [path.suffix for path in files] == [".json", ".md"]
        assert all("2026-10-02_183000" in path.name for path in files)
        return json.loads(files[0].read_text()), files[1].read_text()

    return run, state, output


def test_cli_top_limit_preserves_full_summary_and_real_reports(cli, capsys):
    run, state, _ = cli
    report, markdown = run("--top", "1")
    assert report["schema_version"] == "1.0"
    assert [row["symbol"] for row in report["results"]] == ["BETA"]
    assert report["results"][0]["gap_pct"] == pytest.approx(9)
    assert report["results"][0]["current_price"] == 100
    assert report["summary"]["total"] == 3
    assert report["sector_distribution"] == {"Technology": 3}
    metadata = report["metadata"]
    assert metadata["generated_at"] == "2026-10-02T18:30:00"
    assert metadata["lookback_days"] == 3
    assert metadata["min_market_cap"] == 500_000_000
    assert metadata["min_gap"] == 2
    assert metadata["entry_filter_applied"] is False
    assert metadata["timing_unknown_count"] == 1
    assert metadata["timing_candidates_total"] == 5
    assert state["calendar_calls"] == [("2026-09-29", "2026-10-02")]
    assert state["init"] == [("offline", 200)]
    assert state["history_calls"] == [
        (symbol, 250) for symbol in ["ALPHA", "BETA", "LOW", "FLAT", "SHORT"]
    ]
    assert "Showing top 1 of 3 candidates" in markdown
    assert "**Timing unknown:** 1 of 5" in markdown
    assert "| 1 | **BETA** |" in markdown
    streams = capsys.readouterr()
    assert streams.out == ""
    assert "SKIP (insufficient data: 49 days)" in streams.err
    assert "SKIP (gap 0.0% < min 2.0%)" in streams.err


def test_cli_entry_filter_removes_low_price_and_updates_summary(cli):
    run, _, _ = cli
    report, markdown = run("--apply-entry-filter")
    assert [row["symbol"] for row in report["results"]] == ["BETA", "ALPHA"]
    assert report["results"][0]["composite_score"] > report["results"][1]["composite_score"]
    assert report["results"][1]["earnings_timing"] == "unknown"
    assert report["summary"]["total"] == 2
    assert report["metadata"]["total_screened"] == 2
    assert report["metadata"]["entry_filter_applied"] is True
    assert "| 2 | **ALPHA** |" in markdown
    assert "LOW" not in markdown


def test_cli_budget_trims_to_largest_candidate_before_analysis(cli, capsys):
    run, state, _ = cli
    report, _ = run("--max-api-calls", "3")
    assert state["init"] == [("offline", 3)]
    assert state["history_calls"] == [("BETA", 250)]
    assert [row["symbol"] for row in report["results"]] == ["BETA"]
    assert report["metadata"]["api_stats"]["api_calls_made"] == 3
    assert report["metadata"]["api_stats"]["budget_remaining"] == 0
    assert report["metadata"]["timing_candidates_total"] == 1
    assert report["metadata"]["timing_unknown_count"] == 0
    assert "Trimmed to 1 candidates (by market cap)." in capsys.readouterr().err


def test_cli_filtered_universe_exits_without_report_artifacts(cli, capsys):
    run, state, output = cli
    for profile in state["profiles"].values():
        profile["marketCap"] = 100_000_000
    with pytest.raises(SystemExit) as failure:
        run()
    assert failure.value.code == 0
    assert "ZERO_RESULT_REASON=all_below_market_cap_floor" in capsys.readouterr().err
    assert not state["history_calls"]
    assert not output.exists()
