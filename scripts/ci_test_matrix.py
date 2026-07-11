#!/usr/bin/env python3
"""Discover and run skill tests without hand-maintained CI test steps."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class TestEntry:
    __test__ = False

    id: str
    test_paths: tuple[str, ...]
    coverage_target: str
    requirements: tuple[str, ...] = ()
    allowed_failure: bool = False
    excluded: bool = False
    reason: str | None = None


# Only existing exceptions belong here. Newly discovered skills use the default policy.
POLICY = {
    "canslim-screener": {
        "test_paths": (
            "skills/canslim-screener/scripts/tests/test_fmp_fallback.py",
            "skills/canslim-screener/scripts/tests/test_fmp_stable_migration.py",
            "skills/canslim-screener/scripts/tests/test_institutional_fallback.py",
        ),
        "requirements": ("beautifulsoup4", "lxml"),
        "reason": "Preserve the existing CI FMP contract subset and optional dependencies.",
    },
    "pair-trade-screener": {
        "excluded": True,
        "reason": "Known optional statsmodels dependency; preserved as a covered exclusion.",
    },
    "theme-detector": {
        "requirements": ("pandas", "numpy"),
        "allowed_failure": True,
        "reason": "Preserve the existing non-blocking known-failure CI contract.",
    },
}


class MatrixError(ValueError):
    """Raised when discovered tests and policy do not form a closed matrix."""


def _has_tests(path: Path) -> bool:
    return path.is_dir() and any(path.glob("test_*.py"))


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
                    coverage_target=f"skills/{skill_id}/scripts",
                )

    repo_tests = root / "scripts/tests"
    if _has_tests(repo_tests):
        entries["repo-scripts"] = TestEntry(
            id="repo-scripts",
            test_paths=("scripts/tests",),
            coverage_target="scripts",
        )
    return entries


def build_entries(
    root: Path = ROOT, policy: dict[str, dict[str, object]] | None = None
) -> dict[str, TestEntry]:
    """Apply the explicit policy and fail if any discovered entry is uncovered."""
    discovered = discover(root)
    policy = POLICY if policy is None else policy
    unknown = sorted(set(policy) - set(discovered))
    if unknown:
        raise MatrixError(f"policy references undiscovered test ids: {', '.join(unknown)}")

    result: dict[str, TestEntry] = {}
    for entry_id, base in discovered.items():
        if not ID_RE.fullmatch(entry_id):
            raise MatrixError(f"unsafe test id: {entry_id!r}")
        override = policy.get(entry_id, {})
        allowed_keys = {"test_paths", "requirements", "allowed_failure", "excluded", "reason"}
        extra = set(override) - allowed_keys
        if extra:
            raise MatrixError(f"unknown policy keys for {entry_id}: {sorted(extra)}")
        entry = replace(
            base,
            test_paths=tuple(override.get("test_paths", base.test_paths)),
            requirements=tuple(override.get("requirements", ())),
            allowed_failure=bool(override.get("allowed_failure", False)),
            excluded=bool(override.get("excluded", False)),
            reason=override.get("reason") if isinstance(override.get("reason"), str) else None,
        )
        if (
            entry.allowed_failure or entry.excluded or entry.test_paths != base.test_paths
        ) and not entry.reason:
            raise MatrixError(f"exception policy for {entry_id} requires a reason")
        if entry.allowed_failure and entry.excluded:
            raise MatrixError(f"{entry_id} cannot be both allowed_failure and excluded")
        if not entry.test_paths:
            raise MatrixError(f"{entry_id} has no covered test paths")
        for rel_path in entry.test_paths:
            path = root / rel_path
            if not path.exists() or root not in path.resolve().parents:
                raise MatrixError(f"invalid test path for {entry_id}: {rel_path}")
        for requirement in entry.requirements:
            if not requirement or requirement.startswith("-") or re.search(r"\s", requirement):
                raise MatrixError(f"unsafe requirement for {entry_id}: {requirement!r}")
        result[entry_id] = entry

    if not result:
        raise MatrixError("no test suites discovered")
    if set(result) != set(discovered):
        missing = sorted(set(discovered) - set(result))
        raise MatrixError(f"discovered tests are not covered: {', '.join(missing)}")
    if not any(not entry.excluded for entry in result.values()):
        raise MatrixError("matrix has no runnable test suites")
    return result


def matrix(entries: dict[str, TestEntry]) -> dict[str, list[dict[str, object]]]:
    rows = [
        {"id": entry.id, "allowed_failure": entry.allowed_failure}
        for entry in entries.values()
        if not entry.excluded
    ]
    return {"include": rows}


def install(entry: TestEntry) -> None:
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
    if coverage_dir is not None:
        coverage_dir.mkdir(parents=True, exist_ok=True)
        coverage_file = coverage_dir / f"coverage.{entry.id}"
        manifest = coverage_dir / f"manifest.{entry.id}.json"
        env = {**os.environ, "COVERAGE_FILE": str(coverage_file)}
        command.extend([f"--cov={entry.coverage_target}", "--cov-report=", "--cov-fail-under=0"])
    else:
        env = None

    completed = subprocess.run(command, cwd=root, env=env, check=False)
    if manifest is not None:
        coverage_file = coverage_dir / f"coverage.{entry.id}"
        manifest.write_text(
            json.dumps(
                {
                    "id": entry.id,
                    "allowed_failure": entry.allowed_failure,
                    "test_exit": completed.returncode,
                    "coverage_created": coverage_file.is_file(),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return completed.returncode


def aggregate(entries: dict[str, TestEntry], artifacts: Path, output: Path) -> int:
    expected = {entry.id: entry for entry in entries.values() if not entry.excluded}
    manifests: dict[str, dict[str, object]] = {}
    for path in artifacts.rglob("manifest.*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        entry_id = payload.get("id")
        if not isinstance(entry_id, str) or entry_id in manifests:
            raise MatrixError(f"invalid or duplicate manifest: {path}")
        if path.name != f"manifest.{entry_id}.json":
            raise MatrixError(f"manifest filename/id mismatch: {path}")
        manifests[entry_id] = payload

    unexpected = sorted(set(manifests) - set(expected))
    if unexpected:
        raise MatrixError(f"unexpected manifests: {', '.join(unexpected)}")

    coverage_paths = []
    blocking_errors = []
    for entry_id, entry in expected.items():
        payload = manifests.get(entry_id)
        matching_coverage = list(artifacts.rglob(f"coverage.{entry_id}"))
        if len(matching_coverage) > 1:
            raise MatrixError(f"duplicate coverage data for {entry_id}")
        coverage_path = matching_coverage[0] if matching_coverage else None
        if payload is not None:
            required = {"id", "allowed_failure", "test_exit", "coverage_created"}
            if set(payload) != required:
                raise MatrixError(f"invalid manifest fields for {entry_id}")
            if not isinstance(payload["allowed_failure"], bool) or not isinstance(
                payload["coverage_created"], bool
            ):
                raise MatrixError(f"invalid manifest booleans for {entry_id}")
            if not isinstance(payload["test_exit"], int) or isinstance(payload["test_exit"], bool):
                raise MatrixError(f"invalid test exit for {entry_id}")
            if payload["allowed_failure"] != entry.allowed_failure:
                raise MatrixError(f"allowed-failure mismatch for {entry_id}")
            if payload["coverage_created"] != (coverage_path is not None):
                raise MatrixError(f"coverage manifest mismatch for {entry_id}")
            if payload["test_exit"] != 0 and not entry.allowed_failure:
                blocking_errors.append(f"{entry_id} (tests failed)")
                continue

        missing = payload is None or coverage_path is None
        if missing and entry.allowed_failure:
            print(f"WARNING: allowed-failure row {entry_id} produced no coverage", file=sys.stderr)
            continue
        if missing:
            blocking_errors.append(entry_id)
            continue
        coverage_paths.append(coverage_path)
    if blocking_errors:
        raise MatrixError(
            f"blocking rows missing manifests or coverage: {', '.join(blocking_errors)}"
        )
    if not coverage_paths:
        raise MatrixError("no coverage data available to combine")

    output.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "COVERAGE_FILE": str(output / "coverage")}
    subprocess.run(
        [sys.executable, "-m", "coverage", "combine", *map(str, coverage_paths)],
        cwd=ROOT,
        env=env,
        check=True,
    )
    return subprocess.run(
        [sys.executable, "-m", "coverage", "report", "--fail-under=40"],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode


def _entry(entries: dict[str, TestEntry], entry_id: str) -> TestEntry:
    try:
        entry = entries[entry_id]
    except KeyError as exc:
        raise MatrixError(f"unknown test id: {entry_id}") from exc
    if entry.excluded:
        raise MatrixError(f"test id is a covered exclusion: {entry_id} ({entry.reason})")
    return entry


def _print_local_summary(entries: Iterable[TestEntry]) -> None:
    excluded = [entry for entry in entries if entry.excluded]
    if excluded:
        print("Covered exclusions:")
        for entry in excluded:
            print(f"  {entry.id}: {entry.reason}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("matrix")
    subparsers.add_parser("list")
    allowed_parser = subparsers.add_parser("allowed-failure")
    allowed_parser.add_argument("id")
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("id")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("id")
    run_parser.add_argument("--coverage-dir", type=Path)
    aggregate_parser = subparsers.add_parser("aggregate")
    aggregate_parser.add_argument("--artifacts", type=Path, required=True)
    aggregate_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        entries = build_entries()
        if args.command == "matrix":
            print(json.dumps(matrix(entries), separators=(",", ":")))
        elif args.command == "list":
            for entry in entries.values():
                if not entry.excluded:
                    print(entry.id)
            _print_local_summary(entries.values())
        elif args.command == "allowed-failure":
            return 0 if _entry(entries, args.id).allowed_failure else 1
        elif args.command == "install":
            install(_entry(entries, args.id))
        elif args.command == "run":
            return run(_entry(entries, args.id), ROOT, args.coverage_dir)
        elif args.command == "aggregate":
            return aggregate(entries, args.artifacts, args.output)
    except (MatrixError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
