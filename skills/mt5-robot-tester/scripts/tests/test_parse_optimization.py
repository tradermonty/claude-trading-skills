"""Tests for parse_mt5_optimization: parsing, Round-1 gate, best-param."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parse_mt5_optimization import (  # noqa: E402
    best_param_value,
    best_pass,
    count_positive_profit,
    gate_round1,
    parse_passes,
)

FIX = Path(__file__).resolve().parent / "fixtures" / "sample_opt.xml"


def test_parses_all_passes():
    passes = parse_passes(FIX)
    assert len(passes) == 13
    top = best_pass(passes, by="profit")
    assert top["symbol"] == "US100.cash"
    assert top["profit"] == 45231.12
    assert top["inputs"]["GannHiLoPeriod1"] == 86.0


def test_counts_positive_profit():
    passes = parse_passes(FIX)
    assert count_positive_profit(passes) == 7


def test_gate_passes_with_five_positive_and_3x():
    passes = parse_passes(FIX)
    gate = gate_round1(passes, deposit=10000)
    assert gate["passed"] is True
    assert gate["positive_symbols"] == 7
    assert gate["best_symbol"] == "US100.cash"


def test_gate_fails_when_best_below_3x():
    # Same passes but a deposit whose 3x exceeds the best profit.
    passes = parse_passes(FIX)
    gate = gate_round1(passes, deposit=20000)  # 3x = 60000 > 45231
    assert gate["passed"] is False
    assert "threshold" in gate["reason"]


def test_gate_fails_with_fewer_than_five_positive():
    passes = [
        {"symbol": "A", "profit": 40000, "inputs": {}},
        {"symbol": "B", "profit": 10, "inputs": {}},
        {"symbol": "C", "profit": -5, "inputs": {}},
    ]
    gate = gate_round1(passes, deposit=10000)
    assert gate["passed"] is False
    assert "profitable" in gate["reason"]


def test_best_param_value_picks_from_top_profit():
    passes = [
        {"profit": 100, "inputs": {"P": 5}},
        {"profit": 300, "inputs": {"P": 9}},
        {"profit": 250, "inputs": {"P": 7}},
    ]
    assert best_param_value(passes, "P", by="profit") == 9
