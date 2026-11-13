"""Issue #655: data gaps reach the JSON, console and Markdown as "Unavailable"."""

import copy
import json
import math

import ftd_detector
import pytest
import requests
from helpers import assign_session_dates, make_long_ftd_history, make_rally_history
from post_ftd_monitor import assess_post_ftd_health
from rally_tracker import get_market_state
from report_generator import generate_markdown_report


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("FTD data-gap fixtures must not make network requests")

    monkeypatch.setattr(requests.sessions.Session, "request", unexpected_request)


class FixtureClient:
    def __init__(self, histories, quotes):
        self.histories = histories
        self.quotes = quotes

    def get_historical_prices(self, symbol, days):
        return self.histories[symbol]

    def get_quote(self, symbol):
        return self.quotes[symbol]

    def get_api_stats(self):
        return {"api_calls_made": 4, "cache_entries": 0}


def run_main(monkeypatch, tmp_path, sp_chrono, nq_chrono, quotes=None):
    histories = {
        "^GSPC": {"historical": list(reversed(sp_chrono))},
        "QQQ": {"historical": list(reversed(nq_chrono))},
    }
    client = FixtureClient(histories, quotes or {"^GSPC": None, "QQQ": None})
    monkeypatch.setattr(ftd_detector, "FMPClient", lambda api_key: client)
    monkeypatch.setattr("sys.argv", ["ftd_detector.py", "--output-dir", str(tmp_path)])
    ftd_detector.main()
    (json_path,) = tmp_path.glob("ftd_detector_*.json")
    (md_path,) = tmp_path.glob("ftd_detector_*.md")
    return json.loads(json_path.read_text()), md_path.read_text()


def dated(*, peak=100, confirmed=True):
    bars, _, _, _ = make_rally_history(
        peak=peak, rally_days=8, ftd_day=5 if confirmed else None, ftd_gain_pct=2.1
    )
    return assign_session_dates(bars)


def gap(bars, idx, field="close"):
    out = copy.deepcopy(bars)
    out[idx][field] = math.nan
    return out


NO_NONE_FORMATTING = ("None/100", "$None", "None%", "Unavailable (None)")


def assert_no_none(text):
    for needle in NO_NONE_FORMATTING:
        assert needle not in text


def test_both_indices_gapped_end_to_end(monkeypatch, tmp_path, capsys):
    report, markdown = run_main(
        monkeypatch, tmp_path, gap(dated(), 12), gap(dated(peak=400), 13, "volume")
    )
    console = capsys.readouterr().out

    assert report["data_gap"] is True
    assert report["market_state"]["combined_state"] == "NO_SIGNAL"
    assert report["quality_score"]["total_score"] == 0
    assert report["quality_score"]["signal"] == "Unavailable: data gap"
    for key in ("sp500", "nasdaq"):
        assert report[key]["error"].startswith("Data gap:")
        assert report[key]["data_quality"]["bad_bars"] == 1
        assert report["data_quality"][key]["bad_bars"] == 1
    # the newest-first fallback for index_prices still reads a valid close
    assert report["metadata"]["index_prices"]["sp500"] == dated()[-1]["close"]

    assert "Quality Score: 0/100" in console
    assert_no_none(console)

    assert "**0/100**" in markdown
    assert "Data gap: confirmation unavailable" in markdown
    assert "do not increase exposure on this signal" in markdown
    assert "normal market conditions" not in markdown
    assert "Cautious exposure increase" not in markdown
    assert "**State unavailable (data gap)**" in markdown
    assert "No Signal (Uptrend)" not in markdown
    assert "**Data quality:**" in markdown
    assert_no_none(markdown)
    assert "Combined State: NO_SIGNAL (data gap — state unavailable)" in console


def test_sp500_gapped_nasdaq_confirmed_end_to_end(monkeypatch, tmp_path, capsys):
    report, markdown = run_main(monkeypatch, tmp_path, gap(dated(), 12), dated(peak=400))
    console = capsys.readouterr().out
    assert report["data_gap"] is True
    assert report["market_state"]["combined_state"] == "NO_SIGNAL"
    assert report["market_state"]["ftd_index"] is None
    assert report["market_state"]["dual_confirmation"] is False
    assert report["sp500"]["state"] == "NO_SIGNAL"
    assert report["nasdaq"]["state"] == "FTD_CONFIRMED"  # kept for transparency
    assert report["post_ftd_distribution"] == {} and report["ftd_invalidation"] == {}
    assert report["market_state"]["data_gap"] is True
    assert report["sp500"]["error"].startswith("Data gap:")
    assert report["quality_score"]["total_score"] == 0
    assert report["quality_score"]["signal"] == "Unavailable: data gap"
    assert report["quality_score"]["data_gap"] is True
    assert "**Data quality:**" in markdown
    assert "S&P 500: Data gap:" in markdown
    assert "**State unavailable (data gap)**" in markdown
    assert "FTD Confirmed" not in markdown.split("## Index Status")[0]
    assert "| **FTD Index** |" not in markdown
    assert "Data gap: confirmation unavailable" in markdown
    assert "Aggressively increase" not in markdown
    assert_no_none(markdown)
    assert "Combined State: NO_SIGNAL (data gap — state unavailable)" in console
    assert "Combined:      NO_SIGNAL (data gap — state unavailable)" in console


def test_short_history_power_trend_reports_insufficient_not_gap(monkeypatch, tmp_path):
    """Under 50 bars the power trend never runs, so a bad old bar is not a power-trend gap."""
    bars = dated()  # 24 bars
    bars[0]["close"] = math.nan  # inside the (24-session) window -> index gap
    report, markdown = run_main(monkeypatch, tmp_path, bars, dated(peak=400, confirmed=False))
    assert report["data_quality"]["sp500"]["power_trend_bad_bars"] == 0
    assert report["power_trend"]["reason"] == "Insufficient S&P 500 data"
    assert "power-trend input" not in markdown
    assert "power trend unavailable" not in markdown


def test_clean_run_reports_no_gap_and_no_data_quality_line(monkeypatch, tmp_path):
    report, markdown = run_main(monkeypatch, tmp_path, dated(), dated(peak=400))
    assert report["data_gap"] is False
    assert report["data_quality"]["sp500"]["bad_bars"] == 0
    assert report["data_quality"]["nasdaq"]["bad_bars"] == 0
    assert "error" not in report["sp500"]
    assert "**Data quality:**" not in markdown


def test_insufficient_qqq_exposes_error_but_stays_no_ftd(monkeypatch, tmp_path):
    report, _ = run_main(monkeypatch, tmp_path, dated(confirmed=False), [])
    assert report["nasdaq"]["error"] == "Insufficient data"
    assert report["quality_score"]["signal"] == "No FTD"
    assert report["data_gap"] is False


def test_power_trend_only_gap_prints_unavailable(monkeypatch, tmp_path, capsys):
    bars, _ = make_long_ftd_history()
    report, markdown = run_main(monkeypatch, tmp_path, gap(bars, 3), [])
    console = capsys.readouterr().out
    assert report["data_gap"] is False
    assert report["power_trend"]["power_trend"] is None
    assert report["data_quality"]["sp500"]["power_trend_bad_bars"] == 1
    assert "Power Trend: Unavailable (Data gap: missing or invalid close" in console
    assert "**Power Trend:** Unavailable (Data gap: missing or invalid close" in markdown
    assert "**Data quality:**" in markdown
    assert_no_none(markdown)


def _confirmed_analysis_with_post_ftd_gap(field):
    """FTD_CONFIRMED from clean data, post-FTD history gapped (direct-caller path)."""
    bars, ftd_idx = make_long_ftd_history(post_days=8)
    gapped = copy.deepcopy(bars)
    target = ftd_idx + 2 if field == "volume" else ftd_idx + 8
    gapped[target][field] = math.nan
    market_state = get_market_state(list(reversed(bars)), [])
    market_state = assess_post_ftd_health(market_state, gapped, [])
    return {
        "metadata": {"generated_at": "2026-11-13 00:00:00", "index_prices": {}},
        "market_state": {
            "combined_state": market_state["combined_state"],
            "dual_confirmation": market_state["dual_confirmation"],
            "ftd_index": market_state.get("ftd_index"),
        },
        "data_gap": market_state["data_gap"],
        "data_quality": market_state["data_quality"],
        "sp500": ftd_detector._serialize_index(market_state["sp500"]),
        "nasdaq": ftd_detector._serialize_index(market_state["nasdaq"]),
        "quality_score": market_state["quality_score"],
        "post_ftd_distribution": market_state.get("post_ftd_distribution", {}),
        "ftd_invalidation": market_state.get("ftd_invalidation", {}),
        "power_trend": market_state.get("power_trend", {}),
    }


@pytest.mark.parametrize("field", ["close", "volume"])
def test_confirmed_with_post_ftd_gap_renders_unavailable(tmp_path, field):
    analysis = _confirmed_analysis_with_post_ftd_gap(field)
    # the clean FTD can be neither confirmed nor invalidated on gapped history
    assert analysis["market_state"]["combined_state"] == "NO_SIGNAL"
    assert analysis["market_state"]["ftd_index"] is None
    path = tmp_path / "r.md"
    generate_markdown_report(analysis, str(path))
    markdown = path.read_text(encoding="utf-8")

    assert "**State unavailable (data gap)**" in markdown
    assert "No Signal (Uptrend)" not in markdown
    assert "Unavailable: data gap" in markdown
    assert "Data gap: confirmation unavailable" in markdown
    assert "Cautious exposure increase" not in markdown
    assert "Aggressively increase" not in markdown
    assert "Gradually increase" not in markdown
    if field == "close":
        assert "**FTD Valid:** Unavailable (Data gap:" in markdown
    else:
        assert "**Distribution Days Since FTD:** Unavailable (Data gap:" in markdown
    assert_no_none(markdown)


def test_invalidated_true_with_missing_numbers_does_not_format_none(tmp_path):
    analysis = {
        "market_state": {"combined_state": "FTD_INVALIDATED"},
        "quality_score": {"total_score": 0, "signal": "Failed/Invalidated"},
        "ftd_invalidation": {"invalidated": True, "invalidation_date": "2026-04-03"},
    }
    path = tmp_path / "r.md"
    generate_markdown_report(analysis, str(path))
    markdown = path.read_text(encoding="utf-8")
    assert "**FTD INVALIDATED** on 2026-04-03" in markdown
    assert "$N/A" in markdown
