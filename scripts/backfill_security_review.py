#!/usr/bin/env python3
"""Collect security_review verification evidence for production skills (issue #496).

For the ``security_review`` axis of ``skills-index.yaml``, this collector:

1. enumerates production skills that read an API key, using the same
   ``scripts/**/*.py`` (excluding ``tests``) rule as issue #588, and reconciles
   that set against the SSoT ``integrations[]`` declarations;
2. runs deterministic mechanical checks per skill (hard-coded credential
   literal, shell invocation, network timeout, dependency manifest) and records
   findings;
3. applies a fail-closed confirmation gate: ``--reviewer-confirmed <id>`` starts
   empty, and only clean, explicitly confirmed skills are proposed ``passed``;
4. writes a JSON report. The collector never edits YAML; the reviewer applies
   ``skills-index.yaml`` + ``production-verification-baseline.yaml`` edits
   separately.

Usage::

    python3 scripts/backfill_security_review.py                      # enumerate + checks
    python3 scripts/backfill_security_review.py --skill position-sizer
    python3 scripts/backfill_security_review.py --reviewer-confirmed vcp-screener
    python3 scripts/backfill_security_review.py --review-by "Takuei Saotome (2026-11-15, 13079ab4)"
    python3 scripts/backfill_security_review.py --output-dir reports/
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402

INDEX_PATH = ROOT / "skills-index.yaml"

# Credential identifiers a skill's scripts may reference to make an API call.
CREDENTIAL_PATTERN = re.compile(
    r"FMP_API_KEY|FINVIZ_API_KEY|ALPACA_API_KEY|ALPACA_SECRET_KEY|--api-key|X-API-Key"
)

# Skills whose scripts mention a credential pattern only because they scan other
# skills (metadata cross-checks), not because they read a key themselves.
SCANNER_ONLY = {
    "dual-axis-skill-reviewer",
    "skill-integration-tester",
}

_HARDCODED_ASSIGN = re.compile(
    r"\b(?:api[-_]?key|secret|token|password|passwd)\b\s*[:=]\s*[\"']([^\"']{4,})[\"']",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(r"your[-_]?key|YOUR[-_]?KEY|xxx|example|replace|\$|\.\.\.|enter here")
_SHELL_RE = re.compile(r"shell\s*=\s*True|os\.system\s*\(|popen\s*\([^)]*shell", re.IGNORECASE)
_TIMEOUT_RE = re.compile(r"timeout\s*=")
_KEY_VAR = re.compile(r"FMP_API_KEY|FINVIZ_API_KEY|ALPACA_API_KEY|ALPACA_SECRET_KEY")
_WRITE_RE = re.compile(r"\b(print|logging\.|log\.|\.write\(|stderr|raise )", re.IGNORECASE)


def load_index(path: Path = INDEX_PATH) -> dict:
    with path.open(encoding="utf-8") as handle:
        index = yaml.safe_load(handle)
    return index


def production_skills(index: dict) -> list[dict]:
    return [s for s in (index.get("skills") or []) if s.get("status") == "production"]


def executable_scripts(skill_dir: Path) -> list[Path]:
    scripts_dir = skill_dir / "scripts"
    if not scripts_dir.is_dir():
        return []
    return [
        p
        for p in sorted(scripts_dir.rglob("*.py"))
        if p.is_file()
        and p.name != "__init__.py"
        and "tests" not in p.relative_to(scripts_dir).parts
    ]


def _script_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def reader_ids(index: dict, root: Path = ROOT) -> set[str]:
    """Production skills whose non-test scripts reference a credential pattern."""
    found: set[str] = set()
    for skill in production_skills(index):
        for script in executable_scripts(root / "skills" / str(skill["id"])):
            if CREDENTIAL_PATTERN.search(_script_text(script)):
                found.add(str(skill["id"]))
                break
    return found


def declared_ids(index: dict) -> set[str]:
    """Production skills whose integrations[] declare a paid API key source.

    Only the integration ``id`` is authoritative (``fmp`` / ``finviz`` /
    ``alpaca``). Free-text ``note`` carry-overs such as "Alpaca order templates"
    do not declare a key source.
    """
    found: set[str] = set()
    for skill in production_skills(index):
        for integ in skill.get("integrations") or []:
            if str(integ.get("id", "")).lower() in {"fmp", "finviz", "alpaca"}:
                found.add(str(skill["id"]))
                break
    return found


def reconcile(index: dict, root: Path = ROOT) -> dict:
    readers = reader_ids(index, root)
    declared = declared_ids(index)
    target = sorted((readers | declared) - SCANNER_ONLY)
    return {
        "readers": sorted(readers),
        "declared": sorted(declared),
        "target_skills": target,
        "scanner_only_excluded": sorted(readers & SCANNER_ONLY),
        "declared_but_no_script_ref": sorted(declared - readers),
        "script_ref_but_not_declared": sorted(readers - declared),
    }


def _hardcoded_findings(scripts: list[Path]) -> list[str]:
    finds: list[str] = []
    for script in scripts:
        text = _script_text(script)
        for match in _HARDCODED_ASSIGN.finditer(text):
            value = match.group(1)
            if not _PLACEHOLDER.search(value):
                line = text[: match.start()].count("\n") + 1
                finds.append(f"{script.name}:{line} assigns a non-placeholder {value!r}")
    return finds


def _shell_findings(scripts: list[Path]) -> list[str]:
    finds: list[str] = []
    for script in scripts:
        text = _script_text(script)
        for match in _SHELL_RE.finditer(text):
            line = text[: match.start()].count("\n") + 1
            finds.append(f"{script.name}:{line} {match.group(0)}")
    return finds


def _key_leak_findings(scripts: list[Path]) -> list[str]:
    """Advisory only: a write/error/log line that also names a credential variable.

    This is a signal for manual review, not an automatic fail: usage/help text that
    merely names a credential variable (without a value) is a common benign hit.
    """
    finds: list[str] = []
    for script in scripts:
        text = _script_text(script)
        for match in _WRITE_RE.finditer(text):
            line_start = text.rfind("\n", 0, match.start()) + 1
            line = text[line_start : text.find("\n", match.start())]
            if _KEY_VAR.search(line):
                finds.append(f"{script.name} names a credential on a write/log line (review)")
    return finds


def mechanical_checks(skill_id: str, root: Path = ROOT) -> dict:
    scripts = executable_scripts(root / "skills" / skill_id)
    hardcoded = _hardcoded_findings(scripts)
    shell = _shell_findings(scripts)
    leak_signal = _key_leak_findings(scripts)
    timeout_present = any(_TIMEOUT_RE.search(_script_text(s)) for s in scripts)
    manifest = (root / "skills" / skill_id / "requirements.txt").is_file()
    findings: list[str] = []
    findings.extend(hardcoded)
    findings.extend(shell)
    return {
        "skills": [str(p) for p in scripts],
        "hardcoded_findings": hardcoded,
        "shell_findings": shell,
        "key_leak_signal": leak_signal,
        "timeout_present": timeout_present,
        "requirements_manifest_present": manifest,
        "findings": findings,
        "clean": not bool(findings),
    }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skill", action="append", help="restrict to one skill id (repeatable)")
    parser.add_argument(
        "--reviewer-confirmed",
        action="append",
        default=[],
        help="explicitly reviewed skill ids eligible for `passed` (repeatable)",
    )
    parser.add_argument(
        "--review-by",
        default="",
        help="reviewer name, assessment commit and date, e.g. 'name (YYYY-MM-DD, <40-hex>)'",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args(argv)

    index = load_index()
    recon = reconcile(index)
    target = recon["target_skills"]
    only = set(args.skill or [])
    confirmed = set(args.reviewer_confirmed)

    results: list[dict] = []
    for skill_id in target:
        if only and skill_id not in only:
            continue
        checks = mechanical_checks(skill_id)
        gap_reasons: list[str] = []
        if checks["findings"]:
            gap_reasons = list(checks["findings"])
        if skill_id not in confirmed:
            gap_reasons.append("not reviewer-confirmed")
        proposed = "passed" if not gap_reasons else "gap"
        results.append(
            {
                "skill_id": skill_id,
                "proposed_value": proposed,
                "mechanical": checks,
                "gap_reasons": gap_reasons,
            }
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "assessment_date": date.today().isoformat(),
        "review_by": args.review_by,
        "command": "python3 scripts/backfill_security_review.py "
        + " ".join(shlex.quote(a) for a in argv),
        "issue": "https://github.com/tradermonty/claude-trading-skills/issues/496",
        "note": (
            "proposals are advisory and fail-closed: `passed` requires mechanical-clean AND an "
            "explicit --reviewer-confirmed entry. key_leak_signal is advisory only."
        ),
        "reconciliation": recon,
        "results": results,
    }
    target_path = args.output_dir / "security_review_evidence.json"
    target_path.write_text(json.dumps(report, indent=2, sort_keys=False), encoding="utf-8")

    print(json.dumps({"report": str(target_path), "target_skills": len(target)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
