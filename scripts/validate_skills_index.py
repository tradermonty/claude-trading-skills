#!/usr/bin/env python3
"""Validate skills-index.yaml against skills/ folder, frontmatter, and (optionally) workflows/.

Strictness levels:
  default              : index/folder bijection + required fields + enums
  --strict-workflows   : also resolve workflow references and check internal-consistency
  --strict-metadata    : also enforce timeframe/difficulty/inputs/outputs completeness

Emits stable error codes (IDX001-015, WF001-016). See
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
VALID_OPERATIONAL_ROLES = frozenset(
    {"standalone", "workflow_step", "internal_component", "research_only"}
)

VERIFICATION_AXES = frozenset(
    {
        "instruction_contract",
        "unit_tests",
        "workflow_contract",
        "end_to_end_replay",
        "data_provenance",
        "financial_logic_review",
        "empirical_validation",
        "security_review",
    }
)
VALID_VERIFICATION_VALUES = frozenset({"passed", "not_verified", "not_applicable"})


def _valid_enum(value: object, allowed: frozenset[str]) -> bool:
    return isinstance(value, str) and value in allowed


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
        or not all(isinstance(item, str) for item in categories)
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
        if not _valid_enum(category, VALID_CATEGORIES):
            findings.append(Finding("IDX005", "error", loc, f"invalid category {category!r}"))

        status = entry.get("status")
        if not _valid_enum(status, VALID_STATUSES):
            findings.append(Finding("IDX006", "error", loc, f"invalid status {status!r}"))

        operational_role_present = "operational_role" in entry
        if not operational_role_present:
            severity = "error" if strict_metadata else "warning"
            findings.append(
                Finding(
                    "IDX015",
                    severity,
                    loc,
                    "missing required `operational_role` mapping",
                )
            )
        else:
            operational_role = entry.get("operational_role")
            role_error: str | None = None
            if not isinstance(operational_role, dict):
                role_error = "`operational_role` must be a mapping"
            else:
                role_type = operational_role.get("type")
                expected_keys = {"type", "rationale"} if role_type == "standalone" else {"type"}
                missing_keys = sorted(expected_keys - set(operational_role))
                unknown_keys = sorted(set(operational_role) - expected_keys, key=repr)
                if not _valid_enum(role_type, VALID_OPERATIONAL_ROLES):
                    role_error = f"`operational_role.type` has invalid value {role_type!r}"
                elif missing_keys:
                    role_error = f"`operational_role` missing keys: {missing_keys}"
                elif unknown_keys:
                    role_error = f"`operational_role` has unknown keys: {unknown_keys}"
                elif role_type == "standalone" and (
                    not isinstance(operational_role.get("rationale"), str)
                    or not operational_role["rationale"].strip()
                ):
                    role_error = (
                        "`operational_role.rationale` must be a non-empty string "
                        "for standalone skills"
                    )
            if role_error:
                findings.append(Finding("IDX015", "error", loc, role_error))

        if "knowledge_only" in entry:
            knowledge_only = entry.get("knowledge_only")
            if not isinstance(knowledge_only, bool):
                findings.append(
                    Finding("IDX014", "error", loc, "`knowledge_only` must be a boolean")
                )
            elif knowledge_only:
                scripts_dir = project_root / "skills" / skill_id / "scripts"
                executable_scripts = [
                    path
                    for path in scripts_dir.rglob("*.py")
                    if path.is_file()
                    and path.name != "__init__.py"
                    and "tests" not in path.relative_to(scripts_dir).parts
                ]
                if status != "production":
                    findings.append(
                        Finding(
                            "IDX014",
                            "error",
                            loc,
                            "`knowledge_only: true` is only valid for production skills",
                        )
                    )
                if executable_scripts:
                    findings.append(
                        Finding(
                            "IDX014",
                            "error",
                            loc,
                            "`knowledge_only: true` conflicts with executable Python scripts",
                        )
                    )

        verification_present = "verification" in entry
        if status == "production" and not verification_present:
            severity = "error" if strict_metadata else "warning"
            findings.append(
                Finding(
                    "IDX013",
                    severity,
                    loc,
                    "production skill is missing required `verification` block",
                )
            )
        elif verification_present:
            verification = entry.get("verification")
            verification_error: str | None = None
            if not isinstance(verification, dict):
                verification_error = "`verification` must be a mapping"
            else:
                keys = set(verification)
                missing = sorted(VERIFICATION_AXES - keys)
                unknown = sorted(keys - VERIFICATION_AXES, key=repr)
                invalid = sorted(
                    (axis, verification[axis])
                    for axis in keys & VERIFICATION_AXES
                    if not isinstance(verification[axis], str)
                    or verification[axis] not in VALID_VERIFICATION_VALUES
                )
                if missing:
                    verification_error = f"`verification` missing keys: {missing}"
                elif unknown:
                    verification_error = f"`verification` has unknown keys: {unknown}"
                elif invalid:
                    verification_error = "`verification` has invalid value(s): " + ", ".join(
                        f"{axis}={value!r}" for axis, value in invalid
                    )
            if verification_error:
                findings.append(Finding("IDX013", "error", loc, verification_error))

        if not str(entry.get("summary") or "").strip():
            findings.append(Finding("IDX009", "error", loc, "summary is empty"))

        # integrations
        for idx, integ in enumerate(entry.get("integrations") or []):
            iloc = f"{loc}.integrations[{idx}]"
            if not isinstance(integ, dict):
                findings.append(Finding("IDX-PARSE", "error", iloc, "must be a mapping"))
                continue
            itype = integ.get("type")
            if itype is not None and not _valid_enum(itype, VALID_INTEGRATION_TYPES):
                findings.append(
                    Finding("IDX007", "error", iloc, f"invalid integration type {itype!r}")
                )
            ireq = integ.get("requirement")
            if ireq is not None and not _valid_enum(ireq, VALID_REQUIREMENTS):
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
        if not _valid_enum(timeframe, VALID_TIMEFRAMES):
            sev = "error" if strict_metadata else "warning"
            findings.append(Finding("IDX-META", sev, loc, f"invalid timeframe {timeframe!r}"))
        elif timeframe == "unknown":
            sev = "error" if strict_metadata else "warning"
            findings.append(Finding("IDX-META", sev, loc, "timeframe is `unknown`"))

        difficulty = entry.get("difficulty", "unknown")
        if not _valid_enum(difficulty, VALID_DIFFICULTIES):
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
        workflow_ids = _valid_workflow_backrefs(entry)
        if workflow_ids is None:
            sev = "error" if strict else "warning"
            findings.append(
                Finding(
                    "WF016",
                    sev,
                    f"skills-index.yaml::{skill_id}",
                    (
                        "`workflows` must be a list of unique, non-empty strings; "
                        f"got {entry.get('workflows')!r}"
                    ),
                )
            )
            continue
        for wf_id in workflow_ids:
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


def _valid_workflow_backrefs(entry: dict[str, Any]) -> list[str] | None:
    """Return valid, unique workflow IDs, else None."""
    raw_backrefs = entry.get("workflows")
    if not isinstance(raw_backrefs, list):
        return None
    if not all(isinstance(value, str) and value.strip() for value in raw_backrefs):
        return None
    if len(raw_backrefs) != len(set(raw_backrefs)):
        return None
    return raw_backrefs


def _valid_operational_role(entry: dict[str, Any]) -> str | None:
    """Return a structurally valid operational role type, else None."""
    role = entry.get("operational_role")
    if not isinstance(role, dict):
        return None
    role_type = role.get("type")
    if not _valid_enum(role_type, VALID_OPERATIONAL_ROLES):
        return None
    expected_keys = {"type", "rationale"} if role_type == "standalone" else {"type"}
    if set(role) != expected_keys:
        return None
    if role_type == "standalone" and (
        not isinstance(role.get("rationale"), str) or not role["rationale"].strip()
    ):
        return None
    return role_type


def _validate_operational_role_workflows(
    skills_by_id: dict[str, dict], workflow_paths: dict[str, Path]
) -> list[Finding]:
    """Enforce workflow forward/back references and role classification parity."""
    findings: list[Finding] = []
    forward_refs: dict[str, set[str]] = {skill_id: set() for skill_id in skills_by_id}

    for workflow_path in workflow_paths.values():
        try:
            workflow = _load_yaml(workflow_path)
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(workflow, dict):
            continue
        workflow_id = str(workflow.get("id") or workflow_path.stem)
        referenced: set[str] = set()
        for field in ("required_skills", "optional_skills"):
            values = workflow.get(field) or []
            if isinstance(values, list):
                referenced.update(str(value) for value in values if value)
        steps = workflow.get("steps") or []
        if isinstance(steps, list):
            referenced.update(
                str(step["skill"]) for step in steps if isinstance(step, dict) and step.get("skill")
            )
        for skill_id in referenced:
            if skill_id in forward_refs:
                forward_refs[skill_id].add(workflow_id)

    for skill_id, entry in skills_by_id.items():
        role_type = _valid_operational_role(entry)
        if role_type is None:
            # IDX015 is the single source finding for missing/malformed roles.
            continue
        loc = f"skills-index.yaml::{skill_id}"
        expected = sorted(forward_refs[skill_id])
        should_be_workflow_step = bool(expected)
        if (role_type == "workflow_step") != should_be_workflow_step:
            required_role = "workflow_step" if should_be_workflow_step else "a non-workflow role"
            findings.append(
                Finding(
                    "WF015",
                    "error",
                    loc,
                    (
                        f"operational_role.type is {role_type!r}; forward workflow "
                        f"references require {required_role} (workflows={expected})"
                    ),
                )
            )

        actual = _valid_workflow_backrefs(entry)
        if actual is None:
            # _validate_workflow_references emits the single WF016 shape finding.
            continue
        if sorted(actual) != expected:
            findings.append(
                Finding(
                    "WF016",
                    "error",
                    loc,
                    f"workflows back-references are {actual}; expected exactly {expected}",
                )
            )

    return findings


def _validate_workflow_japanese(
    wf: dict[str, Any],
    rel_loc: str,
) -> list[Finding]:
    """Enforce complete human-facing Japanese workflow prose (WF014)."""
    findings: list[Finding] = []

    def require_text(item: dict[str, Any], field: str, path: str) -> None:
        value = item.get(field)
        if not isinstance(value, str) or not value.strip():
            findings.append(
                Finding(
                    "WF014",
                    "error",
                    rel_loc,
                    f"{path}.{field} must be a non-empty string",
                )
            )

    for field in ("display_name_ja", "when_to_run_ja", "when_not_to_run_ja"):
        require_text(wf, field, rel_loc)

    nested_fields = (
        ("prerequisite_workflows", "rationale_ja"),
        ("manual_inputs", "description_ja"),
        ("final_outputs", "description_ja"),
    )
    for collection_name, field in nested_fields:
        collection = wf.get(collection_name)
        if collection is None:
            collection = []
        if not isinstance(collection, list):
            findings.append(
                Finding(
                    "WF014",
                    "error",
                    rel_loc,
                    f"{collection_name} must be a list for Japanese localization",
                )
            )
            continue
        for index, item in enumerate(collection):
            if not isinstance(item, dict):
                findings.append(
                    Finding(
                        "WF014",
                        "error",
                        rel_loc,
                        f"{collection_name}[{index}] must be a mapping",
                    )
                )
                continue
            require_text(item, field, f"{collection_name}[{index}]")

    steps = wf.get("steps")
    if not isinstance(steps, list):
        findings.append(
            Finding(
                "WF014",
                "error",
                rel_loc,
                "steps must be a list for Japanese localization",
            )
        )
    else:
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                findings.append(
                    Finding(
                        "WF014",
                        "error",
                        rel_loc,
                        f"steps[{index}] must be a mapping",
                    )
                )
                continue
            require_text(step, "name_ja", f"steps[{index}]")
            if step.get("decision_gate"):
                require_text(step, "decision_question_ja", f"steps[{index}]")

    manual_review = wf.get("manual_review")
    if not isinstance(manual_review, list):
        findings.append(
            Finding(
                "WF014",
                "error",
                rel_loc,
                "manual_review must be a list for Japanese localization",
            )
        )
        manual_review = []
    manual_review_ja = wf.get("manual_review_ja")
    if not isinstance(manual_review_ja, list):
        findings.append(
            Finding(
                "WF014",
                "error",
                rel_loc,
                "manual_review_ja must be a list matching manual_review",
            )
        )
    else:
        expected_count = len(manual_review)
        if len(manual_review_ja) != expected_count:
            findings.append(
                Finding(
                    "WF014",
                    "error",
                    rel_loc,
                    (
                        "manual_review_ja must contain exactly "
                        f"{expected_count} item(s) to match manual_review"
                    ),
                )
            )
        for index, item in enumerate(manual_review_ja):
            if not isinstance(item, str) or not item.strip():
                findings.append(
                    Finding(
                        "WF014",
                        "error",
                        rel_loc,
                        f"manual_review_ja[{index}] must be a non-empty string",
                    )
                )

    return findings


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

    findings.extend(_validate_workflow_japanese(wf, rel_loc))

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
        findings.extend(_validate_operational_role_workflows(skills_by_id, available_workflows))

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
