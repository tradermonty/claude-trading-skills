#!/usr/bin/env python3
"""Deterministic trade performance coach.

Reviews closed trades / partial closes / monthly aggregates for process,
risk, execution, and possible behavior-pattern findings. This script is
advisory process-review tooling only; it does not produce trade signals or
broker instructions.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DISCLAIMER = (
    "This review is for trading-process improvement only. It is not financial "
    "advice, investment advice, therapy, mental-health diagnosis, or a trading "
    "signal. The human trader remains responsible for all decisions and risk."
)

ALLOWED_ACTIONS = ["accept_rules", "modify_rules", "defer", "journal_only"]


@dataclass(frozen=True)
class Finding:
    rule: str
    status: str
    evidence: str
    severity: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "status": self.status,
            "evidence": self.evidence,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class RiskNote:
    topic: str
    finding: str
    severity: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return {
            "topic": self.topic,
            "finding": self.finding,
            "severity": self.severity,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ExecutionFinding:
    phase: str
    finding: str
    evidence: str
    severity: str

    def to_dict(self) -> dict[str, str]:
        return {
            "phase": self.phase,
            "finding": self.finding,
            "evidence": self.evidence,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class BehaviorTag:
    tag: str
    confidence: str
    evidence: str
    reflection_question: str

    def to_dict(self) -> dict[str, str]:
        return {
            "tag": self.tag,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "reflection_question": self.reflection_question,
        }


def load_record(path: Path) -> dict[str, Any]:
    """Load JSON, or YAML if PyYAML is available."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "PyYAML is required for YAML input; use JSON or install pyyaml"
            ) from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON/YAML object")
    return data


def deep_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def collect_text(record: dict[str, Any]) -> str:
    parts: list[str] = []
    for path in [
        ("journal", "reflection"),
        ("journal", "notes"),
        ("postmortem", "notes"),
        ("postmortem", "root_cause_notes"),
        ("planned", "thesis"),
        ("summary",),
    ]:
        value = deep_get(record, *path)
        if isinstance(value, list):
            parts.extend(str(x) for x in value)
        elif value:
            parts.append(str(value))
    emotions = deep_get(record, "journal", "emotions")
    if isinstance(emotions, list):
        parts.extend(str(x) for x in emotions)
    return "\n".join(parts).lower()


def evaluate_process_adherence(record: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    thesis_recorded = deep_get(record, "planned", "thesis_recorded_before_entry")
    if thesis_recorded is False:
        findings.append(
            Finding(
                "pre_entry_thesis_record",
                "missed",
                "planned.thesis_recorded_before_entry is false",
                "warning",
            )
        )
    elif thesis_recorded is None:
        findings.append(
            Finding(
                "pre_entry_thesis_record",
                "unclear",
                "No explicit thesis_recorded_before_entry field was provided",
                "warning",
            )
        )
    else:
        findings.append(
            Finding(
                "pre_entry_thesis_record",
                "met",
                "A pre-entry thesis record is present",
                "info",
            )
        )

    setup_confirmed = deep_get(record, "planned", "setup_confirmed")
    entry_before_confirmation = boolish(
        deep_get(record, "actual", "entry_before_confirmation", default=False)
    )
    if entry_before_confirmation or setup_confirmed is False:
        findings.append(
            Finding(
                "setup_confirmation",
                "missed",
                "Entry appears to have occurred before planned setup confirmation",
                "critical",
            )
        )

    regime = str(deep_get(record, "planned", "market_regime", default="unknown")).lower()
    traded_against_regime = boolish(
        deep_get(record, "actual", "traded_against_regime", default=False)
    )
    if traded_against_regime or regime in {"restrictive", "cash_priority", "cash-priority"}:
        findings.append(
            Finding(
                "market_regime_gate",
                "missed",
                f"Trade was taken while market_regime={regime!r} or actual.traded_against_regime=true",
                "critical",
            )
        )

    stop_moved = boolish(deep_get(record, "actual", "stop_moved", default=False))
    stop_move_planned = boolish(deep_get(record, "actual", "stop_move_planned", default=False))
    if stop_moved and not stop_move_planned:
        findings.append(
            Finding(
                "stop_change_rule",
                "missed",
                "Stop was moved after entry without evidence of a pre-defined stop-change rule",
                "critical",
            )
        )

    return findings


def evaluate_risk_discipline(record: dict[str, Any]) -> list[RiskNote]:
    notes: list[RiskNote] = []
    actual_r = number(deep_get(record, "actual", "risk_r"))
    planned_r = number(deep_get(record, "planned", "risk_r"))
    max_r = number(deep_get(record, "risk_plan", "max_risk_per_trade_r"))
    reference_r = max_r if max_r is not None else planned_r
    if actual_r is not None and reference_r is not None:
        if actual_r > reference_r * 1.25:
            notes.append(
                RiskNote(
                    "position_size",
                    "Actual risk materially exceeded the planned or maximum risk.",
                    "critical",
                    f"actual.risk_r={actual_r:g}, reference_r={reference_r:g}",
                )
            )
        elif actual_r > reference_r:
            notes.append(
                RiskNote(
                    "position_size",
                    "Actual risk exceeded the plan by a small amount.",
                    "warning",
                    f"actual.risk_r={actual_r:g}, reference_r={reference_r:g}",
                )
            )
        else:
            notes.append(
                RiskNote(
                    "position_size",
                    "Actual risk was within the provided risk limit.",
                    "info",
                    f"actual.risk_r={actual_r:g}, reference_r={reference_r:g}",
                )
            )
    else:
        notes.append(
            RiskNote(
                "position_size",
                "Risk comparison is unclear because actual risk or risk plan is missing.",
                "warning",
                "Missing actual.risk_r, planned.risk_r, or risk_plan.max_risk_per_trade_r",
            )
        )

    heat = number(deep_get(record, "actual", "portfolio_heat_r"))
    max_heat = number(deep_get(record, "risk_plan", "max_portfolio_heat_r"))
    if heat is not None and max_heat is not None:
        if heat > max_heat:
            notes.append(
                RiskNote(
                    "portfolio_heat",
                    "Portfolio heat exceeded the provided maximum.",
                    "critical",
                    f"portfolio_heat_r={heat:g}, max_portfolio_heat_r={max_heat:g}",
                )
            )
        elif heat > max_heat * 0.9:
            notes.append(
                RiskNote(
                    "portfolio_heat",
                    "Portfolio heat is close to the provided maximum.",
                    "warning",
                    f"portfolio_heat_r={heat:g}, max_portfolio_heat_r={max_heat:g}",
                )
            )

    consecutive_losses = number(deep_get(record, "monthly", "consecutive_losses"))
    if consecutive_losses is not None and consecutive_losses >= 3:
        notes.append(
            RiskNote(
                "drawdown",
                "Consecutive losses are elevated; consider temporary review-only mode.",
                "critical" if consecutive_losses >= 4 else "warning",
                f"monthly.consecutive_losses={consecutive_losses:g}",
            )
        )

    return notes


def evaluate_execution_quality(record: dict[str, Any]) -> list[ExecutionFinding]:
    findings: list[ExecutionFinding] = []
    if boolish(deep_get(record, "actual", "entry_before_confirmation", default=False)):
        findings.append(
            ExecutionFinding(
                "entry",
                "Entry appears to have occurred before planned confirmation.",
                "actual.entry_before_confirmation is true",
                "critical",
            )
        )
    else:
        findings.append(
            ExecutionFinding(
                "entry",
                "No explicit early-entry issue was detected from the provided record.",
                "actual.entry_before_confirmation is false or absent",
                "info",
            )
        )

    if boolish(deep_get(record, "actual", "stop_moved", default=False)):
        severity = (
            "warning"
            if boolish(deep_get(record, "actual", "stop_move_planned", default=False))
            else "critical"
        )
        findings.append(
            ExecutionFinding(
                "stop",
                "Stop was moved after entry."
                if severity == "warning"
                else "Stop was moved without a documented pre-defined rule.",
                "actual.stop_moved is true",
                severity,
            )
        )

    if boolish(deep_get(record, "actual", "premature_exit", default=False)):
        findings.append(
            ExecutionFinding(
                "exit",
                "Exit appears to have occurred before planned invalidation or target rules.",
                "actual.premature_exit is true",
                "warning",
            )
        )

    return findings


def has_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def detect_behavioral_patterns(
    record: dict[str, Any], findings: list[Finding], notes: list[RiskNote]
) -> list[BehaviorTag]:
    text = collect_text(record)
    tags: list[BehaviorTag] = []

    def add(tag: str, confidence: str, evidence: str, question: str) -> None:
        if tag not in {t.tag for t in tags}:
            tags.append(BehaviorTag(tag, confidence, evidence, question))

    if boolish(deep_get(record, "actual", "entry_before_confirmation", default=False)) or has_any(
        text,
        [r"didn'?t want to miss", r"fomo", r"chase", r"miss the move", r"moving fast"],
    ):
        add(
            "fomo_entry",
            "medium" if "fomo" not in text else "high",
            "Entry/journal evidence suggests fear of missing a move or entry before confirmation.",
            "What evidence did you have before entry that would not have been available after waiting for confirmation?",
        )

    if has_any(text, [r"revenge", r"make it back", r"win it back", r"after.*loss"]):
        add(
            "revenge_trade",
            "medium",
            "Journal language suggests a possible attempt to recover prior losses.",
            "Would you have taken this trade if the prior trade had been a winner?",
        )

    if boolish(deep_get(record, "actual", "premature_exit", default=False)) or has_any(
        text, [r"got scared", r"took it off early", r"couldn'?t hold"]
    ):
        add(
            "premature_exit",
            "medium",
            "Exit/journal evidence suggests the trade may have been closed before planned invalidation or target rules.",
            "What rule did the exit satisfy, or was it driven by discomfort?",
        )

    if has_any(text, [r"easy money", r"can'?t lose", r"sure thing", r"increased size after win"]):
        add(
            "overconfidence_after_winner",
            "medium",
            "Journal language suggests possible confidence escalation after a winner.",
            "Did a prior win change the size or quality threshold for this trade?",
        )

    if boolish(deep_get(record, "actual", "stop_moved", default=False)) and not boolish(
        deep_get(record, "actual", "stop_move_planned", default=False)
    ):
        add(
            "stop_moved",
            "high",
            "actual.stop_moved is true and no pre-planned stop-change rule was provided.",
            "Was the new stop part of the plan before entry?",
        )

    # size_creep must require actual evidence that actual.risk_r > reference_r,
    # not just any position_size warning (e.g. missing risk data also produces a warning,
    # but that is not "size creep" — see Blocker 2 from the 2026-05-24 PR-F review).
    actual_r = number(deep_get(record, "actual", "risk_r"))
    max_r = number(deep_get(record, "risk_plan", "max_risk_per_trade_r"))
    planned_r = number(deep_get(record, "planned", "risk_r"))
    reference_r = max_r if max_r is not None else planned_r
    if actual_r is not None and reference_r is not None and actual_r > reference_r:
        add(
            "size_creep",
            "high",
            f"Actual risk exceeded the planned or maximum risk (actual.risk_r={actual_r:g} > reference_r={reference_r:g}).",
            "What would this trade have looked like at the planned risk size?",
        )
    elif any(
        n.topic == "position_size" and n.severity in {"warning", "critical"} for n in notes
    ) and (actual_r is None or reference_r is None):
        add(
            "unknown_size_discipline",
            "medium",
            "Risk discipline could not be assessed because actual.risk_r or risk_plan/planned risk reference is missing.",
            "Can the risk plan or actual risk be recorded for the next trade so size discipline is verifiable?",
        )

    if boolish(deep_get(record, "actual", "hesitated", default=False)) or has_any(
        text, [r"hesitat", r"froze", r"missed my entry"]
    ):
        add(
            "hesitation",
            "medium",
            "Journal/action evidence suggests planned execution may have been delayed or missed.",
            "What objective trigger would have removed the need for discretion?",
        )

    if len([f for f in findings if f.severity in {"warning", "critical"}]) >= 3:
        add(
            "rule_drift",
            "medium",
            "Multiple process findings suggest possible rule drift.",
            "Which single rule should be simplified and enforced next session?",
        )

    if not tags:
        tags.append(
            BehaviorTag(
                "no_pattern_detected",
                "low",
                "No behavior pattern was detected from the available evidence.",
                "Is there any additional journal context that should be added before finalizing this review?",
            )
        )

    return tags


def compute_score(findings: list[Any]) -> int:
    score = 100
    for item in findings:
        severity = getattr(item, "severity", "info")
        if severity == "critical":
            score -= 30
        elif severity == "warning":
            score -= 15
        elif severity == "info":
            score -= 0
    return max(0, min(100, score))


def determine_verdict(
    findings: list[Finding],
    notes: list[RiskNote],
    tags: list[BehaviorTag],
    record: dict[str, Any],
    execution: list[ExecutionFinding] | None = None,
) -> str:
    # Blocker 1 (2026-05-24 PR-F review): execution warnings/critical must also escalate
    # the verdict — previously a premature_exit produced an execution finding + behavior
    # tag but the verdict still came out OK because only process/risk were inspected.
    all_severities = [*findings, *notes, *(execution or [])]
    critical_count = sum(1 for x in all_severities if getattr(x, "severity", "") == "critical")
    revenge = any(t.tag == "revenge_trade" for t in tags)
    consecutive_losses = number(deep_get(record, "monthly", "consecutive_losses")) or 0
    if critical_count >= 2 or (revenge and consecutive_losses >= 2) or consecutive_losses >= 4:
        return "COOL_DOWN"
    if critical_count >= 1:
        return "RULE_VIOLATION"
    if any(getattr(x, "severity", "") == "warning" for x in all_severities):
        return "REVIEW_REQUIRED"
    return "OK"


def infer_root_cause(record: dict[str, Any], findings: list[Finding], notes: list[RiskNote]) -> str:
    provided = deep_get(record, "postmortem", "root_cause")
    if provided:
        return str(provided)
    if any(n.topic == "position_size" and n.severity in {"warning", "critical"} for n in notes):
        return "risk_sizing"
    if any(
        f.rule in {"setup_confirmation", "stop_change_rule"} and f.severity == "critical"
        for f in findings
    ):
        return "execution"
    if any(f.rule == "market_regime_gate" and f.severity == "critical" for f in findings):
        return "market_environment"
    return "unknown"


def next_session_rules(
    verdict: str, notes: list[RiskNote], tags: list[BehaviorTag]
) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []

    def add(rule: str, duration: str, trigger: str, reason: str) -> None:
        if rule not in {r["rule"] for r in rules}:
            rules.append({"rule": rule, "duration": duration, "trigger": trigger, "reason": reason})

    # Blocker 2 follow-up (2026-05-24 PR-F review): the cap-risk rule must
    # only fire when there is explicit evidence that actual risk exceeded the
    # plan (size_creep tag). The missing-risk-data case (unknown_size_discipline)
    # is "unverifiable", not "exceeded", so it gets a different rule asking the
    # trader to record planned/actual risk next time.
    if any(t.tag == "size_creep" for t in tags):
        add(
            "Cap risk at 0.5R for the next two trades unless the trader explicitly modifies the risk plan in the journal.",
            "next_two_trades",
            "size_creep tag",
            "Actual risk exceeded the stated risk plan.",
        )
    elif any(t.tag == "unknown_size_discipline" for t in tags):
        add(
            "On the next trade, record both planned risk_r and actual risk_r in the journal so risk discipline becomes verifiable.",
            "next_trade",
            "unknown_size_discipline tag",
            "Risk discipline could not be assessed because planned or actual risk was missing.",
        )
    if any(t.tag == "fomo_entry" for t in tags):
        add(
            "No new entry without a pre-entry thesis record, invalidation point, and setup-confirmation note.",
            "next_week",
            "possible FOMO entry pattern",
            "The review found evidence of entry before confirmation or fear of missing a move.",
        )
    if any(t.tag == "revenge_trade" for t in tags) or verdict == "COOL_DOWN":
        add(
            "Switch to review-only mode for the next session; do not add new risk until the rule review is journaled.",
            "next_session",
            "possible revenge/cool-down condition",
            "Repeated losses or revenge-trade evidence can escalate risk-taking.",
        )
    if any(t.tag == "stop_moved" for t in tags):
        add(
            "Any stop adjustment must be written before entry; unplanned stop changes require immediate post-trade review.",
            "next_month",
            "unplanned stop move",
            "Stop discipline protects the loss limit and keeps outcomes reviewable.",
        )
    if not rules:
        add(
            "Keep the current process rules unchanged and continue journaling every trade outcome.",
            "next_session",
            "no material process issue detected",
            "The available evidence did not show a rule violation.",
        )
    return rules


def build_review(record: dict[str, Any], source_records: list[str]) -> dict[str, Any]:
    process = evaluate_process_adherence(record)
    risk_notes = evaluate_risk_discipline(record)
    execution = evaluate_execution_quality(record)
    tags = detect_behavioral_patterns(record, process, risk_notes)
    verdict = determine_verdict(process, risk_notes, tags, record, execution=execution)
    root_cause = infer_root_cause(record, process, risk_notes)
    review_id = str(
        record.get("review_id")
        or record.get("trade_id")
        or f"review_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    )
    review_type = str(record.get("review_type") or "single_trade")
    outcome = str(
        record.get("outcome") or deep_get(record, "summary", "outcome", default="unknown")
    )

    scores = {
        "process_score": compute_score(process),
        "risk_score": compute_score(risk_notes),
        "execution_score": compute_score(execution),
        "review_quality_score": review_quality_score(record),
    }

    return {
        "schema_version": 1,
        "review_type": review_type,
        "review_id": review_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_records": source_records,
        "overall_verdict": verdict,
        "summary": {
            "outcome": outcome,
            "primary_root_cause": root_cause,
            "secondary_root_causes": infer_secondary_causes(process, risk_notes, tags),
            "confidence": infer_confidence(scores["review_quality_score"], process, risk_notes),
        },
        "scores": scores,
        "process_adherence_findings": [f.to_dict() for f in process],
        "risk_manager_notes": [n.to_dict() for n in risk_notes],
        "execution_quality_assessment": [e.to_dict() for e in execution],
        "behavioral_pattern_tags": [t.to_dict() for t in tags],
        "next_session_operating_rules": next_session_rules(verdict, risk_notes, tags),
        "coach_questions": [t.reflection_question for t in tags[:4]],
        "human_decision_gate": {
            "question": "Do you accept these temporary operating rules, modify them, defer the decision, or journal this review only?",
            "allowed_actions": ALLOWED_ACTIONS,
            "default_action": "journal_only",
        },
        "disclaimer": DISCLAIMER,
    }


def review_quality_score(record: dict[str, Any]) -> int:
    expected = [
        ("planned", "risk_r"),
        ("actual", "risk_r"),
        ("risk_plan", "max_risk_per_trade_r"),
        ("postmortem", "root_cause"),
        ("journal", "reflection"),
    ]
    present = sum(1 for path in expected if deep_get(record, *path) is not None)
    return int(40 + 60 * (present / len(expected)))


def infer_secondary_causes(
    process: list[Finding], notes: list[RiskNote], tags: list[BehaviorTag]
) -> list[str]:
    causes: list[str] = []
    if any(f.rule == "market_regime_gate" and f.severity == "critical" for f in process):
        causes.append("market_environment")
    if any(n.topic == "position_size" and n.severity in {"warning", "critical"} for n in notes):
        causes.append("risk_sizing")
    if any(t.tag in {"fomo_entry", "revenge_trade", "stop_moved"} for t in tags):
        causes.append("behavior_pattern")
    return list(dict.fromkeys(causes))


def infer_confidence(review_quality: int, process: list[Finding], notes: list[RiskNote]) -> str:
    if review_quality < 60:
        return "low"
    if review_quality >= 85 and (process or notes):
        return "high"
    return "medium"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Trade Performance Coach Report: {report['review_id']}",
        "",
        f"**Verdict:** `{report['overall_verdict']}`",
        f"**Review type:** `{report['review_type']}`",
        f"**Primary root cause:** `{report['summary']['primary_root_cause']}`",
        "",
        "## Scores",
        "",
    ]
    for key, value in report["scores"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Process Adherence", ""])
    for item in report["process_adherence_findings"]:
        lines.append(
            f"- **{item['severity'].upper()}** `{item['rule']}` — {item['status']}: {item['evidence']}"
        )
    lines.extend(["", "## Risk Manager Notes", ""])
    for item in report["risk_manager_notes"]:
        lines.append(
            f"- **{item['severity'].upper()}** `{item['topic']}` — {item['finding']} Evidence: {item['evidence']}"
        )
    lines.extend(["", "## Execution Quality", ""])
    for item in report["execution_quality_assessment"]:
        lines.append(
            f"- **{item['severity'].upper()}** `{item['phase']}` — {item['finding']} Evidence: {item['evidence']}"
        )
    lines.extend(["", "## Possible Behavioral Patterns", ""])
    for item in report["behavioral_pattern_tags"]:
        lines.append(f"- `{item['tag']}` ({item['confidence']}): {item['evidence']}")
        lines.append(f"  - Reflection: {item['reflection_question']}")
    lines.extend(["", "## Next-Session Operating Rules", ""])
    for item in report["next_session_operating_rules"]:
        lines.append(f"- **{item['duration']}**: {item['rule']}")
        lines.append(f"  - Trigger: {item['trigger']}")
        lines.append(f"  - Reason: {item['reason']}")
    lines.extend(["", "## Coach Questions", ""])
    for question in report["coach_questions"]:
        lines.append(f"- {question}")
    gate = report["human_decision_gate"]
    lines.extend(
        [
            "",
            "## Human Decision Gate",
            "",
            gate["question"],
            "",
            f"Allowed actions: {', '.join(gate['allowed_actions'])}",
            f"Default action: `{gate['default_action']}`",
            "",
            "## Disclaimer",
            "",
            report["disclaimer"],
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review trade performance records.")
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Input JSON/YAML record. Can be passed multiple times.",
    )
    parser.add_argument(
        "--output-dir",
        default="reports/trade-performance-coach",
        help="Directory for output reports.",
    )
    parser.add_argument("--json-name", default=None, help="Optional JSON output filename.")
    parser.add_argument("--markdown", action="store_true", help="Also write Markdown report.")
    parser.add_argument("--stdout", action="store_true", help="Print JSON report to stdout.")
    args = parser.parse_args(argv)

    input_paths = [Path(p) for p in args.input]
    if len(input_paths) == 1:
        record = load_record(input_paths[0])
    else:
        # Medium 1 (2026-05-24 PR-F review): multi-input mode currently wraps records
        # without aggregating process/risk/text per trade — the analysis is therefore
        # shallow. Warn loudly so users supply a pre-aggregated monthly JSON when they
        # want accurate monthly analysis. A full aggregate_monthly_inputs() implementation
        # is tracked as follow-up.
        print(
            "warning: multi-input mode wraps records without aggregating process/risk/text per trade. "
            "Pass a single pre-aggregated monthly JSON (with monthly.trades_summary, etc.) for accurate "
            "monthly analysis. See follow-up: trade-performance-coach: implement multi-input aggregate logic.",
            file=sys.stderr,
        )
        # Monthly aggregate wrapper for multiple records.
        record = {
            "review_type": "monthly_aggregate",
            "trade_id": "monthly_aggregate",
            "outcome": "mixed",
            "monthly": {"trades": [load_record(p) for p in input_paths]},
            "journal": {"reflection": "Multiple records supplied for aggregate review."},
        }
    report = build_review(record, [str(p) for p in input_paths])

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_name = args.json_name or f"trade_performance_coach_{report['review_id']}.json"
    json_path = out_dir / json_name
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown:
        md_path = out_dir / json_name.replace(".json", ".md")
        md_path.write_text(render_markdown(report), encoding="utf-8")
    if args.stdout:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json_path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
