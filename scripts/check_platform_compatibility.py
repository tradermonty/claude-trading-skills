#!/usr/bin/env python3
"""Validate and exercise the repository's supported platform contract."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version
from yaml.resolver import BaseResolver

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("config/platform-compatibility.yaml")
DOC_PATHS = (
    Path("docs/dev/platform-support.md"),
    Path("docs/dev/platform-support.ja.md"),
)
PLATFORM_NAMES = {"linux": "linux", "win32": "windows", "darwin": "macos"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DOC_ROW_RE = re.compile(
    r"^\|\s*`(?P<id>[a-z0-9][a-z0-9-]*)`\s*"
    r"\|\s*`(?P<runner>[^`]+)`\s*"
    r"\|\s*(?P<python>3\.\d+)\s*"
    r"\|\s*(?P<pull_request>yes|no)\s*"
    r"\|\s*(?P<nightly>yes|no)\s*\|"
)


class CompatibilityError(ValueError):
    """Raised when the platform policy or current runtime is unsupported."""


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
            raise CompatibilityError(f"unhashable YAML key: {key!r}") from exc
        if duplicate:
            raise CompatibilityError(f"duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


@dataclass(frozen=True)
class MatrixRow:
    id: str
    platform: str
    runner: str
    python: str


@dataclass(frozen=True)
class CompatibilityPolicy:
    python_implementation: str
    python_requires: str
    best_effort: tuple[str, ...]
    platforms: dict[str, str]
    rows: dict[str, MatrixRow]
    profiles: dict[str, tuple[str, ...]]
    test_paths: tuple[str, ...]


def _mapping(value: object, context: str) -> dict[object, object]:
    if not isinstance(value, dict):
        raise CompatibilityError(f"{context} must be a mapping")
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
        raise CompatibilityError(f"{context} missing keys: {', '.join(missing)}")
    if unknown:
        raise CompatibilityError(f"{context} has unknown keys: {unknown}")


def _string(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompatibilityError(f"{context} must be a non-empty string")
    return value.strip()


def _string_list(value: object, context: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise CompatibilityError(f"{context} must be a non-empty list")
    result = tuple(_string(item, f"{context}[]") for item in value)
    if len(set(result)) != len(result):
        raise CompatibilityError(f"{context} contains duplicates")
    return result


def _python_minor(value: object, context: str) -> str:
    raw = _string(value, context)
    if not re.fullmatch(r"3\.\d+", raw):
        raise CompatibilityError(f"{context} must be a Python 3 minor version")
    return raw


def load_policy(root: Path = ROOT) -> CompatibilityPolicy:
    path = root / POLICY_PATH
    try:
        payload = _mapping(
            yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader),
            str(POLICY_PATH),
        )
    except (OSError, yaml.YAMLError) as exc:
        raise CompatibilityError(f"cannot load {POLICY_PATH}: {exc}") from exc
    _strict_keys(
        payload,
        required={"schema_version", "python", "platforms", "rows", "profiles", "test_paths"},
        context=str(POLICY_PATH),
    )
    if payload["schema_version"] != 1:
        raise CompatibilityError(f"{POLICY_PATH}.schema_version must be 1")

    python = _mapping(payload["python"], "python")
    _strict_keys(
        python,
        required={"implementation", "requires", "best_effort"},
        context="python",
    )
    implementation = _string(python["implementation"], "python.implementation")
    if implementation != "CPython":
        raise CompatibilityError("python.implementation must be CPython")
    requires = _string(python["requires"], "python.requires")
    try:
        specifier = SpecifierSet(requires)
    except InvalidSpecifier as exc:
        raise CompatibilityError(f"python.requires is invalid: {requires}") from exc
    best_effort = tuple(
        _python_minor(item, "python.best_effort[]")
        for item in _string_list(python["best_effort"], "python.best_effort", allow_empty=True)
    )

    raw_platforms = _mapping(payload["platforms"], "platforms")
    if set(raw_platforms) != {"linux", "windows", "macos"}:
        raise CompatibilityError("platforms must define exactly linux, windows, and macos")
    platforms: dict[str, str] = {}
    for platform, value in raw_platforms.items():
        entry = _mapping(value, f"platforms.{platform}")
        _strict_keys(entry, required={"runner"}, context=f"platforms.{platform}")
        platforms[str(platform)] = _string(entry["runner"], f"platforms.{platform}.runner")

    raw_rows = _mapping(payload["rows"], "rows")
    if not raw_rows:
        raise CompatibilityError("rows must not be empty")
    rows: dict[str, MatrixRow] = {}
    for raw_id, value in raw_rows.items():
        row_id = _string(raw_id, "rows key")
        if not ID_RE.fullmatch(row_id):
            raise CompatibilityError(f"unsafe row id: {row_id!r}")
        entry = _mapping(value, f"rows.{row_id}")
        _strict_keys(entry, required={"platform", "python"}, context=f"rows.{row_id}")
        platform = _string(entry["platform"], f"rows.{row_id}.platform")
        if platform not in platforms:
            raise CompatibilityError(f"rows.{row_id} references unknown platform: {platform}")
        python_version = _python_minor(entry["python"], f"rows.{row_id}.python")
        if Version(python_version) not in specifier:
            raise CompatibilityError(f"rows.{row_id} Python {python_version} is outside {requires}")
        rows[row_id] = MatrixRow(
            id=row_id,
            platform=platform,
            runner=platforms[platform],
            python=python_version,
        )

    raw_profiles = _mapping(payload["profiles"], "profiles")
    if set(raw_profiles) != {"pull_request", "nightly"}:
        raise CompatibilityError("profiles must define exactly pull_request and nightly")
    profiles: dict[str, tuple[str, ...]] = {}
    for profile, value in raw_profiles.items():
        ids = _string_list(value, f"profiles.{profile}")
        unknown = sorted(set(ids) - set(rows))
        if unknown:
            raise CompatibilityError(
                f"profiles.{profile} references unknown rows: {', '.join(unknown)}"
            )
        profiles[str(profile)] = ids
    if not set(profiles["pull_request"]).issubset(profiles["nightly"]):
        raise CompatibilityError("pull_request rows must be a subset of nightly rows")
    if set(rows) != set(profiles["nightly"]):
        raise CompatibilityError("nightly profile must exercise every configured row")

    missing_platforms = sorted(set(platforms) - {row.platform for row in rows.values()})
    if missing_platforms:
        raise CompatibilityError(
            "compatibility rows do not exercise platforms: " + ", ".join(missing_platforms)
        )
    supported_minors = tuple(
        f"3.{minor}" for minor in range(100) if Version(f"3.{minor}") in specifier
    )
    if not supported_minors:
        raise CompatibilityError("python.requires does not include a Python 3 minor version")
    tested_versions = {row.python for row in rows.values()}
    missing_boundaries = [
        version
        for version in (supported_minors[0], supported_minors[-1])
        if version not in tested_versions
    ]
    if missing_boundaries:
        raise CompatibilityError(
            "compatibility rows do not exercise Python boundary versions: "
            + ", ".join(missing_boundaries)
        )
    if not any(row.platform == "windows" and row.python == "3.13" for row in rows.values()):
        raise CompatibilityError("compatibility rows must retain the Windows/Python 3.13 axis")

    test_paths = _string_list(payload["test_paths"], "test_paths")
    for relative in test_paths:
        path = root / relative
        if not path.exists() or root.resolve() not in path.resolve().parents:
            raise CompatibilityError(f"invalid compatibility test path: {relative}")

    overlap = sorted(set(best_effort) & tested_versions)
    if overlap:
        raise CompatibilityError(
            f"best-effort Python versions are also matrix-tested: {', '.join(overlap)}"
        )
    for version in best_effort:
        if Version(version) not in specifier:
            raise CompatibilityError(f"best-effort Python {version} is outside {requires}")

    return CompatibilityPolicy(
        python_implementation=implementation,
        python_requires=requires,
        best_effort=best_effort,
        platforms=platforms,
        rows=rows,
        profiles=profiles,
        test_paths=test_paths,
    )


def matrix(policy: CompatibilityPolicy, profile: str) -> dict[str, list[dict[str, str]]]:
    if profile not in policy.profiles:
        raise CompatibilityError(f"unknown compatibility profile: {profile}")
    paths = " ".join(policy.test_paths)
    return {
        "include": [
            {
                "id": row.id,
                "runner": row.runner,
                "platform": row.platform,
                "python_version": row.python,
                "pytest_paths": paths,
            }
            for row_id in policy.profiles[profile]
            for row in (policy.rows[row_id],)
        ]
    }


def current_platform(sys_platform: str = sys.platform) -> str:
    try:
        return PLATFORM_NAMES[sys_platform]
    except KeyError as exc:
        raise CompatibilityError(
            f"unsupported operating system {sys_platform!r}; supported: Linux, macOS, Windows"
        ) from exc


def check_runtime(
    policy: CompatibilityPolicy,
    *,
    matrix_id: str | None = None,
    sys_platform: str = sys.platform,
    version_info: tuple[int, int] | None = None,
    implementation: str | None = None,
) -> str:
    implementation = implementation or sys.implementation.name
    if implementation != "cpython":
        raise CompatibilityError(
            f"unsupported Python implementation {implementation!r}; CPython is required"
        )
    platform = current_platform(sys_platform)
    major, minor = version_info or (sys.version_info.major, sys.version_info.minor)
    version = f"{major}.{minor}"
    if Version(version) not in SpecifierSet(policy.python_requires):
        raise CompatibilityError(f"unsupported Python {version}; required {policy.python_requires}")
    if matrix_id is not None:
        try:
            row = policy.rows[matrix_id]
        except KeyError as exc:
            raise CompatibilityError(f"unknown compatibility matrix id: {matrix_id}") from exc
        if row.platform != platform or row.python != version:
            raise CompatibilityError(
                f"runtime mismatch for {matrix_id}: expected {row.platform}/Python {row.python}, "
                f"got {platform}/Python {version}"
            )
        return f"supported matrix runtime: {matrix_id}"
    if version in policy.best_effort:
        return f"supported install range (best-effort CI coverage): {platform}/Python {version}"
    return f"supported runtime: {platform}/Python {version}"


def probe_runtime() -> dict[str, str]:
    """Exercise filesystem and subprocess behavior that has regressed cross-platform."""
    with tempfile.TemporaryDirectory(prefix="cts-platform-") as temp:
        root = Path(temp) / "space ünicode"
        root.mkdir()
        text_path = root / "report 日本語.md"
        expected = "risk: guarded ✅\nsecond line\n"
        text_path.write_bytes(expected.encode("utf-8"))
        if text_path.read_text(encoding="utf-8") != expected:
            raise CompatibilityError("UTF-8/LF round trip failed")

        crlf_path = root / "windows-lines.txt"
        crlf_path.write_bytes(b"alpha\r\nbeta\r\n")
        if crlf_path.read_bytes() != b"alpha\r\nbeta\r\n":
            raise CompatibilityError("CRLF byte preservation failed")

        script = root / "argv probe.py"
        output = root / "argv result.json"
        script.write_text(
            "import json, pathlib, sys\n"
            "pathlib.Path(sys.argv[2]).write_text("
            "json.dumps(sys.argv[1], ensure_ascii=False), encoding='utf-8')\n",
            encoding="utf-8",
        )
        value = "argument with spaces;$(not-a-shell) 日本語"
        subprocess.run([sys.executable, str(script), value, str(output)], check=True)
        if json.loads(output.read_text(encoding="utf-8")) != value:
            raise CompatibilityError("argv-safe subprocess round trip failed")

        if os.name == "nt":
            executable = "not-applicable-on-windows"
        else:
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
            if not os.access(script, os.X_OK):
                raise CompatibilityError("POSIX executable-bit probe failed")
            executable = "passed"
    return {
        "utf8_lf": "passed",
        "crlf": "passed",
        "unicode_space_path": "passed",
        "argv_subprocess": "passed",
        "executable_bit": executable,
    }


def validate_repository_contract(policy: CompatibilityPolicy, root: Path = ROOT) -> None:
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^requires-python\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    if match is None or match.group(1) != policy.python_requires:
        actual = match.group(1) if match else "missing"
        raise CompatibilityError(
            f"pyproject requires-python drift: expected {policy.python_requires}, got {actual}"
        )
    lock_header = "\n".join((root / "uv.lock").read_text(encoding="utf-8").splitlines()[:5])
    if f'requires-python = "{policy.python_requires}"' not in lock_header:
        raise CompatibilityError("uv.lock requires-python does not match platform policy")

    for relative in DOC_PATHS:
        text = (root / relative).read_text(encoding="utf-8")
        if policy.python_requires not in text:
            raise CompatibilityError(f"{relative} does not document {policy.python_requires!r}")
        documented: dict[str, tuple[str, str, str, str]] = {}
        for line in text.splitlines():
            match = DOC_ROW_RE.match(line)
            if match is None:
                continue
            row_id = match.group("id")
            if row_id in documented:
                raise CompatibilityError(f"{relative} contains duplicate matrix row {row_id}")
            documented[row_id] = (
                match.group("runner"),
                match.group("python"),
                match.group("pull_request"),
                match.group("nightly"),
            )
        expected = {
            row_id: (
                row.runner,
                row.python,
                "yes" if row_id in policy.profiles["pull_request"] else "no",
                "yes" if row_id in policy.profiles["nightly"] else "no",
            )
            for row_id, row in policy.rows.items()
        }
        if documented != expected:
            raise CompatibilityError(
                f"{relative} matrix table drift: expected {expected!r}, got {documented!r}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    matrix_parser = subparsers.add_parser("matrix")
    matrix_parser.add_argument("--profile", required=True)
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--matrix-id")
    subparsers.add_parser("probe")
    subparsers.add_parser("validate")
    args = parser.parse_args(argv)

    try:
        policy = load_policy(ROOT)
        if args.command == "matrix":
            print(json.dumps(matrix(policy, args.profile), separators=(",", ":")))
        elif args.command == "check":
            print(check_runtime(policy, matrix_id=args.matrix_id))
        elif args.command == "probe":
            print(json.dumps(probe_runtime(), sort_keys=True))
        elif args.command == "validate":
            validate_repository_contract(policy, ROOT)
            print("platform compatibility policy, lock, and docs are consistent")
    except (CompatibilityError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
