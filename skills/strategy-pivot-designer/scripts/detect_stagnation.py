#!/usr/bin/env python3
"""Detect backtest iteration stagnation for strategy pivot decisions.

Runs four deterministic triggers against an iteration history file and
returns a diagnosis with a recommendation of *continue*, *pivot*, or
*abandon*.  See ``references/stagnation_triggers.md`` for the full
specification.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_history(history: dict[str, Any]) -> None:
    """Validate iteration history structure.

    Raises ``ValueError`` when required fields are missing or malformed.
    """
    sid = history.get("strategy_id")
    if not sid or not isinstance(sid, str):
        raise ValueError("strategy_id must be a non-empty string")

    iterations = history.get("iterations")
    if not iterations or not isinstance(iterations, list) or len(iterations) == 0:
        raise ValueError("iterations must be a non-empty list")

    for idx, it in enumerate(iterations):
        if "eval" not in it:
            raise ValueError(f"iterations[{idx}] missing 'eval' key")
        ev = it["eval"]

        # total_score is required for trajectory and recommendation logic
        if "total_score" not in ev:
            raise ValueError(f"iterations[{idx}].eval missing 'total_score'")

        if "dimensions" not in ev:
            raise ValueError(f"iterations[{idx}].eval missing 'dimensions' list")

        # Validate each dimension has required name/score keys
        for dim_idx, dim in enumerate(ev["dimensions"]):
            if not isinstance(dim, dict):
                raise ValueError(f"iterations[{idx}].eval.dimensions[{dim_idx}] must be a mapping")
            if "name" not in dim:
                raise ValueError(f"iterations[{idx}].eval.dimensions[{dim_idx}] missing 'name'")
            if "score" not in dim:
                raise ValueError(f"iterations[{idx}].eval.dimensions[{dim_idx}] missing 'score'")

        if "red_flags" not in ev:
            raise ValueError(f"iterations[{idx}].eval missing 'red_flags' list")
        if "inputs" not in ev:
            raise ValueError(f"iterations[{idx}].eval missing 'inputs' dict")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_dimension_score(eval_data: dict[str, Any], name: str) -> int | None:
    """Look up a dimension score by *name*.  Returns ``None`` if not found."""
    for dim in eval_data.get("dimensions", []):
        if dim.get("name") == name:
            return dim.get("score")
    return None


def get_red_flag_ids(eval_data: dict[str, Any]) -> list[str]:
    """Extract red-flag IDs from *eval_data*."""
    return [f["id"] for f in eval_data.get("red_flags", []) if isinstance(f, dict) and "id" in f]


# ---------------------------------------------------------------------------
# Trigger detectors
# ---------------------------------------------------------------------------


def detect_plateau(
    iterations: list[dict],
    k: int = 3,
    threshold: int = 3,
) -> dict | None:
    """Detect improvement plateau over the last *k* iterations.

    Returns a trigger dict when the range of ``total_score`` values in the
    last *k* iterations is strictly less than *threshold*.
    """
    if len(iterations) < k:
        return None

    last_k = [it["eval"]["total_score"] for it in iterations[-k:]]
    score_range = max(last_k) - min(last_k)

    if score_range < threshold:
        return {
            "trigger": "improvement_plateau",
            "severity": "high",
            "evidence": {
                "last_k_scores": last_k,
                "score_range": score_range,
                "threshold": threshold,
            },
            "message": (
                f"{k} consecutive iterations with <{threshold}-point "
                f"score improvement (range: {score_range})"
            ),
        }
    return None


def detect_overfitting_proxy(eval_data: dict[str, Any]) -> dict | None:
    """Detect overfitting proxy.

    Fires when Expectancy >= 15, Risk Management >= 15, Robustness < 10,
    AND red-flags contain ``over_optimized`` or ``short_test_period``.
    """
    exp_score = get_dimension_score(eval_data, "Expectancy")
    risk_score = get_dimension_score(eval_data, "Risk Management")
    rob_score = get_dimension_score(eval_data, "Robustness")
    red_flag_ids = get_red_flag_ids(eval_data)

    if (
        exp_score is not None
        and exp_score >= 15
        and risk_score is not None
        and risk_score >= 15
        and rob_score is not None
        and rob_score < 10
        and ("over_optimized" in red_flag_ids or "short_test_period" in red_flag_ids)
    ):
        return {
            "trigger": "overfitting_proxy",
            "severity": "medium",
            "evidence": {
                "expectancy_score": exp_score,
                "risk_mgmt_score": risk_score,
                "robustness_score": rob_score,
                "red_flag_ids": red_flag_ids,
            },
            "message": ("High in-sample scores with low robustness and curve-fitting red flags"),
        }
    return None


def detect_cost_defeat(eval_data: dict[str, Any]) -> dict | None:
    """Detect cost defeat.

    Fires when ``expectancy < 0.3``, ``profit_factor < 1.3``, and
    ``slippage_tested`` is ``True``.
    """
    expectancy = eval_data.get("expectancy", 999)
    profit_factor = eval_data.get("profit_factor", 999)
    inputs = eval_data.get("inputs", {})
    slippage_tested = inputs.get("slippage_tested", False)

    if expectancy < 0.3 and profit_factor < 1.3 and slippage_tested:
        return {
            "trigger": "cost_defeat",
            "severity": "medium",
            "evidence": {
                "expectancy": expectancy,
                "profit_factor": profit_factor,
                "slippage_tested": slippage_tested,
            },
            "message": (
                f"Edge too thin after costs (expectancy={expectancy:.3f}, PF={profit_factor:.2f})"
            ),
        }
    return None


def detect_tail_risk(eval_data: dict[str, Any]) -> dict | None:
    """Detect tail risk.

    Fires when ``max_drawdown_pct > 35`` OR Risk Management score <= 5.
    """
    inputs = eval_data.get("inputs", {})
    max_dd = inputs.get("max_drawdown_pct", 0)
    risk_score = get_dimension_score(eval_data, "Risk Management")

    reasons: list[str] = []
    if max_dd > 35:
        reasons.append(f"max_drawdown_pct={max_dd}% > 35%")
    if risk_score is not None and risk_score <= 5:
        reasons.append(f"Risk Management score={risk_score} <= 5")

    if reasons:
        return {
            "trigger": "tail_risk",
            "severity": "high",
            "evidence": {
                "max_drawdown_pct": max_dd,
                "risk_mgmt_score": risk_score,
            },
            "message": f"Structural risk: {'; '.join(reasons)}",
        }
    return None


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def _determine_recommendation(
    triggers_fired: list[dict],
    score_trajectory: list[int],
    iteration_count: int,
) -> str:
    """Apply the recommendation decision table (priority order).

    1. ``abandon`` -- iterations >= 3, latest score < 30, last-3 monotonically
       non-increasing.
    2. ``pivot`` -- at least one trigger fired.
    3. ``continue`` -- default.
    """
    # Priority 1: abandon
    if iteration_count >= 3 and score_trajectory[-1] < 30 and len(score_trajectory) >= 3:
        last_3 = score_trajectory[-3:]
        if all(last_3[i] >= last_3[i + 1] for i in range(len(last_3) - 1)):
            return "abandon"

    # Priority 2: pivot
    if triggers_fired:
        return "pivot"

    # Priority 3: continue
    return "continue"


def run_all_triggers(
    history: dict[str, Any],
    plateau_k: int = 3,
    plateau_threshold: int = 3,
) -> dict[str, Any]:
    """Run all stagnation triggers and return a full diagnosis dict."""
    validate_history(history)

    iterations = history["iterations"]
    latest_eval = iterations[-1]["eval"]
    latest_inputs = latest_eval.get("inputs", {})

    triggers_fired: list[dict] = []

    # Plateau -- needs >= k iterations
    plateau = detect_plateau(iterations, k=plateau_k, threshold=plateau_threshold)
    if plateau:
        triggers_fired.append(plateau)

    # Overfitting proxy -- needs >= 2 iterations
    if len(iterations) >= 2:
        overfit = detect_overfitting_proxy(latest_eval)
        if overfit:
            triggers_fired.append(overfit)

    # Cost defeat -- needs >= 2 iterations
    if len(iterations) >= 2:
        cost = detect_cost_defeat(latest_eval)
        if cost:
            triggers_fired.append(cost)

    # Tail risk -- can fire on a single iteration
    tail = detect_tail_risk(latest_eval)
    if tail:
        triggers_fired.append(tail)

    # Score trajectory
    score_trajectory = [it["eval"]["total_score"] for it in iterations]

    # Recommendation
    recommendation = _determine_recommendation(triggers_fired, score_trajectory, len(iterations))

    # Dimension scores summary from latest eval
    dim_scores: dict[str, int] = {}
    for dim in latest_eval.get("dimensions", []):
        dim_scores[dim["name"]] = dim["score"]

    return {
        "strategy_id": history["strategy_id"],
        "stagnation_detected": recommendation != "continue",
        "triggers_fired": triggers_fired,
        "iteration_count": len(iterations),
        "score_trajectory": score_trajectory,
        "latest_eval_summary": {
            "total_score": latest_eval.get("total_score"),
            "verdict": latest_eval.get("verdict"),
            "dimension_scores": dim_scores,
            "red_flag_ids": get_red_flag_ids(latest_eval),
            "expectancy": latest_eval.get("expectancy"),
            "profit_factor": latest_eval.get("profit_factor"),
            "max_drawdown_pct": latest_inputs.get("max_drawdown_pct"),
            "slippage_tested": latest_inputs.get("slippage_tested"),
        },
        "recommendation": recommendation,
        "diagnosed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


# ---------------------------------------------------------------------------
# Append eval
# ---------------------------------------------------------------------------


def append_eval(
    eval_path: Path,
    history_path: Path,
    strategy_id: str,
    changes: str = "",
) -> dict[str, Any]:
    """Append a backtest eval result to an iteration history file.

    Creates the history file if it does not exist.
    """
    eval_data = json.loads(eval_path.read_text())

    if history_path.exists():
        history = json.loads(history_path.read_text())
    else:
        history = {"strategy_id": strategy_id, "iterations": []}

    # Ensure strategy_id matches — refuse to mix histories
    existing_id = history.get("strategy_id")
    if existing_id != strategy_id:
        raise ValueError(
            f"strategy_id mismatch: history has '{existing_id}' "
            f"but --strategy-id is '{strategy_id}'. "
            f"Use a different history file or correct the strategy_id."
        )

    next_iteration = len(history["iterations"]) + 1

    iteration_entry = {
        "iteration": next_iteration,
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "changes_from_previous": changes or f"Iteration {next_iteration}",
        "eval": eval_data,
    }

    history["iterations"].append(iteration_entry)
    history_path.write_text(json.dumps(history, indent=2, default=str))

    return history


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Detect stagnation in backtest iteration history.")

    # Detection mode
    parser.add_argument("--history", required=True, help="Path to iteration history JSON")
    parser.add_argument("--output-dir", default="reports/", help="Output directory")

    # Trigger parameters
    parser.add_argument(
        "--plateau-k",
        type=int,
        default=3,
        help="Window size for plateau detection (default: 3)",
    )
    parser.add_argument(
        "--plateau-threshold",
        type=int,
        default=3,
        help="Score range threshold for plateau (default: 3)",
    )

    # Append mode
    parser.add_argument(
        "--append-eval",
        default=None,
        help="Path to backtest eval JSON to append",
    )
    parser.add_argument(
        "--strategy-id",
        default=None,
        help="Strategy ID (required for --append-eval)",
    )
    parser.add_argument(
        "--changes",
        default="",
        help="Description of changes from previous iteration",
    )

    return parser.parse_args()


def main() -> int:
    """Entry point for CLI invocation."""
    args = parse_args()
    history_path = Path(args.history).resolve()

    # --- Append mode ---
    if args.append_eval:
        if not args.strategy_id:
            print("[ERROR] --strategy-id required when using --append-eval")
            return 1
        eval_path = Path(args.append_eval).resolve()
        if not eval_path.exists():
            print(f"[ERROR] eval file not found: {eval_path}")
            return 1
        try:
            history = append_eval(eval_path, history_path, args.strategy_id, args.changes)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"[ERROR] {exc}")
            return 1
        print(f"[OK] Appended iteration {len(history['iterations'])} to {history_path}")
        return 0

    # --- Detection mode ---
    if not history_path.exists():
        print(f"[ERROR] history file not found: {history_path}")
        return 1

    try:
        history = json.loads(history_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"[ERROR] Invalid JSON in history file: {exc}")
        return 1

    try:
        diagnosis = run_all_triggers(
            history,
            plateau_k=args.plateau_k,
            plateau_threshold=args.plateau_threshold,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    strategy_id = diagnosis["strategy_id"]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"pivot_diagnosis_{strategy_id}_{timestamp}.json"
    output_path = output_dir / filename

    output_path.write_text(json.dumps(diagnosis, indent=2, default=str))

    print(f"Recommendation: {diagnosis['recommendation']}")
    if diagnosis["triggers_fired"]:
        print(f"Triggers: {len(diagnosis['triggers_fired'])}")
        for t in diagnosis["triggers_fired"]:
            print(f"  [{t['severity'].upper()}] {t['trigger']}: {t['message']}")
    print(f"Output: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
