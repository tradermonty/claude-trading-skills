"""Unit tests for detect_stagnation.py."""

import json
from pathlib import Path

import detect_stagnation as ds
import pytest
from helpers import make_eval, make_iteration

# ---- Validation tests ----


def test_missing_strategy_id_raises() -> None:
    history = {
        "iterations": [
            {"eval": {"total_score": 50, "dimensions": [], "red_flags": [], "inputs": {}}}
        ]
    }
    with pytest.raises(ValueError, match="strategy_id"):
        ds.validate_history(history)


def test_empty_iterations_raises() -> None:
    history = {"strategy_id": "x", "iterations": []}
    with pytest.raises(ValueError, match="iterations"):
        ds.validate_history(history)


def test_missing_eval_in_iteration_raises() -> None:
    history = {"strategy_id": "x", "iterations": [{"iteration": 1}]}
    with pytest.raises(ValueError, match="eval"):
        ds.validate_history(history)


def test_missing_dimensions_in_eval_raises() -> None:
    history = {
        "strategy_id": "x",
        "iterations": [
            {"iteration": 1, "eval": {"total_score": 50, "red_flags": [], "inputs": {}}}
        ],
    }
    with pytest.raises(ValueError, match="dimensions"):
        ds.validate_history(history)


def test_missing_total_score_in_eval_raises() -> None:
    history = {
        "strategy_id": "x",
        "iterations": [{"iteration": 1, "eval": {"dimensions": [], "red_flags": [], "inputs": {}}}],
    }
    with pytest.raises(ValueError, match="total_score"):
        ds.validate_history(history)


def test_dimension_missing_name_raises() -> None:
    history = {
        "strategy_id": "x",
        "iterations": [
            {
                "iteration": 1,
                "eval": {
                    "total_score": 50,
                    "dimensions": [{"score": 10, "max_score": 20}],
                    "red_flags": [],
                    "inputs": {},
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="missing 'name'"):
        ds.validate_history(history)


def test_dimension_missing_score_raises() -> None:
    history = {
        "strategy_id": "x",
        "iterations": [
            {
                "iteration": 1,
                "eval": {
                    "total_score": 50,
                    "dimensions": [{"name": "Expectancy", "max_score": 20}],
                    "red_flags": [],
                    "inputs": {},
                },
            }
        ],
    }
    with pytest.raises(ValueError, match="missing 'score'"):
        ds.validate_history(history)


# ---- Helper tests ----


def test_get_dimension_score_by_name() -> None:
    eval_data = {
        "dimensions": [
            {"name": "Expectancy", "score": 15, "max_score": 20},
            {"name": "Risk Management", "score": 12, "max_score": 20},
        ],
    }
    assert ds.get_dimension_score(eval_data, "Expectancy") == 15


def test_get_dimension_score_missing_name() -> None:
    eval_data = {
        "dimensions": [
            {"name": "Expectancy", "score": 15, "max_score": 20},
        ],
    }
    assert ds.get_dimension_score(eval_data, "NonExistent") is None


def test_get_red_flag_ids_extracts_ids() -> None:
    eval_data = {
        "red_flags": [
            {"id": "over_optimized", "msg": "over-optimized"},
            {"id": "short_test_period", "msg": "too short"},
        ],
    }
    assert ds.get_red_flag_ids(eval_data) == ["over_optimized", "short_test_period"]


def test_get_red_flag_ids_empty() -> None:
    eval_data = {"red_flags": []}
    assert ds.get_red_flag_ids(eval_data) == []


# ---- Plateau trigger tests ----


def test_plateau_fires_when_scores_within_threshold(sample_iteration_history: dict) -> None:
    """Last 3 scores [72, 73, 72] -> range=1 < threshold=3."""
    iters = sample_iteration_history["iterations"]
    result = ds.detect_plateau(iters, k=3, threshold=3)
    assert result is not None
    assert result["trigger"] == "improvement_plateau"
    assert result["severity"] == "high"
    assert result["evidence"]["score_range"] == 1
    assert result["evidence"]["last_k_scores"] == [72, 73, 72]


def test_plateau_not_fires_when_scores_vary() -> None:
    """Scores [45, 62, 72] -> range=27, well above threshold."""
    iters = [
        make_iteration(1, make_eval(45)),
        make_iteration(2, make_eval(62)),
        make_iteration(3, make_eval(72)),
    ]
    result = ds.detect_plateau(iters, k=3, threshold=3)
    assert result is None


def test_plateau_needs_minimum_k_iterations() -> None:
    """Fewer than K iterations should not fire."""
    iters = [
        make_iteration(1, make_eval(72)),
        make_iteration(2, make_eval(73)),
    ]
    result = ds.detect_plateau(iters, k=3, threshold=3)
    assert result is None


# ---- Overfitting proxy tests ----


def test_overfitting_fires_when_all_conditions_met(overfitting_history: dict) -> None:
    latest_eval = overfitting_history["iterations"][-1]["eval"]
    result = ds.detect_overfitting_proxy(latest_eval)
    assert result is not None
    assert result["trigger"] == "overfitting_proxy"
    assert result["severity"] == "medium"
    assert result["evidence"]["expectancy_score"] == 18
    assert result["evidence"]["robustness_score"] == 5
    assert "over_optimized" in result["evidence"]["red_flag_ids"]


def test_overfitting_not_fires_missing_red_flags() -> None:
    """Expectancy>=15, RiskMgmt>=15, Robustness<10 but no relevant red flags."""
    ev = make_eval(
        70,
        expectancy_score=18,
        risk_mgmt_score=16,
        robustness_score=5,
        red_flags=[],  # no over_optimized or short_test_period
    )
    result = ds.detect_overfitting_proxy(ev)
    assert result is None


def test_overfitting_not_fires_robustness_high() -> None:
    """Robustness >= 10 should prevent firing even with red flags."""
    ev = make_eval(
        80,
        expectancy_score=18,
        risk_mgmt_score=16,
        robustness_score=12,
        red_flags=[{"id": "over_optimized", "msg": "over-optimized"}],
    )
    result = ds.detect_overfitting_proxy(ev)
    assert result is None


# ---- Cost defeat tests ----


def test_cost_defeat_fires_all_conditions(cost_defeat_history: dict) -> None:
    latest_eval = cost_defeat_history["iterations"][-1]["eval"]
    result = ds.detect_cost_defeat(latest_eval)
    assert result is not None
    assert result["trigger"] == "cost_defeat"
    assert result["severity"] == "medium"
    assert result["evidence"]["expectancy"] == 0.12
    assert result["evidence"]["profit_factor"] == 1.15
    assert result["evidence"]["slippage_tested"] is True


def test_cost_defeat_not_fires_without_slippage() -> None:
    """slippage_tested=False prevents firing."""
    ev = make_eval(48, expectancy=0.12, profit_factor=1.15, slippage_tested=False)
    result = ds.detect_cost_defeat(ev)
    assert result is None


def test_cost_defeat_not_fires_high_expectancy() -> None:
    """expectancy >= 0.3 prevents firing."""
    ev = make_eval(60, expectancy=0.5, profit_factor=1.15, slippage_tested=True)
    result = ds.detect_cost_defeat(ev)
    assert result is None


# ---- Tail risk tests ----


def test_tail_risk_fires_high_drawdown(tail_risk_history: dict) -> None:
    latest_eval = tail_risk_history["iterations"][-1]["eval"]
    result = ds.detect_tail_risk(latest_eval)
    assert result is not None
    assert result["trigger"] == "tail_risk"
    assert result["severity"] == "high"
    assert result["evidence"]["max_drawdown_pct"] == 42.0


def test_tail_risk_fires_low_risk_mgmt_score() -> None:
    """Risk Management score <= 5 fires tail risk even with moderate drawdown."""
    ev = make_eval(40, risk_mgmt_score=4, max_drawdown_pct=25.0)
    result = ds.detect_tail_risk(ev)
    assert result is not None
    assert result["trigger"] == "tail_risk"
    assert "Risk Management score=4" in result["message"]


def test_tail_risk_fires_on_single_iteration(tail_risk_history: dict) -> None:
    """Tail risk can fire on a history with only 1 iteration."""
    assert len(tail_risk_history["iterations"]) == 1
    result = ds.run_all_triggers(tail_risk_history)
    triggers = [t["trigger"] for t in result["triggers_fired"]]
    assert "tail_risk" in triggers


def test_tail_risk_not_fires_moderate_values() -> None:
    """Moderate drawdown and decent risk score should not fire."""
    ev = make_eval(60, risk_mgmt_score=12, max_drawdown_pct=20.0)
    result = ds.detect_tail_risk(ev)
    assert result is None


# ---- Integration tests ----


def test_run_all_triggers_plateau_detected(sample_iteration_history: dict) -> None:
    result = ds.run_all_triggers(sample_iteration_history)
    assert result["stagnation_detected"] is True
    triggers = [t["trigger"] for t in result["triggers_fired"]]
    assert "improvement_plateau" in triggers
    assert result["recommendation"] == "pivot"
    assert result["strategy_id"] == "mean_revert_v2"
    assert result["score_trajectory"] == [45, 62, 72, 73, 72]
    assert result["iteration_count"] == 5


def test_run_all_triggers_healthy(healthy_history: dict) -> None:
    result = ds.run_all_triggers(healthy_history)
    assert result["stagnation_detected"] is False
    assert result["triggers_fired"] == []
    assert result["recommendation"] == "continue"


def test_run_all_triggers_abandon(abandon_history: dict) -> None:
    result = ds.run_all_triggers(abandon_history)
    assert result["recommendation"] == "abandon"
    assert result["stagnation_detected"] is True  # abandon implies stagnation
    assert result["score_trajectory"] == [28, 25, 22]


# ---- Append eval tests ----


def test_append_eval_strategy_id_mismatch_raises(tmp_path: Path) -> None:
    """Appending with wrong strategy_id must raise ValueError."""
    existing = {
        "strategy_id": "strat_alpha",
        "iterations": [
            {
                "iteration": 1,
                "timestamp": "2026-02-10T12:00:00Z",
                "changes_from_previous": "Initial",
                "eval": {"total_score": 40, "dimensions": [], "red_flags": [], "inputs": {}},
            },
        ],
    }
    history_path = tmp_path / "history.json"
    history_path.write_text(json.dumps(existing))

    eval_data = {"total_score": 60, "dimensions": [], "red_flags": [], "inputs": {}}
    eval_path = tmp_path / "eval_mismatch.json"
    eval_path.write_text(json.dumps(eval_data))

    with pytest.raises(ValueError, match="strategy_id mismatch"):
        ds.append_eval(eval_path, history_path, "strat_beta", changes="Wrong id")


def test_append_eval_creates_new_history(tmp_path: Path) -> None:
    """Append eval to a non-existent history file -> creates new history."""
    eval_data = {
        "total_score": 55,
        "verdict": "Refine",
        "dimensions": [{"name": "Expectancy", "score": 12, "max_score": 20}],
        "red_flags": [],
        "profit_factor": 1.9,
        "expectancy": 0.6,
        "inputs": {"total_trades": 60, "slippage_tested": False},
    }
    eval_path = tmp_path / "eval.json"
    eval_path.write_text(json.dumps(eval_data))

    history_path = tmp_path / "history.json"
    assert not history_path.exists()

    result = ds.append_eval(eval_path, history_path, "new_strat", changes="Initial run")

    assert history_path.exists()
    assert result["strategy_id"] == "new_strat"
    assert len(result["iterations"]) == 1
    assert result["iterations"][0]["iteration"] == 1
    assert result["iterations"][0]["eval"]["total_score"] == 55
    assert result["iterations"][0]["changes_from_previous"] == "Initial run"


def test_append_eval_increments_iteration(tmp_path: Path) -> None:
    """Append eval to existing history -> increments iteration number."""
    existing = {
        "strategy_id": "existing_strat",
        "iterations": [
            {
                "iteration": 1,
                "timestamp": "2026-02-10T12:00:00Z",
                "changes_from_previous": "Initial",
                "eval": {"total_score": 40, "dimensions": [], "red_flags": [], "inputs": {}},
            },
        ],
    }
    history_path = tmp_path / "history.json"
    history_path.write_text(json.dumps(existing))

    eval_data = {
        "total_score": 60,
        "verdict": "Refine",
        "dimensions": [],
        "red_flags": [],
        "inputs": {},
    }
    eval_path = tmp_path / "eval2.json"
    eval_path.write_text(json.dumps(eval_data))

    result = ds.append_eval(eval_path, history_path, "existing_strat", changes="Added filter")

    assert len(result["iterations"]) == 2
    assert result["iterations"][-1]["iteration"] == 2
    assert result["iterations"][-1]["eval"]["total_score"] == 60
    assert result["iterations"][-1]["changes_from_previous"] == "Added filter"


# ---- CLI corrupt history test ----


def test_main_corrupt_history_returns_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Detection mode with corrupt JSON history returns 1, not traceback."""
    history_path = tmp_path / "bad.json"
    history_path.write_text("{broken json!!!")
    monkeypatch.setattr(
        "sys.argv",
        ["detect_stagnation.py", "--history", str(history_path), "--output-dir", str(tmp_path)],
    )
    assert ds.main() == 1
