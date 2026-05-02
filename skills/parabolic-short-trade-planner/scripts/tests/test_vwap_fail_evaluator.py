"""Tests for the VWAP fail evaluator (6-state FSM)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[1] / "intraday_evaluators"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import vwap_fail_evaluator as vf

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "intraday_bars"


def _load_bars(fixture_name: str, ticker: str) -> list[dict]:
    payload = json.loads((FIXTURES / fixture_name).read_text())
    return payload[ticker]


def _vf_plan() -> dict:
    return {
        "plan_id": "MSFT-20260505-VWF",
        "ticker": "MSFT",
        "trigger_type": "vwap_fail",
    }


class TestFsmTransitions:
    def test_armed_then_first_crack(self):
        # First two bars: armed, then close below VWAP from HOD.
        bars = _load_bars("vwap_full_fsm.json", "MSFT")[:2]
        out = vf.evaluate(_vf_plan(), bars)
        assert out["state"] == "first_crack_seen"
        assert out["first_crack_at"] == "2026-05-05T09:35:00-04:00"

    def test_first_crack_then_retest(self):
        bars = _load_bars("vwap_full_fsm.json", "MSFT")[:3]
        out = vf.evaluate(_vf_plan(), bars)
        assert out["state"] == "vwap_retest_seen"
        assert out["vwap_retest_at"] == "2026-05-05T09:40:00-04:00"
        assert out["retest_bar_high"] == 401.20

    def test_retest_then_rejection(self):
        bars = _load_bars("vwap_full_fsm.json", "MSFT")[:4]
        out = vf.evaluate(_vf_plan(), bars)
        assert out["state"] == "rejection_confirmed"
        assert out["rejection_confirmed_at"] == "2026-05-05T09:45:00-04:00"
        assert out["rejection_bar_low"] == 400.20

    def test_full_walk_to_triggered(self):
        bars = _load_bars("vwap_full_fsm.json", "MSFT")
        out = vf.evaluate(_vf_plan(), bars)
        assert out["state"] == "triggered"
        assert out["triggered_at"] == "2026-05-05T09:50:00-04:00"
        # entry = rejection_bar_low - 0.05 = 400.20 - 0.05 = 400.15
        assert out["entry_actual"] == 400.15
        # stop = retest_bar_high = 401.20
        assert out["stop_actual"] == 401.20


class TestPostTriggerInvalidation:
    def test_triggered_then_invalidated_post_reclaim(self):
        bars = _load_bars("vwap_invalidated_after_trigger.json", "MSFT")
        out = vf.evaluate(_vf_plan(), bars)
        assert out["state"] == "invalidated"
        # Both timestamps populated — triggered first, then invalidated.
        assert out["triggered_at"] == "2026-05-05T09:50:00-04:00"
        assert out["invalidated_at"] == "2026-05-05T09:55:00-04:00"
        assert out["invalidation_reason"] == "post_trigger_close_above_vwap"


class TestIdempotency:
    def test_same_input_produces_same_output(self):
        bars = _load_bars("vwap_full_fsm.json", "MSFT")
        out1 = vf.evaluate(_vf_plan(), bars)
        out2 = vf.evaluate(_vf_plan(), bars)
        assert out1 == out2
