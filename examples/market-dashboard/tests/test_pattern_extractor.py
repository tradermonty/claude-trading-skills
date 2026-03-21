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
        for r in store.load()["rules"]:
            assert r.get("active") is False or r.get("sample_count", 0) < MIN_SAMPLE_COUNT


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
