"""Tests for Component 2: Alt Breadth Participation Calculator."""

from calculators.alt_breadth_calculator import calculate_alt_breadth


def test_too_few_alts_flags_unavailable(universe):
    result = calculate_alt_breadth(universe(n_up=2, n_down=1))
    assert result["data_available"] is False
    assert result["score"] == 50


def test_broad_participation_scores_high(universe):
    result = calculate_alt_breadth(universe(n_up=9, n_down=1))
    assert result["data_available"] is True
    assert result["score"] >= 90  # 90% above 200DMA
    assert result["pct_above_200dma"] == 90.0


def test_narrow_participation_scores_low(universe):
    result = calculate_alt_breadth(universe(n_up=1, n_down=9))
    assert result["score"] <= 25
    assert result["pct_above_200dma"] == 10.0


def test_short_history_coins_are_skipped(universe):
    series = universe(n_up=6, n_down=0)
    series["NEWCOIN"] = [1.0] * 30  # too short for 200DMA
    result = calculate_alt_breadth(series)
    assert result["universe_size"] == 6
    assert "NEWCOIN" in result["skipped"]


def test_short_history_coins_do_not_change_50dma_confirmation_cohort(universe):
    eligible = [50.0] * 150 + [200.0] * 49 + [100.0]
    series = {f"ALT{i}": eligible.copy() for i in range(6)}
    baseline = calculate_alt_breadth(series)
    series["NEWCOIN"] = [float(i + 1) for i in range(100)]

    result = calculate_alt_breadth(series)

    assert result["pct_above_50dma"] == baseline["pct_above_50dma"]
    assert result["universe_size"] == baseline["universe_size"]
    assert "NEWCOIN" in result["skipped"]


def test_rollover_modifier_reduces_score(universe):
    # All above 200DMA but recent 60 days sharply down -> below 50DMA.
    series = universe(n_up=10, n_down=0)
    for closes in series.values():
        for i in range(len(closes) - 60, len(closes)):
            closes[i] = closes[len(closes) - 61] * 0.90
    result = calculate_alt_breadth(series)
    assert result["pct_above_50dma"] < result["pct_above_200dma"]
    assert "rolling over" in result["signal"]
