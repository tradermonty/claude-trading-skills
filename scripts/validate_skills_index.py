#!/usr/bin/env python3
"""Validate skills-index.yaml against skills/ folder, frontmatter, and (optionally) workflows/.

Strictness levels:
  default              : index/folder bijection + required fields + enums
  --strict-workflows   : also resolve workflow references and check internal-consistency
  --strict-metadata    : also enforce timeframe/difficulty/inputs/outputs completeness

Emits stable error codes (IDX001-012, WF001-013). See
docs/dev/metadata-and-workflow-schema.md for the full catalog.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Enums (kept in sync with docs/dev/metadata-and-workflow-schema.md)
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

VALID_STATUSES = frozenset({"production", "beta", "experimental", "deprecated"})

VALID_INTEGRATION_TYPES = frozenset(
    {
        "broker",
        "market_data",
        "screener",
        "web",
        "local_file",
        "image",
        "mcp",
        "calculation",
        "none",
        "unknown",
    }
)

VALID_REQUIREMENTS = frozenset(
    {
        "required",
        "recommended",
        "optional",
        "not_required",
        "unknown",
    }
)

VALID_TIMEFRAMES = frozenset({"daily", "weekly", "event-driven", "research", "unknown"})
VALID_DIFFICULTIES = frozenset({"beginner", "intermediate", "advanced", "unknown"})

# ---------------------------------------------------------------------------
# Frontmatter parser (mirrors scripts/hooks/check_skill_frontmatter.py)
# ---------------------------------------------------------------------------

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
FIELD_RE = re.compile(r"^(\w+):\s*(.+)$", re.MULTILINE)


def parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}
    return dict(FIELD_RE.findall(match.group(1)))


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str  # "error" or "warning"
    location: str
    message: str

    def format(self) -> str:
        return f"[{self.severity.upper():7s}] {self.code} {self.location}: {self.message}"


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _scan_skill_folders(project_root: Path) -> dict[str, Path]:
    """Return {skill_id: SKILL.md path} for every skills/<id>/SKILL.md present."""
    skills_dir = project_root / "skills"
    if not skills_dir.is_dir():
        return {}
    folders = {}
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if skill_md.is_file():
            folders[child.name] = skill_md
    return folders


SUPPORTED_SCHEMA_VERSION = 1


def _validate_index_structure(
    index: Any, project_root: Path, *, strict_metadata: bool, strict_workflows: bool
) -> tuple[list[Finding], dict[str, dict]]:
    """First pass: parse skills-index.yaml structure; collect per-skill entries."""
    findings: list[Finding] = []
    skills_by_id: dict[str, dict] = {}

    if not isinstance(index, dict):
        findings.append(
            Finding("IDX-PARSE", "error", "skills-index.yaml", "top-level must be a mapping")
        )
        return findings, skills_by_id

    # IDX010: schema_version must be present and equal to SUPPORTED_SCHEMA_VERSION
    schema_version = index.get("schema_version")
    if schema_version != SUPPORTED_SCHEMA_VERSION:
        findings.append(
            Finding(
                "IDX010",
                "error",
                "skills-index.yaml",
                f"schema_version is {schema_version!r}, expected {SUPPORTED_SCHEMA_VERSION}",
            )
        )

    # IDX011: categories block must list EXACTLY the canonical 8 (no duplicates,
    # no missing, no extras). Length check catches duplicates that survive set().
    categories = index.get("categories")
    if (
        not isinstance(categories, list)
        or set(categories) != VALID_CATEGORIES
        or len(categories) != len(VALID_CATEGORIES)
    ):
        findings.append(
            Finding(
                "IDX011",
                "error",
                "skills-index.yaml",
                (
                    "`categories:` block must list exactly the 8 canonical categories "
                    f"({sorted(VALID_CATEGORIES)}) with no duplicates"
                ),
            )
        )

    skills = index.get("skills") or []
    if not isinstance(skills, list):
        findings.append(
            Finding("IDX-PARSE", "error", "skills-index.yaml", "`skills:` must be a list")
        )
        return findings, skills_by_id

    seen_ids: dict[str, int] = {}
    for entry in skills:
        if not isinstance(entry, dict):
            findings.append(
                Finding("IDX-PARSE", "error", "skills-index.yaml", "skill entry must be a mapping")
            )
            continue
        skill_id = str(entry.get("id") or "").strip()
        if not skill_id:
            findings.append(
                Finding(
                    "IDX-PARSE",
                    "error",
                    "skills-index.yaml",
                    "skill entry missing required `id`",
                )
            )
            continue

        if skill_id in seen_ids:
            findings.append(
                Finding(
                    "IDX001",
                    "error",
                    f"skills-index.yaml::{skill_id}",
                    "duplicate skill id (also seen earlier)",
                )
            )
            continue
        seen_ids[skill_id] = 1
        skills_by_id[skill_id] = entry

        loc = f"skills-index.yaml::{skill_id}"

        # Required fields
        if not str(entry.get("display_name") or "").strip():
            findings.append(
                Finding("IDX-PARSE", "error", loc, "missing required field `display_name`")
            )

        category = entry.get("category")
        if category not in VALID_CATEGORIES:
            findings.append(Finding("IDX005", "error", loc, f"invalid category {category!r}"))

        status = entry.get("status")
        if status not in VALID_STATUSES:
            findings.append(Finding("IDX006", "error", loc, f"invalid status {status!r}"))

        if not str(entry.get("summary") or "").strip():
            findings.append(Finding("IDX009", "error", loc, "summary is empty"))

        # integrations
        for idx, integ in enumerate(entry.get("integrations") or []):
            iloc = f"{loc}.integrations[{idx}]"
            if not isinstance(integ, dict):
                findings.append(Finding("IDX-PARSE", "error", iloc, "must be a mapping"))
                continue
            itype = integ.get("type")
            if itype is not None and itype not in VALID_INTEGRATION_TYPES:
                findings.append(
                    Finding("IDX007", "error", iloc, f"invalid integration type {itype!r}")
                )
            ireq = integ.get("requirement")
            if ireq is not None and ireq not in VALID_REQUIREMENTS:
                findings.append(Finding("IDX008", "error", iloc, f"invalid requirement {ireq!r}"))
            # IDX012: explicit `unknown` markers are warnings by default,
            # errors under --strict-metadata. Severity is consistent with the
            # schema spec doc (default/strict-workflows: warn; strict-metadata: error).
            if integ.get("id") == "unknown" or itype == "unknown" or ireq == "unknown":
                sev = "error" if strict_metadata else "warning"
                findings.append(
                    Finding(
                        "IDX012",
                        sev,
                        iloc,
                        "integration uses `unknown` marker — flagged for owner review",
                    )
                )

        # Best-effort fields (warn vs error)
        timeframe = entry.get("timeframe", "unknown")
        if timeframe not in VALID_TIMEFRAMES:
            sev = "error" if strict_metadata else "warning"
            findings.append(Finding("IDX-META", sev, loc, f"invalid timeframe {timeframe!r}"))
        elif timeframe == "unknown":
            sev = "error" if strict_metadata else "warning"
            findings.append(Finding("IDX-META", sev, loc, "timeframe is `unknown`"))

        difficulty = entry.get("difficulty", "unknown")
        if difficulty not in VALID_DIFFICULTIES:
            sev = "error" if strict_metadata else "warning"
            findings.append(Finding("IDX-META", sev, loc, f"invalid difficulty {difficulty!r}"))
        elif difficulty == "unknown":
            sev = "error" if strict_metadata else "warning"
            findings.append(Finding("IDX-META", sev, loc, "difficulty is `unknown`"))

        if strict_metadata and not entry.get("inputs"):
            findings.append(Finding("IDX-META", "error", loc, "inputs is empty"))
        if strict_metadata and not entry.get("outputs"):
            findings.append(Finding("IDX-META", "error", loc, "outputs is empty"))

    return findings, skills_by_id


def _validate_bijection_and_frontmatter(
    skills_by_id: dict[str, dict], folders: dict[str, Path]
) -> list[Finding]:
    findings: list[Finding] = []

    # IDX002: index entry without folder
    for skill_id in skills_by_id:
        if skill_id not in folders:
            findings.append(
                Finding(
                    "IDX002",
                    "error",
                    f"skills-index.yaml::{skill_id}",
                    f"index entry has no skills/{skill_id}/ folder",
                )
            )

    # IDX003: folder without index entry
    for skill_id in folders:
        if skill_id not in skills_by_id:
            findings.append(
                Finding(
                    "IDX003",
                    "error",
                    f"skills/{skill_id}/SKILL.md",
                    "skill folder has no entry in skills-index.yaml",
                )
            )

    # IDX004: frontmatter `name` ≠ index `id`
    for skill_id, skill_md in folders.items():
        if skill_id not in skills_by_id:
            continue  # already reported as IDX003
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError as e:
            findings.append(Finding("IDX-PARSE", "error", str(skill_md), f"cannot read: {e}"))
            continue
        fm = parse_frontmatter(text)
        fm_name = (fm.get("name") or "").strip().strip("'\"")
        if fm_name != skill_id:
            findings.append(
                Finding(
                    "IDX004",
                    "error",
                    str(skill_md),
                    f"frontmatter name {fm_name!r} does not match index id {skill_id!r}",
                )
            )

    return findings


def _validate_workflow_references(
    skills_by_id: dict[str, dict], project_root: Path, *, strict: bool
) -> tuple[list[Finding], dict[str, Path]]:
    """Check that each skill's workflows[] entry resolves to a workflows/<id>.yaml file.

    In default mode, missing files are warnings. Under --strict-workflows they are errors.
    Returns (findings, workflow_files_seen).
    """
    findings: list[Finding] = []
    workflows_dir = project_root / "workflows"
    available: dict[str, Path] = {}
    if workflows_dir.is_dir():
        for wf in workflows_dir.glob("*.yaml"):
            available[wf.stem] = wf

    for skill_id, entry in skills_by_id.items():
        for wf_id in entry.get("workflows") or []:
            if wf_id not in available:
                sev = "error" if strict else "warning"
                findings.append(
                    Finding(
                        "WF001",
                        sev,
                        f"skills-index.yaml::{skill_id}",
                        f"workflows[] reference {wf_id!r} has no workflows/{wf_id}.yaml file",
                    )
                )
    return findings, available


def _validate_workflow_internal(
    workflow_path: Path,
    skills_by_id: dict[str, dict],
) -> list[Finding]:
    findings: list[Finding] = []
    rel_loc = f"workflows/{workflow_path.name}"

    try:
        wf = _load_yaml(workflow_path)
    except yaml.YAMLError as e:
        return [Finding("WF-PARSE", "error", rel_loc, f"YAML parse error: {e}")]

    if not isinstance(wf, dict):
        return [Finding("WF-PARSE", "error", rel_loc, "top-level must be a mapping")]

    wf_id = str(wf.get("id") or "")
    if wf_id != workflow_path.stem:
        findings.append(
            Finding(
                "WF002",
                "error",
                rel_loc,
                f"workflow id {wf_id!r} does not match filename {workflow_path.stem!r}",
            )
        )

    required_skills = list(wf.get("required_skills") or [])
    optional_skills = list(wf.get("optional_skills") or [])

    # WF008: deprecated skill in required_skills
    for skill_id in required_skills:
        entry = skills_by_id.get(skill_id)
        if entry and entry.get("status") == "deprecated":
            findings.append(
                Finding(
                    "WF008",
                    "error",
                    rel_loc,
                    f"required_skills contains deprecated skill {skill_id!r}",
                )
            )

    # WF011: every required_skills / optional_skills entry must exist in the index.
    # required_skills missing-from-index is also caught indirectly when the same
    # id appears as a step (WF003), but explicit checking here covers setup-only
    # bundle suggestions where the skill never appears in any step.
    for skill_id in required_skills + optional_skills:
        if skill_id not in skills_by_id:
            findings.append(
                Finding(
                    "WF011",
                    "error",
                    rel_loc,
                    f"required_skills / optional_skills entry {skill_id!r} not in skills-index.yaml",
                )
            )

    steps = wf.get("steps") or []
    if not isinstance(steps, list):
        findings.append(Finding("WF-PARSE", "error", rel_loc, "`steps` must be a list"))
        steps = []

    # Build artifact production map and step skill resolution
    artifacts = wf.get("artifacts") or []
    artifact_produced_by: dict[str, int] = {}
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        art_id = str(art.get("id") or "")
        produced_by = art.get("produced_by_step")
        if art_id and isinstance(produced_by, int):
            artifact_produced_by[art_id] = produced_by

    # Build step.produces map for WF012 cross-check
    step_produces: dict[int, set[str]] = {}
    valid_steps: dict[int, dict] = {}

    seen_step_numbers: set[int] = set()
    non_optional_step_skills: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            findings.append(Finding("WF-PARSE", "error", rel_loc, "step must be a mapping"))
            continue
        step_num = step.get("step")
        if isinstance(step_num, int):
            seen_step_numbers.add(step_num)
        if isinstance(step_num, int) and not isinstance(step_num, bool):
            valid_steps[step_num] = step
        skill_id = str(step.get("skill") or "")
        is_optional = bool(step.get("optional", False))
        if isinstance(step_num, int):
            step_produces[step_num] = set(step.get("produces") or [])

        # WF003: step.skill exists in index
        if skill_id and skill_id not in skills_by_id:
            findings.append(
                Finding(
                    "WF003",
                    "error",
                    f"{rel_loc} step {step_num}",
                    f"step skill {skill_id!r} not in skills-index.yaml",
                )
            )

        # WF010: non-optional step.skill must appear in required_skills
        if not is_optional and skill_id and skill_id not in required_skills:
            findings.append(
                Finding(
                    "WF010",
                    "error",
                    f"{rel_loc} step {step_num}",
                    f"non-optional step skill {skill_id!r} missing from required_skills",
                )
            )
        if not is_optional and skill_id:
            non_optional_step_skills.add(skill_id)

        # WF005: decision_gate true requires decision_question
        if step.get("decision_gate") and not str(step.get("decision_question") or "").strip():
            findings.append(
                Finding(
                    "WF005",
                    "error",
                    f"{rel_loc} step {step_num}",
                    "decision_gate is true but decision_question is missing/empty",
                )
            )

        # WF004: depends_on references prior steps only
        for dep in step.get("depends_on") or []:
            if isinstance(dep, int) and isinstance(step_num, int) and dep >= step_num:
                findings.append(
                    Finding(
                        "WF004",
                        "error",
                        f"{rel_loc} step {step_num}",
                        f"depends_on includes step {dep} which is not strictly earlier",
                    )
                )

        # WF007: consumes artifact produced by an earlier step
        for art_id in step.get("consumes") or []:
            produced_at = artifact_produced_by.get(art_id)
            if produced_at is None:
                findings.append(
                    Finding(
                        "WF007",
                        "error",
                        f"{rel_loc} step {step_num}",
                        f"consumes artifact {art_id!r} which is not declared in artifacts:",
                    )
                )
            elif isinstance(step_num, int) and produced_at >= step_num:
                findings.append(
                    Finding(
                        "WF007",
                        "error",
                        f"{rel_loc} step {step_num}",
                        f"consumes artifact {art_id!r} produced at step {produced_at} (not earlier)",
                    )
                )

    # WF009: every required_skills entry appears in at least one non-optional step
    for skill_id in required_skills:
        if skill_id not in non_optional_step_skills:
            findings.append(
                Finding(
                    "WF009",
                    "error",
                    rel_loc,
                    f"required_skills entry {skill_id!r} never appears in a non-optional step",
                )
            )

    # WF012: artifacts[].produced_by_step <-> steps[N].produces parity.
    # Both directions:
    #   - For every artifact A: the step it claims to be produced by must list A in produces.
    #   - For every step's `produces`: each artifact id must be declared in artifacts[].
    for art in artifacts:
        if not isinstance(art, dict):
            continue
        art_id = str(art.get("id") or "")
        produced_by = art.get("produced_by_step")
        if not art_id or not isinstance(produced_by, int):
            continue
        producing_step_outputs = step_produces.get(produced_by, set())
        if art_id not in producing_step_outputs:
            findings.append(
                Finding(
                    "WF012",
                    "error",
                    rel_loc,
                    (
                        f"artifact {art_id!r} declares produced_by_step={produced_by} "
                        f"but step {produced_by} does not list it in produces"
                    ),
                )
            )
    declared_artifact_ids = {
        str(a.get("id")) for a in artifacts if isinstance(a, dict) and a.get("id")
    }
    for step_num, produced in step_produces.items():
        for art_id in produced:
            if art_id not in declared_artifact_ids:
                findings.append(
                    Finding(
                        "WF012",
                        "error",
                        f"{rel_loc} step {step_num}",
                        f"step produces {art_id!r} which is not declared in artifacts:",
                    )
                )

    # WF013: a required artifact produced before the final valid integer step
    # must be consumed by a later step. Only artifacts whose production
    # contract is WF012-valid participate, so malformed artifacts do not get a
    # redundant WF013 finding.
    if valid_steps:
        final_step = max(valid_steps)
        for art in artifacts:
            if not isinstance(art, dict) or art.get("required") is not True:
                continue
            art_id = str(art.get("id") or "")
            produced_by = art.get("produced_by_step")
            if (
                not art_id
                or not isinstance(produced_by, int)
                or isinstance(produced_by, bool)
                or produced_by not in valid_steps
                or art_id not in set(valid_steps[produced_by].get("produces") or [])
                or produced_by >= final_step
            ):
                continue
            consumed_later = any(
                step_num > produced_by and art_id in set(step.get("consumes") or [])
                for step_num, step in valid_steps.items()
            )
            if not consumed_later:
                findings.append(
                    Finding(
                        "WF013",
                        "error",
                        rel_loc,
                        (
                            f"required artifact {art_id!r} produced at step {produced_by} "
                            "is not consumed by any later step"
                        ),
                    )
                )

    # WF006: journal_destination resolves to a skill id
    journal = wf.get("journal_destination")
    if journal is not None:
        journal = str(journal)
        if journal and journal not in skills_by_id:
            findings.append(
                Finding(
                    "WF006",
                    "error",
                    rel_loc,
                    f"journal_destination {journal!r} does not resolve to a skill id",
                )
            )

    # Track optional_skills for completeness (no current rule, but parse it)
    _ = optional_skills

    return findings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def validate(
    project_root: Path,
    *,
    strict_workflows: bool = False,
    strict_metadata: bool = False,
) -> list[Finding]:
    findings: list[Finding] = []

    index_path = project_root / "skills-index.yaml"
    if not index_path.is_file():
        findings.append(
            Finding(
                "IDX-MISSING",
                "error",
                str(index_path),
                "skills-index.yaml not found at project root",
            )
        )
        return findings

    try:
        index = _load_yaml(index_path)
    except yaml.YAMLError as e:
        findings.append(Finding("IDX-PARSE", "error", str(index_path), f"YAML parse error: {e}"))
        return findings

    structure_findings, skills_by_id = _validate_index_structure(
        index,
        project_root,
        strict_metadata=strict_metadata,
        strict_workflows=strict_workflows,
    )
    findings.extend(structure_findings)

    folders = _scan_skill_folders(project_root)
    findings.extend(_validate_bijection_and_frontmatter(skills_by_id, folders))

    wf_ref_findings, available_workflows = _validate_workflow_references(
        skills_by_id, project_root, strict=strict_workflows
    )
    findings.extend(wf_ref_findings)

    if strict_workflows:
        for wf_path in available_workflows.values():
            findings.extend(_validate_workflow_internal(wf_path, skills_by_id))

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate skills-index.yaml and (optionally) workflow manifests."
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Path to the repository root (default: cwd)",
    )
    parser.add_argument(
        "--strict-workflows",
        action="store_true",
        help="Treat missing workflow files and workflow internal-consistency as errors.",
    )
    parser.add_argument(
        "--strict-metadata",
        action="store_true",
        help="Require timeframe/difficulty/inputs/outputs to be populated.",
    )
    # Hooks pass filenames as positional args; accept and ignore them since we
    # always re-validate the entire index regardless of which file changed.
    parser.add_argument("files", nargs="*", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    findings = validate(
        args.project_root,
        strict_workflows=args.strict_workflows,
        strict_metadata=args.strict_metadata,
    )

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
