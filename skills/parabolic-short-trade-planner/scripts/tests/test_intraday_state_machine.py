"""Tests for the intraday FSM dispatcher + cross-evaluator contracts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1] / "intraday_evaluators"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import intraday_state_machine as ism

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "intraday_bars"


def _load_bars(fixture_name: str, ticker: str) -> list[dict]:
    payload = json.loads((FIXTURES / fixture_name).read_text())
    return payload[ticker]


class TestDispatch:
    def test_orl_dispatch(self):
        plan = {
            "plan_id": "AAPL-20260505-ORL5",
            "ticker": "AAPL",
            "trigger_type": "orl_5min_break",
        }
        bars = _load_bars("orl_clean_break.json", "AAPL")
        out = ism.step_one_plan(plan, bars, atr_14=2.0)
        assert out["state"] == "triggered"
        assert out["trigger_type"] == "orl_5min_break"

    def test_first_red_dispatch(self):
        plan = {
            "plan_id": "NVDA-20260505-FR5",
            "ticker": "NVDA",
            "trigger_type": "first_red_5min",
        }
        bars = _load_bars("first_red_clean.json", "NVDA")
        out = ism.step_one_plan(plan, bars, atr_14=2.0)
        assert out["state"] == "triggered"
        assert out["trigger_type"] == "first_red_5min"

    def test_vwap_fail_dispatch(self):
        plan = {
            "plan_id": "MSFT-20260505-VWF",
            "ticker": "MSFT",
            "trigger_type": "vwap_fail",
        }
        bars = _load_bars("vwap_full_fsm.json", "MSFT")
        out = ism.step_one_plan(plan, bars, atr_14=2.0)
        assert out["state"] == "triggered"
        assert out["trigger_type"] == "vwap_fail"

    def test_unknown_trigger_type_raises(self):
        plan = {"plan_id": "X", "ticker": "X", "trigger_type": "BOGUS"}
        with pytest.raises(ValueError):
            ism.step_one_plan(plan, [], atr_14=2.0)


class TestTerminalContract:
    """Cross-evaluator: invalidated absorbing, triggered does not retrigger
    but can still invalidate."""

    def test_invalidated_is_absorbing(self):
        # ORL invalidated fixture: trigger then post-trigger reclaim.
        plan = {
            "plan_id": "AAPL-20260505-ORL5",
            "ticker": "AAPL",
            "trigger_type": "orl_5min_break",
        }
        bars = _load_bars("orl_invalidated.json", "AAPL")
        # Synthesise a follow-up bar that *would* re-trigger the ORL
        # condition (close < orl_low, vol > 1.2× orl_vol). After
        # invalidation, the FSM must NOT pick it up.
        bars_extended = list(bars) + [
            {
                "ts_et": "2026-05-05T09:50:00-04:00",
                "o": 149.50,
                "h": 149.60,
                "l": 148.20,
                "c": 148.30,
                "v": 3_000_000,
            }
        ]
        out = ism.step_one_plan(plan, bars_extended, atr_14=2.0)
        assert out["state"] == "invalidated"
        # Invalidated_at stays at the ORIGINAL invalidation bar, not
        # reset by the new trigger-shape bar.
        assert out["invalidated_at"] == "2026-05-05T09:45:00-04:00"

    def test_triggered_does_not_retrigger_but_can_invalidate(self):
        # VWAP fail triggers on bar 4, then bar 5 reclaims VWAP →
        # invalidated. (Even though there's no "second trigger" to
        # test directly, this confirms the post-trigger invalidation
        # path keeps running, which is the operational point of the
        # asymmetric terminal contract.)
        plan = {
            "plan_id": "MSFT-20260505-VWF",
            "ticker": "MSFT",
            "trigger_type": "vwap_fail",
        }
        bars = _load_bars("vwap_invalidated_after_trigger.json", "MSFT")
        out = ism.step_one_plan(plan, bars, atr_14=2.0)
        assert out["triggered_at"] is not None  # did fire
        assert out["state"] == "invalidated"  # then invalidated
        assert out["invalidated_at"] is not None
