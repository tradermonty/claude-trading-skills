"""Tests for the ORL 5-min break evaluator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parents[1] / "intraday_evaluators"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import orl_evaluator as orl

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "intraday_bars"


def _load_bars(fixture_name: str, ticker: str) -> list[dict]:
    payload = json.loads((FIXTURES / fixture_name).read_text())
    return payload[ticker]


def _orl_plan() -> dict:
    return {
        "plan_id": "AAPL-20260505-ORL5",
        "ticker": "AAPL",
        "trigger_type": "orl_5min_break",
    }


class TestArmed:
    def test_no_bars_stays_armed(self):
        out = orl.evaluate(_orl_plan(), [], atr_14=2.0)
        assert out["state"] == "armed"
        assert out["evaluation_status"] == "evaluated"
        assert out["triggered_at"] is None

    def test_only_orl_bar_stays_armed(self):
        bars = _load_bars("orl_clean_break.json", "AAPL")[:1]
        out = orl.evaluate(_orl_plan(), bars, atr_14=2.0)
        assert out["state"] == "armed"
        assert out["orl_low"] == 149.00
        assert out["orl_volume"] == 2_000_000


class TestTriggered:
    def test_clean_break_fires(self):
        bars = _load_bars("orl_clean_break.json", "AAPL")
        out = orl.evaluate(_orl_plan(), bars, atr_14=2.0)
        assert out["state"] == "triggered"
        assert out["triggered_at"] == "2026-05-05T09:40:00-04:00"
        # entry = 148.50 - 0.05
        assert out["entry_actual"] == 148.45
        # stop = session_high (149.85) + 0.25 * 2.0 = 149.85 + 0.5 = 150.35
        assert out["stop_actual"] == 150.35

    def test_low_volume_does_not_fire(self):
        bars = _load_bars("orl_low_volume_no_fire.json", "AAPL")
        out = orl.evaluate(_orl_plan(), bars, atr_14=2.0)
        assert out["state"] == "armed"
        assert out["triggered_at"] is None


class TestInvalidated:
    def test_orl_invalidates_only_when_close_reclaims_both_orl_and_vwap(self):
        bars = _load_bars("orl_invalidated.json", "AAPL")
        out = orl.evaluate(_orl_plan(), bars, atr_14=2.0)
        assert out["state"] == "invalidated"
        # Triggered first, then invalidated — both timestamps populated.
        assert out["triggered_at"] == "2026-05-05T09:40:00-04:00"
        assert out["invalidated_at"] == "2026-05-05T09:45:00-04:00"
        assert out["invalidation_reason"] == "post_trigger_close_reclaimed_orl_and_vwap"

    def test_pre_trigger_reclaim_does_not_invalidate(self):
        # Reuse the no-fire fixture: bar 2 closes below ORL but vol
        # too low. Even if a later bar reclaims, plan stays armed.
        bars = _load_bars("orl_low_volume_no_fire.json", "AAPL")
        out = orl.evaluate(_orl_plan(), bars, atr_14=2.0)
        assert out["state"] == "armed"
        assert out["invalidated_at"] is None


class TestSkipPath:
    def test_atr_missing_yields_skipped(self):
        bars = _load_bars("orl_clean_break.json", "AAPL")
        out = orl.evaluate(_orl_plan(), bars, atr_14=None)
        # Skipped is an evaluation_status, not a state — state stays armed.
        assert out["state"] == "armed"
        assert out["evaluation_status"] == "skipped"
        assert out["skip_reason"] == "atr_14_unavailable"
        # No FSM advancement: triggered/invalidated still null.
        assert out["triggered_at"] is None

    def test_opening_range_bar_missing_yields_skipped(self):
        # Alpaca skips empty / halt intervals, so bars[0] could be
        # 09:35 instead of 09:30 when the opening 5 minutes had no
        # trades. ORL cannot anchor on a later bar — must skip.
        bars = _load_bars("orl_clean_break.json", "AAPL")[1:]  # drop the 09:30 bar
        assert bars[0]["ts_et"].endswith("09:35:00-04:00")
        out = orl.evaluate(_orl_plan(), bars, atr_14=2.0)
        assert out["state"] == "armed"
        assert out["evaluation_status"] == "skipped"
        assert out["skip_reason"] == "opening_range_bar_unavailable"
        # No ORL fields populated since we couldn't anchor.
        assert out["orl_low"] is None
        assert out["triggered_at"] is None


class TestIdempotency:
    def test_same_input_produces_same_output(self):
        bars = _load_bars("orl_clean_break.json", "AAPL")
        out1 = orl.evaluate(_orl_plan(), bars, atr_14=2.0)
        out2 = orl.evaluate(_orl_plan(), bars, atr_14=2.0)
        assert out1 == out2
