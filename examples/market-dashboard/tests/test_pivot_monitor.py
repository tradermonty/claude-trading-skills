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
        broker_client=alpaca,
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
            broker_client=alpaca, settings_manager=settings,
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
        monitor._broker.is_configured = True
        monitor._broker.get_positions.return_value = []
        monitor._broker.get_account.return_value = {"portfolio_value": 100_000.0}
        monitor._broker.get_last_price.return_value = 156.0
        monitor._broker.place_bracket_order.return_value = {
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
        monitor._is_market_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._broker.place_bracket_order.assert_called_once()
        assert "AAPL" in monitor._triggered


def test_check_breakout_skips_blocked_candidate():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.is_configured = True
        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "BLOCKED"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        monitor._is_market_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._broker.place_bracket_order.assert_not_called()


def test_check_breakout_skips_when_price_below_buffer():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.is_configured = True
        bar = MagicMock(); bar.symbol = "AAPL"
        bar.close = 155.0  # exactly at pivot, not above buffer (needs > 155.155)
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "CLEAR"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        monitor._is_market_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._broker.place_bracket_order.assert_not_called()


def test_guard_rail_max_positions_blocks_order():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.is_configured = True
        # 5 positions = max_positions → blocked
        monitor._broker.get_positions.return_value = [{}] * 5

        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "CLEAR"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        monitor._is_market_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._broker.place_bracket_order.assert_not_called()


def test_guard_rail_outside_market_hours_blocks_order():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.is_configured = True
        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "CLEAR"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: False
        monitor._is_market_open_now = lambda: False
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._broker.place_bracket_order.assert_not_called()


def test_uncertain_with_negative_stage2_blocks_order():
    def negative_search(sym):
        return ["AAPL: SEC investigation launched"]
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d), search_fn=negative_search)
        monitor._broker.is_configured = True
        monitor._broker.get_positions.return_value = []
        bar = MagicMock(); bar.symbol = "AAPL"; bar.close = 200.0
        candidates = [{"symbol": "AAPL", "pivot_price": 155.0, "confidence_tag": "UNCERTAIN"}]

        import pivot_monitor as pm
        original = pm._market_is_open_now
        pm._market_is_open_now = lambda: True
        monitor._is_market_open_now = lambda: True
        try:
            monitor._check_breakout(bar, candidates)
        finally:
            pm._market_is_open_now = original

        monitor._broker.place_bracket_order.assert_not_called()


def test_high_conviction_uses_1_5x_risk():
    """HIGH_CONVICTION sizing passes risk_pct × 1.5 to qty calculation."""
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.is_configured = True
        monitor._broker.get_account.return_value = {"portfolio_value": 100_000.0}
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
        broker_client=alpaca,
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
        market_id = monitor._market_config.get("id", "us")
        trades_file = tmp / f"{market_id}-auto_trades.json"
        trades = json.loads(trades_file.read_text())["trades"]
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
        market_id = monitor._market_config.get("id", "us")
        trades_file = tmp / f"{market_id}-auto_trades.json"
        trades = json.loads(trades_file.read_text())["trades"]
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
        broker_client=alpaca,
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
        monitor._is_market_open_now = lambda: True
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
        monitor._is_market_open_now = lambda: True
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
        monitor._is_market_open_now = lambda: True
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
            broker_client=alpaca,
            settings_manager=settings,
            cache_dir=Path(d),
            drawdown_tracker=tracker,
        )
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: True
        monitor._is_market_open_now = lambda: True
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
            broker_client=alpaca,
            settings_manager=settings,
            cache_dir=Path(d),
            drawdown_tracker=tracker,
        )
        import pivot_monitor as pm
        pm._market_is_open_now = lambda: True
        monitor._is_market_open_now = lambda: True
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
        monitor._is_market_open_now = lambda: True
        allowed, reason = monitor._guard_rails_allow({"symbol": "AAPL"}, tag="CLEAR")
        assert allowed is False
        assert "earnings" in reason.lower()


# ── Task 1: Volume confirmation tests ────────────────────────────────────────

def test_volume_above_threshold_allowed(tmp_path):
    monitor = make_monitor(tmp_path)
    monitor._broker.get_current_volume = lambda sym: 200_000
    candidate = {"symbol": "AAPL", "pivot_price": 100.0, "confidence_tag": "CLEAR", "avg_volume_20d": 100_000}
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    monitor._is_market_open_now = lambda: True
    monitor._broker.get_positions.return_value = []
    allowed, reason = monitor._guard_rails_allow(candidate, tag="CLEAR")
    assert allowed is True

def test_volume_below_threshold_blocked(tmp_path):
    monitor = make_monitor(tmp_path)
    monitor._broker.get_current_volume = lambda sym: 100_000
    candidate = {"symbol": "AAPL", "pivot_price": 100.0, "confidence_tag": "CLEAR", "avg_volume_20d": 200_000}
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    monitor._is_market_open_now = lambda: True
    monitor._broker.get_positions.return_value = []
    allowed, reason = monitor._guard_rails_allow(candidate, tag="CLEAR")
    assert allowed is False
    assert "volume" in reason.lower()

def test_volume_data_missing_fails_open(tmp_path):
    monitor = make_monitor(tmp_path)
    monitor._broker.get_current_volume = lambda sym: (_ for _ in ()).throw(Exception("API error"))
    candidate = {"symbol": "AAPL", "pivot_price": 100.0, "confidence_tag": "CLEAR", "avg_volume_20d": 100_000}
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    monitor._is_market_open_now = lambda: True
    monitor._broker.get_positions.return_value = []
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
    monitor = PivotWatchlistMonitor(broker_client=alpaca, settings_manager=settings, cache_dir=tmp_path)
    alpaca.get_current_volume = lambda sym: 1
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    monitor._is_market_open_now = lambda: True
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
    monitor = PivotWatchlistMonitor(broker_client=alpaca, settings_manager=settings, cache_dir=tmp_path)
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    monitor._is_market_open_now = lambda: True
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
    monitor = PivotWatchlistMonitor(broker_client=alpaca, settings_manager=settings, cache_dir=tmp_path)
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    monitor._is_market_open_now = lambda: True
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
    monitor = PivotWatchlistMonitor(broker_client=alpaca, settings_manager=settings, cache_dir=tmp_path)
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    monitor._is_market_open_now = lambda: True
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
    monitor = PivotWatchlistMonitor(broker_client=alpaca, settings_manager=settings, cache_dir=tmp_path)
    import pivot_monitor as pm
    pm._market_is_open_now = lambda: True
    monitor._is_market_open_now = lambda: True
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
        monitor._is_market_open_now = lambda: True
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
        monitor._is_market_open_now = lambda: False
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
        monitor._is_market_open_now = lambda: True
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
        monitor._is_market_open_now = lambda: True
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
        monitor._is_market_open_now = lambda: True
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
        monitor._broker.get_last_price.return_value = 103.0
        monitor._broker.replace_order_stop.return_value = {"id": "stop-ord-1", "status": "accepted"}
        trade = make_trailing_trade()
        result = monitor._apply_trailing_stop(trade, {"trailing_stop_enabled": True})
        assert result is True
        assert trade["stop_price"] == 100.0
        monitor._broker.replace_order_stop.assert_called_once_with("stop-ord-1", 100.0)


def test_trailing_stop_moves_to_1r_profit_at_2r():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 106.0
        monitor._broker.replace_order_stop.return_value = {"id": "stop-ord-1", "status": "accepted"}
        trade = make_trailing_trade()
        result = monitor._apply_trailing_stop(trade, {"trailing_stop_enabled": True})
        assert result is True
        assert trade["stop_price"] == 103.0
        monitor._broker.replace_order_stop.assert_called_once_with("stop-ord-1", 103.0)


def test_trailing_stop_no_change_below_1r():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 102.5
        trade = make_trailing_trade()
        result = monitor._apply_trailing_stop(trade, {"trailing_stop_enabled": True})
        assert result is False
        assert trade["stop_price"] == 97.0
        monitor._broker.replace_order_stop.assert_not_called()


def test_trailing_stop_no_change_when_already_at_breakeven():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 103.0
        trade = make_trailing_trade(stop=100.0)
        result = monitor._apply_trailing_stop(trade, {"trailing_stop_enabled": True})
        assert result is False
        monitor._broker.replace_order_stop.assert_not_called()


def test_trailing_stop_disabled_by_setting():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 110.0
        trade = make_trailing_trade()
        result = monitor._apply_trailing_stop(trade, {"trailing_stop_enabled": False})
        assert result is False
        monitor._broker.replace_order_stop.assert_not_called()


# ── Task 4: Partial exit tests ────────────────────────────────────────────────

def make_partial_trade(entry=100.0, stop=97.0, qty=20):
    return {"symbol": "AAPL", "entry_price": entry, "stop_price": stop, "qty": qty, "stop_order_id": "stop-ord-1", "outcome": None, "partial_exit_done": False, "entry_time": "2026-03-20T14:00:00+00:00"}


def test_partial_exit_fires_at_target_r():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 103.0
        monitor._broker.place_market_sell.return_value = {"id": "sell-1", "status": "new"}
        trade = make_partial_trade()
        result = monitor._apply_partial_exit(trade, {"partial_exit_enabled": True, "partial_exit_at_r": 1.0, "partial_exit_pct": 50})
        assert result is True
        assert trade["partial_exit_done"] is True
        assert trade["partial_exit_qty"] == 10
        monitor._broker.place_market_sell.assert_called_once_with("AAPL", 10)


def test_partial_exit_does_not_fire_below_target_r():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 102.5
        trade = make_partial_trade()
        result = monitor._apply_partial_exit(trade, {"partial_exit_enabled": True, "partial_exit_at_r": 1.0, "partial_exit_pct": 50})
        assert result is False
        monitor._broker.place_market_sell.assert_not_called()


def test_partial_exit_skipped_when_flag_already_set():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 106.0
        trade = make_partial_trade()
        trade["partial_exit_done"] = True
        result = monitor._apply_partial_exit(trade, {"partial_exit_enabled": True, "partial_exit_at_r": 1.0, "partial_exit_pct": 50})
        assert result is False
        monitor._broker.place_market_sell.assert_not_called()


def test_partial_exit_disabled_by_setting():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 110.0
        trade = make_partial_trade()
        result = monitor._apply_partial_exit(trade, {"partial_exit_enabled": False})
        assert result is False
        monitor._broker.place_market_sell.assert_not_called()


def test_partial_exit_sets_flag_on_sell_failure():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 103.0
        monitor._broker.place_market_sell.side_effect = RuntimeError("order rejected")
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
        monitor._broker.get_last_price.return_value = 100.5
        monitor._broker.place_market_sell.return_value = {"id": "sell-ts", "status": "new"}
        trade = make_time_stop_trade(days_ago=6)
        result = monitor._apply_time_stop(trade, {"time_stop_days": 5})
        assert result is True
        assert trade["outcome"] == "time_stop"
        monitor._broker.place_market_sell.assert_called_once_with("AAPL", 10)


def test_time_stop_no_exit_within_time_limit():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 100.2
        trade = make_time_stop_trade(days_ago=3)
        result = monitor._apply_time_stop(trade, {"time_stop_days": 5})
        assert result is False
        monitor._broker.place_market_sell.assert_not_called()


def test_time_stop_no_exit_when_position_above_half_r():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 102.0
        trade = make_time_stop_trade(days_ago=7)
        result = monitor._apply_time_stop(trade, {"time_stop_days": 5})
        assert result is False
        monitor._broker.place_market_sell.assert_not_called()


def test_time_stop_disabled_when_days_zero():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        monitor._broker.get_last_price.return_value = 100.1
        trade = make_time_stop_trade(days_ago=30)
        result = monitor._apply_time_stop(trade, {"time_stop_days": 0})
        assert result is False
        monitor._broker.place_market_sell.assert_not_called()


def test_time_stop_skips_when_entry_time_missing():
    with tempfile.TemporaryDirectory() as d:
        monitor = make_monitor(Path(d))
        trade = {"symbol": "AAPL", "entry_price": 100.0, "stop_price": 97.0, "qty": 10, "outcome": None}
        result = monitor._apply_time_stop(trade, {"time_stop_days": 5})
        assert result is False
        monitor._broker.place_market_sell.assert_not_called()


# ── VIX multiplier helpers ────────────────────────────────────────────────────

def write_bubble_cache(tmp_path, vix: float):
    data = {"vix": vix, "risk_score": 30}
    (tmp_path / "us-market-bubble-detector.json").write_text(json.dumps(data))


def make_vix_monitor(tmp_path, settings_overrides=None):
    """Build a PivotWatchlistMonitor with a fake cache dir for VIX tests."""
    from unittest.mock import MagicMock
    from pivot_monitor import PivotWatchlistMonitor
    from settings_manager import SettingsManager

    settings = MagicMock(spec=SettingsManager)
    base = {"vix_sizing_enabled": True, "kelly_sizing_enabled": False}
    if settings_overrides:
        base.update(settings_overrides)
    settings.load.return_value = base

    alpaca = MagicMock()
    monitor = PivotWatchlistMonitor(
        broker_client=alpaca,
        settings_manager=settings,
        cache_dir=tmp_path,
    )
    return monitor


def test_vix_below_20_returns_1_0(tmp_path):
    write_bubble_cache(tmp_path, vix=15.0)
    monitor = make_vix_monitor(tmp_path)
    assert monitor._get_vix_multiplier() == 1.0


def test_vix_between_20_and_25_returns_0_75(tmp_path):
    write_bubble_cache(tmp_path, vix=22.5)
    monitor = make_vix_monitor(tmp_path)
    assert monitor._get_vix_multiplier() == 0.75


def test_vix_between_25_and_30_returns_0_50(tmp_path):
    write_bubble_cache(tmp_path, vix=27.0)
    monitor = make_vix_monitor(tmp_path)
    assert monitor._get_vix_multiplier() == 0.50


def test_vix_above_30_returns_0_25(tmp_path):
    write_bubble_cache(tmp_path, vix=35.0)
    monitor = make_vix_monitor(tmp_path)
    assert monitor._get_vix_multiplier() == 0.25


def test_vix_cache_missing_fails_open(tmp_path):
    """No cache file → return 1.0, never block trading."""
    monitor = make_vix_monitor(tmp_path)
    assert monitor._get_vix_multiplier() == 1.0


def test_vix_disabled_returns_1_0(tmp_path):
    write_bubble_cache(tmp_path, vix=40.0)
    monitor = make_vix_monitor(tmp_path, settings_overrides={"vix_sizing_enabled": False})
    assert monitor._get_vix_multiplier() == 1.0


# ── _calc_qty sizing multiplier tests ─────────────────────────────────────────

def make_monitor_with_account(tmp_path, portfolio_value: float, settings_overrides=None):
    """Monitor with a mock Alpaca that returns a fixed portfolio value."""
    from unittest.mock import MagicMock
    from pivot_monitor import PivotWatchlistMonitor
    from settings_manager import SettingsManager

    alpaca = MagicMock()
    alpaca.get_account.return_value = {"portfolio_value": portfolio_value}
    alpaca.get_positions.return_value = []

    settings = MagicMock(spec=SettingsManager)
    base = {
        "default_risk_pct": 1.0,
        "max_position_size_pct": 50.0,  # large enough that size cap doesn't interfere with tests
        "kelly_sizing_enabled": False,
        "kelly_max_multiplier": 2.0,
        "vix_sizing_enabled": False,  # disable VIX by default so tests are isolated
    }
    if settings_overrides:
        base.update(settings_overrides)
    settings.load.return_value = base

    monitor = PivotWatchlistMonitor(
        broker_client=alpaca,
        settings_manager=settings,
        cache_dir=tmp_path,
    )
    return monitor


def test_calc_qty_kelly_disabled_no_multiplier(tmp_path):
    """Kelly disabled → qty unchanged from base calculation."""
    monitor = make_monitor_with_account(tmp_path, portfolio_value=100_000)
    qty = monitor._calc_qty(
        entry_price=100.0, stop_price=97.0, high_conviction=False, bucket_key="vcp+CLEAR+bull"
    )
    # base: risk $1000 / $3 risk-per-share = 333 shares
    assert qty == 333


def test_calc_qty_kelly_enabled_high_win_rate_increases_qty(tmp_path):
    """Kelly enabled with a high-win-rate bucket → qty larger than base."""
    from unittest.mock import MagicMock, patch
    monitor = make_monitor_with_account(
        tmp_path, portfolio_value=100_000,
        settings_overrides={"kelly_sizing_enabled": True, "kelly_max_multiplier": 2.0},
    )
    # Inject a mock multiplier_store that returns kelly mult of 1.8
    mock_store = MagicMock()
    mock_store.get_kelly_multiplier.return_value = 1.8
    monitor._multiplier_store = mock_store

    base_qty = 333  # from 1% risk on $100k with $3 risk/share
    qty = monitor._calc_qty(
        entry_price=100.0, stop_price=97.0, high_conviction=False, bucket_key="vcp+CLEAR+bull"
    )
    assert qty > base_qty


def test_calc_qty_high_vix_reduces_qty(tmp_path):
    """VIX > 30 → qty reduced to 25% of base."""
    write_bubble_cache(tmp_path, vix=35.0)
    monitor = make_monitor_with_account(
        tmp_path, portfolio_value=100_000,
        settings_overrides={"vix_sizing_enabled": True},
    )
    qty = monitor._calc_qty(
        entry_price=100.0, stop_price=97.0, high_conviction=False, bucket_key="vcp+CLEAR+bull"
    )
    # base 333 × 0.25 = 83 (int floor, min 1)
    assert qty == max(1, int(333 * 0.25))


def test_calc_qty_kelly_and_vix_stack(tmp_path):
    """Kelly mult 1.5 × VIX mult 0.5 = net 0.75 → qty reduced from base."""
    write_bubble_cache(tmp_path, vix=27.0)  # VIX 0.50
    monitor = make_monitor_with_account(
        tmp_path, portfolio_value=100_000,
        settings_overrides={"kelly_sizing_enabled": True, "vix_sizing_enabled": True},
    )
    mock_store = MagicMock()
    mock_store.get_kelly_multiplier.return_value = 1.5
    monitor._multiplier_store = mock_store

    qty = monitor._calc_qty(
        entry_price=100.0, stop_price=97.0, high_conviction=False, bucket_key="vcp+CLEAR+bull"
    )
    expected = max(1, int(333 * 1.5 * 0.50))
    assert qty == expected


# ── Regime confidence multiplier tests ───────────────────────────────────────

def _write_regime_cache(tmp_path, score: float):
    import json
    (tmp_path / "macro-regime-detector.json").write_text(json.dumps({
        "regime": {"current_regime": "bull", "score": score}
    }))


def test_regime_confidence_score_75_returns_1_0(tmp_path):
    _write_regime_cache(tmp_path, 80.0)
    monitor = make_vix_monitor(tmp_path)
    assert monitor._get_regime_confidence_multiplier() == 1.0


def test_regime_confidence_score_50_to_75_returns_0_75(tmp_path):
    _write_regime_cache(tmp_path, 60.0)
    monitor = make_vix_monitor(tmp_path)
    assert monitor._get_regime_confidence_multiplier() == 0.75


def test_regime_confidence_score_below_25_returns_0_25(tmp_path):
    _write_regime_cache(tmp_path, 10.0)
    monitor = make_vix_monitor(tmp_path)
    assert monitor._get_regime_confidence_multiplier() == 0.25


def test_regime_confidence_missing_cache_returns_1_0(tmp_path):
    monitor = make_vix_monitor(tmp_path)
    # No cache file written
    assert monitor._get_regime_confidence_multiplier() == 1.0


# ── Task 6: Scheduler smoke test ─────────────────────────────────────────────

def test_create_scheduler_registers_exit_management_job():
    with tempfile.TemporaryDirectory() as d:
        from scheduler import create_scheduler
        from unittest.mock import MagicMock
        runner = MagicMock()
        monitor = make_monitor(Path(d))
        sched = create_scheduler(runner=runner, cache_dir=Path(d), pivot_monitor=monitor)
        job_ids = {job.id for job in sched.get_jobs()}
        assert "exit_management" in job_ids


# ── Task 4 (broker abstraction): new tests ────────────────────────────────────

def _make_monitor_with_broker(broker, market_config=None, pdt_enabled=True, calendar_file=None):
    """Build a PivotWatchlistMonitor using the new broker abstraction interface."""
    from pivot_monitor import PivotWatchlistMonitor
    from settings_manager import SettingsManager
    from pathlib import Path
    import tempfile

    cache_dir = Path(tempfile.mkdtemp())
    sm = SettingsManager()
    if market_config is None:
        market_config = {
            "id": "us",
            "tz": "America/New_York",
            "open": "09:30",
            "close": "16:00",
        }
    return PivotWatchlistMonitor(
        broker_client=broker,
        settings_manager=sm,
        cache_dir=cache_dir,
        market_config=market_config,
        pdt_enabled=pdt_enabled,
        calendar_file=calendar_file,
    )


def test_monitor_accepts_broker_client_param():
    """PivotWatchlistMonitor accepts broker_client keyword and stores as self._broker."""
    from unittest.mock import MagicMock
    broker = MagicMock()
    broker.is_configured = True

    monitor = _make_monitor_with_broker(broker)
    assert monitor._broker is broker


def test_pdt_disabled_skips_pdt_guard():
    """When pdt_enabled=False, PDT tracker block is skipped even with 0 slots."""
    from unittest.mock import MagicMock
    from learning.pdt_tracker import PDTTracker
    import tempfile
    from pathlib import Path
    from settings_manager import SettingsManager

    broker = MagicMock()
    broker.is_configured = True
    broker.get_positions.return_value = []
    broker.get_account.return_value = {"portfolio_value": 10000.0}
    broker.get_current_volume.side_effect = Exception("no vol")

    pdt = MagicMock()
    pdt.get_allowed_tags.return_value = set()  # 0 slots — would block if PDT enabled

    from pivot_monitor import PivotWatchlistMonitor
    sm = SettingsManager()
    cache_dir = Path(tempfile.mkdtemp())
    market_config = {"id": "oslo", "tz": "Europe/Oslo", "open": "09:00", "close": "16:30"}

    monitor = PivotWatchlistMonitor(
        broker_client=broker,
        settings_manager=sm,
        cache_dir=cache_dir,
        market_config=market_config,
        pdt_enabled=False,  # PDT disabled for Oslo
        pdt_tracker=pdt,
    )

    # Patch _is_market_open_now to return True so we get past the hours check
    monitor._is_market_open_now = lambda: True

    allowed, reason = monitor._guard_rails_allow({"symbol": "EQNR"}, tag="CLEAR")
    # Should not be blocked by PDT since pdt_enabled=False
    assert "PDT" not in reason


def test_market_hours_from_config_oslo():
    """_is_market_open_now uses market_config tz/open/close, not hardcoded ET."""
    from unittest.mock import MagicMock, patch
    from datetime import datetime
    from zoneinfo import ZoneInfo

    broker = MagicMock()
    market_config = {
        "id": "oslo",
        "tz": "Europe/Oslo",
        "open": "09:00",
        "close": "16:30",
    }
    monitor = _make_monitor_with_broker(broker, market_config=market_config)

    # Simulate 10:00 Oslo time on a Tuesday -> should be open
    oslo_tz = ZoneInfo("Europe/Oslo")
    mock_now = datetime(2026, 3, 24, 10, 0, 0, tzinfo=oslo_tz)  # Tuesday 10:00 Oslo

    with patch("pivot_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        result = monitor._is_market_open_now()

    assert result is True


def test_market_hours_closed_outside_config():
    """_is_market_open_now returns False outside configured hours."""
    from unittest.mock import MagicMock, patch
    from datetime import datetime
    from zoneinfo import ZoneInfo

    broker = MagicMock()
    market_config = {
        "id": "oslo",
        "tz": "Europe/Oslo",
        "open": "09:00",
        "close": "16:30",
    }
    monitor = _make_monitor_with_broker(broker, market_config=market_config)

    oslo_tz = ZoneInfo("Europe/Oslo")
    mock_now = datetime(2026, 3, 24, 17, 0, 0, tzinfo=oslo_tz)  # 17:00 -> closed

    with patch("pivot_monitor.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        result = monitor._is_market_open_now()

    assert result is False


def test_per_market_trade_log_file():
    """_log_trade writes to cache/<market-id>-auto_trades.json."""
    from unittest.mock import MagicMock
    import tempfile
    from pathlib import Path

    broker = MagicMock()
    broker.get_account.return_value = {"portfolio_value": 10000.0}

    market_config = {"id": "oslo", "tz": "Europe/Oslo", "open": "09:00", "close": "16:30"}
    monitor = _make_monitor_with_broker(broker, market_config=market_config)

    candidate = {"symbol": "EQNR", "pivot_price": 300.0}
    monitor._log_trade(candidate, "order-123", 310.0, 300.0, 10, "CLEAR")

    trades_file = monitor._cache_dir / "oslo-auto_trades.json"
    assert trades_file.exists()
    import json
    data = json.loads(trades_file.read_text())
    assert len(data["trades"]) == 1
    assert data["trades"][0]["symbol"] == "EQNR"
    assert data["trades"][0]["market"] == "oslo"
