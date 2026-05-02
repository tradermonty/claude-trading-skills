"""Tests for state_caps.evaluate_state_caps."""

from state_caps import evaluate_state_caps


def _candidate(**overrides) -> dict:
    base = {
        "close": 80.0,
        "session_high": 81.0,
        "session_low": 70.0,
        "is_at_52w_high_recently": False,
        "volume_ratio_20d": 1.0,
        "premarket_gap_pct": None,
    }
    base.update(overrides)
    return base


class TestStillInMarkup:
    def test_strong_close_at_52w_high_caps(self):
        # close = 80, low = 70, high = 81 → range_pos = 10/11 ≈ 0.91
        out = evaluate_state_caps(_candidate(is_at_52w_high_recently=True))
        assert "still_in_markup" in out["state_caps"]

    def test_strong_close_but_not_52w_does_not_cap(self):
        out = evaluate_state_caps(_candidate(is_at_52w_high_recently=False))
        assert "still_in_markup" not in out["state_caps"]


class TestTooEarly:
    def test_strong_close_with_volume_warns(self):
        out = evaluate_state_caps(_candidate(volume_ratio_20d=3.0))
        assert "too_early_to_short" in out["warnings"]

    def test_does_not_double_apply_when_already_capped(self):
        # When still_in_markup also fires, too_early_to_short should NOT
        # be added (the stronger signal already constrains Phase 2).
        out = evaluate_state_caps(_candidate(is_at_52w_high_recently=True, volume_ratio_20d=3.0))
        assert "still_in_markup" in out["state_caps"]
        assert "too_early_to_short" not in out["warnings"]


class TestWaitForFirstCrack:
    def test_premarket_gap_triggers(self):
        out = evaluate_state_caps(_candidate(premarket_gap_pct=8.0))
        assert "wait_for_first_crack" in out["warnings"]

    def test_small_premarket_gap_does_not_trigger(self):
        out = evaluate_state_caps(_candidate(premarket_gap_pct=2.0))
        assert "wait_for_first_crack" not in out["warnings"]


class TestEmpty:
    def test_no_signals_returns_empty(self):
        out = evaluate_state_caps(
            _candidate(
                close=75.0,  # mid-range
                volume_ratio_20d=0.8,
                premarket_gap_pct=None,
            )
        )
        assert out["state_caps"] == []
        assert out["warnings"] == []
