#!/usr/bin/env python3
"""Validate standalone ``data_provenance`` blocks or JSON/YAML reports against
the versioned common trading data contract (issue #297).

The contract (see ``docs/dev/data-provenance-contract.md``) mandates that every
data-fetching, screening, and backtesting skill emits an honest provenance block
in its JSON/YAML output. This validator is the shared, versioned gate intended
for use in skill tests and, once hooked up, workflow E2E replay harnesses.

Usage:
    python3 validate_provenance.py --file report.json
    python3 validate_provenance.py --file report.yaml
    python3 validate_provenance.py --stdin

Exit code 0 when the block is valid, 1 when it is invalid, 2 on I/O or parse errors.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml

SCHEMA_VERSION = "1.0"

REQUIRED_FIELDS = (
    "schema_version",
    "provider",
    "endpoint",
    "retrieved_at",
    "as_of",
    "timezone",
    "adjusted",
    "point_in_time",
    "survivorship_free",
    "corporate_actions_handled",
)

# Provenance fields are intentionally global so the contract is versioned in one
# place; each skill references them when emitting a block.
STRING_FIELDS = ("provider", "endpoint", "timezone", "schema_version")
BOOL_FIELDS = (
    "adjusted",
    "point_in_time",
    "survivorship_free",
    "corporate_actions_handled",
)


def _is_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _is_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def validate_provenance(block: Any, schema_version: str = SCHEMA_VERSION) -> list[str]:
    """Return a list of validation errors; an empty list means the block is valid.

    Unknown fields are intentionally permitted so the contract can be extended.
    Each error identifies the offending field and the requirement it violates.
    """
    if not isinstance(block, dict):
        return ["data_provenance must be a mapping"]

    errors: list[str] = []

    declared_version = block.get("schema_version")
    if declared_version is not None and declared_version != schema_version:
        errors.append(
            f"schema_version {declared_version!r} does not match contract {schema_version!r}"
        )

    for field in REQUIRED_FIELDS:
        if field not in block:
            errors.append(f"missing required field: {field}")

    for field in STRING_FIELDS:
        if field in block and (not isinstance(block[field], str) or not block[field].strip()):
            errors.append(f"{field} must be a non-empty string")

    for field in BOOL_FIELDS:
        if field in block and not _is_bool(block[field]):
            errors.append(f"{field} must be a boolean (state honestly, e.g. False)")

    if "retrieved_at" in block and not _is_iso_datetime(block["retrieved_at"]):
        errors.append("retrieved_at must be an ISO-8601 UTC timestamp with timezone")

    if "as_of" in block and not (_is_iso_date(block["as_of"]) or _is_iso_datetime(block["as_of"])):
        errors.append("as_of must be an ISO-8601 date (YYYY-MM-DD)")

    if "timezone" in block and isinstance(block["timezone"], str) and block["timezone"].strip():
        try:
            ZoneInfo(block["timezone"])
        except (KeyError, ValueError):
            errors.append(f"timezone {block['timezone']!r} is not a valid IANA timezone")

    return errors


def load_block(path: Path) -> Any:
    """Load a standalone block or whole report from JSON/YAML by file suffix."""
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    raise ValueError(f"Unsupported file type: {path} (expected .json, .yaml, or .yml)")


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Validate a standalone data_provenance block or a report containing one.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", help="Path to a JSON or YAML standalone block or report")
    source.add_argument("--stdin", action="store_true", help="Read a JSON or YAML block or report")
    args = parser.parse_args(argv)

    try:
        if args.stdin:
            text = sys.stdin.read()
            try:
                block = json.loads(text)
            except json.JSONDecodeError:
                block = yaml.safe_load(text)
        else:
            block = load_block(Path(args.file))
    except (OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if isinstance(block, dict) and "data_provenance" in block:
        block = block["data_provenance"]
    errors = validate_provenance(block)
    if errors:
        print("INVALID data_provenance block")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("OK data_provenance block valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
