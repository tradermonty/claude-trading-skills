#!/usr/bin/env python3
"""Translate engine output into the eight inputs ``backtest-expert`` scores.

``skills/backtest-expert/scripts/evaluate_backtest.py`` grades a backtest on
five dimensions and asks for exactly eight numbers:

    --total-trades --win-rate --avg-win-pct --avg-loss-pct
    --max-drawdown-pct --years-tested --num-parameters --slippage-tested

Its own prerequisites say "metrics are user-provided", which leaves the user to
source those eight by hand. This module produces them from a completed run, so
the two skills chain instead of stopping at each other's edge.

Three conversions are not cosmetic and are the reason this is a module rather
than a dict comprehension:

* **Drawdown sign.** The engine reports ``max_drawdown`` as a negative fraction
  (-0.38 for a 38% fall). The evaluator wants a positive percent and scores
  worse as the number grows, so passing the raw value scores a deep drawdown as
  if it were flawless.
* **Trade count.** The engine's ``total_trades`` counts *fills*, entries and
  exits alike, so it runs at roughly twice the number of round trips. The
  evaluator's sample-size dimension is about round trips; feeding it fills
  doubles the apparent sample and can turn a below-threshold strategy into a
  passing one.
* **Win rate basis.** Percentages come from the paired round trips rather than
  the engine's own ``win_rate``, so the win rate, the average winner and the
  average loser all describe the same population. Mixing sources here is how a
  win rate ends up inconsistent with the averages beside it.
"""

from __future__ import annotations

import math
import shlex
from typing import Any

__all__ = ["build_evaluation_inputs", "format_evaluate_command", "NANOS_PER_YEAR"]

# Julian year in nanoseconds: the engine timestamps in ns, and the evaluator's
# robustness dimension counts calendar years of history.
NANOS_PER_YEAR = 365.25 * 24 * 60 * 60 * 1_000_000_000


def build_evaluation_inputs(
    metrics: dict[str, Any],
    trip_summary: dict[str, Any],
    *,
    start_ns: int | None = None,
    end_ns: int | None = None,
    num_parameters: int = 0,
    slippage_tested: bool = False,
) -> dict[str, Any]:
    """Assemble the eight evaluator inputs from one completed run.

    ``metrics`` is the engine's metrics dict, ``trip_summary`` the output of
    ``round_trips.summarize_round_trips``. Returns the eight values plus a
    ``warnings`` list naming anything that will make the score meaningless.
    """
    warnings_out: list[str] = []

    scratches = int(trip_summary.get("scratches", 0))
    if scratches:
        raise ValueError(
            f"cannot hand off {scratches} scratch trade(s): backtest-expert has no "
            "scratch-rate input, so its derived expectancy would be wrong"
        )

    # Drawdown: stored negative, scored positive. Missing or non-finite risk
    # cannot be represented honestly; zero would award an almost-perfect score.
    dd = metrics.get("max_drawdown")
    if dd is None:
        raise ValueError("max_drawdown absent from engine metrics; refusing to score risk as 0%")
    try:
        dd_value = float(dd)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"max_drawdown is not numeric: {dd!r}") from exc
    if not math.isfinite(dd_value):
        raise ValueError(f"max_drawdown must be finite, got {dd!r}")
    dd_pct = abs(dd_value) * 100.0

    total = int(trip_summary.get("total_trades", 0))
    if total <= 0:
        raise ValueError(
            "no completed round trip: win rate and average returns are undefined; "
            "refusing to generate an evaluator command"
        )
    if total < 30:
        # Not an error. The evaluator scores this zero on sample size by design,
        # and saying so up front beats the user reading a 0 and blaming the run.
        warnings_out.append(
            f"only {total} round trips; the sample-size dimension scores 0 below 30"
        )

    years = 0
    if start_ns is not None and end_ns is not None and end_ns > start_ns:
        years = int((end_ns - start_ns) / NANOS_PER_YEAR)
        if years == 0:
            warnings_out.append("backtest spans under a year; the robustness dimension scores 0")

    if not slippage_tested:
        warnings_out.append(
            "no slippage or fees modelled; execution realism scores 0 and the "
            "result should not be compared against a costed backtest"
        )

    # Reported so a caller can see the engine and the pairing agree. They are two
    # independent computations over the same run, so a gap means one of them is
    # wrong and the numbers should not be published until it is explained.
    engine_win_rate = metrics.get("trade_stats", {}).get("win_rate")
    if engine_win_rate is not None and total:
        gap = abs(float(engine_win_rate) * 100.0 - trip_summary["win_rate_pct"])
        if gap > 1.0:
            warnings_out.append(
                f"win rate from pairing ({trip_summary['win_rate_pct']:.1f}%) and from "
                f"the engine ({float(engine_win_rate) * 100:.1f}%) differ by {gap:.1f} points; "
                "an open final position or a different engine convention usually explains it"
            )

    return {
        "total_trades": total,
        "win_rate": round(trip_summary.get("win_rate_pct", 0.0), 4),
        "avg_win_pct": round(trip_summary.get("avg_win_pct", 0.0), 4),
        "avg_loss_pct": round(trip_summary.get("avg_loss_pct", 0.0), 4),
        "max_drawdown_pct": round(dd_pct, 4),
        "years_tested": years,
        "num_parameters": int(num_parameters),
        "slippage_tested": bool(slippage_tested),
        "warnings": warnings_out,
    }


def format_evaluate_command(
    inputs: dict[str, Any],
    script: str = "skills/backtest-expert/scripts/evaluate_backtest.py",
) -> str:
    """Render the ready-to-run ``evaluate_backtest.py`` invocation.

    Emitted as a string rather than executed here: the two skills stay
    independent, and the user sees the numbers being handed over instead of
    having them pass behind their back.
    """
    parts = [
        "python3",
        script,
        "--total-trades",
        str(inputs["total_trades"]),
        "--win-rate",
        str(inputs["win_rate"]),
        "--avg-win-pct",
        str(inputs["avg_win_pct"]),
        "--avg-loss-pct",
        str(inputs["avg_loss_pct"]),
        "--max-drawdown-pct",
        str(inputs["max_drawdown_pct"]),
        "--years-tested",
        str(inputs["years_tested"]),
        "--num-parameters",
        str(inputs["num_parameters"]),
    ]
    if inputs["slippage_tested"]:
        parts.append("--slippage-tested")
    return " ".join(shlex.quote(p) for p in parts)
