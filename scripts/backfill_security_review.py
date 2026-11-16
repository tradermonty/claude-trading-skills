#!/usr/bin/env python3
"""Collect security_review verification evidence for production skills (issue #496).

For the ``security_review`` axis of ``skills-index.yaml``, this collector:

1. enumerates production skills that read an API key, using the same
   ``scripts/**/*.py`` (excluding ``tests``) rule as issue #588, and reconciles
   that set against the SSoT ``integrations[]`` declarations;
2. runs deterministic mechanical checks per skill (hard-coded credential
   literal, shell invocation, key-in-request combined with an unredacted
   exception print/log, network timeout, dependency manifest) and records
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
    python3 scripts/backfill_security_review.py --assessed-commit <40-hex>
    python3 scripts/backfill_security_review.py --output-dir reports/
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import shlex
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import yaml  # noqa: E402
from security_network_evidence import script_evidence  # noqa: E402

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
# A request that carries the credential value: dict key such as "apikey": ...,
# or a query-string fragment such as apikey={...} / auth=%s inside a URL string.
_KEY_IN_REQUEST = re.compile(
    r"""["'](?:apikey|api_key|auth|access_token|token)["']\s*:"""
    r"""|\b(?:apikey|api_key|auth|access_token|token)=(?:\{|%s|["'+])""",
    re.IGNORECASE,
)
# `except ... as NAME` binds the exception variable that may carry the request URL.
_EXC_BIND = re.compile(r"except\b[^\n:]*\bas\s+(\w+)\s*:")
# A call or definition of a redaction helper; a docstring that merely says "redacted" is not one.
_REDACT_RE = re.compile(r"\w*redact\w*\s*\(", re.IGNORECASE)
_LOG_EXC_RE = re.compile(r"\blogger\.exception\(|\blogging\.exception\(|traceback\.print_exc")
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


def _key_in_request_url(text: str) -> bool:
    """True when a key value can reach the URL/query string (not a header-only use)."""
    for match in _KEY_IN_REQUEST.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.start())
        line = text[line_start : line_end if line_end != -1 else len(text)]
        if "header" not in line.lower():
            return True
    return False


def _fixed_diagnostic_bindings(text: str) -> set[str]:
    """Exclude only local, literal-only diagnostics from this advisory heuristic.

    A plain ValueError/RuntimeError subclass with no executable class body and
    exclusively literal string constructors cannot inherit a requests URL. Do
    not exempt arbitrary custom exceptions, dynamic messages, or a binding also
    used by another handler. Parse failures remain fail-closed in the scanner.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    nodes = list(ast.walk(tree))
    parents = {child: parent for parent in nodes for child in ast.iter_child_nodes(parent)}

    def bound_names(node):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            return {node.name}
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            return {node.id}
        if isinstance(node, ast.arg):
            return {node.arg}
        if isinstance(node, ast.alias):
            return {node.asname or node.name.split(".")[0]}
        if isinstance(node, ast.ExceptHandler) and node.name:
            return {node.name}
        return set()

    safe_types = set()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.decorator_list or node.keywords:
            continue
        if len(node.bases) != 1 or not isinstance(node.bases[0], ast.Name):
            continue
        if node.bases[0].id not in {"ValueError", "RuntimeError"}:
            continue
        if not all(
            isinstance(item, ast.Pass)
            or (
                isinstance(item, ast.Expr)
                and isinstance(item.value, ast.Constant)
                and isinstance(item.value.value, str)
            )
            for item in node.body
        ):
            continue
        # A local class or its builtin base must not be shadowed or rebound.
        if any(node.bases[0].id in bound_names(item) for item in nodes):
            continue
        if any(item is not node and node.name in bound_names(item) for item in nodes):
            continue
        # Every reference must be a direct construction or an except type;
        # an alias/factory/export could later construct a dynamic message.
        references = [item for item in nodes if isinstance(item, ast.Name) and item.id == node.name]
        if any(
            not (
                (isinstance(parents.get(item), ast.Call) and parents[item].func is item)
                or (isinstance(parents.get(item), ast.ExceptHandler) and parents[item].type is item)
            )
            for item in references
        ):
            continue
        calls = [
            item
            for item in ast.walk(tree)
            if isinstance(item, ast.Call)
            and isinstance(item.func, ast.Name)
            and item.func.id == node.name
        ]
        if calls and all(
            len(call.args) == 1
            and not call.keywords
            and isinstance(call.args[0], ast.Constant)
            and isinstance(call.args[0].value, str)
            for call in calls
        ):
            safe_types.add(node.name)
    handlers = [
        node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler) and node.name
    ]

    def only_stringified(name):
        if any(
            not isinstance(item, ast.ExceptHandler) and name in bound_names(item) for item in nodes
        ):
            return False
        # For an exempted variable allow only formatting/str/repr reads. Any
        # alias, mutation, attribute access or opaque call is unproven.
        for item in nodes:
            if not isinstance(item, ast.Name) or item.id != name:
                continue
            parent = parents.get(item)
            if isinstance(parent, ast.FormattedValue) and parent.value is item:
                continue
            if (
                isinstance(parent, ast.Call)
                and isinstance(parent.func, ast.Name)
                and parent.func.id in {"str", "repr"}
                and parent.args == [item]
                and not parent.keywords
            ):
                continue
            return False
        return True

    return {
        name
        for name in {handler.name for handler in handlers}
        if all(
            isinstance(handler.type, ast.Name) and handler.type.id in safe_types
            for handler in handlers
            if handler.name == name
        )
        and only_stringified(name)
    }


def _exception_key_leak_findings(scripts: list[Path]) -> list[str]:
    """Flag scripts that put a key into a request AND print/log the exception object.

    ``requests`` exceptions embed the full request URL, query string included, in
    ``str(e)``. A script that sends the key as a query parameter (or in an f-string
    URL) and then prints ``{e}`` / ``str(e)`` / ``logger.exception(...)`` can
    therefore write the credential value to stderr or logs. Scripts that reference
    a redaction helper (``_redact`` / ``_redact_key``) are treated as handled; this
    is a file-level heuristic, not a data-flow proof.
    """
    finds: list[str] = []
    for script in scripts:
        text = _script_text(script)
        if _REDACT_RE.search(text) or not _key_in_request_url(text):
            continue
        reason = None
        for name in sorted(set(_EXC_BIND.findall(text)) - _fixed_diagnostic_bindings(text)):
            ref = re.compile(
                r"\{\s*" + re.escape(name) + r"\b[^}]*\}"
                r"|\b(?:str|repr)\(\s*" + re.escape(name) + r"\s*\)"
                r"|%s.*,\s*" + re.escape(name) + r"\s*\)"
            )
            if ref.search(text):
                reason = f"prints exception '{name}'"
                break
        if reason is None and _LOG_EXC_RE.search(text):
            reason = "logs a traceback"
        if reason:
            finds.append(
                f"{script.name} sends a key in a request and {reason} without redaction "
                "(exception text can contain the request URL with the key)"
            )
    return finds


def mechanical_checks(skill_id: str, root: Path = ROOT) -> dict:
    scripts = executable_scripts(root / "skills" / skill_id)
    hardcoded = _hardcoded_findings(scripts)
    shell = _shell_findings(scripts)
    exc_leak = _exception_key_leak_findings(scripts)
    leak_signal = _key_leak_findings(scripts)
    timeout_present = any(_TIMEOUT_RE.search(_script_text(s)) for s in scripts)
    manifest = (root / "skills" / skill_id / "requirements.txt").is_file()
    network = [
        script_evidence(script, script.relative_to(root / "skills" / skill_id).as_posix())
        for script in scripts
    ]
    network_findings = [finding for evidence in network for finding in evidence["findings"]]
    calls = [call for evidence in network for call in evidence["calls"]]
    applicability = "unproven" if network_findings else "network" if calls else "not_applicable"
    findings: list[str] = []
    if scripts and not manifest:
        findings.append("executable Python skill is missing requirements.txt")
    findings.extend(network_findings)
    findings.extend(hardcoded)
    findings.extend(shell)
    findings.extend(exc_leak)
    return {
        "skills": [str(p) for p in scripts],
        "hardcoded_findings": hardcoded,
        "shell_findings": shell,
        "exception_key_leak_findings": exc_leak,
        "key_leak_signal": leak_signal,
        "timeout_present": timeout_present,
        "network_applicability": applicability,
        "network_calls": calls,
        "network_timeout_findings": network_findings,
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
        "--assessed-commit",
        default="",
        help="40-hex commit the scan was run against (recorded in the report)",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports")
    args = parser.parse_args(argv)

    index = load_index()
    recon = reconcile(index)
    target = recon["target_skills"]
    only = set(args.skill or [])
    confirmed = set(args.reviewer_confirmed)

    eligible = set(target)
    for option, supplied in (("--skill", only), ("--reviewer-confirmed", confirmed)):
        invalid = sorted(supplied - eligible)
        if invalid:
            print(
                f"Error: {option} IDs are unknown or ineligible: {', '.join(invalid)}. "
                f"Use eligible target IDs: {', '.join(target)}",
                file=sys.stderr,
            )
            return 2

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
        "process": "automated scan via scripts/backfill_security_review.py",
        "assessed_commit": args.assessed_commit,
        "command": "python3 scripts/backfill_security_review.py "
        + " ".join(shlex.quote(a) for a in argv),
        "issue": "https://github.com/tradermonty/claude-trading-skills/issues/496",
        "note": (
            "proposals are advisory and fail-closed: `passed` requires mechanical-clean AND an "
            "explicit --reviewer-confirmed entry. key_leak_signal is advisory only; "
            "exception_key_leak_findings (key in request + unredacted exception print/log) "
            "counts against clean. Missing executable-skill manifests and missing/unproven "
            "per-call timeout prerequisites also prevent passed proposals. Static evidence is "
            "advisory and never replaces the five-dimension per-skill human review."
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
