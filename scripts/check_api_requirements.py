#!/usr/bin/env python3
"""Check literal credential reads against integration declarations, without imports or I/O to providers."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = {
    "FMP_API_KEY": "fmp",  # pragma: allowlist secret - environment name, not a value
    "FINVIZ_API_KEY": "finviz",  # pragma: allowlist secret - environment name, not a value
    "ALPACA_API_KEY": "alpaca",  # pragma: allowlist secret - environment name, not a value
    "ALPACA_API_KEY_ID": "alpaca",  # pragma: allowlist secret - environment name, not a value
    "ALPACA_SECRET_KEY": "alpaca",  # pragma: allowlist secret - environment name, not a value
    "ALPACA_API_SECRET": "alpaca",  # pragma: allowlist secret - environment name, not a value
    "ALPACA_API_SECRET_KEY": "alpaca",  # pragma: allowlist secret - environment name, not a value
    "APCA_API_KEY_ID": "alpaca",  # pragma: allowlist secret - environment name, not a value
    "APCA_API_SECRET_KEY": "alpaca",  # pragma: allowlist secret - environment name, not a value
}
ACTIVE = {"required", "recommended", "optional"}


def environment_reads(source):
    tree = ast.parse(source)
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name == "os":
                    aliases[item.asname or "os"] = "os"
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for item in node.names:
                if item.name in {"environ", "getenv"}:
                    aliases[item.asname or item.name] = "os." + item.name

    def qualified(node):
        if isinstance(node, ast.Name):
            return aliases.get(node.id, "")
        if isinstance(node, ast.Attribute):
            return qualified(node.value) + "." + node.attr
        return ""

    reads = []
    for node in ast.walk(tree):
        key = None
        if isinstance(node, ast.Call) and qualified(node.func) in {"os.getenv", "os.environ.get"}:
            key = (
                node.args[0]
                if node.args
                else next((k.value for k in node.keywords if k.arg == "key"), None)
            )
        elif isinstance(node, ast.Subscript) and qualified(node.value) == "os.environ":
            key = node.slice
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and key.value in PROVIDERS:
            reads.append((PROVIDERS[key.value], node.lineno, key.value))
    return sorted(set(reads))


def check(root):
    root = Path(root)
    errors = []
    try:
        index = yaml.safe_load((root / "skills-index.yaml").read_text(encoding="utf-8"))
        skills = index["skills"]
        if not isinstance(skills, list):
            raise ValueError("skills must be a list")
        by_id = {}
        for skill in skills:
            sid = skill["id"]
            if (
                not isinstance(sid, str)
                or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", sid)
                or sid in by_id
            ):
                raise ValueError("invalid/duplicate skill id")
            integrations = skill.get("integrations") or []
            if not isinstance(integrations, list) or any(
                not isinstance(i, dict) for i in integrations
            ):
                raise ValueError("invalid integrations")
            declarations = {}
            for item in integrations:
                provider, requirement = item["id"], item["requirement"]
                if (
                    not isinstance(provider, str)
                    or not isinstance(requirement, str)
                    or provider in declarations
                ):
                    raise ValueError("invalid/duplicate integration")
                declarations[provider] = requirement
            by_id[sid] = declarations
            if skill.get("status") == "deprecated":
                continue
            for path in sorted((root / "skills" / sid / "scripts").rglob("*.py")):
                rel = path.relative_to(root).as_posix()
                if (
                    "tests" in path.relative_to(root / "skills" / sid / "scripts").parts
                    or path.name.startswith("test_")
                    or path.name.endswith("_test.py")
                ):
                    continue
                try:
                    reads = environment_reads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeError, SyntaxError) as exc:
                    errors.append(f"API003 {rel}: cannot parse Python ({type(exc).__name__})")
                    continue
                for provider, line, key in reads:
                    if declarations.get(provider) not in ACTIVE:
                        errors.append(
                            f"API001 {rel}:{line}: {key} read requires an active {provider} integration (declared {declarations.get(provider, 'absent')})"
                        )
        for path in sorted((root / "workflows").glob("*.yaml")):
            workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(workflow, dict):
                raise ValueError("invalid workflow")
            if workflow.get("api_profile") != "no-api-basic":
                continue
            steps = workflow.get("steps") or []
            if not isinstance(steps, list):
                raise ValueError("invalid workflow steps")
            for step in steps:
                sid = step["skill"]
                if sid not in by_id:
                    raise ValueError("unknown workflow skill")
                paid = sorted(
                    p
                    for p, req in by_id[sid].items()
                    if p in set(PROVIDERS.values()) and req == "required"
                )
                if paid:
                    errors.append(
                        f"API002 {path.relative_to(root)}: step {step.get('step')} ({sid}) needs {', '.join(paid)}; no-api-basic cannot include paid-required steps, even optional ones"
                    )
    except (OSError, UnicodeError, yaml.YAMLError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"API003 API contract input is invalid ({type(exc).__name__})")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    errors = check(args.project_root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("OK: literal credential readers and no-api workflow steps match declared integrations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
