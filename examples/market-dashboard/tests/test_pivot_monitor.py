# tests/test_pivot_monitor.py
import sys
import json
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock
from pivot_monitor import PivotWatchlistMonitor


def make_monitor(tmp_path: Path, search_fn=None):
    alpaca = MagicMock()
    alpaca.is_configured = False
    settings = MagicMock()
    settings.load.return_value = {
        "mode": "auto", "default_risk_pct": 1.0,
        "max_positions": 5, "max_position_size_pct": 10.0,
        "min_volume_ratio": 1.5,
        "avoid_open_close_minutes": 0,   # 0 = disabled — keeps existing tests green
        "breadth_threshold_pct": 60.0,
        "breadth_size_reduction_pct": 0.0,  # 0 = disabled — keeps existing tests green
    }
    return PivotWatchlistMonitor(
        alpaca_client=alpaca,
        settings_manager=settings,
        cache_dir=tmp_path,
        _search_fn=search_fn or (lambda s: []),
    )


def write_vcp_cache(tmp_path: Path, results: list):
    (tmp_path / "vcp-screener.json").write_text(json.dumps({
        "results": results, "generated_at": "2026-03-21T09:35:00",
    }))


def test_load_candidates_returns_empty_when_no_cache():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        assert monitor.load_candidates() == []


def test_load_candidates_parses_vcp_json():
    with tempfile.TemporaryDirectory() as d:
        write_vcp_cache(Path(d), [
            {"symbol": "AAPL", "vcp_pattern": {"pivot_price": 155.0}},
            {"symbol": "TSLA", "vcp_pattern": {"pivot_price": 200.0}},
        ])
        monitor = make_monitor(Path(d))
        candidates = monitor.load_candidates()
        assert len(candidates) == 2
        assert candidates[0] == {"symbol": "AAPL", "pivot_price": 155.0}
        assert candidates[1] == {"symbol": "TSLA", "pivot_price": 200.0}


def test_load_candidates_skips_entries_without_pivot():
    with tempfile.TemporaryDirectory() as d:
        write_vcp_cache(Path(d), [
            {"symbol": "AAPL", "vcp_pattern": {}},  # no pivot_price
            {"symbol": "TSLA", "vcp_pattern": {"pivot_price": 200.0}},
        ])
        monitor = make_monitor(Path(d))
        assert len(monitor.load_candidates()) == 1


def test_stage1_tags_clear_when_no_news():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        result = monitor.run_stage1_check([{"symbol": "AAPL", "pivot_price": 150.0}])
        assert result[0]["confidence_tag"] == "CLEAR"


def test_stage1_tags_blocked_on_negative_news():
    def search(sym):
        return ["AAPL: SEC investigation confirmed, stock halted"]
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d), search_fn=search)
        result = monitor.run_stage1_check([{"symbol": "AAPL", "pivot_price": 150.0}])
        assert result[0]["confidence_tag"] == "BLOCKED"


def test_stage1_tags_high_conviction_on_positive_news():
    def search(sym):
        return ["AAPL: analyst upgrade to buy, strong guidance beat"]
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d), search_fn=search)
        result = monitor.run_stage1_check([{"symbol": "AAPL", "pivot_price": 150.0}])
        assert result[0]["confidence_tag"] == "HIGH_CONVICTION"


def test_stage1_tags_uncertain_for_upcoming_earnings():
    with tempfile.TemporaryDirectory() as d:
        from datetime import date, timedelta
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        (Path(d) / "earnings-calendar.json").write_text(json.dumps({
            "events": [{"symbol": "AAPL", "date": tomorrow + "T07:00:00"}]
        }))
        monitor = make_monitor(Path(d))
        result = monitor.run_stage1_check([{"symbol": "AAPL", "pivot_price": 150.0}])
        assert result[0]["confidence_tag"] == "UNCERTAIN"


def test_stage1_applies_rule_store_rules():
    from learning.rule_store import RuleStore
    with tempfile.TemporaryDirectory() as d:
        store = RuleStore(Path(d) / "learned_rules.json")
        store.save({"rules": [{
            "id": "r1",
            "condition": {"confidence_tag": "UNCERTAIN"},
            "action": {"set_confidence_tag": "BLOCKED"},
            "confidence": 0.8, "sample_count": 10, "active": True,
        }]})
        from datetime import date, timedelta
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        (Path(d) / "earnings-calendar.json").write_text(json.dumps({
            "events": [{"symbol": "TSLA", "date": tomorrow + "T07:00:00"}]
        }))
        alpaca = MagicMock(); alpaca.is_configured = False
        settings = MagicMock(); settings.load.return_value = {
            "mode": "auto", "default_risk_pct": 1.0, "max_positions": 5, "max_position_size_pct": 10.0,
        }
        monitor = PivotWatchlistMonitor(
            alpaca_client=alpaca, settings_manager=settings,
            cache_dir=Path(d), rule_store=store,
        )
        result = monitor.run_stage1_check([{"symbol": "TSLA", "pivot_price": 200.0}])
        # UNCERTAIN upgraded to BLOCKED by the rule
        assert result[0]["confidence_tag"] == "BLOCKED"


# ── Breakout detection and guard rails ─────────────────────────────────────

def test_check_breakout_fires_for_clear_candidate():
    """When price >= pivot × 1.001, a CLEAR candidate should trigger _fire_order."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.is_configured = True
        monitor._alpaca.get_positions.return_value = []
        monitor._alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
        monitor._alpaca.get_last_price.return_value = 156.0
        monitor._alpaca.place_bracket_order.return_value = {
            "id": "ord1", "symbol": "AAPL", "qty": 10.0, "limit_price": 156.0, "status": "new"
        }

        bar = MagicMock()
        bar.symbol = "AAPL"
        bar.close = 156.0  # 156 >= 155 × 1.001 = 155.155 ✓

        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "CLEAR"}]
        monitor._candidates = candidates

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._alpaca.place_bracket_order.assert_called_once()
        assert "AAPL" in monitor._triggered


def test_check_breakout_skips_blocked_candidate():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.is_configured = True
        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "BLOCKED"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._alpaca.place_bracket_order.assert_not_called()


def test_check_breakout_skips_when_price_below_buffer():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.is_configured = True
        bar = MagicMock(); bar.symbol = "AAPL"
        bar.close = 155.0  # exactly at pivot, not above buffer (needs > 155.155)
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "CLEAR"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._alpaca.place_bracket_order.assert_not_called()


def test_guard_rail_max_positions_blocks_order():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.is_configured = True
        # 5 positions = max_positions → blocked
        monitor._alpaca.get_positions.return_value = [{}] * 5

        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "CLEAR"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._alpaca.place_bracket_order.assert_not_called()


def test_guard_rail_outside_market_hours_blocks_order():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.is_configured = True
        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "CLEAR"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: False
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._alpaca.place_bracket_order.assert_not_called()


def test_uncertain_with_negative_stage2_blocks_order():
    def negative_search(sym):
        return ["AAPL: SEC investigation launched"]
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d), search_fn=negative_search)
        monitor._alpaca.is_configured = True
        monitor._alpaca.get_positions.return_value = []
        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "UNCERTAIN"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._alpaca.place_bracket_order.assert_not_called()


def test_high_conviction_uses_1_5x_risk():
    """HIGH_CONVICTION sizing passes risk_pct × 1.5 to qty calculation."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.is_configured = True
        monitor._alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
        # account=100k, risk=1%, entry=100, stop=97 → risk_per_share=3, dollar_risk=1000 → 333 shares
        # HIGH_CONVICTION: risk=1.5%, dollar_risk=1500 → 500 shares
        qty_normal = monitor._calc_qty(100.0, 97.0, high_conviction=False)
        qty_hc = monitor._calc_qty(100.0, 97.0, high_conviction=True)
        assert qty_hc > qty_normal


# ── New tests: multiplier lookup + log field fixes ──

def make_monitor_with_store(tmp_path: Path):
    from learning.multiplier_store import MultiplierStore
    alpaca = MagicMock()
    alpaca.is_configured = True
    settings = MagicMock()
    settings.load.return_value = {
        "mode": "auto", "default_risk_pct": 1.0,
        "max_positions": 5, "max_position_size_pct": 10.0,
        "min_volume_ratio": 1.5,
        "avoid_open_close_minutes": 0,
        "breadth_threshold_pct": 60.0,
        "breadth_size_reduction_pct": 0.0,
    }
    mstore = MultiplierStore(
        learned_file=tmp_path / "learned_multipliers.json",
        seed_file=tmp_path / "seed_multipliers.json",
    )
    monitor = PivotWatchlistMonitor(
        alpaca_client=alpaca,
        settings_manager=settings,
        cache_dir=tmp_path,
        multiplier_store=mstore,
    )
    return monitor, alpaca


def test_fire_order_passes_explicit_take_profit_price():
    """_fire_order must pass take_profit_price explicitly, not rely on 2:1 default."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        monitor, alpaca = make_monitor_with_store(tmp)
        alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
        alpaca.get_positions.return_value = []
        alpaca.get_last_price.return_value = 100.0
        alpaca.place_bracket_order.return_value = {
            "id": "ord1", "symbol": "AAPL", "qty": 10.0, "limit_price": 100.0, "status": "new"
        }
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: True
        monitor._fire_order({"symbol": "AAPL", "pivot_price": 99.0}, "CLEAR")

        call_kwargs = alpaca.place_bracket_order.call_args
        assert call_kwargs is not None
        assert "take_profit_price" in call_kwargs.kwargs
        assert call_kwargs.kwargs["take_profit_price"] is not None
        assert call_kwargs.kwargs["take_profit_price"] > 100.0


def test_log_trade_stores_screener_field():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        monitor, alpaca = make_monitor_with_store(tmp)
        alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
        monitor._log_trade(
            {"symbol": "AAPL", "pivot_price": 99.0}, "ord1", 100.0, 97.0, 10, "CLEAR"
        )
        trades = json.loads((tmp / "auto_trades.json").read_text())["trades"]
        assert trades[0]["screener"] == "vcp"


def test_log_trade_stores_regime_as_string():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        (tmp / "macro-regime-detector.json").write_text(json.dumps({
            "regime": {"current_regime": "bull", "score": 75}
        }))
        monitor, alpaca = make_monitor_with_store(tmp)
        alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
        monitor._log_trade(
            {"symbol": "AAPL", "pivot_price": 99.0}, "ord1", 100.0, 97.0, 10, "CLEAR"
        )
        trades = json.loads((tmp / "auto_trades.json").read_text())["trades"]
        assert trades[0]["regime"] == "bull"
        assert isinstance(trades[0]["regime"], str)
        assert "macro_regime" not in trades[0]


# ── Task 4: Capital protection guard rail tests ──────────────────────────


def make_monitor_with_trackers(tmp_path, pdt_tracker=None, drawdown_tracker=None, earnings_blackout=None):
    alpaca = MagicMock()
    alpaca.is_configured = True
    alpaca.get_positions.return_value = []
    alpaca.get_account.return_value = {"portfolio_value": 100_000.0}
    settings = MagicMock()
    settings.load.return_value = {
        "mode": "auto",
        "default_risk_pct": 1.0,
        "max_positions": 5,
        "max_position_size_pct": 10.0,
        "max_weekly_drawdown_pct": 10.0,
        "max_daily_loss_pct": 5.0,
        "earnings_blackout_days": 5,
        "min_volume_ratio": 1.5,
        "avoid_open_close_minutes": 0,
        "breadth_threshold_pct": 60.0,
        "breadth_size_reduction_pct": 0.0,
    }
    return PivotWatchlistMonitor(
        alpaca_client=alpaca,
        settings_manager=settings,
        cache_dir=Path(tmp_path),
        pdt_tracker=pdt_tracker,
        drawdown_tracker=drawdown_tracker,
        earnings_blackout=earnings_blackout,
    )


def test_pdt_0_slots_blocks_all_tags():
    with tempfile.TemporaryDirectory() as d:
        from learning.pdt_tracker import PDTTracker
        from datetime import date
        tracker = PDTTracker(trades_file=Path(d) / "pdt.json")
        today = date.today()
        for sym in ("A", "B", "C"):
            tracker.record_day_trade(sym, today)
        monitor = make_monitor_with_trackers(Path(d), pdt_tracker=tracker)
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: True
        allowed, reason = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="HIGH_CONVICTION")
        assert allowed is False
        assert "PDT" in reason


def test_pdt_1_slot_blocks_clear_allows_high_conviction():
    with tempfile.TemporaryDirectory() as d:
        from learning.pdt_tracker import PDTTracker
        from datetime import date
        tracker = PDTTracker(trades_file=Path(d) / "pdt.json")
        today = date.today()
        for sym in ("A", "B"):
            tracker.record_day_trade(sym, today)
        monitor = make_monitor_with_trackers(Path(d), pdt_tracker=tracker)
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: True
        allowed_clear, _ = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="CLEAR")
        allowed_hc, _ = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="HIGH_CONVICTION")
        assert allowed_clear is False
        assert allowed_hc is True


def test_pdt_2_slots_blocks_uncertain():
    with tempfile.TemporaryDirectory() as d:
        from learning.pdt_tracker import PDTTracker
        from datetime import date
        tracker = PDTTracker(trades_file=Path(d) / "pdt.json")
        today = date.today()
        tracker.record_day_trade("A", today)
        monitor = make_monitor_with_trackers(Path(d), pdt_tracker=tracker)
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: True
        allowed_uncertain, _ = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="UNCERTAIN")
        allowed_clear, _ = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="CLEAR")
        assert allowed_uncertain is False
        assert allowed_clear is True


def test_drawdown_weekly_limit_blocks_guard():
    with tempfile.TemporaryDirectory() as d:
        from learning.drawdown_tracker import DrawdownTracker
        from datetime import date
        tracker = DrawdownTracker(state_file=Path(d) / "dd.json")
        monday = date(2026, 3, 16)
        tracker.update(10000.0, monday)
        alpaca = MagicMock()
        alpaca.is_configured = True
        alpaca.get_positions.return_value = []
        alpaca.get_account.return_value = {"portfolio_value": 8900.0}
        settings = MagicMock()
        settings.load.return_value = {
            "mode": "auto", "default_risk_pct": 1.0,
            "max_positions": 5, "max_position_size_pct": 10.0,
            "max_weekly_drawdown_pct": 10.0, "max_daily_loss_pct": 5.0,
            "earnings_blackout_days": 5,
        }
        monitor = PivotWatchlistMonitor(
            alpaca_client=alpaca,
            settings_manager=settings,
            cache_dir=Path(d),
            drawdown_tracker=tracker,
        )
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: True
        allowed, reason = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="CLEAR")
        assert allowed is False
        assert "drawdown" in reason.lower()


def test_drawdown_disabled_at_100_pct_always_allows():
    with tempfile.TemporaryDirectory() as d:
        from learning.drawdown_tracker import DrawdownTracker
        from datetime import date
        tracker = DrawdownTracker(state_file=Path(d) / "dd.json")
        monday = date(2026, 3, 16)
        tracker.update(10000.0, monday)
        alpaca = MagicMock()
        alpaca.is_configured = True
        alpaca.get_positions.return_value = []
        alpaca.get_account.return_value = {"portfolio_value": 1.0}
        settings = MagicMock()
        settings.load.return_value = {
            "mode": "auto", "default_risk_pct": 1.0,
            "max_positions": 5, "max_position_size_pct": 10.0,
            "max_weekly_drawdown_pct": 100.0, "max_daily_loss_pct": 100.0,
            "earnings_blackout_days": 0,
        }
        monitor = PivotWatchlistMonitor(
            alpaca_client=alpaca,
            settings_manager=settings,
            cache_dir=Path(d),
            drawdown_tracker=tracker,
        )
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: True
        allowed, _ = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="CLEAR")
        assert allowed is True


def test_earnings_blackout_blocks_when_reporting_soon():
    with tempfile.TemporaryDirectory() as d:
        from learning.earnings_blackout import EarningsBlackout
        from datetime import date, timedelta
        import json as _json
        cache = Path(d)
        today = date.today()
        earnings_in_3_days = (today + timedelta(days=3)).isoformat() + "T07:00:00"
        (cache / "earnings-calendar.json").write_text(
            _json.dumps({"events": [{"symbol": "AAPL", "date": earnings_in_3_days}]})
        )
        eb = EarningsBlackout(cache_dir=cache)
        monitor = make_monitor_with_trackers(Path(d), earnings_blackout=eb)
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: True
        allowed, reason = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="CLEAR")
        assert allowed is False
        assert "earnings" in reason.lower()


# ── Task 1: Volume confirmation tests ────────────────────────────────────────

def test_volume_above_threshold_allowed(tmp_path):
    monitor = make_monitor(tmp_path)
    monitor._alpaca.get_current_volume = lambda sym: 200_000
    candidate = {"symbol": "AAPL", "pivot_price": 100.0, "confidence_tag": "CLEAR", "avg_volume_20d": 100_000}
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    monitor._alpaca.get_positions.return_value = []
    allowed, reason = monitor._guard_rails_allow(candidate, tag="CLEAR")
    assert allowed is True

def test_volume_below_threshold_blocked(tmp_path):
    monitor = make_monitor(tmp_path)
    monitor._alpaca.get_current_volume = lambda sym: 100_000
    candidate = {"symbol": "AAPL", "pivot_price": 100.0, "confidence_tag": "CLEAR", "avg_volume_20d": 200_000}
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    monitor._alpaca.get_positions.return_value = []
    allowed, reason = monitor._guard_rails_allow(candidate, tag="CLEAR")
    assert allowed is False
    assert "volume" in reason.lower()

def test_volume_data_missing_fails_open(tmp_path):
    monitor = make_monitor(tmp_path)
    monitor._alpaca.get_current_volume = lambda sym: (_ for _ in ()).throw(Exception("API error"))
    candidate = {"symbol": "AAPL", "pivot_price": 100.0, "confidence_tag": "CLEAR", "avg_volume_20d": 100_000}
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    monitor._alpaca.get_positions.return_value = []
    allowed, _ = monitor._guard_rails_allow(candidate, tag="CLEAR")
    assert allowed is True

def test_volume_ratio_zero_always_allows(tmp_path):
    from unittest.mock import MagicMock
    from pivot_monitor import PivotWatchlistMonitor
    alpaca = MagicMock()
    alpaca.is_configured = True
    alpaca.get_positions.return_value = []
    settings = MagicMock()
    settings.load.return_value = {
        "mode": "auto", "default_risk_pct": 1.0,
        "max_positions": 5, "max_position_size_pct": 10.0,
        "min_volume_ratio": 0,
        "avoid_open_close_minutes": 0,
        "breadth_threshold_pct": 60.0,
        "breadth_size_reduction_pct": 0.0,
        "max_weekly_drawdown_pct": 100.0, "max_daily_loss_pct": 100.0,
        "earnings_blackout_days": 0,
    }
    monitor = PivotWatchlistMonitor(alpaca_client=alpaca, settings_manager=settings, cache_dir=tmp_path)
    alpaca.get_current_volume = lambda sym: 1
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    candidate = {"symbol": "AAPL", "pivot_price": 100.0, "confidence_tag": "CLEAR", "avg_volume_20d": 1_000_000}
    allowed, _ = monitor._guard_rails_allow(candidate, tag="CLEAR")
    assert allowed is True


# ── Task 2: Time-of-day soft lock tests ──────────────────────────────────────

from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

def make_et_time(hour, minute):
    return datetime(2026, 3, 22, hour, minute, 0, tzinfo=ZoneInfo("America/New_York"))

def test_time_lock_clear_blocked_in_open_window(tmp_path):
    from unittest.mock import MagicMock, patch
    from pivot_monitor import PivotWatchlistMonitor
    alpaca = MagicMock()
    alpaca.is_configured = True
    alpaca.get_positions.return_value = []
    settings = MagicMock()
    settings.load.return_value = {
        "mode": "auto", "default_risk_pct": 1.0,
        "max_positions": 5, "max_position_size_pct": 10.0,
        "min_volume_ratio": 0, "avoid_open_close_minutes": 30,
        "breadth_threshold_pct": 60.0, "breadth_size_reduction_pct": 0.0,
        "max_weekly_drawdown_pct": 100.0, "max_daily_loss_pct": 100.0,
        "earnings_blackout_days": 0,
    }
    monitor = PivotWatchlistMonitor(alpaca_client=alpaca, settings_manager=settings, cache_dir=tmp_path)
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    candidate = {"symbol": "AAPL", "pivot_price": 100.0, "confidence_tag": "CLEAR"}
    with patch("pivot_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = make_et_time(9, 35)
        allowed, reason = monitor._guard_rails_allow(candidate, tag="CLEAR")
    assert allowed is False
    assert "time-of-day" in reason.lower()

def test_time_lock_high_conviction_allowed_in_open_window(tmp_path):
    from unittest.mock import MagicMock, patch
    from pivot_monitor import PivotWatchlistMonitor
    alpaca = MagicMock()
    alpaca.is_configured = True
    alpaca.get_positions.return_value = []
    settings = MagicMock()
    settings.load.return_value = {
        "mode": "auto", "default_risk_pct": 1.0,
        "max_positions": 5, "max_position_size_pct": 10.0,
        "min_volume_ratio": 0, "avoid_open_close_minutes": 30,
        "breadth_threshold_pct": 60.0, "breadth_size_reduction_pct": 0.0,
        "max_weekly_drawdown_pct": 100.0, "max_daily_loss_pct": 100.0,
        "earnings_blackout_days": 0,
    }
    monitor = PivotWatchlistMonitor(alpaca_client=alpaca, settings_manager=settings, cache_dir=tmp_path)
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    candidate = {"symbol": "AAPL", "pivot_price": 100.0, "confidence_tag": "HIGH_CONVICTION"}
    with patch("pivot_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = make_et_time(9, 35)
        allowed, _ = monitor._guard_rails_allow(candidate, tag="HIGH_CONVICTION")
    assert allowed is True

def test_time_lock_clear_allowed_outside_window(tmp_path):
    from unittest.mock import MagicMock, patch
    from pivot_monitor import PivotWatchlistMonitor
    alpaca = MagicMock()
    alpaca.is_configured = True
    alpaca.get_positions.return_value = []
    settings = MagicMock()
    settings.load.return_value = {
        "mode": "auto", "default_risk_pct": 1.0,
        "max_positions": 5, "max_position_size_pct": 10.0,
        "min_volume_ratio": 0, "avoid_open_close_minutes": 30,
        "breadth_threshold_pct": 60.0, "breadth_size_reduction_pct": 0.0,
        "max_weekly_drawdown_pct": 100.0, "max_daily_loss_pct": 100.0,
        "earnings_blackout_days": 0,
    }
    monitor = PivotWatchlistMonitor(alpaca_client=alpaca, settings_manager=settings, cache_dir=tmp_path)
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    candidate = {"symbol": "AAPL", "pivot_price": 100.0, "confidence_tag": "CLEAR"}
    with patch("pivot_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = make_et_time(11, 0)
        allowed, _ = monitor._guard_rails_allow(candidate, tag="CLEAR")
    assert allowed is True

def test_time_lock_disabled_when_zero(tmp_path):
    from unittest.mock import MagicMock, patch
    from pivot_monitor import PivotWatchlistMonitor
    alpaca = MagicMock()
    alpaca.is_configured = True
    alpaca.get_positions.return_value = []
    settings = MagicMock()
    settings.load.return_value = {
        "mode": "auto", "default_risk_pct": 1.0,
        "max_positions": 5, "max_position_size_pct": 10.0,
        "min_volume_ratio": 0, "avoid_open_close_minutes": 0,
        "breadth_threshold_pct": 60.0, "breadth_size_reduction_pct": 0.0,
        "max_weekly_drawdown_pct": 100.0, "max_daily_loss_pct": 100.0,
        "earnings_blackout_days": 0,
    }
    monitor = PivotWatchlistMonitor(alpaca_client=alpaca, settings_manager=settings, cache_dir=tmp_path)
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    candidate = {"symbol": "AAPL", "pivot_price": 100.0, "confidence_tag": "CLEAR"}
    with patch("pivot_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = make_et_time(9, 31)
        allowed, _ = monitor._guard_rails_allow(candidate, tag="CLEAR")
    assert allowed is True


# ── Task 3: Breadth-based size reduction tests ───────────────────────────────

import json

def write_breadth_cache(tmp_path, pct_above_50ma):
    (tmp_path / "market-breadth.json").write_text(json.dumps({
        "pct_above_50ma": pct_above_50ma,
        "generated_at": "2026-03-22T09:35:00",
    }))

def test_breadth_above_threshold_full_size(tmp_path):
    write_breadth_cache(tmp_path, 70.0)
    monitor = make_monitor(tmp_path)
    monitor._settings.load.return_value["breadth_threshold_pct"] = 60.0
    monitor._settings.load.return_value["breadth_size_reduction_pct"] = 50.0
    result = monitor._get_breadth_multiplier()
    assert result == 1.0

def test_breadth_below_threshold_reduces_size(tmp_path):
    write_breadth_cache(tmp_path, 45.0)
    monitor = make_monitor(tmp_path)
    monitor._settings.load.return_value["breadth_threshold_pct"] = 60.0
    monitor._settings.load.return_value["breadth_size_reduction_pct"] = 50.0
    result = monitor._get_breadth_multiplier()
    assert result == 0.5

def test_breadth_cache_missing_returns_full_size(tmp_path):
    monitor = make_monitor(tmp_path)
    result = monitor._get_breadth_multiplier()
    assert result == 1.0

def test_breadth_reduction_zero_disables_filter(tmp_path):
    write_breadth_cache(tmp_path, 10.0)
    monitor = make_monitor(tmp_path)
    monitor._settings.load.return_value["breadth_threshold_pct"] = 60.0
    monitor._settings.load.return_value["breadth_size_reduction_pct"] = 0.0
    result = monitor._get_breadth_multiplier()
    assert result == 1.0


# ── Task 2: Exit management orchestrator tests ────────────────────────────────

import os


def write_auto_trades(tmp_path, trades):
    (tmp_path / "auto_trades.json").write_text(json.dumps({"trades": trades}, indent=2))


def test_check_exit_management_skips_when_no_trades_file():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        try:
            monitor._check_exit_management()
        finally:
            pm._market_is_open_now = original


def test_check_exit_management_skips_outside_market_hours():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        write_auto_trades(Path(d), [{"symbol": "AAPL", "entry_price": 100.0, "stop_price": 97.0, "qty": 10, "outcome": None, "stop_order_id": "ord1", "entry_time": "2026-03-20T14:00:00+00:00"}])
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: False
        called = []
        monitor._apply_trailing_stop = lambda t, s: called.append("trailing") or False
        monitor._apply_partial_exit = lambda t, s: called.append("partial") or False
        monitor._apply_time_stop = lambda t, s: called.append("time") or False
        monitor._check_exit_management()
        assert called == []


def test_check_exit_management_skips_closed_trades():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        write_auto_trades(Path(d), [{"symbol": "AAPL", "entry_price": 100.0, "stop_price": 97.0, "qty": 10, "outcome": "win", "stop_order_id": "ord1", "entry_time": "2026-03-15T14:00:00+00:00"}])
        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        called = []
        monitor._apply_trailing_stop = lambda t, s: called.append("trailing") or False
        try:
            monitor._check_exit_management()
        finally:
            pm._market_is_open_now = original
        assert called == []


def test_check_exit_management_writes_file_when_changed():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        monitor = make_monitor(tmp)
        write_auto_trades(tmp, [{"symbol": "AAPL", "entry_price": 100.0, "stop_price": 97.0, "qty": 10, "outcome": None, "stop_order_id": "ord1", "entry_time": "2026-03-20T14:00:00+00:00"}])
        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        def fake_trailing(trade, settings):
            trade["stop_price"] = 100.0
            return True
        monitor._apply_trailing_stop = fake_trailing
        monitor._apply_partial_exit = lambda t, s: False
        monitor._apply_time_stop = lambda t, s: False
        try:
            monitor._check_exit_management()
        finally:
            pm._market_is_open_now = original
        result = json.loads((tmp / "auto_trades.json").read_text())
        assert result["trades"][0]["stop_price"] == 100.0


def test_check_exit_management_does_not_write_file_when_unchanged():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        monitor = make_monitor(tmp)
        write_auto_trades(tmp, [{"symbol": "AAPL", "entry_price": 100.0, "stop_price": 97.0, "qty": 10, "outcome": None, "stop_order_id": "ord1", "entry_time": "2026-03-20T14:00:00+00:00"}])
        mtime_before = os.path.getmtime(str(tmp / "auto_trades.json"))
        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        monitor._apply_trailing_stop = lambda t, s: False
        monitor._apply_partial_exit = lambda t, s: False
        monitor._apply_time_stop = lambda t, s: False
        try:
            monitor._check_exit_management()
        finally:
            pm._market_is_open_now = original
        mtime_after = os.path.getmtime(str(tmp / "auto_trades.json"))
        assert mtime_before == mtime_after


# ── Task 3: Trailing stop tests ───────────────────────────────────────────────

def make_trailing_trade(entry=100.0, stop=97.0, stop_order_id="stop-ord-1"):
    return {"symbol": "AAPL", "entry_price": entry, "stop_price": stop, "stop_order_id": stop_order_id, "qty": 10, "outcome": None, "entry_time": "2026-03-20T14:00:00+00:00"}


def test_trailing_stop_moves_to_breakeven_at_1r():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 103.0
        monitor._alpaca.replace_order_stop.return_value = {"id": "stop-ord-1", "status": "accepted"}
        trade = make_trailing_trade()
        result = monitor._apply_trailing_stop(trade, {"trailing_stop_enabled": True})
        assert result is True
        assert trade["stop_price"] == 100.0
        monitor._alpaca.replace_order_stop.assert_called_once_with("stop-ord-1", 100.0)


def test_trailing_stop_moves_to_1r_profit_at_2r():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 106.0
        monitor._alpaca.replace_order_stop.return_value = {"id": "stop-ord-1", "status": "accepted"}
        trade = make_trailing_trade()
        result = monitor._apply_trailing_stop(trade, {"trailing_stop_enabled": True})
        assert result is True
        assert trade["stop_price"] == 103.0
        monitor._alpaca.replace_order_stop.assert_called_once_with("stop-ord-1", 103.0)


def test_trailing_stop_no_change_below_1r():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 102.5
        trade = make_trailing_trade()
        result = monitor._apply_trailing_stop(trade, {"trailing_stop_enabled": True})
        assert result is False
        assert trade["stop_price"] == 97.0
        monitor._alpaca.replace_order_stop.assert_not_called()


def test_trailing_stop_no_change_when_already_at_breakeven():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 103.0
        trade = make_trailing_trade(stop=100.0)
        result = monitor._apply_trailing_stop(trade, {"trailing_stop_enabled": True})
        assert result is False
        monitor._alpaca.replace_order_stop.assert_not_called()


def test_trailing_stop_disabled_by_setting():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 110.0
        trade = make_trailing_trade()
        result = monitor._apply_trailing_stop(trade, {"trailing_stop_enabled": False})
        assert result is False
        monitor._alpaca.replace_order_stop.assert_not_called()


# ── Task 4: Partial exit tests ────────────────────────────────────────────────

def make_partial_trade(entry=100.0, stop=97.0, qty=20):
    return {"symbol": "AAPL", "entry_price": entry, "stop_price": stop, "qty": qty, "stop_order_id": "stop-ord-1", "outcome": None, "partial_exit_done": False, "entry_time": "2026-03-20T14:00:00+00:00"}


def test_partial_exit_fires_at_target_r():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 103.0
        monitor._alpaca.place_market_sell.return_value = {"id": "sell-1", "status": "new"}
        trade = make_partial_trade()
        result = monitor._apply_partial_exit(trade, {"partial_exit_enabled": True, "partial_exit_at_r": 1.0, "partial_exit_pct": 50})
        assert result is True
        assert trade["partial_exit_done"] is True
        assert trade["partial_exit_qty"] == 10
        monitor._alpaca.place_market_sell.assert_called_once_with("AAPL", 10)


def test_partial_exit_does_not_fire_below_target_r():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 102.5
        trade = make_partial_trade()
        result = monitor._apply_partial_exit(trade, {"partial_exit_enabled": True, "partial_exit_at_r": 1.0, "partial_exit_pct": 50})
        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_partial_exit_skipped_when_flag_already_set():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 106.0
        trade = make_partial_trade()
        trade["partial_exit_done"] = True
        result = monitor._apply_partial_exit(trade, {"partial_exit_enabled": True, "partial_exit_at_r": 1.0, "partial_exit_pct": 50})
        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_partial_exit_disabled_by_setting():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 110.0
        trade = make_partial_trade()
        result = monitor._apply_partial_exit(trade, {"partial_exit_enabled": False})
        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_partial_exit_sets_flag_on_sell_failure():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 103.0
        monitor._alpaca.place_market_sell.side_effect = RuntimeError("order rejected")
        trade = make_partial_trade()
        monitor._apply_partial_exit(trade, {"partial_exit_enabled": True, "partial_exit_at_r": 1.0, "partial_exit_pct": 50})
        assert trade["partial_exit_done"] is True


# ── Task 5: Time stop tests ───────────────────────────────────────────────────

def make_time_stop_trade(days_ago, entry=100.0, stop=97.0, qty=10):
    from datetime import datetime, timezone, timedelta
    entry_time = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return {"symbol": "AAPL", "entry_price": entry, "stop_price": stop, "qty": qty, "stop_order_id": "stop-ord-1", "outcome": None, "entry_time": entry_time}


def test_time_stop_exits_flat_position_after_time_limit():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 100.5
        monitor._alpaca.place_market_sell.return_value = {"id": "sell-ts", "status": "new"}
        trade = make_time_stop_trade(days_ago=6)
        result = monitor._apply_time_stop(trade, {"time_stop_days": 5})
        assert result is True
        assert trade["outcome"] == "time_stop"
        monitor._alpaca.place_market_sell.assert_called_once_with("AAPL", 10)


def test_time_stop_no_exit_within_time_limit():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 100.2
        trade = make_time_stop_trade(days_ago=3)
        result = monitor._apply_time_stop(trade, {"time_stop_days": 5})
        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_time_stop_no_exit_when_position_above_half_r():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 102.0
        trade = make_time_stop_trade(days_ago=7)
        result = monitor._apply_time_stop(trade, {"time_stop_days": 5})
        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_time_stop_disabled_when_days_zero():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._alpaca.get_last_price.return_value = 100.1
        trade = make_time_stop_trade(days_ago=30)
        result = monitor._apply_time_stop(trade, {"time_stop_days": 0})
        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()


def test_time_stop_skips_when_entry_time_missing():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        trade = {"symbol": "AAPL", "entry_price": 100.0, "stop_price": 97.0, "qty": 10, "outcome": None}
        result = monitor._apply_time_stop(trade, {"time_stop_days": 5})
        assert result is False
        monitor._alpaca.place_market_sell.assert_not_called()
