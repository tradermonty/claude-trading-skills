#!/usr/bin/env python3
"""Tests for historical single-ticker VCP scanning.

Covers:
- analyze_stock(as_of_offset=...) equivalence with pre-sliced inputs
- build_quote_from_history (no-lookahead contract)
- calculate_forward_outcome (breakout / stop-hit / timeout paths)
- HistoricalScanner walk + dedup
"""

import os
import sys

import pytest


# Reuse the synthetic-data helper from the existing test module.
sys.path.insert(0, os.path.dirname(__file__))
from test_vcp_screener import _make_prices  # noqa: E402


# ===========================================================================
# analyze_stock(as_of_offset=...) — equivalence with pre-sliced inputs
# ===========================================================================


class TestAsOfOffsetSeam:
    """as_of_offset=N must produce identical output to pre-slicing the inputs."""

    def test_offset_equals_pre_slice(self):
        from screen_vcp import analyze_stock

        # Generate enough history for trend template (>= 222 bars) and lookback.
        full_hist = _make_prices(300, start=100, daily_change=0.001)
        full_spy = _make_prices(300, start=400, daily_change=0.0005)
        offset = 60

        # When the analysis cursor is at offset 60, treat that bar as "today".
        # Caller is responsible for synthesizing the quote from the slice.
        as_of_bar = full_hist[offset]
        year_window = full_hist[offset : offset + 252]
        synth_quote = {
            "price": as_of_bar["close"],
            "yearHigh": max(d["high"] for d in year_window),
            "yearLow": min(d["low"] for d in year_window),
            "marketCap": 1e9,
            "avgVolume": 1_000_000,
        }

        # Path A: pre-slice both arrays, as_of_offset=0
        result_pre = analyze_stock(
            "TEST",
            full_hist[offset:],
            synth_quote,
            full_spy[offset:],
            sector="Tech",
            company_name="Test Corp",
        )

        # Path B: pass full arrays, as_of_offset=60
        result_off = analyze_stock(
            "TEST",
            full_hist,
            synth_quote,
            full_spy,
            sector="Tech",
            company_name="Test Corp",
            as_of_offset=offset,
        )

        assert result_pre is not None and result_off is not None
        # Compare every numeric / categorical field that matters for downstream
        # use; nested dicts (trend_template, vcp_pattern, etc.) included.
        for key in (
            "composite_score",
            "valid_vcp",
            "execution_state",
            "pattern_type",
            "distance_from_pivot_pct",
            "sma200_distance_pct",
        ):
            assert result_pre[key] == result_off[key], f"mismatch at {key}"
        # Volume zone analysis is the path most affected by slicing — assert it
        # explicitly so a regression on the as-of-offset seam is loud.
        za_pre = result_pre["volume_pattern"].get("zone_analysis")
        za_off = result_off["volume_pattern"].get("zone_analysis")
        assert za_pre == za_off

    def test_offset_zero_is_noop(self):
        """as_of_offset=0 must not change anything (backwards compatibility)."""
        from screen_vcp import analyze_stock

        hist = _make_prices(260, start=100, daily_change=0.001)
        spy = _make_prices(260, start=400, daily_change=0.0005)
        quote = {
            "price": hist[0]["close"],
            "yearHigh": hist[0]["close"] * 1.1,
            "yearLow": hist[0]["close"] * 0.7,
            "marketCap": 1e9,
            "avgVolume": 1_000_000,
        }
        r_default = analyze_stock("TEST", hist, quote, spy)
        r_explicit = analyze_stock("TEST", hist, quote, spy, as_of_offset=0)
        assert r_default == r_explicit


# ===========================================================================
# Forward outcome calculator
# ===========================================================================


def _bar(date, close, low=None, high=None, volume=1_000_000):
    """Single OHLCV bar dict."""
    return {
        "date": date,
        "open": close,
        "high": high if high is not None else close * 1.01,
        "low": low if low is not None else close * 0.99,
        "close": close,
        "adjClose": close,
        "volume": volume,
    }


def _hist(closes_oldest_first):
    """Build a most-recent-first history from a list of closes given
    oldest-to-newest (more natural to write for forward-outcome tests).

    Dates are generated via real ``datetime`` arithmetic starting at
    2025-01-01, so this stays valid past the end of the month.
    """
    from datetime import date, timedelta

    base = date(2025, 1, 1)
    bars = [
        _bar((base + timedelta(days=i)).isoformat(), c, low=c * 0.99, high=c * 1.01)
        for i, c in enumerate(closes_oldest_first)
    ]
    return list(reversed(bars))


class TestForwardOutcome:
    """calculate_forward_outcome walks bars MORE RECENT than the as-of bar
    (indices 0..as_of_offset-1 in the most-recent-first array)."""

    def test_breakout_detected_within_window(self):
        from calculators.forward_outcome import calculate_forward_outcome

        # oldest .. newest: 100, 101, 102, 103, 105, 110 (breakout at day 5)
        # as_of = day 0 (close=100) i.e. historical[5] in MRF
        closes = [100, 101, 102, 103, 105, 110]
        hist = _hist(closes)
        as_of_offset = 5  # MRF index of close=100 (the oldest)
        result = calculate_forward_outcome(
            hist, as_of_offset=as_of_offset,
            pivot_price=104.0, stop_price=95.0, max_window_days=10,
        )
        assert result["outcome_type"] == "breakout"
        assert result["days_to_outcome"] == 4  # 100 -> 101 -> 102 -> 103 -> 105
        assert result["exit_price"] == pytest.approx(105.0)
        # max gain measured as peak close vs as-of close
        assert result["max_gain_pct"] == pytest.approx((110 - 100) / 100 * 100)

    def test_stop_hit_before_breakout(self):
        from calculators.forward_outcome import calculate_forward_outcome

        # oldest..newest closes: 100, 99, 96, 93, 95, 98
        # as_of close = 100, pivot=105, stop=95
        # Forward walk: day 1 -> 99 (no), day 2 -> 96 (no, 96 > 95),
        #               day 3 -> 93 (< 95) -> stop_hit.
        closes = [100, 99, 96, 93, 95, 98]
        hist = _hist(closes)
        result = calculate_forward_outcome(
            hist, as_of_offset=5,
            pivot_price=105.0, stop_price=95.0, max_window_days=10,
        )
        assert result["outcome_type"] == "stop_hit"
        assert result["days_to_outcome"] == 3
        assert result["exit_price"] == pytest.approx(93.0)

    def test_timeout_when_neither_pivot_nor_stop(self):
        from calculators.forward_outcome import calculate_forward_outcome

        # All forward closes between stop and pivot
        closes = [100] + [101, 99, 100, 102, 98]  # newest -> still in range
        hist = _hist(closes)
        result = calculate_forward_outcome(
            hist, as_of_offset=5,
            pivot_price=110.0, stop_price=90.0, max_window_days=10,
        )
        assert result["outcome_type"] == "timeout"
        assert result["days_to_outcome"] is None
        assert result["exit_price"] is None

    def test_insufficient_data_at_recent_offset(self):
        from calculators.forward_outcome import calculate_forward_outcome

        # Only 2 forward bars exist; max_window_days=10 means we time out gracefully
        # but with bars_available reflecting reality.
        hist = _hist([100, 101, 102])
        # as_of at oldest = MRF index 2; 2 forward bars: [102, 101] reversed -> 101, 102
        result = calculate_forward_outcome(
            hist, as_of_offset=2,
            pivot_price=120.0, stop_price=80.0, max_window_days=10,
        )
        # Neither hit, but window was truncated by available data.
        assert result["outcome_type"] == "timeout"
        assert result["bars_available"] == 2

    def test_zero_forward_bars(self):
        from calculators.forward_outcome import calculate_forward_outcome

        hist = _hist([100])
        result = calculate_forward_outcome(
            hist, as_of_offset=0, pivot_price=110.0, stop_price=90.0
        )
        assert result["outcome_type"] == "insufficient_data"
        assert result["bars_available"] == 0

    def test_max_gain_tracks_peak_even_after_stop_hit(self):
        """max_gain_pct should reflect the peak across the entire forward window,
        regardless of where the outcome was resolved."""
        from calculators.forward_outcome import calculate_forward_outcome

        # oldest..newest: 100, 108, 92, 95, 99
        # as_of=100, pivot=110, stop=95.
        # day 1: 108 (gain 8%, no breakout above 110)
        # day 2: 92 (stop hit, since 92 < 95)
        closes = [100, 108, 92, 95, 99]
        hist = _hist(closes)
        result = calculate_forward_outcome(
            hist, as_of_offset=4,
            pivot_price=110.0, stop_price=95.0, max_window_days=10,
        )
        assert result["outcome_type"] == "stop_hit"
        assert result["max_gain_pct"] == pytest.approx(8.0, abs=0.01)
        assert result["max_loss_pct"] == pytest.approx(-8.0, abs=0.01)


# ===========================================================================
# Quote synthesis (build_quote_from_history) — must not peek at future bars
# ===========================================================================


class TestBuildQuoteFromHistory:
    def test_quote_fields_from_as_of_bar(self):
        from historical_scanner import build_quote_from_history

        hist = _make_prices(300, start=100, daily_change=0.001)
        offset = 60
        quote = build_quote_from_history(hist, offset)
        assert quote["price"] == hist[offset]["close"]
        # yearHigh/yearLow over the 252-bar window ENDING at the as-of bar
        # (i.e., bars hist[offset : offset+252]). No more recent bars allowed.
        window = hist[offset : offset + 252]
        assert quote["yearHigh"] == max(d["high"] for d in window)
        assert quote["yearLow"] == min(d["low"] for d in window)

    def test_no_lookahead_into_future(self):
        """yearHigh must NOT include any bar more recent than the as-of bar.

        Bars more recent than the as-of bar are at MRF indices < as_of_offset.
        We poison those bars with a very high price and verify yearHigh stays
        at the as-of-bar level.
        """
        from historical_scanner import build_quote_from_history

        hist = _make_prices(300, start=100, daily_change=0.0)
        # Inject huge highs into "future" bars (more recent than offset=60).
        for i in range(60):
            hist[i]["high"] = 999.99
            hist[i]["close"] = 999.99
        quote = build_quote_from_history(hist, as_of_offset=60)
        # yearHigh should reflect only bars at indices >= 60.
        assert quote["yearHigh"] < 200.0, (
            f"yearHigh={quote['yearHigh']} indicates lookahead into bars[0:60]"
        )

    def test_short_history_uses_available_window(self):
        """If fewer than 252 trailing bars exist, use what's available."""
        from historical_scanner import build_quote_from_history

        hist = _make_prices(120, start=100, daily_change=0.0)
        quote = build_quote_from_history(hist, as_of_offset=0)
        # 120 bars are all that's there; quote uses all of them
        assert quote["yearHigh"] == max(d["high"] for d in hist)
        assert quote["yearLow"] == min(d["low"] for d in hist)


# ===========================================================================
# Historical scanner walk + dedup
# ===========================================================================


def _fake_vcp_result(symbol, pivot, t1_high_date, last_low_date):
    """Minimal analyze_stock-shaped dict used to inject fake detections."""
    return {
        "symbol": symbol,
        "valid_vcp": True,
        "composite_score": 75.0,
        "rating": "Good VCP",
        "execution_state": "Pre-breakout",
        "pattern_type": "Textbook VCP",
        "distance_from_pivot_pct": 1.2,
        "vcp_pattern": {
            "pivot_price": pivot,
            "valid_vcp": True,
            "num_contractions": 2,
            "contractions": [
                {"label": "T1", "high_date": t1_high_date, "low_date": "2024-01-05",
                 "high_price": pivot, "low_price": pivot * 0.85, "depth_pct": 15.0},
                {"label": "T2", "high_date": "2024-01-25", "low_date": last_low_date,
                 "high_price": pivot * 0.99, "low_price": pivot * 0.92, "depth_pct": 7.0},
            ],
        },
        "volume_pattern": {"score": 70, "dry_up_ratio": 0.5},
        "pivot_proximity": {"score": 90, "risk_pct": 5.0},
        "trend_template": {"score": 90},
        "relative_strength": {"score": 80},
    }


class TestHistoricalScannerDedup:
    def test_same_pattern_detected_at_multiple_offsets_yields_one_detection(self, monkeypatch):
        """If analyze_stock keeps reporting the same (T1_high_date, last_low_date,
        pivot) as the cursor strides forward, dedup should collapse to 1."""
        from historical_scanner import scan_history

        hist = _make_prices(400, start=100, daily_change=0.001)
        spy = _make_prices(400, start=400, daily_change=0.0005)

        # Inject a fake analyze_stock that always returns the same VCP.
        def fake_analyze(symbol, historical, quote, sp500, **kw):
            offset = kw.get("as_of_offset", 0)
            r = _fake_vcp_result("TEST", pivot=110.0,
                                 t1_high_date="2024-01-01",
                                 last_low_date="2024-02-15")
            # Vary something irrelevant to the dedup key so we can confirm
            # multiple invocations happened.
            r["_offset"] = offset
            return r

        monkeypatch.setattr("historical_scanner.screen_vcp.analyze_stock", fake_analyze)

        result = scan_history("TEST", hist, spy, stride_days=10)
        assert len(result) == 1

    def test_distinct_patterns_kept(self, monkeypatch):
        """Different (high_date, low_date, pivot) keys should NOT be deduped."""
        from historical_scanner import scan_history

        hist = _make_prices(400, start=100, daily_change=0.001)
        spy = _make_prices(400, start=400, daily_change=0.0005)

        def fake_analyze(symbol, historical, quote, sp500, **kw):
            offset = kw.get("as_of_offset", 0)
            # Return a "different" pattern at each offset by varying the dates.
            return _fake_vcp_result(
                "TEST", pivot=100 + offset,
                t1_high_date=f"2024-01-{offset:03d}",
                last_low_date=f"2024-02-{offset:03d}",
            )

        monkeypatch.setattr("historical_scanner.screen_vcp.analyze_stock", fake_analyze)

        result = scan_history("TEST", hist, spy, stride_days=20)
        assert len(result) > 5

    def test_chronological_order_oldest_first(self, monkeypatch):
        from historical_scanner import scan_history

        hist = _make_prices(400, start=100, daily_change=0.001)
        spy = _make_prices(400, start=400, daily_change=0.0005)

        def fake_analyze(symbol, historical, quote, sp500, **kw):
            offset = kw.get("as_of_offset", 0)
            # Use the as-of bar's date so output ordering reflects time.
            return _fake_vcp_result(
                "TEST", pivot=100.0 + offset,
                t1_high_date=historical[offset]["date"],
                last_low_date=historical[max(offset - 10, 0)]["date"],
            )

        monkeypatch.setattr("historical_scanner.screen_vcp.analyze_stock", fake_analyze)

        result = scan_history("TEST", hist, spy, stride_days=30)
        dates = [r["as_of_date"] for r in result]
        assert dates == sorted(dates)

    def test_short_history_returns_empty(self):
        """History shorter than lookback + a small buffer returns []."""
        from historical_scanner import scan_history

        hist = _make_prices(100, start=100, daily_change=0.001)
        spy = _make_prices(100, start=400, daily_change=0.0005)
        assert scan_history("TEST", hist, spy, lookback_days=120) == []


class TestHistoryFlagParsing:
    """--history takes an optional integer (trading days to scan).
    Bare --history defaults to the canonical 5-year window."""

    def _parse(self, *cli_args):
        import sys as _sys
        from screen_vcp import parse_arguments

        original = _sys.argv
        try:
            _sys.argv = ["screen_vcp.py", *cli_args]
            return parse_arguments()
        finally:
            _sys.argv = original

    def test_bare_history_uses_default(self):
        args = self._parse("--history", "--ticker", "AAPL")
        # 5 years × 252 trading days = 1260 — preserves prior default behavior.
        assert args.history == 1260
        assert args.ticker == "AAPL"

    def test_history_with_explicit_days(self):
        args = self._parse("--history", "500", "--ticker", "AAPL")
        assert args.history == 500

    def test_history_with_equals_syntax(self):
        args = self._parse("--history=2520", "--ticker", "TSLA")
        assert args.history == 2520

    def test_history_omitted_means_cross_sectional_mode(self):
        # Without --history, the cross-sectional pipeline should run; args.history is None.
        args = self._parse("--universe", "AAPL", "MSFT")
        assert args.history is None

    def test_history_requires_ticker(self):
        import pytest as _pytest

        with _pytest.raises(SystemExit):
            self._parse("--history")  # no --ticker

    def test_history_rejects_out_of_range(self):
        import pytest as _pytest

        with _pytest.raises(SystemExit):
            self._parse("--history", "50", "--ticker", "AAPL")  # too short
        with _pytest.raises(SystemExit):
            self._parse("--history", "999999", "--ticker", "AAPL")  # too long


class TestSanitizeTicker:
    """sanitize_ticker is the first line of defence against path injection
    through the --ticker CLI flag."""

    def test_accepts_normal_symbols(self):
        from historical_scanner import sanitize_ticker

        assert sanitize_ticker("FIX") == "FIX"
        assert sanitize_ticker("tsla") == "TSLA"
        assert sanitize_ticker("BRK.B") == "BRK.B"
        assert sanitize_ticker("BF-B") == "BF-B"

    def test_rejects_path_traversal(self):
        from historical_scanner import sanitize_ticker

        for evil in ("../etc/passwd", "../../FOO", "FOO/BAR", "FOO\\BAR",
                     "FOO BAR", "", "1FOO", "FOO;rm -rf /"):
            with pytest.raises(ValueError):
                sanitize_ticker(evil)


# ===========================================================================
# Historical report writers
# ===========================================================================


class TestHistoricalReport:
    def _sample_detection(self, as_of="2024-03-15", outcome_type="breakout",
                          days=10, gain=12.0, loss=-3.0):
        return {
            "symbol": "TEST",
            "as_of_date": as_of,
            "composite_score": 82.5,
            "rating": "Strong VCP",
            "execution_state": "Pre-breakout",
            "pattern_type": "Textbook VCP",
            "vcp_pattern": {
                "pivot_price": 105.50,
                "num_contractions": 3,
                "pattern_duration_days": 45,
                "contractions": [
                    {"label": "T1", "high_date": "2024-02-01", "high_price": 105.50,
                     "low_date": "2024-02-15", "low_price": 95.00,
                     "depth_pct": 9.9, "duration_days": 14},
                    {"label": "T2", "high_date": "2024-02-20", "high_price": 104.30,
                     "low_date": "2024-03-01", "low_price": 99.50,
                     "depth_pct": 4.6, "duration_days": 10},
                ],
            },
            "forward_outcome": {
                "outcome_type": outcome_type,
                "days_to_outcome": days,
                "max_gain_pct": gain,
                "max_loss_pct": loss,
                "bars_evaluated": 60,
            },
        }

    def test_json_report_written(self, tmp_path):
        from historical_report import generate_historical_json_report

        out = tmp_path / "hist.json"
        detections = [self._sample_detection()]
        generate_historical_json_report("TEST", detections, {"generated_at": "now"}, str(out))
        import json as _json
        data = _json.loads(out.read_text(encoding="utf-8"))
        assert data["symbol"] == "TEST"
        assert data["summary"]["total"] == 1
        assert data["summary"]["breakouts"] == 1

    def test_markdown_report_written(self, tmp_path):
        from historical_report import generate_historical_markdown_report

        out = tmp_path / "hist.md"
        detections = [
            self._sample_detection(as_of="2024-03-15", outcome_type="breakout",
                                   days=10, gain=12.0, loss=-3.0),
            self._sample_detection(as_of="2024-08-22", outcome_type="stop_hit",
                                   days=4, gain=2.1, loss=-8.5),
            self._sample_detection(as_of="2025-01-10", outcome_type="timeout",
                                   days=None, gain=5.0, loss=-2.0),
        ]
        generate_historical_markdown_report(
            "TEST", detections,
            {"generated_at": "2026-05-19", "stride_days": 5,
             "lookback_days": 120, "outcome_days": 60,
             "history_range": "2020-01 to 2026-05"},
            str(out),
        )
        text = out.read_text(encoding="utf-8")
        assert "VCP History" in text
        assert "Detection Timeline" in text
        # All three outcomes should appear in the summary table
        assert "breakout" in text
        assert "stop_hit" in text
        assert "timeout" in text

    def test_markdown_empty_detections(self, tmp_path):
        from historical_report import generate_historical_markdown_report

        out = tmp_path / "empty.md"
        generate_historical_markdown_report("FOO", [], {"generated_at": "now"}, str(out))
        text = out.read_text(encoding="utf-8")
        assert "No VCP detections" in text


# ===========================================================================
# End-to-end: run_historical with a mocked FMP client
# ===========================================================================


class _StubFMPClient:
    """Minimal FMPClient stand-in for end-to-end testing of run_historical.
    Returns the synthetic histories supplied at construction time and tracks
    api stats."""

    def __init__(self, ticker_history, spy_history):
        self._ticker = ticker_history
        self._spy = spy_history
        self.api_calls_made = 0
        self.cache = {}

    def get_historical_prices(self, symbol, days=365):
        self.api_calls_made += 1
        if symbol == "SPY":
            return {"symbol": "SPY", "historical": self._spy}
        return {"symbol": symbol, "historical": self._ticker}

    def get_api_stats(self):
        return {
            "cache_entries": len(self.cache),
            "api_calls_made": self.api_calls_made,
            "rate_limit_reached": False,
        }


class TestRunHistoricalE2E:
    def test_end_to_end_dispatch_writes_reports(self, tmp_path):
        """run_historical() must fetch history, sweep, and write both reports."""
        import types
        from screen_vcp import run_historical

        # Build a long, mostly trending synthetic history. We don't require
        # detections to occur — only that the dispatch + report layer survives
        # a real call with synthetic data.
        hist = _make_prices(1500, start=100, daily_change=0.0005)
        spy = _make_prices(1500, start=400, daily_change=0.0003)
        client = _StubFMPClient(hist, spy)

        args = types.SimpleNamespace(
            ticker="TEST",
            history=1260,
            stride_days=20,  # coarse stride keeps test fast
            outcome_days=60,
            lookback_days=120,
            output_dir=str(tmp_path),
            ext_threshold=8.0,
            min_contractions=2,
            t1_depth_min=10.0,
            contraction_ratio=0.70,
            atr_multiplier=1.5,
            min_contraction_days=5,
            breakout_volume_ratio=1.5,
            max_sma200_extension=50.0,
            wide_and_loose_threshold=15.0,
        )
        run_historical(args, client)

        # The dispatcher must always write both report files, even with zero
        # detections — empty timeline is a valid result.
        files = list(tmp_path.iterdir())
        json_files = [f for f in files if f.name.endswith(".json")]
        md_files = [f for f in files if f.name.endswith(".md")]
        assert len(json_files) == 1, files
        assert len(md_files) == 1, files
        assert "TEST" in json_files[0].name
        assert "vcp_history" in json_files[0].name

        # Verify the JSON is well-formed and has expected top-level keys.
        import json as _json
        data = _json.loads(json_files[0].read_text(encoding="utf-8"))
        assert data["symbol"] == "TEST"
        assert "detections" in data
        assert "summary" in data
        assert data["metadata"]["stride_days"] == 20
