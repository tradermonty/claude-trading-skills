#!/usr/bin/env python3
"""Offline action/exception policy and complete, marker-independent uv.lock audit."""

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

try:
    import tomllib
except ImportError:  # Python 3.9/3.10
    import tomli as tomllib


class PolicyError(ValueError):
    """Invalid policy, input, or incomplete audit evidence."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(text):
    return json.loads(text, object_pairs_hook=_unique_object)


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject ambiguous YAML mappings instead of silently keeping the last key."""


def _unique_yaml_mapping(loader, node):
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise PolicyError("YAML mapping keys must be scalar") from exc
        if duplicate:
            raise PolicyError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_yaml_mapping
)


def load_exceptions(path, today=None):
    data = read_json(Path(path).read_text())
    if not isinstance(data, dict) or set(data) != {"schema_version", "vulnerabilities"}:
        raise PolicyError("Exceptions require only schema_version and vulnerabilities")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise PolicyError("Unsupported exceptions schema_version")
    if not isinstance(data["vulnerabilities"], list):
        raise PolicyError("vulnerabilities must be a list")
    today = today or dt.datetime.now(dt.timezone.utc).date()
    seen = set()
    for item in data["vulnerabilities"]:
        fields = {"package", "version", "advisory", "owner", "reason", "expires_on"}
        if not isinstance(item, dict) or set(item) != fields:
            raise PolicyError("Exception has missing or unknown fields")
        if any(not isinstance(v, str) or not v.strip() or v != v.strip() for v in item.values()):
            raise PolicyError("Exception fields must be nonempty trimmed strings")
        _validate_pair(item["package"], item["version"])
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", item["advisory"]):
            raise PolicyError("advisory must be an exact identifier")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", item["expires_on"]):
            raise PolicyError("expires_on must be YYYY-MM-DD (UTC)")
        try:
            expiry = dt.date.fromisoformat(item["expires_on"])
        except ValueError as exc:
            raise PolicyError("Invalid expires_on date") from exc
        if expiry <= today:
            raise PolicyError("Exception expired or expires today (UTC)")
        identity = (canonicalize_name(item["package"]), item["version"], item["advisory"])
        if identity in seen:
            raise PolicyError("Duplicate vulnerability exception")
        seen.add(identity)
    return seen


def _validate_pair(name, version):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name):
        raise PolicyError("Invalid package name")
    if not isinstance(version, str) or not version or any(c.isspace() for c in version):
        raise PolicyError("Invalid package version")
    try:
        Version(version)
    except InvalidVersion as exc:
        raise PolicyError("Invalid package version") from exc


def check_actions(root):
    root = Path(root).resolve()
    paths = set((root / ".github/workflows").glob("*.yml"))
    paths.update((root / ".github/workflows").glob("*.yaml"))
    paths.update(root.rglob("action.yml"))
    paths.update(root.rglob("action.yaml"))
    # Avoid interpreting vendored environments as repository actions.
    paths = {
        p
        for p in paths
        if not any(x in {".git", ".venv", "node_modules"} for x in p.relative_to(root).parts)
    }
    if not paths:
        raise PolicyError("No workflow/action definitions found")

    def inspect(value, path):
        if isinstance(value, list):
            for entry in value:
                inspect(entry, path)
        elif isinstance(value, dict):
            for key, entry in value.items():
                if key != "uses":
                    inspect(entry, path)
                    continue
                if not isinstance(entry, str):
                    raise PolicyError(f"{path}: uses must be a string")
                if entry.startswith("./"):
                    target = (root / entry).resolve()
                    if not target.is_relative_to(root):
                        raise PolicyError(f"{path}: local action escapes repository")
                    if target.suffix in {".yml", ".yaml"}:
                        valid = target in paths
                    else:
                        valid = any(
                            target / filename in paths for filename in ("action.yml", "action.yaml")
                        )
                    if not valid:
                        raise PolicyError(f"{path}: uninspected local action {entry}")
                elif entry.startswith("docker://"):
                    if not re.fullmatch(r"docker://[^\s@]+@sha256:[0-9a-fA-F]{64}", entry):
                        raise PolicyError(f"{path}: Docker action must use sha256: {entry}")
                elif not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-fA-F]{40}", entry):
                    raise PolicyError(f"{path}: action must use full commit SHA: {entry}")

    for path in sorted(paths):
        data = yaml.load(path.read_text(), Loader=UniqueKeyLoader)
        if not isinstance(data, dict):
            raise PolicyError(f"{path}: invalid workflow/action document")
        runs = data.get("runs")
        if isinstance(runs, dict) and runs.get("using") == "docker":
            # Local Dockerfiles can hide mutable FROM dependencies; unsupported until
            # their complete build inputs have a dedicated policy inspection.
            image = runs.get("image")
            if not isinstance(image, str) or not re.fullmatch(
                r"docker://[^\s@]+@sha256:[0-9a-fA-F]{64}", image
            ):
                raise PolicyError(f"{path}: Docker action image must use a remote sha256 digest")
        inspect(data, path)
    return len(paths)


def lock_inventory(path):
    with Path(path).open("rb") as stream:
        lock = tomllib.load(stream)
    packages = lock.get("package")
    if not isinstance(packages, list) or not packages:
        raise PolicyError("Lock has no packages")
    inventory = set()
    for package in packages:
        if not isinstance(package, dict):
            raise PolicyError("Malformed lock package")
        name, version = package.get("name"), package.get("version")
        _validate_pair(name, version)
        source = package.get("source")
        if source in ({"virtual": "."}, {"editable": "."}) and name == "claude-trading-skills":
            continue
        if (
            not isinstance(source, dict)
            or set(source) != {"registry"}
            or not isinstance(source["registry"], str)
        ):
            raise PolicyError(f"Unsupported lock source for {name}: {source}")
        if source["registry"] != "https://pypi.org/simple":
            raise PolicyError(f"Unsupported registry for {name}: {source['registry']}")
        inventory.add((canonicalize_name(name), version))
    if not inventory:
        raise PolicyError("Lock has no registry packages")
    return inventory


def audit_batches(inventory):
    batches = []
    for name, version in sorted(inventory):
        for batch in batches:
            if all(pair[0] != name for pair in batch):
                batch.append((name, version))
                break
        else:
            batches.append([(name, version)])
    return batches


def evaluate_report(data, expected, exceptions):
    if not isinstance(data, dict) or not isinstance(data.get("dependencies"), list):
        raise PolicyError("Audit report lacks dependencies")
    seen = set()
    blocked = []
    for package in data["dependencies"]:
        if not isinstance(package, dict) or "skip_reason" in package:
            raise PolicyError("Audit skipped or malformed dependency")
        name, version = package.get("name"), package.get("version")
        _validate_pair(name, version)
        pair = (canonicalize_name(name), version)
        if pair in seen:
            raise PolicyError("Duplicate dependency in audit report")
        seen.add(pair)
        vulns = package.get("vulns")
        if not isinstance(vulns, list):
            raise PolicyError("Audit dependency lacks vulnerabilities list")
        for vuln in vulns:
            if (
                not isinstance(vuln, dict)
                or not isinstance(vuln.get("id"), str)
                or not vuln["id"].strip()
            ):
                raise PolicyError("Malformed vulnerability")
            aliases = vuln.get("aliases", [])
            if not isinstance(aliases, list) or any(
                not isinstance(x, str) or not x.strip() for x in aliases
            ):
                raise PolicyError("Malformed vulnerability aliases")
            if not any((*pair, advisory) in exceptions for advisory in [vuln["id"], *aliases]):
                blocked.append({"name": pair[0], "version": version, "id": vuln["id"]})
    if seen != set(expected):
        raise PolicyError(
            f"Audit inventory mismatch: missing={sorted(set(expected) - seen)}, extra={sorted(seen - set(expected))}"
        )
    return blocked


def audit_lock(lock_path, exceptions, report_path):
    report = {"dependencies": [], "batches": [], "errors": []}
    try:
        inventory = lock_inventory(lock_path)
        report["inventory"] = [{"name": n, "version": v} for n, v in sorted(inventory)]
        with tempfile.TemporaryDirectory(prefix="lock-audit-") as directory:
            for index, batch in enumerate(audit_batches(inventory)):
                pins = Path(directory) / f"batch-{index}.txt"
                pins.write_text("".join(f"{n}=={v}\n" for n, v in batch))
                result = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip_audit",
                        "--no-deps",
                        "--disable-pip",
                        "-r",
                        str(pins),
                        "-f",
                        "json",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    check=False,
                )
                report["batches"].append({"returncode": result.returncode, "stderr": result.stderr})
                if result.returncode not in (0, 1):
                    raise PolicyError(f"pip-audit failed with exit code {result.returncode}")
                data = read_json(result.stdout)
                evaluate_report(data, batch, exceptions)
                has_vulns = any(p["vulns"] for p in data["dependencies"])
                if (result.returncode == 1) != has_vulns:
                    raise PolicyError("pip-audit exit code disagrees with report")
                report["dependencies"].extend(data["dependencies"])
        report["blocked"] = evaluate_report(report, inventory, exceptions)
        return 1 if report["blocked"] else 0
    except (PolicyError, ValueError, OSError, subprocess.SubprocessError) as exc:
        report["errors"].append(str(exc))
        return 1
    finally:
        output = Path(report_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "audit"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--report", type=Path, default=Path("reports/supply-chain-audit.json"))
    args = parser.parse_args(argv)
    try:
        exceptions = load_exceptions(args.root / "config/security-exceptions.json")
        if args.command == "check":
            count = check_actions(args.root)
            print(f"Supply-chain policy passed: {count} action/workflow definitions")
            return 0
        return audit_lock(args.root / "uv.lock", exceptions, args.report)
    except (PolicyError, ValueError, OSError, yaml.YAMLError) as exc:
        print(f"Supply-chain policy failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
