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

    Returns float('inf') when loss component is zero.
    """
    wr = win_rate / 100.0
    loss_component = (1 - wr) * avg_loss_pct
    if loss_component == 0:
        return float("inf")
    return (wr * avg_win_pct) / loss_component


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

    if max_drawdown_pct > 50:
        flags.append(
            {
                "id": "excessive_drawdown",
                "severity": "high",
                "message": f"Max drawdown {max_drawdown_pct}% exceeds 50% threshold — catastrophic risk.",
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
) -> None:
    """Validate evaluation inputs at system boundary. Raises ValueError."""
    if total_trades < 0:
        raise ValueError("total_trades must be >= 0")
    if not (0 <= win_rate <= 100):
        raise ValueError("win_rate must be between 0 and 100")
    if avg_win_pct < 0:
        raise ValueError("avg_win_pct must be >= 0")
    if avg_loss_pct < 0:
        raise ValueError("avg_loss_pct must be >= 0")
    if max_drawdown_pct < 0:
        raise ValueError("max_drawdown_pct must be >= 0")
    if years_tested < 0:
        raise ValueError("years_tested must be >= 0")
    if num_parameters < 0:
        raise ValueError("num_parameters must be >= 0")


def evaluate(
    total_trades: int,
    win_rate: float,
    avg_win_pct: float,
    avg_loss_pct: float,
    max_drawdown_pct: float,
    years_tested: int,
    num_parameters: int,
    slippage_tested: bool,
) -> dict:
    """Run full 5-dimension evaluation and return structured result."""
    validate_inputs(total_trades, win_rate, avg_win_pct, avg_loss_pct, max_drawdown_pct, years_tested, num_parameters)
    d1 = score_sample_size(total_trades)
    d2 = score_expectancy(win_rate, avg_win_pct, avg_loss_pct)
    d3 = score_risk_management(max_drawdown_pct, win_rate, avg_win_pct, avg_loss_pct)
    d4 = score_robustness(years_tested, num_parameters)
    d5 = score_execution_realism(slippage_tested)

    total = d1 + d2 + d3 + d4 + d5
    total = max(0, min(100, total))

    return {
        "total_score": total,
        "verdict": get_verdict(total),
        "dimensions": [
            {"name": "Sample Size", "score": d1, "max_score": 20},
            {"name": "Expectancy", "score": d2, "max_score": 20},
            {"name": "Risk Management", "score": d3, "max_score": 20},
            {"name": "Robustness", "score": d4, "max_score": 20},
            {"name": "Execution Realism", "score": d5, "max_score": 20},
        ],
        "red_flags": detect_red_flags(
            total_trades,
            win_rate,
            avg_win_pct,
            avg_loss_pct,
            max_drawdown_pct,
            years_tested,
            num_parameters,
            slippage_tested,
        ),
        "profit_factor": calc_profit_factor(win_rate, avg_win_pct, avg_loss_pct),
        "expectancy": calc_expectancy(win_rate, avg_win_pct, avg_loss_pct),
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
        f"## Verdict: {result['verdict']}",
        "",
        f"**Total Score: {result['total_score']} / 100**",
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
            f"- **Profit Factor**: {result['profit_factor']:.2f}"
            if result["profit_factor"] != float("inf")
            else "- **Profit Factor**: Inf (no losing trades)",
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
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
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
    parser.add_argument("--total-trades", type=int, required=True, help="Number of trades in backtest")
    parser.add_argument("--win-rate", type=float, required=True, help="Win rate in percent (e.g. 58)")
    parser.add_argument("--avg-win-pct", type=float, required=True, help="Average winning trade in percent")
    parser.add_argument("--avg-loss-pct", type=float, required=True, help="Average losing trade in percent (positive number)")
    parser.add_argument("--max-drawdown-pct", type=float, required=True, help="Maximum drawdown in percent")
    parser.add_argument("--years-tested", type=int, required=True, help="Number of years in backtest period")
    parser.add_argument("--num-parameters", type=int, required=True, help="Number of tunable parameters in strategy")
    parser.add_argument("--slippage-tested", action="store_true", help="Whether slippage/friction was modeled")
    parser.add_argument("--output-dir", default="reports/", help="Output directory (default: reports/)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    result = evaluate(
        total_trades=args.total_trades,
        win_rate=args.win_rate,
        avg_win_pct=args.avg_win_pct,
        avg_loss_pct=args.avg_loss_pct,
        max_drawdown_pct=args.max_drawdown_pct,
        years_tested=args.years_tested,
        num_parameters=args.num_parameters,
        slippage_tested=args.slippage_tested,
    )

    output_dir = Path(args.output_dir)
    json_path, md_path = write_outputs(result, output_dir)

    print(f"Score: {result['total_score']}/100 — Verdict: {result['verdict']}")
    if result["red_flags"]:
        print(f"Red flags: {len(result['red_flags'])}")
        for flag in result["red_flags"]:
            print(f"  [{flag['severity'].upper()}] {flag['message']}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
