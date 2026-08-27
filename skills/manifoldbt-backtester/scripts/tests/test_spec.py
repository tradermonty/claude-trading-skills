"""Tests for spec validation and the parameter count.

Validation exists to fail before the data is loaded, so the tests are mostly
about rejecting things clearly rather than accepting things quietly.
"""

import pytest
from spec import SpecError, count_parameters, describe_warnings, validate_spec


def _spec(**kw):
    base = {
        "name": "sma_cross",
        "indicators": {
            "fast": {"type": "sma", "period": 20},
            "slow": {"type": "sma", "period": 60},
        },
        "entry": {"left": "fast", "op": ">", "right": "slow"},
    }
    base.update(kw)
    return base


# ------------------------------------------------------------------ acceptance


def test_minimal_spec_normalises_with_defaults():
    out = validate_spec(_spec())
    assert out["size"] == 1.0
    assert out["fees_bps"] == 0.0
    # One bar, not zero: filling on the signal bar is look-ahead.
    assert out["signal_delay"] == 1
    assert out["indicators"]["fast"]["source"] == "close"


def test_numeric_threshold_is_accepted_as_an_operand():
    out = validate_spec(
        _spec(
            indicators={"rsi": {"type": "rsi", "period": 14}},
            entry={"left": "rsi", "op": "<", "right": 30},
        )
    )
    assert out["entry"]["right"] == 30


def test_price_column_is_accepted_as_an_operand():
    out = validate_spec(_spec(entry={"left": "close", "op": ">", "right": "slow"}))
    assert out["entry"]["left"] == "close"


# ------------------------------------------------------------------- rejection


def test_unknown_indicator_reference_is_named():
    with pytest.raises(SpecError, match="neither a declared indicator"):
        validate_spec(_spec(entry={"left": "typo", "op": ">", "right": "slow"}))


def test_unsupported_indicator_type_lists_what_is_supported():
    with pytest.raises(SpecError, match="supported: ema, rsi, sma"):
        validate_spec(_spec(indicators={"x": {"type": "kalman", "period": 5}}))


def test_non_positive_period_is_rejected():
    with pytest.raises(SpecError, match="positive integer"):
        validate_spec(_spec(indicators={"x": {"type": "sma", "period": 0}}))


def test_boolean_period_is_not_an_integer():
    """`True` is an int in Python; a spec that says True must not build a period."""
    with pytest.raises(SpecError, match="positive integer"):
        validate_spec(_spec(indicators={"x": {"type": "sma", "period": True}}))


def test_size_outside_the_unit_interval_is_rejected():
    with pytest.raises(SpecError, match="must be in"):
        validate_spec(_spec(size=1.5))


def test_empty_indicator_block_is_rejected():
    with pytest.raises(SpecError, match="at least one indicator"):
        validate_spec(_spec(indicators={}))


def test_negative_cost_is_rejected():
    with pytest.raises(SpecError, match="cannot be negative"):
        validate_spec(_spec(fees_bps=-1))


# ------------------------------------------------------------- parameter count


def test_parameters_count_indicator_periods():
    assert count_parameters(_spec()) == 2


def test_numeric_threshold_counts_as_a_parameter():
    s = _spec(
        indicators={"rsi": {"type": "rsi", "period": 14}},
        entry={"left": "rsi", "op": "<", "right": 30},
    )
    assert count_parameters(s) == 2  # the period and the threshold


def test_bracket_distances_count_as_parameters():
    assert count_parameters(_spec(stop_loss_pct=1.0, take_profit_pct=2.0)) == 4


def test_explicit_position_size_counts_as_a_parameter():
    assert count_parameters(_spec(size=0.25)) == 3


def test_default_position_size_is_not_counted_when_omitted():
    assert count_parameters(_spec()) == 2


def test_costs_are_not_parameters():
    """Fees are imposed by the market, not fitted; counting them would flatter
    nothing and would misreport how much freedom the strategy really has."""
    assert count_parameters(_spec(fees_bps=5, slippage_bps=2)) == 2


# ---------------------------------------------------------------- pre-warnings


def test_zero_delay_is_flagged_as_look_ahead():
    assert any("look-ahead" in w for w in describe_warnings(_spec(signal_delay=0)))


def test_frictionless_spec_is_flagged_before_running():
    assert any("frictionless" in w for w in describe_warnings(_spec()))


def test_knob_count_above_four_is_flagged():
    s = _spec(
        indicators={f"i{i}": {"type": "sma", "period": 10 + i} for i in range(4)},
        stop_loss_pct=1.0,
        take_profit_pct=2.0,
    )
    assert any("tunable parameters" in w for w in describe_warnings(s))
