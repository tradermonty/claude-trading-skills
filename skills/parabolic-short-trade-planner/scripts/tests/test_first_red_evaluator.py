"""Tests for the First Red 5-min evaluator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[1] / "intraday_evaluators"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import first_red_evaluator as fr

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "intraday_bars"


def _load_bars(fixture_name: str, ticker: str) -> list[dict]:
    payload = json.loads((FIXTURES / fixture_name).read_text())
    return payload[ticker]


def _fr_plan() -> dict:
    return {
        "plan_id": "NVDA-20260505-FR5",
        "ticker": "NVDA",
        "trigger_type": "first_red_5min",
    }


class TestRedMarking:
    def test_no_bars_stays_armed(self):
        out = fr.evaluate(_fr_plan(), [])
        assert out["state"] == "armed"
        assert out["red_marked_at"] is None

    def test_first_red_bar_marks(self):
        bars = _load_bars("first_red_clean.json", "NVDA")[:2]  # green + red
        out = fr.evaluate(_fr_plan(), bars)
        assert out["state"] == "red_marked"
        assert out["red_marked_at"] == "2026-05-05T09:35:00-04:00"
        assert out["red_low"] == 149.30
        assert out["red_high"] == 150.10


class TestTriggered:
    def test_first_red_clean_trigger(self):
        bars = _load_bars("first_red_clean.json", "NVDA")
        out = fr.evaluate(_fr_plan(), bars)
        assert out["state"] == "triggered"
        assert out["triggered_at"] == "2026-05-05T09:40:00-04:00"
        # entry = red_low - 0.05 = 149.30 - 0.05 = 149.25
        assert out["entry_actual"] == 149.25
        # stop = red_high = 150.10
        assert out["stop_actual"] == 150.10


class TestInvalidated:
    def test_red_high_taken_out_invalidates_pre_trigger(self):
        bars = _load_bars("first_red_invalidated.json", "NVDA")
        out = fr.evaluate(_fr_plan(), bars)
        assert out["state"] == "invalidated"
        assert out["invalidated_at"] == "2026-05-05T09:40:00-04:00"
        assert out["invalidation_reason"] == "red_high_taken_out"
        # Trigger never fired
        assert out["triggered_at"] is None

    def test_first_red_same_bar_invalidation_wins_over_trigger(self):
        # The same bar prints both high > red_high (would invalidate)
        # AND low < red_low (would trigger). v0.5b contract: invalidation wins.
        bars = _load_bars("first_red_same_bar_invalidation_wins.json", "NVDA")
        out = fr.evaluate(_fr_plan(), bars)
        assert out["state"] == "invalidated"
        assert out["invalidation_reason"] == "red_high_taken_out"
        assert out["triggered_at"] is None


class TestIdempotency:
    def test_same_input_produces_same_output(self):
        bars = _load_bars("first_red_clean.json", "NVDA")
        out1 = fr.evaluate(_fr_plan(), bars)
        out2 = fr.evaluate(_fr_plan(), bars)
        assert out1 == out2
