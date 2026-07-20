#!/usr/bin/env python3
"""
Futures Position Sizer -- CLI

Shapiro pipeline step 4: converts a direction + entry + stop into a
contract count, given an account risk budget and a verified per-symbol
contract spec (multiplier, tick size, tick value). Pure calculation, fully
offline, no API keys.

Two input modes:

  Mode A (explicit): --symbol --direction --entry --stop
  Mode B (gate handoff): --gate-json <contrarian-setup-gate report> --entry
    -- direction and stop (the gate's invalidation_level) come from the
    report; --direction/--stop are rejected if given alongside --gate-json
    (the gate is authoritative when provided). --entry is ALWAYS required,
    in both modes -- the gate never emits an entry price.

Exit behavior mirrors contrarian-setup-gate's asymmetric convention:
  - An OPERATOR config mistake (bad CLI flag, geometry violation on an
    explicit --stop, an off-tick-grid bond price the operator typed,
    a stop closer than one tick, an unresolvable symbol) is a usage
    error: exit 2, no report written.
  - A problem with the gate-report FILE, or a legitimate risk-math
    outcome of zero contracts, is always fail-closed instead: exit 0,
    and a report IS written with sizing_status=NO_TRADE naming the
    reason -- the sizer never crashes on a bad or not-yet-ready gate
    file.

Never emits a size without an explicit stop. Never rounds a contract
count up. Margin is never computed (a static note only -- broker/time-
dependent, out of scope). See SKILL.md guardrails and
references/sizing-methodology.md for the full contract.

Output:
  - JSON: futures_position_size_<SYMBOL>_<as-of>.json (--format json|both)
  - Text summary printed to stdout (--format text|both, default text)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import futures_sizing as fs

SKILL_NAME = "futures-position-sizer"


# --- Hardened gate-json loader (copied-verbatim idiom from
# contrarian-setup-gate's run_contrarian_setup_gate.load_json_file; the
# iterative non-finite scan itself is `futures_sizing.contains_non_finite`,
# the same construction, rather than a second copy of the scanning loop) --


def load_json_file(path: str) -> tuple[Any | None, str | None]:
    """Read and parse a JSON file. Returns (data, None) on success, or
    (None, reason) on failure: `"unreadable"` (missing, permission-denied,
    a directory, or not valid UTF-8), `"parse_error"` (opened and decoded
    fine but isn't valid JSON, including a decoder-level RecursionError on
    extreme nesting), or `"non_finite"` (valid JSON, but a non-finite
    float exists somewhere in the parsed structure -- an ordinary-looking
    number like `1e309` that overflows to `inf` on parse, or a bare
    `Infinity`/`-Infinity`/`NaN` literal `json.loads` accepts by default).

    This function's job stops at "loads a well-formed JSON document with
    no non-finite floats anywhere" -- it does NOT know the GATE-REPORT
    schema. Wrong-shape JSON (not a dict, missing setup_status, an
    invalid direction/invalidation_level, ...) is `futures_sizing.
    normalize_gate_report`'s job, exactly mirroring how contrarian-setup-
    gate splits `load_json_file` from `gate_logic.normalize_*`.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None, "unreadable"
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None, "parse_error"
    except RecursionError:
        # json.loads itself can raise this on extreme nesting, independent
        # of our own scan below -- NOT a JSONDecodeError/ValueError
        # subclass, so it must be caught explicitly or it escapes this
        # function entirely (same empirically-confirmed decoder limit
        # contrarian-setup-gate documents: ~200,000 levels).
        return None, "parse_error"
    if fs.contains_non_finite(data):
        return None, "non_finite"
    return data, None


# --- Argparse-facing strict numeric validators -------------------------------


def _strict_float_type(max_value: float | None = None):
    def _parse(value: str) -> float:
        try:
            return fs.strict_positive_float(value, max_value=max_value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(str(exc)) from exc

    return _parse


def _strict_int_type(value: str) -> int:
    try:
        return fs.strict_nonneg_int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _as_of_type(value: str) -> str:
    """--as-of must be YYYY-MM-DD when given. Unlike contrarian-setup-gate
    (a pipeline-stage tool where reruns must be deterministic against an
    explicit reference date), this is an operator-time sizing tool -- a
    missing --as-of defaults to today (handled in parse_arguments, not
    here) rather than being required."""
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--as-of must be YYYY-MM-DD, got {value!r}") from exc
    return value


def _symbol_type(value: str) -> str:
    """--symbol must be a plain, filename-safe alphanumeric token (see
    `futures_sizing.SYMBOL_PATTERN`) -- the SAME allowlist
    `normalize_gate_report` applies to an untrusted gate-report file's own
    `symbol` field (user review round 3, P1-3c). An operator typo here is
    a usage error, exit 2, symmetric with how a gate file's invalid symbol
    becomes a fail-closed `gate_json_malformed` NO_TRADE report."""
    stripped = value.strip()
    if not fs.is_valid_symbol(stripped):
        raise argparse.ArgumentTypeError(
            f"--symbol must be 1-12 plain alphanumeric characters, got {value!r}"
        )
    return stripped.upper()


# Sane upper bounds for numeric flags whose PRODUCT feeds risk math (never
# individually implausible, but an extreme value on one of these combined
# with another can overflow float64 before the defense-in-depth isfinite()
# guards in futures_sizing.size_futures_position ever run -- capping here
# means the failure is an ordinary argparse usage error, exit 2, with a
# clear message, rather than a silent OverflowError/ValueError crash deeper
# in the pipeline). Each bound is generously above any plausible real value:
RISK_PCT_MAX = 10.0
ACCOUNT_SIZE_MAX = 1e12  # $1 trillion -- no real trading account approaches this
MULTIPLIER_MAX = 1e9  # largest core-table multiplier (J6) is 1.25e7
TICK_SIZE_MAX = 1e6  # largest core-table tick_size (YM) is 1.0
FX_RATE_MAX = 1e6  # no real currency pair trades at anywhere near this rate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Size a futures position from a direction/entry/stop and an "
        "account risk budget -- explicit flags, or a contrarian-setup-gate "
        "READY_FOR_PLAN report handoff.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--symbol", type=_symbol_type, help="Futures ticker, e.g. ES (required in explicit mode)"
    )
    parser.add_argument("--direction", choices=["LONG", "SHORT"], help="Explicit mode only")
    parser.add_argument("--entry", type=_strict_float_type(), help="Entry price (always required)")
    parser.add_argument("--stop", type=_strict_float_type(), help="Explicit mode only")
    parser.add_argument(
        "--gate-json", help="contrarian-setup-gate JSON report path (mode B: gate handoff)"
    )
    parser.add_argument(
        "--account-size",
        type=_strict_float_type(max_value=ACCOUNT_SIZE_MAX),
        help="Account size in USD",
    )
    parser.add_argument(
        "--risk-pct",
        type=_strict_float_type(max_value=RISK_PCT_MAX),
        default=1.0,
        help="Percent of account risked per trade, (0, 10]. Default 1.0; warns above 2.0",
    )
    parser.add_argument(
        "--max-contracts",
        type=_strict_int_type,
        default=0,
        help="Hard cap on contract count. 0 = no cap (default)",
    )
    parser.add_argument(
        "--fx-rate",
        type=_strict_float_type(max_value=FX_RATE_MAX),
        default=None,
        help="Contract-currency-to-USD rate. REQUIRED if the contract's currency != USD",
    )
    parser.add_argument(
        "--multiplier", type=_strict_float_type(max_value=MULTIPLIER_MAX), default=None
    )
    parser.add_argument(
        "--tick-size", type=_strict_float_type(max_value=TICK_SIZE_MAX), default=None
    )
    parser.add_argument("--contract-currency", default=None)
    parser.add_argument(
        "--as-of",
        type=_as_of_type,
        default=None,
        help="Reference date YYYY-MM-DD for the report filename/run_context. Default: today",
    )
    parser.add_argument("--output-dir", default="reports/")
    parser.add_argument("--format", choices=["text", "json", "both"], default="text")
    parser.add_argument(
        "--list-specs", action="store_true", help="Print the verified contract-spec table and exit"
    )
    return parser


def parse_arguments() -> tuple[argparse.Namespace, argparse.ArgumentParser]:
    parser = build_parser()
    args = parser.parse_args()
    return args, parser


# --- Report rendering ---------------------------------------------------------


def generate_json_report(result: dict[str, Any], output_path: Path) -> None:
    # allow_nan=False is defense-in-depth: size_futures_position/
    # build_gate_failure_result should never produce a non-finite value,
    # but if one ever did, this makes that failure loud (ValueError) at
    # write time instead of silently emitting non-standard JSON.
    output_path.write_text(
        json.dumps(result, indent=2, sort_keys=False, allow_nan=False) + "\n", encoding="utf-8"
    )


def _fmt(value: Any) -> str:
    return "n/a" if value is None else str(value)


def generate_text_report(result: dict[str, Any]) -> str:
    lines = [
        "=" * 72,
        "Futures Position Sizer",
        "=" * 72,
        f"Symbol: {result.get('symbol')}    Direction: {_fmt(result.get('direction'))}",
        f"Status: {result.get('sizing_status')}"
        + (f"  (reason: {result['no_trade_reason']})" if result.get("no_trade_reason") else ""),
        "",
        f"Entry: {_fmt(result.get('entry'))}    Stop: {_fmt(result.get('stop'))}",
    ]
    if result.get("stop_distance_points") is not None:
        lines.append(
            f"Stop distance: {result['stop_distance_points']} points "
            f"({_fmt(result.get('stop_distance_ticks'))} ticks)"
        )
    spec = result.get("contract_spec")
    if spec:
        lines.append(
            f"Contract: multiplier={spec['multiplier']} tick_size={spec['tick_size']} "
            f"tick_value={spec['tick_value']} currency={spec['currency']} "
            f"source={_fmt(spec.get('source'))}"
        )
    if result.get("risk_per_contract_usd") is not None:
        lines.append(f"Risk per contract: ${result['risk_per_contract_usd']:,.2f}")
    if result.get("risk_budget_usd") is not None:
        lines.append(f"Risk budget: ${result['risk_budget_usd']:,.2f}")
    lines.append(f"Contracts: {result.get('contracts')}")
    if result.get("max_contracts_cap_applied"):
        lines.append("  (capped by --max-contracts)")
    if result.get("total_risk_usd") is not None:
        lines.append(
            f"Total risk: ${result['total_risk_usd']:,.2f} "
            f"({result.get('risk_pct_of_account')}% of account)"
        )
    if result.get("fx_rate_used") is not None:
        lines.append(f"FX rate used: {result['fx_rate_used']}")
    gate = result.get("gate")
    if gate:
        lines.append("")
        lines.append(
            f"Gate: {_fmt(gate.get('setup_status'))} (confidence: {_fmt(gate.get('gate_confidence'))}) "
            f"-- {_fmt(gate.get('report_path'))}"
        )
        if gate.get("warnings"):
            lines.append(f"  gate warnings: {', '.join(gate['warnings'])}")
    warnings = result.get("warnings") or []
    if warnings:
        lines.append("")
        lines.append("Warnings: " + ", ".join(warnings))
    lines.append("")
    lines.append(f"Margin note: {result.get('margin_note')}")
    lines.append("")
    return "\n".join(lines)


def print_spec_table() -> None:
    header = f"{'SYMBOL':<6} {'PRODUCT':<28} {'MULT':>10} {'TICK':>12} {'TICK $':>9} {'CCY':>4} {'EXCH':>6}"
    print(header)
    print("-" * len(header))
    for symbol in sorted(fs.CONTRACT_SPECS):
        row = fs.CONTRACT_SPECS[symbol]
        print(
            f"{symbol:<6} {str(row['exchange_product'])[:28]:<28} {row['multiplier']:>10} "
            f"{row['tick_size']:>12} {row['tick_value']:>9} {row['currency']:>4} "
            f"{str(row['exchange']):>6}"
        )


# --- Main ----------------------------------------------------------------------


def main() -> int:
    args, parser = parse_arguments()

    if args.list_specs:
        print_spec_table()
        return 0

    if args.entry is None:
        parser.error("--entry is required")
    if args.account_size is None:
        parser.error("--account-size is required")

    mode_b = args.gate_json is not None
    if mode_b:
        if args.direction is not None or args.stop is not None:
            parser.error(
                "--direction/--stop cannot be combined with --gate-json -- the gate "
                "report is authoritative for direction and stop when provided"
            )
    else:
        if args.symbol is None:
            parser.error("--symbol is required in explicit mode (pass --gate-json for mode B)")
        if args.direction is None or args.stop is None:
            parser.error("explicit mode requires both --direction and --stop")

    as_of = args.as_of or date.today().isoformat()
    output_dir = Path(args.output_dir)

    if mode_b:
        raw_data, load_error = load_json_file(args.gate_json)
        gate = fs.normalize_gate_report(raw_data, load_error, symbol=args.symbol)
        if not gate.usable:
            resolved_symbol = (args.symbol or gate.symbol or "UNKNOWN").strip().upper()
            result = fs.build_gate_failure_result(
                symbol=resolved_symbol,
                entry=args.entry,
                reason=gate.reason,
                as_of=as_of,
                report_path=args.gate_json,
                setup_status=gate.setup_status,
                gate_confidence=gate.gate_confidence,
                warnings=gate.warnings,
            )
            _write_and_print(result, args, output_dir, as_of)
            return 0
        symbol = gate.symbol
        direction = gate.direction
        stop = gate.invalidation_level
        stop_source = "gate"
        gate_block: dict[str, Any] | None = {
            "report_path": args.gate_json,
            "setup_status": gate.setup_status,
            "gate_confidence": gate.gate_confidence,
            "warnings": list(gate.warnings),
        }
    else:
        symbol = args.symbol.strip().upper()
        direction = args.direction
        stop = args.stop
        stop_source = "operator"
        gate_block = None

    try:
        spec = fs.resolve_spec(
            symbol,
            multiplier=args.multiplier,
            tick_size=args.tick_size,
            contract_currency=args.contract_currency,
        )
    except fs.ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.fx_rate is None:
        if fs.requires_fx_rate(spec["currency"]):
            print(
                f"Error: {symbol} is quoted in {spec['currency']}; --fx-rate is "
                "required to convert risk to USD",
                file=sys.stderr,
            )
            return 2
        fx_rate = 1.0
    else:
        fx_rate = args.fx_rate

    max_contracts = args.max_contracts if args.max_contracts else None

    try:
        result = fs.size_futures_position(
            symbol=symbol,
            direction=direction,
            entry=args.entry,
            stop=stop,
            stop_source=stop_source,
            spec=spec,
            account_size=args.account_size,
            risk_pct=args.risk_pct,
            max_contracts=max_contracts,
            fx_rate=fx_rate,
            as_of=as_of,
            gate_block=gate_block,
        )
    except fs.ConfigError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    _write_and_print(result, args, output_dir, as_of)
    return 0


def _write_and_print(
    result: dict[str, Any], args: argparse.Namespace, output_dir: Path, as_of: str
) -> None:
    symbol = result["symbol"]
    if args.format in ("json", "both"):
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / f"futures_position_size_{symbol}_{as_of}.json"
        generate_json_report(result, json_path)
        print(f"JSON report: {json_path}")
    if args.format in ("text", "both"):
        print(generate_text_report(result))
    else:
        status_line = f"Status: {result['sizing_status']}"
        if result.get("no_trade_reason"):
            status_line += f" ({result['no_trade_reason']})"
        print(status_line)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - CLI should return a clear message, not a traceback.
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
