"""Offline CLI regressions through the real state machine and report writers."""

import copy
import json
from datetime import date, timedelta

import ftd_detector
import pytest
import requests
from helpers import make_bar, make_rally_history


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("FTD CLI fixtures must not make network requests")

    monkeypatch.setattr(requests.sessions.Session, "request", unexpected_request)


def market_history(*, peak=100, confirmed=True, invalidated=False):
    bars, _, _, ftd_idx = make_rally_history(
        peak=peak,
        rally_days=8,
        ftd_day=5 if confirmed else None,
        ftd_gain_pct=2.1,
    )
    if invalidated:
        bars.append(make_bar(bars[ftd_idx]["low"] - 0.1, volume=2_000_000))
    session = date(2026, 3, 2)
    for bar in bars:
        bar["date"] = session.isoformat()
        session += timedelta(days=1)
        while session.weekday() >= 5:
            session += timedelta(days=1)
    return list(reversed(bars))


class FixtureClient:
    def __init__(self, histories, quotes):
        self.histories = histories
        self.quotes = quotes
        self.calls = []

    def get_historical_prices(self, symbol, days):
        self.calls.append(("history", symbol, days))
        return self.histories[symbol]

    def get_quote(self, symbol):
        self.calls.append(("quote", symbol))
        return self.quotes[symbol]

    def get_api_stats(self):
        return {"api_calls_made": len(self.calls), "cache_entries": 0}


def install_client(monkeypatch, tmp_path, client):
    monkeypatch.setattr(ftd_detector, "FMPClient", lambda api_key: client)
    monkeypatch.setattr("sys.argv", ["ftd_detector.py", "--output-dir", str(tmp_path)])


def read_reports(tmp_path):
    json_paths = list(tmp_path.glob("ftd_detector_*.json"))
    md_paths = list(tmp_path.glob("ftd_detector_*.md"))
    assert len(json_paths) == len(md_paths) == 1
    assert json_paths[0].stem == md_paths[0].stem
    return json.loads(json_paths[0].read_text()), md_paths[0].read_text()


@pytest.mark.parametrize(
    "scenario,expected_state,expected_score",
    [
        ("dual", "FTD_CONFIRMED", 100),
        ("single", "FTD_CONFIRMED", 95),
        ("invalidated", "FTD_INVALIDATED", 0),
        ("window", "FTD_WINDOW", 0),
    ],
)
def test_main_writes_real_decision_reports(
    monkeypatch, tmp_path, scenario, expected_state, expected_score
):
    sp500 = market_history(confirmed=scenario != "window", invalidated=scenario == "invalidated")
    qqq = market_history(
        peak=400,
        confirmed=scenario not in {"single", "window"},
        invalidated=scenario == "invalidated",
    )
    histories = {"^GSPC": {"historical": sp500}, "QQQ": {"historical": qqq}}
    original = copy.deepcopy(histories)
    client = FixtureClient(histories, {"^GSPC": [{"price": 101.25}], "QQQ": [{"price": 405.5}]})
    install_client(monkeypatch, tmp_path, client)

    ftd_detector.main()

    report, markdown = read_reports(tmp_path)
    assert client.calls == [
        ("history", "^GSPC", 80),
        ("history", "QQQ", 80),
        ("quote", "^GSPC"),
        ("quote", "QQQ"),
    ]
    assert histories == original
    assert report["metadata"]["api_calls"] == {"api_calls_made": 4, "cache_entries": 0}
    assert report["metadata"]["index_prices"] == {"sp500": 101.25, "qqq": 405.5}
    assert "**S&P 500:** $101.25" in markdown
    assert "**QQQ:** $405.50" in markdown
    assert report["market_state"]["combined_state"] == expected_state
    assert report["market_state"]["dual_confirmation"] is (scenario == "dual")
    assert report["quality_score"]["total_score"] == expected_score
    assert f"**{expected_score}/100**" in markdown
    for key, history in [("sp500", sp500), ("nasdaq", qqq)]:
        index = report[key]
        assert index["current_price"] == history[0]["close"]
        assert index["swing_low"]["price"] == (95 if key == "sp500" else 380)
        assert index["rally_attempt"]["day1_date"] == "2026-03-24"
        assert "rally_days" not in index["rally_attempt"]
        assert "_ftd_idx" not in index["ftd"]
    if scenario == "window":
        assert report["sp500"]["ftd"]["ftd_detected"] is False
        assert report["quality_score"]["signal"] == "No FTD"
        assert "## FTD Signal" not in markdown
        assert "Do not buy ahead of FTD confirmation" in markdown
    else:
        assert report["sp500"]["ftd"]["ftd_date"] == "2026-03-30"
        assert report["sp500"]["ftd"]["ftd_day_number"] == 5
        assert report["sp500"]["ftd"]["gain_pct"] == 2.1
        assert "## FTD Signal" in markdown
    if scenario == "invalidated":
        invalidation = report["ftd_invalidation"]
        assert invalidation["invalidated"] is True
        assert invalidation["invalidation_date"] == "2026-04-03"
        assert invalidation["days_after_ftd"] == 4
        assert report["post_ftd_distribution"]["distribution_count"] == 1
        assert report["quality_score"]["signal"] == "Failed/Invalidated"
        assert report["quality_score"]["exposure_range"] == "0-25%"
        assert "Reduce exposure back to defensive levels" in markdown
        assert "Aggressively increase equity exposure" not in markdown
    elif scenario == "dual":
        assert "YES (S&P 500 + NASDAQ)" in markdown
        assert report["ftd_invalidation"]["invalidated"] is False
    elif scenario == "single":
        assert "| **FTD Index** | S&P 500 |" in markdown
        assert "YES (S&P 500 + NASDAQ)" not in markdown


@pytest.mark.parametrize("qqq_available", [True, False])
def test_missing_quotes_use_latest_historical_close_in_real_reports(
    monkeypatch, tmp_path, capsys, qqq_available
):
    sp500 = market_history()
    qqq = market_history(peak=400) if qqq_available else []
    client = FixtureClient(
        {"^GSPC": {"historical": sp500}, "QQQ": {"historical": qqq}},
        {"^GSPC": None, "QQQ": []},
    )
    install_client(monkeypatch, tmp_path, client)

    ftd_detector.main()

    report, markdown = read_reports(tmp_path)
    assert report["metadata"]["index_prices"] == {
        "sp500": sp500[0]["close"],
        "qqq": qqq[0]["close"] if qqq else None,
    }
    assert f"**S&P 500:** ${sp500[0]['close']:.2f}" in markdown
    output = capsys.readouterr().out
    assert output.count("Using historical close as current price") == 2
    if qqq_available:
        assert f"**QQQ:** ${qqq[0]['close']:.2f}" in markdown
    else:
        assert "NASDAQ data unavailable, using S&P 500 only" in output
        assert report["nasdaq"]["current_price"] is None
        assert report["market_state"]["dual_confirmation"] is False
        assert report["market_state"]["ftd_index"] == "S&P 500"
        assert "**QQQ:**" not in markdown


@pytest.mark.parametrize("history", [None, {}, {"historical": []}])
def test_missing_mandatory_history_exits_without_reports(monkeypatch, tmp_path, capsys, history):
    client = FixtureClient({"^GSPC": history}, {})
    install_client(monkeypatch, tmp_path, client)
    with pytest.raises(SystemExit) as exc:
        ftd_detector.main()
    assert exc.value.code == 1
    assert "Cannot proceed without S&P 500 data" in capsys.readouterr().err
    assert client.calls == [("history", "^GSPC", 80)]
    assert list(tmp_path.iterdir()) == []


def test_missing_credentials_exits_without_reports(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["ftd_detector.py", "--output-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        ftd_detector.main()
    assert exc.value.code == 1
    assert "API key" in capsys.readouterr().err
    assert list(tmp_path.iterdir()) == []


def test_cli_parses_explicit_arguments(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "sys.argv",
        ["ftd_detector.py", "--api-key", "fixture-only", "--output-dir", str(tmp_path)],
    )
    args = ftd_detector.parse_arguments()
    assert args.api_key == "fixture-only"  # pragma: allowlist secret
    assert args.output_dir == str(tmp_path)
