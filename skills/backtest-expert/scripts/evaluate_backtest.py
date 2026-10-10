#!/usr/bin/env python3
"""Evaluate backtest quality using a 5-dimension scoring framework.

Dimensions (each 20 points, total 100):
  1. Sample Size   — total trades
  2. Expectancy    — win rate * avg win vs loss rate * avg loss
  3. Risk Mgmt     — max drawdown and profit factor
  4. Robustness    — years tested and parameter count
  5. Exec Realism  — slippage/friction tested flag

Based on methodology from skills/backtest-expert/references/methodology.md
and red-flag checklist from skills/backtest-expert/references/failed_tests.md.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Scoring functions (each returns 0-20)
# ---------------------------------------------------------------------------


def score_sample_size(total_trades: int) -> int:
    """Score based on number of trades.

    <30  -> 0
    30   -> 8
    100  -> 15
    200+ -> 20
    """
    if total_trades < 30:
        return 0
    if total_trades < 100:
        # Linear interpolation 8..14 for 30..99
        return 8 + int((total_trades - 30) / 70 * 7)
    if total_trades < 200:
        return 15 + int((total_trades - 100) / 100 * 5)
    return 20


def calc_profit_factor(win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> float:
    """Calculate profit factor: (win_rate * avg_win) / (loss_rate * avg_loss).

    Returns infinity for positive gross profit with no losses, or zero for 0/0.
    """
    wr = win_rate / 100.0
    profit_component = wr * avg_win_pct
    loss_component = (1 - wr) * avg_loss_pct
    if loss_component == 0:
        return float("inf") if profit_component > 0 else 0.0
    return profit_component / loss_component


def calc_expectancy(win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> float:
    """Calculate expectancy per trade in percent.

    E = win_rate * avg_win - loss_rate * avg_loss
    """
    wr = win_rate / 100.0
    return wr * avg_win_pct - (1 - wr) * avg_loss_pct


def score_expectancy(win_rate: float, avg_win_pct: float, avg_loss_pct: float) -> int:
    """Score based on expectancy value.

    <=0       -> 0
    0..0.5    -> 5..10  (linear)
    0.5..1.5  -> 10..18 (linear)
    >=1.5     -> 20
    """
    exp = calc_expectancy(win_rate, avg_win_pct, avg_loss_pct)
    if exp <= 0:
        return 0
    if exp < 0.5:
        return 5 + int(exp / 0.5 * 5)
    if exp < 1.5:
        return 10 + int((exp - 0.5) / 1.0 * 8)
    return 20


def score_risk_management(
    max_drawdown_pct: float,
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
) -> int:
    """Score based on max drawdown and profit factor.

    Drawdown component (0-12):
      <20%  -> 12
      20-50% -> linear 12..0
      >50%  -> 0

    Profit factor component (0-8):
      <1.0  -> 0
      1.0-3.0 -> linear 0..8
      3.0+  -> 8
    """
    # Drawdown component (0-12)
    # 50%+ drawdown is catastrophic — override total to 0
    if max_drawdown_pct >= 50:
        return 0
    if max_drawdown_pct < 20:
        dd_score = 12
    else:
        dd_score = int(12 * (50 - max_drawdown_pct) / 30)

    # Profit factor component (0-8)
    # Continuous: PF 1.0→3.0 maps linearly to 0→8, capped at 8 for PF≥3.0
    pf = calc_profit_factor(win_rate, avg_win_pct, avg_loss_pct)
    if pf < 1.0:
        pf_score = 0
    elif pf >= 3.0:
        pf_score = 8
    else:
        pf_score = int((pf - 1.0) / 2.0 * 8)

    total = dd_score + pf_score
    return min(20, total)


def score_robustness(years_tested: int, num_parameters: int) -> int:
    """Score based on test duration and parameter count.

    Years component (0-15):
      <5   -> 0
      5-9  -> linear 5..14
      10+  -> 15

    Parameter component (0-5):
      <=4  -> 5
      5-6  -> 3
      7    -> 1
      8+   -> 0
    """
    # Years component (0-15)
    if years_tested < 5:
        years_score = 0
    elif years_tested >= 10:
        years_score = 15
    else:
        years_score = 5 + int((years_tested - 5) / 5 * 10)

    # Parameter component (0-5)
    if num_parameters <= 4:
        param_score = 5
    elif num_parameters <= 6:
        param_score = 3
    elif num_parameters == 7:
        param_score = 1
    else:
        param_score = 0

    return min(20, years_score + param_score)


def score_execution_realism(slippage_tested: bool) -> int:
    """Score based on whether slippage/friction was tested.

    Tested   -> 20
    Untested -> 0
    """
    return 20 if slippage_tested else 0


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


def get_verdict(total_score: int) -> str:
    """Map total score to Deploy / Refine / Abandon."""
    if total_score >= 70:
        return "Deploy"
    if total_score >= 40:
        return "Refine"
    return "Abandon"


# ---------------------------------------------------------------------------
# Red flags
# ---------------------------------------------------------------------------


def detect_red_flags(
    total_trades: int,
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    max_drawdown_pct: float,
    years_tested: int,
    num_parameters: int,
    slippage_tested: bool,
) -> list[dict]:
    """Detect red flags based on methodology checklist."""
    flags: list[dict] = []

    if total_trades < 30:
        flags.append(
            {
                "id": "small_sample",
                "severity": "high",
                "message": f"Only {total_trades} trades — minimum 30 required for statistical confidence.",
            }
        )

    if not slippage_tested:
        flags.append(
            {
                "id": "no_slippage_test",
                "severity": "high",
                "message": "Slippage/friction not tested — results may not survive real-world execution.",
            }
        )

    if max_drawdown_pct >= 50:
        flags.append(
            {
                "id": "excessive_drawdown",
                "severity": "high",
                "message": f"Max drawdown {max_drawdown_pct}% meets or exceeds the 50% hard ceiling — catastrophic risk.",
            }
        )

    if num_parameters >= 7:
        flags.append(
            {
                "id": "over_optimized",
                "severity": "medium",
                "message": f"{num_parameters} parameters suggests over-optimization / curve-fitting risk.",
            }
        )

    if years_tested < 5:
        flags.append(
            {
                "id": "short_test_period",
                "severity": "medium",
                "message": f"Only {years_tested} years tested — may miss regime changes (minimum 5 recommended).",
            }
        )

    exp = calc_expectancy(win_rate, avg_win_pct, avg_loss_pct)
    if exp < 0:
        flags.append(
            {
                "id": "negative_expectancy",
                "severity": "high",
                "message": f"Negative expectancy ({exp:.3f}%) — strategy loses money on average.",
            }
        )

    if win_rate > 90 and max_drawdown_pct < 5:
        flags.append(
            {
                "id": "too_good",
                "severity": "medium",
                "message": "Results look too good — audit for look-ahead bias or data issues.",
            }
        )

    return flags


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------


def validate_inputs(
    total_trades: int,
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    max_drawdown_pct: float,
    years_tested: int,
    num_parameters: int,
    slippage_tested: bool,
    max_acceptable_drawdown_pct: float,
) -> None:
    """Validate evaluation inputs at system boundary. Raises ValueError."""
    for name, value in (
        ("total_trades", total_trades),
        ("years_tested", years_tested),
        ("num_parameters", num_parameters),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
    for name, value in (
        ("win_rate", win_rate),
        ("avg_win_pct", avg_win_pct),
        ("avg_loss_pct", avg_loss_pct),
        ("max_drawdown_pct", max_drawdown_pct),
        ("max_acceptable_drawdown_pct", max_acceptable_drawdown_pct),
    ):
        try:
            finite = math.isfinite(value)
        except (TypeError, OverflowError):
            finite = False
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not finite:
            raise ValueError(f"{name} must be a finite number")
    if not isinstance(slippage_tested, bool):
        raise ValueError("slippage_tested must be boolean")
    if total_trades < 0:
        raise ValueError("total_trades must be >= 0")
    if not (0 <= win_rate <= 100):
        raise ValueError("win_rate must be between 0 and 100")
    if avg_win_pct < 0:
        raise ValueError("avg_win_pct must be >= 0")
    if avg_loss_pct < 0:
        raise ValueError("avg_loss_pct must be >= 0")
    if not (0 <= max_drawdown_pct <= 100):
        raise ValueError("max_drawdown_pct must be between 0 and 100")
    if not (0 <= max_acceptable_drawdown_pct <= 100):
        raise ValueError("max_acceptable_drawdown_pct must be between 0 and 100")
    if years_tested < 0:
        raise ValueError("years_tested must be >= 0")
    if num_parameters < 0:
        raise ValueError("num_parameters must be >= 0")
    win_fraction = win_rate / 100.0
    loss_fraction = 1.0 - win_fraction
    if win_rate > 0 and avg_win_pct > 0 and win_fraction * avg_win_pct == 0:
        raise ValueError("win_rate and avg_win_pct produce an unrepresentable gross profit")
    if win_rate < 100 and avg_loss_pct > 0 and loss_fraction * avg_loss_pct == 0:
        raise ValueError("avg_loss_pct produces an unrepresentable gross loss")


def evaluate(
    total_trades: int,
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    max_drawdown_pct: float,
    years_tested: int,
    num_parameters: int,
    slippage_tested: bool,
    max_acceptable_drawdown_pct: float = 50,
) -> dict:
    """Run full 5-dimension evaluation and return structured result."""
    validate_inputs(
        total_trades,
        win_rate,
        avg_win_pct,
        avg_loss_pct,
        max_drawdown_pct,
        years_tested,
        num_parameters,
        slippage_tested,
        max_acceptable_drawdown_pct,
    )
    d1 = score_sample_size(total_trades)
    d2 = score_expectancy(win_rate, avg_win_pct, avg_loss_pct)
    d3 = score_risk_management(max_drawdown_pct, win_rate, avg_win_pct, avg_loss_pct)
    d4 = score_robustness(years_tested, num_parameters)
    d5 = score_execution_realism(slippage_tested)

    total = d1 + d2 + d3 + d4 + d5
    total = max(0, min(100, total))

    expectancy = calc_expectancy(win_rate, avg_win_pct, avg_loss_pct)
    profit_factor = calc_profit_factor(win_rate, avg_win_pct, avg_loss_pct)
    gross_profit = (win_rate / 100.0) * avg_win_pct
    gross_loss = (1 - win_rate / 100.0) * avg_loss_pct
    red_flags = detect_red_flags(
        total_trades,
        win_rate,
        avg_win_pct,
        avg_loss_pct,
        max_drawdown_pct,
        years_tested,
        num_parameters,
        slippage_tested,
    )
    blocking_reasons = []
    if gross_loss > 0 and math.isinf(profit_factor):
        blocking_reasons.append("profit_factor_overflow")
    if total_trades < 30:
        blocking_reasons.append("small_sample")
    if expectancy < 0:
        blocking_reasons.append("negative_expectancy")
    elif expectancy == 0:
        blocking_reasons.append("zero_expectancy")
    if max_drawdown_pct >= 50:
        blocking_reasons.append("excessive_drawdown")
    if max_acceptable_drawdown_pct < 50 and max_drawdown_pct > max_acceptable_drawdown_pct:
        blocking_reasons.append("risk_limit_exceeded")
    if not slippage_tested:
        blocking_reasons.append("no_slippage_test")
    if years_tested < 5:
        blocking_reasons.append("short_test_period")

    if "small_sample" in blocking_reasons or "profit_factor_overflow" in blocking_reasons:
        decision = "NOT_EVALUABLE"
    elif any(
        reason in blocking_reasons
        for reason in ("negative_expectancy", "zero_expectancy", "excessive_drawdown")
    ):
        decision = "REJECT"
    elif "risk_limit_exceeded" in blocking_reasons:
        decision = "RISK_LIMIT_EXCEEDED"
    elif any(reason in blocking_reasons for reason in ("no_slippage_test", "short_test_period")):
        decision = "VALIDATION_REQUIRED"
    else:
        decision = get_verdict(total).upper()

    if decision == "REJECT":
        verdict = "Abandon"
    elif decision in ("NOT_EVALUABLE", "RISK_LIMIT_EXCEEDED", "VALIDATION_REQUIRED"):
        verdict = "Refine"
    else:
        verdict = get_verdict(total)

    if gross_loss == 0 and gross_profit > 0:
        reported_profit_factor = None
        profit_factor_status = "NO_LOSSES"
    elif gross_loss == 0 and gross_profit == 0:
        reported_profit_factor = None
        profit_factor_status = "UNDEFINED_ZERO_GROSS"
    elif math.isinf(profit_factor):
        reported_profit_factor = None
        profit_factor_status = "OVERFLOW"
    else:
        reported_profit_factor = profit_factor
        profit_factor_status = "FINITE"

    return {
        "total_score": total,
        "quality_score": total,
        "decision": decision,
        "blocking_reasons": blocking_reasons,
        "verdict": verdict,
        "dimensions": [
            {"name": "Sample Size", "score": d1, "max_score": 20},
            {"name": "Expectancy", "score": d2, "max_score": 20},
            {"name": "Risk Management", "score": d3, "max_score": 20},
            {"name": "Robustness", "score": d4, "max_score": 20},
            {"name": "Execution Realism", "score": d5, "max_score": 20},
        ],
        "red_flags": red_flags,
        "profit_factor": reported_profit_factor,
        "profit_factor_status": profit_factor_status,
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
            "max_acceptable_drawdown_pct": max_acceptable_drawdown_pct,
        },
    }


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def to_markdown(result: dict) -> str:
    """Render evaluation result as markdown report."""
    lines = [
        "# Backtest Evaluation Report",
        "",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"## Decision: {result['decision']}",
        "",
        f"**Quality Score: {result['quality_score']} / 100**",
        f"**Legacy Verdict: {result['verdict']}**",
        "",
        "## Blocking Reasons",
        "",
        *([f"- {reason}" for reason in result["blocking_reasons"]] or ["None."]),
        "",
        "## Dimension Scores",
        "",
        "| Dimension | Score | Max |",
        "|-----------|------:|----:|",
    ]
    for dim in result["dimensions"]:
        lines.append(f"| {dim['name']} | {dim['score']} | {dim['max_score']} |")

    lines.extend(
        [
            "",
            "## Key Metrics",
            "",
            (
                f"- **Profit Factor**: {result['profit_factor']:.2f}"
                if result["profit_factor_status"] == "FINITE"
                else "- **Profit Factor**: Inf (no losing trades)"
                if result["profit_factor_status"] == "NO_LOSSES"
                else "- **Profit Factor**: Undefined (zero gross wins and losses)"
                if result["profit_factor_status"] == "UNDEFINED_ZERO_GROSS"
                else "- **Profit Factor**: Overflow (nonzero gross losses; evaluation required)"
            ),
            f"- **Expectancy**: {result['expectancy']:.3f}% per trade",
        ]
    )

    if result["red_flags"]:
        lines.extend(["", "## Red Flags", ""])
        for flag in result["red_flags"]:
            icon = "🔴" if flag["severity"] == "high" else "🟡"
            lines.append(f"- {icon} **{flag['id']}**: {flag['message']}")
    else:
        lines.extend(["", "## Red Flags", "", "No red flags detected."])

    lines.extend(
        [
            "",
            "## Input Parameters",
            "",
        ]
    )
    for key, value in result["inputs"].items():
        lines.append(f"- **{key}**: {value}")

    lines.append("")
    return "\n".join(lines)


def write_outputs(result: dict, output_dir: Path) -> tuple[Path, Path]:
    """Write JSON and Markdown reports to output_dir. Returns (json_path, md_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    stem = f"backtest_eval_{timestamp}"

    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"

    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    md_path.write_text(to_markdown(result), encoding="utf-8")

    return json_path, md_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate backtest quality using a 5-dimension scoring framework."
    )
    parser.add_argument(
        "--total-trades", type=int, required=True, help="Number of trades in backtest"
    )
    parser.add_argument(
        "--win-rate", type=float, required=True, help="Win rate in percent (e.g. 58)"
    )
    parser.add_argument(
        "--avg-win-pct", type=float, required=True, help="Average winning trade in percent"
    )
    parser.add_argument(
        "--avg-loss-pct",
        type=float,
        required=True,
        help="Average losing trade in percent (positive number)",
    )
    parser.add_argument(
        "--max-drawdown-pct", type=float, required=True, help="Maximum drawdown in percent"
    )
    parser.add_argument(
        "--years-tested", type=int, required=True, help="Number of years in backtest period"
    )
    parser.add_argument(
        "--num-parameters", type=int, required=True, help="Number of tunable parameters in strategy"
    )
    parser.add_argument(
        "--slippage-tested", action="store_true", help="Whether slippage/friction was modeled"
    )
    parser.add_argument(
        "--max-acceptable-drawdown-pct",
        type=float,
        default=50,
        help="Personal maximum drawdown in percent (hard ceiling remains 50%%)",
    )
    parser.add_argument(
        "--output-dir", default="reports/", help="Output directory (default: reports/)"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        result = evaluate(
            total_trades=args.total_trades,
            win_rate=args.win_rate,
            avg_win_pct=args.avg_win_pct,
            avg_loss_pct=args.avg_loss_pct,
            max_drawdown_pct=args.max_drawdown_pct,
            years_tested=args.years_tested,
            num_parameters=args.num_parameters,
            slippage_tested=args.slippage_tested,
            max_acceptable_drawdown_pct=args.max_acceptable_drawdown_pct,
        )
    except ValueError as exc:
        print(f"NOT_EVALUABLE: {exc}", file=sys.stderr)
        return 2

    output_dir = Path(args.output_dir)
    json_path, md_path = write_outputs(result, output_dir)

    print(
        f"Quality score: {result['quality_score']}/100 — Decision: {result['decision']}"
        f" (legacy verdict: {result['verdict']})"
    )
    if result["blocking_reasons"]:
        print(f"Blocking reasons: {', '.join(result['blocking_reasons'])}")
    if result["red_flags"]:
        print(f"Red flags: {len(result['red_flags'])}")
        for flag in result["red_flags"]:
            print(f"  [{flag['severity'].upper()}] {flag['message']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
