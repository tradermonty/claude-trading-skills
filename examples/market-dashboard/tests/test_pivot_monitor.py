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
