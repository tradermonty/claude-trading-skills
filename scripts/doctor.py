#!/usr/bin/env python3
"""Offline, best-effort environment diagnostics; never contacts providers."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNC_HINT = "Run uv sync --locked --extra dev, then uv run python scripts/doctor.py."


def check(name, status, detail, hint=""):
    return {"name": name, "status": status, "detail": detail, "hint": hint}


def python_check(root, version):
    try:
        policy = json.loads((root / "config/python-support.json").read_text(encoding="utf-8"))
        requirement = policy["root_project"]
        match = re.fullmatch(r">=(\d+)\.(\d+),<(\d+)\.(\d+)", requirement)
        if not match:
            raise ValueError
        major_min, minor_min, major_max, minor_max = map(int, match.groups())
        lower, upper = (major_min, minor_min), (major_max, minor_max)
        if lower >= upper:
            raise ValueError
    except (OSError, ValueError, TypeError, KeyError):
        return check(
            "python",
            "unknown",
            "Python support policy could not be read.",
            "Restore config/python-support.json from this checkout's Git revision.",
        )
    supported = lower <= tuple(version[:2]) < upper
    return check(
        "python",
        "ok" if supported else "warning",
        f"Python {version[0]}.{version[1]}; repository requires {requirement}.",
        "" if supported else f"Re-run with Python {requirement}; standalone skill support differs.",
    )


def load_toml(path):
    for module in ("tomllib", "tomli"):
        try:
            parser = importlib.import_module(module)
        except ImportError:
            continue
        with path.open("rb") as stream:
            return parser.load(stream)
    raise ImportError("TOML parser unavailable")


def distribution_check(name):
    try:
        importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return check(f"package:{name}", "warning", "Distribution not installed.", SYNC_HINT)
    except (OSError, ValueError, TypeError):
        return check(f"package:{name}", "unknown", "Distribution metadata unreadable.", SYNC_HINT)
    return check(
        f"package:{name}",
        "ok",
        "Distribution installed; version compatibility and imports not tested.",
    )


def dependency_checks(root):
    try:
        deps = load_toml(root / "pyproject.toml")["project"]["dependencies"]
        if not isinstance(deps, list) or not all(isinstance(dep, str) for dep in deps):
            raise ValueError
    except (ImportError, OSError, ValueError, TypeError, KeyError):
        return [
            check(
                "dependencies",
                "unknown",
                "Project dependencies could not be inspected.",
                "Use Python 3.11+ (built-in TOML parser) or install tomli; restore pyproject.toml if damaged.",
            )
        ]
    checks = []
    for position, dep in enumerate(deps, 1):
        # Only the repository's simple named requirements are supported. Reject
        # URLs, markers and extras instead of silently claiming they were checked.
        match = re.fullmatch(
            r"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\s*(?:>=|<=|==|!=|~=|>|<)[0-9][A-Za-z0-9.*+!_-]*(?:\.[A-Za-z0-9.*+!_-]+)*(?:\s*,\s*(?:>=|<=|==|!=|~=|>|<)[0-9][A-Za-z0-9.*+!_-]*(?:\.[A-Za-z0-9.*+!_-]+)*)?)",
            dep,
        )
        if not match:
            checks.append(
                check(
                    f"dependency:{position}",
                    "unknown",
                    "Unsupported requirement syntax.",
                    "Inspect project.dependencies locally; no requirement text is emitted.",
                )
            )
        else:
            checks.append(distribution_check(match.group(1)))
    return checks


def build_report(root=ROOT, environ=None, version=None):
    environ = os.environ if environ is None else environ
    version = sys.version_info if version is None else version
    checks = [python_check(root, version)]
    checks.extend(dependency_checks(root))
    checks.append(distribution_check("pre-commit"))
    for provider, names in (
        ("FMP", ("FMP_API_KEY",)),
        ("FINVIZ", ("FINVIZ_API_KEY",)),
        ("Alpaca", ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")),
    ):
        present = all(bool(environ.get(name, "").strip()) for name in names)
        checks.append(
            check(
                f"credentials:{provider}",
                "ok" if present else "warning",
                "Required environment variables present; validity not checked."
                if present
                else "One or more required environment variables absent or blank.",
                "" if present else "Set " + " and ".join(names) + " only if using this provider.",
            )
        )
    return {
        "schema_version": 1,
        "mode": "offline",
        "checks": checks,
        "limitations": [
            "No network requests, dotenv reads, installations, or credential validation performed.",
            "Installed distributions do not prove version compatibility or successful imports.",
            "Skillset readiness and provider connectivity are not assessed.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable diagnostics")
    args = parser.parse_args(argv)
    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print("Offline environment doctor (warnings do not change exit status)")
        for item in report["checks"]:
            print(f"[{item['status']}] {item['name']}: {item['detail']}")
            if item["hint"]:
                print(f"  Hint: {item['hint']}")
        for limitation in report["limitations"]:
            print(limitation)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
