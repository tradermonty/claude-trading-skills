"""Network/CLI tests for fetch_breadth_csv.py (all HTTP mocked, no network)."""

import io
import json
import sys
import urllib.error

import fetch_breadth_csv as fbc
import pytest
from fetch_breadth_csv import BreadthData, SectorData, UptrendData


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def install_fake_urlopen(monkeypatch, text, calls=None):
    def fake_urlopen(req, timeout=None):
        if calls is not None:
            calls.append((req, timeout))
        return FakeResponse(text.encode("utf-8"))

    monkeypatch.setattr(fbc.urllib.request, "urlopen", fake_urlopen)


class TestFetchCsv:
    def test_parses_rows_and_sends_user_agent(self, monkeypatch):
        calls = []
        install_fake_urlopen(monkeypatch, "a,b\n1,2\n3,4\n", calls)
        rows = fbc.fetch_csv("https://example.invalid/x.csv", timeout=7)
        assert rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]
        req, timeout = calls[0]
        assert req.full_url == "https://example.invalid/x.csv"
        assert req.get_header("User-agent") == "breadth-csv-fetcher/1.0"
        assert timeout == 7

    def test_url_error_propagates(self, monkeypatch):
        def boom(req, timeout=None):
            raise urllib.error.URLError("offline")

        monkeypatch.setattr(fbc.urllib.request, "urlopen", boom)
        with pytest.raises(urllib.error.URLError):
            fbc.fetch_csv("https://example.invalid/x.csv")


class TestFetchBreadthData:
    def test_standard_columns(self, monkeypatch):
        csv_text = (
            "Date,S&P500_Price,Breadth_Index_Raw,Breadth_Index_200MA,Breadth_Index_8MA,"
            "Breadth_200MA_Trend\n"
            "2026-02-12,6800.5,0.6,0.62,0.66,UPTREND\n"
            "2026-02-13,6828.3,0.65,0.6226,0.6756,\n"
        )
        install_fake_urlopen(monkeypatch, csv_text)
        rows = fbc.fetch_breadth_data()
        assert len(rows) == 2
        assert rows[0] == BreadthData("2026-02-12", 6800.5, 0.6, 0.62, 0.66, "UPTREND")
        assert rows[1].trend is None  # blank trend normalized to None

    def test_alternate_column_names(self, monkeypatch):
        csv_text = "Date,SP500_Price,Breadth_200MA,Breadth_8MA,Trend\n2026-02-13,1.5,0.5,0.4,DOWN\n"
        install_fake_urlopen(monkeypatch, csv_text)
        (row,) = fbc.fetch_breadth_data()
        assert (row.sp500_price, row.breadth_200ma, row.breadth_8ma) == (1.5, 0.5, 0.4)
        assert row.breadth_raw is None
        assert row.trend == "DOWN"

    def test_malformed_row_skipped(self, monkeypatch):
        csv_text = (
            "Date,Breadth_Index_200MA,Breadth_Index_8MA\n"
            "2026-02-12,not-a-number,0.5\n"
            "2026-02-13,0.6,0.7\n"
        )
        install_fake_urlopen(monkeypatch, csv_text)
        rows = fbc.fetch_breadth_data()
        assert [r.date for r in rows] == ["2026-02-13"]


class TestFetchUptrendData:
    CSV = (
        "date,worksheet,ratio,ma_10,slope,trend\n"
        "2026-02-12,all,0.31,0.30,0.004,up\n"
        "2026-02-12,Technology,0.5,0.5,0.0,up\n"
        "2026-02-13,ALL,0.33,0.3265,0.0055,\n"
        "2026-02-14,all,bad,0.3,0.0,up\n"
    )

    def test_filters_by_worksheet_case_insensitive_and_skips_bad(self, monkeypatch):
        install_fake_urlopen(monkeypatch, self.CSV)
        rows = fbc.fetch_uptrend_data()
        assert [r.date for r in rows] == ["2026-02-12", "2026-02-13"]
        assert rows[1] == UptrendData("2026-02-13", 0.33, 0.3265, 0.0055, None)

    def test_other_worksheet(self, monkeypatch):
        install_fake_urlopen(monkeypatch, self.CSV)
        rows = fbc.fetch_uptrend_data(worksheet="technology")
        assert [r.ratio for r in rows] == [0.5]


class TestFetchSectorData:
    def test_parses_and_normalizes_blanks(self, monkeypatch):
        csv_text = (
            "Sector,Ratio,10MA,Trend,Slope,Status\n"
            "Energy,0.606,0.55,up,0.01,overbought\n"
            "Utilities,,0.4,,NA,\n"
            "Broken,xx,0.4,up,0.1,\n"
        )
        install_fake_urlopen(monkeypatch, csv_text)
        rows = fbc.fetch_sector_data()
        assert rows == [
            SectorData("Energy", 0.606, 0.55, "up", 0.01, "overbought"),
            SectorData("Utilities", None, 0.4, None, None, None),
        ]


class TestClassifyAndRange:
    def test_classify_value_below_all_thresholds_uses_last_label(self):
        thresholds = [(50, "high"), (20, "mid"), (10, "low")]
        assert fbc.classify_value(5, thresholds) == "low"
        assert fbc.classify_value(20, thresholds) == "mid"

    def test_threshold_range_descriptions(self):
        t = fbc.BREADTH_200MA_THRESHOLDS
        top, second = t[0][0], t[1][0]
        assert fbc._threshold_range(top + 5, t) == f">={top}%"
        assert fbc._threshold_range(second, t) == f"{second}-{top}%"
        assert fbc._threshold_range(-1, t) == f"<{t[-1][0]}%"


class TestAnalyzeErrors:
    def _b(self, **kw):
        base = dict(
            date="2026-02-13",
            sp500_price=1.0,
            breadth_raw=0.5,
            breadth_200ma=0.6,
            breadth_8ma=0.7,
            trend="UPTREND",
        )
        base.update(kw)
        return [BreadthData(**base)]

    def _u(self, **kw):
        base = dict(date="2026-02-13", ratio=0.3, ma_10=0.3, slope=0.01, trend="up")
        base.update(kw)
        return [UptrendData(**base)]

    def test_missing_breadth_ma(self):
        with pytest.raises(ValueError, match="Missing breadth MA values for 2026-02-13"):
            fbc.analyze(self._b(breadth_200ma=None), self._u(), [])
        with pytest.raises(ValueError, match="Missing breadth MA values"):
            fbc.analyze(self._b(breadth_8ma=None), self._u(), [])

    def test_missing_uptrend_ratio(self):
        with pytest.raises(ValueError, match="Missing uptrend ratio for 2026-02-13"):
            fbc.analyze(self._b(), self._u(ratio=None), [])

    def test_missing_optional_uptrend_fields_default(self):
        result = fbc.analyze(self._b(), self._u(ma_10=None, slope=None, trend=None), [])
        assert result.uptrend_ma10 == 0.0
        assert result.uptrend_slope == 0.0
        assert result.uptrend_trend == "UNKNOWN"
        assert result.uptrend_color == "UNKNOWN"

    def test_sector_with_missing_ratio(self):
        sectors = [SectorData("Utilities", None, None, None, None, None)]
        result = fbc.analyze(self._b(), self._u(), sectors)
        assert result.sectors == [
            {"sector": "Utilities", "ratio": None, "trend": None, "status": None}
        ]


class TestFormatHumanSectors:
    def _result(self, sectors):
        return fbc.analyze(
            [BreadthData("2026-02-13", 1.0, 0.5, 0.6, 0.7, "UPTREND")],
            [UptrendData("2026-02-13", 0.3, 0.3, 0.01, "up")],
            sectors,
        )

    def test_blank_status_and_trend_do_not_crash(self):
        # Regression: real CSV rows with blank Status/Trend become None, and
        # format_human used to call .lower() on None.
        sectors = [SectorData("Utilities", 0.35, 0.4, None, 0.0, None)]
        text = fbc.format_human(self._result(sectors))
        assert "--- Sector Summary ---" in text
        assert "Overbought" not in text

    def test_all_sector_groups_rendered(self):
        sectors = [
            SectorData("Energy", 0.606, 0.55, "up", 0.01, "overbought"),
            SectorData("Tech", 0.10, 0.2, "down", -0.01, "oversold"),
            SectorData("Health", 0.40, 0.4, "uptrend", 0.0, None),
            SectorData("Staples", 0.30, 0.3, "Downtrend", 0.0, None),
            SectorData("Mystery", None, None, "up", None, "Overbought"),
        ]
        text = fbc.format_human(self._result(sectors))
        assert "Overbought: Energy (60.6%), Mystery" in text
        assert "Oversold: Tech (10.0%)" in text
        assert "Uptrend: Energy (60.6%), Health (40.0%), Mystery" in text
        assert "Downtrend: Tech (10.0%), Staples (30.0%)" in text

    def test_dead_cross_wording(self):
        result = fbc.analyze(
            [BreadthData("2026-02-13", 1.0, 0.5, 0.7, 0.6, "DOWNTREND")],
            [UptrendData("2026-02-13", 0.3, 0.3, 0.01, "down")],
            [],
        )
        text = fbc.format_human(result)
        assert "8MA BELOW -- DEAD CROSS" in text
        assert "-10.00pt" in text
        assert "--- Sector Summary ---" not in text


class TestMain:
    def _patch_fetchers(self, monkeypatch, breadth=None, uptrend=None, sectors=None):
        monkeypatch.setattr(
            fbc,
            "fetch_breadth_data",
            lambda: (
                breadth
                if breadth is not None
                else [BreadthData("2026-02-13", 1.0, 0.5, 0.6226, 0.6756, "UPTREND")]
            ),
        )
        monkeypatch.setattr(
            fbc,
            "fetch_uptrend_data",
            lambda: (
                uptrend
                if uptrend is not None
                else [UptrendData("2026-02-13", 0.3303, 0.3265, 0.0055, "up")]
            ),
        )
        monkeypatch.setattr(fbc, "fetch_sector_data", lambda: sectors or [])

    def test_human_output(self, monkeypatch, capsys):
        self._patch_fetchers(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["prog"])
        fbc.main()
        out = capsys.readouterr().out
        assert "Breadth Data (CSV) - 2026-02-13" in out
        assert "200-Day MA: 62.26%" in out

    def test_json_output(self, monkeypatch, capsys):
        self._patch_fetchers(monkeypatch)
        monkeypatch.setattr(sys, "argv", ["prog", "--json", "--days", "3"])
        fbc.main()
        data = json.loads(capsys.readouterr().out)
        assert data["breadth_200ma"] == 62.26
        assert data["uptrend_color"] == "GREEN"
        assert data["dead_cross"] is False

    def test_url_error_exits_1(self, monkeypatch, capsys):
        def boom():
            raise urllib.error.URLError("dns failure")

        monkeypatch.setattr(fbc, "fetch_breadth_data", boom)
        monkeypatch.setattr(sys, "argv", ["prog"])
        with pytest.raises(SystemExit) as exc:
            fbc.main()
        assert exc.value.code == 1
        assert "ERROR: Failed to fetch CSV data" in capsys.readouterr().err

    def test_value_error_exits_1(self, monkeypatch, capsys):
        self._patch_fetchers(monkeypatch, breadth=[], uptrend=None)
        monkeypatch.setattr(fbc, "fetch_breadth_data", lambda: [])
        monkeypatch.setattr(sys, "argv", ["prog"])
        with pytest.raises(SystemExit) as exc:
            fbc.main()
        assert exc.value.code == 1
        assert "No breadth data available" in capsys.readouterr().err
