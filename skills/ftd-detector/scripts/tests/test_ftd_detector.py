"""Offline CLI regressions through the real state machine and report writers."""

import copy
import json
from collections import Counter
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
        bars.append(make_bar(min(b["low"] for b in bars) - 0.1, volume=2_000_000))
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


def test_default_output_writes_reports_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    history = market_history()
    client = FixtureClient(
        {"^GSPC": {"historical": history}, "^IXIC": {"historical": history}},
        {"^GSPC": [{"price": 101.25}], "^IXIC": [{"price": 101.25}]},
    )
    monkeypatch.setattr(ftd_detector, "FMPClient", lambda api_key: client)
    monkeypatch.setattr("sys.argv", ["ftd_detector.py", "--api-key", "fixture-only"])

    ftd_detector.main()

    read_reports(tmp_path / "reports")
    assert not list(tmp_path.glob("ftd_detector_*.json"))


@pytest.mark.parametrize(
    "scenario,expected_state,expected_score",
    [
        ("dual", "FTD_CONFIRMED", 100),
        ("single", "FTD_CONFIRMED", 95),
        ("nasdaq_single", "FTD_CONFIRMED", 95),
        ("invalidated", "FTD_INVALIDATED", 0),
        ("window", "FTD_WINDOW", 0),
    ],
)
def test_main_writes_real_decision_reports(
    monkeypatch, tmp_path, scenario, expected_state, expected_score
):
    sp500 = market_history(
        confirmed=scenario not in {"nasdaq_single", "window"},
        invalidated=scenario == "invalidated",
    )
    qqq = market_history(
        peak=400,
        confirmed=scenario not in {"single", "window"},
        invalidated=scenario == "invalidated",
    )
    histories = {"^GSPC": {"historical": sp500}, "^IXIC": {"historical": qqq}}
    original = copy.deepcopy(histories)
    client = FixtureClient(histories, {"^GSPC": [{"price": 101.25}], "^IXIC": [{"price": 405.5}]})
    install_client(monkeypatch, tmp_path, client)

    ftd_detector.main()

    report, markdown = read_reports(tmp_path)
    assert Counter((call[0], call[1]) for call in client.calls) == Counter(
        {
            ("history", "^GSPC"): 1,
            ("history", "^IXIC"): 1,
            ("quote", "^GSPC"): 1,
            ("quote", "^IXIC"): 1,
        }
    )
    assert histories == original
    assert report["metadata"]["api_calls"] == {"api_calls_made": 4, "cache_entries": 0}
    assert report["metadata"]["index_prices"] == {"sp500": 101.25, "nasdaq": 405.5}
    assert "**S&P 500:** $101.25" in markdown
    assert "**Nasdaq Composite (^IXIC):** $405.50" in markdown
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
        assert "Rally attempt is not FTD confirmation" in markdown
    else:
        confirmed_index = report["nasdaq"] if scenario == "nasdaq_single" else report["sp500"]
        assert confirmed_index["ftd"]["ftd_date"] == "2026-03-30"
        assert confirmed_index["ftd"]["ftd_day_number"] == 5
        assert confirmed_index["ftd"]["gain_pct"] == 2.1
        assert "## FTD Signal" in markdown
    if scenario == "invalidated":
        invalidation = report["ftd_invalidation"]
        assert invalidation["invalidated"] is True
        assert invalidation["invalidation_date"] == "2026-04-03"
        assert invalidation["days_after_ftd"] == 4
        assert report["post_ftd_distribution"]["distribution_count"] == 1
        assert report["quality_score"]["signal"] == "Failed/Invalidated"
        assert report["quality_score"]["exposure_range"] == "Not assessed"
        assert "Recorded rally reference breached" in markdown
        assert "Aggressively increase equity exposure" not in markdown
    elif scenario == "dual":
        assert "YES (S&P 500 + Nasdaq Composite (^IXIC))" in markdown
        assert report["ftd_invalidation"]["invalidated"] is False
    elif scenario == "single":
        assert "| **FTD Index** | S&P 500 |" in markdown
        assert "YES (S&P 500 + Nasdaq Composite (^IXIC))" not in markdown
    elif scenario == "nasdaq_single":
        assert report["sp500"]["ftd"]["ftd_detected"] is False
        assert report["nasdaq"]["ftd"]["ftd_detected"] is True
        assert report["market_state"]["dual_confirmation"] is False
        assert report["market_state"]["ftd_index"] == "Nasdaq Composite (^IXIC)"
        assert "| **FTD Index** | Nasdaq Composite (^IXIC) |" in markdown
        assert "### Nasdaq Composite (^IXIC) FTD" in markdown
        assert "### S&P 500 FTD" not in markdown


@pytest.mark.parametrize("qqq_available", [True, False])
def test_missing_quotes_use_latest_historical_close_in_real_reports(
    monkeypatch, tmp_path, capsys, qqq_available
):
    sp500 = market_history()
    qqq = market_history(peak=400) if qqq_available else []
    client = FixtureClient(
        {"^GSPC": {"historical": sp500}, "^IXIC": {"historical": qqq}},
        {"^GSPC": None, "^IXIC": []},
    )
    install_client(monkeypatch, tmp_path, client)

    ftd_detector.main()

    report, markdown = read_reports(tmp_path)
    assert report["metadata"]["index_prices"] == {
        "sp500": sp500[0]["close"],
        "nasdaq": qqq[0]["close"] if qqq else None,
    }
    assert f"**S&P 500:** ${sp500[0]['close']:.2f}" in markdown
    output = capsys.readouterr().out
    assert output.count("Using historical close as current price") == 2
    if qqq_available:
        assert f"**Nasdaq Composite (^IXIC):** ${qqq[0]['close']:.2f}" in markdown
    else:
        assert "NASDAQ data unavailable, using S&P 500 only" in output
        assert report["nasdaq"]["current_price"] is None
        assert report["market_state"]["dual_confirmation"] is False
        assert report["market_state"]["ftd_index"] == "S&P 500"
        assert "**Nasdaq Composite (^IXIC):**" not in markdown


@pytest.mark.parametrize("history", [None, {}, {"historical": []}])
def test_missing_mandatory_history_exits_without_reports(monkeypatch, tmp_path, capsys, history):
    client = FixtureClient({"^GSPC": history}, {})
    install_client(monkeypatch, tmp_path, client)
    with pytest.raises(SystemExit) as exc:
        ftd_detector.main()
    assert exc.value.code == 1
    assert "Cannot proceed without S&P 500 data" in capsys.readouterr().err
    assert [(call[0], call[1]) for call in client.calls] == [("history", "^GSPC")]
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


@pytest.mark.parametrize("symbol", ["^IXIC", "QQQ"])
def test_instrument_identity_keeps_price_and_volume_on_selected_series(
    monkeypatch, tmp_path, symbol
):
    client = FixtureClient(
        {
            "^GSPC": {"historical": market_history()},
            "^IXIC": {"historical": market_history(peak=1000)},
            "QQQ": {"historical": market_history(peak=400)},
        },
        {"^GSPC": [{"price": 101}], "^IXIC": [{"price": 1001}], "QQQ": [{"price": 401}]},
    )
    install_client(monkeypatch, tmp_path, client)
    monkeypatch.setattr(
        "sys.argv", ["ftd_detector.py", "--output-dir", str(tmp_path), "--nasdaq-symbol", symbol]
    )
    ftd_detector.main()
    report, markdown = read_reports(tmp_path)
    identity = report["metadata"]["instruments"]["nasdaq"]
    assert identity["symbol"] == symbol
    assert identity["kind"] == ("index" if symbol == "^IXIC" else "etf_proxy")
    assert report["metadata"]["index_prices"]["nasdaq"] == (1001 if symbol == "^IXIC" else 401)
    assert all(call[1] in ("^GSPC", symbol) for call in client.calls)
    assert identity["label"] in markdown
    assert "Aggressively increase" not in markdown
    assert report["quality_score"]["exposure_range"] == "Not assessed"


def test_explicit_qqq_identity_reaches_all_public_fields(monkeypatch, tmp_path):
    client = FixtureClient(
        {
            "^GSPC": {"historical": market_history(confirmed=False)},
            "QQQ": {"historical": market_history(peak=400)},
        },
        {"^GSPC": [], "QQQ": []},
    )
    install_client(monkeypatch, tmp_path, client)
    monkeypatch.setattr(
        "sys.argv", ["ftd_detector.py", "--output-dir", str(tmp_path), "--nasdaq-symbol", "QQQ"]
    )
    ftd_detector.main()
    report, markdown = read_reports(tmp_path)
    label = report["metadata"]["instruments"]["nasdaq"]["label"]
    assert report["market_state"]["ftd_index"] == label
    assert report["quality_score"]["ftd_source"] == label
    assert f"FTD Index** | {label}" in markdown


def test_dual_report_exposes_both_day1_failure_levels(monkeypatch, tmp_path):
    client = FixtureClient(
        {
            "^GSPC": {"historical": market_history()},
            "^IXIC": {"historical": market_history(peak=200)},
        },
        {"^GSPC": [], "^IXIC": []},
    )
    install_client(monkeypatch, tmp_path, client)
    ftd_detector.main()
    report, markdown = read_reports(tmp_path)
    levels = markdown.split("## Key Watch Levels", 1)[1].split("## Methodology", 1)[0]
    for key, label in [("sp500", "S&P 500"), ("nasdaq", "Nasdaq Composite (^IXIC)")]:
        section = levels.split(f"**{label}:**", 1)[1].split("\n\n", 1)[0]
        rally = report[key]["rally_attempt"]
        assert f"Rally Day 1: {rally['day1_date']}" in section
        assert (
            f"Day 1 Low (rally failure level; intraday breach): ${rally['day1_low']:.2f}" in section
        )
        assert "Swing Low:" in section
        assert "FTD Day Low (warning level):" in section
