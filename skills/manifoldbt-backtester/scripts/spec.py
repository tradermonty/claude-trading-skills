#!/usr/bin/env python3
"""Validate and normalise a strategy spec before anything is run.

The spec is deliberately small and declarative: a strategy is a set of named
indicators plus one entry condition over them. That covers the shapes
``backtest-expert`` tells you to test first: a rule stated in one sentence,
carrying as few tunable parameters as possible. It refuses the rest instead of
half-supporting it.

Validation lives here, separate from execution, for two reasons. It runs under
the repository's test job, which has no backtest engine installed. And a spec
mistake should be reported before minutes of data loading, not after.

The parameter count matters beyond validation: ``backtest-expert`` scores
robustness partly on how many knobs a strategy has, and counting them by hand is
exactly the step a user skips or fudges. ``count_parameters`` does it from the
spec, so the number handed to the evaluator is the number the strategy actually
carries.
"""

from __future__ import annotations

from typing import Any

__all__ = ["validate_spec", "count_parameters", "SpecError", "INDICATORS", "OPERATORS", "SOURCES"]

# Indicator kinds this skill will build. Everything the engine offers is not
# here: the list is what can be expressed in a one-sentence rule, which is the
# scope the methodology skill asks for.
INDICATORS = frozenset({"sma", "ema", "rsi"})
OPERATORS = frozenset({">", "<", ">=", "<="})
SOURCES = frozenset({"open", "high", "low", "close"})


class SpecError(ValueError):
    """A spec that cannot be run, reported before any data is touched."""


def _require(cond: bool, message: str) -> None:
    if not cond:
        raise SpecError(message)


def _validate_operand(operand: Any, declared: dict[str, Any], side_name: str) -> None:
    """An operand is an indicator name, a raw price column, or a number."""
    if isinstance(operand, (int, float)) and not isinstance(operand, bool):
        return
    _require(
        isinstance(operand, str),
        f"entry.{side_name} must be an indicator name, a price column, or a number, "
        f"got {type(operand).__name__}",
    )
    _require(
        operand in declared or operand in SOURCES,
        f"entry.{side_name} references '{operand}', which is neither a declared "
        f"indicator ({', '.join(sorted(declared)) or 'none'}) nor a price "
        f"column ({', '.join(sorted(SOURCES))})",
    )


def validate_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Check a spec and return it normalised, or raise ``SpecError``.

    Defaults applied: ``size`` 1.0, ``fees_bps`` 0.0, ``slippage_bps`` 0.0,
    ``signal_delay`` 1. The delay defaults to one bar on purpose. Acting on the
    bar that produced the signal is look-ahead, and the methodology skill treats
    it as a red flag, not a setting.
    """
    _require(isinstance(spec, dict), "spec must be a mapping")
    _require(bool(spec.get("name")), "spec.name is required")

    declared = spec.get("indicators") or {}
    _require(isinstance(declared, dict), "spec.indicators must be a mapping")
    _require(bool(declared), "spec.indicators must declare at least one indicator")

    normalised: dict[str, Any] = {}
    for name, body in declared.items():
        _require(isinstance(body, dict), f"indicator '{name}' must be a mapping")
        kind = body.get("type")
        _require(
            kind in INDICATORS,
            f"indicator '{name}' has type '{kind}'; supported: {', '.join(sorted(INDICATORS))}",
        )
        period = body.get("period")
        _require(
            isinstance(period, int) and not isinstance(period, bool) and period > 0,
            f"indicator '{name}' needs a positive integer 'period'",
        )
        source = body.get("source", "close")
        _require(
            source in SOURCES,
            f"indicator '{name}' reads '{source}'; supported: {', '.join(sorted(SOURCES))}",
        )
        normalised[name] = {"type": kind, "period": period, "source": source}

    entry = spec.get("entry")
    _require(isinstance(entry, dict), "spec.entry is required and must be a mapping")
    op = entry.get("op")
    _require(op in OPERATORS, f"entry.op is '{op}'; supported: {', '.join(sorted(OPERATORS))}")
    _require("left" in entry and "right" in entry, "entry needs both 'left' and 'right'")
    _validate_operand(entry["left"], normalised, "left")
    _validate_operand(entry["right"], normalised, "right")

    size_pct = float(spec.get("size", 1.0))
    _require(0.0 < size_pct <= 1.0, f"spec.size must be in (0, 1], got {size_pct}")

    for field in ("stop_loss_pct", "take_profit_pct"):
        value = spec.get(field)
        if value is not None:
            _require(
                isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0,
                f"spec.{field} must be a positive number when present",
            )

    for field in ("fees_bps", "slippage_bps"):
        value = float(spec.get(field, 0.0))
        _require(value >= 0.0, f"spec.{field} cannot be negative")

    delay = spec.get("signal_delay", 1)
    _require(
        isinstance(delay, int) and not isinstance(delay, bool) and delay >= 0,
        "spec.signal_delay must be a non-negative integer",
    )

    return {
        "name": spec["name"],
        "indicators": normalised,
        "entry": {"left": entry["left"], "op": op, "right": entry["right"]},
        "size": size_pct,
        "stop_loss_pct": spec.get("stop_loss_pct"),
        "take_profit_pct": spec.get("take_profit_pct"),
        "fees_bps": float(spec.get("fees_bps", 0.0)),
        "slippage_bps": float(spec.get("slippage_bps", 0.0)),
        "signal_delay": delay,
    }


def count_parameters(spec: dict[str, Any]) -> int:
    """Count the strategy's tunable knobs, for the robustness dimension.

    Counted: one per indicator period, plus a numeric threshold used directly in
    the entry condition, an explicitly supplied position size, plus each bracket
    distance. Not counted: fees and slippage, which are costs the market imposes
    rather than knobs to fit, and the signal delay, which is an execution
    convention.
    """
    n = len(spec.get("indicators") or {})
    entry = spec.get("entry") or {}
    for side_name in ("left", "right"):
        v = entry.get(side_name)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            n += 1
    if "size" in spec:
        n += 1
    n += sum(1 for c in ("stop_loss_pct", "take_profit_pct") if spec.get(c) is not None)
    return n


def describe_warnings(spec: dict[str, Any]) -> list[str]:
    """Spec-level red flags worth saying before the run, not after."""
    out: list[str] = []
    if spec.get("signal_delay", 1) == 0:
        out.append(
            "signal_delay is 0: the strategy fills on the bar that produced the "
            "signal, which is look-ahead unless the fill price is genuinely "
            "knowable at signal time"
        )
    if not spec.get("fees_bps") and not spec.get("slippage_bps"):
        out.append(
            "neither fees nor slippage are set: the run is frictionless and the "
            "execution-realism dimension will score 0"
        )
    if count_parameters(spec) > 4:
        out.append(
            f"{count_parameters(spec)} tunable parameters: the robustness "
            "dimension penalises above 4, and every added knob makes an "
            "in-sample fit easier to obtain by accident"
        )
    return out
