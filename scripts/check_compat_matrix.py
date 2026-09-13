#!/usr/bin/env python3
"""Drift guard for the documented OS/Python compatibility matrix (issue #333).

Single source of truth is ``docs/dev/compatibility-matrix.md``. This checker
parses that document's machine-readable fenced YAML block (keyed on
``compat_matrix``) and compares it against the actual ``.github/workflows``
declarations for the compatibility-defining jobs, then validates a repository
policy over every job in those workflows.

Policy enforced (static only):
  * Every job in ``ci.yml`` and ``compat-nightly.yml`` runs on an OS in
    ``{ubuntu-latest, windows-latest, macos-latest}``.
  * Every job's Python version falls inside the supported range declared in
    ``pyproject.toml`` (``requires-python``), validated as a bounded range.
  * The ``compat-smoke`` / ``compat-nightly`` job axis sets match the matrix
    document exactly.

Runtime enforcement of an unsupported combination on the runner is explicitly
out of scope for a static checker (documented in the matrix doc).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_FILES = ("ci.yml", "compat-nightly.yml")
SUPPORTED_OS = {"ubuntu-latest", "windows-latest", "macos-latest"}
DEFAULT_REQUIRES_PYTHON = ">=3.9,<3.14"
COMPAT_JOBS = ("compat-smoke", "compat-nightly")
DOC = "docs/dev/compatibility-matrix.md"
PYPROJECT = "pyproject.toml"

# Jobs that run a third-party action and have no ``actions/setup-python`` step,
# so no Python version can be extracted; they are OS-checked only.
NO_SETUP_PYTHON_JOBS = {"dependency-review"}


@dataclass
class JobCombo:
    """A single (os, python) combination inferred for a CI job."""

    os: str
    python: str | None

    def key(self) -> tuple[str, str | None]:
        return (self.os, self.python)


@dataclass
class JobResult:
    job: str
    combos: list[JobCombo] = field(default_factory=list)
    used_matrix: bool = False


def _load_yaml_text(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _load_workflow(path: Path) -> dict:
    return _load_yaml_text(ROOT / ".github" / "workflows" / path)


def _requires_python() -> str | None:
    """Extract ``requires-python`` from pyproject.toml via regex (stdlib-safe)."""
    try:
        text = (ROOT / PYPROJECT).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    match = re.search(r'requires-python\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else None


def _validate_python_bound(value: str | None) -> tuple[str, str]:
    """Validate the requires-python bound and return (python_expr, error)."""
    if value is None:
        return "", f"{PYPROJECT} does not declare requires-python"
    lower = re.search(r">=\s*([0-9.]+)", value)
    upper = re.search(r"<\s*([0-9.]+)", value)
    if not lower or not upper:
        return "", (
            f"{PYPROJECT} requires-python='{value}' is not a bounded range (expected '>=3.9,<3.14')"
        )
    return value, ""


def _matrix_os(runs_on: str | None, matrix: dict | None, python_ver: str | None) -> list[str]:
    """Resolve the set of OS labels for a job from its matrix + runs-on."""
    if isinstance(matrix, dict) and isinstance(matrix.get("os"), list):
        return [str(x) for x in matrix["os"]]
    if runs_on:
        return [runs_on]
    return []


def _matrix_python(python_ver: str | None, matrix: dict | None) -> list[str | None]:
    """Resolve the set of Python versions for a job from its setup-python step."""
    if isinstance(matrix, dict) and isinstance(matrix.get("python"), list):
        return [str(x) for x in matrix["python"]]
    return [python_ver]


def _step_python_ver(step: dict) -> str | None:
    """Return the target Python version from an actions/setup-python step, if any."""
    if "actions/setup-python@" not in str(step.get("uses", "")):
        return None
    with_ = step.get("with", {}) or {}
    return with_.get("python-version")


def _extract_jobs(workflow: dict) -> dict[str, JobResult]:
    """Return {job_id: JobResult} for a parsed workflow."""
    results: dict[str, JobResult] = {}
    for job_id, job in workflow.get("jobs", {}).items():
        matrix = job.get("strategy", {}).get("matrix")
        runs_on = job.get("runs-on")
        python_ver = None
        for step in job.get("steps", []):
            found = _step_python_ver(step)
            if found is not None:
                python_ver = str(found)
                break
        os_list = _matrix_os(runs_on, matrix, python_ver)
        py_list = _matrix_python(python_ver, matrix)
        used_matrix = bool(isinstance(matrix, dict) and isinstance(matrix.get("os"), list))
        combos = [
            JobCombo(os=os_val, python=(py_val if not _is_expr(py_val) else None))
            for os_val in os_list
            for py_val in py_list
        ]
        results[job_id] = JobResult(job=job_id, combos=combos, used_matrix=used_matrix)
    return results


def _is_expr(value: str | None) -> bool:
    return value is not None and str(value).startswith("${{")


def _parse_doc_declared(path: Path | None = None) -> dict:
    """Parse the ``compat_matrix`` fenced YAML block from the matrix doc."""
    if path is None:
        path = ROOT / DOC
    text = (path if path.is_absolute() else ROOT / path).read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\s*\n(.*?)```", text, re.DOTALL)
    for block in blocks:
        parsed = yaml.load(block, Loader=yaml.BaseLoader)
        if isinstance(parsed, dict) and "compat_matrix" in parsed:
            return parsed["compat_matrix"]
    return {}


def _doc_header() -> dict:
    """Return the doc's top-level ``python`` / ``supported_os`` declarations."""
    declared = _parse_doc_declared()
    return {
        "python": str(declared["python"]) if "python" in declared else None,
        "supported_os": sorted(str(x) for x in declared.get("supported_os", [])),
    }


def _declared_from_doc() -> dict:
    declared = _parse_doc_declared()
    jobs = declared.get("jobs", {})
    out: dict[str, dict] = {}
    for job in COMPAT_JOBS:
        entry = jobs.get(job, {})
        out[job] = {
            "os": sorted(str(x) for x in entry.get("os", [])),
            "python": sorted(str(x) for x in entry.get("python", [])),
        }
    return out


def _actual_combo_sets(all_results: dict[str, JobResult]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for job in COMPAT_JOBS:
        if job not in all_results:
            out[job] = {"os": [], "python": []}
            continue
        result = all_results[job]
        os_set = sorted({c.os for c in result.combos if c.os})
        py_set = sorted({c.python for c in result.combos if c.python})
        out[job] = {"os": os_set, "python": py_set}
    return out


def _check_declared_workflow_match(declared: dict, actual: dict, errors: list[str]) -> None:
    for job in COMPAT_JOBS:
        if declared[job]["os"] != actual[job]["os"]:
            errors.append(
                f"{job}: documented OS {declared[job]['os']} != workflow OS {actual[job]['os']}"
            )
        if declared[job]["python"] != actual[job]["python"]:
            errors.append(
                f"{job}: documented Python {declared[job]['python']} != "
                f"workflow Python {actual[job]['python']}"
            )


def _bound_range(python_expr: str) -> tuple[str, str]:
    """Derive the (lower, upper) half-open range from a requires-python expr."""
    lower = re.search(r">=\s*([0-9.]+)", python_expr)
    upper = re.search(r"<\s*([0-9.]+)", python_expr)
    return (lower.group(1) if lower else "0", upper.group(1) if upper else "999")


def _check_os_and_python_policy(
    all_results: dict[str, JobResult], python_expr: str, errors: list[str]
) -> None:
    lower, upper = _bound_range(python_expr)
    for job_id, result in all_results.items():
        for combo in result.combos:
            if combo.os not in SUPPORTED_OS:
                errors.append(f"{job_id}: OS {combo.os!r} is outside supported set")
            if combo.python is None:
                if job_id not in NO_SETUP_PYTHON_JOBS and result.used_matrix:
                    errors.append(f"{job_id}: could not resolve a Python version")
                continue
            if not _in_range(combo.python, lower, upper):
                errors.append(
                    f"{job_id}: Python {combo.python} is outside supported range [{lower}, {upper})"
                )


def _in_range(version: str, lower: str, upper: str) -> bool:
    parts = [int(x) for x in re.findall(r"\d+", version)[:2]] or [0]
    # Normalize to a comparable (major, minor) tuple.
    major, minor = (parts + [0])[:2]
    lo = [int(x) for x in lower.split(".")]
    hi = [int(x) for x in upper.split(".")]
    v = (major, minor)
    return (lo[0], lo[1] if len(lo) > 1 else 0) <= v < (hi[0], hi[1] if len(hi) > 1 else 0)


def _load_all_results() -> dict[str, JobResult]:
    all_results: dict[str, JobResult] = {}
    for wf in WORKFLOW_FILES:
        path = ROOT / ".github" / "workflows" / wf
        if not path.exists():
            continue
        all_results.update(_extract_jobs(_load_workflow(wf)))
    return all_results


def check(quiet: bool = False, as_json: bool = False) -> int:
    errors: list[str] = []
    python_expr, bound_error = _validate_python_bound(_requires_python())
    if bound_error:
        errors.append(bound_error)

    declared = _declared_from_doc()
    if not declared or all(not v["os"] for v in declared.values()):
        errors.append(f"{DOC} missing compatible compat_matrix job mapping")

    header = _doc_header()
    if header["python"] and python_expr and header["python"] != python_expr:
        errors.append(
            f"{DOC} declares python {header['python']} but pyproject requires {python_expr}"
        )
    if header["supported_os"] and header["supported_os"] != sorted(SUPPORTED_OS):
        errors.append(
            f"{DOC} supported_os {header['supported_os']} != policy {sorted(SUPPORTED_OS)}"
        )

    all_results = _load_all_results()

    missing_wf = [wf for wf in WORKFLOW_FILES if not (ROOT / ".github" / "workflows" / wf).exists()]
    for wf in missing_wf:
        errors.append(f".github/workflows/{wf} not found")

    actual = _actual_combo_sets(all_results)
    _check_declared_workflow_match(declared, actual, errors)
    _check_os_and_python_policy(all_results, python_expr, errors)

    payload = {
        "ok": not errors,
        "errors": errors,
        "python_requires": python_expr or DEFAULT_REQUIRES_PYTHON,
        "declared": declared,
        "actual": actual,
    }
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        if payload["ok"]:
            if not quiet:
                print(f"OK: compat matrix matches ({python_expr or DEFAULT_REQUIRES_PYTHON})")
        for err in errors:
            print(f"ERROR: {err}")
    return 0 if payload["ok"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    parser.add_argument("--quiet", action="store_true", help="suppress OK output")
    args = parser.parse_args(argv)
    return check(quiet=args.quiet, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main())
