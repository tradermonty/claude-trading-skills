"""Test configuration and shared fixtures for strategy-pivot-designer scripts."""

import os
import sys

import pytest

# Add scripts/ directory to sys.path so detect_stagnation can be imported.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Add tests/ directory to sys.path so helpers can be imported by tests.
sys.path.insert(0, os.path.dirname(__file__))

from helpers import make_eval, make_iteration  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_iteration_history() -> dict:
    """Valid history with 5 iterations showing plateau pattern.

    Scores: 45, 62, 72, 73, 72 -- last 3 form a plateau (range=1).
    """
    evals = [
        make_eval(45, expectancy_score=8, robustness_score=12),
        make_eval(62, expectancy_score=12, robustness_score=14),
        make_eval(72, expectancy_score=15, robustness_score=16),
        make_eval(73, expectancy_score=15, robustness_score=16),
        make_eval(72, expectancy_score=15, robustness_score=16),
    ]
    iterations = [make_iteration(i + 1, ev, f"Change {i + 1}") for i, ev in enumerate(evals)]
    return {"strategy_id": "mean_revert_v2", "iterations": iterations}


@pytest.fixture()
def single_iteration_history() -> dict:
    """History with only 1 iteration."""
    return {
        "strategy_id": "single_test",
        "iterations": [
            make_iteration(1, make_eval(45)),
        ],
    }


@pytest.fixture()
def overfitting_history() -> dict:
    """History where overfitting_proxy triggers.

    Conditions: Expectancy >= 15, Risk Mgmt >= 15, Robustness < 10,
    red_flags contain 'over_optimized'.
    """
    ev1 = make_eval(50)
    ev2 = make_eval(
        78,
        expectancy_score=18,
        risk_mgmt_score=17,
        robustness_score=5,
        red_flags=[{"id": "over_optimized", "msg": "Strategy appears over-optimized"}],
    )
    return {
        "strategy_id": "overfit_strat",
        "iterations": [
            make_iteration(1, ev1, "Initial run"),
            make_iteration(2, ev2, "Added many parameters"),
        ],
    }


@pytest.fixture()
def cost_defeat_history() -> dict:
    """History where cost_defeat triggers.

    Conditions: expectancy < 0.3, profit_factor < 1.3, slippage_tested=True.
    """
    ev1 = make_eval(55)
    ev2 = make_eval(
        48,
        expectancy=0.12,
        profit_factor=1.15,
        slippage_tested=True,
    )
    return {
        "strategy_id": "thin_edge",
        "iterations": [
            make_iteration(1, ev1, "Initial run"),
            make_iteration(2, ev2, "Added slippage model"),
        ],
    }


@pytest.fixture()
def tail_risk_history() -> dict:
    """History where tail_risk triggers via high drawdown.

    Condition: max_drawdown_pct > 35.
    """
    ev = make_eval(40, max_drawdown_pct=42.0, risk_mgmt_score=4)
    return {
        "strategy_id": "risky_strat",
        "iterations": [
            make_iteration(1, ev, "Initial run"),
        ],
    }


@pytest.fixture()
def abandon_history() -> dict:
    """History with 3+ iterations, latest score < 30, monotonically non-increasing last 3.

    Scores: 28, 25, 22 -- declining and all below 30.
    """
    evals = [
        make_eval(28),
        make_eval(25),
        make_eval(22),
    ]
    return {
        "strategy_id": "hopeless_strat",
        "iterations": [make_iteration(i + 1, ev, f"Attempt {i + 1}") for i, ev in enumerate(evals)],
    }


@pytest.fixture()
def healthy_history() -> dict:
    """History with no triggers fired -- good scores, improving trajectory.

    Scores: 45, 58, 72 -- clearly improving with good internals.
    """
    evals = [
        make_eval(
            45,
            expectancy_score=10,
            risk_mgmt_score=10,
            robustness_score=12,
            max_drawdown_pct=18.0,
            expectancy=0.8,
            profit_factor=2.0,
        ),
        make_eval(
            58,
            expectancy_score=12,
            risk_mgmt_score=12,
            robustness_score=14,
            max_drawdown_pct=16.0,
            expectancy=0.9,
            profit_factor=2.2,
        ),
        make_eval(
            72,
            expectancy_score=14,
            risk_mgmt_score=14,
            robustness_score=16,
            max_drawdown_pct=14.0,
            expectancy=1.1,
            profit_factor=2.5,
        ),
    ]
    return {
        "strategy_id": "healthy_momentum",
        "iterations": [
            make_iteration(i + 1, ev, f"Improvement {i + 1}") for i, ev in enumerate(evals)
        ],
    }
