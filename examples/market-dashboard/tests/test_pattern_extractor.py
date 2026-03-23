# tests/test_pattern_extractor.py
import sys, json, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from unittest.mock import MagicMock, patch
from learning.pattern_extractor import PatternExtractor
from learning.rule_store import RuleStore, MIN_SAMPLE_COUNT


def make_extractor(tmp_path: Path, alpaca=None):
    if alpaca is None:
        alpaca = MagicMock()
        alpaca.is_configured = False
    store = RuleStore(tmp_path / "learned_rules.json")
    return PatternExtractor(alpaca_client=alpaca, rule_store=store, cache_dir=tmp_path), store


def write_trades(tmp_path: Path, trades: list):
    (tmp_path / "auto_trades.json").write_text(json.dumps({"trades": trades}))


def test_extract_with_no_trades_file_returns_zero():
    with tempfile.TemporaryDirectory() as d:
        extractor, _ = make_extractor(Path(d))
        result = extractor.extract()
        assert result["trades_analyzed"] == 0
        assert result["rules_updated"] == 0


def test_extract_with_zero_outcome_trades_when_alpaca_not_configured():
    """When Alpaca not configured, outcome=None trades cannot be refreshed."""
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [
            {"symbol": "AAPL", "confidence_tag": "UNCERTAIN", "outcome": None, "order_id": "abc"},
        ])
        extractor, _ = make_extractor(Path(d))
        result = extractor.extract()
        assert result["trades_analyzed"] == 0


def test_refresh_trade_outcomes_updates_loss_when_stop_fills():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "UNCERTAIN", "outcome": None,
            "order_id": "ord1", "entry_price": 155.0,
        }])
        alpaca = MagicMock()
        alpaca.is_configured = True
        # Mock: stop-loss leg filled at 150 (below entry → loss)
        stop_leg = MagicMock()
        stop_leg.side = "sell"
        stop_leg.status = "filled"
        stop_leg.filled_avg_price = 150.0
        parent_order = MagicMock()
        parent_order.legs = [stop_leg]
        alpaca.trading_client.get_order_by_id.return_value = parent_order

        extractor, _ = make_extractor(Path(d), alpaca=alpaca)
        updated = extractor.refresh_trade_outcomes()
        assert updated == 1
        trades = json.loads((Path(d) / "auto_trades.json").read_text())["trades"]
        assert trades[0]["outcome"] == "loss"


def test_refresh_trade_outcomes_updates_win_when_takeprofit_fills():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "outcome": None,
            "order_id": "ord2", "entry_price": 155.0,
        }])
        alpaca = MagicMock()
        alpaca.is_configured = True
        tp_leg = MagicMock()
        tp_leg.side = "sell"
        tp_leg.status = "filled"
        tp_leg.filled_avg_price = 163.0  # above entry → win
        parent_order = MagicMock()
        parent_order.legs = [tp_leg]
        alpaca.trading_client.get_order_by_id.return_value = parent_order

        extractor, _ = make_extractor(Path(d), alpaca=alpaca)
        updated = extractor.refresh_trade_outcomes()
        assert updated == 1
        trades = json.loads((Path(d) / "auto_trades.json").read_text())["trades"]
        assert trades[0]["outcome"] == "win"


def test_refresh_returns_zero_when_order_still_open():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "outcome": None,
            "order_id": "ord3", "entry_price": 155.0,
        }])
        alpaca = MagicMock()
        alpaca.is_configured = True
        parent_order = MagicMock()
        parent_order.legs = []  # no filled sell legs
        alpaca.trading_client.get_order_by_id.return_value = parent_order

        extractor, _ = make_extractor(Path(d), alpaca=alpaca)
        updated = extractor.refresh_trade_outcomes()
        assert updated == 0


def test_extract_generates_uncertain_blocked_rule_when_high_loss_rate():
    with tempfile.TemporaryDirectory() as d:
        # 6 UNCERTAIN trades with outcomes already set (skip refresh)
        trades = [
            {"symbol": f"T{i}", "confidence_tag": "UNCERTAIN", "outcome": "loss"}
            for i in range(5)
        ] + [{"symbol": "T5", "confidence_tag": "UNCERTAIN", "outcome": "win"}]
        write_trades(Path(d), trades)
        extractor, store = make_extractor(Path(d))
        result = extractor.extract()
        rules = store.load()["rules"]
        assert any(r["id"] == "auto_uncertain_to_blocked" for r in rules)
        rule = next(r for r in rules if r["id"] == "auto_uncertain_to_blocked")
        assert rule["active"] is True
        assert rule["sample_count"] == 6


def test_extract_does_not_activate_rule_below_min_sample_count():
    with tempfile.TemporaryDirectory() as d:
        trades = [
            {"symbol": f"T{i}", "confidence_tag": "UNCERTAIN", "outcome": "loss"}
            for i in range(MIN_SAMPLE_COUNT - 1)
        ]
        write_trades(Path(d), trades)
        extractor, store = make_extractor(Path(d))
        extractor.extract()
        assert store.load()["rules"] == []


def test_extract_does_not_create_rule_when_loss_rate_below_threshold():
    with tempfile.TemporaryDirectory() as d:
        trades = (
            [{"symbol": f"W{i}", "confidence_tag": "UNCERTAIN", "outcome": "win"} for i in range(3)] +
            [{"symbol": f"L{i}", "confidence_tag": "UNCERTAIN", "outcome": "loss"} for i in range(2)]
        )
        write_trades(Path(d), trades)
        extractor, store = make_extractor(Path(d))
        extractor.extract()
        assert not any(r["id"] == "auto_uncertain_to_blocked" for r in store.load()["rules"])


def test_extract_updates_existing_rule_confidence():
    with tempfile.TemporaryDirectory() as d:
        store = RuleStore(Path(d) / "learned_rules.json")
        store.save({"rules": [{
            "id": "auto_uncertain_to_blocked",
            "condition": {"confidence_tag": "UNCERTAIN"},
            "action": {"set_confidence_tag": "BLOCKED"},
            "confidence": 0.70, "sample_count": 7, "active": True,
        }]})
        trades = (
            [{"symbol": f"T{i}", "confidence_tag": "UNCERTAIN", "outcome": "loss"} for i in range(8)] +
            [{"symbol": "T8", "confidence_tag": "UNCERTAIN", "outcome": "win"}]
        )
        write_trades(Path(d), trades)
        alpaca = MagicMock(); alpaca.is_configured = False
        extractor = PatternExtractor(alpaca_client=alpaca, rule_store=store, cache_dir=Path(d))
        extractor.extract()
        rule = next(r for r in store.load()["rules"] if r["id"] == "auto_uncertain_to_blocked")
        assert rule["sample_count"] == 9


# ── New helpers and tests ──

def make_extractor_with_mstore(tmp_path: Path, alpaca=None):
    if alpaca is None:
        alpaca = MagicMock()
        alpaca.is_configured = False
    from learning.multiplier_store import MultiplierStore
    rule_store = RuleStore(tmp_path / "learned_rules.json")
    mstore = MultiplierStore(
        learned_file=tmp_path / "learned_multipliers.json",
        seed_file=tmp_path / "seed_multipliers.json",
    )
    extractor = PatternExtractor(
        alpaca_client=alpaca,
        rule_store=rule_store,
        cache_dir=tmp_path,
        multiplier_store=mstore,
    )
    return extractor, mstore


def test_refresh_saves_exit_price_to_trade_entry():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "outcome": None,
            "order_id": "ord1", "entry_price": 155.0,
        }])
        alpaca = MagicMock()
        alpaca.is_configured = True
        tp_leg = MagicMock()
        tp_leg.side = "sell"; tp_leg.status = "filled"; tp_leg.filled_avg_price = 163.0
        order = MagicMock(); order.legs = [tp_leg]
        alpaca.trading_client.get_order_by_id.return_value = order

        extractor, _ = make_extractor(Path(d), alpaca=alpaca)
        extractor.refresh_trade_outcomes()
        trades = json.loads((Path(d) / "auto_trades.json").read_text())["trades"]
        assert trades[0]["exit_price"] == 163.0


def test_extract_updates_multiplier_store_for_winning_trade():
    with tempfile.TemporaryDirectory() as d:
        # entry=100, stop=97, exit=109 → risk=3, achieved_rr = (109-100)/3 = 3.0
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "screener": "vcp",
            "regime": "bull", "outcome": "win",
            "entry_price": 100.0, "stop_price": 97.0, "exit_price": 109.0,
        }])
        extractor, mstore = make_extractor_with_mstore(Path(d))
        extractor.extract()
        data = json.loads((Path(d) / "learned_multipliers.json").read_text())
        assert "vcp+CLEAR+bull" in data
        assert data["vcp+CLEAR+bull"]["observed_rr"] == [3.0]


def test_extract_tracks_loss_count_but_not_rr_for_losing_trade():
    """Losing trades update win/loss counts but do not append to observed_rr."""
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "screener": "vcp",
            "regime": "bull", "outcome": "loss",
            "entry_price": 100.0, "stop_price": 97.0, "exit_price": 96.0,
        }])
        extractor, mstore = make_extractor_with_mstore(Path(d))
        extractor.extract()
        import json as _json
        learned_file = Path(d) / "learned_multipliers.json"
        assert learned_file.exists()
        data = _json.loads(learned_file.read_text())
        bucket = data.get("vcp+CLEAR+bull", {})
        assert bucket.get("losses", 0) == 1
        assert bucket.get("wins", 0) == 0
        assert bucket.get("observed_rr", []) == []


def test_extract_skips_trade_missing_stop_price():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "screener": "vcp",
            "regime": "bull", "outcome": "win",
            "entry_price": 100.0, "exit_price": 109.0,
            # stop_price missing — must skip without error
        }])
        extractor, mstore = make_extractor_with_mstore(Path(d))
        extractor.extract()  # must not raise
        assert not (Path(d) / "learned_multipliers.json").exists()


def test_extract_skips_trade_missing_regime():
    with tempfile.TemporaryDirectory() as d:
        write_trades(Path(d), [{
            "symbol": "AAPL", "confidence_tag": "CLEAR", "screener": "vcp",
            "outcome": "win",
            "entry_price": 100.0, "stop_price": 97.0, "exit_price": 109.0,
            # regime missing — must skip without error
        }])
        extractor, mstore = make_extractor_with_mstore(Path(d))
        extractor.extract()  # must not raise
        assert not (Path(d) / "learned_multipliers.json").exists()


# ── Tier 5 wiring tests ───────────────────────────────────────────────────────

def _make_closed_trade(outcome: str = "win") -> dict:
    return {
        "symbol": "AAPL",
        "order_id": "abc123",
        "entry_time": "2026-03-22T14:30:00+00:00",
        "entry_price": 100.0,
        "stop_price": 97.0,
        "exit_price": 106.0,
        "confidence_tag": "CLEAR",
        "screener": "vcp",
        "regime": "bull",
        "outcome": outcome,
    }

def _make_extractor_t5(tmp_path, time_of_day_tracker=None, stop_distance_store=None):
    from learning.pattern_extractor import PatternExtractor
    from learning.rule_store import RuleStore
    from unittest.mock import MagicMock
    alpaca = MagicMock()
    alpaca.is_configured = False
    rule_store = RuleStore(rules_file=tmp_path / "rules.json")
    return PatternExtractor(
        alpaca_client=alpaca,
        rule_store=rule_store,
        cache_dir=tmp_path,
        time_of_day_tracker=time_of_day_tracker,
        stop_distance_store=stop_distance_store,
    )

def test_time_of_day_tracker_called_for_closed_trade(tmp_path):
    from unittest.mock import MagicMock
    tracker = MagicMock()
    extractor = _make_extractor_t5(tmp_path, time_of_day_tracker=tracker)
    trade = _make_closed_trade("win")
    extractor._update_multipliers([trade])
    tracker.record.assert_called_once()
    call_args = tracker.record.call_args[0]
    # First arg is hour (ET), second is outcome
    assert call_args[1] == "win"

def test_stop_distance_store_called_for_all_closed_trades(tmp_path):
    from unittest.mock import MagicMock
    store = MagicMock()
    extractor = _make_extractor_t5(tmp_path, stop_distance_store=store)
    trades = [_make_closed_trade("win"), _make_closed_trade("loss")]
    extractor._update_multipliers(trades)
    assert store.record.call_count == 2

def test_neither_store_called_when_stores_are_none(tmp_path):
    # No stores injected — should not raise
    extractor = _make_extractor_t5(tmp_path)
    trade = _make_closed_trade("win")
    # Should complete without error
    extractor._update_multipliers([trade])
