"""Behavior tests for analyze_symbol, report generation and main() (fetch layer mocked)."""

import json
import sys

import analyze_downtrends as adt
import pandas as pd
import pytest

# Peak at index 4 (110), trough at index 8 (90) with window=2.
CLOSES = [100, 102, 104, 108, 110, 105, 100, 95, 90, 92, 95, 98, 100]


def make_prices(closes):
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=len(closes), freq="D"),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1000] * len(closes),
        }
    )


def run_analyze(symbol="AAA", market_cap=5e9, min_depth=5.0, window=2):
    return adt.analyze_symbol(
        "k", symbol, "Energy", market_cap, "2024-01-01", "2024-02-01", window, window, min_depth
    )


class TestAnalyzeSymbol:
    def test_detects_downtrend_and_attaches_metadata(self, monkeypatch):
        monkeypatch.setattr(adt, "fetch_historical_prices", lambda *a, **k: make_prices(CLOSES))
        result = run_analyze()
        assert len(result) == 1
        dt = result[0]
        assert dt["duration_days"] == 4
        assert dt["depth_pct"] == pytest.approx(-18.18)
        assert dt["peak_date"] == "2024-01-05"
        assert dt["trough_date"] == "2024-01-09"
        assert dt["symbol"] == "AAA"
        assert dt["sector"] == "Energy"
        assert dt["market_cap_tier"] == "Mid"

    def test_empty_prices_returns_empty(self, monkeypatch):
        monkeypatch.setattr(adt, "fetch_historical_prices", lambda *a, **k: pd.DataFrame())
        assert run_analyze() == []

    def test_too_few_rows_returns_empty(self, monkeypatch):
        monkeypatch.setattr(adt, "fetch_historical_prices", lambda *a, **k: make_prices([1, 2, 3]))
        assert run_analyze() == []

    def test_flat_series_yields_no_downtrend(self, monkeypatch):
        # Pinned: on a flat series every point is both window max and min, but
        # no downtrend passes the depth filter.
        monkeypatch.setattr(
            adt, "fetch_historical_prices", lambda *a, **k: make_prices([100.0] * 15)
        )
        assert run_analyze() == []

    def test_monotonic_rise_has_no_downtrend(self, monkeypatch):
        monkeypatch.setattr(
            adt, "fetch_historical_prices", lambda *a, **k: make_prices(list(range(1, 16)))
        )
        assert run_analyze() == []

    def test_min_depth_filters_shallow_move(self, monkeypatch):
        monkeypatch.setattr(adt, "fetch_historical_prices", lambda *a, **k: make_prices(CLOSES))
        assert run_analyze(min_depth=25.0) == []

    def test_none_market_cap_is_unknown_tier(self, monkeypatch):
        monkeypatch.setattr(adt, "fetch_historical_prices", lambda *a, **k: make_prices(CLOSES))
        assert run_analyze(market_cap=None)[0]["market_cap_tier"] == "Unknown"


class TestFindDowntrendsEdges:
    def test_peak_without_following_trough_skipped(self):
        assert adt.find_downtrends(make_prices(CLOSES), [4], [2]) == []

    def test_no_trough_before_next_peak_skipped(self):
        # Next peak at 6 precedes the only later trough at 8.
        assert adt.find_downtrends(make_prices(CLOSES), [4, 6], [8]) == []

    def test_deepest_trough_chosen(self):
        result = adt.find_downtrends(make_prices(CLOSES), [4], [6, 8])
        assert len(result) == 1
        assert result[0]["trough_idx"] == 8
        assert result[0]["trough_price"] == 90.0


def sample_result(sector_filter=None, by_market_cap=None, by_sector=None):
    return {
        "analysis_date": "2026-01-02T03:04:05Z",
        "parameters": {"lookback_years": 3, "sector_filter": sector_filter},
        "summary": {
            "total_downtrends": 1234,
            "median_duration_days": 10,
            "mean_duration_days": 12.5,
            "p25_duration_days": 5,
            "p75_duration_days": 15,
            "p90_duration_days": 30,
        },
        "by_market_cap": by_market_cap or {},
        "by_sector": by_sector or {},
    }


class TestMarkdownReport:
    def test_full_report_contents_and_ordering(self, tmp_path):
        out = tmp_path / "r.md"
        adt.generate_markdown_report(
            sample_result(
                sector_filter="Energy",
                by_market_cap={
                    "Small": {"count": 1, "median_days": 9, "mean_days": 9.0},
                    "Mega": {"count": 2, "median_days": 7, "mean_days": 7.5},
                },
                by_sector={
                    "Tech": {"count": 3, "median_days": 20, "mean_days": 21.0},
                    "Utilities": {"count": 4, "median_days": 8, "mean_days": 8.5},
                },
            ),
            out,
        )
        text = out.read_text(encoding="utf-8")
        assert "**Date**: 2026-01-02" in text
        assert "**Lookback**: 3 years" in text
        assert "**Sector**: Energy" in text
        assert "| Total Downtrends | 1,234 |" in text
        assert "| 90th Percentile | 30 days |" in text
        # Tier order fixed Mega -> Small regardless of dict order.
        assert text.index("| Mega |") < text.index("| Small |")
        assert "| Mega | 2 | 7 days | 7.5 days |" in text
        # Sectors sorted by median ascending.
        assert text.index("| Utilities |") < text.index("| Tech |")
        assert "## Key Insights" in text

    def test_minimal_report_omits_optional_sections(self, tmp_path):
        out = tmp_path / "r.md"
        adt.generate_markdown_report(sample_result(), out)
        text = out.read_text(encoding="utf-8")
        assert "**Sector**" not in text
        assert "## By Market Cap Tier" not in text
        assert "## By Sector" not in text
        assert "## Summary Statistics" in text

    def test_unknown_tier_not_listed_pinned(self, tmp_path):
        # Pinned: tiers outside Mega/Large/Mid/Small (e.g. "Unknown") are dropped
        # from the market cap table although the section header is emitted.
        out = tmp_path / "r.md"
        adt.generate_markdown_report(
            sample_result(
                by_market_cap={"Unknown": {"count": 1, "median_days": 1, "mean_days": 1}}
            ),
            out,
        )
        text = out.read_text(encoding="utf-8")
        assert "## By Market Cap Tier" in text
        assert "| Unknown |" not in text


class TestGetApiKey:
    def test_argument_wins(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "envkey")  # pragma: allowlist secret
        assert adt.get_api_key("argkey") == "argkey"  # pragma: allowlist secret

    def test_env_fallback(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "envkey")  # pragma: allowlist secret
        assert adt.get_api_key(None) == "envkey"  # pragma: allowlist secret

    def test_missing_key_exits_with_message(self, monkeypatch, capsys):
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc:
            adt.get_api_key(None)
        assert exc.value.code == 1
        assert "FMP API key required" in capsys.readouterr().err


STOCKS = [
    {"symbol": "AAA", "sector": "Energy", "marketCap": 5e9},
    {"symbol": "BBB", "sector": "Technology", "marketCap": 3e11},
    {"symbol": "CCC", "sector": "Energy", "marketCap": 5e8},
]


class TestMain:
    def _run(self, monkeypatch, tmp_path, extra=()):
        argv = [
            "analyze_downtrends.py",
            "--api-key",
            "fake",  # pragma: allowlist secret
            "--output-dir",
            str(tmp_path / "out"),
            "--peak-window",
            "2",
            "--trough-window",
            "2",
            *extra,
        ]
        monkeypatch.setattr(sys, "argv", argv)
        adt.main()

    def test_end_to_end_writes_json_and_markdown(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(adt, "fetch_stock_list", lambda key, sector=None: STOCKS)
        monkeypatch.setattr(adt, "fetch_historical_prices", lambda *a, **k: make_prices(CLOSES))
        self._run(monkeypatch, tmp_path)
        out = tmp_path / "out"
        jsons = list(out.glob("downtrend_analysis_*.json"))
        mds = list(out.glob("downtrend_analysis_*.md"))
        assert len(jsons) == 1 and len(mds) == 1
        data = json.loads(jsons[0].read_text())
        assert data["schema_version"] == "1.0"
        assert data["parameters"]["peak_window"] == 2
        assert data["summary"]["total_downtrends"] == 3
        assert data["summary"]["median_duration_days"] == 4
        assert data["by_sector"]["Energy"]["count"] == 2
        assert data["by_market_cap"]["Mega"]["count"] == 1
        assert {d["symbol"] for d in data["downtrends"]} == {"AAA", "BBB", "CCC"}
        assert "| Total Downtrends | 3 |" in mds[0].read_text()
        stdout = capsys.readouterr().out
        assert "Analyzing 3 stocks..." in stdout
        assert "Found 3 downtrend periods" in stdout

    def test_max_stocks_limits_universe(self, monkeypatch, tmp_path):
        monkeypatch.setattr(adt, "fetch_stock_list", lambda key, sector=None: STOCKS)
        monkeypatch.setattr(adt, "fetch_historical_prices", lambda *a, **k: make_prices(CLOSES))
        self._run(monkeypatch, tmp_path, ["--max-stocks", "1"])
        data = json.loads(next((tmp_path / "out").glob("*.json")).read_text())
        assert [d["symbol"] for d in data["downtrends"]] == ["AAA"]

    def test_sector_passed_to_fetch(self, monkeypatch, tmp_path):
        seen = {}

        def fake_list(key, sector=None):
            seen["sector"] = sector
            return STOCKS[:1]

        monkeypatch.setattr(adt, "fetch_stock_list", fake_list)
        monkeypatch.setattr(adt, "fetch_historical_prices", lambda *a, **k: make_prices(CLOSES))
        self._run(monkeypatch, tmp_path, ["--sector", "Energy"])
        assert seen["sector"] == "Energy"
        md = next((tmp_path / "out").glob("*.md")).read_text()
        assert "**Sector**: Energy" in md

    def test_empty_stock_list_exits_1(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(adt, "fetch_stock_list", lambda key, sector=None: [])
        with pytest.raises(SystemExit) as exc:
            self._run(monkeypatch, tmp_path)
        assert exc.value.code == 1
        assert "No stocks found" in capsys.readouterr().err

    def test_no_downtrends_still_writes_zero_summary(self, monkeypatch, tmp_path):
        monkeypatch.setattr(adt, "fetch_stock_list", lambda key, sector=None: STOCKS)
        monkeypatch.setattr(adt, "fetch_historical_prices", lambda *a, **k: pd.DataFrame())
        self._run(monkeypatch, tmp_path)
        data = json.loads(next((tmp_path / "out").glob("*.json")).read_text())
        assert data["summary"]["total_downtrends"] == 0
        assert data["downtrends"] == []

    def test_missing_api_key_exits(self, monkeypatch, capsys):
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        monkeypatch.setattr(sys, "argv", ["analyze_downtrends.py"])
        with pytest.raises(SystemExit) as exc:
            adt.main()
        assert exc.value.code == 1
        assert "FMP API key required" in capsys.readouterr().err
