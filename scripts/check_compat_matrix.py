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
  * Root-project jobs use the range declared in ``pyproject.toml``; explicitly
    listed standalone jobs may use the separate packaged-skill floor.
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
SELF_HOSTED_PLATFORM_LABELS = {"linux", "windows", "macos"}
RECOGNIZED_SELF_HOSTED_CATEGORIES = {
    f"self-hosted-{platform}" for platform in SELF_HOSTED_PLATFORM_LABELS
} | {"self-hosted-unknown", "self-hosted-ambiguous"}
DEFAULT_REQUIRES_PYTHON = ">=3.10,<3.14"
COMPAT_JOBS = ("compat-smoke", "compat-nightly")
DOC = "docs/dev/compatibility-matrix.md"
PYPROJECT = "pyproject.toml"
PYTHON_SUPPORT = "config/python-support.json"

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


def _python_support() -> dict:
    try:
        value = json.loads((ROOT / PYTHON_SUPPORT).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _validate_python_bound(value: str | None) -> tuple[str, str]:
    """Validate the requires-python bound and return (python_expr, error)."""
    if value is None:
        return "", f"{PYPROJECT} does not declare requires-python"
    lower = re.search(r">=\s*([0-9.]+)", value)
    upper = re.search(r"<\s*([0-9.]+)", value)
    if not lower or not upper:
        return "", (
            f"{PYPROJECT} requires-python='{value}' is not a bounded range "
            "(expected '>=LOWER,<UPPER')"
        )
    return value, ""


def _matrix_os(
    runs_on: str | list | None, matrix: dict | None, python_ver: str | None
) -> list[str]:
    """Resolve the set of OS labels for a job from its matrix + runs-on.

    A literal ``runs-on`` (not a matrix expression) IS the actual runner OS,
    regardless of any remaining matrix axes, so it wins. Only when
    ``runs-on`` is itself a matrix expression (``${{ matrix.os }}``) is the
    OS set expanded from ``matrix.os``. This stops the checker from crediting
    an OS axis that ``runs-on`` no longer actually dispatches on (hence
    hardcoding ``runs-on: ubuntu-latest`` while leaving a stale OS matrix no
    longer hides Windows/macOS from drift detection).
    """
    if isinstance(runs_on, list):
        # A list is a conjunction of runner labels, not a list of operating
        # systems. Keep self-hosted platforms distinct from GitHub-hosted
        # images: ``linux`` does not imply ``ubuntu-latest``.
        labels = [str(item).strip() for item in runs_on]
        normalized = {label.casefold() for label in labels}
        if "self-hosted" in normalized:
            if any(_is_expr(label) for label in labels):
                return ["self-hosted-unknown"]
            platforms = normalized & SELF_HOSTED_PLATFORM_LABELS
            if len(platforms) == 1:
                return [f"self-hosted-{next(iter(platforms))}"]
            if not platforms:
                return ["self-hosted-unknown"]
            return ["self-hosted-ambiguous"]
        # GitHub documents list-form runs-on for self-hosted label matching.
        # A list without that marker is not a hosted-image declaration, so
        # retain an explicitly unsupported category and fail closed later.
        return ["runner-labels-unsupported"]
    if runs_on and not _is_expr(runs_on):
        return [str(runs_on)]
    if isinstance(matrix, dict) and isinstance(matrix.get("os"), list):
        return [str(x) for x in matrix["os"]]
    if runs_on:
        return [str(runs_on)]
    return []


def _matrix_python(python_ver: str | None, matrix: dict | None) -> list[str | None]:
    """Resolve the set of Python versions for a job from its setup-python step."""
    if isinstance(matrix, dict):
        for axis in ("python", "python-version"):
            if isinstance(matrix.get(axis), list):
                return [str(x) for x in matrix[axis]]
    return [python_ver]


def _step_python_ver(step: dict) -> str | None:
    """Return the target Python version from an actions/setup-python step, if any."""
    if "actions/setup-python@" not in str(step.get("uses", "")):
        return None
    with_ = step.get("with", {}) or {}
    return with_.get("python-version")


def _combo_matches(combo: JobCombo, item: dict) -> bool:
    """True if ``item`` (a matrix exclude/include entry) covers ``combo``."""
    if "os" in item and combo.os != str(item["os"]):
        return False
    if "python" in item and (combo.python or "none") != str(item["python"]):
        return False
    return True


def _apply_matrix_extras(
    combos: list[JobCombo], matrix: dict | None, default_python: str | None
) -> list[JobCombo]:
    """Apply GitHub ``matrix.exclude`` / ``matrix.include`` semantics.

    GitHub computes the axis product, removes any combo matched by an
    ``exclude`` entry, then appends any ``include`` entry not already present.
    Matching an ``exclude`` entry with only ``os`` removes the whole OS axis.
    """
    if not isinstance(matrix, dict):
        return combos
    exclude = matrix.get("exclude") or []
    if isinstance(exclude, list):
        combos = [
            c
            for c in combos
            if not any(_combo_matches(c, i) for i in exclude if isinstance(i, dict))
        ]
    include = matrix.get("include") or []
    if isinstance(include, list):
        seen = {c.key() for c in combos}
        for item in include:
            if not isinstance(item, dict) or "os" not in item:
                continue
            py_val = str(item["python"]) if "python" in item else default_python
            new_combo = JobCombo(os=str(item["os"]), python=py_val)
            if new_combo.key() not in seen:
                combos.append(new_combo)
                seen.add(new_combo.key())
    return combos


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
        combos = _apply_matrix_extras(combos, matrix, python_ver)
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
        matches = [result for result in all_results.values() if result.job == job]
        if not matches:
            out[job] = {"os": [], "python": []}
            continue
        result = matches[0]
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
    all_results: dict[str, JobResult],
    python_expr: str,
    standalone_floor: str,
    standalone_jobs: set[str],
    allowed_self_hosted: set[str],
    errors: list[str],
) -> None:
    lower, upper = _bound_range(python_expr)
    for qualified_job, result in all_results.items():
        for combo in result.combos:
            if combo.os not in SUPPORTED_OS and combo.os not in allowed_self_hosted:
                errors.append(
                    f"{qualified_job}: runner target {combo.os!r} is outside supported set"
                )
            if combo.python is None:
                if result.job not in NO_SETUP_PYTHON_JOBS:
                    errors.append(f"{qualified_job}: could not resolve a Python version")
                continue
            job_lower = standalone_floor if qualified_job in standalone_jobs else lower
            if not _in_range(combo.python, job_lower, upper):
                errors.append(
                    f"{qualified_job}: Python {combo.python} is outside supported range "
                    f"[{job_lower}, {upper})"
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
    # Scan every workflow, not just the two known compatibility files, so a
    # future workflow that runs a job on an unsupported OS/Python in range is
    # caught by the policy leg instead of silently escaping the drift guard.
    all_results: dict[str, JobResult] = {}
    wf_dir = ROOT / ".github" / "workflows"
    for path in sorted(wf_dir.glob("*.y*ml")):
        for job_id, result in _extract_jobs(_load_yaml_text(path)).items():
            all_results[f"{path.name}:{job_id}"] = result
    return all_results


def check(quiet: bool = False, as_json: bool = False) -> int:
    errors: list[str] = []
    python_expr, bound_error = _validate_python_bound(_requires_python())
    if bound_error:
        errors.append(bound_error)
    support = _python_support()
    standalone_floor = str(support.get("standalone_skills_minimum", ""))
    standalone_jobs_raw = support.get("standalone_workflow_jobs", [])
    standalone_jobs = (
        {str(item) for item in standalone_jobs_raw}
        if isinstance(standalone_jobs_raw, list)
        else set()
    )
    allowed_self_hosted_raw = support.get("allowed_self_hosted_runner_categories")
    allowed_self_hosted = (
        {str(item) for item in allowed_self_hosted_raw}
        if isinstance(allowed_self_hosted_raw, list)
        else set()
    )
    if support.get("root_project") != python_expr:
        errors.append(
            f"{PYTHON_SUPPORT} root_project {support.get('root_project')!r} "
            f"!= {PYPROJECT} requires-python {python_expr!r}"
        )
    if not re.fullmatch(r"\d+\.\d+", standalone_floor):
        errors.append(f"{PYTHON_SUPPORT} has invalid standalone_skills_minimum")
    if not standalone_jobs:
        errors.append(f"{PYTHON_SUPPORT} has no standalone_workflow_jobs")
    if not isinstance(allowed_self_hosted_raw, list):
        errors.append(f"{PYTHON_SUPPORT} has invalid allowed_self_hosted_runner_categories")
    unknown_self_hosted = allowed_self_hosted - RECOGNIZED_SELF_HOSTED_CATEGORIES
    if unknown_self_hosted:
        errors.append(
            f"{PYTHON_SUPPORT} has unknown self-hosted runner categories: "
            f"{sorted(unknown_self_hosted)}"
        )

    declared = _declared_from_doc()
    if not declared or all(not v["os"] for v in declared.values()):
        errors.append(f"{DOC} missing compatible compat_matrix job mapping")

    header = _doc_header()
    if not header["python"]:
        errors.append(f"{DOC} missing top-level `python` declaration")
    elif python_expr and header["python"] != python_expr:
        errors.append(
            f"{DOC} declares python {header['python']} but pyproject requires {python_expr}"
        )
    if not header["supported_os"]:
        errors.append(f"{DOC} missing top-level `supported_os` declaration")
    elif header["supported_os"] != sorted(SUPPORTED_OS):
        errors.append(
            f"{DOC} supported_os {header['supported_os']} != policy {sorted(SUPPORTED_OS)}"
        )

    all_results = _load_all_results()

    missing_wf = [wf for wf in WORKFLOW_FILES if not (ROOT / ".github" / "workflows" / wf).exists()]
    for wf in missing_wf:
        errors.append(f".github/workflows/{wf} not found")

    actual = _actual_combo_sets(all_results)
    _check_declared_workflow_match(declared, actual, errors)
    _check_os_and_python_policy(
        all_results,
        python_expr,
        standalone_floor or "999",
        standalone_jobs,
        allowed_self_hosted,
        errors,
    )

    payload = {
        "ok": not errors,
        "errors": errors,
        "python_requires": python_expr or DEFAULT_REQUIRES_PYTHON,
        "allowed_self_hosted_runner_categories": sorted(allowed_self_hosted),
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
