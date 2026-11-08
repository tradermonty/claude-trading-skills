"""Stale/dead tickers cannot become current Momentum Burst candidates (#670)."""

import json
import sys
from argparse import Namespace
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
import screen_momentum_burst as screen


def args(**overrides):
    values = dict(
        min_price=5,
        min_volume=100_000,
        four_pct_threshold=4,
        dollar_threshold=0.9,
        nine_million_volume=9_000_000,
        max_prev_day_gain_for_range=2,
        min_base_days=3,
        max_base_days=20,
        max_base_width_pct=15,
        max_prior_avg_range_pct=5,
        narrow_prior_day_range_pct=3,
        recent_breakdown_lookback=5,
        breakdown_threshold_pct=4,
        max_risk_pct_to_stop=10,
        market_gate="allowed",
        as_of="2026-11-06",
        max_bar_age_sessions=0,
    )
    values.update(overrides)
    return Namespace(**values)


def rows(latest="2026-11-06"):
    day = date.fromisoformat(latest)
    history = [
        dict(
            date=(day - timedelta(days=i)).isoformat(),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=180_000,
        )
        for i in range(35)
    ]
    history[0].update(high=106, low=102, close=105, volume=600_000)
    return history


def analyze(latest="2026-11-06", **options):
    return screen.analyze_symbol("TEST", screen.normalize_bars(rows(latest)), args(**options))


def test_stale_strong_breakout_is_rejected_and_fresh_score_is_preserved():
    fresh = analyze()
    assert fresh["state"] == "ACTIONABLE_DAY1"
    stale = analyze("2023-07-31")
    assert stale["state"] == "REJECTED"
    assert stale["setup_score"] == 0
    assert stale["reject_reasons"] == ["stale_price_data"]
    assert stale["latest_bar_date"] == "2023-07-31"
    assert "Do not trade" in stale["downstream_action"]
    assert fresh["latest_bar_date"] == "2026-11-06"
    assert fresh["bar_age_sessions"] == 0


@pytest.mark.parametrize("limit,state", [(0, "REJECTED"), (1, "MANUAL_REVIEW")])
def test_exact_session_age_boundary(limit, state):
    result = analyze("2026-11-05", max_bar_age_sessions=limit)
    assert result["state"] == state
    assert result["bar_age_sessions"] == 1


def test_holiday_weekend_do_not_count_as_stale_sessions():
    # July 3 is the Independence Day closure; July 4-5 are the weekend.
    result = analyze("2026-07-02", as_of="2026-07-05")
    assert result["expected_session"] == "2026-07-02"
    assert result["bar_age_sessions"] == 0
    assert result["state"] == "ACTIONABLE_DAY1"


@pytest.mark.parametrize(
    "now,expected",
    [
        ("2026-11-06T14:00:00+00:00", "2026-11-05"),  # before open
        ("2026-11-06T20:59:59+00:00", "2026-11-05"),  # intraday, EST
        ("2026-11-06T21:00:00+00:00", "2026-11-06"),
        ("2026-07-06T19:59:59+00:00", "2026-07-02"),  # EDT after holiday
        ("2026-07-06T20:00:00+00:00", "2026-07-06"),
        ("2026-11-27T17:59:59+00:00", "2026-11-25"),  # early close
        ("2026-11-27T18:00:00+00:00", "2026-11-27"),
        ("2026-11-28T12:00:00+00:00", "2026-11-27"),
    ],
)
def test_default_cutoff_is_latest_completed_session(now, expected):
    assert (
        screen.resolve_expected_session(None, now=datetime.fromisoformat(now)).isoformat()
        == expected
    )


@pytest.mark.parametrize("cutoff", ["2026-11-06", "2026-11-09"])
def test_explicit_uncompleted_or_future_session_is_rejected(cutoff):
    with pytest.raises(ValueError, match="completed"):
        screen.resolve_expected_session(cutoff, now=datetime(2026, 11, 6, 17, tzinfo=timezone.utc))


def test_future_rows_cannot_change_historical_score():
    expected = analyze()
    future = rows("2026-11-09")[0]
    result = screen.analyze_symbol("TEST", screen.normalize_bars([future] + rows()), args())
    assert result == expected


def test_only_future_rows_have_no_eligible_observation():
    result = screen.analyze_symbol("TEST", screen.normalize_bars([rows("2026-11-09")[0]]), args())
    assert result["state"] == "REJECTED"
    assert "no_completed_price_data" in result["reject_reasons"]


def test_non_session_bar_is_rejected_not_given_zero_age():
    result = analyze("2026-11-01")
    assert result["state"] == "REJECTED"
    assert "invalid_price_date" in result["reject_reasons"]


def cli(tmp_path, monkeypatch, data, *flags):
    source = tmp_path / "prices.json"
    source.write_text(json.dumps(data))
    output = tmp_path / "out"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "screen",
            "--prices-json",
            str(source),
            "--as-of",
            "2026-11-06",
            "--output-dir",
            str(output),
            "--market-gate",
            "allowed",
            *flags,
        ],
    )
    screen.main()
    return json.loads(next(output.glob("*.json")).read_text()), next(
        output.glob("*.md")
    ).read_text()


@pytest.mark.parametrize("bad", [None, "", "20261106", "2026-02-30", "2026-11-06T10:00:00Z"])
def test_cli_raw_bad_date_cannot_disappear_before_fresh_breakout(tmp_path, monkeypatch, bad):
    invalid = {"date": bad, "close": 100}  # numeric validation used to drop this row
    payload, _ = cli(tmp_path, monkeypatch, {"BAD": rows() + [invalid]})
    result = payload["candidates"][0]
    assert result["state"] == "REJECTED"
    assert "invalid_price_date" in result["reject_reasons"]


def test_cli_metadata_and_markdown_expose_staleness_without_reject_flag(tmp_path, monkeypatch):
    payload, md = cli(tmp_path, monkeypatch, {"FRESH": rows(), "STALE": rows("2025-07-01")})
    meta = payload["metadata"]
    assert meta["expected_session"] == "2026-11-06"
    assert meta["stale_price_data_count"] == 1
    assert meta["latest_bar_dates"] == {"FRESH": "2026-11-06", "STALE": "2025-07-01"}
    assert meta["max_bar_age_sessions"] == 0
    assert "Stale price data rejected: 1" in md
    assert "2026-11-06" in md


def test_all_stale_universe_emits_publish_lag_warning(tmp_path, monkeypatch):
    payload, md = cli(tmp_path, monkeypatch, {"A": rows("2026-11-05"), "B": rows("2026-11-05")})
    assert payload["metadata"]["stale_price_data_count"] == 2
    assert len(payload["warnings"]) == 1
    assert "all" in payload["warnings"][0].lower()
    assert "EOD" in payload["warnings"][0]
    assert "## Warnings" in md
    assert payload["warnings"][0] in md


def test_partial_stale_universe_has_no_all_stale_warning(tmp_path, monkeypatch):
    payload, md = cli(tmp_path, monkeypatch, {"A": rows(), "B": rows("2026-11-05")})
    assert payload["warnings"] == []
    assert "## Warnings" not in md


def test_one_session_old_bar_is_capped_at_manual_review():
    result = analyze("2026-11-05", max_bar_age_sessions=1)
    assert result["bar_age_sessions"] == 1
    assert result["state"] == "MANUAL_REVIEW"
    assert "stale_bar_tolerated" in result["soft_failure_tags"]
    fresh = analyze(max_bar_age_sessions=1)
    assert fresh["state"] == "ACTIONABLE_DAY1"
    assert "stale_bar_tolerated" not in fresh["soft_failure_tags"]


@pytest.mark.parametrize(
    "flags",
    [
        ["--as-of", "20261106"],
        ["--as-of", "2026-02-30"],
        ["--max-bar-age-sessions", "-1"],
        ["--max-bar-age-sessions", "1.5"],
    ],
)
def test_invalid_cli_controls_are_usage_errors(monkeypatch, flags):
    monkeypatch.setattr(sys, "argv", ["screen", *flags])
    with pytest.raises(SystemExit) as exc:
        screen.parse_arguments()
    assert exc.value.code == 2


def test_calendar_unavailable_fails_before_http_or_output(tmp_path, monkeypatch, capsys):
    def unavailable(*_a, **_kw):
        raise screen.calendar.CalendarUnavailableError("offline calendar failed")

    monkeypatch.setattr(screen.calendar, "previous_session_on_or_before", unavailable)
    monkeypatch.setattr(
        screen, "collect_price_data", MagicMock(side_effect=AssertionError("HTTP before calendar"))
    )
    monkeypatch.setattr(sys, "argv", ["screen", "--symbols", "TEST", "--output-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        screen.main()
    assert exc.value.code == 1
    assert "calendar" in capsys.readouterr().err.lower()
    assert list(tmp_path.iterdir()) == []


def test_universe_requests_active_and_excludes_inactive(monkeypatch):
    client = screen.FMPClient("fixture-key")
    fetch = MagicMock(
        return_value=[
            {"symbol": "LIVE", "isActivelyTrading": True},
            {"symbol": "DEAD", "isActivelyTrading": False},
            {"symbol": "UNKNOWN"},
        ]
    )
    monkeypatch.setattr(client._client, "fetch_screener_rows", fetch)
    result = client.get_universe(500_000_000, 5, 100_000, 100)
    assert [r["symbol"] for r in result] == ["LIVE", "UNKNOWN"]
    assert fetch.call_args.args[0]["isActivelyTrading"] == "true"


def test_direct_caller_without_new_flags_cannot_bypass_stale_gate():
    options = args()
    del options.as_of
    del options.max_bar_age_sessions
    result = screen.analyze_symbol("DEAD", screen.normalize_bars(rows("2023-07-31")), options)
    assert result["state"] == "REJECTED"
    assert result["reject_reasons"] == ["stale_price_data"]


def test_default_session_is_frozen_before_collection(tmp_path, monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 11, 6, 21, tzinfo=timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.current.astimezone(tz) if tz else cls.current.replace(tzinfo=None)

    def collect(_args):
        Clock.current = datetime(2026, 11, 9, 22, tzinfo=timezone.utc)
        return {"TEST": screen.normalize_bars(rows())}, None

    monkeypatch.setattr(screen, "datetime", Clock)
    monkeypatch.setattr(screen, "collect_price_data", collect)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "screen",
            "--prices-json",
            "fictional",
            "--market-gate",
            "allowed",
            "--output-dir",
            str(tmp_path),
        ],
    )
    screen.main()
    payload = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert payload["metadata"]["expected_session"] == "2026-11-06"
    assert payload["candidates"][0]["state"] == "ACTIONABLE_DAY1"


@pytest.mark.parametrize("bad_date", [None, "not-a-date"])
def test_fmp_cli_invalid_date_beyond_history_limit_is_not_hidden(tmp_path, monkeypatch, bad_date):
    shared = screen._load_shared_fmp()
    response = MagicMock(status_code=200, text="")
    response.json.return_value = rows() + [{"date": bad_date, "close": 100}]
    session = MagicMock()
    session.headers = {}
    session.get.return_value = response
    monkeypatch.setattr(shared.requests, "Session", lambda: session)
    monkeypatch.setattr(shared.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "screen",
            "--symbols",
            "TEST",
            "--api-key",
            "fixture-key",
            "--history-days",
            "30",
            "--as-of",
            "2026-11-06",
            "--market-gate",
            "allowed",
            "--output-dir",
            str(tmp_path),
        ],
    )
    screen.main()
    payload = json.loads(next(tmp_path.glob("*.json")).read_text())
    result = payload["candidates"][0]
    assert result["state"] == "REJECTED"
    assert result["reject_reasons"] == ["invalid_price_date"]
    assert result["setup_score"] == 0
    assert session.get.call_count == 1
    assert session.get.call_args.args[0].endswith("/stable/historical-price-eod/full")


def test_fmp_cutoff_precedes_history_limit(tmp_path, monkeypatch):
    shared = screen._load_shared_fmp()
    session = MagicMock()
    session.headers = {}
    response = MagicMock(status_code=200, text="")
    session.get.return_value = response
    monkeypatch.setattr(shared.requests, "Session", lambda: session)
    monkeypatch.setattr(shared.time, "sleep", lambda _seconds: None)
    baseline = rows("2026-11-05")[:25]
    results = []
    for label, raw in [("baseline", baseline), ("future", [rows()[0]] + baseline)]:
        response.json.return_value = raw
        output = tmp_path / label
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "screen",
                "--symbols",
                "TEST",
                "--api-key",
                "fixture-key",
                "--history-days",
                "25",
                "--as-of",
                "2026-11-05",
                "--market-gate",
                "allowed",
                "--output-dir",
                str(output),
            ],
        )
        screen.main()
        results.append(json.loads(next(output.glob("*.json")).read_text())["candidates"][0])
    assert results[0]["state"] == "ACTIONABLE_DAY1"
    assert results[1] == results[0]
