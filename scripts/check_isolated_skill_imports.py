#!/usr/bin/env python3
"""Import configured skill entry modules in clean dependency environments.

The compatibility jobs use this checker to prove that each selected packaged
skill can import with only the dependencies declared in its own
``requirements.txt``. The module inventory is explicit so adding an unrelated
script with import-time side effects does not silently expand CI execution.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_skill_deps import parse_requirements  # noqa: E402

DEFAULT_CONFIG = Path("config/compat-import-smoke.json")
MODULE_RE = re.compile(r"[A-Za-z_]\w*")
SKILL_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


@dataclass(frozen=True)
class SmokePlan:
    timeout_seconds: int
    skills: dict[str, tuple[str, ...]]


def load_plan(root: Path, config_path: Path | None = None) -> tuple[SmokePlan | None, list[str]]:
    """Load and validate the explicit isolated-import inventory."""
    path = config_path or root / DEFAULT_CONFIG
    if not path.is_absolute():
        path = root / path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, [f"cannot read {path}: {exc}"]

    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, [f"{path}: root must be an object"]
    expected_keys = {"schema_version", "timeout_seconds", "skills"}
    if set(raw) != expected_keys:
        errors.append(
            f"{path}: root keys must be exactly {sorted(expected_keys)}; got {sorted(raw)}"
        )
    schema_version = raw.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != 1
    ):
        errors.append(f"{path}: schema_version must be 1")

    timeout = raw.get("timeout_seconds")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 3600:
        errors.append(f"{path}: timeout_seconds must be an integer from 1 to 3600")

    raw_skills = raw.get("skills")
    if not isinstance(raw_skills, dict) or not raw_skills:
        errors.append(f"{path}: skills must be a non-empty object")
        raw_skills = {}

    skills: dict[str, tuple[str, ...]] = {}
    for skill_id, spec in raw_skills.items():
        if not isinstance(skill_id, str) or not SKILL_RE.fullmatch(skill_id):
            errors.append(f"{path}: invalid skill id {skill_id!r}")
            continue
        if not isinstance(spec, dict) or set(spec) != {"modules"}:
            errors.append(f"{path}: {skill_id} must contain only a modules list")
            continue
        modules = spec.get("modules")
        if not isinstance(modules, list) or not modules:
            errors.append(f"{path}: {skill_id}.modules must be a non-empty list")
            continue
        if any(
            not isinstance(module, str) or not MODULE_RE.fullmatch(module) for module in modules
        ):
            errors.append(f"{path}: {skill_id}.modules contains an invalid module name")
            continue
        if len(modules) != len(set(modules)):
            errors.append(f"{path}: {skill_id}.modules contains duplicates")
            continue
        skills[skill_id] = tuple(modules)

    if errors:
        return None, errors
    assert isinstance(timeout, int)
    return SmokePlan(timeout_seconds=timeout, skills=skills), []


def _import_code(scripts_dir: Path, module: str) -> str:
    return (
        "import importlib, sys\n"
        f"sys.path.insert(0, {str(scripts_dir.resolve())!r})\n"
        f"importlib.import_module({module!r})\n"
    )


def check(
    root: Path | None = None,
    config_path: Path | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> int:
    """Run every configured module smoke and return a process exit code."""
    root = (root or ROOT).resolve()
    plan, errors = load_plan(root, config_path)
    if plan is None:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    failures: list[str] = []
    for skill_id, modules in plan.skills.items():
        skill_dir = root / "skills" / skill_id
        scripts_dir = skill_dir / "scripts"
        manifest = skill_dir / "requirements.txt"
        if not manifest.is_file():
            failures.append(f"{skill_id}: missing requirements.txt")
            continue
        entries, parse_errors = parse_requirements(manifest)
        if parse_errors:
            failures.append(f"{skill_id}: requirements parse errors: {parse_errors}")
            continue

        missing = [module for module in modules if not (scripts_dir / f"{module}.py").is_file()]
        if missing:
            failures.append(f"{skill_id}: configured modules not found: {missing}")
            continue

        with_args: list[str] = []
        for entry in entries.values():
            if not entry.optional:
                with_args.extend(["--with", entry.spec])

        for module in modules:
            command = [
                "uv",
                "run",
                "--isolated",
                "--no-project",
                *with_args,
                "python",
                "-c",
                _import_code(scripts_dir, module),
            ]
            try:
                proc = run(
                    command,
                    cwd=root,
                    capture_output=True,
                    text=True,
                    timeout=plan.timeout_seconds,
                )
            except subprocess.TimeoutExpired:
                failures.append(
                    f"{skill_id}:{module}: timed out after {plan.timeout_seconds} seconds"
                )
                print(f"FAIL {skill_id}:{module}")
                continue
            except OSError as exc:
                failures.append(f"{skill_id}:{module}: could not start uv: {exc}")
                print(f"FAIL {skill_id}:{module}")
                continue

            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "no subprocess output").strip()
                failures.append(f"{skill_id}:{module}: import failed: {detail}")
                print(f"FAIL {skill_id}:{module}")
            else:
                print(f"OK   {skill_id}:{module}")

    if failures:
        print("ISOLATED IMPORT FAILURES:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="override the import-smoke config path")
    args = parser.parse_args(argv)
    return check(config_path=args.config)


if __name__ == "__main__":
    sys.exit(main())
