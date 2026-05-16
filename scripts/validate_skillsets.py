#!/usr/bin/env python3
"""Validate skillsets/*.yaml manifests (Phase-2 SSoT-strength gate).

A skillset manifest is a category-scoped skill bundle tied to the workflow(s)
that operationalize it. This validator is intentionally strict: it enforces
full-field completeness AND live `related_workflows` coherence, so a workflow
edit that a skillset fails to track is a hard error (the pre-commit hook fires
on `workflows/*.yaml` too).

Emits stable error codes SK001-SK013 (+ SK-PARSE / SK-MISSING). See
docs/dev/metadata-and-workflow-schema.md for the full catalog. Mirrors the
patterns of scripts/validate_skills_index.py (Finding/_load_yaml/main/exit).
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Enums (kept in sync with docs/dev/metadata-and-workflow-schema.md +
# skills-index.yaml / workflow schema)
# ---------------------------------------------------------------------------

VALID_CATEGORIES = frozenset(
    {
        "market-regime",
        "core-portfolio",
        "swing-opportunity",
        "trade-planning",
        "trade-memory",
        "strategy-research",
        "advanced-satellite",
        "meta",
    }
)
VALID_TIMEFRAMES = frozenset({"daily", "weekly", "event-driven", "research"})
VALID_DIFFICULTIES = frozenset({"beginner", "intermediate", "advanced"})
VALID_API_PROFILES = frozenset({"no-api-basic", "fmp-required", "alpaca-required", "mixed"})

# Mirrors recommend.py:PAID_INTEGRATION_IDS — keep in lockstep.
PAID_INTEGRATION_IDS = frozenset({"fmp", "finviz", "alpaca"})

SUPPORTED_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # "error" or "warning"
    location: str
    message: str

    def format(self) -> str:
        return f"[{self.severity.upper():7s}] {self.code} {self.location}: {self.message}"


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Cross-loaded SSoT inputs
# ---------------------------------------------------------------------------


def _load_skills_index(project_root: Path) -> dict[str, dict]:
    """Return {skill_id: {category, status, integrations}} from skills-index.yaml."""
    path = project_root / "skills-index.yaml"
    if not path.is_file():
        return {}
    index = _load_yaml(path)
    out: dict[str, dict] = {}
    for entry in (index or {}).get("skills") or []:
        if isinstance(entry, dict) and entry.get("id"):
            out[str(entry["id"])] = entry
    return out


def _load_workflows(project_root: Path) -> dict[str, dict]:
    """Return {workflow_id: {required_skills, api_profile}} from workflows/*.yaml."""
    wf_dir = project_root / "workflows"
    out: dict[str, dict] = {}
    if not wf_dir.is_dir():
        return out
    for wf_path in sorted(wf_dir.glob("*.yaml")):
        wf = _load_yaml(wf_path)
        if isinstance(wf, dict) and wf.get("id"):
            out[str(wf["id"])] = wf
    return out


def _api_covers(skillset_profile: str, workflow_profile: str) -> bool:
    """True iff a skillset's api_profile covers a related workflow's.

    - `mixed` is the multi-provider umbrella → covers everything.
    - Any profile covers a `no-api-basic` workflow (no extra keys needed).
    - Otherwise the provider must match EXACTLY: `fmp-required` and
      `alpaca-required` are the same "needs a paid key" tier but are NOT
      interchangeable (different provider), so they do not cover each other.
    """
    if skillset_profile == "mixed":
        return True
    if workflow_profile == "no-api-basic":
        return True
    return skillset_profile == workflow_profile


def _skill_is_paid_required(skill: dict | None) -> bool:
    """True iff the skill has a PAID integration at requirement == required.

    Mirrors recommend.py:workflow_paid_api_reason's skill-level predicate.
    """
    if not skill:
        return False
    for ig in skill.get("integrations") or []:
        if (
            isinstance(ig, dict)
            and ig.get("id") in PAID_INTEGRATION_IDS
            and ig.get("requirement") == "required"
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Per-manifest validation
# ---------------------------------------------------------------------------


def _validate_manifest(
    path: Path,
    skills_by_id: dict[str, dict],
    workflows_by_id: dict[str, dict],
) -> list[Finding]:
    findings: list[Finding] = []
    rel = f"skillsets/{path.name}"
    stem = path.stem

    try:
        m = _load_yaml(path)
    except yaml.YAMLError as e:
        return [Finding("SK-PARSE", "error", rel, f"YAML parse error: {e}")]
    if not isinstance(m, dict):
        return [Finding("SK-PARSE", "error", rel, "top-level must be a mapping")]

    mid = str(m.get("id") or "").strip()

    # SK001 — id == filename stem
    if mid != stem:
        findings.append(Finding("SK001", "error", rel, f"id {mid!r} != filename stem {stem!r}"))

    # SK002 — id is a canonical category, and category == id
    if mid and mid not in VALID_CATEGORIES:
        findings.append(
            Finding(
                "SK002",
                "error",
                rel,
                f"id {mid!r} is not a canonical skills-index category",
            )
        )
    if str(m.get("category") or "").strip() != mid:
        findings.append(
            Finding(
                "SK002",
                "error",
                rel,
                f"category {m.get('category')!r} must equal id {mid!r}",
            )
        )

    # SK003 — scalar fields present + valid
    if m.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        findings.append(
            Finding(
                "SK003",
                "error",
                rel,
                f"schema_version is {m.get('schema_version')!r}, expected "
                f"{SUPPORTED_SCHEMA_VERSION}",
            )
        )
    if not str(m.get("display_name") or "").strip():
        findings.append(Finding("SK003", "error", rel, "display_name is missing/empty"))
    if m.get("timeframe") not in VALID_TIMEFRAMES:
        findings.append(Finding("SK003", "error", rel, f"invalid timeframe {m.get('timeframe')!r}"))
    if m.get("difficulty") not in VALID_DIFFICULTIES:
        findings.append(
            Finding("SK003", "error", rel, f"invalid difficulty {m.get('difficulty')!r}")
        )
    api_profile = m.get("api_profile")
    if api_profile not in VALID_API_PROFILES:
        findings.append(Finding("SK003", "error", rel, f"invalid api_profile {api_profile!r}"))

    # SK004 — prose fields present + non-blank
    for field in ("when_to_use", "when_not_to_use"):
        val = m.get(field)
        if not isinstance(val, str) or not val.strip():
            findings.append(Finding("SK004", "error", rel, f"{field} is missing/blank/non-str"))

    # SK005 — list field type + non-empty rules
    def _is_str_list(v: Any) -> bool:
        return isinstance(v, list) and all(isinstance(x, str) for x in v)

    for field in ("target_users", "required_skills", "related_workflows"):
        v = m.get(field)
        if not _is_str_list(v) or not v:
            findings.append(
                Finding("SK005", "error", rel, f"{field} must be a non-empty list[str]")
            )
    for field in ("recommended_skills", "optional_skills"):
        # Key is REQUIRED (DoD lists recommended/optional skills); value must
        # be a list[str] but may be empty. Absent key or null value is an error
        # — do not silently coerce a missing key to [].
        if field not in m:
            findings.append(
                Finding(
                    "SK005",
                    "error",
                    rel,
                    f"{field} key is required (use an empty list if none)",
                )
            )
            continue
        if not _is_str_list(m.get(field)):
            findings.append(Finding("SK005", "error", rel, f"{field} must be a list[str]"))

    req = [s for s in (m.get("required_skills") or []) if isinstance(s, str)]
    rec = [s for s in (m.get("recommended_skills") or []) if isinstance(s, str)]
    opt = [s for s in (m.get("optional_skills") or []) if isinstance(s, str)]
    rel_wfs = [s for s in (m.get("related_workflows") or []) if isinstance(s, str)]
    all_listed = req + rec + opt

    # SK006 — every listed skill exists in skills-index.yaml
    for sid in all_listed:
        if sid not in skills_by_id:
            findings.append(
                Finding("SK006", "error", rel, f"skill {sid!r} not in skills-index.yaml")
            )

    # SK007 — no deprecated skill in required_skills
    for sid in req:
        sk = skills_by_id.get(sid)
        if sk and sk.get("status") == "deprecated":
            findings.append(Finding("SK007", "error", rel, f"required skill {sid!r} is deprecated"))

    # SK008 — required/recommended/optional pairwise disjoint
    for a_name, a, b_name, b in (
        ("required_skills", req, "recommended_skills", rec),
        ("required_skills", req, "optional_skills", opt),
        ("recommended_skills", rec, "optional_skills", opt),
    ):
        overlap = sorted(set(a) & set(b))
        if overlap:
            findings.append(
                Finding(
                    "SK008",
                    "error",
                    rel,
                    f"{a_name} and {b_name} overlap: {overlap}",
                )
            )

    # SK009 — related_workflows resolve to workflows/<id>.yaml
    for wid in rel_wfs:
        if wid not in workflows_by_id:
            findings.append(
                Finding(
                    "SK009",
                    "error",
                    rel,
                    f"related_workflows {wid!r} has no workflows/{wid}.yaml",
                )
            )

    resolved_wfs = [workflows_by_id[w] for w in rel_wfs if w in workflows_by_id]

    # SK010 — coverage drift: union(workflow.required_skills) subset of req
    wf_required_union: set[str] = set()
    for wf in resolved_wfs:
        wf_required_union |= {s for s in (wf.get("required_skills") or []) if isinstance(s, str)}
    missing = sorted(wf_required_union - set(req))
    if missing:
        findings.append(
            Finding(
                "SK010",
                "error",
                rel,
                f"related workflows require skills not in this skillset's "
                f"required_skills: {missing}",
            )
        )

    # SK011 — single related workflow => required_skills set parity
    if len(resolved_wfs) == 1:
        only = {s for s in (resolved_wfs[0].get("required_skills") or []) if isinstance(s, str)}
        if set(req) != only:
            findings.append(
                Finding(
                    "SK011",
                    "error",
                    rel,
                    f"single related workflow {rel_wfs[0]!r}: required_skills "
                    f"{sorted(set(req))} != workflow's {sorted(only)}",
                )
            )

    # SK012 — api_profile must COVER every related workflow's api_profile.
    # Coverage (not rank): `mixed` is the multi-provider umbrella and covers
    # all; any profile covers a `no-api-basic` workflow; otherwise the provider
    # must match EXACTLY. So an fmp-required workflow under an alpaca-required
    # skillset is a provider mismatch and fails (same-rank but incompatible).
    if api_profile in VALID_API_PROFILES:
        for wf in resolved_wfs:
            wf_profile = str(wf.get("api_profile"))
            if not _api_covers(api_profile, wf_profile):
                findings.append(
                    Finding(
                        "SK012",
                        "error",
                        rel,
                        f"api_profile {api_profile!r} does not cover related "
                        f"workflow api_profile {wf_profile!r}",
                    )
                )

    # SK013 — no-api-basic bundle must contain no paid-required skill anywhere
    if api_profile == "no-api-basic":
        for sid in all_listed:
            if _skill_is_paid_required(skills_by_id.get(sid)):
                findings.append(
                    Finding(
                        "SK013",
                        "error",
                        rel,
                        f"no-api-basic skillset lists paid-required skill {sid!r}",
                    )
                )

    return findings


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def validate(project_root: Path) -> list[Finding]:
    skillsets_dir = project_root / "skillsets"
    if not skillsets_dir.is_dir():
        # Absent directory is OK (0 findings) — validator is safe to run anywhere.
        return []

    skills_by_id = _load_skills_index(project_root)
    workflows_by_id = _load_workflows(project_root)

    findings: list[Finding] = []
    for path in sorted(skillsets_dir.glob("*.yaml")):
        findings.extend(_validate_manifest(path, skills_by_id, workflows_by_id))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate skillsets/*.yaml manifests (SK001-SK013)."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the repository root (default: cwd)",
    )
    # Hooks pass changed filenames as positional args; accept and ignore them
    # since we always re-validate every manifest regardless of which changed.
    parser.add_argument("files", nargs="*", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    findings = validate(args.project_root)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]

    for f in findings:
        print(f.format(), file=sys.stderr)

    if errors:
        print(
            f"\nFAIL: {len(errors)} error(s), {len(warnings)} warning(s)",
            file=sys.stderr,
        )
        return 1
    if warnings:
        print(f"\nOK with {len(warnings)} warning(s)", file=sys.stderr)
    else:
        print("OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
