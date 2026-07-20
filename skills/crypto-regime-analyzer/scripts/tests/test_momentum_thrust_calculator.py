"""Tests for Component 6: Momentum Thrust / Washout Calculator."""

from calculators.momentum_thrust_calculator import calculate_momentum_thrust


def test_too_small_universe_flags_unavailable(universe):
    result = calculate_momentum_thrust(universe(n_up=2, n_down=1))
    assert result["data_available"] is False


def test_broad_thrust_scores_high(universe):
    result = calculate_momentum_thrust(universe(n_up=9, n_down=1))
    assert result["score"] == 90
    assert "BROAD THRUST" in result["signal"]


def test_weak_momentum_scores_low(universe):
    result = calculate_momentum_thrust(universe(n_up=3, n_down=7))
    assert result["score"] == 35
    assert "WEAK" in result["signal"]


def test_washout_contrarian_bump(universe):
    total_negative = calculate_momentum_thrust(universe(n_up=0, n_down=10))
    broadly_negative = calculate_momentum_thrust(universe(n_up=2, n_down=8))
    assert "WASHOUT" in total_negative["signal"]
    assert total_negative["score"] > broadly_negative["score"]


def test_short_history_coins_ignored(universe):
    series = universe(n_up=6, n_down=0)
    series["NEWCOIN"] = [1.0] * 10
    result = calculate_momentum_thrust(series)
    assert result["universe_size"] == 6
