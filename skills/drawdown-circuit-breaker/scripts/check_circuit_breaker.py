#!/usr/bin/env python3
"""
Drawdown Circuit Breaker - account-level risk gate for new trade risk.

Reads trader-memory-core thesis YAML files, aggregates realized P&L from each
thesis status_history ledger, and emits a TRADING_ALLOWED / COOLDOWN / HALTED
decision for today's new entries.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

ET = ZoneInfo("America/New_York")
TERMINAL_STATUSES = {"CLOSED", "INVALIDATED"}
RECOMMENDATION_RANK = {"TRADING_ALLOWED": 0, "COOLDOWN": 1, "HALTED": 2}
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PRODUCER_UTC_MIDNIGHT_RE = re.compile(
    r"^(?P<day>\d{4}-\d{2}-\d{2})T00:00:00(?:\.0+)?(?:Z|\+00:00)$"
)


@dataclass(frozen=True)
class CircuitConfig:
    max_daily_loss_pct: float = 2.0
    losing_streak_n: int = 2
    cooldown_hours: float = 24.0
    weekly_drawdown_pct: float = 5.0
    monthly_drawdown_pct: float = 8.0


@dataclass(frozen=True)
class LedgerEntry:
    realized_pnl: float
    at: datetime


@dataclass(frozen=True)
class TerminalResult:
    pnl: float
    event_key: str
    event_at: datetime | None
    thesis_id: str
    ticker: str


def _parse_datetime(
    value: Any,
    *,
    default_tz: ZoneInfo | timezone = timezone.utc,
) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected non-empty datetime string")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed_date = date.fromisoformat(normalized)
        parsed = datetime.combine(parsed_date, time.min)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)
    return parsed


def _parse_event_datetime(value: Any) -> datetime:
    """Parse trader-memory-core event timestamps into ET accounting time.

    trader-memory-core widens bare dates (for example trim --date 2026-07-02)
    to 2026-07-02T00:00:00+00:00. Treat that producer artifact as the named
    ET accounting date instead of the prior ET evening.
    """
    if isinstance(value, str):
        stripped = value.strip()
        match = PRODUCER_UTC_MIDNIGHT_RE.match(stripped)
        if match:
            return datetime.combine(date.fromisoformat(match.group("day")), time.min, tzinfo=ET)
    return _parse_datetime(value).astimezone(ET)


def parse_as_of(value: str | None) -> datetime:
    if not value:
        return datetime.now(ET)
    stripped = value.strip()
    if DATE_ONLY_RE.match(stripped):
        return datetime.combine(date.fromisoformat(stripped), time.max, tzinfo=ET)
    parsed = _parse_datetime(value, default_tz=ET)
    return parsed.astimezone(ET)


def _load_config_file(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    with path.open() as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("--config must be a JSON object")
    allowed_keys = set(asdict(CircuitConfig()))
    unknown_keys = sorted(set(data) - allowed_keys)
    if unknown_keys:
        raise ValueError(f"Unknown config key(s): {', '.join(unknown_keys)}")
    return data


def build_config(args: argparse.Namespace) -> CircuitConfig:
    raw = asdict(CircuitConfig())
    raw.update(_load_config_file(args.config))
    cli_overrides = {
        "max_daily_loss_pct": args.max_daily_loss_pct,
        "losing_streak_n": args.losing_streak_n,
        "cooldown_hours": args.cooldown_hours,
        "weekly_drawdown_pct": args.weekly_drawdown_pct,
        "monthly_drawdown_pct": args.monthly_drawdown_pct,
    }
    raw.update({key: value for key, value in cli_overrides.items() if value is not None})
    config = CircuitConfig(
        max_daily_loss_pct=float(raw["max_daily_loss_pct"]),
        losing_streak_n=int(raw["losing_streak_n"]),
        cooldown_hours=float(raw["cooldown_hours"]),
        weekly_drawdown_pct=float(raw["weekly_drawdown_pct"]),
        monthly_drawdown_pct=float(raw["monthly_drawdown_pct"]),
    )
    if config.losing_streak_n < 1:
        raise ValueError("losing_streak_n must be at least 1")
    if config.cooldown_hours <= 0:
        raise ValueError("cooldown_hours must be positive")
    for name in ("max_daily_loss_pct", "weekly_drawdown_pct", "monthly_drawdown_pct"):
        if getattr(config, name) <= 0:
            raise ValueError(f"{name} must be positive")
    return config


def _load_thesis_file(path: Path) -> dict:
    with path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("thesis file must contain a YAML object")
    return data


def load_theses(state_dir: Path) -> tuple[list[dict], str, list[str]]:
    """Load thesis YAMLs, returning (valid theses, data_quality, warnings)."""
    if not state_dir.exists():
        return [], "EMPTY_STATE", []
    paths = sorted(state_dir.glob("th_*.yaml"))
    if not paths:
        return [], "EMPTY_STATE", []

    theses: list[dict] = []
    warnings: list[str] = []
    for path in paths:
        try:
            thesis = _load_thesis_file(path)
            thesis.setdefault("_source_path", str(path))
            theses.append(thesis)
        except Exception as exc:  # noqa: BLE001 - degrade partially on local state issues.
            warnings.append(f"Skipped {path}: {exc}")

    if warnings:
        return theses, "PARTIAL", warnings
    return theses, "OK", []


def _iter_ledger_entries(theses: Iterable[dict]) -> tuple[list[LedgerEntry], list[str]]:
    entries: list[LedgerEntry] = []
    warnings: list[str] = []
    for thesis in theses:
        source = thesis.get("_source_path") or thesis.get("thesis_id", "<unknown>")
        thesis_entries: list[LedgerEntry] = []
        history = thesis.get("status_history", [])
        if not isinstance(history, list):
            warnings.append(f"Skipped status_history for {source}: expected list")
            history = []
        for event in history:
            if not isinstance(event, dict) or "realized_pnl" not in event:
                continue
            try:
                realized_pnl = float(event["realized_pnl"])
                at = _parse_event_datetime(event.get("at"))
            except Exception as exc:  # noqa: BLE001 - malformed ledger entry should not block.
                warnings.append(f"Skipped realized_pnl event for {source}: {exc}")
                continue
            entry = LedgerEntry(realized_pnl=realized_pnl, at=at)
            thesis_entries.append(entry)
            entries.append(entry)

        if thesis.get("status") in TERMINAL_STATUSES:
            outcome = thesis.get("outcome") or {}
            outcome_pnl = outcome.get("pnl_dollars") if isinstance(outcome, dict) else None
            if outcome_pnl is None:
                continue
            try:
                outcome_pnl_float = float(outcome_pnl)
            except (TypeError, ValueError):
                continue

            ledger_total = round(sum(entry.realized_pnl for entry in thesis_entries), 2)
            if thesis_entries:
                if abs(ledger_total - outcome_pnl_float) >= 0.01:
                    warnings.append(
                        "Ledger/outcome P&L mismatch for "
                        f"{thesis.get('thesis_id')}: ledger={ledger_total:.2f}, "
                        f"outcome={outcome_pnl_float:.2f}; using ledger entries"
                    )
                continue

            event_at = _terminal_event_datetime(thesis)
            if event_at is None:
                warnings.append(
                    "Could not infer missing realized_pnl from outcome.pnl_dollars for "
                    f"{thesis.get('thesis_id')}: no valid terminal date"
                )
                continue
            entries.append(LedgerEntry(realized_pnl=outcome_pnl_float, at=event_at))
            warnings.append(
                "Inferred missing realized_pnl from outcome.pnl_dollars for "
                f"{thesis.get('thesis_id')}: {outcome_pnl_float:.2f}"
            )
    return entries, warnings


def _terminal_event_datetime(thesis: dict) -> datetime | None:
    exit_data = thesis.get("exit") or {}
    exit_date = exit_data.get("actual_date") if isinstance(exit_data, dict) else None
    if exit_date:
        try:
            return _parse_event_datetime(exit_date)
        except ValueError:
            return None
    history = thesis.get("status_history", [])
    if not isinstance(history, list):
        return None
    for event in reversed(history):
        if isinstance(event, dict) and event.get("status") in TERMINAL_STATUSES and event.get("at"):
            try:
                return _parse_event_datetime(event["at"])
            except ValueError:
                return None
    return None


def collect_terminal_results(theses: Iterable[dict]) -> tuple[list[TerminalResult], list[str]]:
    results: list[TerminalResult] = []
    warnings: list[str] = []
    for thesis in theses:
        if thesis.get("status") not in TERMINAL_STATUSES:
            continue
        outcome = thesis.get("outcome", {})
        if not isinstance(outcome, dict) or outcome.get("pnl_dollars") is None:
            warnings.append(
                f"Skipped terminal thesis with missing pnl_dollars: {thesis.get('thesis_id')}"
            )
            continue
        event_at = _terminal_event_datetime(thesis)
        if event_at is None:
            warnings.append(
                f"Skipped terminal thesis without valid exit date: {thesis.get('thesis_id')}"
            )
            continue
        try:
            pnl = float(outcome["pnl_dollars"])
        except (TypeError, ValueError):
            warnings.append(f"Skipped terminal thesis with invalid pnl: {thesis.get('thesis_id')}")
            continue
        results.append(
            TerminalResult(
                pnl=pnl,
                event_key=event_at.date().isoformat(),
                event_at=event_at,
                thesis_id=str(thesis.get("thesis_id", "")),
                ticker=str(thesis.get("ticker", "")),
            )
        )
    results.sort(key=lambda item: (item.event_at, item.ticker))
    return results, warnings


def _sum_realized_between(
    entries: Iterable[LedgerEntry],
    start_date: date,
    end_date: date,
    as_of: datetime,
) -> float:
    as_of_et = as_of.astimezone(ET)
    return round(
        sum(
            entry.realized_pnl
            for entry in entries
            if entry.at <= as_of_et and start_date <= entry.at.date() <= end_date
        ),
        2,
    )


def _next_weekday(day: date) -> date:
    candidate = day + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def _next_monday(day: date) -> date:
    days_ahead = 7 - day.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return day + timedelta(days=days_ahead)


def _first_next_month(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _start_of_day_et(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=ET)


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _consecutive_losses(results: list[TerminalResult]) -> tuple[int, datetime | None]:
    count = 0
    last_loss_exit_at: datetime | None = None
    for result in reversed(results):
        if result.pnl >= 0:
            break
        count += 1
        if last_loss_exit_at is None:
            last_loss_exit_at = result.event_at
    return count, last_loss_exit_at


def evaluate_circuit_breaker(
    theses: list[dict],
    account_size: float,
    as_of: datetime,
    config: CircuitConfig,
    initial_quality: str = "OK",
    initial_warnings: list[str] | None = None,
) -> dict:
    warnings = list(initial_warnings or [])
    ledger_entries, ledger_warnings = _iter_ledger_entries(theses)
    terminal_results, terminal_warnings = collect_terminal_results(theses)
    warnings.extend(ledger_warnings)
    warnings.extend(terminal_warnings)

    quality = initial_quality
    if warnings and quality == "OK":
        quality = "PARTIAL"

    as_of_et = as_of.astimezone(ET)
    as_of_date = as_of_et.date()
    week_start = as_of_date - timedelta(days=as_of_date.weekday())
    month_start = as_of_date.replace(day=1)

    terminal_results = [
        result
        for result in terminal_results
        if result.event_at is not None and result.event_at <= as_of_et
    ]

    realized_today = _sum_realized_between(ledger_entries, as_of_date, as_of_date, as_of_et)
    realized_wtd = _sum_realized_between(ledger_entries, week_start, as_of_date, as_of_et)
    realized_mtd = _sum_realized_between(ledger_entries, month_start, as_of_date, as_of_et)
    consecutive_losses, last_loss_exit_at = _consecutive_losses(terminal_results)

    triggered_rules: list[dict] = []

    daily_threshold = account_size * config.max_daily_loss_pct / 100
    if realized_today <= -daily_threshold:
        active_until = _start_of_day_et(_next_weekday(as_of_date))
        triggered_rules.append(
            {
                "rule": "max_daily_loss",
                "threshold": round(daily_threshold, 2),
                "observed": realized_today,
                "active_until": active_until.isoformat(),
                "severity": "HALTED",
                "detail": (
                    f"Realized P&L today is {realized_today:.2f}, breaching the "
                    f"{config.max_daily_loss_pct:.2f}% daily loss limit."
                ),
            }
        )

    if consecutive_losses >= config.losing_streak_n and last_loss_exit_at is not None:
        active_until = last_loss_exit_at + timedelta(hours=config.cooldown_hours)
        if as_of_et < active_until:
            triggered_rules.append(
                {
                    "rule": "losing_streak_cooldown",
                    "threshold": config.losing_streak_n,
                    "observed": consecutive_losses,
                    "active_until": active_until.isoformat(),
                    "severity": "COOLDOWN",
                    "detail": (
                        f"{consecutive_losses} consecutive losing closes; last loss exit "
                        f"{last_loss_exit_at.isoformat()}."
                    ),
                }
            )

    weekly_threshold = account_size * config.weekly_drawdown_pct / 100
    if realized_wtd <= -weekly_threshold:
        active_until = _start_of_day_et(_next_monday(as_of_date))
        triggered_rules.append(
            {
                "rule": "weekly_drawdown_halt",
                "threshold": round(weekly_threshold, 2),
                "observed": realized_wtd,
                "active_until": active_until.isoformat(),
                "severity": "HALTED",
                "detail": (
                    f"Week-to-date realized P&L is {realized_wtd:.2f}, breaching the "
                    f"{config.weekly_drawdown_pct:.2f}% weekly loss limit."
                ),
            }
        )

    monthly_threshold = account_size * config.monthly_drawdown_pct / 100
    if realized_mtd <= -monthly_threshold:
        active_until = _start_of_day_et(_first_next_month(as_of_date))
        triggered_rules.append(
            {
                "rule": "monthly_drawdown_halt",
                "threshold": round(monthly_threshold, 2),
                "observed": realized_mtd,
                "active_until": active_until.isoformat(),
                "severity": "HALTED",
                "detail": (
                    f"Month-to-date realized P&L is {realized_mtd:.2f}, breaching the "
                    f"{config.monthly_drawdown_pct:.2f}% monthly loss limit."
                ),
            }
        )

    recommendation = "TRADING_ALLOWED"
    for rule in triggered_rules:
        severity = rule.pop("severity")
        if RECOMMENDATION_RANK[severity] > RECOMMENDATION_RANK[recommendation]:
            recommendation = severity

    if recommendation == "TRADING_ALLOWED":
        rationale = "No account-level circuit breaker rules are active; new trade risk may proceed."
    elif recommendation == "COOLDOWN":
        rationale = "Recent losing closes triggered a cooldown. Avoid new entries until the cooldown expires."
    else:
        rationale = "Realized losses breached one or more drawdown limits. Halt new entries and focus on review."

    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of_date.isoformat(),
        "recommendation": recommendation,
        "triggered_rules": triggered_rules,
        "metrics": {
            "realized_pnl_today": realized_today,
            "realized_pnl_wtd": realized_wtd,
            "realized_pnl_mtd": realized_mtd,
            "consecutive_losses": consecutive_losses,
            "last_loss_exit_at": _iso_or_none(last_loss_exit_at),
            "theses_scanned": len(theses),
        },
        "account_size": account_size,
        "config": asdict(config),
        "data_quality": quality,
        "warnings": warnings,
        "rationale": rationale,
    }


def generate_markdown_report(result: dict) -> str:
    metrics = result["metrics"]
    lines = [
        "# Drawdown Circuit Breaker Decision",
        f"**As of:** {result['as_of_date']}",
        f"**Recommendation:** {result['recommendation']}",
        f"**Data quality:** {result['data_quality']}",
        "",
        "## Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Realized P&L today | {metrics['realized_pnl_today']:.2f} |",
        f"| Realized P&L WTD | {metrics['realized_pnl_wtd']:.2f} |",
        f"| Realized P&L MTD | {metrics['realized_pnl_mtd']:.2f} |",
        f"| Consecutive losses | {metrics['consecutive_losses']} |",
        f"| Last loss exit | {metrics['last_loss_exit_at'] or 'None'} |",
        f"| Theses scanned | {metrics['theses_scanned']} |",
        "",
        "## Rationale",
        "",
        result["rationale"],
        "",
    ]

    if result["triggered_rules"]:
        lines.extend(["## Triggered Rules", ""])
        for rule in result["triggered_rules"]:
            lines.append(
                "- {rule}: observed {observed}, threshold {threshold}, active until {until}. {detail}".format(
                    rule=rule["rule"],
                    observed=rule["observed"],
                    threshold=rule["threshold"],
                    until=rule["active_until"],
                    detail=rule["detail"],
                )
            )
        lines.append("")

    if result["warnings"]:
        lines.extend(["## Data Warnings", ""])
        lines.extend(f"- {warning}" for warning in result["warnings"])
        lines.append("")

    return "\n".join(lines)


def write_reports(result: dict, output_dir: Path, json_only: bool) -> tuple[Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = _parse_datetime(result["generated_at"]).astimezone(timezone.utc)
    timestamp = generated_at.strftime("%Y-%m-%d_%H%M%S")
    json_path = output_dir / f"circuit_breaker_decision_{timestamp}.json"
    json_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    md_path = None
    if not json_only:
        md_path = output_dir / f"circuit_breaker_decision_{timestamp}.md"
        md_path.write_text(generate_markdown_report(result), encoding="utf-8")
    return json_path, md_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate account-level drawdown circuit breaker rules"
    )
    parser.add_argument("--state-dir", type=Path, default=Path("state/theses"))
    parser.add_argument("--account-size", type=float, required=True)
    parser.add_argument(
        "--as-of", help="Evaluation date/time; date-only values cover the full ET day"
    )
    parser.add_argument("--config", type=Path, help="JSON config overriding circuit thresholds")
    parser.add_argument("--max-daily-loss-pct", type=float)
    parser.add_argument("--losing-streak-n", type=int)
    parser.add_argument("--cooldown-hours", type=float)
    parser.add_argument("--weekly-drawdown-pct", type=float)
    parser.add_argument("--monthly-drawdown-pct", type=float)
    parser.add_argument("--output-dir", type=Path, default=Path("reports"))
    parser.add_argument("--json-only", action="store_true", help="Write only JSON artifact")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.account_size <= 0:
        parser.error("--account-size must be positive")

    try:
        config = build_config(args)
        as_of = parse_as_of(args.as_of)
        theses, data_quality, warnings = load_theses(args.state_dir)
        result = evaluate_circuit_breaker(
            theses,
            args.account_size,
            as_of,
            config,
            initial_quality=data_quality,
            initial_warnings=warnings,
        )
        json_path, md_path = write_reports(result, args.output_dir, args.json_only)
    except Exception as exc:  # noqa: BLE001 - CLI should return a clear message.
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"JSON report: {json_path}")
    if md_path is not None:
        print(f"Markdown report: {md_path}")
    print(f"\nRecommendation: {result['recommendation']}")
    print(f"Data quality: {result['data_quality']}")
    print(result["rationale"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
