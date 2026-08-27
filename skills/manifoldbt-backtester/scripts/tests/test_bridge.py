"""Tests for the hand-off into ``backtest-expert``.

The three conversions tested first are the ones that fail silently: each
produces a plausible number that scores the strategy wrongly rather than
raising.
"""

import pytest
from bridge import NANOS_PER_YEAR, build_evaluation_inputs, format_evaluate_command


def _summary(**kw):
    base = {
        "total_trades": 200,
        "wins": 100,
        "losses": 100,
        "scratches": 0,
        "win_rate_pct": 50.0,
        "avg_win_pct": 3.0,
        "avg_loss_pct": 2.0,
        "total_fees": 0.0,
    }
    base.update(kw)
    return base


# ------------------------------------------------------- the silent-failure trio


def test_negative_drawdown_becomes_positive_percent():
    """Passing the engine's raw -0.38 would score a 38% fall as flawless."""
    out = build_evaluation_inputs({"max_drawdown": -0.3846}, _summary())
    assert out["max_drawdown_pct"] == 38.46


def test_trade_count_comes_from_round_trips_not_fills():
    """The engine's total_trades counts fills, about twice the round trips.

    Handing fills to the sample-size dimension doubles the apparent sample.
    """
    metrics = {"max_drawdown": -0.1, "trade_stats": {"total_trades": 400}}
    out = build_evaluation_inputs(metrics, _summary(total_trades=200))
    assert out["total_trades"] == 200


def test_percentages_all_come_from_the_same_pairing():
    """Win rate must describe the same population as the averages beside it."""
    metrics = {"max_drawdown": -0.1, "trade_stats": {"win_rate": 0.50}}
    out = build_evaluation_inputs(metrics, _summary(win_rate_pct=50.0))
    assert out["win_rate"] == 50.0
    assert not any("differ by" in w for w in out["warnings"])


# ------------------------------------------------------------------- disagreement


def test_win_rate_disagreement_is_reported_not_hidden():
    metrics = {"max_drawdown": -0.1, "trade_stats": {"win_rate": 0.28}}
    out = build_evaluation_inputs(metrics, _summary(win_rate_pct=50.0))
    assert any("differ by" in w for w in out["warnings"])


# ------------------------------------------------------------------------ years


def test_years_derived_from_the_tested_span():
    start = 1_600_000_000_000_000_000
    out = build_evaluation_inputs(
        {"max_drawdown": -0.1},
        _summary(),
        start_ns=start,
        end_ns=start + int(NANOS_PER_YEAR * 5),
    )
    assert out["years_tested"] == 5


def test_span_under_a_year_is_flagged():
    start = 1_600_000_000_000_000_000
    out = build_evaluation_inputs(
        {"max_drawdown": -0.1},
        _summary(),
        start_ns=start,
        end_ns=start + int(NANOS_PER_YEAR * 0.5),
    )
    assert out["years_tested"] == 0
    assert any("under a year" in w for w in out["warnings"])


# ---------------------------------------------------------------------- warnings


def test_no_round_trip_is_rejected_instead_of_scored():
    with pytest.raises(ValueError, match="no completed round trip"):
        build_evaluation_inputs({"max_drawdown": -0.1}, _summary(total_trades=0))


def test_thin_sample_is_named_before_the_evaluator_scores_it_zero():
    out = build_evaluation_inputs({"max_drawdown": -0.1}, _summary(total_trades=12))
    assert any("scores 0 below 30" in w for w in out["warnings"])


def test_frictionless_run_is_flagged():
    out = build_evaluation_inputs({"max_drawdown": -0.1}, _summary(), slippage_tested=False)
    assert any("no slippage" in w for w in out["warnings"])


def test_missing_drawdown_is_rejected_instead_of_scored_as_zero():
    with pytest.raises(ValueError, match="max_drawdown absent"):
        build_evaluation_inputs({}, _summary())


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_drawdown_is_rejected(value):
    with pytest.raises(ValueError, match="must be finite"):
        build_evaluation_inputs({"max_drawdown": value}, _summary())


def test_non_numeric_drawdown_is_rejected():
    with pytest.raises(ValueError, match="not numeric"):
        build_evaluation_inputs({"max_drawdown": "unknown"}, _summary())


def test_scratch_population_is_rejected_before_expectancy_is_distorted():
    with pytest.raises(ValueError, match="scratch trade"):
        build_evaluation_inputs(
            {"max_drawdown": -0.1},
            _summary(
                total_trades=100,
                wins=1,
                losses=0,
                scratches=99,
                win_rate_pct=1.0,
                avg_win_pct=10.0,
                avg_loss_pct=0.0,
            ),
        )


# ----------------------------------------------------------------- command output


def test_command_carries_every_value():
    out = build_evaluation_inputs(
        {"max_drawdown": -0.2}, _summary(), num_parameters=3, slippage_tested=True
    )
    cmd = format_evaluate_command(out)
    assert "--total-trades 200" in cmd
    assert "--max-drawdown-pct 20.0" in cmd
    assert "--num-parameters 3" in cmd
    assert cmd.endswith("--slippage-tested")


def test_command_omits_the_flag_when_friction_was_not_modelled():
    out = build_evaluation_inputs({"max_drawdown": -0.2}, _summary(), slippage_tested=False)
    assert "--slippage-tested" not in format_evaluate_command(out)
