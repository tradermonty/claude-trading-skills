#!/usr/bin/env python3
"""Discover skill tests and enforce the versioned CI test/coverage policy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from datetime import date
from importlib import metadata
from pathlib import Path

import yaml
from packaging.requirements import InvalidRequirement, Requirement
from yaml.resolver import BaseResolver

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("config/ci-test-policy.yaml")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
POLICY_GATE_ID = "executable-test-policy"


class MatrixError(ValueError):
    """Raised when discovery, policy, and artifacts do not form a closed matrix."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    loader.flatten_mapping(node)
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise MatrixError(f"unhashable YAML mapping key: {key!r}") from exc
        if duplicate:
            raise MatrixError(f"duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


@dataclass(frozen=True)
class SkillMetadata:
    status: str
    knowledge_only: bool = False


@dataclass(frozen=True)
class DatedException:
    expires_on: date
    issue: int
    reason: str

    def as_dict(self) -> dict[str, object]:
        return {
            "expires_on": self.expires_on.isoformat(),
            "issue": self.issue,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class CoverageWaiver(DatedException):
    floor: int
    target: int

    def as_dict(self) -> dict[str, object]:
        return {
            "floor": self.floor,
            "target": self.target,
            **super().as_dict(),
        }


@dataclass(frozen=True)
class TestPolicy:
    __test__ = False

    aggregate_target: int
    aggregate_waiver: CoverageWaiver | None
    default_target: int
    tier_targets: dict[str, int]
    coverage_waivers: dict[str, CoverageWaiver]
    allowed_failures: dict[str, DatedException]
    matrix_overrides: dict[str, dict[str, object]]

    def target_for(self, skill_id: str) -> int:
        return self.tier_targets.get(skill_id, self.default_target)


@dataclass(frozen=True)
class TestEntry:
    __test__ = False

    id: str
    test_paths: tuple[str, ...]
    coverage_source: str
    requirements: tuple[str, ...] = ()
    allowed_failure: bool = False
    allowed_failure_policy: DatedException | None = None
    coverage_target: int | None = None
    coverage_floor: int | None = None
    coverage_waiver: CoverageWaiver | None = None
    reason: str | None = None
    policy_signature: str = ""


def _mapping(value: object, context: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise MatrixError(f"{context} must be a mapping")
    return value


def _strict_keys(
    value: dict[object, object],
    *,
    required: set[str],
    optional: set[str] = frozenset(),
    context: str,
) -> None:
    keys = set(value)
    missing = sorted(required - keys)
    unknown = sorted(keys - required - optional, key=repr)
    if missing:
        raise MatrixError(f"{context} missing keys: {', '.join(missing)}")
    if unknown:
        raise MatrixError(f"{context} has unknown keys: {unknown}")


def _bounded_int(value: object, context: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise MatrixError(f"{context} must be an integer from {minimum} to {maximum}")
    return value


def _nonempty_string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MatrixError(f"{context} must be a non-empty string")
    return value.strip()


def _expiry(value: object, context: str, today: date) -> date:
    raw = _nonempty_string(value, context)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError as exc:
        raise MatrixError(f"{context} must use YYYY-MM-DD") from exc
    if parsed < today:
        raise MatrixError(f"{context} expired on {parsed.isoformat()}")
    return parsed


def _dated_exception(value: object, context: str, today: date) -> DatedException:
    payload = _mapping(value, context)
    _strict_keys(
        payload,
        required={"expires_on", "issue", "reason"},
        context=context,
    )
    return DatedException(
        expires_on=_expiry(payload["expires_on"], f"{context}.expires_on", today),
        issue=_bounded_int(payload["issue"], f"{context}.issue", minimum=1, maximum=10**9),
        reason=_nonempty_string(payload["reason"], f"{context}.reason"),
    )


def _coverage_waiver(value: object, context: str, today: date) -> CoverageWaiver:
    payload = _mapping(value, context)
    _strict_keys(
        payload,
        required={"floor", "target", "expires_on", "issue", "reason"},
        context=context,
    )
    dated = _dated_exception(
        {key: payload[key] for key in ("expires_on", "issue", "reason")}, context, today
    )
    floor = _bounded_int(payload["floor"], f"{context}.floor", minimum=0, maximum=100)
    target = _bounded_int(payload["target"], f"{context}.target", minimum=1, maximum=100)
    if floor >= target:
        raise MatrixError(f"{context}.floor must be lower than target")
    return CoverageWaiver(
        floor=floor,
        target=target,
        expires_on=dated.expires_on,
        issue=dated.issue,
        reason=dated.reason,
    )


def _string_list(value: object, context: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise MatrixError(f"{context} must be a non-empty list")
    result = tuple(_nonempty_string(item, f"{context}[]") for item in value)
    if len(set(result)) != len(result):
        raise MatrixError(f"{context} contains duplicates")
    return result


def _load_yaml(path: Path, context: str) -> object:
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, yaml.YAMLError) as exc:
        raise MatrixError(f"cannot load {context}: {exc}") from exc


def load_skill_metadata(root: Path = ROOT) -> dict[str, SkillMetadata]:
    payload = _mapping(_load_yaml(root / "skills-index.yaml", "skills-index.yaml"), "skills-index")
    skills = payload.get("skills")
    if not isinstance(skills, list):
        raise MatrixError("skills-index.skills must be a list")
    result: dict[str, SkillMetadata] = {}
    for index, item in enumerate(skills):
        entry = _mapping(item, f"skills-index.skills[{index}]")
        skill_id = entry.get("id")
        if not isinstance(skill_id, str) or not ID_RE.fullmatch(skill_id):
            raise MatrixError(f"unsafe skill id in skills-index: {skill_id!r}")
        if skill_id in result:
            raise MatrixError(f"duplicate skill id in skills-index: {skill_id}")
        status = _nonempty_string(entry.get("status"), f"skills-index::{skill_id}.status")
        knowledge_only = entry.get("knowledge_only", False)
        if not isinstance(knowledge_only, bool):
            raise MatrixError(f"skills-index::{skill_id}.knowledge_only must be a boolean")
        result[skill_id] = SkillMetadata(status=status, knowledge_only=knowledge_only)
    return result


def load_policy(root: Path = ROOT, *, today: date | None = None) -> TestPolicy:
    today = date.today() if today is None else today
    payload = _mapping(_load_yaml(root / POLICY_PATH, str(POLICY_PATH)), str(POLICY_PATH))
    _strict_keys(
        payload,
        required={
            "schema_version",
            "aggregate_coverage",
            "coverage",
            "allowed_failures",
            "matrix",
        },
        context=str(POLICY_PATH),
    )
    if payload["schema_version"] != 1:
        raise MatrixError(f"{POLICY_PATH}.schema_version must be 1")

    aggregate = _mapping(payload["aggregate_coverage"], "aggregate_coverage")
    _strict_keys(aggregate, required={"target", "waiver"}, context="aggregate_coverage")
    aggregate_target = _bounded_int(
        aggregate["target"], "aggregate_coverage.target", minimum=1, maximum=100
    )
    aggregate_waiver = (
        None
        if aggregate["waiver"] is None
        else _coverage_waiver(aggregate["waiver"], "aggregate_coverage.waiver", today)
    )
    if aggregate_waiver is not None and aggregate_waiver.target != aggregate_target:
        raise MatrixError("aggregate coverage waiver target does not match aggregate target")

    coverage = _mapping(payload["coverage"], "coverage")
    _strict_keys(
        coverage,
        required={"default_target", "tiers", "waivers"},
        context="coverage",
    )
    default_target = _bounded_int(
        coverage["default_target"], "coverage.default_target", minimum=1, maximum=100
    )
    tier_targets: dict[str, int] = {}
    tiers = _mapping(coverage["tiers"], "coverage.tiers")
    for tier_name, raw_tier in tiers.items():
        if not isinstance(tier_name, str) or not ID_RE.fullmatch(tier_name):
            raise MatrixError(f"unsafe coverage tier name: {tier_name!r}")
        tier = _mapping(raw_tier, f"coverage.tiers.{tier_name}")
        _strict_keys(
            tier,
            required={"target", "skills"},
            context=f"coverage.tiers.{tier_name}",
        )
        target = _bounded_int(
            tier["target"], f"coverage.tiers.{tier_name}.target", minimum=1, maximum=100
        )
        for skill_id in _string_list(tier["skills"], f"coverage.tiers.{tier_name}.skills"):
            if not ID_RE.fullmatch(skill_id):
                raise MatrixError(f"unsafe skill id in coverage tier: {skill_id!r}")
            if skill_id in tier_targets:
                raise MatrixError(f"skill appears in multiple coverage tiers: {skill_id}")
            tier_targets[skill_id] = target

    coverage_waivers: dict[str, CoverageWaiver] = {}
    for skill_id, raw_waiver in _mapping(coverage["waivers"], "coverage.waivers").items():
        if not isinstance(skill_id, str) or not ID_RE.fullmatch(skill_id):
            raise MatrixError(f"unsafe coverage waiver skill id: {skill_id!r}")
        coverage_waivers[skill_id] = _coverage_waiver(
            raw_waiver, f"coverage.waivers.{skill_id}", today
        )

    allowed_failures: dict[str, DatedException] = {}
    for skill_id, raw_exception in _mapping(
        payload["allowed_failures"], "allowed_failures"
    ).items():
        if not isinstance(skill_id, str) or not ID_RE.fullmatch(skill_id):
            raise MatrixError(f"unsafe allowed-failure skill id: {skill_id!r}")
        allowed_failures[skill_id] = _dated_exception(
            raw_exception, f"allowed_failures.{skill_id}", today
        )

    matrix_overrides: dict[str, dict[str, object]] = {}
    for entry_id, raw_override in _mapping(payload["matrix"], "matrix").items():
        if not isinstance(entry_id, str) or not ID_RE.fullmatch(entry_id):
            raise MatrixError(f"unsafe matrix id: {entry_id!r}")
        override = _mapping(raw_override, f"matrix.{entry_id}")
        _strict_keys(
            override,
            required={"reason"},
            optional={"test_paths", "requirements"},
            context=f"matrix.{entry_id}",
        )
        parsed: dict[str, object] = {
            "reason": _nonempty_string(override["reason"], f"matrix.{entry_id}.reason")
        }
        for field in ("test_paths", "requirements"):
            if field in override:
                parsed[field] = _string_list(override[field], f"matrix.{entry_id}.{field}")
        matrix_overrides[entry_id] = parsed

    policy = TestPolicy(
        aggregate_target=aggregate_target,
        aggregate_waiver=aggregate_waiver,
        default_target=default_target,
        tier_targets=tier_targets,
        coverage_waivers=coverage_waivers,
        allowed_failures=allowed_failures,
        matrix_overrides=matrix_overrides,
    )
    for skill_id, waiver in coverage_waivers.items():
        if waiver.target != policy.target_for(skill_id):
            raise MatrixError(f"coverage waiver target mismatch for {skill_id}")
    return policy


def _has_tests(path: Path) -> bool:
    return path.is_dir() and any(candidate.is_file() for candidate in path.glob("test_*.py"))


def executable_test_inventory(root: Path = ROOT) -> dict[str, bool]:
    """Return canonical-test presence for every skill with executable Python code."""
    skills_dir = root / "skills"
    if not skills_dir.is_dir():
        raise MatrixError(f"skills directory is missing: {skills_dir}")
    inventory: dict[str, bool] = {}
    for skill_dir in sorted(path for path in skills_dir.iterdir() if path.is_dir()):
        skill_id = skill_dir.name
        if not ID_RE.fullmatch(skill_id):
            raise MatrixError(f"unsafe skill id: {skill_id!r}")
        scripts_dir = skill_dir / "scripts"
        executable_scripts = tuple(
            path
            for path in sorted(scripts_dir.rglob("*.py"))
            if path.is_file()
            and path.name != "__init__.py"
            and "tests" not in path.relative_to(scripts_dir).parts
        )
        if not executable_scripts:
            continue
        inventory[skill_id] = any(
            _has_tests(skill_dir / relative) for relative in (Path("scripts/tests"), Path("tests"))
        )
    return inventory


def validate_executable_test_coverage(
    root: Path = ROOT, metadata: dict[str, SkillMetadata] | None = None
) -> dict[str, bool]:
    """Fail closed on missing tests or inconsistent knowledge-only metadata."""
    metadata = load_skill_metadata(root) if metadata is None else metadata
    inventory = executable_test_inventory(root)
    unknown = sorted(set(inventory) - set(metadata))
    if unknown:
        raise MatrixError("executable skills missing from skills-index: " + ", ".join(unknown))
    missing = sorted(skill_id for skill_id, has_tests in inventory.items() if not has_tests)
    if missing:
        raise MatrixError(
            "skills with executable scripts lack canonical tests: " + ", ".join(missing)
        )
    invalid_knowledge = sorted(
        skill_id
        for skill_id, item in metadata.items()
        if item.knowledge_only and (item.status != "production" or skill_id in inventory)
    )
    if invalid_knowledge:
        raise MatrixError(
            "knowledge_only must identify script-free production skills: "
            + ", ".join(invalid_knowledge)
        )
    unclassified = sorted(
        skill_id
        for skill_id, item in metadata.items()
        if item.status == "production" and skill_id not in inventory and not item.knowledge_only
    )
    if unclassified:
        raise MatrixError(
            "script-free production skills must set knowledge_only: true: "
            + ", ".join(unclassified)
        )
    return inventory


def discover(root: Path = ROOT) -> dict[str, TestEntry]:
    """Return canonical direct-layout test entries from the filesystem."""
    entries: dict[str, TestEntry] = {}
    skills_dir = root / "skills"
    if skills_dir.is_dir():
        for skill_dir in sorted(path for path in skills_dir.iterdir() if path.is_dir()):
            paths = []
            for relative in (Path("scripts/tests"), Path("tests")):
                candidate = skill_dir / relative
                if _has_tests(candidate):
                    paths.append(candidate.relative_to(root).as_posix())
            if paths:
                skill_id = skill_dir.name
                entries[skill_id] = TestEntry(
                    id=skill_id,
                    test_paths=tuple(paths),
                    coverage_source=f"skills/{skill_id}/scripts",
                )

    repo_tests = root / "scripts/tests"
    if _has_tests(repo_tests):
        entries["repo-scripts"] = TestEntry(
            id="repo-scripts",
            test_paths=("scripts/tests",),
            coverage_source="scripts",
        )
    return entries


def _signature(entry: TestEntry) -> str:
    payload = {
        "id": entry.id,
        "test_paths": entry.test_paths,
        "coverage_source": entry.coverage_source,
        "requirements": entry.requirements,
        "allowed_failure": entry.allowed_failure,
        "allowed_failure_policy": (
            entry.allowed_failure_policy.as_dict() if entry.allowed_failure_policy else None
        ),
        "coverage_target": entry.coverage_target,
        "coverage_floor": entry.coverage_floor,
        "coverage_waiver": entry.coverage_waiver.as_dict() if entry.coverage_waiver else None,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_entries(
    root: Path = ROOT,
    policy: TestPolicy | None = None,
    metadata: dict[str, SkillMetadata] | None = None,
) -> dict[str, TestEntry]:
    """Apply the versioned policy and fail if discovery is not fully covered."""
    policy = load_policy(root) if policy is None else policy
    metadata = load_skill_metadata(root) if metadata is None else metadata
    inventory = validate_executable_test_coverage(root, metadata)
    discovered = discover(root)

    for label, configured, valid in (
        ("matrix", set(policy.matrix_overrides), set(discovered)),
        ("allowed failure", set(policy.allowed_failures), set(discovered)),
        ("coverage waiver", set(policy.coverage_waivers), set(inventory)),
        ("coverage tier", set(policy.tier_targets), set(inventory)),
    ):
        unknown = sorted(configured - valid)
        if unknown:
            raise MatrixError(f"{label} references unknown ids: {', '.join(unknown)}")

    uncovered = sorted(set(inventory) - set(discovered))
    if uncovered:
        raise MatrixError(
            "executable skills are absent from the test matrix: " + ", ".join(uncovered)
        )

    result: dict[str, TestEntry] = {}
    for entry_id, base in discovered.items():
        if not ID_RE.fullmatch(entry_id):
            raise MatrixError(f"unsafe test id: {entry_id!r}")
        override = policy.matrix_overrides.get(entry_id, {})
        test_paths = tuple(override.get("test_paths", base.test_paths))
        requirements = tuple(override.get("requirements", ()))
        for rel_path in test_paths:
            path = root / rel_path
            if not path.is_file() and not _has_tests(path):
                raise MatrixError(f"invalid test path for {entry_id}: {rel_path}")
            if root.resolve() not in path.resolve().parents:
                raise MatrixError(f"test path escapes repository for {entry_id}: {rel_path}")
        for requirement in requirements:
            try:
                parsed_requirement = Requirement(requirement)
            except InvalidRequirement as exc:
                raise MatrixError(f"unsafe requirement for {entry_id}: {requirement!r}") from exc
            if parsed_requirement.url is not None:
                raise MatrixError(f"unsafe requirement for {entry_id}: {requirement!r}")

        target = policy.target_for(entry_id) if entry_id in inventory else None
        waiver = policy.coverage_waivers.get(entry_id)
        floor = waiver.floor if waiver is not None else target
        allowed_policy = policy.allowed_failures.get(entry_id)
        entry = replace(
            base,
            test_paths=test_paths,
            requirements=requirements,
            allowed_failure=allowed_policy is not None,
            allowed_failure_policy=allowed_policy,
            coverage_target=target,
            coverage_floor=floor,
            coverage_waiver=waiver,
            reason=override.get("reason") if isinstance(override.get("reason"), str) else None,
        )
        result[entry_id] = replace(entry, policy_signature=_signature(entry))

    if not result:
        raise MatrixError("no test suites discovered")
    return result


def matrix(entries: dict[str, TestEntry]) -> dict[str, list[dict[str, object]]]:
    return {
        "include": [
            {"id": entry.id, "allowed_failure": entry.allowed_failure} for entry in entries.values()
        ]
    }


def install(entry: TestEntry, *, check: bool = False) -> None:
    if check:
        for raw in entry.requirements:
            requirement = Requirement(raw)
            if requirement.marker is not None and not requirement.marker.evaluate():
                continue
            if requirement.url or requirement.extras:
                raise MatrixError(f"cannot verify installed requirement: {raw}")
            try:
                installed = metadata.version(requirement.name)
            except metadata.PackageNotFoundError as exc:
                raise MatrixError(f"locked environment missing requirement: {raw}") from exc
            if installed not in requirement.specifier:
                raise MatrixError(
                    f"locked environment has {requirement.name}=={installed}, needs {raw}"
                )
        return
    if entry.requirements:
        uv = shutil.which("uv")
        command = (
            [uv, "pip", "install", "--python", sys.executable, "--", *entry.requirements]
            if uv
            else [sys.executable, "-m", "pip", "install", "--", *entry.requirements]
        )
        subprocess.run(command, check=True)


def run(entry: TestEntry, root: Path, coverage_dir: Path | None) -> int:
    command = [sys.executable, "-m", "pytest", *entry.test_paths, "--tb=short", "-q"]
    manifest = None
    coverage_file = None
    if coverage_dir is not None:
        coverage_dir.mkdir(parents=True, exist_ok=True)
        coverage_file = coverage_dir / f"coverage.{entry.id}"
        manifest = coverage_dir / f"manifest.{entry.id}.json"
        env = {**os.environ, "COVERAGE_FILE": str(coverage_file)}
        command.extend([f"--cov={entry.coverage_source}", "--cov-report=", "--cov-fail-under=0"])
    else:
        env = None

    completed = subprocess.run(command, cwd=root, env=env, check=False)
    if manifest is not None and coverage_file is not None:
        manifest.write_text(
            json.dumps(
                {
                    "id": entry.id,
                    "allowed_failure": entry.allowed_failure,
                    "coverage_created": coverage_file.is_file(),
                    "coverage_floor": entry.coverage_floor,
                    "coverage_target": entry.coverage_target,
                    "policy_signature": entry.policy_signature,
                    "test_exit": completed.returncode,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return completed.returncode


def _coverage_percent(data_file: Path, output_json: Path, root: Path) -> float:
    env = {**os.environ, "COVERAGE_FILE": str(data_file)}
    subprocess.run(
        [
            sys.executable,
            "-m",
            "coverage",
            "json",
            "--omit=*/tests/*",
            "--fail-under=0",
            "-o",
            str(output_json),
        ],
        cwd=root,
        env=env,
        check=True,
    )
    try:
        payload = json.loads(output_json.read_text(encoding="utf-8"))
        value = payload["totals"]["percent_covered"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise MatrixError(f"invalid coverage JSON: {output_json}") from exc
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MatrixError(f"invalid coverage percentage: {output_json}")
    return float(value)


def _waiver_payload(waiver: CoverageWaiver | None) -> dict[str, object] | None:
    return waiver.as_dict() if waiver is not None else None


def _write_reports(
    output: Path,
    *,
    today: date,
    aggregate_row: dict[str, object],
    skill_rows: list[dict[str, object]],
    skipped_allowed_failures: list[str],
    violations: list[str],
) -> None:
    summary = {
        "schema_version": 1,
        "generated_on": today.isoformat(),
        "scope": "executable skill and repository scripts, excluding */tests/*",
        "aggregate": aggregate_row,
        "skills": skill_rows,
        "skipped_allowed_failures": skipped_allowed_failures,
        "violations": violations,
    }
    (output / "per-skill-coverage.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        "# Executable-code coverage policy report",
        "",
        f"Generated: {today.isoformat()}",
        "",
        "Tests under `*/tests/*` are excluded from every percentage.",
        "",
        "## Repository aggregate",
        "",
        "| Actual | Effective floor | Target | Status | Waiver |",
        "|---:|---:|---:|---|---|",
        f"| {_format_percent(aggregate_row['actual'])} | "
        f"{aggregate_row['effective_floor']}% | {aggregate_row['target']}% | "
        f"{aggregate_row['status']} | {_format_exception(aggregate_row.get('waiver'))} |",
        "",
        "## Per-skill coverage",
        "",
        "| Skill | Actual | Effective floor | Target | Status | Coverage waiver | Test waiver |",
        "|---|---:|---:|---:|---|---|---|",
    ]
    for row in skill_rows:
        lines.append(
            f"| {row['id']} | {_format_percent(row['actual'])} | {row['effective_floor']}% | "
            f"{row['target']}% | {row['status']} | {_format_exception(row.get('waiver'))} | "
            f"{_format_exception(row.get('allowed_failure'))} |"
        )
    if skipped_allowed_failures:
        lines.extend(
            [
                "",
                "## Skipped allowed failures",
                "",
                *[f"- {entry_id}" for entry_id in skipped_allowed_failures],
            ]
        )
    if violations:
        lines.extend(["", "## Violations", "", *[f"- {item}" for item in violations]])
    (output / "per-skill-coverage.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_percent(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "-"
    return f"{value:.2f}%"


def _format_exception(value: object) -> str:
    if not isinstance(value, dict):
        return "-"
    return f"#{value['issue']} until {value['expires_on']}"


def aggregate(
    entries: dict[str, TestEntry],
    policy: TestPolicy,
    artifacts: Path,
    output: Path,
    *,
    root: Path = ROOT,
    today: date | None = None,
) -> int:
    today = date.today() if today is None else today
    manifests: dict[str, dict[str, object]] = {}
    for path in artifacts.rglob("manifest.*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        entry_id = payload.get("id")
        if not isinstance(entry_id, str) or entry_id in manifests:
            raise MatrixError(f"invalid or duplicate manifest: {path}")
        if path.name != f"manifest.{entry_id}.json":
            raise MatrixError(f"manifest filename/id mismatch: {path}")
        manifests[entry_id] = payload

    unexpected = sorted(set(manifests) - set(entries))
    if unexpected:
        raise MatrixError(f"unexpected manifests: {', '.join(unexpected)}")

    coverage_paths: list[Path] = []
    per_entry_coverage: dict[str, Path] = {}
    blocking_errors: list[str] = []
    skipped_allowed_failures: list[str] = []
    for entry_id, entry in entries.items():
        payload = manifests.get(entry_id)
        matching_coverage = list(artifacts.rglob(f"coverage.{entry_id}"))
        if len(matching_coverage) > 1:
            raise MatrixError(f"duplicate coverage data for {entry_id}")
        coverage_path = matching_coverage[0] if matching_coverage else None
        if payload is not None:
            required = {
                "id",
                "allowed_failure",
                "coverage_created",
                "coverage_floor",
                "coverage_target",
                "policy_signature",
                "test_exit",
            }
            if set(payload) != required:
                raise MatrixError(f"invalid manifest fields for {entry_id}")
            if not isinstance(payload["allowed_failure"], bool) or not isinstance(
                payload["coverage_created"], bool
            ):
                raise MatrixError(f"invalid manifest booleans for {entry_id}")
            if not isinstance(payload["test_exit"], int) or isinstance(payload["test_exit"], bool):
                raise MatrixError(f"invalid test exit for {entry_id}")
            expected_policy = {
                "allowed_failure": entry.allowed_failure,
                "coverage_floor": entry.coverage_floor,
                "coverage_target": entry.coverage_target,
                "policy_signature": entry.policy_signature,
            }
            for field, expected_value in expected_policy.items():
                if payload[field] != expected_value:
                    raise MatrixError(f"{field.replace('_', '-')} mismatch for {entry_id}")
            if payload["coverage_created"] != (coverage_path is not None):
                raise MatrixError(f"coverage manifest mismatch for {entry_id}")
            if payload["test_exit"] != 0:
                if entry.allowed_failure:
                    print(
                        f"WARNING: skipping failed allowed-failure row {entry_id}", file=sys.stderr
                    )
                    skipped_allowed_failures.append(entry_id)
                else:
                    blocking_errors.append(f"{entry_id} (tests failed)")
                continue

        missing = payload is None or coverage_path is None
        if missing and entry.allowed_failure:
            print(f"WARNING: allowed-failure row {entry_id} produced no coverage", file=sys.stderr)
            skipped_allowed_failures.append(entry_id)
            continue
        if missing:
            blocking_errors.append(entry_id)
            continue
        coverage_paths.append(coverage_path)
        per_entry_coverage[entry_id] = coverage_path
    if blocking_errors:
        raise MatrixError(
            f"blocking rows missing manifests or coverage: {', '.join(blocking_errors)}"
        )

    output.mkdir(parents=True, exist_ok=True)
    raw_dir = output / "raw"
    raw_dir.mkdir(exist_ok=True)
    combined_file = output / "coverage"
    if coverage_paths:
        env = {**os.environ, "COVERAGE_FILE": str(combined_file)}
        subprocess.run(
            [sys.executable, "-m", "coverage", "combine", "--keep", *map(str, coverage_paths)],
            cwd=root,
            env=env,
            check=True,
        )

    violations: list[str] = []
    skill_rows: list[dict[str, object]] = []
    for entry_id, entry in entries.items():
        if entry.coverage_target is None:
            continue
        if entry_id in skipped_allowed_failures:
            skill_rows.append(
                {
                    "id": entry_id,
                    "actual": None,
                    "effective_floor": entry.coverage_floor,
                    "target": entry.coverage_target,
                    "status": "allowed_failure",
                    "waiver": _waiver_payload(entry.coverage_waiver),
                    "allowed_failure": (
                        entry.allowed_failure_policy.as_dict()
                        if entry.allowed_failure_policy is not None
                        else None
                    ),
                }
            )
            continue
        actual = _coverage_percent(per_entry_coverage[entry_id], raw_dir / f"{entry_id}.json", root)
        if entry.coverage_floor is None:
            raise MatrixError(f"coverage floor missing for executable skill: {entry_id}")
        if actual + 1e-9 < entry.coverage_floor:
            status = "floor_failed"
            violations.append(
                f"{entry_id}: {actual:.2f}% is below {entry.coverage_floor}% effective floor"
            )
        elif actual + 1e-9 >= entry.coverage_target:
            status = "target_met"
        else:
            status = "waiver_active"
        skill_rows.append(
            {
                "id": entry_id,
                "actual": actual,
                "effective_floor": entry.coverage_floor,
                "target": entry.coverage_target,
                "status": status,
                "waiver": _waiver_payload(entry.coverage_waiver),
                "allowed_failure": (
                    entry.allowed_failure_policy.as_dict()
                    if entry.allowed_failure_policy is not None
                    else None
                ),
            }
        )

    aggregate_waiver = policy.aggregate_waiver
    aggregate_floor = aggregate_waiver.floor if aggregate_waiver else policy.aggregate_target
    aggregate_actual = (
        _coverage_percent(combined_file, output / "repository-coverage.json", root)
        if coverage_paths
        else None
    )
    if skipped_allowed_failures:
        aggregate_status = "partial_allowed_failure" if coverage_paths else "not_measured"
    elif aggregate_actual is None:
        raise MatrixError("no coverage data available to combine")
    elif aggregate_actual + 1e-9 < aggregate_floor:
        aggregate_status = "floor_failed"
        violations.append(
            f"repository: {aggregate_actual:.2f}% is below {aggregate_floor}% effective floor"
        )
    elif aggregate_actual + 1e-9 >= policy.aggregate_target:
        aggregate_status = "target_met"
    else:
        aggregate_status = "waiver_active"
    aggregate_row: dict[str, object] = {
        "actual": aggregate_actual,
        "effective_floor": aggregate_floor,
        "target": policy.aggregate_target,
        "status": aggregate_status,
        "waiver": _waiver_payload(aggregate_waiver),
    }
    _write_reports(
        output,
        today=today,
        aggregate_row=aggregate_row,
        skill_rows=skill_rows,
        skipped_allowed_failures=skipped_allowed_failures,
        violations=violations,
    )
    for violation in violations:
        print(f"ERROR: {violation}", file=sys.stderr)
    return 1 if violations else 0


def _entry(entries: dict[str, TestEntry], entry_id: str) -> TestEntry:
    try:
        return entries[entry_id]
    except KeyError as exc:
        raise MatrixError(f"unknown test id: {entry_id}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("matrix")
    subparsers.add_parser("list")
    allowed_parser = subparsers.add_parser("allowed-failure")
    allowed_parser.add_argument("id")
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("id")
    install_parser.add_argument("--check", action="store_true", help="verify without installing")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("id")
    run_parser.add_argument("--coverage-dir", type=Path)
    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("--artifacts", type=Path, required=True)
    aggregate_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        policy = load_policy(ROOT)
        metadata = load_skill_metadata(ROOT)
        entries = build_entries(ROOT, policy, metadata)
        if args.command == "matrix":
            print(json.dumps(matrix(entries), separators=(",", ":")))
        elif args.command == "list":
            for entry in entries.values():
                print(entry.id)
        elif args.command == "allowed-failure":
            return 0 if _entry(entries, args.id).allowed_failure else 1
        elif args.command == "install":
            install(_entry(entries, args.id), check=args.check)
        elif args.command == "run":
            return run(_entry(entries, args.id), ROOT, args.coverage_dir)
        elif args.command == "aggregate":
            return aggregate(entries, policy, args.artifacts, args.output)
    except (MatrixError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        if args.command == "matrix":
            # ci.yml captures this command inside echo, masking its exit status.
            # A blocking fallback row makes the following direct invocation fail.
            print(
                json.dumps(
                    {"include": [{"id": POLICY_GATE_ID, "allowed_failure": False}]},
                    separators=(",", ":"),
                )
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
