"""Shared test helpers for building iteration history data."""

from __future__ import annotations


def make_eval(
    total_score: int,
    verdict: str = "Refine",
    sample_size: int = 10,
    expectancy_score: int = 10,
    risk_mgmt_score: int = 12,
    robustness_score: int = 15,
    exec_realism_score: int = 0,
    red_flags: list | None = None,
    profit_factor: float = 1.8,
    expectancy: float = 0.5,
    total_trades: int = 50,
    win_rate: int = 58,
    avg_win_pct: float = 1.5,
    avg_loss_pct: float = 1.0,
    max_drawdown_pct: float = 22.0,
    years_tested: int = 8,
    num_parameters: int = 3,
    slippage_tested: bool = False,
) -> dict:
    """Build a well-formed eval dict with customisable fields."""
    return {
        "total_score": total_score,
        "verdict": verdict,
        "dimensions": [
            {"name": "Sample Size", "score": sample_size, "max_score": 20},
            {"name": "Expectancy", "score": expectancy_score, "max_score": 20},
            {"name": "Risk Management", "score": risk_mgmt_score, "max_score": 20},
            {"name": "Robustness", "score": robustness_score, "max_score": 20},
            {"name": "Execution Realism", "score": exec_realism_score, "max_score": 20},
        ],
        "red_flags": red_flags or [],
        "profit_factor": profit_factor,
        "expectancy": expectancy,
        "inputs": {
            "total_trades": total_trades,
            "win_rate": win_rate,
            "avg_win_pct": avg_win_pct,
            "avg_loss_pct": avg_loss_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "years_tested": years_tested,
            "num_parameters": num_parameters,
            "slippage_tested": slippage_tested,
        },
    }


def make_iteration(
    iteration: int,
    eval_data: dict,
    changes: str = "",
    timestamp: str = "2026-02-10T12:00:00Z",
) -> dict:
    """Wrap an eval dict into a full iteration entry."""
    return {
        "iteration": iteration,
        "timestamp": timestamp,
        "changes_from_previous": changes or f"Iteration {iteration}",
        "eval": eval_data,
    }
