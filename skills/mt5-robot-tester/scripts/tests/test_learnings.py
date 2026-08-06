"""Tests for the cross-run learning store (ordering + persistence)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mt5_learnings import Learnings  # noqa: E402


def test_param_priority_orders_by_historical_impact(tmp_path):
    learn = Learnings(tmp_path / "learnings.json")
    learn.record_param_optimization("A", 100)
    learn.record_param_optimization("B", 5000)
    learn.record_param_optimization("C", 0)
    ordered = learn.param_priority_order(["A", "B", "C"])
    assert ordered == ["B", "A", "C"]


def test_unknown_params_keep_original_order(tmp_path):
    learn = Learnings(tmp_path / "learnings.json")
    # No history at all -> stable original order.
    assert learn.param_priority_order(["X", "Y", "Z"]) == ["X", "Y", "Z"]


def test_persistence_round_trip_accumulates(tmp_path):
    path = tmp_path / "learnings.json"
    learn = Learnings(path)
    learn.bump_run()
    learn.record_best_pair("US100.cash", 45000)
    learn.record_param_optimization("GannHiLoPeriod1", 1200)
    learn.record_bot("Bot1", "finalist", "ok")
    learn.save()

    reloaded = Learnings(path)
    assert reloaded.data["runs"] == 1
    assert reloaded.symbol_prior("US100.cash")["best_pair_count"] == 1
    assert reloaded.param_avg_improvement("GannHiLoPeriod1") == 1200

    # Second loop accumulates rather than overwriting.
    reloaded.bump_run()
    reloaded.record_best_pair("US100.cash", 55000)
    reloaded.save()
    again = Learnings(path)
    assert again.data["runs"] == 2
    assert again.symbol_prior("US100.cash")["best_pair_count"] == 2
    assert again.symbol_prior("US100.cash")["avg_profit"] == 50000


def test_markdown_renders(tmp_path):
    learn = Learnings(tmp_path / "learnings.json")
    learn.record_param_optimization("A", 100)
    md = learn.render_markdown()
    assert "Learnings" in md
    assert "| A |" in md
